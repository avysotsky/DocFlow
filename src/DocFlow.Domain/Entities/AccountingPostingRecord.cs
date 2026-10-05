using DocFlow.Domain.Enums;

namespace DocFlow.Domain.Entities;

public sealed class AccountingPostingRecord
{
    public const int MaxProviderLength = 64;
    public const int MaxTargetKeyLength = 100;
    public const int MaxTargetAccountLength = 200;
    public const int MaxIdempotencyKeyLength = 128;
    public const int MaxExternalReferenceLength = 200;
    public const int MaxErrorLength = 500;

    public Guid Id { get; private set; }
    public Guid CustomerId { get; private set; }
    public Guid DocumentId { get; private set; }
    public string Provider { get; private set; } = string.Empty;
    public string TargetKey { get; private set; } = string.Empty;
    public string TargetAccount { get; private set; } = string.Empty;
    public string IdempotencyKey { get; private set; } = string.Empty;
    public string PayloadJson { get; private set; } = string.Empty;
    public AccountingPostingStatus Status { get; private set; }
    public int Attempts { get; private set; }
    public DateTimeOffset CreatedAt { get; private set; }
    public DateTimeOffset UpdatedAt { get; private set; }
    public DateTimeOffset? LastAttemptAt { get; private set; }
    public DateTimeOffset? NextAttemptAt { get; private set; }
    public string? LastError { get; private set; }
    public string? ExternalReference { get; private set; }

    private AccountingPostingRecord()
    {
    }

    public AccountingPostingRecord(
        Guid customerId,
        Guid documentId,
        string provider,
        string targetKey,
        string targetAccount,
        string idempotencyKey,
        string payloadJson)
    {
        if (customerId == Guid.Empty)
            throw new ArgumentException("Customer id is required.", nameof(customerId));
        if (documentId == Guid.Empty)
            throw new ArgumentException("Document id is required.", nameof(documentId));

        Provider = NormalizeRequired(
            provider,
            MaxProviderLength,
            nameof(provider))
            .ToLowerInvariant();
        TargetKey = NormalizeRequired(
            targetKey,
            MaxTargetKeyLength,
            nameof(targetKey));
        TargetAccount = NormalizeRequired(
            targetAccount,
            MaxTargetAccountLength,
            nameof(targetAccount));
        IdempotencyKey = NormalizeRequired(
            idempotencyKey,
            MaxIdempotencyKeyLength,
            nameof(idempotencyKey));

        if (string.IsNullOrWhiteSpace(payloadJson))
            throw new ArgumentException("Posting payload is required.", nameof(payloadJson));

        Id = Guid.NewGuid();
        CustomerId = customerId;
        DocumentId = documentId;
        PayloadJson = payloadJson;
        Status = AccountingPostingStatus.Pending;
        CreatedAt = DateTimeOffset.UtcNow;
        UpdatedAt = CreatedAt;
        NextAttemptAt = CreatedAt;
    }

    public void MarkAttemptStarted(DateTimeOffset startedAt)
    {
        if (Status is AccountingPostingStatus.Posted or AccountingPostingStatus.Failed)
            throw new InvalidOperationException(
                "A terminal accounting posting cannot be retried.");

        if (Status == AccountingPostingStatus.Posting)
            throw new InvalidOperationException("Accounting posting is already in progress.");

        Attempts = checked(Attempts + 1);
        Status = AccountingPostingStatus.Posting;
        LastAttemptAt = startedAt;
        NextAttemptAt = null;
        LastError = null;
        UpdatedAt = startedAt;
    }

    public void RecoverInterruptedAttempt(DateTimeOffset recoveredAt)
    {
        if (Status != AccountingPostingStatus.Posting)
        {
            throw new InvalidOperationException(
                "Only an in-progress accounting posting can be recovered.");
        }

        Status = AccountingPostingStatus.Pending;
        NextAttemptAt = recoveredAt;
        LastError = "Previous accounting posting attempt was interrupted before completion.";
        UpdatedAt = recoveredAt;
    }

    public void MarkPosted(DateTimeOffset completedAt, string externalReference)
    {
        if (Status != AccountingPostingStatus.Posting)
            throw new InvalidOperationException("Only an in-progress accounting posting can complete.");

        ExternalReference = NormalizeRequired(
            externalReference,
            MaxExternalReferenceLength,
            nameof(externalReference));
        Status = AccountingPostingStatus.Posted;
        LastError = null;
        NextAttemptAt = null;
        UpdatedAt = completedAt;
    }

    public void MarkAttemptFailed(
        DateTimeOffset completedAt,
        string errorSummary,
        int maxAttempts,
        int baseRetryDelaySeconds,
        int maxRetryDelaySeconds)
    {
        if (Status != AccountingPostingStatus.Posting)
            throw new InvalidOperationException("Only an in-progress accounting posting can fail.");
        if (maxAttempts < 1)
            throw new ArgumentOutOfRangeException(nameof(maxAttempts));
        if (baseRetryDelaySeconds < 1)
            throw new ArgumentOutOfRangeException(nameof(baseRetryDelaySeconds));
        if (maxRetryDelaySeconds < baseRetryDelaySeconds)
            throw new ArgumentOutOfRangeException(nameof(maxRetryDelaySeconds));
        if (string.IsNullOrWhiteSpace(errorSummary))
            throw new ArgumentException("Posting error summary is required.", nameof(errorSummary));

        var normalizedError = errorSummary.Trim();
        LastError = normalizedError.Length <= MaxErrorLength
            ? normalizedError
            : normalizedError[..MaxErrorLength];
        UpdatedAt = completedAt;

        if (Attempts >= maxAttempts)
        {
            Status = AccountingPostingStatus.Failed;
            NextAttemptAt = null;
            return;
        }

        Status = AccountingPostingStatus.Pending;
        var exponent = Math.Min(Attempts - 1, 30);
        var multiplier = 1L << exponent;
        var delaySeconds = Math.Min(
            (long)maxRetryDelaySeconds,
            (long)baseRetryDelaySeconds * multiplier);
        NextAttemptAt = completedAt.AddSeconds(delaySeconds);
    }

    private static string NormalizeRequired(
        string value,
        int maxLength,
        string parameterName)
    {
        if (string.IsNullOrWhiteSpace(value))
            throw new ArgumentException($"{parameterName} is required.", parameterName);

        var normalized = value.Trim();
        if (normalized.Length > maxLength)
            throw new ArgumentOutOfRangeException(parameterName);

        return normalized;
    }
}
