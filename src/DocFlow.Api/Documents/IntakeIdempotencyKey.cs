using DocFlow.Domain.Entities;
using Microsoft.Extensions.Primitives;

namespace DocFlow.Api.Documents;

public static class IntakeIdempotencyKey
{
    public const string HeaderName = "Idempotency-Key";
    public const string ReplayHeaderName = "Idempotency-Replayed";
    public const string ReservedPrefix = "docflow-internal:";

    public static (string? Key, string? Error) NormalizeExternal(StringValues values)
    {
        if (values.Count == 0)
            return (null, null);

        if (values.Count != 1)
            return (null, "Exactly one Idempotency-Key header value is allowed.");

        var normalized = (values[0] ?? string.Empty).Trim();
        if (normalized.Length == 0)
            return (null, "Idempotency-Key must not be empty.");

        if (normalized.Length > IntakeIdempotencyRecord.MaxKeyLength)
        {
            return (
                null,
                $"Idempotency-Key must not exceed {IntakeIdempotencyRecord.MaxKeyLength} characters.");
        }

        if (normalized.Any(char.IsControl))
            return (null, "Idempotency-Key must not contain control characters.");

        if (normalized.StartsWith(ReservedPrefix, StringComparison.OrdinalIgnoreCase))
            return (null, $"Idempotency-Key prefix '{ReservedPrefix}' is reserved.");

        return (normalized, null);
    }

    public static bool IsInternal(string key)
    {
        return !string.IsNullOrWhiteSpace(key)
            && key.StartsWith(ReservedPrefix, StringComparison.Ordinal);
    }

    public static string CreateBatchItemKey(Guid generationId, int index)
    {
        if (generationId == Guid.Empty)
            throw new ArgumentException("Generation id is required.", nameof(generationId));
        if (index < 0)
            throw new ArgumentOutOfRangeException(nameof(index));

        var key = $"{ReservedPrefix}batch:{generationId:N}:{index}";
        if (key.Length > IntakeIdempotencyRecord.MaxKeyLength)
            throw new InvalidOperationException("Generated internal idempotency key is too long.");

        return key;
    }

    public static string CreateSingleLockScope(Guid customerId, string key)
        => $"{customerId:N}:{key}";

    public static string CreateBatchLockScope(Guid customerId, string key)
        => $"batch:{customerId:N}:{key}";
}
