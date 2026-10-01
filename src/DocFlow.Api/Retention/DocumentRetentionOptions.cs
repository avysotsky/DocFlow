namespace DocFlow.Api.Retention;

public sealed class DocumentRetentionOptions
{
    public const string ConfigurationSection = "Retention";

    public bool Enabled { get; set; }
    public int DefaultRetentionDays { get; set; } = 30;
    public int SweepIntervalSeconds { get; set; } = 3600;
    public int BatchSize { get; set; } = 100;
    public List<DocumentRetentionTenantOverrideOptions> TenantOverrides { get; set; } = [];

    public bool IsSweepEnabled =>
        Enabled || TenantOverrides.Any(tenant => tenant.Enabled == true);

    public DocumentRetentionPolicy Resolve(Guid customerId)
    {
        if (customerId == Guid.Empty)
            throw new ArgumentException("Customer id is required.", nameof(customerId));

        var tenantOverride = TenantOverrides.SingleOrDefault(
            tenant => tenant.CustomerId == customerId);

        return new DocumentRetentionPolicy(
            tenantOverride?.Enabled ?? Enabled,
            tenantOverride?.RetentionDays ?? DefaultRetentionDays);
    }
}

public sealed class DocumentRetentionTenantOverrideOptions
{
    public Guid CustomerId { get; set; }
    public bool? Enabled { get; set; }
    public int? RetentionDays { get; set; }
}

public sealed record DocumentRetentionPolicy(bool Enabled, int RetentionDays);
