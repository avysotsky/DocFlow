using System.Net;
using System.Text;
using DocFlow.Infrastructure.Accounting.QuickBooksOnline;
using Xunit;

namespace DocFlow.Infrastructure.Tests;

public sealed class QuickBooksOnlineTokenClientTests
{
    [Fact]
    public async Task ExchangeAuthorizationCodeAsync_SendsBasicAuthAndStoresLatestTokens()
    {
        var handler = new RecordingHandler(_ =>
            JsonResponse(
                HttpStatusCode.OK,
                """
                {
                  "access_token": "access-1",
                  "expires_in": 3600,
                  "refresh_token": "refresh-1",
                  "x_refresh_token_expires_in": 8726400
                }
                """));

        var client = CreateClient(handler);

        var tokens = await client.ExchangeAuthorizationCodeAsync(
            "authorization-code");

        Assert.Equal("access-1", tokens.AccessToken);
        Assert.Equal(3600, tokens.AccessTokenExpiresInSeconds);
        Assert.Equal("refresh-1", tokens.RefreshToken);
        Assert.Equal(8726400, tokens.RefreshTokenExpiresInSeconds);

        var request = Assert.Single(handler.Requests);
        Assert.Equal(
            "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer",
            request.Uri);
        Assert.Equal("Basic", request.AuthorizationScheme);
        Assert.Equal(
            Convert.ToBase64String(
                Encoding.UTF8.GetBytes("client-id:client-secret")),
            request.AuthorizationParameter);
        Assert.Contains(
            "grant_type=authorization_code",
            request.Body,
            StringComparison.Ordinal);
        Assert.Contains(
            "code=authorization-code",
            request.Body,
            StringComparison.Ordinal);
        Assert.Contains(
            "redirect_uri=https%3A%2F%2Fdocflow.example%2Fapi%2Faccounting-connections%2Fquickbooks-online%2Fcallback",
            request.Body,
            StringComparison.Ordinal);
    }

    [Fact]
    public async Task RefreshAsync_UsesReturnedRotatedRefreshToken()
    {
        var handler = new RecordingHandler(_ =>
            JsonResponse(
                HttpStatusCode.OK,
                """
                {
                  "access_token": "access-2",
                  "expires_in": 3600,
                  "refresh_token": "refresh-2",
                  "x_refresh_token_expires_in": 8726400
                }
                """));

        var client = CreateClient(handler);

        var tokens = await client.RefreshAsync("refresh-1");

        Assert.NotNull(tokens);
        Assert.Equal("access-2", tokens!.AccessToken);
        Assert.Equal("refresh-2", tokens.RefreshToken);

        var request = Assert.Single(handler.Requests);
        Assert.Contains(
            "grant_type=refresh_token",
            request.Body,
            StringComparison.Ordinal);
        Assert.Contains(
            "refresh_token=refresh-1",
            request.Body,
            StringComparison.Ordinal);
    }

    [Fact]
    public async Task RefreshAsync_PreservesExistingRefreshTokenWhenResponseOmitsIt()
    {
        var handler = new RecordingHandler(_ =>
            JsonResponse(
                HttpStatusCode.OK,
                """
                {
                  "access_token": "access-2",
                  "expires_in": 3600,
                  "x_refresh_token_expires_in": 8640000
                }
                """));

        var client = CreateClient(handler);

        var tokens = await client.RefreshAsync("refresh-1");

        Assert.NotNull(tokens);
        Assert.Equal("refresh-1", tokens!.RefreshToken);
        Assert.Equal(8640000, tokens.RefreshTokenExpiresInSeconds);
    }

    [Fact]
    public async Task RefreshAsync_InvalidGrantReturnsDisconnectedSignal()
    {
        var handler = new RecordingHandler(_ =>
            JsonResponse(
                HttpStatusCode.BadRequest,
                """{"error":"invalid_grant","error_description":"Refresh token invalid"}"""));

        var client = CreateClient(handler);

        var tokens = await client.RefreshAsync("stale-refresh-token");

        Assert.Null(tokens);
    }

    [Fact]
    public async Task RefreshAsync_TransientTokenEndpointFailureThrowsHttpRequestException()
    {
        var handler = new RecordingHandler(_ =>
            JsonResponse(
                HttpStatusCode.ServiceUnavailable,
                """{"error":"temporarily_unavailable"}"""));

        var client = CreateClient(handler);

        var exception = await Assert.ThrowsAsync<HttpRequestException>(
            () => client.RefreshAsync("refresh-1"));

        Assert.Equal(
            HttpStatusCode.ServiceUnavailable,
            exception.StatusCode);
    }

    private static QuickBooksOnlineTokenClient CreateClient(
        RecordingHandler handler)
        => new(
            new HttpClient(handler),
            new QuickBooksOnlineOAuthOptions
            {
                ClientId = "client-id",
                ClientSecret = "client-secret",
                RedirectUri =
                    "https://docflow.example/api/accounting-connections/quickbooks-online/callback",
                TokenUrl =
                    "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"
            });

    private static HttpResponseMessage JsonResponse(
        HttpStatusCode statusCode,
        string body)
        => new(statusCode)
        {
            Content = new StringContent(
                body,
                Encoding.UTF8,
                "application/json")
        };

    private sealed class RecordingHandler : HttpMessageHandler
    {
        private readonly Func<HttpRequestMessage, HttpResponseMessage> _handler;

        public RecordingHandler(
            Func<HttpRequestMessage, HttpResponseMessage> handler)
        {
            _handler = handler;
        }

        public List<RecordedRequest> Requests { get; } = [];

        protected override async Task<HttpResponseMessage> SendAsync(
            HttpRequestMessage request,
            CancellationToken cancellationToken)
        {
            Requests.Add(
                new RecordedRequest(
                    request.RequestUri!.ToString(),
                    request.Headers.Authorization?.Scheme,
                    request.Headers.Authorization?.Parameter,
                    request.Content is null
                        ? string.Empty
                        : await request.Content.ReadAsStringAsync(
                            cancellationToken)));

            return _handler(request);
        }
    }

    private sealed record RecordedRequest(
        string Uri,
        string? AuthorizationScheme,
        string? AuthorizationParameter,
        string Body);
}
