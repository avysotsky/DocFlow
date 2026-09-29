namespace DocFlow.Application.Abstractions;

public interface IFileStorage
{
    Task<string> UploadAsync(
        Stream content,
        string fileName,
        string contentType,
        CancellationToken cancellationToken = default);

    Task<Stream> OpenReadAsync(
        string storageKey,
        CancellationToken cancellationToken = default);

    Task DeleteAsync(
        string storageKey,
        CancellationToken cancellationToken = default);
}
