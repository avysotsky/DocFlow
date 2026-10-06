namespace DocFlow.Infrastructure.Accounting.QuickBooksOnline;

public sealed record QuickBooksOnlineTokenSet(
    string AccessToken,
    int AccessTokenExpiresInSeconds,
    string RefreshToken,
    int RefreshTokenExpiresInSeconds);

public interface IQuickBooksOnlineTokenClient
{
    Task<QuickBooksOnlineTokenSet> ExchangeAuthorizationCodeAsync(
        string authorizationCode,
        CancellationToken cancellationToken = default);

    Task<QuickBooksOnlineTokenSet?> RefreshAsync(
        string refreshToken,
        CancellationToken cancellationToken = default);
}
