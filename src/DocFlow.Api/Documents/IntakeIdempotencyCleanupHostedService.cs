using DocFlow.Infrastructure.Persistence;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Options;

namespace DocFlow.Api.Documents;

public sealed class IntakeIdempotencyCleanupHostedService : BackgroundService
{
    private readonly IServiceScopeFactory _scopeFactory;
    private readonly DocumentIntakeIdempotencyOptions _options;
    private readonly ILogger<IntakeIdempotencyCleanupHostedService> _logger;

    public IntakeIdempotencyCleanupHostedService(
        IServiceScopeFactory scopeFactory,
        IOptions<DocumentIntakeIdempotencyOptions> options,
        ILogger<IntakeIdempotencyCleanupHostedService> logger)
    {
        _scopeFactory = scopeFactory;
        _options = options.Value;
        _logger = logger;
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        _logger.LogInformation(
            "Intake idempotency cleanup enabled: {CleanupIntervalSeconds} second interval, batch size {CleanupBatchSize}.",
            _options.CleanupIntervalSeconds,
            _options.CleanupBatchSize);

        while (!stoppingToken.IsCancellationRequested)
        {
            try
            {
                await SweepOnceAsync(stoppingToken);
            }
            catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested)
            {
                break;
            }
            catch (Exception exception)
            {
                _logger.LogError(exception, "Intake idempotency cleanup sweep failed.");
            }

            try
            {
                await Task.Delay(
                    TimeSpan.FromSeconds(_options.CleanupIntervalSeconds),
                    stoppingToken);
            }
            catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested)
            {
                break;
            }
        }
    }

    private async Task SweepOnceAsync(CancellationToken cancellationToken)
    {
        var cutoff = DateTimeOffset.UtcNow;
        List<CleanupCandidate> candidates;

        await using (var queryScope = _scopeFactory.CreateAsyncScope())
        {
            var dbContext = queryScope.ServiceProvider.GetRequiredService<DocFlowDbContext>();

            candidates = await dbContext.IntakeIdempotencyRecords
                .AsNoTracking()
                .Where(record => record.ExpiresAt <= cutoff)
                .OrderBy(record => record.ExpiresAt)
                .ThenBy(record => record.CustomerId)
                .ThenBy(record => record.Key)
                .Take(_options.CleanupBatchSize)
                .Select(record => new CleanupCandidate(record.CustomerId, record.Key))
                .ToListAsync(cancellationToken);
        }

        if (candidates.Count == 0)
            return;

        var deleted = 0;
        var skipped = 0;
        var failed = 0;

        foreach (var candidate in candidates)
        {
            cancellationToken.ThrowIfCancellationRequested();

            try
            {
                await using var deleteScope = _scopeFactory.CreateAsyncScope();
                var dbContext = deleteScope.ServiceProvider.GetRequiredService<DocFlowDbContext>();
                await using var transaction = await dbContext.Database.BeginTransactionAsync(cancellationToken);

                // Must match DocumentIntakeService lock scope exactly so cleanup cannot delete
                // a key while intake is replaying or replacing that same tenant/key record.
                var lockScope = $"{candidate.CustomerId:N}:{candidate.Key}";
                await dbContext.Database.ExecuteSqlInterpolatedAsync(
                    $"SELECT pg_advisory_xact_lock(hashtextextended({lockScope}, 0));",
                    cancellationToken);

                var affected = await dbContext.IntakeIdempotencyRecords
                    .Where(record =>
                        record.CustomerId == candidate.CustomerId
                        && record.Key == candidate.Key
                        && record.ExpiresAt <= cutoff)
                    .ExecuteDeleteAsync(cancellationToken);

                await transaction.CommitAsync(cancellationToken);

                if (affected == 1)
                    deleted++;
                else
                    skipped++;
            }
            catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
            {
                throw;
            }
            catch (Exception exception)
            {
                failed++;
                _logger.LogError(
                    exception,
                    "Failed to delete an expired intake idempotency record.");
            }
        }

        _logger.LogInformation(
            "Intake idempotency cleanup considered {CandidateCount} expired records: {DeletedCount} deleted, {SkippedCount} skipped after re-check, {FailedCount} failed.",
            candidates.Count,
            deleted,
            skipped,
            failed);
    }

    private sealed record CleanupCandidate(Guid CustomerId, string Key);
}
