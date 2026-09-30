using DocFlow.Domain.Enums;

namespace DocFlow.Application.Abstractions;

public interface IDocumentExtractionRunner
{
    Task<DocumentExtractionResult> RunAsync(
        string storageKey,
        CancellationToken cancellationToken = default);
}

public sealed record DocumentExtractionResult(
    string StructuredDataJson,
    string DocumentType,
    decimal? Confidence,
    ValidationStatus ValidationStatus);
