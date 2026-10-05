using System.Text.Json;
using System.Text.Json.Serialization;

namespace DocFlow.Application.Abstractions;

public sealed record AccountingBillPayload(
    string SchemaVersion,
    string SupplierName,
    string InvoiceNumber,
    DateOnly? InvoiceDate,
    DateOnly? DueDate,
    string Currency,
    string? CustomerReference,
    string? PurchaseOrderNumber,
    IReadOnlyList<AccountingBillLine> Lines,
    decimal? DiscountAmount,
    bool TaxInclusive,
    decimal? Subtotal,
    decimal? TaxRate,
    decimal? TaxAmount,
    decimal Total,
    IReadOnlyList<AccountingBillTax> Taxes,
    string? PaymentTerms,
    string? Notes)
{
    public const string CurrentSchemaVersion = "accounting_bill_v1";
}

public sealed record AccountingBillLine(
    string? Sku,
    string Description,
    decimal Quantity,
    string? Unit,
    decimal? UnitPrice,
    decimal? DiscountRate,
    decimal? LineTotal);

public sealed record AccountingBillTax(
    string? CategoryCode,
    decimal Rate,
    decimal TaxableAmount,
    decimal? TaxAmount);

public static class AccountingBillPayloadJson
{
    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        DefaultIgnoreCondition = JsonIgnoreCondition.Never
    };

    public static string Serialize(AccountingBillPayload payload)
        => JsonSerializer.Serialize(payload, JsonOptions);

    public static AccountingBillPayload Deserialize(string json)
    {
        using var document = JsonDocument.Parse(json);
        var root = document.RootElement;

        foreach (var requiredProperty in new[]
                 {
                     "schemaVersion",
                     "supplierName",
                     "invoiceNumber",
                     "currency",
                     "total",
                     "lines",
                     "taxes"
                 })
        {
            if (!root.TryGetProperty(requiredProperty, out _))
            {
                throw new InvalidOperationException(
                    $"Persisted accounting bill payload is missing required property '{requiredProperty}'.");
            }
        }

        var payload = JsonSerializer.Deserialize<AccountingBillPayload>(
            json,
            JsonOptions)
            ?? throw new InvalidOperationException(
                "Persisted accounting bill payload is invalid.");

        if (!string.Equals(
                payload.SchemaVersion,
                AccountingBillPayload.CurrentSchemaVersion,
                StringComparison.Ordinal))
        {
            throw new InvalidOperationException(
                $"Unsupported accounting bill schema version '{payload.SchemaVersion}'.");
        }

        if (string.IsNullOrWhiteSpace(payload.SupplierName)
            || string.IsNullOrWhiteSpace(payload.InvoiceNumber)
            || string.IsNullOrWhiteSpace(payload.Currency))
        {
            throw new InvalidOperationException(
                "Persisted accounting bill payload is missing required identity fields.");
        }

        if (payload.Lines is null || payload.Taxes is null)
        {
            throw new InvalidOperationException(
                "Persisted accounting bill payload collections are invalid.");
        }

        return payload;
    }
}
