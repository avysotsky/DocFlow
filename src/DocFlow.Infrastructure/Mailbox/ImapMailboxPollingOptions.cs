namespace DocFlow.Infrastructure.Mailbox;

public sealed class ImapMailboxPollingOptions
{
    public const string ConfigurationSection = "Mailbox:Imap";

    public bool Enabled { get; set; }
    public int PollIntervalSeconds { get; set; } = 30;
    public int BatchSize { get; set; } = 20;
    public List<ImapMailboxAccountOptions> Accounts { get; set; } = [];
}

public sealed class ImapMailboxAccountOptions
{
    public string Name { get; set; } = string.Empty;
    public Guid CustomerId { get; set; }
    public string Host { get; set; } = string.Empty;
    public int Port { get; set; } = 993;
    public bool UseSsl { get; set; } = true;
    public string Username { get; set; } = string.Empty;
    public string Password { get; set; } = string.Empty;
    public string Folder { get; set; } = "INBOX";
}

public sealed record ImapMailboxPollResult(
    string MailboxKey,
    string FolderName,
    uint UidValidity,
    uint LastUid,
    int Considered,
    int Completed);
