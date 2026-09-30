using DocFlow.Domain.Enums;

namespace DocFlow.Application.Abstractions;

public interface IExtractionResultService
{
    Task<SaveExtractionResultResult> SaveAsync(
        Guid documentId,
        string structuredDataJson,
        string documentType,
        decimal? confidence,
        ValidationStatus validationStatus,
        CancellationToken cancellationToken = default);
}

public enum ExtractionResultSaveOutcome
{
    Saved = 1,
    DocumentNotFound = 2,
    AlreadyExists = 3
}

public sealed record SavedExtractionResult(
    Guid Id,
    Guid DocumentId,
    DocumentStatus DocumentStatus,
    string? DocumentType,
    ValidationStatus ValidationStatus,
    decimal? Confidence,
    DateTimeOffset CreatedAt);

public sealed record SaveExtractionResultResult(
    ExtractionResultSaveOutcome Outcome,
    SavedExtractionResult? SavedResult = null);
