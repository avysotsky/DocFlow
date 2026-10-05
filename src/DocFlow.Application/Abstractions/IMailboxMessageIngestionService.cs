namespace DocFlow.Application.Abstractions;

public sealed record ParsedMailboxPdfAttachment(
    int Ordinal,
    string FileName,
    string ContentType,
    long Size,
    string Sha256,
    byte[] Content);

public sealed record ParsedMailboxMessage(
    string MessageIdentity,
    string RawMessageSha256,
    string? InternetMessageId,
    string? Sender,
    string? Subject,
    DateTimeOffset? ReceivedAt,
    IReadOnlyList<ParsedMailboxPdfAttachment> PdfAttachments);

public interface IMailboxMessageParser
{
    Task<ParsedMailboxMessage> ParseAsync(
        Stream rawMessage,
        CancellationToken cancellationToken = default);
}

public enum MailboxMessageIngestionOutcome
{
    Accepted,
    Replay,
    Conflict,
    Rejected
}

public sealed record MailboxAttachmentIngestionItem(
    Guid Id,
    int Ordinal,
    string FileName,
    string ContentType,
    long Size,
    string Sha256);

public sealed record MailboxMessageIngestionResult(
    MailboxMessageIngestionOutcome Outcome,
    Guid? MailboxMessageId,
    string MessageIdentity,
    string? InternetMessageId,
    string? Sender,
    string? Subject,
    DateTimeOffset? ReceivedAt,
    IReadOnlyList<MailboxAttachmentIngestionItem> PdfAttachments,
    string? Error = null);

public interface IMailboxMessageIngestionService
{
    Task<MailboxMessageIngestionResult> IngestAsync(
        Guid customerId,
        Stream rawMessage,
        CancellationToken cancellationToken = default);
}
