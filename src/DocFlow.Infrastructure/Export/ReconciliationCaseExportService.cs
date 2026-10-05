using DocFlow.Application.Abstractions;

namespace DocFlow.Infrastructure.Export;

public sealed class ReconciliationCaseExportService : IReconciliationCaseExportService
{
    private readonly IReconciliationCaseService _caseService;

    public ReconciliationCaseExportService(IReconciliationCaseService caseService)
    {
        _caseService = caseService;
    }

    public async Task<ReconciliationCaseExportFile?> ExportAsync(
        Guid customerId,
        Guid caseId,
        ReconciliationCaseExportFormat format,
        CancellationToken cancellationToken = default)
    {
        var snapshot = await _caseService.GetAsync(
            customerId,
            caseId,
            cancellationToken);

        if (snapshot is null)
            return null;

        var safeId = snapshot.Id.ToString("N");

        return format switch
        {
            ReconciliationCaseExportFormat.Csv => new ReconciliationCaseExportFile(
                ReconciliationCaseBusinessExporter.ToCsv(snapshot),
                "text/csv; charset=utf-8",
                $"reconciliation-{safeId}.csv"),
            ReconciliationCaseExportFormat.Xlsx => new ReconciliationCaseExportFile(
                ReconciliationCaseBusinessExporter.ToXlsx(snapshot),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                $"reconciliation-{safeId}.xlsx"),
            _ => throw new ArgumentOutOfRangeException(
                nameof(format),
                format,
                "Unsupported reconciliation case export format.")
        };
    }
}
