namespace DocFlow.Api.Notifications;

public sealed class WebhookDeliveryOptions
{
    public const string ConfigurationSection = "Notifications:Webhooks";

    public int PollIntervalSeconds { get; set; } = 5;
    public int RequestTimeoutSeconds { get; set; } = 10;
    public int MaxAttempts { get; set; } = 5;
    public int BaseRetryDelaySeconds { get; set; } = 30;
    public int MaxRetryDelaySeconds { get; set; } = 3600;
    public int BatchSize { get; set; } = 50;
    public bool DevelopmentAllowInsecureHttp { get; set; }
    public bool DevelopmentAllowPrivateNetworks { get; set; }
    public List<WebhookTenantOptions> Tenants { get; set; } = [];
}

public sealed class WebhookTenantOptions
{
    public Guid CustomerId { get; set; }
    public string Url { get; set; } = string.Empty;
    public string Secret { get; set; } = string.Empty;
}
