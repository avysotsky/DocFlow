using System.Security.Cryptography;
using DocFlow.Application.Abstractions;
using MimeKit;

namespace DocFlow.Infrastructure.Mailbox;

public sealed class MimeMailboxMessageParser : IMailboxMessageParser
{
    public const long MaxRawMessageSize = 30L * 1024 * 1024;
    public const long MaxPdfAttachmentSize = 20L * 1024 * 1024;

    public async Task<ParsedMailboxMessage> ParseAsync(
        Stream rawMessage,
        CancellationToken cancellationToken = default)
    {
        if (rawMessage is null)
            throw new ArgumentNullException(nameof(rawMessage));

        await using var copy = new MemoryStream();
        var buffer = new byte[81920];
        long total = 0;

        while (true)
        {
            var read = await rawMessage.ReadAsync(buffer.AsMemory(), cancellationToken);
            if (read == 0)
                break;

            total += read;
            if (total > MaxRawMessageSize)
                throw new InvalidDataException("The RFC822 message must not exceed 30 MB.");

            await copy.WriteAsync(buffer.AsMemory(0, read), cancellationToken);
        }

        if (copy.Length == 0)
            throw new InvalidDataException("A non-empty RFC822 message is required.");

        var rawBytes = copy.ToArray();
        var rawSha256 = Convert.ToHexString(SHA256.HashData(rawBytes)).ToLowerInvariant();

        copy.Position = 0;
        MimeMessage message;
        try
        {
            message = await MimeMessage.LoadAsync(copy, cancellationToken);
        }
        catch (FormatException exception)
        {
            throw new InvalidDataException("The payload is not a valid RFC822/MIME message.", exception);
        }

        using (message)
        {
            var internetMessageId = NormalizeInternetMessageId(message.MessageId);
            var messageIdentity = internetMessageId is null
                ? $"sha256:{rawSha256}"
                : $"message-id:{internetMessageId.ToLowerInvariant()}";

            var attachments = new List<ParsedMailboxPdfAttachment>();
            var ordinal = 0;

            foreach (var entity in message.Attachments)
            {
                cancellationToken.ThrowIfCancellationRequested();

                if (entity is not MimePart part || part.Content is null)
                    continue;

                var rawFileName = part.FileName
                    ?? part.ContentDisposition?.FileName
                    ?? part.ContentType.Name;
                var fileName = string.IsNullOrWhiteSpace(rawFileName)
                    ? $"attachment-{ordinal + 1}.pdf"
                    : Path.GetFileName(rawFileName.Trim());

                var isPdfCandidate =
                    string.Equals(
                        part.ContentType.MimeType,
                        "application/pdf",
                        StringComparison.OrdinalIgnoreCase)
                    || string.Equals(
                        Path.GetExtension(fileName),
                        ".pdf",
                        StringComparison.OrdinalIgnoreCase);

                if (!isPdfCandidate)
                    continue;

                await using var decoded = new MemoryStream();
                await part.Content.DecodeToAsync(decoded, cancellationToken);

                if (decoded.Length == 0)
                    throw new InvalidDataException($"PDF attachment '{fileName}' is empty.");
                if (decoded.Length > MaxPdfAttachmentSize)
                    throw new InvalidDataException(
                        $"PDF attachment '{fileName}' must not exceed 20 MB.");

                var content = decoded.ToArray();
                if (!HasPdfSignature(content))
                {
                    throw new InvalidDataException(
                        $"Attachment '{fileName}' does not have a valid PDF signature.");
                }

                attachments.Add(
                    new ParsedMailboxPdfAttachment(
                        ordinal,
                        fileName,
                        "application/pdf",
                        content.LongLength,
                        Convert.ToHexString(SHA256.HashData(content)).ToLowerInvariant(),
                        content));
                ordinal++;
            }

            var sender = message.From.Mailboxes.FirstOrDefault()?.Address;

            return new ParsedMailboxMessage(
                messageIdentity,
                rawSha256,
                internetMessageId,
                string.IsNullOrWhiteSpace(sender) ? null : sender.Trim(),
                string.IsNullOrWhiteSpace(message.Subject) ? null : message.Subject.Trim(),
                message.Date == DateTimeOffset.MinValue ? null : message.Date,
                attachments);
        }
    }

    private static string? NormalizeInternetMessageId(string? value)
    {
        if (string.IsNullOrWhiteSpace(value))
            return null;

        var normalized = value.Trim().Trim('<', '>').Trim();
        return normalized.Length == 0 ? null : normalized;
    }

    private static bool HasPdfSignature(ReadOnlySpan<byte> bytes)
        => bytes.Length >= 5
            && bytes[0] == (byte)'%'
            && bytes[1] == (byte)'P'
            && bytes[2] == (byte)'D'
            && bytes[3] == (byte)'F'
            && bytes[4] == (byte)'-';
}
