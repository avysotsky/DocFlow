using DocFlow.Api.Controllers;
using Microsoft.OpenApi.Models;
using Swashbuckle.AspNetCore.SwaggerGen;

namespace DocFlow.Api.OpenApi;

public sealed class DocumentContractSchemaFilter : ISchemaFilter
{
    public void Apply(OpenApiSchema schema, SchemaFilterContext context)
    {
        if (context.Type != typeof(DocumentsController.GetDocumentResponse))
            return;

        if (schema.Properties.TryGetValue("storageKey", out var storageKey))
        {
            storageKey.Deprecated = true;
            storageKey.Description =
                "Deprecated internal storage locator. Use sourceFileUrl or GET /api/documents/{id}/file.";
        }

        if (schema.Properties.TryGetValue("sourceFileUrl", out var sourceFileUrl))
        {
            sourceFileUrl.Description =
                "Stable tenant-scoped API path for retrieving the original source PDF.";
        }
    }
}
