namespace DocFlow.Domain.Entities;

public sealed class MailboxMessageRecord
{
    public const int MaxIdentityLength = 512;
    public const int MaxInternetMessageIdLength = 998;
    public const int MaxSenderLength = 512;
    public const int MaxSubjectLength = 998;
    public const int Sha256Length = 64;

    public Guid Id { get; private set; }
    public Guid CustomerId { get; private set; }
    public string MessageIdentity { get; private set; } = string.Empty;
    public string RawMessageSha256 { get; private set; } = string.Empty;
    public string? InternetMessageId { get; private set; }
    public string? Sender { get; private set; }
    public string? Subject { get; private set; }
    public DateTimeOffset? ReceivedAt { get; private set; }
    public DateTimeOffset CreatedAt { get; private set; }

    private MailboxMessageRecord()
    {
    }

    public MailboxMessageRecord(
        Guid customerId,
        string messageIdentity,
        string rawMessageSha256,
        string? internetMessageId,
        string? sender,
        string? subject,
        DateTimeOffset? receivedAt)
    {
        if (customerId == Guid.Empty)
            throw new ArgumentException("Customer id is required.", nameof(customerId));
        if (string.IsNullOrWhiteSpace(messageIdentity))
            throw new ArgumentException("Message identity is required.", nameof(messageIdentity));
        if (string.IsNullOrWhiteSpace(rawMessageSha256))
            throw new ArgumentException("Raw message SHA-256 is required.", nameof(rawMessageSha256));

        MessageIdentity = NormalizeRequired(messageIdentity, MaxIdentityLength, nameof(messageIdentity));
        RawMessageSha256 = NormalizeRequired(rawMessageSha256, Sha256Length, nameof(rawMessageSha256));
        if (RawMessageSha256.Length != Sha256Length)
            throw new ArgumentOutOfRangeException(nameof(rawMessageSha256));

        Id = Guid.NewGuid();
        CustomerId = customerId;
        InternetMessageId = NormalizeOptional(internetMessageId, MaxInternetMessageIdLength, nameof(internetMessageId));
        Sender = NormalizeOptional(sender, MaxSenderLength, nameof(sender));
        Subject = NormalizeOptional(subject, MaxSubjectLength, nameof(subject));
        ReceivedAt = receivedAt;
        CreatedAt = DateTimeOffset.UtcNow;
    }

    private static string NormalizeRequired(string value, int maxLength, string parameterName)
    {
        var normalized = value.Trim();
        if (normalized.Length > maxLength)
            throw new ArgumentOutOfRangeException(parameterName);
        return normalized;
    }

    private static string? NormalizeOptional(string? value, int maxLength, string parameterName)
    {
        if (string.IsNullOrWhiteSpace(value))
            return null;

        var normalized = value.Trim();
        if (normalized.Length > maxLength)
            throw new ArgumentOutOfRangeException(parameterName);
        return normalized;
    }
}
