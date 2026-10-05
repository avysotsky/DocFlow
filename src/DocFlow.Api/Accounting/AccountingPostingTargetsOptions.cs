namespace DocFlow.Api.Accounting;

public sealed class AccountingPostingTargetsOptions
{
    public const string ConfigurationSection = "AccountingPosting";

    public List<AccountingPostingTargetOptions> Targets { get; set; } = [];
}

public sealed class AccountingPostingTargetOptions
{
    public Guid CustomerId { get; set; }
    public string Key { get; set; } = string.Empty;
    public string Provider { get; set; } = string.Empty;
    public string TargetAccount { get; set; } = string.Empty;
}
