using DocFlow.Application.Abstractions;
using DocFlow.Domain.Enums;
using DocFlow.Infrastructure.Persistence;
using Microsoft.EntityFrameworkCore;

namespace DocFlow.Api.BackgroundServices;

public sealed class DocumentProcessingRecoveryHostedService : IHostedService
{
    private readonly IDocumentProcessingQueue _queue;
    private readonly IServiceScopeFactory _scopeFactory;
    private readonly ILogger<DocumentProcessingRecoveryHostedService> _logger;

    public DocumentProcessingRecoveryHostedService(
        IDocumentProcessingQueue queue,
        IServiceScopeFactory scopeFactory,
        ILogger<DocumentProcessingRecoveryHostedService> logger)
    {
        _queue = queue;
        _scopeFactory = scopeFactory;
        _logger = logger;
    }

    public async Task StartAsync(CancellationToken cancellationToken)
    {
        await using var scope = _scopeFactory.CreateAsyncScope();
        var dbContext = scope.ServiceProvider.GetRequiredService<DocFlowDbContext>();

        var candidates = await dbContext.Documents
            .AsNoTracking()
            .Where(document =>
                (document.Status == DocumentStatus.Uploaded
                    || document.Status == DocumentStatus.Processing)
                && !dbContext.ExtractionResults.Any(
                    extractionResult => extractionResult.DocumentId == document.Id))
            .OrderBy(document => document.CreatedAt)
            .ThenBy(document => document.Id)
            .Select(document => new
            {
                document.Id,
                document.Status
            })
            .ToListAsync(cancellationToken);

        foreach (var candidate in candidates)
            await _queue.EnqueueAsync(candidate.Id, cancellationToken);

        var uploadedCount = candidates.Count(x => x.Status == DocumentStatus.Uploaded);
        var processingCount = candidates.Count(x => x.Status == DocumentStatus.Processing);

        _logger.LogInformation(
            "Startup processing recovery enqueued {TotalCount} persisted documents: {UploadedCount} Uploaded and {ProcessingCount} orphaned Processing.",
            candidates.Count,
            uploadedCount,
            processingCount);
    }

    public Task StopAsync(CancellationToken cancellationToken) => Task.CompletedTask;
}
