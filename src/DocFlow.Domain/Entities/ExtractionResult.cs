using DocFlow.Domain.Enums;

namespace DocFlow.Domain.Entities;

public sealed class ExtractionResult
{
    public Guid Id { get; private set; }
    public Guid DocumentId { get; private set; }
    public string StructuredDataJson { get; private set; } = string.Empty;
    public decimal? Confidence { get; private set; }
    public ValidationStatus ValidationStatus { get; private set; }
    public DateTimeOffset CreatedAt { get; private set; }

    private ExtractionResult()
    {
    }

    public ExtractionResult(
        Guid documentId,
        string structuredDataJson,
        decimal? confidence,
        ValidationStatus validationStatus)
    {
        if (documentId == Guid.Empty)
            throw new ArgumentException("Document id is required.", nameof(documentId));
        if (string.IsNullOrWhiteSpace(structuredDataJson))
            throw new ArgumentException("Structured extraction data is required.", nameof(structuredDataJson));
        if (confidence is < 0 or > 1)
            throw new ArgumentOutOfRangeException(nameof(confidence), "Confidence must be between 0 and 1.");

        Id = Guid.NewGuid();
        DocumentId = documentId;
        StructuredDataJson = structuredDataJson;
        Confidence = confidence;
        ValidationStatus = validationStatus;
        CreatedAt = DateTimeOffset.UtcNow;
    }
}
