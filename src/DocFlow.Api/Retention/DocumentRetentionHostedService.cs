using DocFlow.Application.Abstractions;
using DocFlow.Application.Observability;
using DocFlow.Domain.Enums;
using DocFlow.Infrastructure.Persistence;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Options;

namespace DocFlow.Api.Retention;

public sealed class DocumentRetentionHostedService : BackgroundService
{
    private readonly IServiceScopeFactory _scopeFactory;
    private readonly DocumentRetentionOptions _options;
    private readonly OperationalMetrics _metrics;
    private readonly ILogger<DocumentRetentionHostedService> _logger;

    public DocumentRetentionHostedService(
        IServiceScopeFactory scopeFactory,
        IOptions<DocumentRetentionOptions> options,
        OperationalMetrics metrics,
        ILogger<DocumentRetentionHostedService> logger)
    {
        _scopeFactory = scopeFactory;
        _options = options.Value;
        _metrics = metrics;
        _logger = logger;
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        if (!_options.IsSweepEnabled)
        {
            _logger.LogInformation("Document retention sweep is disabled for the deployment and all tenant overrides.");
            return;
        }

        _logger.LogInformation(
            "Document retention sweep enabled: global enabled {GlobalEnabled}, {DefaultRetentionDays} day default retention, {TenantOverrideCount} tenant overrides, {SweepIntervalSeconds} second interval, batch size {BatchSize}.",
            _options.Enabled,
            _options.DefaultRetentionDays,
            _options.TenantOverrides.Count,
            _options.SweepIntervalSeconds,
            _options.BatchSize);

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
                _metrics.RecordRetentionFailure();
                _logger.LogError(exception, "Document retention sweep failed.");
            }

            try
            {
                await Task.Delay(
                    TimeSpan.FromSeconds(_options.SweepIntervalSeconds),
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
        List<RetentionCandidate> candidates;
        var now = DateTimeOffset.UtcNow;

        await using (var queryScope = _scopeFactory.CreateAsyncScope())
        {
            var dbContext = queryScope.ServiceProvider.GetRequiredService<DocFlowDbContext>();

            candidates = await dbContext.Documents
                .AsNoTracking()
                .Where(document =>
                    document.DeleteAt != null
                    && document.DeleteAt <= now
                    && (document.Status == DocumentStatus.Processed
                        || document.Status == DocumentStatus.NeedsReview
                        || document.Status == DocumentStatus.Failed))
                .OrderBy(document => document.DeleteAt)
                .ThenBy(document => document.CreatedAt)
                .ThenBy(document => document.Id)
                .Take(_options.BatchSize)
                .Select(document => new RetentionCandidate(
                    document.Id,
                    document.CustomerId))
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
                var deletionService = deleteScope.ServiceProvider
                    .GetRequiredService<IDocumentDeletionService>();

                var outcome = await deletionService.DeleteAsync(
                    candidate.DocumentId,
                    candidate.CustomerId,
                    cancellationToken);

                switch (outcome)
                {
                    case DocumentDeletionOutcome.Deleted:
                        deleted++;
                        _metrics.RecordRetentionDeleted();
                        break;
                    case DocumentDeletionOutcome.NotFound:
                    case DocumentDeletionOutcome.ActiveProcessingConflict:
                        skipped++;
                        break;
                    default:
                        throw new InvalidOperationException(
                            $"Unsupported document deletion outcome '{outcome}'.");
                }
            }
            catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
            {
                throw;
            }
            catch (Exception exception)
            {
                failed++;
                _metrics.RecordRetentionFailure();
                _logger.LogError(
                    exception,
                    "Retention deletion failed for document {DocumentId}.",
                    candidate.DocumentId);
            }
        }

        _logger.LogInformation(
            "Document retention sweep considered {CandidateCount} expired terminal documents: {DeletedCount} deleted, {SkippedCount} skipped, {FailedCount} failed.",
            candidates.Count,
            deleted,
            skipped,
            failed);
    }

    private sealed record RetentionCandidate(Guid DocumentId, Guid CustomerId);
}
