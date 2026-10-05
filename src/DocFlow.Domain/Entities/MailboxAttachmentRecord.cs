namespace DocFlow.Domain.Entities;

public sealed class MailboxAttachmentRecord
{
    public const int MaxFileNameLength = 512;
    public const int MaxContentTypeLength = 100;
    public const int Sha256Length = 64;

    public Guid Id { get; private set; }
    public Guid MailboxMessageId { get; private set; }
    public int Ordinal { get; private set; }
    public string FileName { get; private set; } = string.Empty;
    public string ContentType { get; private set; } = string.Empty;
    public long Size { get; private set; }
    public string Sha256 { get; private set; } = string.Empty;
    public DateTimeOffset CreatedAt { get; private set; }

    private MailboxAttachmentRecord()
    {
    }

    public MailboxAttachmentRecord(
        Guid mailboxMessageId,
        int ordinal,
        string fileName,
        string contentType,
        long size,
        string sha256)
    {
        if (mailboxMessageId == Guid.Empty)
            throw new ArgumentException("Mailbox message id is required.", nameof(mailboxMessageId));
        if (ordinal < 0)
            throw new ArgumentOutOfRangeException(nameof(ordinal));
        if (string.IsNullOrWhiteSpace(fileName))
            throw new ArgumentException("Attachment file name is required.", nameof(fileName));
        if (string.IsNullOrWhiteSpace(contentType))
            throw new ArgumentException("Attachment content type is required.", nameof(contentType));
        if (size <= 0)
            throw new ArgumentOutOfRangeException(nameof(size));
        if (string.IsNullOrWhiteSpace(sha256))
            throw new ArgumentException("Attachment SHA-256 is required.", nameof(sha256));

        var normalizedFileName = fileName.Trim();
        var normalizedContentType = contentType.Trim();
        var normalizedSha256 = sha256.Trim();

        if (normalizedFileName.Length > MaxFileNameLength)
            throw new ArgumentOutOfRangeException(nameof(fileName));
        if (normalizedContentType.Length > MaxContentTypeLength)
            throw new ArgumentOutOfRangeException(nameof(contentType));
        if (normalizedSha256.Length != Sha256Length)
            throw new ArgumentOutOfRangeException(nameof(sha256));

        Id = Guid.NewGuid();
        MailboxMessageId = mailboxMessageId;
        Ordinal = ordinal;
        FileName = normalizedFileName;
        ContentType = normalizedContentType;
        Size = size;
        Sha256 = normalizedSha256;
        CreatedAt = DateTimeOffset.UtcNow;
    }
}
