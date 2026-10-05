namespace DocFlow.Application.Abstractions;

public enum AccountingPostingAdapterOutcome
{
    Posted,
    RetryableFailure,
    PermanentFailure
}

public sealed record AccountingPostingRequest(
    Guid PostingId,
    Guid CustomerId,
    Guid DocumentId,
    string TargetAccount,
    string IdempotencyKey,
    AccountingBillPayload Payload);

public sealed record AccountingPostingAdapterResult(
    AccountingPostingAdapterOutcome Outcome,
    string? ExternalReference = null,
    string? ErrorSummary = null);

public interface IAccountingPostingAdapter
{
    string Provider { get; }

    Task<AccountingPostingAdapterResult> PostAsync(
        AccountingPostingRequest request,
        CancellationToken cancellationToken = default);
}
