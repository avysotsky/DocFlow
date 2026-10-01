using DocFlow.Application.Abstractions;
using DocFlow.Domain.Entities;
using DocFlow.Domain.Enums;
using DocFlow.Infrastructure.Persistence;
using Microsoft.EntityFrameworkCore;
using Npgsql;

namespace DocFlow.Infrastructure.Processing;

public sealed class DocumentReviewService : IDocumentReviewService
{
    private readonly DocFlowDbContext _dbContext;

    public DocumentReviewService(DocFlowDbContext dbContext)
    {
        _dbContext = dbContext;
    }

    public async Task<DocumentReviewResult> ReviewAsync(
        Guid documentId,
        Guid expectedExtractionResultId,
        string correctedDataJson,
        string? note,
        CancellationToken cancellationToken = default)
    {
        var document = await _dbContext.Documents
            .SingleOrDefaultAsync(x => x.Id == documentId, cancellationToken);

        if (document is null)
            return new DocumentReviewResult(DocumentReviewOutcome.DocumentNotFound);

        var extractionResult = await _dbContext.ExtractionResults
            .SingleOrDefaultAsync(x => x.DocumentId == documentId, cancellationToken);

        if (extractionResult is null)
            return new DocumentReviewResult(DocumentReviewOutcome.ExtractionResultNotFound);

        if (extractionResult.Id != expectedExtractionResultId)
            return new DocumentReviewResult(DocumentReviewOutcome.StaleExtractionResult);

        var alreadyReviewed = await _dbContext.DocumentReviews
            .AnyAsync(x => x.DocumentId == documentId, cancellationToken);

        if (alreadyReviewed)
            return new DocumentReviewResult(DocumentReviewOutcome.AlreadyReviewed);

        if (document.Status != DocumentStatus.NeedsReview
            || string.IsNullOrWhiteSpace(document.DocumentType))
        {
            return new DocumentReviewResult(DocumentReviewOutcome.NotReviewable);
        }

        var review = new DocumentReview(
            documentId,
            extractionResult.Id,
            correctedDataJson,
            note);

        _dbContext.DocumentReviews.Add(review);
        document.MarkProcessed(document.DocumentType);

        try
        {
            await _dbContext.SaveChangesAsync(cancellationToken);
        }
        catch (DbUpdateException exception)
            when (exception.InnerException is PostgresException
            {
                SqlState: PostgresErrorCodes.UniqueViolation
            })
        {
            return new DocumentReviewResult(DocumentReviewOutcome.AlreadyReviewed);
        }

        return new DocumentReviewResult(
            DocumentReviewOutcome.Reviewed,
            new ReviewedDocument(
                document.Id,
                extractionResult.Id,
                review.Id,
                review.ReviewedAt,
                document.Status.ToString(),
                review.Note));
    }
}
