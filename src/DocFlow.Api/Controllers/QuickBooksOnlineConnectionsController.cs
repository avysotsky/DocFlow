using DocFlow.Api.Authentication;
using DocFlow.Infrastructure.Accounting.QuickBooksOnline;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace DocFlow.Api.Controllers;

[ApiController]
[Route("api/accounting-connections/quickbooks-online")]
public sealed class QuickBooksOnlineConnectionsController : ControllerBase
{
    private readonly IQuickBooksOnlineOAuthService _oauthService;

    public QuickBooksOnlineConnectionsController(
        IQuickBooksOnlineOAuthService oauthService)
    {
        _oauthService = oauthService;
    }

    [Authorize]
    [HttpPost("targets/{targetKey}/authorize")]
    [ProducesResponseType(
        typeof(QuickBooksAuthorizationResponse),
        StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status400BadRequest)]
    [ProducesResponseType(StatusCodes.Status401Unauthorized)]
    public async Task<ActionResult<QuickBooksAuthorizationResponse>> AuthorizeTarget(
        string targetKey,
        CancellationToken cancellationToken)
    {
        if (string.IsNullOrWhiteSpace(targetKey))
            return BadRequest("Target key is required.");

        try
        {
            var result = await _oauthService.BeginAuthorizationAsync(
                User.GetRequiredCustomerId(),
                targetKey,
                cancellationToken);

            return Ok(
                new QuickBooksAuthorizationResponse(
                    result.AuthorizationUrl,
                    result.ExpiresAt));
        }
        catch (InvalidOperationException exception)
        {
            return BadRequest(exception.Message);
        }
    }

    [AllowAnonymous]
    [HttpGet("callback")]
    [ProducesResponseType(
        typeof(QuickBooksConnectionResponse),
        StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status400BadRequest)]
    public async Task<ActionResult<QuickBooksConnectionResponse>> Callback(
        [FromQuery] string? code,
        [FromQuery] string? state,
        [FromQuery] string? realmId,
        [FromQuery] string? error,
        CancellationToken cancellationToken)
    {
        if (!string.IsNullOrWhiteSpace(error))
            return BadRequest("QuickBooks Online authorization was not granted.");

        if (string.IsNullOrWhiteSpace(code)
            || string.IsNullOrWhiteSpace(state)
            || string.IsNullOrWhiteSpace(realmId))
        {
            return BadRequest("QuickBooks Online callback is incomplete.");
        }

        var connection = await _oauthService.CompleteAuthorizationAsync(
            code,
            state,
            realmId,
            cancellationToken);

        return connection is null
            ? BadRequest("QuickBooks Online OAuth state or realm is invalid.")
            : Ok(ToResponse(connection));
    }

    [Authorize]
    [HttpGet("targets/{targetKey}")]
    [ProducesResponseType(
        typeof(QuickBooksConnectionResponse),
        StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status401Unauthorized)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<ActionResult<QuickBooksConnectionResponse>> GetConnection(
        string targetKey,
        CancellationToken cancellationToken)
    {
        if (string.IsNullOrWhiteSpace(targetKey))
            return NotFound();

        var connection = await _oauthService.GetConnectionAsync(
            User.GetRequiredCustomerId(),
            targetKey,
            cancellationToken);

        return connection is null
            ? NotFound()
            : Ok(ToResponse(connection));
    }

    private static QuickBooksConnectionResponse ToResponse(
        QuickBooksOnlineConnectionSnapshot connection)
        => new(
            connection.TargetKey,
            connection.RealmId,
            connection.AccessTokenExpiresAt,
            connection.RefreshTokenExpiresAt,
            connection.ConnectedAt,
            connection.UpdatedAt,
            connection.IsConnected);

    public sealed record QuickBooksAuthorizationResponse(
        string AuthorizationUrl,
        DateTimeOffset ExpiresAt);

    public sealed record QuickBooksConnectionResponse(
        string TargetKey,
        string RealmId,
        DateTimeOffset AccessTokenExpiresAt,
        DateTimeOffset RefreshTokenExpiresAt,
        DateTimeOffset ConnectedAt,
        DateTimeOffset UpdatedAt,
        bool IsConnected);
}
