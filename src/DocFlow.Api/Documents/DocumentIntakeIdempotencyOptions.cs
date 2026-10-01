namespace DocFlow.Api.Documents;

public sealed class DocumentIntakeIdempotencyOptions
{
    public const string ConfigurationSection = "Intake:Idempotency";

    public int RetentionHours { get; set; } = 24;
    public int CleanupIntervalSeconds { get; set; } = 3600;
    public int CleanupBatchSize { get; set; } = 500;
}
