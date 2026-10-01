using DocFlow.Api.Retention;
using DocFlow.Application.Abstractions;
using DocFlow.Domain.Entities;
using DocFlow.Infrastructure.Persistence;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Options;

namespace DocFlow.Api.Documents;

public enum DocumentIntakeOutcome
{
    Accepted = 1,
    Rejected = 2,
    Failed = 3
}

public sealed record DocumentIntakeResult(
    DocumentIntakeOutcome Outcome,
    string OriginalFileName,
    Guid? DocumentId = null,
    string? DocumentStatus = null,
    DateTimeOffset? CreatedAt = null,
    DateTimeOffset? DeleteAt = null,
    string? Error = null);

public sealed class DocumentIntakeService
{
    public const long MaxFileSize = 20L * 1024 * 1024;

    private readonly DocFlowDbContext _dbContext;
    private readonly IFileStorage _fileStorage;
    private readonly IDocumentProcessingQueue _documentProcessingQueue;
    private readonly DocumentRetentionOptions _retentionOptions;
    private readonly ILogger<DocumentIntakeService> _logger;

    public DocumentIntakeService(
        DocFlowDbContext dbContext,
        IFileStorage fileStorage,
        IDocumentProcessingQueue documentProcessingQueue,
        IOptions<DocumentRetentionOptions> retentionOptions,
        ILogger<DocumentIntakeService> logger)
    {
        _dbContext = dbContext;
        _fileStorage = fileStorage;
        _documentProcessingQueue = documentProcessingQueue;
        _retentionOptions = retentionOptions.Value;
        _logger = logger;
    }

    public async Task<DocumentIntakeResult> IntakeAsync(
        Guid customerId,
        IFormFile? file,
        CancellationToken cancellationToken = default)
    {
        if (customerId == Guid.Empty)
            throw new ArgumentException("Customer id is required.", nameof(customerId));

        var fileName = file?.FileName ?? string.Empty;
        var validationError = await ValidateAsync(file, cancellationToken);
        if (validationError is not null)
        {
            return new DocumentIntakeResult(
                DocumentIntakeOutcome.Rejected,
                fileName,
                Error: validationError);
        }

        var validatedFile = file!;

        string storageKey;
        try
        {
            await using var input = validatedFile.OpenReadStream();
            storageKey = await _fileStorage.UploadAsync(
                input,
                validatedFile.FileName,
                validatedFile.ContentType,
                cancellationToken);
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            throw;
        }
        catch (Exception exception)
        {
            _logger.LogError(
                exception,
                "Document intake storage upload failed for file {FileName}.",
                validatedFile.FileName);

            return new DocumentIntakeResult(
                DocumentIntakeOutcome.Failed,
                validatedFile.FileName,
                Error: "The document could not be stored.");
        }

        var deleteAt = _retentionOptions.Enabled
            ? DateTimeOffset.UtcNow.AddDays(_retentionOptions.DefaultRetentionDays)
            : (DateTimeOffset?)null;

        var document = new Document(
            customerId,
            validatedFile.FileName,
            validatedFile.ContentType,
            storageKey,
            validatedFile.Length,
            deleteAt);

        try
        {
            _dbContext.Documents.Add(document);
            await _dbContext.SaveChangesAsync(cancellationToken);
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            _dbContext.Entry(document).State = EntityState.Detached;
            await TryDeleteStoredFileAsync(storageKey);
            throw;
        }
        catch (Exception exception)
        {
            _dbContext.Entry(document).State = EntityState.Detached;
            await TryDeleteStoredFileAsync(storageKey);

            _logger.LogError(
                exception,
                "Document intake persistence failed for file {FileName}.",
                validatedFile.FileName);

            return new DocumentIntakeResult(
                DocumentIntakeOutcome.Failed,
                validatedFile.FileName,
                Error: "The document could not be persisted.");
        }

        try
        {
            // The database row is already durable. Preserve the previous single-upload behavior
            // by completing the enqueue independently of the request cancellation token.
            await _documentProcessingQueue.EnqueueAsync(document.Id, CancellationToken.None);
        }
        catch (Exception exception)
        {
            // A persisted Uploaded document is still recoverable on the next process start and
            // can also be explicitly re-enqueued through POST /api/documents/{id}/process.
            _logger.LogError(
                exception,
                "Document {DocumentId} was persisted but could not be enqueued immediately.",
                document.Id);
        }

        return new DocumentIntakeResult(
            DocumentIntakeOutcome.Accepted,
            document.OriginalFileName,
            document.Id,
            document.Status.ToString(),
            document.CreatedAt,
            document.DeleteAt);
    }

    private static async Task<string?> ValidateAsync(
        IFormFile? file,
        CancellationToken cancellationToken)
    {
        if (file is null || file.Length == 0)
            return "A non-empty PDF file is required.";

        if (file.Length > MaxFileSize)
            return "The PDF file must not exceed 20 MB.";

        if (!string.Equals(
                Path.GetExtension(file.FileName),
                ".pdf",
                StringComparison.OrdinalIgnoreCase))
        {
            return "Only PDF files are supported.";
        }

        if (!string.Equals(
                file.ContentType,
                "application/pdf",
                StringComparison.OrdinalIgnoreCase))
        {
            return "The file content type must be application/pdf.";
        }

        var signature = new byte[5];
        await using var stream = file.OpenReadStream();
        var bytesRead = await stream.ReadAsync(
            signature.AsMemory(0, signature.Length),
            cancellationToken);

        var validSignature = bytesRead == signature.Length
            && signature[0] == (byte)'%'
            && signature[1] == (byte)'P'
            && signature[2] == (byte)'D'
            && signature[3] == (byte)'F'
            && signature[4] == (byte)'-';

        return validSignature
            ? null
            : "The uploaded file does not have a valid PDF signature.";
    }

    private async Task TryDeleteStoredFileAsync(string storageKey)
    {
        try
        {
            await _fileStorage.DeleteAsync(storageKey, CancellationToken.None);
        }
        catch (Exception cleanupException)
        {
            _logger.LogWarning(
                cleanupException,
                "Document intake rollback could not delete storage object {StorageKey}.",
                storageKey);
        }
    }
}
