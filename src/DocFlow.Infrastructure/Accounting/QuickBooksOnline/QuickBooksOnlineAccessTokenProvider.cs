using DocFlow.Application.Abstractions;
using DocFlow.Infrastructure.Persistence;
using Microsoft.EntityFrameworkCore;

namespace DocFlow.Infrastructure.Accounting.QuickBooksOnline;

public sealed class QuickBooksOnlineAccessTokenProvider
    : IQuickBooksOnlineAccessTokenProvider
{
    private readonly DocFlowDbContext _dbContext;
    private readonly IQuickBooksOnlineTokenClient _tokenClient;
    private readonly ISecretProtector _secretProtector;
    private readonly QuickBooksOnlineOAuthOptions _options;

    public QuickBooksOnlineAccessTokenProvider(
        DocFlowDbContext dbContext,
        IQuickBooksOnlineTokenClient tokenClient,
        ISecretProtector secretProtector,
        QuickBooksOnlineOAuthOptions options)
    {
        _dbContext = dbContext;
        _tokenClient = tokenClient;
        _secretProtector = secretProtector;
        _options = options;
    }

    public async Task<string?> GetAccessTokenAsync(
        Guid customerId,
        string targetKey,
        CancellationToken cancellationToken = default)
    {
        if (customerId == Guid.Empty || string.IsNullOrWhiteSpace(targetKey))
            return null;

        await using var transaction =
            await _dbContext.Database.BeginTransactionAsync(
                cancellationToken);

        var normalizedTargetKey = targetKey.Trim();

        var connection = await _dbContext.QuickBooksOnlineConnections
            .FromSqlInterpolated(
                $"""
                SELECT *
                FROM "QuickBooksOnlineConnections"
                WHERE "CustomerId" = {customerId}
                  AND "TargetKey" = {normalizedTargetKey}
                FOR UPDATE
                """)
            .SingleOrDefaultAsync(cancellationToken);

        if (connection is null || connection.DisconnectedAt is not null)
        {
            await transaction.CommitAsync(cancellationToken);
            return null;
        }

        var now = DateTimeOffset.UtcNow;
        var refreshAt = now.AddSeconds(
            _options.AccessTokenRefreshSkewSeconds);

        if (connection.AccessTokenExpiresAt > refreshAt)
        {
            var accessToken = _secretProtector.Unprotect(
                connection.ProtectedAccessToken);

            await transaction.CommitAsync(cancellationToken);
            return accessToken;
        }

        if (connection.RefreshTokenExpiresAt <= now)
        {
            connection.Disconnect(now);
            await _dbContext.SaveChangesAsync(cancellationToken);
            await transaction.CommitAsync(cancellationToken);
            return null;
        }

        var refreshToken = _secretProtector.Unprotect(
            connection.ProtectedRefreshToken);

        var tokens = await _tokenClient.RefreshAsync(
            refreshToken,
            cancellationToken);

        if (tokens is null)
        {
            connection.Disconnect(now);
            await _dbContext.SaveChangesAsync(cancellationToken);
            await transaction.CommitAsync(cancellationToken);
            return null;
        }

        var protectedAccessToken = _secretProtector.Protect(
            tokens.AccessToken);
        var protectedRefreshToken = _secretProtector.Protect(
            tokens.RefreshToken);

        connection.RotateTokens(
            protectedAccessToken,
            now.AddSeconds(tokens.AccessTokenExpiresInSeconds),
            protectedRefreshToken,
            now.AddSeconds(tokens.RefreshTokenExpiresInSeconds),
            now);

        await _dbContext.SaveChangesAsync(cancellationToken);
        await transaction.CommitAsync(cancellationToken);

        return tokens.AccessToken;
    }
}
