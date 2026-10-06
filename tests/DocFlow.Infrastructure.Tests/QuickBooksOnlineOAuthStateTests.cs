using DocFlow.Domain.Entities;
using Xunit;

namespace DocFlow.Infrastructure.Tests;

public sealed class QuickBooksOnlineOAuthStateTests
{
    [Fact]
    public void OAuthState_IsOneTime()
    {
        var createdAt = new DateTimeOffset(
            2026, 10, 6, 10, 0, 0, TimeSpan.Zero);

        var state = new QuickBooksOnlineOAuthState(
            Guid.Parse("11111111-1111-1111-1111-111111111111"),
            "primary-ledger",
            new string('A', 64),
            createdAt,
            createdAt.AddMinutes(10));

        state.MarkConsumed(createdAt.AddMinutes(1));

        Assert.Equal(createdAt.AddMinutes(1), state.ConsumedAt);
        Assert.Throws<InvalidOperationException>(
            () => state.MarkConsumed(createdAt.AddMinutes(2)));
    }

    [Fact]
    public void OAuthState_RequiresFutureExpiry()
    {
        var now = DateTimeOffset.UtcNow;

        Assert.Throws<ArgumentOutOfRangeException>(
            () => new QuickBooksOnlineOAuthState(
                Guid.NewGuid(),
                "primary-ledger",
                new string('B', 64),
                now,
                now));
    }
}
