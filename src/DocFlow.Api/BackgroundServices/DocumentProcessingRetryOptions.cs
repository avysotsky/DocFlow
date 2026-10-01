namespace DocFlow.Api.BackgroundServices;

public sealed class DocumentProcessingRetryOptions
{
    public const string ConfigurationSection = "Processing:Retry";

    public int MaxAttempts { get; set; } = 3;
    public int RetryDelayMilliseconds { get; set; } = 250;
}
