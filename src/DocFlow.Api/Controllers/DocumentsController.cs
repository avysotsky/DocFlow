using DocFlow.Application.Abstractions;
using DocFlow.Domain.Entities;
using DocFlow.Infrastructure.Persistence;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace DocFlow.Api.Controllers;

[ApiController]
[Route("api/documents")]
public sealed class DocumentsController : ControllerBase
{
    private const long MaxFileSize = 20 * 1024 * 1024;

    private readonly DocFlowDbContext _dbContext;
    private readonly IFileStorage _fileStorage;

    public DocumentsController(
        DocFlowDbContext dbContext,
        IFileStorage fileStorage)
    {
        _dbContext = dbContext;
        _fileStorage = fileStorage;
    }

    [HttpGet("{id:guid}")]
    [ProducesResponseType(typeof(GetDocumentResponse), StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<ActionResult<GetDocumentResponse>> GetById(
        Guid id,
        CancellationToken cancellationToken)
    {
        var document = await _dbContext.Documents
            .AsNoTracking()
            .Where(x => x.Id == id)
            .Select(x => new GetDocumentResponse(
                x.Id,
                x.CustomerId,
                x.OriginalFileName,
                x.ContentType,
                x.StorageKey,
                x.Size,
                x.DocumentType,
                x.Status.ToString(),
                x.CreatedAt,
                x.ProcessedAt,
                x.DeleteAt))
            .SingleOrDefaultAsync(cancellationToken);

        if (document is null)
            return NotFound();

        return Ok(document);
    }

    [HttpPost]
    [Consumes("multipart/form-data")]
    [ProducesResponseType(typeof(UploadDocumentResponse), StatusCodes.Status201Created)]
    [ProducesResponseType(StatusCodes.Status400BadRequest)]
    public async Task<ActionResult<UploadDocumentResponse>> Upload(
        [FromForm] UploadDocumentRequest request,
        CancellationToken cancellationToken)
    {
        if (request.CustomerId == Guid.Empty)
            return BadRequest("Customer id is required.");

        var file = request.File;

        if (file is null || file.Length == 0)
            return BadRequest("A non-empty PDF file is required.");

        if (file.Length > MaxFileSize)
            return BadRequest("The PDF file must not exceed 20 MB.");

        if (!string.Equals(Path.GetExtension(file.FileName), ".pdf", StringComparison.OrdinalIgnoreCase))
            return BadRequest("Only PDF files are supported.");

        if (!string.Equals(file.ContentType, "application/pdf", StringComparison.OrdinalIgnoreCase))
            return BadRequest("The file content type must be application/pdf.");

        if (!await HasPdfSignatureAsync(file, cancellationToken))
            return BadRequest("The uploaded file does not have a valid PDF signature.");

        string storageKey;
        await using (var input = file.OpenReadStream())
        {
            storageKey = await _fileStorage.UploadAsync(
                input,
                file.FileName,
                file.ContentType,
                cancellationToken);
        }

        var document = new Document(
            request.CustomerId,
            file.FileName,
            file.ContentType,
            storageKey,
            file.Length);

        try
        {
            _dbContext.Documents.Add(document);
            await _dbContext.SaveChangesAsync(cancellationToken);
        }
        catch
        {
            try
            {
                await _fileStorage.DeleteAsync(storageKey, CancellationToken.None);
            }
            catch
            {
                // Preserve the original database exception.
            }

            throw;
        }

        var response = new UploadDocumentResponse(
            document.Id,
            document.Status.ToString(),
            document.OriginalFileName,
            document.CreatedAt);

        return StatusCode(StatusCodes.Status201Created, response);
    }

    private static async Task<bool> HasPdfSignatureAsync(
        IFormFile file,
        CancellationToken cancellationToken)
    {
        var signature = new byte[5];

        await using var stream = file.OpenReadStream();
        var bytesRead = await stream.ReadAsync(signature.AsMemory(0, signature.Length), cancellationToken);

        return bytesRead == signature.Length
            && signature[0] == (byte)'%'
            && signature[1] == (byte)'P'
            && signature[2] == (byte)'D'
            && signature[3] == (byte)'F'
            && signature[4] == (byte)'-';
    }

    public sealed class UploadDocumentRequest
    {
        public Guid CustomerId { get; init; }
        public IFormFile? File { get; init; }
    }

    public sealed record UploadDocumentResponse(
        Guid Id,
        string Status,
        string OriginalFileName,
        DateTimeOffset CreatedAt);

    public sealed record GetDocumentResponse(
        Guid Id,
        Guid CustomerId,
        string OriginalFileName,
        string ContentType,
        string StorageKey,
        long Size,
        string? DocumentType,
        string Status,
        DateTimeOffset CreatedAt,
        DateTimeOffset? ProcessedAt,
        DateTimeOffset? DeleteAt);
}
