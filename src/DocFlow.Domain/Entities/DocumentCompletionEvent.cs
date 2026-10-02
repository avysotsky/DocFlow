using DocFlow.Domain.Enums;

namespace DocFlow.Domain.Entities;

public sealed class DocumentCompletionEvent
{
    public const int MaxDeliveryErrorLength = 500;

    public Guid Id { get; private set; }
    public Guid DocumentId { get; private set; }
    public Guid CustomerId { get; private set; }
    public DocumentStatus Status { get; private set; }
    public string? DocumentType { get; private set; }
    public int ProcessingAttempts { get; private set; }
    public DateTimeOffset OccurredAt { get; private set; }
    public int DeliveryAttempts { get; private set; }
    public DateTimeOffset? NextDeliveryAttemptAt { get; private set; }
    public DateTimeOffset? LastDeliveryAttemptAt { get; private set; }
    public string? LastDeliveryError { get; private set; }
    public DateTimeOffset? DeliveredAt { get; private set; }
    public DateTimeOffset? DeliveryAbandonedAt { get; private set; }

    private DocumentCompletionEvent()
    {
    }

    public DocumentCompletionEvent(
        Guid documentId,
        Guid customerId,
        DocumentStatus status,
        string? documentType,
        int processingAttempts,
        DateTimeOffset occurredAt)
    {
        if (documentId == Guid.Empty)
            throw new ArgumentException("Document id is required.", nameof(documentId));
        if (customerId == Guid.Empty)
            throw new ArgumentException("Customer id is required.", nameof(customerId));
        if (status is not (DocumentStatus.Processed or DocumentStatus.NeedsReview or DocumentStatus.Failed))
            throw new ArgumentOutOfRangeException(nameof(status), "Only terminal processing statuses can create completion events.");
        if (processingAttempts < 0)
            throw new ArgumentOutOfRangeException(nameof(processingAttempts));

        Id = Guid.NewGuid();
        DocumentId = documentId;
        CustomerId = customerId;
        Status = status;
        DocumentType = string.IsNullOrWhiteSpace(documentType) ? null : documentType.Trim();
        ProcessingAttempts = processingAttempts;
        OccurredAt = occurredAt;
        NextDeliveryAttemptAt = occurredAt;
    }

    public void MarkDelivered(DateTimeOffset completedAt)
    {
        DeliveryAttempts = checked(DeliveryAttempts + 1);
        LastDeliveryAttemptAt = completedAt;
        DeliveredAt = completedAt;
        NextDeliveryAttemptAt = null;
        DeliveryAbandonedAt = null;
    }

    public void MarkDeliveryFailed(
        DateTimeOffset completedAt,
        string errorSummary,
        int maxAttempts,
        int baseRetryDelaySeconds,
        int maxRetryDelaySeconds)
    {
        if (string.IsNullOrWhiteSpace(errorSummary))
            throw new ArgumentException("Delivery error summary is required.", nameof(errorSummary));
        if (maxAttempts < 1)
            throw new ArgumentOutOfRangeException(nameof(maxAttempts));
        if (baseRetryDelaySeconds < 1)
            throw new ArgumentOutOfRangeException(nameof(baseRetryDelaySeconds));
        if (maxRetryDelaySeconds < baseRetryDelaySeconds)
            throw new ArgumentOutOfRangeException(nameof(maxRetryDelaySeconds));

        DeliveryAttempts = checked(DeliveryAttempts + 1);
        LastDeliveryAttemptAt = completedAt;

        var normalized = errorSummary.Trim();
        LastDeliveryError = normalized.Length <= MaxDeliveryErrorLength
            ? normalized
            : normalized[..MaxDeliveryErrorLength];

        if (DeliveryAttempts >= maxAttempts)
        {
            DeliveryAbandonedAt = completedAt;
            NextDeliveryAttemptAt = null;
            return;
        }

        var exponent = Math.Min(DeliveryAttempts - 1, 30);
        var multiplier = 1L << exponent;
        var delaySeconds = Math.Min(
            (long)maxRetryDelaySeconds,
            (long)baseRetryDelaySeconds * multiplier);

        NextDeliveryAttemptAt = completedAt.AddSeconds(delaySeconds);
    }
}
