using System.Text.Json;
using DocFlow.Application.Abstractions;
using DocFlow.Domain.Entities;
using DocFlow.Domain.Enums;
using DocFlow.Infrastructure.Persistence;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace DocFlow.Api.Controllers;

[ApiController]
[Route("api/documents")]
public sealed class DocumentsController : ControllerBase
{
    private const long MaxFileSize = 20 * 1024 * 1024;
    private const int MaxPageSize = 100;
    private const int MaxDocumentTypeLength = 100;

    private readonly DocFlowDbContext _dbContext;
    private readonly IFileStorage _fileStorage;
    private readonly IExtractionResultService _extractionResultService;
    private readonly IDocumentProcessingQueue _documentProcessingQueue;

    public DocumentsController(
        DocFlowDbContext dbContext,
        IFileStorage fileStorage,
        IExtractionResultService extractionResultService,
        IDocumentProcessingQueue documentProcessingQueue)
    {
        _dbContext = dbContext;
        _fileStorage = fileStorage;
        _extractionResultService = extractionResultService;
        _documentProcessingQueue = documentProcessingQueue;
    }

    [HttpGet]
    [ProducesResponseType(typeof(ListDocumentsResponse), StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status400BadRequest)]
    public async Task<ActionResult<ListDocumentsResponse>> List(
        [FromQuery] ListDocumentsRequest request,
        CancellationToken cancellationToken)
    {
        if (request.CustomerId == Guid.Empty)
            return BadRequest("Customer id is required.");

        if (request.Page < 1)
            return BadRequest("Page must be greater than or equal to 1.");

        if (request.PageSize is < 1 or > MaxPageSize)
            return BadRequest($"Page size must be between 1 and {MaxPageSize}.");

        DocumentStatus? statusFilter = null;
        if (!string.IsNullOrWhiteSpace(request.Status))
        {
            if (!Enum.TryParse<DocumentStatus>(
                    request.Status.Trim(),
                    ignoreCase: true,
                    out var parsedStatus)
                || !Enum.IsDefined(parsedStatus))
            {
                return BadRequest(
                    "Status must be Uploaded, Processing, Processed, NeedsReview, or Failed.");
            }

            statusFilter = parsedStatus;
        }

        string? documentTypeFilter = null;
        if (!string.IsNullOrWhiteSpace(request.DocumentType))
        {
            documentTypeFilter = request.DocumentType.Trim().ToLowerInvariant();
            if (documentTypeFilter.Length > MaxDocumentTypeLength)
            {
                return BadRequest(
                    $"Document type must not exceed {MaxDocumentTypeLength} characters.");
            }
        }

        var skipLong = (long)(request.Page - 1) * request.PageSize;
        if (skipLong > int.MaxValue)
            return BadRequest("Page is too large.");

        var documents = _dbContext.Documents
            .AsNoTracking()
            .Where(x => x.CustomerId == request.CustomerId);

        if (statusFilter is not null)
            documents = documents.Where(x => x.Status == statusFilter.Value);

        if (documentTypeFilter is not null)
            documents = documents.Where(x => x.DocumentType == documentTypeFilter);

        var totalCount = await documents.CountAsync(cancellationToken);

        var pageRows = await (
                from document in documents
                join extractionResult in _dbContext.ExtractionResults.AsNoTracking()
                    on document.Id equals extractionResult.DocumentId into extractionResults
                from extractionResult in extractionResults.DefaultIfEmpty()
                orderby document.CreatedAt descending, document.Id descending
                select new DocumentInboxProjection(
                    document.Id,
                    document.CustomerId,
                    document.OriginalFileName,
                    document.Size,
                    document.DocumentType,
                    document.Status,
                    document.CreatedAt,
                    document.ProcessedAt,
                    extractionResult == null ? (Guid?)null : extractionResult.Id,
                    extractionResult == null
                        ? (ValidationStatus?)null
                        : extractionResult.ValidationStatus,
                    extractionResult == null ? null : extractionResult.Confidence))
            .Skip((int)skipLong)
            .Take(request.PageSize)
            .ToListAsync(cancellationToken);

        var items = pageRows
            .Select(x => new DocumentListItemResponse(
                x.Id,
                x.CustomerId,
                x.OriginalFileName,
                x.Size,
                x.DocumentType,
                x.DocumentStatus.ToString(),
                x.CreatedAt,
                x.ProcessedAt,
                x.ExtractionResultId,
                x.ValidationStatus?.ToString(),
                x.Confidence))
            .ToArray();

        var totalPages = totalCount == 0
            ? 0
            : (int)Math.Ceiling(totalCount / (double)request.PageSize);

        return Ok(new ListDocumentsResponse(
            request.Page,
            request.PageSize,
            totalCount,
            totalPages,
            items));
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

    [HttpGet("{id:guid}/extraction-result")]
    [ProducesResponseType(typeof(GetExtractionResultResponse), StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<ActionResult<GetExtractionResultResponse>> GetExtractionResult(
        Guid id,
        CancellationToken cancellationToken)
    {
        var result = await _dbContext.ExtractionResults
            .AsNoTracking()
            .Where(x => x.DocumentId == id)
            .Select(x => new
            {
                x.Id,
                x.DocumentId,
                x.StructuredDataJson,
                x.Confidence,
                x.ValidationStatus,
                x.CreatedAt
            })
            .SingleOrDefaultAsync(cancellationToken);

        if (result is null)
            return NotFound();

        var structuredData = JsonSerializer.Deserialize<JsonElement>(result.StructuredDataJson);

        return Ok(new GetExtractionResultResponse(
            result.Id,
            result.DocumentId,
            structuredData,
            result.Confidence,
            result.ValidationStatus.ToString(),
            result.CreatedAt));
    }

    [HttpPost("{id:guid}/extraction-result")]
    [Consumes("application/json")]
    [ProducesResponseType(typeof(SaveExtractionResultResponse), StatusCodes.Status201Created)]
    [ProducesResponseType(StatusCodes.Status400BadRequest)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    [ProducesResponseType(StatusCodes.Status409Conflict)]
    public async Task<ActionResult<SaveExtractionResultResponse>> SaveExtractionResult(
        Guid id,
        [FromBody] JsonElement request,
        CancellationToken cancellationToken)
    {
        if (request.ValueKind != JsonValueKind.Object)
            return BadRequest("The extraction result must be a JSON object.");

        if (!TryGetRequiredString(request, "engine", out _))
            return BadRequest("The extraction result must contain a non-empty 'engine'.");

        if (!TryGetRequiredString(request, "document_type", out var documentType))
            return BadRequest("The extraction result must contain a non-empty 'document_type'.");

        if (!request.TryGetProperty("data", out var data) || data.ValueKind != JsonValueKind.Object)
            return BadRequest("The extraction result must contain an object-valued 'data'.");

        if (!TryGetRequiredString(request, "validation_status", out var validationStatusText))
            return BadRequest("The extraction result must contain a non-empty 'validation_status'.");

        if (!TryParseValidationStatus(validationStatusText, out var validationStatus))
            return BadRequest("'validation_status' must be 'valid', 'invalid', or 'incomplete'.");

        decimal? confidence = null;
        if (request.TryGetProperty("confidence", out var confidenceElement)
            && confidenceElement.ValueKind != JsonValueKind.Null)
        {
            if (confidenceElement.ValueKind != JsonValueKind.Number
                || !confidenceElement.TryGetDecimal(out var parsedConfidence)
                || parsedConfidence is < 0 or > 1)
            {
                return BadRequest("'confidence' must be null or a number between 0 and 1.");
            }

            confidence = parsedConfidence;
        }

        var saveResult = await _extractionResultService.SaveAsync(
            id,
            request.GetRawText(),
            documentType,
            confidence,
            validationStatus,
            cancellationToken);

        if (saveResult.Outcome == ExtractionResultSaveOutcome.DocumentNotFound)
            return NotFound();

        if (saveResult.Outcome == ExtractionResultSaveOutcome.AlreadyExists)
            return Conflict("An extraction result already exists for this document.");

        var saved = saveResult.SavedResult
            ?? throw new InvalidOperationException("The extraction result service returned no saved result.");

        var response = new SaveExtractionResultResponse(
            saved.Id,
            saved.DocumentId,
            saved.DocumentStatus.ToString(),
            saved.DocumentType,
            saved.ValidationStatus.ToString(),
            saved.Confidence,
            saved.CreatedAt);

        return StatusCode(StatusCodes.Status201Created, response);
    }

    [HttpPost("{id:guid}/process")]
    [ProducesResponseType(StatusCodes.Status202Accepted)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<IActionResult> Process(
        Guid id,
        CancellationToken cancellationToken)
    {
        var exists = await _dbContext.Documents
            .AsNoTracking()
            .AnyAsync(x => x.Id == id, cancellationToken);

        if (!exists)
            return NotFound();

        await _documentProcessingQueue.EnqueueAsync(id, cancellationToken);
        return Accepted();
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

        await _documentProcessingQueue.EnqueueAsync(
            document.Id,
            CancellationToken.None);

        var response = new UploadDocumentResponse(
            document.Id,
            document.Status.ToString(),
            document.OriginalFileName,
            document.CreatedAt);

        return StatusCode(StatusCodes.Status201Created, response);
    }

    private static bool TryGetRequiredString(
        JsonElement request,
        string propertyName,
        out string value)
    {
        value = string.Empty;

        if (!request.TryGetProperty(propertyName, out var element)
            || element.ValueKind != JsonValueKind.String)
        {
            return false;
        }

        var text = element.GetString();
        if (string.IsNullOrWhiteSpace(text))
            return false;

        value = text.Trim();
        return true;
    }

    private static bool TryParseValidationStatus(
        string value,
        out ValidationStatus validationStatus)
    {
        switch (value.Trim().ToLowerInvariant())
        {
            case "valid":
                validationStatus = ValidationStatus.Valid;
                return true;
            case "invalid":
                validationStatus = ValidationStatus.Invalid;
                return true;
            case "incomplete":
                validationStatus = ValidationStatus.NeedsReview;
                return true;
            default:
                validationStatus = default;
                return false;
        }
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

    public sealed class ListDocumentsRequest
    {
        public Guid CustomerId { get; init; }
        public string? Status { get; init; }
        public string? DocumentType { get; init; }
        public int Page { get; init; } = 1;
        public int PageSize { get; init; } = 50;
    }

    public sealed record ListDocumentsResponse(
        int Page,
        int PageSize,
        int TotalCount,
        int TotalPages,
        IReadOnlyList<DocumentListItemResponse> Items);

    public sealed record DocumentListItemResponse(
        Guid Id,
        Guid CustomerId,
        string OriginalFileName,
        long Size,
        string? DocumentType,
        string DocumentStatus,
        DateTimeOffset CreatedAt,
        DateTimeOffset? ProcessedAt,
        Guid? ExtractionResultId,
        string? ValidationStatus,
        decimal? Confidence);

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

    public sealed record SaveExtractionResultResponse(
        Guid Id,
        Guid DocumentId,
        string DocumentStatus,
        string? DocumentType,
        string ValidationStatus,
        decimal? Confidence,
        DateTimeOffset CreatedAt);

    public sealed record GetExtractionResultResponse(
        Guid Id,
        Guid DocumentId,
        JsonElement StructuredData,
        decimal? Confidence,
        string ValidationStatus,
        DateTimeOffset CreatedAt);

    private sealed record DocumentInboxProjection(
        Guid Id,
        Guid CustomerId,
        string OriginalFileName,
        long Size,
        string? DocumentType,
        DocumentStatus DocumentStatus,
        DateTimeOffset CreatedAt,
        DateTimeOffset? ProcessedAt,
        Guid? ExtractionResultId,
        ValidationStatus? ValidationStatus,
        decimal? Confidence);
}
