using DocFlow.Api.Authentication;
using DocFlow.Application.Abstractions;
using DocFlow.Infrastructure.Persistence;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace DocFlow.Api.Controllers;

[ApiController]
[Authorize]
[Route("api/documents/{documentId:guid}/export")]
public sealed class DocumentExportsController : ControllerBase
{
    private readonly DocFlowDbContext _dbContext;
    private readonly IExtractionResultExportService _exportService;

    public DocumentExportsController(
        DocFlowDbContext dbContext,
        IExtractionResultExportService exportService)
    {
        _dbContext = dbContext;
        _exportService = exportService;
    }

    [HttpGet]
    [ProducesResponseType(typeof(FileContentResult), StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status400BadRequest)]
    [ProducesResponseType(StatusCodes.Status401Unauthorized)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<IActionResult> Export(
        Guid documentId,
        [FromQuery] string? format,
        CancellationToken cancellationToken)
    {
        if (!TryParseFormat(format, out var exportFormat))
            return BadRequest("'format' must be 'csv' or 'xlsx'.");

        var customerId = User.GetRequiredCustomerId();
        var isOwned = await _dbContext.Documents
            .AsNoTracking()
            .AnyAsync(
                x => x.Id == documentId && x.CustomerId == customerId,
                cancellationToken);

        if (!isOwned)
            return NotFound();

        var exported = await _exportService.ExportAsync(
            documentId,
            exportFormat,
            cancellationToken);

        if (exported is null)
            return NotFound();

        return File(exported.Content, exported.ContentType, exported.FileName);
    }

    private static bool TryParseFormat(
        string? value,
        out ExtractionResultExportFormat format)
    {
        switch (value?.Trim().ToLowerInvariant())
        {
            case "csv":
                format = ExtractionResultExportFormat.Csv;
                return true;
            case "xlsx":
                format = ExtractionResultExportFormat.Xlsx;
                return true;
            default:
                format = default;
                return false;
        }
    }
}
