using System.Net;
using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;

namespace DocFlow.Infrastructure.Accounting.QuickBooksOnline;

public sealed class QuickBooksOnlineTokenClient
    : IQuickBooksOnlineTokenClient
{
    private readonly HttpClient _httpClient;
    private readonly QuickBooksOnlineOAuthOptions _options;

    public QuickBooksOnlineTokenClient(
        HttpClient httpClient,
        QuickBooksOnlineOAuthOptions options)
    {
        _httpClient = httpClient;
        _options = options;
    }

    public Task<QuickBooksOnlineTokenSet> ExchangeAuthorizationCodeAsync(
        string authorizationCode,
        CancellationToken cancellationToken = default)
        => SendTokenRequestAsync(
            new Dictionary<string, string>
            {
                ["grant_type"] = "authorization_code",
                ["code"] = authorizationCode,
                ["redirect_uri"] = _options.RedirectUri
            },
            existingRefreshToken: null,
            allowInvalidGrant: false,
            cancellationToken)!;

    public async Task<QuickBooksOnlineTokenSet?> RefreshAsync(
        string refreshToken,
        CancellationToken cancellationToken = default)
        => await SendTokenRequestAsync(
            new Dictionary<string, string>
            {
                ["grant_type"] = "refresh_token",
                ["refresh_token"] = refreshToken
            },
            existingRefreshToken: refreshToken,
            allowInvalidGrant: true,
            cancellationToken);

    private async Task<QuickBooksOnlineTokenSet?> SendTokenRequestAsync(
        IReadOnlyDictionary<string, string> form,
        string? existingRefreshToken,
        bool allowInvalidGrant,
        CancellationToken cancellationToken)
    {
        using var request = new HttpRequestMessage(
            HttpMethod.Post,
            _options.TokenUrl);

        var credentials = Convert.ToBase64String(
            Encoding.UTF8.GetBytes(
                $"{_options.ClientId}:{_options.ClientSecret}"));

        request.Headers.Authorization =
            new AuthenticationHeaderValue("Basic", credentials);
        request.Headers.Accept.Add(
            new MediaTypeWithQualityHeaderValue("application/json"));
        request.Content = new FormUrlEncodedContent(form);

        using var response = await _httpClient.SendAsync(
            request,
            cancellationToken);
        var body = await response.Content.ReadAsStringAsync(
            cancellationToken);

        if (!response.IsSuccessStatusCode)
        {
            var error = TryReadError(body);

            if (allowInvalidGrant
                && string.Equals(
                    error.Error,
                    "invalid_grant",
                    StringComparison.Ordinal))
            {
                return null;
            }

            throw new HttpRequestException(
                $"QuickBooks Online token endpoint returned HTTP {(int)response.StatusCode}"
                + (string.IsNullOrWhiteSpace(error.Error)
                    ? "."
                    : $" ({error.Error})."),
                inner: null,
                response.StatusCode);
        }

        using var document = JsonDocument.Parse(body);
        var root = document.RootElement;

        var accessToken = RequiredString(root, "access_token");
        var expiresIn = RequiredPositiveInt(root, "expires_in");

        var returnedRefreshToken = root.TryGetProperty(
                "refresh_token",
                out var refreshTokenProperty)
            && refreshTokenProperty.ValueKind == JsonValueKind.String
            ? refreshTokenProperty.GetString()
            : null;

        var effectiveRefreshToken =
            !string.IsNullOrWhiteSpace(returnedRefreshToken)
                ? returnedRefreshToken!
                : existingRefreshToken
                    ?? throw new InvalidOperationException(
                        "QuickBooks Online token response did not contain a refresh token.");

        var refreshExpiresIn = RequiredPositiveInt(
            root,
            "x_refresh_token_expires_in");

        return new QuickBooksOnlineTokenSet(
            accessToken,
            expiresIn,
            effectiveRefreshToken,
            refreshExpiresIn);
    }

    private static string RequiredString(
        JsonElement root,
        string propertyName)
    {
        if (!root.TryGetProperty(propertyName, out var property)
            || property.ValueKind != JsonValueKind.String
            || string.IsNullOrWhiteSpace(property.GetString()))
        {
            throw new InvalidOperationException(
                $"QuickBooks Online token response is missing '{propertyName}'.");
        }

        return property.GetString()!;
    }

    private static int RequiredPositiveInt(
        JsonElement root,
        string propertyName)
    {
        if (!root.TryGetProperty(propertyName, out var property)
            || property.ValueKind != JsonValueKind.Number
            || !property.TryGetInt32(out var value)
            || value <= 0)
        {
            throw new InvalidOperationException(
                $"QuickBooks Online token response is missing positive '{propertyName}'.");
        }

        return value;
    }

    private static OAuthError TryReadError(string body)
    {
        if (string.IsNullOrWhiteSpace(body))
            return new OAuthError(null);

        try
        {
            using var document = JsonDocument.Parse(body);
            return new OAuthError(
                document.RootElement.TryGetProperty(
                    "error",
                    out var property)
                    && property.ValueKind == JsonValueKind.String
                    ? property.GetString()
                    : null);
        }
        catch (JsonException)
        {
            return new OAuthError(null);
        }
    }

    private sealed record OAuthError(string? Error);
}
