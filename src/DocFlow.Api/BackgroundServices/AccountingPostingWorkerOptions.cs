namespace DocFlow.Api.BackgroundServices;

public sealed class AccountingPostingWorkerOptions
{
    public const string ConfigurationSection = "AccountingPosting:Worker";

    public int PollIntervalSeconds { get; set; } = 5;
    public int BatchSize { get; set; } = 20;
}
