using System.Text.Json;
using DocFlow.Application.Abstractions;
using DocFlow.Infrastructure.Accounting.QuickBooksOnline;
using Xunit;

namespace DocFlow.Infrastructure.Tests;

public sealed class QuickBooksOnlineBillRequestBuilderTests
{
    private static readonly Guid CustomerId =
        Guid.Parse("11111111-1111-1111-1111-111111111111");

    [Fact]
    public void Build_MapsCanonicalBillToAccountBasedExpenseBill()
    {
        var builder = CreateBuilder();

        var result = builder.Build(CreatePosting());

        Assert.Equal(QuickBooksOnlineBillBuildOutcome.Completed, result.Outcome);
        var request = Assert.IsType<QuickBooksOnlineBillRequest>(result.Request);

        Assert.Equal("vendor-41", request.VendorRef.Value);
        Assert.Equal("ap-33", request.APAccountRef.Value);
        Assert.Equal("INV-2026-091", request.DocNumber);
        Assert.Equal("2026-09-30", request.TxnDate);
        Assert.Equal("2026-10-30", request.DueDate);
        Assert.Equal("EUR", request.CurrencyRef.Value);
        Assert.Equal("Supplier note", request.PrivateNote);

        Assert.Equal(2, request.Line.Count);

        var skuLine = request.Line[0];
        Assert.Equal(250.00m, skuLine.Amount);
        Assert.Equal("AccountBasedExpenseLineDetail", skuLine.DetailType);
        Assert.Equal(
            "expense-components",
            skuLine.AccountBasedExpenseLineDetail.AccountRef.Value);
        Assert.Equal(
            "vat-20",
            skuLine.AccountBasedExpenseLineDetail.TaxCodeRef!.Value);

        var fallbackLine = request.Line[1];
        Assert.Equal(90.00m, fallbackLine.Amount);
        Assert.Equal(
            "expense-default",
            fallbackLine.AccountBasedExpenseLineDetail.AccountRef.Value);

        var json = QuickBooksOnlineBillRequestJson.Serialize(request);
        using var document = JsonDocument.Parse(json);
        var root = document.RootElement;

        Assert.Equal(
            "vendor-41",
            root.GetProperty("VendorRef").GetProperty("value").GetString());
        Assert.Equal(
            "ap-33",
            root.GetProperty("APAccountRef").GetProperty("value").GetString());
        Assert.Equal(
            "EUR",
            root.GetProperty("CurrencyRef").GetProperty("value").GetString());

        var firstLine = root.GetProperty("Line")[0];
        Assert.Equal(
            "AccountBasedExpenseLineDetail",
            firstLine.GetProperty("DetailType").GetString());
        Assert.Equal(
            "expense-components",
            firstLine
                .GetProperty("AccountBasedExpenseLineDetail")
                .GetProperty("AccountRef")
                .GetProperty("value")
                .GetString());
        Assert.Equal(
            "vat-20",
            firstLine
                .GetProperty("AccountBasedExpenseLineDetail")
                .GetProperty("TaxCodeRef")
                .GetProperty("value")
                .GetString());
    }

    [Fact]
    public void Build_RejectsUnmappedVendor()
    {
        var builder = CreateBuilder();
        var posting = CreatePosting() with
        {
            Payload = CreatePosting().Payload with
            {
                SupplierName = "Unknown Supplier"
            }
        };

        var result = builder.Build(posting);

        Assert.Equal(
            QuickBooksOnlineBillBuildOutcome.VendorNotMapped,
            result.Outcome);
        Assert.Null(result.Request);
    }

    [Fact]
    public void Build_RejectsUnmappedTaxRate()
    {
        var builder = CreateBuilder();
        var posting = CreatePosting() with
        {
            Payload = CreatePosting().Payload with
            {
                TaxRate = 7m
            }
        };

        var result = builder.Build(posting);

        Assert.Equal(
            QuickBooksOnlineBillBuildOutcome.TaxCodeNotMapped,
            result.Outcome);
        Assert.Null(result.Request);
    }

    [Fact]
    public void Build_RejectsUnknownTenantTarget()
    {
        var builder = CreateBuilder();
        var posting = CreatePosting() with
        {
            TargetKey = "secondary-ledger"
        };

        var result = builder.Build(posting);

        Assert.Equal(
            QuickBooksOnlineBillBuildOutcome.TargetMappingNotFound,
            result.Outcome);
        Assert.Null(result.Request);
    }

    private static QuickBooksOnlineBillRequestBuilder CreateBuilder()
        => new(
            new QuickBooksOnlineBillMappingOptions
            {
                Targets =
                [
                    new QuickBooksOnlineTargetMappingOptions
                    {
                        CustomerId = CustomerId,
                        TargetKey = "primary-ledger",
                        ApAccountId = "ap-33",
                        DefaultExpenseAccountId = "expense-default",
                        Vendors =
                        [
                            new QuickBooksOnlineVendorMappingOptions
                            {
                                SupplierName = "ACME Components Ltd.",
                                VendorId = "vendor-41"
                            }
                        ],
                        ExpenseAccounts =
                        [
                            new QuickBooksOnlineExpenseAccountMappingOptions
                            {
                                Sku = "AX-100",
                                AccountId = "expense-components"
                            }
                        ],
                        TaxCodes =
                        [
                            new QuickBooksOnlineTaxCodeMappingOptions
                            {
                                Rate = 20m,
                                TaxCodeId = "vat-20"
                            }
                        ]
                    }
                ]
            });

    private static AccountingPostingRequest CreatePosting()
        => new(
            Guid.Parse("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
            CustomerId,
            Guid.Parse("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"),
            "primary-ledger",
            "realm-123",
            "posting-key-1",
            new AccountingBillPayload(
                AccountingBillPayload.CurrentSchemaVersion,
                "ACME Components Ltd.",
                "INV-2026-091",
                new DateOnly(2026, 9, 30),
                new DateOnly(2026, 10, 30),
                "eur",
                "customer-ref",
                "PO-78421",
                [
                    new AccountingBillLine(
                        "AX-100",
                        "Sensor bracket",
                        20m,
                        "pcs",
                        12.50m,
                        null,
                        250.00m),
                    new AccountingBillLine(
                        "OTHER",
                        "Fallback expense",
                        2m,
                        "pcs",
                        50.00m,
                        10m,
                        null)
                ],
                null,
                false,
                340.00m,
                20m,
                68.00m,
                408.00m,
                [
                    new AccountingBillTax(
                        "S",
                        20m,
                        340.00m,
                        68.00m)
                ],
                "Net 30",
                "Supplier note"));
}
