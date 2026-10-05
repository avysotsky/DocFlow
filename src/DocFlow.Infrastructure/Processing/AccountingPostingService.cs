using DocFlow.Application.Abstractions;
using DocFlow.Domain.Entities;
using DocFlow.Domain.Enums;
using DocFlow.Infrastructure.Persistence;
using Microsoft.EntityFrameworkCore;
using Npgsql;

namespace DocFlow.Infrastructure.Processing;

public sealed class AccountingPostingService : IAccountingPostingService
{
    private const int MaxAttempts = 3;
    private const int BaseRetryDelaySeconds = 5;
    private const int MaxRetryDelaySeconds = 60;

    private readonly DocFlowDbContext _dbContext;
    private readonly IReadOnlyDictionary<string, IAccountingPostingAdapter> _adapters;

    public AccountingPostingService(
        DocFlowDbContext dbContext,
        IEnumerable<IAccountingPostingAdapter> adapters)
    {
        _dbContext = dbContext;
        _adapters = adapters.ToDictionary(
            adapter => adapter.Provider,
            StringComparer.OrdinalIgnoreCase);
    }

    public async Task<AccountingPostingCreateResult> CreateAndPostAsync(
        Guid customerId,
        Guid documentId,
        string provider,
        string targetAccount,
        string idempotencyKey,
        CancellationToken cancellationToken = default)
    {
        var normalizedProvider = provider.Trim().ToLowerInvariant();
        var normalizedTarget = targetAccount.Trim();
        var normalizedKey = idempotencyKey.Trim();

        if (!_adapters.TryGetValue(normalizedProvider, out var adapter))
        {
            return new AccountingPostingCreateResult(
                AccountingPostingCreateOutcome.UnsupportedProvider);
        }

        var source = await (
                from document in _dbContext.Documents.AsNoTracking()
                join extractionResult in _dbContext.ExtractionResults.AsNoTracking()
                    on document.Id equals extractionResult.DocumentId into extractionResults
                from extractionResult in extractionResults.DefaultIfEmpty()
                join review in _dbContext.DocumentReviews.AsNoTracking()
                    on document.Id equals review.DocumentId into reviews
                from review in reviews.DefaultIfEmpty()
                where document.Id == documentId && document.CustomerId == customerId
                select new
                {
                    Document = document,
                    ExtractionResult = extractionResult,
                    Review = review
                })
            .SingleOrDefaultAsync(cancellationToken);

        if (source is null)
        {
            return new AccountingPostingCreateResult(
                AccountingPostingCreateOutcome.DocumentNotFound);
        }

        if (!string.Equals(
                source.Document.DocumentType,
                "supplier_invoice",
                StringComparison.OrdinalIgnoreCase))
        {
            return new AccountingPostingCreateResult(
                AccountingPostingCreateOutcome.InvalidDocumentType);
        }

        if (source.Document.Status != DocumentStatus.Processed)
        {
            return new AccountingPostingCreateResult(
                AccountingPostingCreateOutcome.DocumentNotReady);
        }

        if (source.ExtractionResult is null)
        {
            return new AccountingPostingCreateResult(
                AccountingPostingCreateOutcome.ExtractionResultNotFound);
        }

        var payloadJson = ReviewedStructuredDataComposer.Compose(
            source.ExtractionResult.StructuredDataJson,
            source.Review);

        var existing = await FindByIdempotencyScopeAsync(
            customerId,
            normalizedProvider,
            normalizedTarget,
            normalizedKey,
            cancellationToken);

        if (existing is not null)
            return ReplayOrConflict(existing, documentId, payloadJson);

        var entity = new AccountingPostingRecord(
            customerId,
            documentId,
            normalizedProvider,
            normalizedTarget,
            normalizedKey,
            payloadJson);

        _dbContext.AccountingPostingRecords.Add(entity);

        try
        {
            await _dbContext.SaveChangesAsync(cancellationToken);
        }
        catch (DbUpdateException exception)
            when (exception.InnerException is PostgresException
            {
                SqlState: PostgresErrorCodes.UniqueViolation,
                ConstraintName: "UX_AccountingPostingRecords_Idempotency"
            })
        {
            _dbContext.Entry(entity).State = EntityState.Detached;

            existing = await FindByIdempotencyScopeAsync(
                customerId,
                normalizedProvider,
                normalizedTarget,
                normalizedKey,
                cancellationToken);

            if (existing is null)
                throw;

            return ReplayOrConflict(existing, documentId, payloadJson);
        }

        entity.MarkAttemptStarted(DateTimeOffset.UtcNow);
        await _dbContext.SaveChangesAsync(cancellationToken);

        AccountingPostingAdapterResult adapterResult;
        try
        {
            adapterResult = await adapter.PostAsync(
                new AccountingPostingRequest(
                    entity.Id,
                    entity.CustomerId,
                    entity.DocumentId,
                    entity.TargetAccount,
                    entity.IdempotencyKey,
                    entity.PayloadJson),
                cancellationToken);
        }
        catch (OperationCanceledException)
            when (cancellationToken.IsCancellationRequested)
        {
            throw;
        }
        catch (Exception exception)
        {
            adapterResult = new AccountingPostingAdapterResult(
                AccountingPostingAdapterOutcome.RetryableFailure,
                ErrorSummary: exception.Message);
        }

        ApplyAdapterResult(entity, adapterResult);
        await _dbContext.SaveChangesAsync(CancellationToken.None);

        return new AccountingPostingCreateResult(
            AccountingPostingCreateOutcome.Created,
            ToSnapshot(entity));
    }

    public async Task<AccountingPostingSnapshot?> GetAsync(
        Guid customerId,
        Guid postingId,
        CancellationToken cancellationToken = default)
    {
        var entity = await _dbContext.AccountingPostingRecords
            .AsNoTracking()
            .SingleOrDefaultAsync(
                item => item.Id == postingId && item.CustomerId == customerId,
                cancellationToken);

        return entity is null ? null : ToSnapshot(entity);
    }

    private async Task<AccountingPostingRecord?> FindByIdempotencyScopeAsync(
        Guid customerId,
        string provider,
        string targetAccount,
        string idempotencyKey,
        CancellationToken cancellationToken)
        => await _dbContext.AccountingPostingRecords
            .AsNoTracking()
            .SingleOrDefaultAsync(
                item => item.CustomerId == customerId
                    && item.Provider == provider
                    && item.TargetAccount == targetAccount
                    && item.IdempotencyKey == idempotencyKey,
                cancellationToken);

    private static AccountingPostingCreateResult ReplayOrConflict(
        AccountingPostingRecord existing,
        Guid documentId,
        string payloadJson)
    {
        var sameRequest = existing.DocumentId == documentId
            && string.Equals(
                existing.PayloadJson,
                payloadJson,
                StringComparison.Ordinal);

        return new AccountingPostingCreateResult(
            sameRequest
                ? AccountingPostingCreateOutcome.Replay
                : AccountingPostingCreateOutcome.Conflict,
            sameRequest ? ToSnapshot(existing) : null);
    }

    private static void ApplyAdapterResult(
        AccountingPostingRecord entity,
        AccountingPostingAdapterResult result)
    {
        var completedAt = DateTimeOffset.UtcNow;

        switch (result.Outcome)
        {
            case AccountingPostingAdapterOutcome.Posted:
                entity.MarkPosted(
                    completedAt,
                    result.ExternalReference
                        ?? throw new InvalidOperationException(
                            "Posted accounting result requires an external reference."));
                break;

            case AccountingPostingAdapterOutcome.RetryableFailure:
                entity.MarkAttemptFailed(
                    completedAt,
                    result.ErrorSummary ?? "Accounting provider request failed.",
                    MaxAttempts,
                    BaseRetryDelaySeconds,
                    MaxRetryDelaySeconds);
                break;

            case AccountingPostingAdapterOutcome.PermanentFailure:
                entity.MarkAttemptFailed(
                    completedAt,
                    result.ErrorSummary ?? "Accounting provider rejected the request.",
                    maxAttempts: 1,
                    BaseRetryDelaySeconds,
                    MaxRetryDelaySeconds);
                break;

            default:
                throw new InvalidOperationException(
                    $"Unsupported accounting adapter outcome '{result.Outcome}'.");
        }
    }

    private static AccountingPostingSnapshot ToSnapshot(
        AccountingPostingRecord entity)
        => new(
            entity.Id,
            entity.CustomerId,
            entity.DocumentId,
            entity.Provider,
            entity.TargetAccount,
            entity.IdempotencyKey,
            entity.Status,
            entity.Attempts,
            entity.CreatedAt,
            entity.UpdatedAt,
            entity.LastAttemptAt,
            entity.NextAttemptAt,
            entity.LastError,
            entity.ExternalReference);
}
