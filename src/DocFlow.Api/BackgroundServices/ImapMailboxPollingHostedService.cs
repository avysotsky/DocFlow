using DocFlow.Infrastructure.Mailbox;
using Microsoft.Extensions.Options;

namespace DocFlow.Api.BackgroundServices;

public sealed class ImapMailboxPollingHostedService : BackgroundService
{
    private readonly IServiceScopeFactory _scopeFactory;
    private readonly IOptions<ImapMailboxPollingOptions> _options;
    private readonly ILogger<ImapMailboxPollingHostedService> _logger;

    public ImapMailboxPollingHostedService(
        IServiceScopeFactory scopeFactory,
        IOptions<ImapMailboxPollingOptions> options,
        ILogger<ImapMailboxPollingHostedService> logger)
    {
        _scopeFactory = scopeFactory;
        _options = options;
        _logger = logger;
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        var options = _options.Value;
        if (!options.Enabled)
        {
            _logger.LogInformation("IMAP mailbox polling is disabled.");
            return;
        }

        while (!stoppingToken.IsCancellationRequested)
        {
            foreach (var account in options.Accounts)
            {
                try
                {
                    await using var scope = _scopeFactory.CreateAsyncScope();
                    var poller = scope.ServiceProvider
                        .GetRequiredService<ImapMailboxPoller>();

                    var result = await poller.PollAsync(
                        account,
                        options.BatchSize,
                        stoppingToken);

                    if (result.Completed > 0)
                    {
                        _logger.LogInformation(
                            "IMAP mailbox {MailboxKey}/{FolderName} completed {CompletedCount} message(s); UIDVALIDITY={UidValidity}, LastUid={LastUid}.",
                            result.MailboxKey,
                            result.FolderName,
                            result.Completed,
                            result.UidValidity,
                            result.LastUid);
                    }
                }
                catch (OperationCanceledException)
                    when (stoppingToken.IsCancellationRequested)
                {
                    return;
                }
                catch (Exception exception)
                {
                    _logger.LogError(
                        exception,
                        "IMAP mailbox poll failed for {MailboxKey}/{FolderName}; the persisted checkpoint was not advanced past the failed UID.",
                        account.Name,
                        account.Folder);
                }
            }

            try
            {
                await Task.Delay(
                    TimeSpan.FromSeconds(options.PollIntervalSeconds),
                    stoppingToken);
            }
            catch (OperationCanceledException)
                when (stoppingToken.IsCancellationRequested)
            {
                return;
            }
        }
    }
}
