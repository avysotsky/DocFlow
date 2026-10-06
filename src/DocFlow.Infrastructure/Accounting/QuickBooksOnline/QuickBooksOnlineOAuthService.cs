using System.Security.Cryptography;
using System.Text;
using DocFlow.Application.Abstractions;
using DocFlow.Domain.Entities;
using DocFlow.Infrastructure.Persistence;
using Microsoft.EntityFrameworkCore;
using Npgsql;

namespace DocFlow.Infrastructure.Accounting.QuickBooksOnline;

public sealed record QuickBooksOnlineAuthorizationStart(
    string AuthorizationUrl,
    DateTimeOffset ExpiresAt);

public sealed record QuickBooksOnlineConnectionSnapshot(
    Guid CustomerId,
    string TargetKey,
    string RealmId,
    DateTimeOffset AccessTokenExpiresAt,
    DateTimeOffset RefreshTokenExpiresAt,
    DateTimeOffset ConnectedAt,
    DateTimeOffset UpdatedAt,
    bool IsConnected);

public interface IQuickBooksOnlineOAuthService
{
    Task<QuickBooksOnlineAuthorizationStart> BeginAuthorizationAsync(
        Guid customerId,
        string targetKey,
        CancellationToken cancellationToken = default);

    Task<QuickBooksOnlineConnectionSnapshot?> CompleteAuthorizationAsync(
        string authorizationCode,
        string state,
        string realmId,
        CancellationToken cancellationToken = default);

    Task<QuickBooksOnlineConnectionSnapshot?> GetConnectionAsync(
        Guid customerId,
        string targetKey,
        CancellationToken cancellationToken = default);
}

public sealed class QuickBooksOnlineOAuthService
    : IQuickBooksOnlineOAuthService
{
    private readonly DocFlowDbContext _dbContext;
    private readonly IAccountingPostingTargetResolver _targetResolver;
    private readonly IQuickBooksOnlineTokenClient _tokenClient;
    private readonly ISecretProtector _secretProtector;
    private readonly QuickBooksOnlineOAuthOptions _options;

    public QuickBooksOnlineOAuthService(
        DocFlowDbContext dbContext,
        IAccountingPostingTargetResolver targetResolver,
        IQuickBooksOnlineTokenClient tokenClient,
        ISecretProtector secretProtector,
        QuickBooksOnlineOAuthOptions options)
    {
        _dbContext = dbContext;
        _targetResolver = targetResolver;
        _tokenClient = tokenClient;
        _secretProtector = secretProtector;
        _options = options;
    }

    public async Task<QuickBooksOnlineAuthorizationStart> BeginAuthorizationAsync(
        Guid customerId,
        string targetKey,
        CancellationToken cancellationToken = default)
    {
        if (!_options.Enabled)
        {
            throw new InvalidOperationException(
                "QuickBooks Online OAuth is not enabled.");
        }

        var target = ResolveQuickBooksTarget(customerId, targetKey);
        var now = DateTimeOffset.UtcNow;

        await _dbContext.QuickBooksOnlineOAuthStates
            .Where(item =>
                item.ExpiresAt <= now
                || (item.ConsumedAt != null
                    && item.ConsumedAt <= now.AddHours(-1)))
            .ExecuteDeleteAsync(cancellationToken);

        var expiresAt = now.AddMinutes(_options.StateLifetimeMinutes);

        var state = GenerateState();
        var stateHash = HashState(state);

        _dbContext.QuickBooksOnlineOAuthStates.Add(
            new QuickBooksOnlineOAuthState(
                customerId,
                target.Key,
                stateHash,
                now,
                expiresAt));

        await _dbContext.SaveChangesAsync(cancellationToken);

        var authorizationUrl = BuildAuthorizationUrl(state);

        return new QuickBooksOnlineAuthorizationStart(
            authorizationUrl,
            expiresAt);
    }

    public async Task<QuickBooksOnlineConnectionSnapshot?> CompleteAuthorizationAsync(
        string authorizationCode,
        string state,
        string realmId,
        CancellationToken cancellationToken = default)
    {
        if (!_options.Enabled)
            return null;

        if (string.IsNullOrWhiteSpace(authorizationCode)
            || string.IsNullOrWhiteSpace(state)
            || string.IsNullOrWhiteSpace(realmId))
        {
            return null;
        }

        var now = DateTimeOffset.UtcNow;
        var stateHash = HashState(state);

        var oauthState = await _dbContext.QuickBooksOnlineOAuthStates
            .AsNoTracking()
            .SingleOrDefaultAsync(
                item => item.StateHash == stateHash,
                cancellationToken);

        if (oauthState is null
            || oauthState.ConsumedAt is not null
            || oauthState.ExpiresAt <= now)
        {
            return null;
        }

        var target = ResolveQuickBooksTarget(
            oauthState.CustomerId,
            oauthState.TargetKey);

        if (!string.Equals(
                target.TargetAccount,
                realmId.Trim(),
                StringComparison.Ordinal))
        {
            return null;
        }

        var consumed = await _dbContext.QuickBooksOnlineOAuthStates
            .Where(item =>
                item.Id == oauthState.Id
                && item.ConsumedAt == null
                && item.ExpiresAt > now)
            .ExecuteUpdateAsync(
                setters => setters
                    .SetProperty(item => item.ConsumedAt, now),
                cancellationToken);

        if (consumed != 1)
            return null;

        var tokens = await _tokenClient.ExchangeAuthorizationCodeAsync(
            authorizationCode.Trim(),
            cancellationToken);

        var protectedAccessToken =
            _secretProtector.Protect(tokens.AccessToken);
        var protectedRefreshToken =
            _secretProtector.Protect(tokens.RefreshToken);

        var accessExpiresAt = now.AddSeconds(
            tokens.AccessTokenExpiresInSeconds);
        var refreshExpiresAt = now.AddSeconds(
            tokens.RefreshTokenExpiresInSeconds);

        var connection = await _dbContext.QuickBooksOnlineConnections
            .SingleOrDefaultAsync(
                item => item.CustomerId == oauthState.CustomerId
                    && item.TargetKey == oauthState.TargetKey,
                cancellationToken);

        if (connection is null)
        {
            connection = new QuickBooksOnlineConnection(
                oauthState.CustomerId,
                oauthState.TargetKey,
                realmId.Trim(),
                protectedAccessToken,
                accessExpiresAt,
                protectedRefreshToken,
                refreshExpiresAt,
                now);

            _dbContext.QuickBooksOnlineConnections.Add(connection);
        }
        else
        {
            connection.Reconnect(
                realmId.Trim(),
                protectedAccessToken,
                accessExpiresAt,
                protectedRefreshToken,
                refreshExpiresAt,
                now);
        }

        try
        {
            await _dbContext.SaveChangesAsync(cancellationToken);
        }
        catch (DbUpdateException exception)
            when (exception.InnerException is PostgresException
            {
                SqlState: PostgresErrorCodes.UniqueViolation,
                ConstraintName:
                    "UX_QuickBooksOnlineConnections_TenantTarget"
            })
        {
            _dbContext.Entry(connection).State = EntityState.Detached;

            connection = await _dbContext.QuickBooksOnlineConnections
                .SingleAsync(
                    item => item.CustomerId == oauthState.CustomerId
                        && item.TargetKey == oauthState.TargetKey,
                    cancellationToken);

            connection.Reconnect(
                realmId.Trim(),
                protectedAccessToken,
                accessExpiresAt,
                protectedRefreshToken,
                refreshExpiresAt,
                now);

            await _dbContext.SaveChangesAsync(cancellationToken);
        }

        return ToSnapshot(connection);
    }

    public async Task<QuickBooksOnlineConnectionSnapshot?> GetConnectionAsync(
        Guid customerId,
        string targetKey,
        CancellationToken cancellationToken = default)
    {
        var connection = await _dbContext.QuickBooksOnlineConnections
            .AsNoTracking()
            .SingleOrDefaultAsync(
                item => item.CustomerId == customerId
                    && item.TargetKey == targetKey.Trim(),
                cancellationToken);

        return connection is null
            ? null
            : ToSnapshot(connection);
    }

    private AccountingPostingTarget ResolveQuickBooksTarget(
        Guid customerId,
        string targetKey)
    {
        var target = _targetResolver.Resolve(customerId, targetKey)
            ?? throw new InvalidOperationException(
                "Accounting target was not found for this tenant.");

        if (!string.Equals(
                target.Provider,
                QuickBooksOnlineAccountingAdapter.ProviderName,
                StringComparison.OrdinalIgnoreCase))
        {
            throw new InvalidOperationException(
                "Accounting target is not configured for QuickBooks Online.");
        }

        return target;
    }

    private string BuildAuthorizationUrl(string state)
    {
        static string Escape(string value) =>
            Uri.EscapeDataString(value);

        return _options.AuthorizationUrl
            + "?client_id=" + Escape(_options.ClientId)
            + "&redirect_uri=" + Escape(_options.RedirectUri)
            + "&response_type=code"
            + "&scope=" + Escape(_options.Scope)
            + "&state=" + Escape(state);
    }

    private static string GenerateState()
    {
        Span<byte> bytes = stackalloc byte[32];
        RandomNumberGenerator.Fill(bytes);

        return Convert.ToBase64String(bytes)
            .TrimEnd('=')
            .Replace('+', '-')
            .Replace('/', '_');
    }

    private static string HashState(string state)
    {
        var bytes = SHA256.HashData(
            Encoding.UTF8.GetBytes(state.Trim()));
        return Convert.ToHexString(bytes);
    }

    private static QuickBooksOnlineConnectionSnapshot ToSnapshot(
        QuickBooksOnlineConnection connection)
        => new(
            connection.CustomerId,
            connection.TargetKey,
            connection.RealmId,
            connection.AccessTokenExpiresAt,
            connection.RefreshTokenExpiresAt,
            connection.ConnectedAt,
            connection.UpdatedAt,
            connection.DisconnectedAt is null);
}
