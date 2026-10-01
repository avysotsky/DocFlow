using System.Text.Json;
using DocFlow.Api.Authentication;
using DocFlow.Application.Abstractions;
using DocFlow.Infrastructure.Persistence;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace DocFlow.Api.Controllers;

[ApiController]
[Authorize]
[Route("api/documents/{documentId:guid}/review")]
public sealed class DocumentReviewsController : ControllerBase
{
    private const int MaxReviewNoteLength = 2000;

    private readonly DocFlowDbContext _dbContext;
    private readonly IDocumentReviewService _documentReviewService;

    public DocumentReviewsController(
        DocFlowDbContext dbContext,
        IDocumentReviewService documentReviewService)
    {
        _dbContext = dbContext;
        _documentReviewService = documentReviewService;
    }

    [HttpPut]
    [Consumes("application/json")]
    [ProducesResponseType(typeof(DocumentReviewResponse), StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status400BadRequest)]
    [ProducesResponseType(StatusCodes.Status401Unauthorized)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    [ProducesResponseType(StatusCodes.Status409Conflict)]
    public async Task<ActionResult<DocumentReviewResponse>> Review(
        Guid documentId,
        [FromBody] DocumentReviewRequest request,
        CancellationToken cancellationToken)
    {
        var customerId = User.GetRequiredCustomerId();
        var reviewedByClient = User.GetRequiredClientName();
        var isOwned = await _dbContext.Documents
            .AsNoTracking()
            .AnyAsync(
                x => x.Id == documentId && x.CustomerId == customerId,
                cancellationToken);

        if (!isOwned)
            return NotFound();

        if (request.ExpectedExtractionResultId == Guid.Empty)
            return BadRequest("Expected extraction result id is required.");

        if (request.Data.ValueKind != JsonValueKind.Object)
            return BadRequest("Review data must be a JSON object.");

        if (request.Note?.Length > MaxReviewNoteLength)
            return BadRequest($"Review note must not exceed {MaxReviewNoteLength} characters.");

        var result = await _documentReviewService.ReviewAsync(
            documentId,
            request.ExpectedExtractionResultId,
            request.Data.GetRawText(),
            request.Note,
            reviewedByClient,
            cancellationToken);

        return result.Outcome switch
        {
            DocumentReviewOutcome.Reviewed => Ok(new DocumentReviewResponse(
                result.Review!.DocumentId,
                result.Review.ExtractionResultId,
                result.Review.ReviewId,
                result.Review.ReviewedAt,
                result.Review.DocumentStatus,
                result.Review.Note,
                result.Review.ReviewedByClient)),
            DocumentReviewOutcome.DocumentNotFound => NotFound(),
            DocumentReviewOutcome.ExtractionResultNotFound => NotFound(),
            DocumentReviewOutcome.StaleExtractionResult => Conflict(
                "The extraction result changed after the review was loaded."),
            DocumentReviewOutcome.AlreadyReviewed => Conflict(
                "The document has already been reviewed."),
            DocumentReviewOutcome.NotReviewable => Conflict(
                "The document is not in a reviewable state."),
            _ => throw new InvalidOperationException(
                $"Unsupported document review outcome '{result.Outcome}'.")
        };
    }

    public sealed class DocumentReviewRequest
    {
        public Guid ExpectedExtractionResultId { get; init; }
        public JsonElement Data { get; init; }
        public string? Note { get; init; }
    }

    public sealed record DocumentReviewResponse(
        Guid DocumentId,
        Guid ExtractionResultId,
        Guid ReviewId,
        DateTimeOffset ReviewedAt,
        string DocumentStatus,
        string? Note,
        string ReviewedByClient);
}
