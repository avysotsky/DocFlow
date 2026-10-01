namespace DocFlow.Domain.Entities;

public sealed class BatchIntakeIdempotencyRecord
{
    public const int MaxKeyLength = IntakeIdempotencyRecord.MaxKeyLength;
    public const int RequestFingerprintLength = IntakeIdempotencyRecord.RequestFingerprintLength;

    public Guid CustomerId { get; private set; }
    public string Key { get; private set; } = string.Empty;
    public string RequestFingerprint { get; private set; } = string.Empty;
    public Guid GenerationId { get; private set; }
    public string? ResponseJson { get; private set; }
    public DateTimeOffset CreatedAt { get; private set; }
    public DateTimeOffset ExpiresAt { get; private set; }

    private BatchIntakeIdempotencyRecord()
    {
    }

    public BatchIntakeIdempotencyRecord(
        Guid customerId,
        string key,
        string requestFingerprint,
        Guid generationId,
        DateTimeOffset createdAt,
        DateTimeOffset expiresAt)
    {
        if (customerId == Guid.Empty)
            throw new ArgumentException("Customer id is required.", nameof(customerId));

        CustomerId = customerId;
        Key = NormalizeRequired(key, MaxKeyLength, nameof(key));
        Replace(requestFingerprint, generationId, createdAt, expiresAt);
    }

    public void Replace(
        string requestFingerprint,
        Guid generationId,
        DateTimeOffset createdAt,
        DateTimeOffset expiresAt)
    {
        if (generationId == Guid.Empty)
            throw new ArgumentException("Generation id is required.", nameof(generationId));
        if (expiresAt <= createdAt)
            throw new ArgumentOutOfRangeException(nameof(expiresAt), "Expiry must be after creation time.");

        RequestFingerprint = NormalizeRequired(
            requestFingerprint,
            RequestFingerprintLength,
            nameof(requestFingerprint));
        GenerationId = generationId;
        ResponseJson = null;
        CreatedAt = createdAt;
        ExpiresAt = expiresAt;
    }

    public void Complete(string responseJson)
    {
        if (string.IsNullOrWhiteSpace(responseJson))
            throw new ArgumentException("Batch response snapshot is required.", nameof(responseJson));

        ResponseJson = responseJson;
    }

    private static string NormalizeRequired(string value, int maxLength, string parameterName)
    {
        if (string.IsNullOrWhiteSpace(value))
            throw new ArgumentException("A non-empty value is required.", parameterName);

        var normalized = value.Trim();
        if (normalized.Length > maxLength)
            throw new ArgumentOutOfRangeException(parameterName, $"Value must not exceed {maxLength} characters.");

        return normalized;
    }
}
