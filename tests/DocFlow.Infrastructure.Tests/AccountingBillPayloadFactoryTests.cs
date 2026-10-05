using DocFlow.Application.Abstractions;
using DocFlow.Infrastructure.Processing;
using Xunit;

namespace DocFlow.Infrastructure.Tests;

public sealed class AccountingBillPayloadFactoryTests
{
    private readonly AccountingBillPayloadFactory _factory = new();

    [Fact]
    public void Build_NormalizesSupplierInvoiceIntoCanonicalBill()
    {
        const string json = """
        {
          "engine": "deterministic_supplier_invoice_v2",
          "document_type": "supplier_invoice",
          "data": {
            "supplier_name": " ACME Components Ltd. ",
            "invoice_number": " INV-2026-091 ",
            "invoice_date": "2026-09-30",
            "due_date": "2026-10-30",
            "currency": "eur",
            "customer_reference": "PO-78421",
            "purchase_order_number": "PO-78421",
            "items": [
              {
                "sku": "AX-100",
                "description": "Sensor bracket",
                "quantity": "20",
                "unit": "pcs",
                "unit_price": "12.50",
                "discount_rate": null,
                "line_total": "250.00"
              }
            ],
            "discount_amount": null,
            "tax_inclusive": false,
            "subtotal": "1457.00",
            "vat_amount": "291.40",
            "tax_breakdown": [
              {
                "category_code": "S",
                "rate": "20",
                "taxable_amount": "1457.00",
                "tax_amount": "291.40"
              }
            ],
            "total": "1748.40",
            "payment_terms": "Net 30",
            "notes": "Thank you."
          }
        }
        """;

        var result = _factory.Build(json);

        Assert.Equal(AccountingBillPayloadBuildOutcome.Completed, result.Outcome);
        var payload = Assert.IsType<AccountingBillPayload>(result.Payload);

        Assert.Equal(AccountingBillPayload.CurrentSchemaVersion, payload.SchemaVersion);
        Assert.Equal("ACME Components Ltd.", payload.SupplierName);
        Assert.Equal("INV-2026-091", payload.InvoiceNumber);
        Assert.Equal(new DateOnly(2026, 9, 30), payload.InvoiceDate);
        Assert.Equal(new DateOnly(2026, 10, 30), payload.DueDate);
        Assert.Equal("EUR", payload.Currency);
        Assert.Equal("PO-78421", payload.PurchaseOrderNumber);
        Assert.Equal(1457.00m, payload.Subtotal);
        Assert.Equal(291.40m, payload.TaxAmount);
        Assert.Equal(1748.40m, payload.Total);

        var line = Assert.Single(payload.Lines);
        Assert.Equal("AX-100", line.Sku);
        Assert.Equal(20m, line.Quantity);
        Assert.Equal(12.50m, line.UnitPrice);
        Assert.Equal(250.00m, line.LineTotal);

        var tax = Assert.Single(payload.Taxes);
        Assert.Equal("S", tax.CategoryCode);
        Assert.Equal(20m, tax.Rate);
        Assert.Equal(1457.00m, tax.TaxableAmount);
        Assert.Equal(291.40m, tax.TaxAmount);

        var canonicalJson = AccountingBillPayloadJson.Serialize(payload);
        Assert.Contains("\"schemaVersion\":\"accounting_bill_v1\"", canonicalJson);
        Assert.Contains("\"total\":1748.40", canonicalJson);
        Assert.DoesNotContain("\"engine\"", canonicalJson);
        Assert.DoesNotContain("\"validation\"", canonicalJson);

        var roundTrip = AccountingBillPayloadJson.Deserialize(canonicalJson);
        Assert.Equal(payload, roundTrip);
    }

    [Fact]
    public void Build_RejectsMissingRequiredTotal()
    {
        const string json = """
        {
          "data": {
            "supplier_name": "ACME Components Ltd.",
            "invoice_number": "INV-1",
            "currency": "EUR"
          }
        }
        """;

        var result = _factory.Build(json);

        Assert.Equal(
            AccountingBillPayloadBuildOutcome.MissingRequiredField,
            result.Outcome);
        Assert.Null(result.Payload);
        Assert.Contains("total", result.Error!, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void Build_RejectsMalformedDecimal()
    {
        const string json = """
        {
          "data": {
            "supplier_name": "ACME Components Ltd.",
            "invoice_number": "INV-1",
            "currency": "EUR",
            "total": "not-money"
          }
        }
        """;

        var result = _factory.Build(json);

        Assert.Equal(AccountingBillPayloadBuildOutcome.InvalidJson, result.Outcome);
        Assert.Null(result.Payload);
        Assert.Contains("total", result.Error!, StringComparison.OrdinalIgnoreCase);
    }
}
