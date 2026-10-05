using DocFlow.Application.Abstractions;
using DocFlow.Domain.Entities;
using DocFlow.Infrastructure.Persistence;
using Microsoft.EntityFrameworkCore;

namespace DocFlow.Infrastructure.Mailbox;

public sealed class MailboxMessageIngestionService : IMailboxMessageIngestionService
{
    private readonly DocFlowDbContext _dbContext;
    private readonly IMailboxMessageParser _parser;
    private readonly IInternalDocumentIntakeService _documentIntakeService;

    public MailboxMessageIngestionService(
        DocFlowDbContext dbContext,
        IMailboxMessageParser parser,
        IInternalDocumentIntakeService documentIntakeService)
    {
        _dbContext = dbContext;
        _parser = parser;
        _documentIntakeService = documentIntakeService;
    }

    public async Task<MailboxMessageIngestionResult> IngestAsync(
        Guid customerId,
        Stream rawMessage,
        CancellationToken cancellationToken = default)
    {
        if (customerId == Guid.Empty)
            throw new ArgumentException("Customer id is required.", nameof(customerId));

        ParsedMailboxMessage parsed;
        try
        {
            parsed = await _parser.ParseAsync(rawMessage, cancellationToken);
        }
        catch (InvalidDataException exception)
        {
            return new MailboxMessageIngestionResult(
                MailboxMessageIngestionOutcome.Rejected,
                null,
                string.Empty,
                null,
                null,
                null,
                null,
                [],
                exception.Message);
        }

        MailboxMessageRecord message;
        MailboxAttachmentRecord[] attachments;
        var replay = false;

        await using (var transaction = await _dbContext.Database
                         .BeginTransactionAsync(cancellationToken))
        {
            var lockScope = $"mailbox-message:{customerId:D}:{parsed.MessageIdentity}";
            await _dbContext.Database.ExecuteSqlInterpolatedAsync(
                $"SELECT pg_advisory_xact_lock(hashtextextended({lockScope}, 0));",
                cancellationToken);

            var existing = await _dbContext.MailboxMessages
                .SingleOrDefaultAsync(
                    item => item.CustomerId == customerId
                        && item.MessageIdentity == parsed.MessageIdentity,
                    cancellationToken);

            if (existing is not null)
            {
                attachments = await _dbContext.MailboxAttachments
                    .Where(item => item.MailboxMessageId == existing.Id)
                    .OrderBy(item => item.Ordinal)
                    .ToArrayAsync(cancellationToken);

                await transaction.CommitAsync(cancellationToken);

                if (!string.Equals(
                        existing.RawMessageSha256,
                        parsed.RawMessageSha256,
                        StringComparison.Ordinal))
                {
                    return BuildResult(
                        MailboxMessageIngestionOutcome.Conflict,
                        existing,
                        attachments,
                        "The same mailbox message identity was received with a different MIME payload.");
                }

                message = existing;
                replay = true;
            }
            else
            {
                message = new MailboxMessageRecord(
                    customerId,
                    parsed.MessageIdentity,
                    parsed.RawMessageSha256,
                    parsed.InternetMessageId,
                    parsed.Sender,
                    parsed.Subject,
                    parsed.ReceivedAt);

                attachments = parsed.PdfAttachments
                    .Select(item => new MailboxAttachmentRecord(
                        message.Id,
                        item.Ordinal,
                        item.FileName,
                        item.ContentType,
                        item.Size,
                        item.Sha256))
                    .ToArray();

                _dbContext.MailboxMessages.Add(message);
                _dbContext.MailboxAttachments.AddRange(attachments);
                await _dbContext.SaveChangesAsync(cancellationToken);
                await transaction.CommitAsync(cancellationToken);
            }
        }

        await EnsureDocumentLinksAsync(
            customerId,
            parsed.PdfAttachments,
            attachments,
            cancellationToken);

        return BuildResult(
            replay
                ? MailboxMessageIngestionOutcome.Replay
                : MailboxMessageIngestionOutcome.Accepted,
            message,
            attachments,
            null);
    }

    private async Task EnsureDocumentLinksAsync(
        Guid customerId,
        IReadOnlyList<ParsedMailboxPdfAttachment> parsedAttachments,
        IReadOnlyList<MailboxAttachmentRecord> persistedAttachments,
        CancellationToken cancellationToken)
    {
        if (parsedAttachments.Count != persistedAttachments.Count)
        {
            throw new InvalidOperationException(
                "Persisted mailbox attachments no longer match the parsed MIME message.");
        }

        var parsedByOrdinal = parsedAttachments.ToDictionary(item => item.Ordinal);

        foreach (var attachment in persistedAttachments)
        {
            if (attachment.DocumentId.HasValue)
                continue;

            if (!parsedByOrdinal.TryGetValue(attachment.Ordinal, out var parsed)
                || !string.Equals(
                    parsed.Sha256,
                    attachment.Sha256,
                    StringComparison.Ordinal))
            {
                throw new InvalidOperationException(
                    $"Mailbox attachment '{attachment.Id}' does not match the parsed MIME payload.");
            }

            var intake = await _documentIntakeService.IntakePdfAsync(
                customerId,
                attachment.Id,
                attachment.FileName,
                attachment.ContentType,
                parsed.Content,
                cancellationToken);

            if (intake.Outcome != InternalDocumentIntakeOutcome.Accepted
                || !intake.DocumentId.HasValue)
            {
                throw new InvalidOperationException(
                    $"Mailbox attachment '{attachment.Id}' could not enter document intake: "
                    + (intake.Error ?? intake.Outcome.ToString()));
            }

            attachment.AttachDocument(intake.DocumentId.Value);

            // Persist each link independently. If the process stops after document intake
            // commits but before this write, replay uses the same source idempotency key and
            // recovers the existing DocumentId instead of creating a duplicate Document.
            await _dbContext.SaveChangesAsync(CancellationToken.None);
        }
    }

    private static MailboxMessageIngestionResult BuildResult(
        MailboxMessageIngestionOutcome outcome,
        MailboxMessageRecord message,
        IReadOnlyList<MailboxAttachmentRecord> attachments,
        string? error)
        => new(
            outcome,
            message.Id,
            message.MessageIdentity,
            message.InternetMessageId,
            message.Sender,
            message.Subject,
            message.ReceivedAt,
            attachments
                .Select(item => new MailboxAttachmentIngestionItem(
                    item.Id,
                    item.Ordinal,
                    item.FileName,
                    item.ContentType,
                    item.Size,
                    item.Sha256,
                    item.DocumentId))
                .ToArray(),
            error);
}
