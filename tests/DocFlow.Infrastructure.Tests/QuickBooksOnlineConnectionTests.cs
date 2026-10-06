using DocFlow.Domain.Entities;
using Xunit;

namespace DocFlow.Infrastructure.Tests;

public sealed class QuickBooksOnlineConnectionTests
{
    [Fact]
    public void RotateTokens_ReplacesBothTokensAndExpirations()
    {
        var now = new DateTimeOffset(
            2026, 10, 6, 10, 0, 0, TimeSpan.Zero);

        var connection = CreateConnection(now);

        connection.RotateTokens(
            "protected-access-2",
            now.AddHours(2),
            "protected-refresh-2",
            now.AddDays(90),
            now.AddMinutes(30));

        Assert.Equal("protected-access-2", connection.ProtectedAccessToken);
        Assert.Equal("protected-refresh-2", connection.ProtectedRefreshToken);
        Assert.Equal(now.AddHours(2), connection.AccessTokenExpiresAt);
        Assert.Equal(now.AddDays(90), connection.RefreshTokenExpiresAt);
        Assert.Null(connection.DisconnectedAt);
    }

    [Fact]
    public void Disconnect_AndReconnect_RestoresConnection()
    {
        var now = new DateTimeOffset(
            2026, 10, 6, 10, 0, 0, TimeSpan.Zero);

        var connection = CreateConnection(now);
        connection.Disconnect(now.AddHours(1));

        Assert.Equal(now.AddHours(1), connection.DisconnectedAt);

        connection.Reconnect(
            "realm-456",
            "protected-access-3",
            now.AddHours(3),
            "protected-refresh-3",
            now.AddDays(80),
            now.AddHours(2));

        Assert.Equal("realm-456", connection.RealmId);
        Assert.Equal("protected-access-3", connection.ProtectedAccessToken);
        Assert.Equal("protected-refresh-3", connection.ProtectedRefreshToken);
        Assert.Null(connection.DisconnectedAt);
        Assert.Equal(now.AddHours(2), connection.ConnectedAt);
    }

    private static QuickBooksOnlineConnection CreateConnection(
        DateTimeOffset now)
        => new(
            Guid.Parse("11111111-1111-1111-1111-111111111111"),
            "primary-ledger",
            "realm-123",
            "protected-access-1",
            now.AddHours(1),
            "protected-refresh-1",
            now.AddDays(100),
            now);
}
