namespace DocFlow.Application.Abstractions;

public interface IDocumentProcessingService
{
    Task ProcessAsync(
        Guid documentId,
        CancellationToken cancellationToken = default);
}
