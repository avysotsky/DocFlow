namespace DocFlow.Application.Abstractions;

public enum ReconciliationCaseExportFormat
{
    Csv,
    Xlsx
}

public sealed record ReconciliationCaseExportFile(
    byte[] Content,
    string ContentType,
    string FileName);

public interface IReconciliationCaseExportService
{
    Task<ReconciliationCaseExportFile?> ExportAsync(
        Guid customerId,
        Guid caseId,
        ReconciliationCaseExportFormat format,
        CancellationToken cancellationToken = default);
}
