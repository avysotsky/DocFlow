using DocFlow.Application.Abstractions;

namespace DocFlow.Infrastructure.Accounting.QuickBooksOnline;

public enum QuickBooksOnlineBillBuildOutcome
{
    Completed,
    TargetMappingNotFound,
    VendorNotMapped,
    TaxCodeNotMapped,
    InvalidLineAmount
}

public sealed record QuickBooksOnlineBillBuildResult(
    QuickBooksOnlineBillBuildOutcome Outcome,
    QuickBooksOnlineBillRequest? Request = null,
    string? Error = null);

public sealed class QuickBooksOnlineBillRequestBuilder
{
    private readonly IReadOnlyList<QuickBooksOnlineTargetMappingOptions> _targets;

    public QuickBooksOnlineBillRequestBuilder(
        QuickBooksOnlineBillMappingOptions options)
    {
        _targets = options.Targets;
    }

    public QuickBooksOnlineBillBuildResult Build(
        AccountingPostingRequest posting)
    {
        var target = _targets.SingleOrDefault(item =>
            item.CustomerId == posting.CustomerId
            && string.Equals(
                item.TargetKey.Trim(),
                posting.TargetKey.Trim(),
                StringComparison.OrdinalIgnoreCase));

        if (target is null)
        {
            return Failure(
                QuickBooksOnlineBillBuildOutcome.TargetMappingNotFound,
                "QuickBooks Online mapping was not found for the accounting target.");
        }

        var vendor = target.Vendors.SingleOrDefault(item =>
            string.Equals(
                item.SupplierName.Trim(),
                posting.Payload.SupplierName.Trim(),
                StringComparison.OrdinalIgnoreCase));

        if (vendor is null)
        {
            return Failure(
                QuickBooksOnlineBillBuildOutcome.VendorNotMapped,
                $"Supplier '{posting.Payload.SupplierName}' is not mapped to a QuickBooks Online vendor.");
        }

        QuickBooksOnlineReference? taxCodeRef = null;
        if (posting.Payload.TaxRate is decimal taxRate)
        {
            var taxCode = target.TaxCodes.SingleOrDefault(item =>
                item.Rate == taxRate);

            if (taxCode is null)
            {
                return Failure(
                    QuickBooksOnlineBillBuildOutcome.TaxCodeNotMapped,
                    $"Tax rate '{taxRate}' is not mapped to a QuickBooks Online tax code.");
            }

            taxCodeRef = new QuickBooksOnlineReference(taxCode.TaxCodeId.Trim());
        }

        var lines = new List<QuickBooksOnlineBillLine>(
            posting.Payload.Lines.Count);

        foreach (var sourceLine in posting.Payload.Lines)
        {
            var amount = ResolveLineAmount(sourceLine);
            if (amount is null || amount <= 0)
            {
                return Failure(
                    QuickBooksOnlineBillBuildOutcome.InvalidLineAmount,
                    $"Line '{sourceLine.Description}' does not have a positive posting amount.");
            }

            var expenseAccountId = ResolveExpenseAccountId(target, sourceLine);
            lines.Add(
                new QuickBooksOnlineBillLine(
                    amount.Value,
                    "AccountBasedExpenseLineDetail",
                    string.IsNullOrWhiteSpace(sourceLine.Description)
                        ? null
                        : sourceLine.Description.Trim(),
                    new QuickBooksOnlineAccountBasedExpenseLineDetail(
                        new QuickBooksOnlineReference(expenseAccountId),
                        taxCodeRef)));
        }

        if (lines.Count == 0)
        {
            return Failure(
                QuickBooksOnlineBillBuildOutcome.InvalidLineAmount,
                "QuickBooks Online bills require at least one expense line.");
        }

        var request = new QuickBooksOnlineBillRequest(
            new QuickBooksOnlineReference(vendor.VendorId.Trim()),
            new QuickBooksOnlineReference(target.ApAccountId.Trim()),
            posting.Payload.InvoiceNumber.Trim(),
            posting.Payload.InvoiceDate?.ToString("yyyy-MM-dd"),
            posting.Payload.DueDate?.ToString("yyyy-MM-dd"),
            new QuickBooksOnlineReference(
                posting.Payload.Currency.Trim().ToUpperInvariant()),
            lines,
            string.IsNullOrWhiteSpace(posting.Payload.Notes)
                ? null
                : posting.Payload.Notes.Trim());

        return new QuickBooksOnlineBillBuildResult(
            QuickBooksOnlineBillBuildOutcome.Completed,
            request);
    }

    private static string ResolveExpenseAccountId(
        QuickBooksOnlineTargetMappingOptions target,
        AccountingBillLine sourceLine)
    {
        if (!string.IsNullOrWhiteSpace(sourceLine.Sku))
        {
            var mapped = target.ExpenseAccounts.SingleOrDefault(item =>
                string.Equals(
                    item.Sku.Trim(),
                    sourceLine.Sku.Trim(),
                    StringComparison.OrdinalIgnoreCase));

            if (mapped is not null)
                return mapped.AccountId.Trim();
        }

        return target.DefaultExpenseAccountId.Trim();
    }

    private static decimal? ResolveLineAmount(AccountingBillLine line)
    {
        if (line.LineTotal is decimal lineTotal)
            return lineTotal;

        if (line.UnitPrice is not decimal unitPrice)
            return null;

        var amount = line.Quantity * unitPrice;
        if (line.DiscountRate is decimal discountRate)
            amount *= 1m - (discountRate / 100m);

        return decimal.Round(
            amount,
            2,
            MidpointRounding.AwayFromZero);
    }

    private static QuickBooksOnlineBillBuildResult Failure(
        QuickBooksOnlineBillBuildOutcome outcome,
        string error)
        => new(outcome, Error: error);
}
