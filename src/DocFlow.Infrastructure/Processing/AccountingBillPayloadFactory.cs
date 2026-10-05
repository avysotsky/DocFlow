using System.Globalization;
using System.Text.Json;
using DocFlow.Application.Abstractions;

namespace DocFlow.Infrastructure.Processing;

public sealed class AccountingBillPayloadFactory
    : IAccountingBillPayloadFactory
{
    public AccountingBillPayloadBuildResult Build(string structuredDataJson)
    {
        if (string.IsNullOrWhiteSpace(structuredDataJson))
        {
            return Invalid(
                AccountingBillPayloadBuildOutcome.InvalidJson,
                "Structured invoice data is empty.");
        }

        try
        {
            using var document = JsonDocument.Parse(structuredDataJson);
            var root = document.RootElement;

            if (!root.TryGetProperty("data", out var data)
                || data.ValueKind != JsonValueKind.Object)
            {
                return Invalid(
                    AccountingBillPayloadBuildOutcome.InvalidJson,
                    "Structured invoice data is missing object-valued data.");
            }

            var supplierName = RequiredText(
                data,
                "supplier_name",
                "Supplier name is required for accounting posting.");
            if (!supplierName.Success)
                return supplierName.Error!;

            var invoiceNumber = RequiredText(
                data,
                "invoice_number",
                "Invoice number is required for accounting posting.");
            if (!invoiceNumber.Success)
                return invoiceNumber.Error!;

            var currency = RequiredText(
                data,
                "currency",
                "Currency is required for accounting posting.");
            if (!currency.Success)
                return currency.Error!;

            var total = ReadDecimal(data, "total");
            if (total is null)
            {
                return Invalid(
                    AccountingBillPayloadBuildOutcome.MissingRequiredField,
                    "Invoice total is required for accounting posting.");
            }

            var lines = ReadLines(data);
            var taxes = ReadTaxes(data);

            var payload = new AccountingBillPayload(
                AccountingBillPayload.CurrentSchemaVersion,
                supplierName.Value!,
                invoiceNumber.Value!,
                ReadDate(data, "invoice_date"),
                ReadDate(data, "due_date"),
                currency.Value!.ToUpperInvariant(),
                ReadText(data, "customer_reference"),
                ReadText(data, "purchase_order_number"),
                lines,
                ReadDecimal(data, "discount_amount"),
                ReadBoolean(data, "tax_inclusive") ?? false,
                ReadDecimal(data, "subtotal"),
                ReadDecimal(data, "vat_amount"),
                total.Value,
                taxes,
                ReadText(data, "payment_terms"),
                ReadText(data, "notes"));

            return new AccountingBillPayloadBuildResult(
                AccountingBillPayloadBuildOutcome.Completed,
                payload);
        }
        catch (JsonException exception)
        {
            return Invalid(
                AccountingBillPayloadBuildOutcome.InvalidJson,
                $"Structured invoice JSON is invalid: {exception.Message}");
        }
        catch (FormatException exception)
        {
            return Invalid(
                AccountingBillPayloadBuildOutcome.InvalidJson,
                exception.Message);
        }
    }

    private static IReadOnlyList<AccountingBillLine> ReadLines(JsonElement data)
    {
        if (!data.TryGetProperty("items", out var items)
            || items.ValueKind != JsonValueKind.Array)
        {
            return [];
        }

        var lines = new List<AccountingBillLine>();
        foreach (var item in items.EnumerateArray())
        {
            if (item.ValueKind != JsonValueKind.Object)
                continue;

            var description = ReadText(item, "description") ?? string.Empty;
            var quantity = ReadDecimal(item, "quantity") ?? 0m;

            lines.Add(
                new AccountingBillLine(
                    ReadText(item, "sku"),
                    description,
                    quantity,
                    ReadText(item, "unit"),
                    ReadDecimal(item, "unit_price"),
                    ReadDecimal(item, "discount_rate"),
                    ReadDecimal(item, "line_total")));
        }

        return lines;
    }

    private static IReadOnlyList<AccountingBillTax> ReadTaxes(JsonElement data)
    {
        if (!data.TryGetProperty("tax_breakdown", out var taxes)
            || taxes.ValueKind != JsonValueKind.Array)
        {
            return [];
        }

        var results = new List<AccountingBillTax>();
        foreach (var item in taxes.EnumerateArray())
        {
            if (item.ValueKind != JsonValueKind.Object)
                continue;

            var rate = ReadDecimal(item, "rate");
            var taxableAmount = ReadDecimal(item, "taxable_amount");
            if (rate is null || taxableAmount is null)
                continue;

            results.Add(
                new AccountingBillTax(
                    ReadText(item, "category_code"),
                    rate.Value,
                    taxableAmount.Value,
                    ReadDecimal(item, "tax_amount")));
        }

        return results;
    }

    private static RequiredTextResult RequiredText(
        JsonElement element,
        string propertyName,
        string error)
    {
        var value = ReadText(element, propertyName);
        return string.IsNullOrWhiteSpace(value)
            ? new RequiredTextResult(
                false,
                null,
                Invalid(
                    AccountingBillPayloadBuildOutcome.MissingRequiredField,
                    error))
            : new RequiredTextResult(true, value.Trim(), null);
    }

    private static string? ReadText(
        JsonElement element,
        string propertyName)
    {
        if (!element.TryGetProperty(propertyName, out var property)
            || property.ValueKind is JsonValueKind.Null
                or JsonValueKind.Undefined)
        {
            return null;
        }

        return property.ValueKind == JsonValueKind.String
            ? property.GetString()?.Trim()
            : property.ToString().Trim();
    }

    private static DateOnly? ReadDate(
        JsonElement element,
        string propertyName)
    {
        var value = ReadText(element, propertyName);
        if (string.IsNullOrWhiteSpace(value))
            return null;

        if (DateOnly.TryParseExact(
            value,
            "yyyy-MM-dd",
            CultureInfo.InvariantCulture,
            DateTimeStyles.None,
            out var parsed))
        {
            return parsed;
        }

        throw new FormatException(
            $"Invoice field '{propertyName}' is not a valid ISO date.");
    }

    private static decimal? ReadDecimal(
        JsonElement element,
        string propertyName)
    {
        if (!element.TryGetProperty(propertyName, out var property)
            || property.ValueKind is JsonValueKind.Null
                or JsonValueKind.Undefined)
        {
            return null;
        }

        if (property.ValueKind == JsonValueKind.Number
            && property.TryGetDecimal(out var numeric))
        {
            return numeric;
        }

        if (property.ValueKind == JsonValueKind.String
            && decimal.TryParse(
                property.GetString(),
                NumberStyles.Number,
                CultureInfo.InvariantCulture,
                out var parsed))
        {
            return parsed;
        }

        throw new FormatException(
            $"Invoice field '{propertyName}' is not a valid decimal.");
    }

    private static bool? ReadBoolean(
        JsonElement element,
        string propertyName)
    {
        if (!element.TryGetProperty(propertyName, out var property)
            || property.ValueKind is JsonValueKind.Null
                or JsonValueKind.Undefined)
        {
            return null;
        }

        if (property.ValueKind is JsonValueKind.True or JsonValueKind.False)
            return property.GetBoolean();

        if (property.ValueKind == JsonValueKind.String
            && bool.TryParse(property.GetString(), out var parsed))
        {
            return parsed;
        }

        throw new FormatException(
            $"Invoice field '{propertyName}' is not a valid boolean.");
    }

    private static AccountingBillPayloadBuildResult Invalid(
        AccountingBillPayloadBuildOutcome outcome,
        string error)
        => new(outcome, Error: error);

    private sealed record RequiredTextResult(
        bool Success,
        string? Value,
        AccountingBillPayloadBuildResult? Error);
}
