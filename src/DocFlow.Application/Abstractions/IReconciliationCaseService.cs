namespace DocFlow.Application.Abstractions;

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
    InvoicePoReconciliationReport Report);

public sealed record ReconciliationCaseCreateResult(
    InvoicePoReconciliationOutcome Outcome,
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
}
