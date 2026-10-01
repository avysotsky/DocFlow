using System.Security.Claims;
using System.Security.Cryptography;
using System.Text;
using System.Text.Encodings.Web;
using Microsoft.AspNetCore.Authentication;
using Microsoft.Extensions.Options;

namespace DocFlow.Api.Authentication;

public static class ApiKeyAuthenticationDefaults
{
    public const string Scheme = "DocFlowApiKey";
    public const string ConfigurationSection = "Authentication:ApiKey";
    public const string DefaultHeaderName = "X-DocFlow-Api-Key";
    public const string CustomerIdClaimType = "docflow:customer_id";
}

public sealed class ApiKeyAuthenticationOptions
{
    public string HeaderName { get; set; } = ApiKeyAuthenticationDefaults.DefaultHeaderName;
    public List<ApiKeyClientOptions> Clients { get; set; } = [];
}

public sealed class ApiKeyClientOptions
{
    public string? Name { get; set; }
    public Guid CustomerId { get; set; }
    public string ApiKey { get; set; } = string.Empty;
}

public sealed class ApiKeyAuthenticationHandler : AuthenticationHandler<AuthenticationSchemeOptions>
{
    private readonly IOptionsMonitor<ApiKeyAuthenticationOptions> _apiKeyOptions;

    public ApiKeyAuthenticationHandler(
        IOptionsMonitor<AuthenticationSchemeOptions> schemeOptions,
        IOptionsMonitor<ApiKeyAuthenticationOptions> apiKeyOptions,
        ILoggerFactory logger,
        UrlEncoder encoder)
        : base(schemeOptions, logger, encoder)
    {
        _apiKeyOptions = apiKeyOptions;
    }

    protected override Task<AuthenticateResult> HandleAuthenticateAsync()
    {
        var options = _apiKeyOptions.CurrentValue;
        var headerName = string.IsNullOrWhiteSpace(options.HeaderName)
            ? ApiKeyAuthenticationDefaults.DefaultHeaderName
            : options.HeaderName.Trim();

        if (!Request.Headers.TryGetValue(headerName, out var headerValues)
            || headerValues.Count != 1)
        {
            return Task.FromResult(AuthenticateResult.NoResult());
        }

        var presentedKey = headerValues[0];
        if (string.IsNullOrWhiteSpace(presentedKey))
            return Task.FromResult(AuthenticateResult.Fail("The API key is invalid."));

        ApiKeyClientOptions? matchedClient = null;
        foreach (var client in options.Clients)
        {
            if (client.CustomerId == Guid.Empty || string.IsNullOrEmpty(client.ApiKey))
                continue;

            if (FixedTimeEquals(client.ApiKey, presentedKey))
            {
                matchedClient = client;
                break;
            }
        }

        if (matchedClient is null)
            return Task.FromResult(AuthenticateResult.Fail("The API key is invalid."));

        var customerId = matchedClient.CustomerId.ToString("D");
        var clientName = string.IsNullOrWhiteSpace(matchedClient.Name)
            ? customerId
            : matchedClient.Name.Trim();

        var claims = new[]
        {
            new Claim(ClaimTypes.NameIdentifier, clientName),
            new Claim(ClaimTypes.Name, clientName),
            new Claim(ApiKeyAuthenticationDefaults.CustomerIdClaimType, customerId)
        };

        var identity = new ClaimsIdentity(claims, Scheme.Name);
        var principal = new ClaimsPrincipal(identity);
        var ticket = new AuthenticationTicket(principal, Scheme.Name);

        return Task.FromResult(AuthenticateResult.Success(ticket));
    }

    private static bool FixedTimeEquals(string expected, string actual)
    {
        var expectedBytes = Encoding.UTF8.GetBytes(expected);
        var actualBytes = Encoding.UTF8.GetBytes(actual);

        return expectedBytes.Length == actualBytes.Length
            && CryptographicOperations.FixedTimeEquals(expectedBytes, actualBytes);
    }
}

public static class ClaimsPrincipalExtensions
{
    public static Guid GetRequiredCustomerId(this ClaimsPrincipal principal)
    {
        var value = principal.FindFirst(ApiKeyAuthenticationDefaults.CustomerIdClaimType)?.Value;
        if (!Guid.TryParse(value, out var customerId) || customerId == Guid.Empty)
        {
            throw new InvalidOperationException(
                "The authenticated principal does not contain a valid DocFlow customer id.");
        }

        return customerId;
    }
}
