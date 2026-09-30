using System.Threading.Channels;
using DocFlow.Application.Abstractions;

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

    public ValueTask EnqueueAsync(
        Guid documentId,
        CancellationToken cancellationToken = default)
    {
        if (documentId == Guid.Empty)
            throw new ArgumentException("Document id is required.", nameof(documentId));

        return _channel.Writer.WriteAsync(documentId, cancellationToken);
    }

    public ValueTask<Guid> DequeueAsync(
        CancellationToken cancellationToken = default)
    {
        return _channel.Reader.ReadAsync(cancellationToken);
    }
}
