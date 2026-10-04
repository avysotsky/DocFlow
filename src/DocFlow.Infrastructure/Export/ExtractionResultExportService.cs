using System.Diagnostics;
using DocFlow.Application.Abstractions;
using DocFlow.Infrastructure.Persistence;
using DocFlow.Infrastructure.Processing;
using Microsoft.EntityFrameworkCore;

namespace DocFlow.Infrastructure.Export;

public sealed class ExtractionResultExportService : IExtractionResultExportService
{
    private readonly DocFlowDbContext _dbContext;

    public ExtractionResultExportService(DocFlowDbContext dbContext)
    {
        _dbContext = dbContext;
    }

    public async Task<ExtractionResultExportFile?> ExportAsync(
        Guid documentId,
        ExtractionResultExportFormat format,
        CancellationToken cancellationToken = default)
    {
        var source = await (
                from extractionResult in _dbContext.ExtractionResults.AsNoTracking()
                join document in _dbContext.Documents.AsNoTracking()
                    on extractionResult.DocumentId equals document.Id
                join review in _dbContext.DocumentReviews.AsNoTracking()
                    on extractionResult.DocumentId equals review.DocumentId into reviews
                from review in reviews.DefaultIfEmpty()
                where extractionResult.DocumentId == documentId
                select new
                {
                    extractionResult.StructuredDataJson,
                    extractionResult.ValidationStatus,
                    document.OriginalFileName,
                    Review = review
                })
            .SingleOrDefaultAsync(cancellationToken);

        if (source is null)
            return null;

        var effectiveStructuredDataJson = ReviewedStructuredDataComposer.Compose(
            source.StructuredDataJson,
            source.Review);
        var safeBaseName = BuildSafeBaseName(source.OriginalFileName, documentId);

        if (format is ExtractionResultExportFormat.PurchaseOrderCsv
            or ExtractionResultExportFormat.PurchaseOrderXlsx)
        {
            var purchaseOrder = PurchaseOrderBusinessExporter.Parse(
                effectiveStructuredDataJson,
                source.ValidationStatus.ToString(),
                source.Review is not null);

            return format switch
            {
                ExtractionResultExportFormat.PurchaseOrderCsv => new ExtractionResultExportFile(
                    PurchaseOrderBusinessExporter.ToCsv(purchaseOrder),
                    "text/csv; charset=utf-8",
                    $"{safeBaseName}-purchase-order.csv"),
                ExtractionResultExportFormat.PurchaseOrderXlsx => new ExtractionResultExportFile(
                    PurchaseOrderBusinessExporter.ToXlsx(purchaseOrder),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    $"{safeBaseName}-purchase-order.xlsx"),
                _ => throw new UnreachableException()
            };
        }

        if (format is ExtractionResultExportFormat.InvoiceCsv
            or ExtractionResultExportFormat.InvoiceXlsx)
        {
            var invoice = SupplierInvoiceBusinessExporter.Parse(
                effectiveStructuredDataJson,
                source.ValidationStatus.ToString(),
                source.Review is not null);

            return format switch
            {
                ExtractionResultExportFormat.InvoiceCsv => new ExtractionResultExportFile(
                    SupplierInvoiceBusinessExporter.ToCsv(invoice),
                    "text/csv; charset=utf-8",
                    $"{safeBaseName}-invoice.csv"),
                ExtractionResultExportFormat.InvoiceXlsx => new ExtractionResultExportFile(
                    SupplierInvoiceBusinessExporter.ToXlsx(invoice),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    $"{safeBaseName}-invoice.xlsx"),
                _ => throw new UnreachableException()
            };
        }

        var rows = StructuredDataTabularExporter.Flatten(effectiveStructuredDataJson);
        return format switch
        {
            ExtractionResultExportFormat.Csv => new ExtractionResultExportFile(
                StructuredDataTabularExporter.ToCsv(rows),
                "text/csv; charset=utf-8",
                $"{safeBaseName}-extraction.csv"),
            ExtractionResultExportFormat.Xlsx => new ExtractionResultExportFile(
                StructuredDataTabularExporter.ToXlsx(rows),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                $"{safeBaseName}-extraction.xlsx"),
            _ => throw new ArgumentOutOfRangeException(nameof(format), format, "Unsupported export format.")
        };
    }

    private static string BuildSafeBaseName(string originalFileName, Guid documentId)
    {
        var baseName = Path.GetFileNameWithoutExtension(originalFileName).Trim();
        if (string.IsNullOrWhiteSpace(baseName))
            return documentId.ToString("N");

        var invalid = Path.GetInvalidFileNameChars();
        var sanitized = new string(
            baseName
                .Select(character => invalid.Contains(character) ? '_' : character)
                .ToArray())
            .Trim();

        if (string.IsNullOrWhiteSpace(sanitized))
            return documentId.ToString("N");

        return sanitized.Length <= 120
            ? sanitized
            : sanitized[..120];
    }
}
