namespace DocFlow.Application.Abstractions;

public interface IDocumentDeletionService
{
    Task<DocumentDeletionOutcome> DeleteAsync(
        Guid documentId,
        Guid customerId,
        CancellationToken cancellationToken = default);
}

public enum DocumentDeletionOutcome
{
    Deleted = 0,
    NotFound = 1,
    ActiveProcessingConflict = 2
}
