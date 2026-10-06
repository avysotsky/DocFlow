namespace DocFlow.Infrastructure.Accounting.QuickBooksOnline;

public sealed record QuickBooksOnlineMappingValidationResult(
    bool IsValid,
    IReadOnlyList<QuickBooksOnlineMappingValidationIssue> Issues);

public sealed record QuickBooksOnlineMappingValidationIssue(
    string Code,
    string Message);

public sealed class QuickBooksOnlineMappingValidationService
{
    private readonly QuickBooksOnlineBillMappingOptions _mappingOptions;
    private readonly QuickBooksOnlineReferenceDiscoveryService _referenceDiscovery;

    public QuickBooksOnlineMappingValidationService(
        QuickBooksOnlineBillMappingOptions mappingOptions,
        QuickBooksOnlineReferenceDiscoveryService referenceDiscovery)
    {
        _mappingOptions = mappingOptions;
        _referenceDiscovery = referenceDiscovery;
    }

    public async Task<QuickBooksOnlineMappingValidationResult> ValidateAsync(
        Guid customerId,
        string targetKey,
        CancellationToken cancellationToken = default)
    {
        var normalizedTargetKey = targetKey.Trim();

        var mapping = _mappingOptions.Targets.SingleOrDefault(item =>
            item.CustomerId == customerId
            && string.Equals(
                item.TargetKey.Trim(),
                normalizedTargetKey,
                StringComparison.OrdinalIgnoreCase));

        if (mapping is null)
        {
            return Invalid(
                "mapping_not_configured",
                "QuickBooks Online posting mappings are not configured for this target.");
        }

        var references = await _referenceDiscovery.DiscoverAsync(
            customerId,
            normalizedTargetKey,
            cancellationToken);

        if (references is null)
        {
            return Invalid(
                "connection_not_available",
                "QuickBooks Online connection is not available for this target.");
        }

        var issues = new List<QuickBooksOnlineMappingValidationIssue>();

        var apAccount = references.Accounts.SingleOrDefault(item =>
            string.Equals(item.Id, mapping.ApAccountId.Trim(), StringComparison.Ordinal));

        if (apAccount is null)
        {
            issues.Add(new(
                "ap_account_not_found",
                $"Configured AP account '{mapping.ApAccountId}' was not returned by QuickBooks Online."));
        }
        else
        {
            if (!apAccount.Active)
            {
                issues.Add(new(
                    "ap_account_inactive",
                    $"Configured AP account '{apAccount.Id}' is inactive."));
            }

            if (!IsAccountsPayable(apAccount))
            {
                issues.Add(new(
                    "ap_account_wrong_type",
                    $"Configured AP account '{apAccount.Id}' is not an Accounts Payable account."));
            }
        }

        ValidateExpenseAccount(
            references,
            mapping.DefaultExpenseAccountId,
            "default_expense_account",
            issues);

        foreach (var expenseMapping in mapping.ExpenseAccounts)
        {
            ValidateExpenseAccount(
                references,
                expenseMapping.AccountId,
                $"sku:{expenseMapping.Sku}",
                issues);
        }

        foreach (var vendorMapping in mapping.Vendors)
        {
            var vendor = references.Vendors.SingleOrDefault(item =>
                string.Equals(
                    item.Id,
                    vendorMapping.VendorId.Trim(),
                    StringComparison.Ordinal));

            if (vendor is null)
            {
                issues.Add(new(
                    "vendor_not_found",
                    $"Vendor id '{vendorMapping.VendorId}' for supplier '{vendorMapping.SupplierName}' was not returned by QuickBooks Online."));
            }
            else if (!vendor.Active)
            {
                issues.Add(new(
                    "vendor_inactive",
                    $"Vendor id '{vendor.Id}' for supplier '{vendorMapping.SupplierName}' is inactive."));
            }
        }

        foreach (var taxMapping in mapping.TaxCodes)
        {
            var taxCode = references.TaxCodes.SingleOrDefault(item =>
                string.Equals(
                    item.Id,
                    taxMapping.TaxCodeId.Trim(),
                    StringComparison.Ordinal));

            if (taxCode is null)
            {
                issues.Add(new(
                    "tax_code_not_found",
                    $"Tax code id '{taxMapping.TaxCodeId}' for rate '{taxMapping.Rate}' was not returned by QuickBooks Online."));
            }
            else if (!taxCode.Active)
            {
                issues.Add(new(
                    "tax_code_inactive",
                    $"Tax code id '{taxCode.Id}' for rate '{taxMapping.Rate}' is inactive."));
            }
        }

        return new QuickBooksOnlineMappingValidationResult(
            issues.Count == 0,
            issues);
    }

    private static void ValidateExpenseAccount(
        QuickBooksOnlineReferenceCatalog references,
        string accountId,
        string mappingName,
        List<QuickBooksOnlineMappingValidationIssue> issues)
    {
        var account = references.Accounts.SingleOrDefault(item =>
            string.Equals(
                item.Id,
                accountId.Trim(),
                StringComparison.Ordinal));

        if (account is null)
        {
            issues.Add(new(
                "expense_account_not_found",
                $"Expense account '{accountId}' for '{mappingName}' was not returned by QuickBooks Online."));
            return;
        }

        if (!account.Active)
        {
            issues.Add(new(
                "expense_account_inactive",
                $"Expense account '{account.Id}' for '{mappingName}' is inactive."));
        }

        if (!IsExpenseLike(account))
        {
            issues.Add(new(
                "expense_account_wrong_type",
                $"Account '{account.Id}' for '{mappingName}' is not an expense/cost-of-goods account."));
        }
    }

    private static bool IsAccountsPayable(
        QuickBooksOnlineAccountReference account)
        => string.Equals(
                account.AccountType,
                "Accounts Payable",
                StringComparison.OrdinalIgnoreCase)
            || string.Equals(
                account.AccountSubType,
                "AccountsPayable",
                StringComparison.OrdinalIgnoreCase);

    private static bool IsExpenseLike(
        QuickBooksOnlineAccountReference account)
        => account.AccountType is not null
            && (account.AccountType.Equals(
                    "Expense",
                    StringComparison.OrdinalIgnoreCase)
                || account.AccountType.Equals(
                    "Other Expense",
                    StringComparison.OrdinalIgnoreCase)
                || account.AccountType.Equals(
                    "Cost of Goods Sold",
                    StringComparison.OrdinalIgnoreCase));

    private static QuickBooksOnlineMappingValidationResult Invalid(
        string code,
        string message)
        => new(
            false,
            [new QuickBooksOnlineMappingValidationIssue(code, message)]);
}
