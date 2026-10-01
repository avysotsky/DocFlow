using System.Buffers.Binary;
using System.Globalization;
using System.Security.Cryptography;
using System.Text;
using DocFlow.Api.Retention;
using DocFlow.Application.Abstractions;
using DocFlow.Domain.Entities;
using DocFlow.Infrastructure.Persistence;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Options;

namespace DocFlow.Api.Documents;

public enum DocumentIntakeOutcome
{
    Accepted = 1,
    Rejected = 2,
    Failed = 3
}

public sealed record DocumentIntakeResult(
    DocumentIntakeOutcome Outcome,
    string OriginalFileName,
    Guid? DocumentId = null,
    string? DocumentStatus = null,
    DateTimeOffset? CreatedAt = null,
    DateTimeOffset? DeleteAt = null,
    string? Error = null,
    bool IsReplay = false);

public sealed class DocumentIntakeService
{
    public const long MaxFileSize = 20L * 1024 * 1024;

    private readonly DocFlowDbContext _dbContext;
    private readonly IFileStorage _fileStorage;
    private readonly IDocumentProcessingQueue _documentProcessingQueue;
    private readonly DocumentRetentionOptions _retentionOptions;
    private readonly DocumentIntakeIdempotencyOptions _idempotencyOptions;
    private readonly IHttpContextAccessor _httpContextAccessor;
    private readonly ILogger<DocumentIntakeService> _logger;

    public DocumentIntakeService(
        DocFlowDbContext dbContext,
        IFileStorage fileStorage,
        IDocumentProcessingQueue documentProcessingQueue,
        IOptions<DocumentRetentionOptions> retentionOptions,
        IOptions<DocumentIntakeIdempotencyOptions> idempotencyOptions,
        IHttpContextAccessor httpContextAccessor,
        ILogger<DocumentIntakeService> logger)
    {
        _dbContext = dbContext;
        _fileStorage = fileStorage;
        _documentProcessingQueue = documentProcessingQueue;
        _retentionOptions = retentionOptions.Value;
        _idempotencyOptions = idempotencyOptions.Value;
        _httpContextAccessor = httpContextAccessor;
        _logger = logger;
    }

    public async Task<DocumentIntakeResult> IntakeAsync(
        Guid customerId,
        IFormFile? file,
        CancellationToken cancellationToken = default)
    {
        if (customerId == Guid.Empty)
            throw new ArgumentException("Customer id is required.", nameof(customerId));

        var (idempotencyKey, headerError) = ResolveSingleUploadIdempotencyKey();
        if (headerError is not null)
        {
            return new DocumentIntakeResult(
                DocumentIntakeOutcome.Rejected,
                file?.FileName ?? string.Empty,
                Error: headerError);
        }

        if (idempotencyKey is null)
            return await IntakeWithoutIdempotencyAsync(customerId, file, cancellationToken);

        var fingerprint = await ComputeRequestFingerprintAsync(file, cancellationToken);
        var result = await IntakeWithIdempotencyAsync(
            customerId,
            file,
            idempotencyKey,
            fingerprint,
            cancellationToken);

        if (result.IsReplay && _httpContextAccessor.HttpContext is { } httpContext)
            httpContext.Response.Headers[IntakeIdempotencyKey.ReplayHeaderName] = "true";

        return result;
    }

    public async Task<DocumentIntakeResult> IntakeWithInternalIdempotencyKeyAsync(
        Guid customerId,
        IFormFile? file,
        string internalKey,
        CancellationToken cancellationToken = default)
    {
        if (customerId == Guid.Empty)
            throw new ArgumentException("Customer id is required.", nameof(customerId));
        if (!IntakeIdempotencyKey.IsInternal(internalKey))
            throw new ArgumentException("An internal idempotency key is required.", nameof(internalKey));
        if (internalKey.Length > IntakeIdempotencyRecord.MaxKeyLength)
            throw new ArgumentOutOfRangeException(nameof(internalKey));

        var fingerprint = await ComputeRequestFingerprintAsync(file, cancellationToken);
        return await IntakeWithIdempotencyAsync(
            customerId,
            file,
            internalKey,
            fingerprint,
            cancellationToken);
    }

    private async Task<DocumentIntakeResult> IntakeWithoutIdempotencyAsync(
        Guid customerId,
        IFormFile? file,
        CancellationToken cancellationToken)
    {
        var fileName = file?.FileName ?? string.Empty;
        var validationError = await ValidateAsync(file, cancellationToken);
        if (validationError is not null)
        {
            return new DocumentIntakeResult(
                DocumentIntakeOutcome.Rejected,
                fileName,
                Error: validationError);
        }

        var validatedFile = file!;

        string storageKey;
        try
        {
            await using var input = validatedFile.OpenReadStream();
            storageKey = await _fileStorage.UploadAsync(
                input,
                validatedFile.FileName,
                validatedFile.ContentType,
                cancellationToken);
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            throw;
        }
        catch (Exception exception)
        {
            _logger.LogError(
                exception,
                "Document intake storage upload failed for file {FileName}.",
                validatedFile.FileName);

            return new DocumentIntakeResult(
                DocumentIntakeOutcome.Failed,
                validatedFile.FileName,
                Error: "The document could not be stored.");
        }

        var document = CreateDocument(customerId, validatedFile, storageKey);

        try
        {
            _dbContext.Documents.Add(document);
            await _dbContext.SaveChangesAsync(cancellationToken);
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            _dbContext.Entry(document).State = EntityState.Detached;
            await TryDeleteStoredFileAsync(storageKey);
            throw;
        }
        catch (Exception exception)
        {
            _dbContext.Entry(document).State = EntityState.Detached;
            await TryDeleteStoredFileAsync(storageKey);

            _logger.LogError(
                exception,
                "Document intake persistence failed for file {FileName}.",
                validatedFile.FileName);

            return new DocumentIntakeResult(
                DocumentIntakeOutcome.Failed,
                validatedFile.FileName,
                Error: "The document could not be persisted.");
        }

        await TryEnqueueAsync(document);
        return AcceptedResult(document);
    }

    private async Task<DocumentIntakeResult> IntakeWithIdempotencyAsync(
        Guid customerId,
        IFormFile? file,
        string key,
        string fingerprint,
        CancellationToken cancellationToken)
    {
        await using var transaction = await _dbContext.Database.BeginTransactionAsync(cancellationToken);

        var lockScope = IntakeIdempotencyKey.CreateSingleLockScope(customerId, key);
        await _dbContext.Database.ExecuteSqlInterpolatedAsync(
            $"SELECT pg_advisory_xact_lock(hashtextextended({lockScope}, 0));",
            cancellationToken);

        var existing = await _dbContext.IntakeIdempotencyRecords
            .SingleOrDefaultAsync(
                x => x.CustomerId == customerId && x.Key == key,
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
                    "The Idempotency-Key was already used with a different request payload.");
            }

            var replay = ReplayResult(existing);
            await transaction.CommitAsync(cancellationToken);
            return replay;
        }

        var validationError = await ValidateAsync(file, cancellationToken);
        if (validationError is not null)
        {
            var rejected = new DocumentIntakeResult(
                DocumentIntakeOutcome.Rejected,
                file?.FileName ?? string.Empty,
                Error: validationError);
            IntakeIdempotencyRecord? persistedRejectedRecord = null;

            try
            {
                persistedRejectedRecord = UpsertIdempotencyRecord(
                    existing,
                    customerId,
                    key,
                    fingerprint,
                    rejected,
                    now);
                await _dbContext.SaveChangesAsync(cancellationToken);
                await transaction.CommitAsync(cancellationToken);
                return rejected;
            }
            catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
            {
                if (persistedRejectedRecord is not null)
                    _dbContext.Entry(persistedRejectedRecord).State = EntityState.Detached;
                throw;
            }
            catch (Exception exception)
            {
                if (persistedRejectedRecord is not null)
                    _dbContext.Entry(persistedRejectedRecord).State = EntityState.Detached;

                _logger.LogError(
                    exception,
                    "Could not persist rejected idempotent intake outcome for key {IdempotencyKey}.",
                    key);

                return new DocumentIntakeResult(
                    DocumentIntakeOutcome.Failed,
                    file?.FileName ?? string.Empty,
                    Error: "The document intake result could not be persisted.");
            }
        }

        var validatedFile = file!;
        string storageKey;
        try
        {
            await using var input = validatedFile.OpenReadStream();
            storageKey = await _fileStorage.UploadAsync(
                input,
                validatedFile.FileName,
                validatedFile.ContentType,
                cancellationToken);
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            throw;
        }
        catch (Exception exception)
        {
            _logger.LogError(
                exception,
                "Idempotent document intake storage upload failed for file {FileName}.",
                validatedFile.FileName);

            return new DocumentIntakeResult(
                DocumentIntakeOutcome.Failed,
                validatedFile.FileName,
                Error: "The document could not be stored.");
        }

        var document = CreateDocument(customerId, validatedFile, storageKey);
        var accepted = AcceptedResult(document);
        IntakeIdempotencyRecord? persistedRecord = null;

        try
        {
            _dbContext.Documents.Add(document);
            persistedRecord = UpsertIdempotencyRecord(
                existing,
                customerId,
                key,
                fingerprint,
                accepted,
                now);

            // Once storage succeeds, complete the durable state transition independently from
            // client disconnect. A retry can then replay the committed response.
            await _dbContext.SaveChangesAsync(CancellationToken.None);
            await transaction.CommitAsync(CancellationToken.None);
        }
        catch (Exception exception)
        {
            try
            {
                await transaction.RollbackAsync(CancellationToken.None);
            }
            catch
            {
                // Preserve the original persistence exception.
            }

            _dbContext.Entry(document).State = EntityState.Detached;
            if (persistedRecord is not null)
                _dbContext.Entry(persistedRecord).State = EntityState.Detached;

            await TryDeleteStoredFileAsync(storageKey);

            _logger.LogError(
                exception,
                "Idempotent document intake persistence failed for file {FileName}.",
                validatedFile.FileName);

            return new DocumentIntakeResult(
                DocumentIntakeOutcome.Failed,
                validatedFile.FileName,
                Error: "The document could not be persisted.");
        }

        await TryEnqueueAsync(document);
        return accepted;
    }

    private IntakeIdempotencyRecord UpsertIdempotencyRecord(
        IntakeIdempotencyRecord? existing,
        Guid customerId,
        string key,
        string fingerprint,
        DocumentIntakeResult result,
        DateTimeOffset now)
    {
        var expiresAt = now.AddHours(_idempotencyOptions.RetentionHours);

        if (existing is null)
        {
            var created = new IntakeIdempotencyRecord(
                customerId,
                key,
                fingerprint,
                result.Outcome.ToString(),
                result.OriginalFileName,
                now,
                expiresAt,
                result.DocumentId,
                result.DocumentStatus,
                result.CreatedAt,
                result.DeleteAt,
                result.Error);

            _dbContext.IntakeIdempotencyRecords.Add(created);
            return created;
        }

        existing.Replace(
            fingerprint,
            result.Outcome.ToString(),
            result.OriginalFileName,
            now,
            expiresAt,
            result.DocumentId,
            result.DocumentStatus,
            result.CreatedAt,
            result.DeleteAt,
            result.Error);
        return existing;
    }

    private Document CreateDocument(Guid customerId, IFormFile file, string storageKey)
    {
        var deleteAt = _retentionOptions.Enabled
            ? DateTimeOffset.UtcNow.AddDays(_retentionOptions.DefaultRetentionDays)
            : (DateTimeOffset?)null;

        return new Document(
            customerId,
            file.FileName,
            file.ContentType,
            storageKey,
            file.Length,
            deleteAt);
    }

    private static DocumentIntakeResult AcceptedResult(Document document)
    {
        return new DocumentIntakeResult(
            DocumentIntakeOutcome.Accepted,
            document.OriginalFileName,
            document.Id,
            document.Status.ToString(),
            document.CreatedAt,
            document.DeleteAt);
    }

    private static DocumentIntakeResult ReplayResult(IntakeIdempotencyRecord record)
    {
        if (!Enum.TryParse<DocumentIntakeOutcome>(record.Outcome, out var outcome)
            || outcome is not (DocumentIntakeOutcome.Accepted or DocumentIntakeOutcome.Rejected))
        {
            throw new InvalidOperationException(
                $"Unsupported persisted idempotency outcome '{record.Outcome}'.");
        }

        return new DocumentIntakeResult(
            outcome,
            record.OriginalFileName,
            record.DocumentId,
            record.DocumentStatus,
            record.DocumentCreatedAt,
            record.DocumentDeleteAt,
            record.Error,
            IsReplay: true);
    }

    private async Task TryEnqueueAsync(Document document)
    {
        try
        {
            await _documentProcessingQueue.EnqueueAsync(document.Id, CancellationToken.None);
        }
        catch (Exception exception)
        {
            // A persisted Uploaded document remains recoverable on the next process start and
            // can also be explicitly re-enqueued through POST /api/documents/{id}/process.
            _logger.LogError(
                exception,
                "Document {DocumentId} was persisted but could not be enqueued immediately.",
                document.Id);
        }
    }

    private (string? Key, string? Error) ResolveSingleUploadIdempotencyKey()
    {
        var context = _httpContextAccessor.HttpContext;
        if (context is null
            || !HttpMethods.IsPost(context.Request.Method)
            || !IsSingleUploadPath(context.Request.Path))
        {
            return (null, null);
        }

        return IntakeIdempotencyKey.NormalizeExternal(
            context.Request.Headers[IntakeIdempotencyKey.HeaderName]);
    }

    private static bool IsSingleUploadPath(PathString path)
    {
        return path.Equals(new PathString("/api/documents"))
            || path.Equals(new PathString("/api/documents/"));
    }

    private static async Task<string?> ValidateAsync(
        IFormFile? file,
        CancellationToken cancellationToken)
    {
        if (file is null || file.Length == 0)
            return "A non-empty PDF file is required.";

        if (file.Length > MaxFileSize)
            return "The PDF file must not exceed 20 MB.";

        if (!string.Equals(
                Path.GetExtension(file.FileName),
                ".pdf",
                StringComparison.OrdinalIgnoreCase))
        {
            return "Only PDF files are supported.";
        }

        if (!string.Equals(
                file.ContentType,
                "application/pdf",
                StringComparison.OrdinalIgnoreCase))
        {
            return "The file content type must be application/pdf.";
        }

        var signature = new byte[5];
        await using var stream = file.OpenReadStream();
        var bytesRead = await stream.ReadAsync(
            signature.AsMemory(0, signature.Length),
            cancellationToken);

        var validSignature = bytesRead == signature.Length
            && signature[0] == (byte)'%'
            && signature[1] == (byte)'P'
            && signature[2] == (byte)'D'
            && signature[3] == (byte)'F'
            && signature[4] == (byte)'-';

        return validSignature
            ? null
            : "The uploaded file does not have a valid PDF signature.";
    }

    private static async Task<string> ComputeRequestFingerprintAsync(
        IFormFile? file,
        CancellationToken cancellationToken)
    {
        using var hash = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
        AppendFingerprintComponent(hash, "docflow-intake-v1");
        AppendFingerprintComponent(hash, file?.FileName ?? string.Empty);
        AppendFingerprintComponent(hash, file?.ContentType ?? string.Empty);
        AppendFingerprintComponent(
            hash,
            (file?.Length ?? -1).ToString(CultureInfo.InvariantCulture));

        if (file is not null)
        {
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

    private async Task TryDeleteStoredFileAsync(string storageKey)
    {
        try
        {
            await _fileStorage.DeleteAsync(storageKey, CancellationToken.None);
        }
        catch (Exception cleanupException)
        {
            _logger.LogWarning(
                cleanupException,
                "Document intake rollback could not delete storage object {StorageKey}.",
                storageKey);
        }
    }
}
