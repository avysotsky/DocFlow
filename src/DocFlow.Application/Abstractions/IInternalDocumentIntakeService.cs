namespace DocFlow.Application.Abstractions;

public enum InternalDocumentIntakeOutcome
{
    Accepted,
    Rejected,
    Failed
}

public sealed record InternalDocumentIntakeResult(
    InternalDocumentIntakeOutcome Outcome,
    Guid? DocumentId,
    string? DocumentStatus,
    bool IsReplay,
    string? Error = null);

public interface IInternalDocumentIntakeService
{
    Task<InternalDocumentIntakeResult> IntakePdfAsync(
        Guid customerId,
        Guid sourceId,
        string fileName,
        string contentType,
        byte[] content,
        CancellationToken cancellationToken = default);
}
