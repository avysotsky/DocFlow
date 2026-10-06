namespace DocFlow.Infrastructure.Accounting.QuickBooksOnline;

public sealed class QuickBooksOnlineOAuthOptions
{
    public const string ConfigurationSection =
        "AccountingPosting:QuickBooksOnline:OAuth";

    public bool Enabled { get; set; }
    public string ClientId { get; set; } = string.Empty;
    public string ClientSecret { get; set; } = string.Empty;
    public string RedirectUri { get; set; } = string.Empty;
    public string AuthorizationUrl { get; set; } =
        "https://appcenter.intuit.com/connect/oauth2";
    public string TokenUrl { get; set; } =
        "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer";
    public string Scope { get; set; } =
        "com.intuit.quickbooks.accounting";
    public int StateLifetimeMinutes { get; set; } = 10;
    public int AccessTokenRefreshSkewSeconds { get; set; } = 120;
    public string DataProtectionKeyRingPath { get; set; } = string.Empty;
    public bool DevelopmentAllowNonOfficialEndpoints { get; set; }
}
