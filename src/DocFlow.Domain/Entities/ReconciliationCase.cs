namespace DocFlow.Domain.Entities;

public sealed class ReconciliationCase
{
    public const int MaxStatusLength = 32;
    public const int MaxClientNameLength = 200;

    public Guid Id { get; private set; }
    public Guid CustomerId { get; private set; }
    public Guid InvoiceDocumentId { get; private set; }
    public Guid PurchaseOrderDocumentId { get; private set; }
    public string ReconciliationStatus { get; private set; } = string.Empty;
    public string ReviewStatus { get; private set; } = string.Empty;
    public string ReportJson { get; private set; } = string.Empty;
    public DateTimeOffset CreatedAt { get; private set; }
    public DateTimeOffset UpdatedAt { get; private set; }
    public string CreatedByClient { get; private set; } = string.Empty;

    private ReconciliationCase()
    {
    }

    public ReconciliationCase(
        Guid customerId,
        Guid invoiceDocumentId,
        Guid purchaseOrderDocumentId,
        string reconciliationStatus,
        string reviewStatus,
        string reportJson,
        string createdByClient)
    {
        if (customerId == Guid.Empty)
            throw new ArgumentException("Customer id is required.", nameof(customerId));
        if (invoiceDocumentId == Guid.Empty)
            throw new ArgumentException("Invoice document id is required.", nameof(invoiceDocumentId));
        if (purchaseOrderDocumentId == Guid.Empty)
            throw new ArgumentException("Purchase-order document id is required.", nameof(purchaseOrderDocumentId));
        if (invoiceDocumentId == purchaseOrderDocumentId)
            throw new ArgumentException("Invoice and purchase-order document ids must be different.");
        if (string.IsNullOrWhiteSpace(reconciliationStatus))
            throw new ArgumentException("Reconciliation status is required.", nameof(reconciliationStatus));
        if (string.IsNullOrWhiteSpace(reviewStatus))
            throw new ArgumentException("Review status is required.", nameof(reviewStatus));
        if (string.IsNullOrWhiteSpace(reportJson))
            throw new ArgumentException("Reconciliation report is required.", nameof(reportJson));
        if (string.IsNullOrWhiteSpace(createdByClient))
            throw new ArgumentException("Creator client attribution is required.", nameof(createdByClient));

        var normalizedReconciliationStatus = reconciliationStatus.Trim();
        var normalizedReviewStatus = reviewStatus.Trim();
        var normalizedClient = createdByClient.Trim();

        if (normalizedReconciliationStatus.Length > MaxStatusLength)
            throw new ArgumentOutOfRangeException(nameof(reconciliationStatus));
        if (normalizedReviewStatus.Length > MaxStatusLength)
            throw new ArgumentOutOfRangeException(nameof(reviewStatus));
        if (normalizedClient.Length > MaxClientNameLength)
            throw new ArgumentOutOfRangeException(nameof(createdByClient));

        Id = Guid.NewGuid();
        CustomerId = customerId;
        InvoiceDocumentId = invoiceDocumentId;
        PurchaseOrderDocumentId = purchaseOrderDocumentId;
        ReconciliationStatus = normalizedReconciliationStatus;
        ReviewStatus = normalizedReviewStatus;
        ReportJson = reportJson;
        CreatedByClient = normalizedClient;
        CreatedAt = DateTimeOffset.UtcNow;
        UpdatedAt = CreatedAt;
    }
}
