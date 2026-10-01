namespace DocFlow.Api.Documents;

public sealed class DocumentIntakeIdempotencyOptions
{
    public const string ConfigurationSection = "Intake:Idempotency";

    public int RetentionHours { get; set; } = 24;
}
