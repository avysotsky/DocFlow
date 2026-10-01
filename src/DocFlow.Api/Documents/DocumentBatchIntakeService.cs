using System.Buffers.Binary;
using System.Globalization;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using DocFlow.Domain.Entities;
using DocFlow.Infrastructure.Persistence;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Options;

namespace DocFlow.Api.Documents;

public sealed record BatchDocumentIntakeItemResult(
    int Index,
    string OriginalFileName,
    string Outcome,
    Guid? DocumentId,
    string? DocumentStatus,
    DateTimeOffset? CreatedAt,
    DateTimeOffset? DeleteAt,
    string? Error);

public sealed record BatchDocumentIntakeResult(
    int TotalCount,
    int AcceptedCount,
    int RejectedCount,
    int FailedCount,
    BatchDocumentIntakeItemResult[] Items,
    bool IsReplay = false);

public sealed class DocumentBatchIntakeService
{
    private static readonly JsonSerializerOptions SnapshotJsonOptions =
        new(JsonSerializerDefaults.Web);

    private readonly IServiceScopeFactory _scopeFactory;
    private readonly DocumentIntakeService _documentIntakeService;
    private readonly DocumentIntakeIdempotencyOptions _idempotencyOptions;
    private readonly ILogger<DocumentBatchIntakeService> _logger;

    public DocumentBatchIntakeService(
        IServiceScopeFactory scopeFactory,
        DocumentIntakeService documentIntakeService,
        IOptions<DocumentIntakeIdempotencyOptions> idempotencyOptions,
        ILogger<DocumentBatchIntakeService> logger)
    {
        _scopeFactory = scopeFactory;
        _documentIntakeService = documentIntakeService;
        _idempotencyOptions = idempotencyOptions.Value;
        _logger = logger;
    }

    public async Task<BatchDocumentIntakeResult> IntakeAsync(
        Guid customerId,
        IReadOnlyList<IFormFile> files,
        string? idempotencyKey,
        CancellationToken cancellationToken = default)
    {
        if (customerId == Guid.Empty)
            throw new ArgumentException("Customer id is required.", nameof(customerId));

        if (idempotencyKey is null)
            return await ProcessBatchAsync(customerId, files, null, cancellationToken);

        var fingerprint = await ComputeBatchFingerprintAsync(files, cancellationToken);
        var prepared = await PrepareManifestAsync(
            customerId,
            idempotencyKey,
            fingerprint,
            cancellationToken);

        if (prepared.Replay is not null)
            return prepared.Replay with { IsReplay = true };

        var result = await ProcessBatchAsync(
            customerId,
            files,
            prepared.GenerationId,
            cancellationToken);

        if (result.FailedCount != 0)
            return result;

        return await TryCompleteManifestAsync(
            customerId,
            idempotencyKey,
            fingerprint,
            prepared.GenerationId,
            result);
    }

    private async Task<BatchDocumentIntakeResult> ProcessBatchAsync(
        Guid customerId,
        IReadOnlyList<IFormFile> files,
        Guid? generationId,
        CancellationToken cancellationToken)
    {
        var items = new List<BatchDocumentIntakeItemResult>(files.Count);
        var accepted = 0;
        var rejected = 0;
        var failed = 0;

        for (var index = 0; index < files.Count; index++)
        {
            DocumentIntakeResult result;
            if (generationId is null)
            {
                result = await _documentIntakeService.IntakeAsync(
                    customerId,
                    files[index],
                    cancellationToken);
            }
            else
            {
                var internalKey = IntakeIdempotencyKey.CreateBatchItemKey(
                    generationId.Value,
                    index);
                result = await _documentIntakeService.IntakeWithInternalIdempotencyKeyAsync(
                    customerId,
                    files[index],
                    internalKey,
                    cancellationToken);
            }

            switch (result.Outcome)
            {
                case DocumentIntakeOutcome.Accepted:
                    accepted++;
                    break;
                case DocumentIntakeOutcome.Rejected:
                    rejected++;
                    break;
                case DocumentIntakeOutcome.Failed:
                    failed++;
                    break;
                default:
                    throw new InvalidOperationException(
                        $"Unsupported document intake outcome '{result.Outcome}'.");
            }

            items.Add(new BatchDocumentIntakeItemResult(
                index,
                result.OriginalFileName,
                result.Outcome.ToString(),
                result.DocumentId,
                result.DocumentStatus,
                result.CreatedAt,
                result.DeleteAt,
                result.Error));
        }

        return new BatchDocumentIntakeResult(
            files.Count,
            accepted,
            rejected,
            failed,
            items.ToArray());
    }

    private async Task<PreparedManifest> PrepareManifestAsync(
        Guid customerId,
        string key,
        string fingerprint,
        CancellationToken cancellationToken)
    {
        await using var scope = _scopeFactory.CreateAsyncScope();
        var dbContext = scope.ServiceProvider.GetRequiredService<DocFlowDbContext>();
        await using var transaction = await dbContext.Database.BeginTransactionAsync(cancellationToken);

        var lockScope = IntakeIdempotencyKey.CreateBatchLockScope(customerId, key);
        await dbContext.Database.ExecuteSqlInterpolatedAsync(
            $"SELECT pg_advisory_xact_lock(hashtextextended({lockScope}, 0));",
            cancellationToken);

        var existing = await dbContext.BatchIntakeIdempotencyRecords
            .SingleOrDefaultAsync(
                record => record.CustomerId == customerId && record.Key == key,
                cancellationToken);

        var now = DateTimeOffset.UtcNow;
        if (existing is not null && existing.ExpiresAt > now)
        {
            if (!string.Equals(
                    existing.RequestFingerprint,
                    fingerprint,
                    StringComparison.Ordinal))
            {
                throw new IntakeIdempotencyConflictException(
                    "The Idempotency-Key was already used with a different batch request payload.");
            }

            var replay = existing.ResponseJson is null
                ? null
                : DeserializeSnapshot(existing.ResponseJson);

            await transaction.CommitAsync(cancellationToken);
            return new PreparedManifest(existing.GenerationId, replay);
        }

        var generationId = Guid.NewGuid();
        var expiresAt = now.AddHours(_idempotencyOptions.RetentionHours);

        if (existing is null)
        {
            dbContext.BatchIntakeIdempotencyRecords.Add(
                new BatchIntakeIdempotencyRecord(
                    customerId,
                    key,
                    fingerprint,
                    generationId,
                    now,
                    expiresAt));
        }
        else
        {
            existing.Replace(fingerprint, generationId, now, expiresAt);
        }

        await dbContext.SaveChangesAsync(cancellationToken);
        await transaction.CommitAsync(cancellationToken);
        return new PreparedManifest(generationId, null);
    }

    private async Task<BatchDocumentIntakeResult> TryCompleteManifestAsync(
        Guid customerId,
        string key,
        string fingerprint,
        Guid generationId,
        BatchDocumentIntakeResult result)
    {
        try
        {
            await using var scope = _scopeFactory.CreateAsyncScope();
            var dbContext = scope.ServiceProvider.GetRequiredService<DocFlowDbContext>();
            await using var transaction = await dbContext.Database.BeginTransactionAsync(
                CancellationToken.None);

            var lockScope = IntakeIdempotencyKey.CreateBatchLockScope(customerId, key);
            await dbContext.Database.ExecuteSqlInterpolatedAsync(
                $"SELECT pg_advisory_xact_lock(hashtextextended({lockScope}, 0));",
                CancellationToken.None);

            var existing = await dbContext.BatchIntakeIdempotencyRecords
                .SingleOrDefaultAsync(
                    record => record.CustomerId == customerId && record.Key == key,
                    CancellationToken.None);

            if (existing is null
                || existing.GenerationId != generationId
                || existing.ExpiresAt <= DateTimeOffset.UtcNow
                || !string.Equals(
                    existing.RequestFingerprint,
                    fingerprint,
                    StringComparison.Ordinal))
            {
                _logger.LogWarning(
                    "Batch idempotency manifest changed before completion for tenant {CustomerId}.",
                    customerId);
                await transaction.CommitAsync(CancellationToken.None);
                return result;
            }

            if (existing.ResponseJson is not null)
            {
                var replay = DeserializeSnapshot(existing.ResponseJson);
                await transaction.CommitAsync(CancellationToken.None);
                return replay with { IsReplay = true };
            }

            existing.Complete(SerializeSnapshot(result));
            await dbContext.SaveChangesAsync(CancellationToken.None);
            await transaction.CommitAsync(CancellationToken.None);
            return result;
        }
        catch (Exception exception)
        {
            // All accepted/rejected item checkpoints are already durable. Leaving the manifest
            // incomplete is safe: a retry reuses the same generation and replays those items.
            _logger.LogError(
                exception,
                "Could not persist completed batch idempotency response for tenant {CustomerId}.",
                customerId);
            return result;
        }
    }

    private static async Task<string> ComputeBatchFingerprintAsync(
        IReadOnlyList<IFormFile> files,
        CancellationToken cancellationToken)
    {
        using var hash = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
        AppendFingerprintComponent(hash, "docflow-batch-intake-v1");
        AppendFingerprintComponent(hash, files.Count.ToString(CultureInfo.InvariantCulture));

        for (var index = 0; index < files.Count; index++)
        {
            var file = files[index];
            AppendFingerprintComponent(hash, index.ToString(CultureInfo.InvariantCulture));
            AppendFingerprintComponent(hash, file.FileName);
            AppendFingerprintComponent(hash, file.ContentType);
            AppendFingerprintComponent(hash, file.Length.ToString(CultureInfo.InvariantCulture));

            await using var stream = file.OpenReadStream();
            var buffer = new byte[81920];
            while (true)
            {
                var bytesRead = await stream.ReadAsync(buffer.AsMemory(), cancellationToken);
                if (bytesRead == 0)
                    break;

                hash.AppendData(buffer.AsSpan(0, bytesRead));
            }
        }

        return Convert.ToHexString(hash.GetHashAndReset()).ToLowerInvariant();
    }

    private static void AppendFingerprintComponent(IncrementalHash hash, string value)
    {
        var bytes = Encoding.UTF8.GetBytes(value);
        Span<byte> length = stackalloc byte[4];
        BinaryPrimitives.WriteInt32LittleEndian(length, bytes.Length);
        hash.AppendData(length);
        hash.AppendData(bytes);
    }

    private static string SerializeSnapshot(BatchDocumentIntakeResult result)
    {
        return JsonSerializer.Serialize(
            result with { IsReplay = false },
            SnapshotJsonOptions);
    }

    private static BatchDocumentIntakeResult DeserializeSnapshot(string json)
    {
        return JsonSerializer.Deserialize<BatchDocumentIntakeResult>(
                   json,
                   SnapshotJsonOptions)
               ?? throw new InvalidOperationException(
                   "Persisted batch idempotency response could not be deserialized.");
    }

    private sealed record PreparedManifest(
        Guid GenerationId,
        BatchDocumentIntakeResult? Replay);
}
