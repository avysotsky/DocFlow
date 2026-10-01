using DocFlow.Api.Authentication;
using DocFlow.Application.Abstractions;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace DocFlow.Api.Controllers;

[ApiController]
[Authorize]
[Route("api/documents/{documentId:guid}")]
public sealed class DocumentDeletionController : ControllerBase
{
    private readonly IDocumentDeletionService _documentDeletionService;

    public DocumentDeletionController(IDocumentDeletionService documentDeletionService)
    {
        _documentDeletionService = documentDeletionService;
    }

    [HttpDelete]
    [ProducesResponseType(StatusCodes.Status204NoContent)]
    [ProducesResponseType(StatusCodes.Status401Unauthorized)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    [ProducesResponseType(StatusCodes.Status409Conflict)]
    public async Task<IActionResult> Delete(
        Guid documentId,
        CancellationToken cancellationToken)
    {
        var customerId = User.GetRequiredCustomerId();

        var outcome = await _documentDeletionService.DeleteAsync(
            documentId,
            customerId,
            cancellationToken);

        return outcome switch
        {
            DocumentDeletionOutcome.Deleted => NoContent(),
            DocumentDeletionOutcome.NotFound => NotFound(),
            DocumentDeletionOutcome.ActiveProcessingConflict => Conflict(
                "Uploaded or Processing documents cannot be deleted while background processing may own them."),
            _ => throw new InvalidOperationException(
                $"Unsupported document deletion outcome '{outcome}'.")
        };
    }
}
