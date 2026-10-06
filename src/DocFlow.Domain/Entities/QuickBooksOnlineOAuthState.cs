namespace DocFlow.Domain.Entities;

public sealed class QuickBooksOnlineOAuthState
{
    public const int MaxTargetKeyLength = 100;
    public const int MaxStateHashLength = 64;

    public Guid Id { get; private set; }
    public Guid CustomerId { get; private set; }
    public string TargetKey { get; private set; } = string.Empty;
    public string StateHash { get; private set; } = string.Empty;
    public DateTimeOffset CreatedAt { get; private set; }
    public DateTimeOffset ExpiresAt { get; private set; }
    public DateTimeOffset? ConsumedAt { get; private set; }

    private QuickBooksOnlineOAuthState()
    {
    }

    public QuickBooksOnlineOAuthState(
        Guid customerId,
        string targetKey,
        string stateHash,
        DateTimeOffset createdAt,
        DateTimeOffset expiresAt)
    {
        if (customerId == Guid.Empty)
            throw new ArgumentException("Customer id is required.", nameof(customerId));
        if (expiresAt <= createdAt)
            throw new ArgumentOutOfRangeException(nameof(expiresAt));

        Id = Guid.NewGuid();
        CustomerId = customerId;
        TargetKey = NormalizeRequired(targetKey, MaxTargetKeyLength, nameof(targetKey));
        StateHash = NormalizeRequired(stateHash, MaxStateHashLength, nameof(stateHash));
        CreatedAt = createdAt;
        ExpiresAt = expiresAt;
    }

    public void MarkConsumed(DateTimeOffset consumedAt)
    {
        if (ConsumedAt is not null)
            throw new InvalidOperationException("OAuth state has already been consumed.");
        if (consumedAt < CreatedAt)
            throw new ArgumentOutOfRangeException(nameof(consumedAt));

        ConsumedAt = consumedAt;
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
