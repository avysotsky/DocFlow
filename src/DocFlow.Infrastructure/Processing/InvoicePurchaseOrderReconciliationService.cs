using System.Globalization;
using System.Text;
using System.Text.Json;
using DocFlow.Application.Abstractions;
using DocFlow.Domain.Entities;
using DocFlow.Infrastructure.Persistence;
using Microsoft.EntityFrameworkCore;

namespace DocFlow.Infrastructure.Processing;

public sealed class InvoicePurchaseOrderReconciliationService
    : IInvoicePurchaseOrderReconciliationService
{
    private const decimal MoneyTolerance = 0.01m;

    private readonly DocFlowDbContext _dbContext;

    public InvoicePurchaseOrderReconciliationService(DocFlowDbContext dbContext)
    {
        _dbContext = dbContext;
    }

    public async Task<InvoicePoReconciliationResult> ReconcileAsync(
        Guid customerId,
        Guid invoiceDocumentId,
        Guid purchaseOrderDocumentId,
        CancellationToken cancellationToken = default)
    {
        var invoiceSource = await LoadSourceAsync(
            customerId,
            invoiceDocumentId,
            cancellationToken);

        if (invoiceSource is null)
            return new InvoicePoReconciliationResult(
                InvoicePoReconciliationOutcome.InvoiceNotFound);

        if (invoiceSource.ExtractionResult is null)
            return new InvoicePoReconciliationResult(
                InvoicePoReconciliationOutcome.InvoiceExtractionResultNotFound);

        if (!string.Equals(
                invoiceSource.DocumentType,
                "supplier_invoice",
                StringComparison.OrdinalIgnoreCase))
        {
            return new InvoicePoReconciliationResult(
                InvoicePoReconciliationOutcome.InvalidInvoiceDocumentType);
        }

        var purchaseOrderSource = await LoadSourceAsync(
            customerId,
            purchaseOrderDocumentId,
            cancellationToken);

        if (purchaseOrderSource is null)
            return new InvoicePoReconciliationResult(
                InvoicePoReconciliationOutcome.PurchaseOrderNotFound);

        if (purchaseOrderSource.ExtractionResult is null)
        {
            return new InvoicePoReconciliationResult(
                InvoicePoReconciliationOutcome.PurchaseOrderExtractionResultNotFound);
        }

        if (!string.Equals(
                purchaseOrderSource.DocumentType,
                "purchase_order",
                StringComparison.OrdinalIgnoreCase))
        {
            return new InvoicePoReconciliationResult(
                InvoicePoReconciliationOutcome.InvalidPurchaseOrderDocumentType);
        }

        var invoiceJson = ReviewedStructuredDataComposer.Compose(
            invoiceSource.ExtractionResult.StructuredDataJson,
            invoiceSource.Review);
        var purchaseOrderJson = ReviewedStructuredDataComposer.Compose(
            purchaseOrderSource.ExtractionResult.StructuredDataJson,
            purchaseOrderSource.Review);

        var invoice = ParseInvoice(invoiceJson);
        var purchaseOrder = ParsePurchaseOrder(purchaseOrderJson);

        var documentChecks = new[]
        {
            CompareIdentifier(
                "purchase_order_number",
                invoice.PurchaseOrderNumber,
                purchaseOrder.PurchaseOrderNumber,
                "Invoice PO reference matches the purchase order number.",
                "Invoice PO reference does not match the purchase order number.",
                "PO identity cannot be verified because one or both PO numbers are missing."),
            CompareText(
                "currency",
                invoice.Currency,
                purchaseOrder.Currency,
                "Invoice and purchase order currencies match.",
                "Invoice and purchase order currencies differ.",
                "Currency comparison is unavailable because one or both currencies are missing.")
        };

        var matchedPurchaseOrderIndexes = new HashSet<int>();
        var itemResults = new List<ReconciliationItemResult>();

        for (var invoiceIndex = 0; invoiceIndex < invoice.Items.Count; invoiceIndex++)
        {
            var invoiceItem = invoice.Items[invoiceIndex];
            var match = FindPurchaseOrderItem(
                invoiceItem,
                purchaseOrder.Items,
                matchedPurchaseOrderIndexes);

            if (match is null)
            {
                itemResults.Add(
                    new ReconciliationItemResult(
                        invoiceIndex + 1,
                        null,
                        "none",
                        invoiceItem.Sku,
                        invoiceItem.Description,
                        null,
                        null,
                        ReconciliationCheckStatus.NeedsReview,
                        [
                            new ReconciliationFieldCheck(
                                "item_match",
                                ReconciliationCheckStatus.NeedsReview,
                                invoiceItem.Sku ?? invoiceItem.Description,
                                null,
                                null,
                                "No exact PO line match was found by SKU/reference or normalized description.")
                        ]));
                continue;
            }

            matchedPurchaseOrderIndexes.Add(match.Value.Index);
            var poItem = match.Value.Item;
            var checks = new[]
            {
                CompareDecimal(
                    "quantity",
                    invoiceItem.Quantity,
                    poItem.Quantity,
                    "Invoice quantity matches the PO line.",
                    "Invoice quantity differs from the PO line.",
                    "Quantity comparison is unavailable because one side is missing."),
                CompareDecimal(
                    "unit_price",
                    invoiceItem.UnitPrice,
                    poItem.UnitPrice,
                    "Invoice unit price matches the PO line.",
                    "Invoice unit price differs from the PO line.",
                    "Unit-price comparison is unavailable because one side is missing."),
                CompareDecimal(
                    "line_total",
                    invoiceItem.LineTotal,
                    poItem.LineTotal,
                    "Invoice line total matches the PO line.",
                    "Invoice line total differs from the PO line.",
                    "Line-total comparison is unavailable because one side is missing.")
            };

            var itemStatus = checks.All(check =>
                    check.Status == ReconciliationCheckStatus.Passed)
                ? ReconciliationCheckStatus.Passed
                : ReconciliationCheckStatus.NeedsReview;

            itemResults.Add(
                new ReconciliationItemResult(
                    invoiceIndex + 1,
                    match.Value.Index + 1,
                    match.Value.Method,
                    invoiceItem.Sku,
                    invoiceItem.Description,
                    poItem.SupplierReference,
                    poItem.Description,
                    itemStatus,
                    checks));
        }

        var unmatchedPurchaseOrderIndexes = purchaseOrder.Items
            .Select((_, index) => index)
            .Where(index => !matchedPurchaseOrderIndexes.Contains(index))
            .Select(index => index + 1)
            .ToArray();

        var allChecks = documentChecks
            .Concat(itemResults.SelectMany(item => item.Checks))
            .ToArray();

        var passedChecks = allChecks.Count(
            check => check.Status == ReconciliationCheckStatus.Passed);
        var needsReviewChecks = allChecks.Count(
            check => check.Status == ReconciliationCheckStatus.NeedsReview);
        var skippedChecks = allChecks.Count(
            check => check.Status == ReconciliationCheckStatus.Skipped);

        var isMatch = invoice.Items.Count > 0
            && documentChecks.All(
                check => check.Status == ReconciliationCheckStatus.Passed)
            && itemResults.All(
                item => item.Status == ReconciliationCheckStatus.Passed);

        var report = new InvoicePoReconciliationReport(
            invoiceDocumentId,
            purchaseOrderDocumentId,
            isMatch ? "Match" : "NeedsReview",
            documentChecks,
            itemResults,
            unmatchedPurchaseOrderIndexes,
            passedChecks,
            needsReviewChecks,
            skippedChecks);

        return new InvoicePoReconciliationResult(
            InvoicePoReconciliationOutcome.Completed,
            report);
    }

    private async Task<ReconciliationSource?> LoadSourceAsync(
        Guid customerId,
        Guid documentId,
        CancellationToken cancellationToken)
    {
        return await (
                from document in _dbContext.Documents.AsNoTracking()
                join extractionResult in _dbContext.ExtractionResults.AsNoTracking()
                    on document.Id equals extractionResult.DocumentId into extractionResults
                from extractionResult in extractionResults.DefaultIfEmpty()
                join review in _dbContext.DocumentReviews.AsNoTracking()
                    on document.Id equals review.DocumentId into reviews
                from review in reviews.DefaultIfEmpty()
                where document.Id == documentId && document.CustomerId == customerId
                select new ReconciliationSource(
                    document.DocumentType,
                    extractionResult,
                    review))
            .SingleOrDefaultAsync(cancellationToken);
    }

    private static ParsedInvoice ParseInvoice(string json)
    {
        using var document = JsonDocument.Parse(json);
        var data = GetData(document.RootElement);

        return new ParsedInvoice(
            ReadText(data, "purchase_order_number"),
            ReadText(data, "currency"),
            ReadInvoiceItems(data));
    }

    private static ParsedPurchaseOrder ParsePurchaseOrder(string json)
    {
        using var document = JsonDocument.Parse(json);
        var data = GetData(document.RootElement);

        return new ParsedPurchaseOrder(
            ReadText(data, "purchase_order_number"),
            ReadText(data, "currency"),
            ReadPurchaseOrderItems(data));
    }

    private static JsonElement GetData(JsonElement root)
    {
        if (!root.TryGetProperty("data", out var data)
            || data.ValueKind != JsonValueKind.Object)
        {
            throw new InvalidOperationException(
                "Persisted structured extraction result is missing object-valued data.");
        }

        return data;
    }

    private static IReadOnlyList<InvoiceLine> ReadInvoiceItems(JsonElement data)
    {
        if (!data.TryGetProperty("items", out var items)
            || items.ValueKind != JsonValueKind.Array)
        {
            return [];
        }

        return items
            .EnumerateArray()
            .Where(item => item.ValueKind == JsonValueKind.Object)
            .Select(item => new InvoiceLine(
                ReadText(item, "sku"),
                ReadText(item, "description") ?? string.Empty,
                ReadDecimal(item, "quantity"),
                ReadDecimal(item, "unit_price"),
                ReadDecimal(item, "line_total")))
            .ToArray();
    }

    private static IReadOnlyList<PurchaseOrderLine> ReadPurchaseOrderItems(
        JsonElement data)
    {
        if (!data.TryGetProperty("items", out var items)
            || items.ValueKind != JsonValueKind.Array)
        {
            return [];
        }

        return items
            .EnumerateArray()
            .Where(item => item.ValueKind == JsonValueKind.Object)
            .Select(item => new PurchaseOrderLine(
                ReadText(item, "supplier_reference"),
                ReadText(item, "description") ?? string.Empty,
                ReadDecimal(item, "quantity"),
                ReadDecimal(item, "unit_price"),
                ReadDecimal(item, "line_total")))
            .ToArray();
    }

    private static ItemMatch? FindPurchaseOrderItem(
        InvoiceLine invoiceItem,
        IReadOnlyList<PurchaseOrderLine> purchaseOrderItems,
        ISet<int> alreadyMatched)
    {
        var normalizedSku = NormalizeIdentifier(invoiceItem.Sku);
        if (!string.IsNullOrEmpty(normalizedSku))
        {
            for (var index = 0; index < purchaseOrderItems.Count; index++)
            {
                if (alreadyMatched.Contains(index))
                    continue;

                var poReference = NormalizeIdentifier(
                    purchaseOrderItems[index].SupplierReference);
                if (!string.IsNullOrEmpty(poReference)
                    && string.Equals(
                        normalizedSku,
                        poReference,
                        StringComparison.Ordinal))
                {
                    return new ItemMatch(index, purchaseOrderItems[index], "sku_reference");
                }
            }
        }

        var normalizedDescription = NormalizeDescription(invoiceItem.Description);
        if (!string.IsNullOrEmpty(normalizedDescription))
        {
            for (var index = 0; index < purchaseOrderItems.Count; index++)
            {
                if (alreadyMatched.Contains(index))
                    continue;

                if (string.Equals(
                        normalizedDescription,
                        NormalizeDescription(purchaseOrderItems[index].Description),
                        StringComparison.Ordinal))
                {
                    return new ItemMatch(index, purchaseOrderItems[index], "description_exact");
                }
            }
        }

        return null;
    }

    private static ReconciliationFieldCheck CompareIdentifier(
        string field,
        string? invoiceValue,
        string? purchaseOrderValue,
        string passMessage,
        string failMessage,
        string skippedMessage)
    {
        if (string.IsNullOrWhiteSpace(invoiceValue)
            || string.IsNullOrWhiteSpace(purchaseOrderValue))
        {
            return new ReconciliationFieldCheck(
                field,
                ReconciliationCheckStatus.Skipped,
                invoiceValue,
                purchaseOrderValue,
                null,
                skippedMessage);
        }

        var matches = string.Equals(
            NormalizeIdentifier(invoiceValue),
            NormalizeIdentifier(purchaseOrderValue),
            StringComparison.Ordinal);

        return new ReconciliationFieldCheck(
            field,
            matches
                ? ReconciliationCheckStatus.Passed
                : ReconciliationCheckStatus.NeedsReview,
            invoiceValue,
            purchaseOrderValue,
            null,
            matches ? passMessage : failMessage);
    }

    private static ReconciliationFieldCheck CompareText(
        string field,
        string? invoiceValue,
        string? purchaseOrderValue,
        string passMessage,
        string failMessage,
        string skippedMessage)
    {
        if (string.IsNullOrWhiteSpace(invoiceValue)
            || string.IsNullOrWhiteSpace(purchaseOrderValue))
        {
            return new ReconciliationFieldCheck(
                field,
                ReconciliationCheckStatus.Skipped,
                invoiceValue,
                purchaseOrderValue,
                null,
                skippedMessage);
        }

        var matches = string.Equals(
            invoiceValue.Trim(),
            purchaseOrderValue.Trim(),
            StringComparison.OrdinalIgnoreCase);

        return new ReconciliationFieldCheck(
            field,
            matches
                ? ReconciliationCheckStatus.Passed
                : ReconciliationCheckStatus.NeedsReview,
            invoiceValue,
            purchaseOrderValue,
            null,
            matches ? passMessage : failMessage);
    }

    private static ReconciliationFieldCheck CompareDecimal(
        string field,
        decimal? invoiceValue,
        decimal? purchaseOrderValue,
        string passMessage,
        string failMessage,
        string skippedMessage)
    {
        if (invoiceValue is null || purchaseOrderValue is null)
        {
            return new ReconciliationFieldCheck(
                field,
                ReconciliationCheckStatus.Skipped,
                FormatDecimal(invoiceValue),
                FormatDecimal(purchaseOrderValue),
                null,
                skippedMessage);
        }

        var delta = invoiceValue.Value - purchaseOrderValue.Value;
        var matches = Math.Abs(delta) <= MoneyTolerance;

        return new ReconciliationFieldCheck(
            field,
            matches
                ? ReconciliationCheckStatus.Passed
                : ReconciliationCheckStatus.NeedsReview,
            FormatDecimal(invoiceValue),
            FormatDecimal(purchaseOrderValue),
            delta.ToString("0.####", CultureInfo.InvariantCulture),
            matches ? passMessage : failMessage);
    }

    private static string? ReadText(JsonElement element, string propertyName)
    {
        if (!element.TryGetProperty(propertyName, out var value)
            || value.ValueKind is JsonValueKind.Null or JsonValueKind.Undefined)
        {
            return null;
        }

        return value.ValueKind switch
        {
            JsonValueKind.String => value.GetString(),
            JsonValueKind.Number => value.GetRawText(),
            _ => value.ToString()
        };
    }

    private static decimal? ReadDecimal(JsonElement element, string propertyName)
    {
        var text = ReadText(element, propertyName);
        if (string.IsNullOrWhiteSpace(text))
            return null;

        return decimal.TryParse(
            text,
            NumberStyles.Number | NumberStyles.AllowLeadingSign,
            CultureInfo.InvariantCulture,
            out var value)
            ? value
            : null;
    }

    private static string NormalizeIdentifier(string? value)
    {
        if (string.IsNullOrWhiteSpace(value))
            return string.Empty;

        var builder = new StringBuilder();
        foreach (var character in value.Trim())
        {
            if (char.IsLetterOrDigit(character))
                builder.Append(char.ToUpperInvariant(character));
        }
        return builder.ToString();
    }

    private static string NormalizeDescription(string? value)
    {
        if (string.IsNullOrWhiteSpace(value))
            return string.Empty;

        var builder = new StringBuilder();
        var previousWasSeparator = false;

        foreach (var character in value.Trim().ToLowerInvariant())
        {
            if (char.IsLetterOrDigit(character))
            {
                builder.Append(character);
                previousWasSeparator = false;
            }
            else if (!previousWasSeparator)
            {
                builder.Append(' ');
                previousWasSeparator = true;
            }
        }

        return string.Join(
            ' ',
            builder
                .ToString()
                .Split(' ', StringSplitOptions.RemoveEmptyEntries));
    }

    private static string? FormatDecimal(decimal? value)
        => value?.ToString("0.####", CultureInfo.InvariantCulture);

    private sealed record ReconciliationSource(
        string? DocumentType,
        ExtractionResult? ExtractionResult,
        DocumentReview? Review);

    private sealed record ParsedInvoice(
        string? PurchaseOrderNumber,
        string? Currency,
        IReadOnlyList<InvoiceLine> Items);

    private sealed record ParsedPurchaseOrder(
        string? PurchaseOrderNumber,
        string? Currency,
        IReadOnlyList<PurchaseOrderLine> Items);

    private sealed record InvoiceLine(
        string? Sku,
        string Description,
        decimal? Quantity,
        decimal? UnitPrice,
        decimal? LineTotal);

    private sealed record PurchaseOrderLine(
        string? SupplierReference,
        string Description,
        decimal? Quantity,
        decimal? UnitPrice,
        decimal? LineTotal);

    private readonly record struct ItemMatch(
        int Index,
        PurchaseOrderLine Item,
        string Method);
}
