using DocFlow.Api.Authentication;
using DocFlow.Application.Abstractions;
using DocFlow.Infrastructure.Persistence;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace DocFlow.Api.Controllers;

[ApiController]
[Authorize]
[Route("api/documents/{documentId:guid}/file")]
public sealed class DocumentFilesController : ControllerBase
{
    private const string PdfContentType = "application/pdf";

    private readonly DocFlowDbContext _dbContext;
    private readonly IFileStorage _fileStorage;
    private readonly ILogger<DocumentFilesController> _logger;

    public DocumentFilesController(
        DocFlowDbContext dbContext,
        IFileStorage fileStorage,
        ILogger<DocumentFilesController> logger)
    {
        _dbContext = dbContext;
        _fileStorage = fileStorage;
        _logger = logger;
    }

    [HttpGet]
    [ProducesResponseType(typeof(FileStreamResult), StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status206PartialContent)]
    [ProducesResponseType(StatusCodes.Status401Unauthorized)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    [ProducesResponseType(StatusCodes.Status500InternalServerError)]
    public async Task<IActionResult> Download(
        Guid documentId,
        CancellationToken cancellationToken)
    {
        var customerId = User.GetRequiredCustomerId();

        var document = await _dbContext.Documents
            .AsNoTracking()
            .Where(x => x.Id == documentId && x.CustomerId == customerId)
            .Select(x => new
            {
                x.OriginalFileName,
                x.StorageKey
            })
            .SingleOrDefaultAsync(cancellationToken);

        if (document is null)
            return NotFound();

        Stream stream;
        try
        {
            stream = await _fileStorage.OpenReadAsync(
                document.StorageKey,
                cancellationToken);
        }
        catch (FileNotFoundException exception)
        {
            _logger.LogError(
                exception,
                "Backing file is missing for document {DocumentId}.",
                documentId);
            return SourceFileUnavailable();
        }
        catch (DirectoryNotFoundException exception)
        {
            _logger.LogError(
                exception,
                "Backing storage directory is missing for document {DocumentId}.",
                documentId);
            return SourceFileUnavailable();
        }

        return File(
            stream,
            PdfContentType,
            CreateSafeDownloadName(document.OriginalFileName),
            enableRangeProcessing: true);
    }

    private ObjectResult SourceFileUnavailable()
    {
        return Problem(
            statusCode: StatusCodes.Status500InternalServerError,
            title: "Source document file is unavailable.");
    }

    private static string CreateSafeDownloadName(string originalFileName)
    {
        var normalized = (originalFileName ?? string.Empty).Replace('\\', '/');
        var fileName = Path.GetFileName(normalized);

        if (string.IsNullOrWhiteSpace(fileName))
            return "document.pdf";

        var sanitized = new string(fileName
            .Where(character => !char.IsControl(character) && character is not '"' and not '/' and not '\\')
            .ToArray())
            .Trim();

        if (string.IsNullOrWhiteSpace(sanitized))
            return "document.pdf";

        return sanitized.EndsWith(".pdf", StringComparison.OrdinalIgnoreCase)
            ? sanitized
            : $"{sanitized}.pdf";
    }
}
