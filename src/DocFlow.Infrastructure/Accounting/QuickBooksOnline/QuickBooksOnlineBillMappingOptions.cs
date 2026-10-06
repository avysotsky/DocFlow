namespace DocFlow.Infrastructure.Accounting.QuickBooksOnline;

public sealed class QuickBooksOnlineBillMappingOptions
{
    public const string ConfigurationSection = "AccountingPosting:QuickBooksOnline";

    public List<QuickBooksOnlineTargetMappingOptions> Targets { get; set; } = [];
}

public sealed class QuickBooksOnlineTargetMappingOptions
{
    public Guid CustomerId { get; set; }
    public string TargetKey { get; set; } = string.Empty;
    public string ApAccountId { get; set; } = string.Empty;
    public string DefaultExpenseAccountId { get; set; } = string.Empty;
    public List<QuickBooksOnlineVendorMappingOptions> Vendors { get; set; } = [];
    public List<QuickBooksOnlineExpenseAccountMappingOptions> ExpenseAccounts { get; set; } = [];
    public List<QuickBooksOnlineTaxCodeMappingOptions> TaxCodes { get; set; } = [];
}

public sealed class QuickBooksOnlineVendorMappingOptions
{
    public string SupplierName { get; set; } = string.Empty;
    public string VendorId { get; set; } = string.Empty;
}

public sealed class QuickBooksOnlineExpenseAccountMappingOptions
{
    public string Sku { get; set; } = string.Empty;
    public string AccountId { get; set; } = string.Empty;
}

public sealed class QuickBooksOnlineTaxCodeMappingOptions
{
    public decimal Rate { get; set; }
    public string TaxCodeId { get; set; } = string.Empty;
}
