using System.Text.Json.Serialization;

namespace DocFlow.Application.Abstractions;

public enum InvoicePoReconciliationOutcome
{
    Completed,
    InvoiceNotFound,
    PurchaseOrderNotFound,
    InvoiceExtractionResultNotFound,
    PurchaseOrderExtractionResultNotFound,
    InvalidInvoiceDocumentType,
    InvalidPurchaseOrderDocumentType
}

[JsonConverter(typeof(JsonStringEnumConverter))]
public enum ReconciliationCheckStatus
{
    Passed,
    NeedsReview,
    Skipped
}

public sealed record ReconciliationFieldCheck(
    string Field,
    ReconciliationCheckStatus Status,
    string? InvoiceValue,
    string? PurchaseOrderValue,
    string? Delta,
    string Message);

public sealed record ReconciliationItemResult(
    int InvoiceItemIndex,
    int? PurchaseOrderItemIndex,
    string MatchMethod,
    string? InvoiceSku,
    string InvoiceDescription,
    string? PurchaseOrderReference,
    string? PurchaseOrderDescription,
    ReconciliationCheckStatus Status,
    IReadOnlyList<ReconciliationFieldCheck> Checks);

public sealed record InvoicePoReconciliationReport(
    Guid InvoiceDocumentId,
    Guid PurchaseOrderDocumentId,
    string Status,
    IReadOnlyList<ReconciliationFieldCheck> DocumentChecks,
    IReadOnlyList<ReconciliationItemResult> InvoiceItems,
    IReadOnlyList<int> UnmatchedPurchaseOrderItemIndexes,
    int PassedChecks,
    int NeedsReviewChecks,
    int SkippedChecks);

public sealed record InvoicePoReconciliationResult(
    InvoicePoReconciliationOutcome Outcome,
    InvoicePoReconciliationReport? Report = null);

public interface IInvoicePurchaseOrderReconciliationService
{
    Task<InvoicePoReconciliationResult> ReconcileAsync(
        Guid customerId,
        Guid invoiceDocumentId,
        Guid purchaseOrderDocumentId,
        CancellationToken cancellationToken = default);
}
