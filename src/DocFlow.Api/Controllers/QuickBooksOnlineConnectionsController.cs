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
    private readonly QuickBooksOnlineReferenceDiscoveryService _referenceDiscovery;
    private readonly QuickBooksOnlineMappingValidationService _mappingValidation;

    public QuickBooksOnlineConnectionsController(
        IQuickBooksOnlineOAuthService oauthService,
        QuickBooksOnlineReferenceDiscoveryService referenceDiscovery,
        QuickBooksOnlineMappingValidationService mappingValidation)
    {
        _oauthService = oauthService;
        _referenceDiscovery = referenceDiscovery;
        _mappingValidation = mappingValidation;
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
    [HttpGet("targets/{targetKey}/references")]
    [ProducesResponseType(
        typeof(QuickBooksReferenceCatalogResponse),
        StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status401Unauthorized)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    [ProducesResponseType(StatusCodes.Status502BadGateway)]
    public async Task<ActionResult<QuickBooksReferenceCatalogResponse>> GetReferences(
        string targetKey,
        CancellationToken cancellationToken)
    {
        if (string.IsNullOrWhiteSpace(targetKey))
            return NotFound();

        try
        {
            var references = await _referenceDiscovery.DiscoverAsync(
                User.GetRequiredCustomerId(),
                targetKey,
                cancellationToken);

            return references is null
                ? NotFound()
                : Ok(new QuickBooksReferenceCatalogResponse(
                    references.Vendors,
                    references.Accounts,
                    references.TaxCodes));
        }
        catch (HttpRequestException)
        {
            return StatusCode(
                StatusCodes.Status502BadGateway,
                "QuickBooks Online reference discovery failed.");
        }
        catch (InvalidOperationException)
        {
            return StatusCode(
                StatusCodes.Status502BadGateway,
                "QuickBooks Online reference discovery returned invalid data.");
        }
    }

    [Authorize]
    [HttpGet("targets/{targetKey}/mapping-validation")]
    [ProducesResponseType(
        typeof(QuickBooksOnlineMappingValidationResult),
        StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status401Unauthorized)]
    [ProducesResponseType(StatusCodes.Status502BadGateway)]
    public async Task<ActionResult<QuickBooksOnlineMappingValidationResult>> ValidateMapping(
        string targetKey,
        CancellationToken cancellationToken)
    {
        if (string.IsNullOrWhiteSpace(targetKey))
        {
            return Ok(
                new QuickBooksOnlineMappingValidationResult(
                    false,
                    [
                        new QuickBooksOnlineMappingValidationIssue(
                            "target_key_required",
                            "Target key is required.")
                    ]));
        }

        try
        {
            var result = await _mappingValidation.ValidateAsync(
                User.GetRequiredCustomerId(),
                targetKey,
                cancellationToken);

            return Ok(result);
        }
        catch (HttpRequestException)
        {
            return StatusCode(
                StatusCodes.Status502BadGateway,
                "QuickBooks Online mapping validation failed.");
        }
        catch (InvalidOperationException)
        {
            return StatusCode(
                StatusCodes.Status502BadGateway,
                "QuickBooks Online mapping validation returned invalid provider data.");
        }
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
            connection.AccessTokenExpiresAt,
            connection.RefreshTokenExpiresAt,
            connection.ConnectedAt,
            connection.UpdatedAt,
            connection.IsConnected);

    public sealed record QuickBooksReferenceCatalogResponse(
        IReadOnlyList<QuickBooksOnlineVendorReference> Vendors,
        IReadOnlyList<QuickBooksOnlineAccountReference> Accounts,
        IReadOnlyList<QuickBooksOnlineTaxCodeReference> TaxCodes);

    public sealed record QuickBooksAuthorizationResponse(
        string AuthorizationUrl,
        DateTimeOffset ExpiresAt);

    public sealed record QuickBooksConnectionResponse(
        string TargetKey,
        DateTimeOffset AccessTokenExpiresAt,
        DateTimeOffset RefreshTokenExpiresAt,
        DateTimeOffset ConnectedAt,
        DateTimeOffset UpdatedAt,
        bool IsConnected);
}
