namespace DocFlow.Domain.Entities;

public sealed class IntakeIdempotencyRecord
{
    public const int MaxKeyLength = 128;
    public const int RequestFingerprintLength = 64;
    public const int MaxOutcomeLength = 16;
    public const int MaxOriginalFileNameLength = 512;
    public const int MaxDocumentStatusLength = 32;
    public const int MaxErrorLength = 500;

    public Guid CustomerId { get; private set; }
    public string Key { get; private set; } = string.Empty;
    public string RequestFingerprint { get; private set; } = string.Empty;
    public string Outcome { get; private set; } = string.Empty;
    public Guid? DocumentId { get; private set; }
    public string OriginalFileName { get; private set; } = string.Empty;
    public string? DocumentStatus { get; private set; }
    public DateTimeOffset? DocumentCreatedAt { get; private set; }
    public DateTimeOffset? DocumentDeleteAt { get; private set; }
    public string? Error { get; private set; }
    public DateTimeOffset CreatedAt { get; private set; }
    public DateTimeOffset ExpiresAt { get; private set; }

    private IntakeIdempotencyRecord()
    {
    }

    public IntakeIdempotencyRecord(
        Guid customerId,
        string key,
        string requestFingerprint,
        string outcome,
        string originalFileName,
        DateTimeOffset createdAt,
        DateTimeOffset expiresAt,
        Guid? documentId = null,
        string? documentStatus = null,
        DateTimeOffset? documentCreatedAt = null,
        DateTimeOffset? documentDeleteAt = null,
        string? error = null)
    {
        CustomerId = customerId;
        Key = NormalizeRequired(key, MaxKeyLength, nameof(key));
        Replace(
            requestFingerprint,
            outcome,
            originalFileName,
            createdAt,
            expiresAt,
            documentId,
            documentStatus,
            documentCreatedAt,
            documentDeleteAt,
            error);
    }

    public void Replace(
        string requestFingerprint,
        string outcome,
        string originalFileName,
        DateTimeOffset createdAt,
        DateTimeOffset expiresAt,
        Guid? documentId = null,
        string? documentStatus = null,
        DateTimeOffset? documentCreatedAt = null,
        DateTimeOffset? documentDeleteAt = null,
        string? error = null)
    {
        if (CustomerId == Guid.Empty)
            throw new ArgumentException("Customer id is required.", nameof(CustomerId));
        if (expiresAt <= createdAt)
            throw new ArgumentOutOfRangeException(nameof(expiresAt), "Expiry must be after creation time.");

        RequestFingerprint = NormalizeRequired(
            requestFingerprint,
            RequestFingerprintLength,
            nameof(requestFingerprint));
        Outcome = NormalizeRequired(outcome, MaxOutcomeLength, nameof(outcome));
        OriginalFileName = NormalizeOptional(originalFileName, MaxOriginalFileNameLength) ?? string.Empty;
        DocumentId = documentId;
        DocumentStatus = NormalizeOptional(documentStatus, MaxDocumentStatusLength);
        DocumentCreatedAt = documentCreatedAt;
        DocumentDeleteAt = documentDeleteAt;
        Error = NormalizeOptional(error, MaxErrorLength);
        CreatedAt = createdAt;
        ExpiresAt = expiresAt;
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

    private static string? NormalizeOptional(string? value, int maxLength)
    {
        if (string.IsNullOrWhiteSpace(value))
            return null;

        var normalized = value.Trim();
        return normalized.Length <= maxLength
            ? normalized
            : normalized[..maxLength];
    }
}
