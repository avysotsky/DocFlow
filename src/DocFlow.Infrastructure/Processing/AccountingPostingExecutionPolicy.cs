using DocFlow.Application.Abstractions;
using DocFlow.Domain.Entities;

namespace DocFlow.Infrastructure.Processing;

public static class AccountingPostingExecutionPolicy
{
    public const int MaxAttempts = 3;
    public const int BaseRetryDelaySeconds = 5;
    public const int MaxRetryDelaySeconds = 60;

    public static AccountingPostingRequest CreateRequest(
        AccountingPostingRecord entity)
        => new(
            entity.Id,
            entity.CustomerId,
            entity.DocumentId,
            entity.TargetAccount,
            entity.IdempotencyKey,
            AccountingBillPayloadJson.Deserialize(entity.PayloadJson));

    public static void ApplyResult(
        AccountingPostingRecord entity,
        AccountingPostingAdapterResult result,
        DateTimeOffset completedAt)
    {
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
}
