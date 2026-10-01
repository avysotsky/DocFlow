using DocFlow.Application.Abstractions;
using DocFlow.Domain.Enums;
using DocFlow.Infrastructure.Persistence;
using Microsoft.EntityFrameworkCore;

namespace DocFlow.Infrastructure.Documents;

public sealed class DocumentDeletionService : IDocumentDeletionService
{
    private readonly DocFlowDbContext _dbContext;
    private readonly IFileStorage _fileStorage;

    public DocumentDeletionService(
        DocFlowDbContext dbContext,
        IFileStorage fileStorage)
    {
        _dbContext = dbContext;
        _fileStorage = fileStorage;
    }

    public async Task<DocumentDeletionOutcome> DeleteAsync(
        Guid documentId,
        Guid customerId,
        CancellationToken cancellationToken = default)
    {
        await using var transaction = await _dbContext.Database
            .BeginTransactionAsync(cancellationToken);

        var document = await _dbContext.Documents
            .FromSqlInterpolated($"""
                SELECT *
                FROM "Documents"
                WHERE "Id" = {documentId}
                  AND "CustomerId" = {customerId}
                FOR UPDATE
                """)
            .SingleOrDefaultAsync(cancellationToken);

        if (document is null)
        {
            await transaction.RollbackAsync(CancellationToken.None);
            return DocumentDeletionOutcome.NotFound;
        }

        if (document.Status is DocumentStatus.Uploaded or DocumentStatus.Processing)
        {
            await transaction.RollbackAsync(CancellationToken.None);
            return DocumentDeletionOutcome.ActiveProcessingConflict;
        }

        var storageKey = document.StorageKey;

        try
        {
            _dbContext.Documents.Remove(document);
            await _dbContext.SaveChangesAsync(CancellationToken.None);

            await _fileStorage.DeleteAsync(
                storageKey,
                CancellationToken.None);

            await transaction.CommitAsync(CancellationToken.None);
            return DocumentDeletionOutcome.Deleted;
        }
        catch
        {
            try
            {
                await transaction.RollbackAsync(CancellationToken.None);
            }
            catch
            {
                // Preserve the original deletion exception.
            }

            throw;
        }
    }
}
