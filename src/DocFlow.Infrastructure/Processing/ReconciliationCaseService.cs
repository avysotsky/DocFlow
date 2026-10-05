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

        var createdEvent = new ReconciliationCaseAuditEvent(
            entity.Id,
            "Created",
            null,
            entity.ReviewStatus,
            null,
            createdByClient);

        _dbContext.ReconciliationCases.Add(entity);
        _dbContext.ReconciliationCaseAuditEvents.Add(createdEvent);
        await _dbContext.SaveChangesAsync(cancellationToken);

        return new ReconciliationCaseCreateResult(
            InvoicePoReconciliationOutcome.Completed,
            ToSnapshot(entity, report, [createdEvent]));
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

        var auditEvents = await LoadAuditEventsAsync(caseId, cancellationToken);
        return ToSnapshot(entity, DeserializeReport(entity), auditEvents);
    }

    public async Task<ReconciliationCaseDecisionResult> DecideAsync(
        Guid customerId,
        Guid caseId,
        ReconciliationReviewDecision decision,
        string? note,
        string performedByClient,
        CancellationToken cancellationToken = default)
    {
        var entity = await _dbContext.ReconciliationCases
            .SingleOrDefaultAsync(
                item => item.Id == caseId && item.CustomerId == customerId,
                cancellationToken);

        if (entity is null)
        {
            return new ReconciliationCaseDecisionResult(
                ReconciliationCaseDecisionOutcome.NotFound);
        }

        if (decision is ReconciliationReviewDecision.Reject
            or ReconciliationReviewDecision.Resolve
            && string.IsNullOrWhiteSpace(note))
        {
            return new ReconciliationCaseDecisionResult(
                ReconciliationCaseDecisionOutcome.NoteRequired);
        }

        var action = decision.ToString();
        string previousStatus;
        try
        {
            previousStatus = entity.ApplyReviewDecision(action);
        }
        catch (InvalidOperationException)
        {
            return new ReconciliationCaseDecisionResult(
                ReconciliationCaseDecisionOutcome.InvalidTransition);
        }

        var auditEvent = new ReconciliationCaseAuditEvent(
            entity.Id,
            action,
            previousStatus,
            entity.ReviewStatus,
            note,
            performedByClient);

        _dbContext.ReconciliationCaseAuditEvents.Add(auditEvent);
        await _dbContext.SaveChangesAsync(cancellationToken);

        var previousEvents = await LoadAuditEventsAsync(caseId, cancellationToken);

        return new ReconciliationCaseDecisionResult(
            ReconciliationCaseDecisionOutcome.Completed,
            ToSnapshot(entity, DeserializeReport(entity), previousEvents));
    }

    private async Task<IReadOnlyList<ReconciliationCaseAuditEvent>> LoadAuditEventsAsync(
        Guid caseId,
        CancellationToken cancellationToken)
        => await _dbContext.ReconciliationCaseAuditEvents
            .AsNoTracking()
            .Where(item => item.ReconciliationCaseId == caseId)
            .OrderBy(item => item.OccurredAt)
            .ThenBy(item => item.Id)
            .ToArrayAsync(cancellationToken);

    private static InvoicePoReconciliationReport DeserializeReport(
        ReconciliationCase entity)
        => JsonSerializer.Deserialize<InvoicePoReconciliationReport>(entity.ReportJson)
            ?? throw new InvalidOperationException(
                $"Persisted reconciliation case '{entity.Id}' has an invalid report.");

    private static ReconciliationCaseSnapshot ToSnapshot(
        ReconciliationCase entity,
        InvoicePoReconciliationReport report,
        IReadOnlyList<ReconciliationCaseAuditEvent> auditEvents)
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
            report,
            auditEvents
                .Select(item => new ReconciliationCaseAuditEntry(
                    item.Id,
                    item.Action,
                    item.PreviousStatus,
                    item.NewStatus,
                    item.Note,
                    item.PerformedByClient,
                    item.OccurredAt))
                .ToArray());
}
