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
        => JsonSerializer.Deserialize<AccountingBillPayload>(json, JsonOptions)
            ?? throw new InvalidOperationException(
                "Persisted accounting bill payload is invalid.");
}
