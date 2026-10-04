namespace DocFlow.Application.Abstractions;

public enum ExtractionResultExportFormat
{
    Csv,
    Xlsx,
    InvoiceCsv,
    InvoiceXlsx,
    PurchaseOrderCsv,
    PurchaseOrderXlsx
}

public sealed record ExtractionResultExportFile(
    byte[] Content,
    string ContentType,
    string FileName);

public interface IExtractionResultExportService
{
    Task<ExtractionResultExportFile?> ExportAsync(
        Guid documentId,
        ExtractionResultExportFormat format,
        CancellationToken cancellationToken = default);
}
