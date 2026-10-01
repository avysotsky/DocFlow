namespace DocFlow.Domain.Entities;

public sealed class DocumentReview
{
    public const int MaxReviewedByClientLength = 200;

    public Guid Id { get; private set; }
    public Guid DocumentId { get; private set; }
    public Guid ExtractionResultId { get; private set; }
    public string CorrectedDataJson { get; private set; } = string.Empty;
    public string? Note { get; private set; }
    public DateTimeOffset ReviewedAt { get; private set; }
    public string? ReviewedByClient { get; private set; }

    private DocumentReview()
    {
    }

    public DocumentReview(
        Guid documentId,
        Guid extractionResultId,
        string correctedDataJson,
        string? note,
        string reviewedByClient)
    {
        if (documentId == Guid.Empty)
            throw new ArgumentException("Document id is required.", nameof(documentId));
        if (extractionResultId == Guid.Empty)
            throw new ArgumentException("Extraction result id is required.", nameof(extractionResultId));
        if (string.IsNullOrWhiteSpace(correctedDataJson))
            throw new ArgumentException("Corrected data is required.", nameof(correctedDataJson));
        if (note?.Length > 2000)
            throw new ArgumentOutOfRangeException(nameof(note), "Review note must not exceed 2000 characters.");
        if (string.IsNullOrWhiteSpace(reviewedByClient))
            throw new ArgumentException("Review client attribution is required.", nameof(reviewedByClient));

        var normalizedClient = reviewedByClient.Trim();
        if (normalizedClient.Length > MaxReviewedByClientLength)
        {
            throw new ArgumentOutOfRangeException(
                nameof(reviewedByClient),
                $"Review client attribution must not exceed {MaxReviewedByClientLength} characters.");
        }

        Id = Guid.NewGuid();
        DocumentId = documentId;
        ExtractionResultId = extractionResultId;
        CorrectedDataJson = correctedDataJson;
        Note = string.IsNullOrWhiteSpace(note) ? null : note.Trim();
        ReviewedAt = DateTimeOffset.UtcNow;
        ReviewedByClient = normalizedClient;
    }
}
