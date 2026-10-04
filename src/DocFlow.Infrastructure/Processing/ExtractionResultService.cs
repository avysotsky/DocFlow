using System.Text.Json;
using System.Text.Json.Nodes;
using DocFlow.Application.Abstractions;
using DocFlow.Application.Observability;
using DocFlow.Domain.Entities;
using DocFlow.Domain.Enums;
using DocFlow.Infrastructure.Persistence;
using Microsoft.EntityFrameworkCore;

namespace DocFlow.Infrastructure.Processing;

public sealed class ExtractionResultService : IExtractionResultService
{
    private readonly DocFlowDbContext _dbContext;
    private readonly OperationalMetrics _metrics;

    public ExtractionResultService(
        DocFlowDbContext dbContext,
        OperationalMetrics metrics)
    {
        _dbContext = dbContext;
        _metrics = metrics;
    }

    public async Task<SaveExtractionResultResult> SaveAsync(
        Guid documentId,
        string structuredDataJson,
        string documentType,
        decimal? confidence,
        ValidationStatus validationStatus,
        CancellationToken cancellationToken = default)
    {
        var document = await _dbContext.Documents
            .SingleOrDefaultAsync(x => x.Id == documentId, cancellationToken);

        if (document is null)
        {
            return new SaveExtractionResultResult(
                ExtractionResultSaveOutcome.DocumentNotFound);
        }

        var alreadyExists = await _dbContext.ExtractionResults
            .AnyAsync(x => x.DocumentId == documentId, cancellationToken);

        if (alreadyExists)
        {
            return new SaveExtractionResultResult(
                ExtractionResultSaveOutcome.AlreadyExists);
        }

        Guid? suspectedDuplicateOfDocumentId = null;
        if (string.Equals(documentType, "supplier_invoice", StringComparison.OrdinalIgnoreCase)
            && TryGetInvoiceBusinessKey(structuredDataJson, out var currentBusinessKey))
        {
            var previousInvoices = await (
                    from previousResult in _dbContext.ExtractionResults.AsNoTracking()
                    join previousDocument in _dbContext.Documents.AsNoTracking()
                        on previousResult.DocumentId equals previousDocument.Id
                    where previousDocument.CustomerId == document.CustomerId
                        && previousDocument.Id != documentId
                        && previousDocument.DocumentType == "supplier_invoice"
                    orderby previousResult.CreatedAt, previousResult.Id
                    select new
                    {
                        previousResult.DocumentId,
                        previousResult.StructuredDataJson
                    })
                .ToListAsync(cancellationToken);

            foreach (var previous in previousInvoices)
            {
                if (!TryGetInvoiceBusinessKey(
                        previous.StructuredDataJson,
                        out var previousBusinessKey))
                {
                    continue;
                }

                if (currentBusinessKey == previousBusinessKey)
                {
                    suspectedDuplicateOfDocumentId = previous.DocumentId;
                    break;
                }
            }

            structuredDataJson = AddDuplicateCheck(
                structuredDataJson,
                suspectedDuplicateOfDocumentId is null ? "clear" : "suspected",
                suspectedDuplicateOfDocumentId);
        }
        else if (string.Equals(
                     documentType,
                     "supplier_invoice",
                     StringComparison.OrdinalIgnoreCase))
        {
            structuredDataJson = AddDuplicateCheck(
                structuredDataJson,
                "not_checked",
                duplicateOfDocumentId: null);
        }

        var extractionResult = new ExtractionResult(
            documentId,
            structuredDataJson,
            confidence,
            validationStatus);

        _dbContext.ExtractionResults.Add(extractionResult);

        if (validationStatus == ValidationStatus.Valid
            && suspectedDuplicateOfDocumentId is null)
        {
            document.MarkProcessed(documentType);
        }
        else
        {
            document.MarkNeedsReview(documentType);
        }

        _dbContext.DocumentCompletionEvents.Add(new DocumentCompletionEvent(
            document.Id,
            document.CustomerId,
            document.Status,
            document.DocumentType,
            document.ProcessingAttempts,
            document.ProcessedAt ?? DateTimeOffset.UtcNow));

        await _dbContext.SaveChangesAsync(cancellationToken);

        if (document.Status == DocumentStatus.Processed)
            _metrics.RecordProcessingCompleted();
        else
            _metrics.RecordProcessingNeedsReview();

        var savedResult = new SavedExtractionResult(
            extractionResult.Id,
            extractionResult.DocumentId,
            document.Status,
            document.DocumentType,
            extractionResult.ValidationStatus,
            extractionResult.Confidence,
            extractionResult.CreatedAt);

        return new SaveExtractionResultResult(
            ExtractionResultSaveOutcome.Saved,
            savedResult);
    }


    private static bool TryGetInvoiceBusinessKey(
        string structuredDataJson,
        out InvoiceBusinessKey businessKey)
    {
        businessKey = default;

        try
        {
            using var json = JsonDocument.Parse(structuredDataJson);
            var root = json.RootElement;

            if (!root.TryGetProperty("data", out var data)
                || data.ValueKind != JsonValueKind.Object)
            {
                return false;
            }

            var supplier = ReadBusinessKeyValue(data, "supplier_name");
            var invoiceNumber = ReadBusinessKeyValue(data, "invoice_number");
            if (string.IsNullOrWhiteSpace(supplier)
                || string.IsNullOrWhiteSpace(invoiceNumber))
            {
                return false;
            }

            var normalizedSupplier = NormalizeBusinessKeyComponent(supplier);
            var normalizedInvoiceNumber = NormalizeBusinessKeyComponent(invoiceNumber);
            if (normalizedSupplier.Length == 0 || normalizedInvoiceNumber.Length == 0)
                return false;

            businessKey = new InvoiceBusinessKey(
                normalizedSupplier,
                normalizedInvoiceNumber);
            return true;
        }
        catch (JsonException)
        {
            return false;
        }
    }

    private static string AddDuplicateCheck(
        string structuredDataJson,
        string status,
        Guid? duplicateOfDocumentId)
    {
        var root = JsonNode.Parse(structuredDataJson) as JsonObject
            ?? throw new InvalidOperationException(
                "Structured extraction data must be a JSON object.");

        var businessChecks = root["business_checks"] as JsonObject;
        if (businessChecks is null)
        {
            businessChecks = new JsonObject();
            root["business_checks"] = businessChecks;
        }

        businessChecks["duplicate_check"] = new JsonObject
        {
            ["status"] = status,
            ["basis"] = "supplier_name+invoice_number",
            ["duplicate_of_document_id"] = duplicateOfDocumentId?.ToString()
        };

        return root.ToJsonString();
    }

    private static string? ReadBusinessKeyValue(
        JsonElement data,
        string propertyName)
    {
        if (!data.TryGetProperty(propertyName, out var value)
            || value.ValueKind != JsonValueKind.String)
        {
            return null;
        }

        return value.GetString()?.Trim();
    }

    private static string NormalizeBusinessKeyComponent(string value)
    {
        return new string(
            value
                .Where(char.IsLetterOrDigit)
                .Select(char.ToUpperInvariant)
                .ToArray());
    }

    private readonly record struct InvoiceBusinessKey(
        string Supplier,
        string InvoiceNumber);
}
