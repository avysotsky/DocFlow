namespace DocFlow.Infrastructure.Accounting.QuickBooksOnline;

public sealed class QuickBooksOnlineHttpOptions
{
    public const string ConfigurationSection =
        "AccountingPosting:QuickBooksOnline:Http";

    public string BaseUrl { get; set; } =
        "https://sandbox-quickbooks.api.intuit.com";
    public int RequestTimeoutSeconds { get; set; } = 30;
    public bool DevelopmentAllowNonOfficialEndpoints { get; set; }
}
