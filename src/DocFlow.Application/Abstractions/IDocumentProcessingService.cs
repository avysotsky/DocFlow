namespace DocFlow.Application.Abstractions;

public interface IDocumentProcessingService
{
    Task ProcessAsync(
        Guid documentId,
        CancellationToken cancellationToken = default);

    Task MarkFailedAsync(
        Guid documentId,
        CancellationToken cancellationToken = default);
}
