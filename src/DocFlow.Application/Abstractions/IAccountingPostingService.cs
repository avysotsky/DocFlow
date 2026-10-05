using DocFlow.Domain.Enums;

namespace DocFlow.Application.Abstractions;

public enum AccountingPostingCreateOutcome
{
    Created,
    Replay,
    Conflict,
    DocumentNotFound,
    InvalidDocumentType,
    DocumentNotReady,
    ExtractionResultNotFound,
    InvalidPayload,
    TargetNotFound,
    UnsupportedProvider
}

public sealed record AccountingPostingSnapshot(
    Guid Id,
    Guid CustomerId,
    Guid DocumentId,
    string Provider,
    string TargetAccount,
    string IdempotencyKey,
    AccountingPostingStatus Status,
    int Attempts,
    DateTimeOffset CreatedAt,
    DateTimeOffset UpdatedAt,
    DateTimeOffset? LastAttemptAt,
    DateTimeOffset? NextAttemptAt,
    string? LastError,
    string? ExternalReference);

public sealed record AccountingPostingCreateResult(
    AccountingPostingCreateOutcome Outcome,
    AccountingPostingSnapshot? Posting = null);

public interface IAccountingPostingService
{
    Task<AccountingPostingCreateResult> CreateAndPostAsync(
        Guid customerId,
        Guid documentId,
        string targetKey,
        string idempotencyKey,
        CancellationToken cancellationToken = default);

    Task<AccountingPostingSnapshot?> GetAsync(
        Guid customerId,
        Guid postingId,
        CancellationToken cancellationToken = default);
}
