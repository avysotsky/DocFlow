using DocFlow.Api.Authentication;
using DocFlow.Infrastructure.Persistence;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace DocFlow.Api.Controllers;

[ApiController]
[Authorize]
[Route("api/documents/{documentId:guid}/processing-diagnostics")]
public sealed class DocumentProcessingDiagnosticsController : ControllerBase
{
    private readonly DocFlowDbContext _dbContext;

    public DocumentProcessingDiagnosticsController(DocFlowDbContext dbContext)
    {
        _dbContext = dbContext;
    }

    [HttpGet]
    [ProducesResponseType(typeof(DocumentProcessingDiagnosticsResponse), StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status401Unauthorized)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<ActionResult<DocumentProcessingDiagnosticsResponse>> Get(
        Guid documentId,
        CancellationToken cancellationToken)
    {
        var customerId = User.GetRequiredCustomerId();

        var diagnostics = await _dbContext.Documents
            .AsNoTracking()
            .Where(x => x.Id == documentId && x.CustomerId == customerId)
            .Select(x => new DocumentProcessingDiagnosticsResponse(
                x.Id,
                x.Status.ToString(),
                x.ProcessingAttempts,
                x.LastProcessingAttemptAt,
                x.LastProcessingFailureAt,
                x.LastProcessingError))
            .SingleOrDefaultAsync(cancellationToken);

        if (diagnostics is null)
            return NotFound();

        return Ok(diagnostics);
    }

    public sealed record DocumentProcessingDiagnosticsResponse(
        Guid DocumentId,
        string Status,
        int ProcessingAttempts,
        DateTimeOffset? LastProcessingAttemptAt,
        DateTimeOffset? LastProcessingFailureAt,
        string? LastProcessingError);
}
