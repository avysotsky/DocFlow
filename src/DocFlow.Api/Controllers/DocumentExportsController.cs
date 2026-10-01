using DocFlow.Application.Abstractions;
using Microsoft.AspNetCore.Mvc;

namespace DocFlow.Api.Controllers;

[ApiController]
[Route("api/documents/{documentId:guid}/export")]
public sealed class DocumentExportsController : ControllerBase
{
    private readonly IExtractionResultExportService _exportService;

    public DocumentExportsController(IExtractionResultExportService exportService)
    {
        _exportService = exportService;
    }

    [HttpGet]
    [ProducesResponseType(typeof(FileContentResult), StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status400BadRequest)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<IActionResult> Export(
        Guid documentId,
        [FromQuery] string? format,
        CancellationToken cancellationToken)
    {
        if (!TryParseFormat(format, out var exportFormat))
            return BadRequest("'format' must be 'csv' or 'xlsx'.");

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
