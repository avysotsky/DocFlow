using System.Text.Json.Serialization;

namespace DocFlow.Application.Abstractions;

[JsonConverter(typeof(JsonStringEnumConverter))]
public enum ReconciliationReviewDecision
{
    Approve,
    Reject,
    Resolve
}

public enum ReconciliationCaseDecisionOutcome
{
    Completed,
    NotFound,
    InvalidTransition,
    NoteRequired
}

public sealed record ReconciliationCaseAuditEntry(
    Guid Id,
    string Action,
    string? PreviousStatus,
    string NewStatus,
    string? Note,
    string PerformedByClient,
    DateTimeOffset OccurredAt);

public sealed record ReconciliationCaseSnapshot(
    Guid Id,
    Guid CustomerId,
    Guid InvoiceDocumentId,
    Guid PurchaseOrderDocumentId,
    string ReconciliationStatus,
    string ReviewStatus,
    DateTimeOffset CreatedAt,
    DateTimeOffset UpdatedAt,
    string CreatedByClient,
    InvoicePoReconciliationReport Report,
    IReadOnlyList<ReconciliationCaseAuditEntry> AuditHistory);

public sealed record ReconciliationCaseCreateResult(
    InvoicePoReconciliationOutcome Outcome,
    ReconciliationCaseSnapshot? Case = null);

public sealed record ReconciliationCaseDecisionResult(
    ReconciliationCaseDecisionOutcome Outcome,
    ReconciliationCaseSnapshot? Case = null);

public interface IReconciliationCaseService
{
    Task<ReconciliationCaseCreateResult> CreateAsync(
        Guid customerId,
        Guid invoiceDocumentId,
        Guid purchaseOrderDocumentId,
        string createdByClient,
        CancellationToken cancellationToken = default);

    Task<ReconciliationCaseSnapshot?> GetAsync(
        Guid customerId,
        Guid caseId,
        CancellationToken cancellationToken = default);

    Task<ReconciliationCaseDecisionResult> DecideAsync(
        Guid customerId,
        Guid caseId,
        ReconciliationReviewDecision decision,
        string? note,
        string performedByClient,
        CancellationToken cancellationToken = default);
}
