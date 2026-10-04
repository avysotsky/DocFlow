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
            return BadRequest("'format' must be 'csv', 'xlsx', 'invoice-csv', 'invoice-xlsx', 'po-csv', or 'po-xlsx'.");

        var customerId = User.GetRequiredCustomerId();
        var document = await _dbContext.Documents
            .AsNoTracking()
            .Where(x => x.Id == documentId && x.CustomerId == customerId)
            .Select(x => new { x.DocumentType })
            .SingleOrDefaultAsync(cancellationToken);

        if (document is null)
            return NotFound();

        if (exportFormat is ExtractionResultExportFormat.InvoiceCsv
            or ExtractionResultExportFormat.InvoiceXlsx)
        {
            if (!string.Equals(
                    document.DocumentType,
                    "supplier_invoice",
                    StringComparison.OrdinalIgnoreCase))
            {
                return BadRequest(
                    "Business invoice export is only available for processed supplier_invoice documents.");
            }
        }

        if (exportFormat is ExtractionResultExportFormat.PurchaseOrderCsv
            or ExtractionResultExportFormat.PurchaseOrderXlsx)
        {
            if (!string.Equals(
                    document.DocumentType,
                    "purchase_order",
                    StringComparison.OrdinalIgnoreCase))
            {
                return BadRequest(
                    "Business purchase-order export is only available for processed purchase_order documents.");
            }
        }

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
            case "invoice-csv":
                format = ExtractionResultExportFormat.InvoiceCsv;
                return true;
            case "invoice-xlsx":
                format = ExtractionResultExportFormat.InvoiceXlsx;
                return true;
            case "po-csv":
                format = ExtractionResultExportFormat.PurchaseOrderCsv;
                return true;
            case "po-xlsx":
                format = ExtractionResultExportFormat.PurchaseOrderXlsx;
                return true;
            default:
                format = default;
                return false;
        }
    }
}
