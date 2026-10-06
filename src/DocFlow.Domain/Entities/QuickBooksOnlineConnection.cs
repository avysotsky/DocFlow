namespace DocFlow.Domain.Entities;

public sealed class QuickBooksOnlineConnection
{
    public const int MaxTargetKeyLength = 100;
    public const int MaxRealmIdLength = 200;
    public const int MaxProtectedTokenLength = 8192;

    public Guid Id { get; private set; }
    public Guid CustomerId { get; private set; }
    public string TargetKey { get; private set; } = string.Empty;
    public string RealmId { get; private set; } = string.Empty;
    public string ProtectedAccessToken { get; private set; } = string.Empty;
    public DateTimeOffset AccessTokenExpiresAt { get; private set; }
    public string ProtectedRefreshToken { get; private set; } = string.Empty;
    public DateTimeOffset RefreshTokenExpiresAt { get; private set; }
    public DateTimeOffset ConnectedAt { get; private set; }
    public DateTimeOffset UpdatedAt { get; private set; }

    private QuickBooksOnlineConnection()
    {
    }

    public QuickBooksOnlineConnection(
        Guid customerId,
        string targetKey,
        string realmId,
        string protectedAccessToken,
        DateTimeOffset accessTokenExpiresAt,
        string protectedRefreshToken,
        DateTimeOffset refreshTokenExpiresAt,
        DateTimeOffset connectedAt)
    {
        if (customerId == Guid.Empty)
            throw new ArgumentException("Customer id is required.", nameof(customerId));

        Id = Guid.NewGuid();
        CustomerId = customerId;
        TargetKey = NormalizeRequired(targetKey, MaxTargetKeyLength, nameof(targetKey));
        RealmId = NormalizeRequired(realmId, MaxRealmIdLength, nameof(realmId));
        ProtectedAccessToken = NormalizeRequired(
            protectedAccessToken,
            MaxProtectedTokenLength,
            nameof(protectedAccessToken));
        ProtectedRefreshToken = NormalizeRequired(
            protectedRefreshToken,
            MaxProtectedTokenLength,
            nameof(protectedRefreshToken));

        ValidateExpiry(accessTokenExpiresAt, refreshTokenExpiresAt, connectedAt);

        AccessTokenExpiresAt = accessTokenExpiresAt;
        RefreshTokenExpiresAt = refreshTokenExpiresAt;
        ConnectedAt = connectedAt;
        UpdatedAt = connectedAt;
    }

    public void RotateTokens(
        string protectedAccessToken,
        DateTimeOffset accessTokenExpiresAt,
        string protectedRefreshToken,
        DateTimeOffset refreshTokenExpiresAt,
        DateTimeOffset updatedAt)
    {
        ProtectedAccessToken = NormalizeRequired(
            protectedAccessToken,
            MaxProtectedTokenLength,
            nameof(protectedAccessToken));
        ProtectedRefreshToken = NormalizeRequired(
            protectedRefreshToken,
            MaxProtectedTokenLength,
            nameof(protectedRefreshToken));

        ValidateExpiry(accessTokenExpiresAt, refreshTokenExpiresAt, updatedAt);

        AccessTokenExpiresAt = accessTokenExpiresAt;
        RefreshTokenExpiresAt = refreshTokenExpiresAt;
        UpdatedAt = updatedAt;
    }

    private static void ValidateExpiry(
        DateTimeOffset accessTokenExpiresAt,
        DateTimeOffset refreshTokenExpiresAt,
        DateTimeOffset referenceTime)
    {
        if (accessTokenExpiresAt <= referenceTime)
            throw new ArgumentOutOfRangeException(nameof(accessTokenExpiresAt));
        if (refreshTokenExpiresAt <= referenceTime)
            throw new ArgumentOutOfRangeException(nameof(refreshTokenExpiresAt));
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
