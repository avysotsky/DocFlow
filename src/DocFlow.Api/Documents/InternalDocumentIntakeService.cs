using DocFlow.Application.Abstractions;
using Microsoft.AspNetCore.Http;

namespace DocFlow.Api.Documents;

public sealed class InternalDocumentIntakeService : IInternalDocumentIntakeService
{
    private readonly DocumentIntakeService _documentIntakeService;

    public InternalDocumentIntakeService(DocumentIntakeService documentIntakeService)
    {
        _documentIntakeService = documentIntakeService;
    }

    public async Task<InternalDocumentIntakeResult> IntakePdfAsync(
        Guid customerId,
        Guid sourceId,
        string fileName,
        string contentType,
        byte[] content,
        CancellationToken cancellationToken = default)
    {
        if (sourceId == Guid.Empty)
            throw new ArgumentException("Source id is required.", nameof(sourceId));
        if (content is null)
            throw new ArgumentNullException(nameof(content));

        var stream = new MemoryStream(content, writable: false);
        var formFile = new FormFile(
            stream,
            0,
            content.LongLength,
            "File",
            fileName)
        {
            Headers = new HeaderDictionary(),
            ContentType = contentType
        };

        var internalKey =
            $"{IntakeIdempotencyKey.ReservedPrefix}mailbox-attachment:{sourceId:N}";

        var result = await _documentIntakeService.IntakeWithInternalIdempotencyKeyAsync(
            customerId,
            formFile,
            internalKey,
            cancellationToken);

        return new InternalDocumentIntakeResult(
            result.Outcome switch
            {
                DocumentIntakeOutcome.Accepted => InternalDocumentIntakeOutcome.Accepted,
                DocumentIntakeOutcome.Rejected => InternalDocumentIntakeOutcome.Rejected,
                DocumentIntakeOutcome.Failed => InternalDocumentIntakeOutcome.Failed,
                _ => throw new InvalidOperationException(
                    $"Unsupported document intake outcome '{result.Outcome}'.")
            },
            result.DocumentId,
            result.DocumentStatus,
            result.IsReplay,
            result.Error);
    }
}
