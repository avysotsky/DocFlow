namespace DocFlow.Api.Observability;

public sealed class OperationalMetricsOptions
{
    public const string ConfigurationSection = "Operations:Metrics";
    public const string HeaderName = "X-DocFlow-Metrics-Key";

    public bool Enabled { get; set; }
    public string ApiKey { get; set; } = string.Empty;
}
