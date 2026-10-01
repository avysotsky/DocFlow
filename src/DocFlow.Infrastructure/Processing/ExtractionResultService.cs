using DocFlow.Application.Abstractions;
using DocFlow.Application.Observability;
using DocFlow.Domain.Entities;
using DocFlow.Domain.Enums;
using DocFlow.Infrastructure.Persistence;
using Microsoft.EntityFrameworkCore;

namespace DocFlow.Infrastructure.Processing;

public sealed class ExtractionResultService : IExtractionResultService
{
    private readonly DocFlowDbContext _dbContext;
    private readonly OperationalMetrics _metrics;

    public ExtractionResultService(
        DocFlowDbContext dbContext,
        OperationalMetrics metrics)
    {
        _dbContext = dbContext;
        _metrics = metrics;
    }

    public async Task<SaveExtractionResultResult> SaveAsync(
        Guid documentId,
        string structuredDataJson,
        string documentType,
        decimal? confidence,
        ValidationStatus validationStatus,
        CancellationToken cancellationToken = default)
    {
        var document = await _dbContext.Documents
            .SingleOrDefaultAsync(x => x.Id == documentId, cancellationToken);

        if (document is null)
        {
            return new SaveExtractionResultResult(
                ExtractionResultSaveOutcome.DocumentNotFound);
        }

        var alreadyExists = await _dbContext.ExtractionResults
            .AnyAsync(x => x.DocumentId == documentId, cancellationToken);

        if (alreadyExists)
        {
            return new SaveExtractionResultResult(
                ExtractionResultSaveOutcome.AlreadyExists);
        }

        var extractionResult = new ExtractionResult(
            documentId,
            structuredDataJson,
            confidence,
            validationStatus);

        _dbContext.ExtractionResults.Add(extractionResult);

        if (validationStatus == ValidationStatus.Valid)
            document.MarkProcessed(documentType);
        else
            document.MarkNeedsReview(documentType);

        await _dbContext.SaveChangesAsync(cancellationToken);

        if (validationStatus == ValidationStatus.Valid)
            _metrics.RecordProcessingCompleted();
        else
            _metrics.RecordProcessingNeedsReview();

        var savedResult = new SavedExtractionResult(
            extractionResult.Id,
            extractionResult.DocumentId,
            document.Status,
            document.DocumentType,
            extractionResult.ValidationStatus,
            extractionResult.Confidence,
            extractionResult.CreatedAt);

        return new SaveExtractionResultResult(
            ExtractionResultSaveOutcome.Saved,
            savedResult);
    }
}
