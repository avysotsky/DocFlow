namespace DocFlow.Domain.Entities;

public sealed class ImapMailboxCheckpoint
{
    public const int MaxMailboxKeyLength = 100;
    public const int MaxFolderNameLength = 255;

    public Guid Id { get; private set; }
    public Guid CustomerId { get; private set; }
    public string MailboxKey { get; private set; } = string.Empty;
    public string FolderName { get; private set; } = string.Empty;
    public long UidValidity { get; private set; }
    public long LastUid { get; private set; }
    public DateTimeOffset UpdatedAt { get; private set; }

    private ImapMailboxCheckpoint()
    {
    }

    public ImapMailboxCheckpoint(
        Guid customerId,
        string mailboxKey,
        string folderName,
        uint uidValidity)
    {
        if (customerId == Guid.Empty)
            throw new ArgumentException("Customer id is required.", nameof(customerId));

        Id = Guid.NewGuid();
        CustomerId = customerId;
        MailboxKey = Normalize(mailboxKey, MaxMailboxKeyLength, nameof(mailboxKey));
        FolderName = Normalize(folderName, MaxFolderNameLength, nameof(folderName));
        UidValidity = uidValidity;
        LastUid = 0;
        UpdatedAt = DateTimeOffset.UtcNow;
    }

    public void Reset(uint uidValidity)
    {
        UidValidity = uidValidity;
        LastUid = 0;
        UpdatedAt = DateTimeOffset.UtcNow;
    }

    public void Advance(uint uidValidity, uint uid)
    {
        if (UidValidity != uidValidity)
            throw new InvalidOperationException("UIDVALIDITY changed before checkpoint advance.");
        if (uid < LastUid)
            throw new InvalidOperationException("IMAP checkpoint cannot move backwards.");

        LastUid = uid;
        UpdatedAt = DateTimeOffset.UtcNow;
    }

    private static string Normalize(string value, int maxLength, string parameterName)
    {
        if (string.IsNullOrWhiteSpace(value))
            throw new ArgumentException("A non-empty value is required.", parameterName);

        var normalized = value.Trim();
        if (normalized.Length > maxLength)
            throw new ArgumentOutOfRangeException(parameterName);

        return normalized;
    }
}
