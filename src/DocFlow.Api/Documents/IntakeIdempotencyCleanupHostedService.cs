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
            "Intake idempotency cleanup enabled: {CleanupIntervalSeconds} second interval, batch size {CleanupBatchSize} per record type.",
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
        List<CleanupCandidate> singleCandidates;
        List<CleanupCandidate> batchCandidates;

        await using (var queryScope = _scopeFactory.CreateAsyncScope())
        {
            var dbContext = queryScope.ServiceProvider.GetRequiredService<DocFlowDbContext>();

            singleCandidates = await dbContext.IntakeIdempotencyRecords
                .AsNoTracking()
                .Where(record => record.ExpiresAt <= cutoff)
                .OrderBy(record => record.ExpiresAt)
                .ThenBy(record => record.CustomerId)
                .ThenBy(record => record.Key)
                .Take(_options.CleanupBatchSize)
                .Select(record => new CleanupCandidate(record.CustomerId, record.Key))
                .ToListAsync(cancellationToken);

            batchCandidates = await dbContext.BatchIntakeIdempotencyRecords
                .AsNoTracking()
                .Where(record => record.ExpiresAt <= cutoff)
                .OrderBy(record => record.ExpiresAt)
                .ThenBy(record => record.CustomerId)
                .ThenBy(record => record.Key)
                .Take(_options.CleanupBatchSize)
                .Select(record => new CleanupCandidate(record.CustomerId, record.Key))
                .ToListAsync(cancellationToken);
        }

        if (singleCandidates.Count == 0 && batchCandidates.Count == 0)
            return;

        var singleDeleted = 0;
        var singleSkipped = 0;
        var singleFailed = 0;
        foreach (var candidate in singleCandidates)
        {
            cancellationToken.ThrowIfCancellationRequested();
            var outcome = await DeleteSingleCandidateAsync(candidate, cutoff, cancellationToken);
            CountOutcome(outcome, ref singleDeleted, ref singleSkipped, ref singleFailed);
        }

        var batchDeleted = 0;
        var batchSkipped = 0;
        var batchFailed = 0;
        foreach (var candidate in batchCandidates)
        {
            cancellationToken.ThrowIfCancellationRequested();
            var outcome = await DeleteBatchCandidateAsync(candidate, cutoff, cancellationToken);
            CountOutcome(outcome, ref batchDeleted, ref batchSkipped, ref batchFailed);
        }

        _logger.LogInformation(
            "Intake idempotency cleanup considered {SingleCandidateCount} single records and {BatchCandidateCount} batch manifests: single {SingleDeleted} deleted/{SingleSkipped} skipped/{SingleFailed} failed; batch {BatchDeleted} deleted/{BatchSkipped} skipped/{BatchFailed} failed.",
            singleCandidates.Count,
            batchCandidates.Count,
            singleDeleted,
            singleSkipped,
            singleFailed,
            batchDeleted,
            batchSkipped,
            batchFailed);
    }

    private async Task<CleanupOutcome> DeleteSingleCandidateAsync(
        CleanupCandidate candidate,
        DateTimeOffset cutoff,
        CancellationToken cancellationToken)
    {
        try
        {
            await using var deleteScope = _scopeFactory.CreateAsyncScope();
            var dbContext = deleteScope.ServiceProvider.GetRequiredService<DocFlowDbContext>();
            await using var transaction = await dbContext.Database.BeginTransactionAsync(cancellationToken);

            var lockScope = IntakeIdempotencyKey.CreateSingleLockScope(
                candidate.CustomerId,
                candidate.Key);
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
            return affected == 1 ? CleanupOutcome.Deleted : CleanupOutcome.Skipped;
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            throw;
        }
        catch (Exception exception)
        {
            _logger.LogError(
                exception,
                "Failed to delete an expired single intake idempotency record.");
            return CleanupOutcome.Failed;
        }
    }

    private async Task<CleanupOutcome> DeleteBatchCandidateAsync(
        CleanupCandidate candidate,
        DateTimeOffset cutoff,
        CancellationToken cancellationToken)
    {
        try
        {
            await using var deleteScope = _scopeFactory.CreateAsyncScope();
            var dbContext = deleteScope.ServiceProvider.GetRequiredService<DocFlowDbContext>();
            await using var transaction = await dbContext.Database.BeginTransactionAsync(cancellationToken);

            var lockScope = IntakeIdempotencyKey.CreateBatchLockScope(
                candidate.CustomerId,
                candidate.Key);
            await dbContext.Database.ExecuteSqlInterpolatedAsync(
                $"SELECT pg_advisory_xact_lock(hashtextextended({lockScope}, 0));",
                cancellationToken);

            var affected = await dbContext.BatchIntakeIdempotencyRecords
                .Where(record =>
                    record.CustomerId == candidate.CustomerId
                    && record.Key == candidate.Key
                    && record.ExpiresAt <= cutoff)
                .ExecuteDeleteAsync(cancellationToken);

            await transaction.CommitAsync(cancellationToken);
            return affected == 1 ? CleanupOutcome.Deleted : CleanupOutcome.Skipped;
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            throw;
        }
        catch (Exception exception)
        {
            _logger.LogError(
                exception,
                "Failed to delete an expired batch intake idempotency manifest.");
            return CleanupOutcome.Failed;
        }
    }

    private static void CountOutcome(
        CleanupOutcome outcome,
        ref int deleted,
        ref int skipped,
        ref int failed)
    {
        switch (outcome)
        {
            case CleanupOutcome.Deleted:
                deleted++;
                break;
            case CleanupOutcome.Skipped:
                skipped++;
                break;
            case CleanupOutcome.Failed:
                failed++;
                break;
            default:
                throw new InvalidOperationException($"Unsupported cleanup outcome '{outcome}'.");
        }
    }

    private enum CleanupOutcome
    {
        Deleted = 1,
        Skipped = 2,
        Failed = 3
    }

    private sealed record CleanupCandidate(Guid CustomerId, string Key);
}
