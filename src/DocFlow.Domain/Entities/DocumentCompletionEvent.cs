using DocFlow.Domain.Enums;

namespace DocFlow.Domain.Entities;

public sealed class DocumentCompletionEvent
{
    public Guid Id { get; private set; }
    public Guid DocumentId { get; private set; }
    public Guid CustomerId { get; private set; }
    public DocumentStatus Status { get; private set; }
    public string? DocumentType { get; private set; }
    public int ProcessingAttempts { get; private set; }
    public DateTimeOffset OccurredAt { get; private set; }

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
    }
}
