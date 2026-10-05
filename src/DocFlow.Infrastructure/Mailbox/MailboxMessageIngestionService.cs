using DocFlow.Application.Abstractions;
using DocFlow.Domain.Entities;
using DocFlow.Infrastructure.Persistence;
using Microsoft.EntityFrameworkCore;

namespace DocFlow.Infrastructure.Mailbox;

public sealed class MailboxMessageIngestionService : IMailboxMessageIngestionService
{
    private readonly DocFlowDbContext _dbContext;
    private readonly IMailboxMessageParser _parser;

    public MailboxMessageIngestionService(
        DocFlowDbContext dbContext,
        IMailboxMessageParser parser)
    {
        _dbContext = dbContext;
        _parser = parser;
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

        await using var transaction = await _dbContext.Database
            .BeginTransactionAsync(cancellationToken);

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
            var existingAttachments = await _dbContext.MailboxAttachments
                .AsNoTracking()
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
                    existingAttachments,
                    "The same mailbox message identity was received with a different MIME payload.");
            }

            return BuildResult(
                MailboxMessageIngestionOutcome.Replay,
                existing,
                existingAttachments,
                null);
        }

        var message = new MailboxMessageRecord(
            customerId,
            parsed.MessageIdentity,
            parsed.RawMessageSha256,
            parsed.InternetMessageId,
            parsed.Sender,
            parsed.Subject,
            parsed.ReceivedAt);

        var attachments = parsed.PdfAttachments
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

        return BuildResult(
            MailboxMessageIngestionOutcome.Accepted,
            message,
            attachments,
            null);
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
                    item.Sha256))
                .ToArray(),
            error);
}
