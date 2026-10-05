using DocFlow.Api.Authentication;
using DocFlow.Api.Documents;
using DocFlow.Application.Abstractions;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace DocFlow.Api.Controllers;

[ApiController]
[Authorize]
[Route("api/mailbox/messages")]
public sealed class MailboxMessagesController : ControllerBase
{
    private readonly IMailboxMessageIngestionService _ingestionService;

    public MailboxMessagesController(IMailboxMessageIngestionService ingestionService)
    {
        _ingestionService = ingestionService;
    }

    [HttpPost("rfc822")]
    [Consumes("message/rfc822", "application/octet-stream")]
    [ProducesResponseType(typeof(MailboxMessageIngestionResult), StatusCodes.Status201Created)]
    [ProducesResponseType(typeof(MailboxMessageIngestionResult), StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status400BadRequest)]
    [ProducesResponseType(StatusCodes.Status401Unauthorized)]
    [ProducesResponseType(StatusCodes.Status409Conflict)]
    public async Task<ActionResult<MailboxMessageIngestionResult>> IngestRfc822(
        CancellationToken cancellationToken)
    {
        var result = await _ingestionService.IngestAsync(
            User.GetRequiredCustomerId(),
            Request.Body,
            cancellationToken);

        return result.Outcome switch
        {
            MailboxMessageIngestionOutcome.Accepted => StatusCode(
                StatusCodes.Status201Created,
                result),
            MailboxMessageIngestionOutcome.Replay => Replay(result),
            MailboxMessageIngestionOutcome.Conflict => Conflict(result),
            MailboxMessageIngestionOutcome.Rejected => BadRequest(result),
            _ => throw new InvalidOperationException(
                $"Unsupported mailbox ingestion outcome '{result.Outcome}'.")
        };
    }

    private ActionResult<MailboxMessageIngestionResult> Replay(
        MailboxMessageIngestionResult result)
    {
        Response.Headers[IntakeIdempotencyKey.ReplayHeaderName] = "true";
        return Ok(result);
    }
}
