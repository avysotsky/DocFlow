using DocFlow.Application.Abstractions;
using DocFlow.Domain.Enums;
using DocFlow.Infrastructure.Persistence;
using DocFlow.Infrastructure.Processing;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Options;

namespace DocFlow.Api.BackgroundServices;

public sealed class AccountingPostingHostedService : BackgroundService
{
    private readonly IServiceScopeFactory _scopeFactory;
    private readonly AccountingPostingWorkerOptions _options;
    private readonly ILogger<AccountingPostingHostedService> _logger;

    public AccountingPostingHostedService(
        IServiceScopeFactory scopeFactory,
        IOptions<AccountingPostingWorkerOptions> options,
        ILogger<AccountingPostingHostedService> logger)
    {
        _scopeFactory = scopeFactory;
        _options = options.Value;
        _logger = logger;
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        while (!stoppingToken.IsCancellationRequested)
        {
            var processed = 0;

            try
            {
                processed = await ProcessDueBatchAsync(stoppingToken);
            }
            catch (OperationCanceledException)
                when (stoppingToken.IsCancellationRequested)
            {
                break;
            }
            catch (Exception exception)
            {
                _logger.LogError(
                    exception,
                    "Accounting posting delivery sweep failed.");
            }

            if (processed >= _options.BatchSize)
                continue;

            try
            {
                await Task.Delay(
                    TimeSpan.FromSeconds(_options.PollIntervalSeconds),
                    stoppingToken);
            }
            catch (OperationCanceledException)
                when (stoppingToken.IsCancellationRequested)
            {
                break;
            }
        }
    }

    private async Task<int> ProcessDueBatchAsync(
        CancellationToken stoppingToken)
    {
        await using var scope = _scopeFactory.CreateAsyncScope();
        var dbContext = scope.ServiceProvider
            .GetRequiredService<DocFlowDbContext>();
        var adapters = scope.ServiceProvider
            .GetServices<IAccountingPostingAdapter>()
            .ToDictionary(
                adapter => adapter.Provider,
                StringComparer.OrdinalIgnoreCase);

        var now = DateTimeOffset.UtcNow;
        var staleBefore = now.AddSeconds(-_options.InProgressTimeoutSeconds);

        var interruptedPostings = await dbContext.AccountingPostingRecords
            .Where(item =>
                item.Status == AccountingPostingStatus.Posting
                && item.LastAttemptAt != null
                && item.LastAttemptAt <= staleBefore)
            .OrderBy(item => item.LastAttemptAt)
            .Take(_options.BatchSize)
            .ToListAsync(stoppingToken);

        foreach (var interrupted in interruptedPostings)
        {
            interrupted.RecoverInterruptedAttempt(now);
            _logger.LogWarning(
                "Recovered interrupted accounting posting {PostingId}; attempts={Attempts}.",
                interrupted.Id,
                interrupted.Attempts);
        }

        if (interruptedPostings.Count > 0)
            await dbContext.SaveChangesAsync(stoppingToken);

        var postings = await dbContext.AccountingPostingRecords
            .Where(item =>
                item.Status == AccountingPostingStatus.Pending
                && item.NextAttemptAt != null
                && item.NextAttemptAt <= now)
            .OrderBy(item => item.NextAttemptAt)
            .ThenBy(item => item.CreatedAt)
            .Take(_options.BatchSize)
            .ToListAsync(stoppingToken);

        foreach (var posting in postings)
        {
            if (!adapters.TryGetValue(posting.Provider, out var adapter))
            {
                posting.MarkAttemptStarted(DateTimeOffset.UtcNow);
                AccountingPostingExecutionPolicy.ApplyResult(
                    posting,
                    new AccountingPostingAdapterResult(
                        AccountingPostingAdapterOutcome.PermanentFailure,
                        ErrorSummary:
                            $"Accounting provider '{posting.Provider}' is not configured."),
                    DateTimeOffset.UtcNow);

                await dbContext.SaveChangesAsync(stoppingToken);
                continue;
            }

            posting.MarkAttemptStarted(DateTimeOffset.UtcNow);
            await dbContext.SaveChangesAsync(stoppingToken);

            AccountingPostingAdapterResult result;
            try
            {
                result = await adapter.PostAsync(
                    AccountingPostingExecutionPolicy.CreateRequest(posting),
                    stoppingToken);
            }
            catch (OperationCanceledException)
                when (stoppingToken.IsCancellationRequested)
            {
                AccountingPostingExecutionPolicy.ApplyResult(
                    posting,
                    new AccountingPostingAdapterResult(
                        AccountingPostingAdapterOutcome.RetryableFailure,
                        ErrorSummary:
                            "Accounting posting attempt was interrupted by application shutdown."),
                    DateTimeOffset.UtcNow);

                await dbContext.SaveChangesAsync(CancellationToken.None);
                throw;
            }
            catch (Exception exception)
            {
                result = new AccountingPostingAdapterResult(
                    AccountingPostingAdapterOutcome.RetryableFailure,
                    ErrorSummary: exception.Message);
            }

            AccountingPostingExecutionPolicy.ApplyResult(
                posting,
                result,
                DateTimeOffset.UtcNow);
            await dbContext.SaveChangesAsync(CancellationToken.None);

            _logger.LogInformation(
                "Accounting posting {PostingId} provider={Provider} status={Status} attempts={Attempts}.",
                posting.Id,
                posting.Provider,
                posting.Status,
                posting.Attempts);
        }

        return postings.Count;
    }
}
