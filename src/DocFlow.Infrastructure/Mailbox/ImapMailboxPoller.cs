using DocFlow.Application.Abstractions;
using DocFlow.Domain.Entities;
using DocFlow.Infrastructure.Persistence;
using MailKit;
using MailKit.Net.Imap;
using MailKit.Search;
using MailKit.Security;
using Microsoft.EntityFrameworkCore;

namespace DocFlow.Infrastructure.Mailbox;

public sealed class ImapMailboxPoller
{
    private readonly DocFlowDbContext _dbContext;
    private readonly IMailboxMessageIngestionService _ingestionService;

    public ImapMailboxPoller(
        DocFlowDbContext dbContext,
        IMailboxMessageIngestionService ingestionService)
    {
        _dbContext = dbContext;
        _ingestionService = ingestionService;
    }

    public async Task<ImapMailboxPollResult> PollAsync(
        ImapMailboxAccountOptions account,
        int batchSize,
        CancellationToken cancellationToken = default)
    {
        if (batchSize is < 1 or > 500)
            throw new ArgumentOutOfRangeException(nameof(batchSize));

        using var client = new ImapClient();
        var socketOptions = account.UseSsl
            ? SecureSocketOptions.SslOnConnect
            : SecureSocketOptions.None;

        await client.ConnectAsync(
            account.Host,
            account.Port,
            socketOptions,
            cancellationToken);

        await client.AuthenticateAsync(
            account.Username,
            account.Password,
            cancellationToken);

        var folder = string.Equals(
                account.Folder,
                "INBOX",
                StringComparison.OrdinalIgnoreCase)
            ? client.Inbox
            : await client.GetFolderAsync(account.Folder, cancellationToken);

        await folder.OpenAsync(FolderAccess.ReadOnly, cancellationToken);

        var uidValidity = folder.UidValidity;
        var checkpoint = await _dbContext.ImapMailboxCheckpoints
            .SingleOrDefaultAsync(
                item => item.CustomerId == account.CustomerId
                    && item.MailboxKey == account.Name
                    && item.FolderName == account.Folder,
                cancellationToken);

        if (checkpoint is null)
        {
            checkpoint = new ImapMailboxCheckpoint(
                account.CustomerId,
                account.Name,
                account.Folder,
                uidValidity);
            _dbContext.ImapMailboxCheckpoints.Add(checkpoint);
            await _dbContext.SaveChangesAsync(cancellationToken);
        }
        else if (checkpoint.UidValidity != uidValidity)
        {
            checkpoint.Reset(uidValidity);
            await _dbContext.SaveChangesAsync(cancellationToken);
        }

        var allUids = await folder.SearchAsync(
            SearchQuery.All,
            cancellationToken);

        var pending = allUids
            .Where(uid => uid.IsValid && uid.Id > checkpoint.LastUid)
            .OrderBy(uid => uid.Id)
            .Take(batchSize)
            .ToArray();

        var completed = 0;

        foreach (var uid in pending)
        {
            await using var raw = await folder.GetStreamAsync(
                uid,
                cancellationToken);

            var result = await _ingestionService.IngestAsync(
                account.CustomerId,
                raw,
                cancellationToken);

            if (result.Outcome is not (
                    MailboxMessageIngestionOutcome.Accepted
                    or MailboxMessageIngestionOutcome.Replay
                    or MailboxMessageIngestionOutcome.Conflict
                    or MailboxMessageIngestionOutcome.Rejected))
            {
                throw new InvalidOperationException(
                    $"Mailbox ingestion returned non-terminal outcome '{result.Outcome}'.");
            }

            checkpoint.Advance(uidValidity, uid.Id);
            await _dbContext.SaveChangesAsync(CancellationToken.None);
            completed++;
        }

        await client.DisconnectAsync(true, cancellationToken);

        return new ImapMailboxPollResult(
            account.Name,
            account.Folder,
            uidValidity,
            checked((uint)checkpoint.LastUid),
            pending.Length,
            completed);
    }
}
