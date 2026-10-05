using DocFlow.Api.Authentication;
using DocFlow.Application.Abstractions;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace DocFlow.Api.Controllers;

[ApiController]
[Authorize]
[Route("api/accounting-postings")]
public sealed class AccountingPostingsController : ControllerBase
{
    private readonly IAccountingPostingService _service;
    private readonly IAccountingPostingTargetResolver _targetResolver;

    public AccountingPostingsController(
        IAccountingPostingService service,
        IAccountingPostingTargetResolver targetResolver)
    {
        _service = service;
        _targetResolver = targetResolver;
    }

    [HttpPost]
    [Consumes("application/json")]
    [ProducesResponseType(typeof(AccountingPostingSnapshot), StatusCodes.Status201Created)]
    [ProducesResponseType(typeof(AccountingPostingSnapshot), StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status400BadRequest)]
    [ProducesResponseType(StatusCodes.Status401Unauthorized)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    [ProducesResponseType(StatusCodes.Status409Conflict)]
    [ProducesResponseType(StatusCodes.Status422UnprocessableEntity)]
    public async Task<ActionResult<AccountingPostingSnapshot>> Create(
        [FromBody] CreateAccountingPostingRequest request,
        CancellationToken cancellationToken)
    {
        if (request.DocumentId == Guid.Empty)
            return BadRequest("Document id is required.");
        if (string.IsNullOrWhiteSpace(request.TargetKey))
            return BadRequest("Target key is required.");
        if (request.TargetKey.Trim().Length > 100)
            return BadRequest("Target key must not exceed 100 characters.");
        if (string.IsNullOrWhiteSpace(request.IdempotencyKey))
            return BadRequest("Idempotency key is required.");
        if (request.IdempotencyKey.Trim().Length > 128)
            return BadRequest("Idempotency key must not exceed 128 characters.");

        var result = await _service.CreateAndPostAsync(
            User.GetRequiredCustomerId(),
            request.DocumentId,
            request.TargetKey,
            request.IdempotencyKey,
            cancellationToken);

        switch (result.Outcome)
        {
            case AccountingPostingCreateOutcome.Created:
                return CreatedAtAction(
                    nameof(Get),
                    new { postingId = result.Posting!.Id },
                    result.Posting);

            case AccountingPostingCreateOutcome.Replay:
                Response.Headers["Idempotency-Replayed"] = "true";
                return Ok(result.Posting!);

            case AccountingPostingCreateOutcome.Conflict:
                return Conflict(
                    "The idempotency key is already used for a different accounting posting request.");

            case AccountingPostingCreateOutcome.DocumentNotFound:
                return NotFound(
                    "Document was not found for the authenticated tenant.");

            case AccountingPostingCreateOutcome.InvalidDocumentType:
                return BadRequest(
                    "Only supplier_invoice documents can be posted.");

            case AccountingPostingCreateOutcome.DocumentNotReady:
                return Conflict(
                    "Document must be fully Processed before accounting posting.");

            case AccountingPostingCreateOutcome.ExtractionResultNotFound:
                return NotFound(
                    "Document extraction result was not found.");

            case AccountingPostingCreateOutcome.InvalidPayload:
                return UnprocessableEntity(
                    "Processed invoice does not contain a valid canonical accounting bill payload.");

            case AccountingPostingCreateOutcome.TargetNotFound:
                return NotFound(
                    "Accounting target was not found for the authenticated tenant.");

            case AccountingPostingCreateOutcome.UnsupportedProvider:
                return BadRequest(
                    "The requested accounting provider is not configured.");

            default:
                throw new InvalidOperationException(
                    $"Unsupported accounting posting outcome '{result.Outcome}'.");
        }
    }

    [HttpGet("targets")]
    [ProducesResponseType(
        typeof(IReadOnlyList<AccountingPostingTargetSummary>),
        StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status401Unauthorized)]
    public ActionResult<IReadOnlyList<AccountingPostingTargetSummary>> GetTargets()
    {
        var targets = _targetResolver
            .GetAvailable(User.GetRequiredCustomerId())
            .Select(target => new AccountingPostingTargetSummary(
                target.Key,
                target.Provider))
            .ToArray();

        return Ok(targets);
    }

    [HttpGet("{postingId:guid}")]
    [ProducesResponseType(typeof(AccountingPostingSnapshot), StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status401Unauthorized)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<ActionResult<AccountingPostingSnapshot>> Get(
        Guid postingId,
        CancellationToken cancellationToken)
    {
        if (postingId == Guid.Empty)
            return NotFound();

        var posting = await _service.GetAsync(
            User.GetRequiredCustomerId(),
            postingId,
            cancellationToken);

        return posting is null ? NotFound() : Ok(posting);
    }

    public sealed record AccountingPostingTargetSummary(
        string Key,
        string Provider);

    public sealed record CreateAccountingPostingRequest(
        Guid DocumentId,
        string TargetKey,
        string IdempotencyKey);
}
