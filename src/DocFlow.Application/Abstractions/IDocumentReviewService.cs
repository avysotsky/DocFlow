namespace DocFlow.Application.Abstractions;

public interface IDocumentReviewService
{
    Task<DocumentReviewResult> ReviewAsync(
        Guid documentId,
        Guid expectedExtractionResultId,
        string correctedDataJson,
        string? note,
        string reviewedByClient,
        CancellationToken cancellationToken = default);
}

public enum DocumentReviewOutcome
{
    Reviewed = 1,
    DocumentNotFound = 2,
    ExtractionResultNotFound = 3,
    NotReviewable = 4,
    StaleExtractionResult = 5,
    AlreadyReviewed = 6
}

public sealed record ReviewedDocument(
    Guid DocumentId,
    Guid ExtractionResultId,
    Guid ReviewId,
    DateTimeOffset ReviewedAt,
    string DocumentStatus,
    string? Note,
    string ReviewedByClient);

public sealed record DocumentReviewResult(
    DocumentReviewOutcome Outcome,
    ReviewedDocument? Review = null);
