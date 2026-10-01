using DocFlow.Application.Abstractions;
using DocFlow.Application.Observability;
using Microsoft.Extensions.Options;

namespace DocFlow.Api.BackgroundServices;

public sealed class DocumentProcessingBackgroundService : BackgroundService
{
    private readonly IDocumentProcessingQueue _queue;
    private readonly IServiceScopeFactory _scopeFactory;
    private readonly DocumentProcessingRetryOptions _retryOptions;
    private readonly OperationalMetrics _metrics;
    private readonly ILogger<DocumentProcessingBackgroundService> _logger;

    public DocumentProcessingBackgroundService(
        IDocumentProcessingQueue queue,
        IServiceScopeFactory scopeFactory,
        IOptions<DocumentProcessingRetryOptions> retryOptions,
        OperationalMetrics metrics,
        ILogger<DocumentProcessingBackgroundService> logger)
    {
        _queue = queue;
        _scopeFactory = scopeFactory;
        _retryOptions = retryOptions.Value;
        _metrics = metrics;
        _logger = logger;
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        while (!stoppingToken.IsCancellationRequested)
        {
            Guid documentId;

            try
            {
                documentId = await _queue.DequeueAsync(stoppingToken);
            }
            catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested)
            {
                break;
            }

            await ProcessWithRetriesAsync(documentId, stoppingToken);
        }
    }

    private async Task ProcessWithRetriesAsync(
        Guid documentId,
        CancellationToken stoppingToken)
    {
        for (var attempt = 1; attempt <= _retryOptions.MaxAttempts; attempt++)
        {
            using var scope = _scopeFactory.CreateScope();
            var processingService = scope.ServiceProvider
                .GetRequiredService<IDocumentProcessingService>();

            try
            {
                await processingService.ProcessAsync(documentId, stoppingToken);

                _logger.LogInformation(
                    "Document {DocumentId} processing completed on job attempt {Attempt} of {MaxAttempts}.",
                    documentId,
                    attempt,
                    _retryOptions.MaxAttempts);
                return;
            }
            catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested)
            {
                return;
            }
            catch (Exception exception) when (attempt < _retryOptions.MaxAttempts)
            {
                _metrics.RecordProcessingRetry();

                _logger.LogWarning(
                    exception,
                    "Document {DocumentId} processing attempt {Attempt} of {MaxAttempts} failed. Retrying.",
                    documentId,
                    attempt,
                    _retryOptions.MaxAttempts);

                if (_retryOptions.RetryDelayMilliseconds > 0)
                {
                    try
                    {
                        await Task.Delay(
                            _retryOptions.RetryDelayMilliseconds,
                            stoppingToken);
                    }
                    catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested)
                    {
                        return;
                    }
                }
            }
            catch (Exception exception)
            {
                try
                {
                    await processingService.MarkFailedAsync(
                        documentId,
                        CancellationToken.None);
                }
                catch (Exception markFailedException)
                {
                    _logger.LogError(
                        markFailedException,
                        "Document {DocumentId} exhausted {MaxAttempts} processing attempts, but persisting the final Failed status also failed.",
                        documentId,
                        _retryOptions.MaxAttempts);
                }

                _logger.LogError(
                    exception,
                    "Document {DocumentId} processing failed after {MaxAttempts} attempts.",
                    documentId,
                    _retryOptions.MaxAttempts);
                return;
            }
        }
    }
}
