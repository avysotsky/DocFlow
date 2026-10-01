namespace DocFlow.Api.Retention;

public sealed class DocumentRetentionOptions
{
    public const string ConfigurationSection = "Retention";

    public bool Enabled { get; set; }
    public int DefaultRetentionDays { get; set; } = 30;
    public int SweepIntervalSeconds { get; set; } = 3600;
    public int BatchSize { get; set; } = 100;
}
