using System.Threading.Channels;
using DocFlow.Application.Abstractions;
using DocFlow.Application.Observability;

namespace DocFlow.Infrastructure.Processing;

public sealed class DocumentProcessingQueue : IDocumentProcessingQueue
{
    private readonly Channel<Guid> _channel = Channel.CreateUnbounded<Guid>(
        new UnboundedChannelOptions
        {
            SingleReader = true,
            SingleWriter = false,
            AllowSynchronousContinuations = false
        });

    private readonly OperationalMetrics _metrics;

    public DocumentProcessingQueue(OperationalMetrics metrics)
    {
        _metrics = metrics;
    }

    public async ValueTask EnqueueAsync(
        Guid documentId,
        CancellationToken cancellationToken = default)
    {
        if (documentId == Guid.Empty)
            throw new ArgumentException("Document id is required.", nameof(documentId));

        await _channel.Writer.WriteAsync(documentId, cancellationToken);
        _metrics.RecordQueueEnqueued();
    }

    public async ValueTask<Guid> DequeueAsync(
        CancellationToken cancellationToken = default)
    {
        var documentId = await _channel.Reader.ReadAsync(cancellationToken);
        _metrics.RecordQueueDequeued();
        return documentId;
    }
}
