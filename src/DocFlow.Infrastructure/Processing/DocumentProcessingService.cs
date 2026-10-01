using DocFlow.Application.Abstractions;
using DocFlow.Infrastructure.Persistence;
using Microsoft.EntityFrameworkCore;

namespace DocFlow.Infrastructure.Processing;

public sealed class DocumentProcessingService : IDocumentProcessingService
{
    private readonly DocFlowDbContext _dbContext;
    private readonly IDocumentExtractionRunner _extractionRunner;
    private readonly IExtractionResultService _extractionResultService;

    public DocumentProcessingService(
        DocFlowDbContext dbContext,
        IDocumentExtractionRunner extractionRunner,
        IExtractionResultService extractionResultService)
    {
        _dbContext = dbContext;
        _extractionRunner = extractionRunner;
        _extractionResultService = extractionResultService;
    }

    public async Task ProcessAsync(
        Guid documentId,
        CancellationToken cancellationToken = default)
    {
        var document = await _dbContext.Documents
            .SingleOrDefaultAsync(x => x.Id == documentId, cancellationToken);

        if (document is null)
            throw new KeyNotFoundException($"Document '{documentId}' was not found.");

        var alreadyProcessed = await _dbContext.ExtractionResults
            .AnyAsync(x => x.DocumentId == documentId, cancellationToken);

        if (alreadyProcessed)
            return;

        document.BeginProcessingAttempt();
        await _dbContext.SaveChangesAsync(cancellationToken);

        try
        {
            var extraction = await _extractionRunner.RunAsync(
                document.StorageKey,
                cancellationToken);

            var saveResult = await _extractionResultService.SaveAsync(
                documentId,
                extraction.StructuredDataJson,
                extraction.DocumentType,
                extraction.Confidence,
                extraction.ValidationStatus,
                cancellationToken);

            if (saveResult.Outcome == ExtractionResultSaveOutcome.DocumentNotFound)
            {
                throw new InvalidOperationException(
                    $"Document '{documentId}' disappeared while its extraction result was being saved.");
            }

            // AlreadyExists is intentionally treated as success. It can happen after a retry
            // or concurrent enqueue and the database unique constraint remains the final guard.
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            throw;
        }
        catch (Exception exception)
        {
            await TryRecordFailureAsync(
                documentId,
                CreateFailureSummary(exception));
            throw;
        }
    }

    public async Task MarkFailedAsync(
        Guid documentId,
        CancellationToken cancellationToken = default)
    {
        _dbContext.ChangeTracker.Clear();

        var document = await _dbContext.Documents
            .SingleOrDefaultAsync(x => x.Id == documentId, cancellationToken);

        if (document is null)
            return;

        var alreadyProcessed = await _dbContext.ExtractionResults
            .AnyAsync(x => x.DocumentId == documentId, cancellationToken);

        if (alreadyProcessed)
            return;

        document.MarkFailed();
        await _dbContext.SaveChangesAsync(cancellationToken);
    }

    private async Task TryRecordFailureAsync(
        Guid documentId,
        string failureSummary)
    {
        try
        {
            _dbContext.ChangeTracker.Clear();

            var document = await _dbContext.Documents
                .SingleOrDefaultAsync(x => x.Id == documentId, CancellationToken.None);

            if (document is null)
                return;

            document.RecordProcessingFailure(failureSummary);
            await _dbContext.SaveChangesAsync(CancellationToken.None);
        }
        catch
        {
            // Preserve the original processing exception.
        }
    }

    private static string CreateFailureSummary(Exception exception)
    {
        var message = exception switch
        {
            FileNotFoundException => "Required document file was not found.",
            DirectoryNotFoundException => "Required processing path was not found.",
            UnauthorizedAccessException => "Document processing could not access a required resource.",
            IOException => "Document processing could not read or write a required resource.",
            TimeoutException => "Document processing timed out.",
            _ => "Document extraction failed."
        };

        return $"{exception.GetType().Name}: {message}";
    }
}
