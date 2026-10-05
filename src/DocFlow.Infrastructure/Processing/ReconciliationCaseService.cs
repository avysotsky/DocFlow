using System.Text.Json;
using DocFlow.Application.Abstractions;
using DocFlow.Domain.Entities;
using DocFlow.Infrastructure.Persistence;
using Microsoft.EntityFrameworkCore;

namespace DocFlow.Infrastructure.Processing;

public sealed class ReconciliationCaseService : IReconciliationCaseService
{
    private readonly DocFlowDbContext _dbContext;
    private readonly IInvoicePurchaseOrderReconciliationService _reconciliationService;

    public ReconciliationCaseService(
        DocFlowDbContext dbContext,
        IInvoicePurchaseOrderReconciliationService reconciliationService)
    {
        _dbContext = dbContext;
        _reconciliationService = reconciliationService;
    }

    public async Task<ReconciliationCaseCreateResult> CreateAsync(
        Guid customerId,
        Guid invoiceDocumentId,
        Guid purchaseOrderDocumentId,
        string createdByClient,
        CancellationToken cancellationToken = default)
    {
        var reconciliation = await _reconciliationService.ReconcileAsync(
            customerId,
            invoiceDocumentId,
            purchaseOrderDocumentId,
            cancellationToken);

        if (reconciliation.Outcome != InvoicePoReconciliationOutcome.Completed)
            return new ReconciliationCaseCreateResult(reconciliation.Outcome);

        var report = reconciliation.Report
            ?? throw new InvalidOperationException(
                "Completed reconciliation did not provide a report.");

        var reviewStatus = string.Equals(
                report.Status,
                "Match",
                StringComparison.OrdinalIgnoreCase)
            ? "Open"
            : "NeedsReview";

        var entity = new ReconciliationCase(
            customerId,
            invoiceDocumentId,
            purchaseOrderDocumentId,
            report.Status,
            reviewStatus,
            JsonSerializer.Serialize(report),
            createdByClient);

        _dbContext.ReconciliationCases.Add(entity);
        await _dbContext.SaveChangesAsync(cancellationToken);

        return new ReconciliationCaseCreateResult(
            InvoicePoReconciliationOutcome.Completed,
            ToSnapshot(entity, report));
    }

    public async Task<ReconciliationCaseSnapshot?> GetAsync(
        Guid customerId,
        Guid caseId,
        CancellationToken cancellationToken = default)
    {
        var entity = await _dbContext.ReconciliationCases
            .AsNoTracking()
            .SingleOrDefaultAsync(
                item => item.Id == caseId && item.CustomerId == customerId,
                cancellationToken);

        if (entity is null)
            return null;

        var report = JsonSerializer.Deserialize<InvoicePoReconciliationReport>(
            entity.ReportJson)
            ?? throw new InvalidOperationException(
                $"Persisted reconciliation case '{entity.Id}' has an invalid report.");

        return ToSnapshot(entity, report);
    }

    private static ReconciliationCaseSnapshot ToSnapshot(
        ReconciliationCase entity,
        InvoicePoReconciliationReport report)
        => new(
            entity.Id,
            entity.CustomerId,
            entity.InvoiceDocumentId,
            entity.PurchaseOrderDocumentId,
            entity.ReconciliationStatus,
            entity.ReviewStatus,
            entity.CreatedAt,
            entity.UpdatedAt,
            entity.CreatedByClient,
            report);
}
