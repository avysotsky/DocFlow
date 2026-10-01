using DocFlow.Domain.Enums;

namespace DocFlow.Domain.Entities;

public sealed class Document
{
    public const int MaxProcessingErrorLength = 1000;

    public Guid Id { get; private set; }
    public Guid CustomerId { get; private set; }
    public string OriginalFileName { get; private set; } = string.Empty;
    public string ContentType { get; private set; } = string.Empty;
    public string StorageKey { get; private set; } = string.Empty;
    public long Size { get; private set; }
    public string? DocumentType { get; private set; }
    public DocumentStatus Status { get; private set; }
    public DateTimeOffset CreatedAt { get; private set; }
    public DateTimeOffset? ProcessedAt { get; private set; }
    public DateTimeOffset? DeleteAt { get; private set; }
    public int ProcessingAttempts { get; private set; }
    public DateTimeOffset? LastProcessingAttemptAt { get; private set; }
    public DateTimeOffset? LastProcessingFailureAt { get; private set; }
    public string? LastProcessingError { get; private set; }

    private Document()
    {
    }

    public Document(
        Guid customerId,
        string originalFileName,
        string contentType,
        string storageKey,
        long size,
        DateTimeOffset? deleteAt = null)
    {
        if (customerId == Guid.Empty)
            throw new ArgumentException("Customer id is required.", nameof(customerId));
        if (string.IsNullOrWhiteSpace(originalFileName))
            throw new ArgumentException("Original file name is required.", nameof(originalFileName));
        if (string.IsNullOrWhiteSpace(contentType))
            throw new ArgumentException("Content type is required.", nameof(contentType));
        if (string.IsNullOrWhiteSpace(storageKey))
            throw new ArgumentException("Storage key is required.", nameof(storageKey));
        if (size <= 0)
            throw new ArgumentOutOfRangeException(nameof(size), "File size must be greater than zero.");

        Id = Guid.NewGuid();
        CustomerId = customerId;
        OriginalFileName = originalFileName.Trim();
        ContentType = contentType.Trim();
        StorageKey = storageKey.Trim();
        Size = size;
        Status = DocumentStatus.Uploaded;
        CreatedAt = DateTimeOffset.UtcNow;
        DeleteAt = deleteAt;
    }

    public void BeginProcessingAttempt()
    {
        ProcessingAttempts = checked(ProcessingAttempts + 1);
        LastProcessingAttemptAt = DateTimeOffset.UtcNow;
        Status = DocumentStatus.Processing;
    }

    public void RecordProcessingFailure(string errorSummary)
    {
        if (string.IsNullOrWhiteSpace(errorSummary))
            throw new ArgumentException("Processing error summary is required.", nameof(errorSummary));

        var normalized = errorSummary.Trim();
        if (normalized.Length > MaxProcessingErrorLength)
            normalized = normalized[..MaxProcessingErrorLength];

        LastProcessingFailureAt = DateTimeOffset.UtcNow;
        LastProcessingError = normalized;
    }

    public void MarkProcessed(string documentType)
    {
        if (string.IsNullOrWhiteSpace(documentType))
            throw new ArgumentException("Document type is required.", nameof(documentType));

        DocumentType = documentType.Trim();
        Status = DocumentStatus.Processed;
        ProcessedAt = DateTimeOffset.UtcNow;
        ClearProcessingFailure();
    }

    public void MarkNeedsReview(string? documentType = null)
    {
        if (!string.IsNullOrWhiteSpace(documentType))
            DocumentType = documentType.Trim();

        Status = DocumentStatus.NeedsReview;
        ProcessedAt = DateTimeOffset.UtcNow;
        ClearProcessingFailure();
    }

    public void MarkFailed() => Status = DocumentStatus.Failed;

    private void ClearProcessingFailure()
    {
        LastProcessingFailureAt = null;
        LastProcessingError = null;
    }
}
