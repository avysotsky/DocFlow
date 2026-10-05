using DocFlow.Domain.Entities;
using Xunit;

namespace DocFlow.Infrastructure.Tests;

public sealed class ImapMailboxCheckpointTests
{
    [Fact]
    public void Advance_IsMonotonicWithinSameUidValidity()
    {
        var checkpoint = new ImapMailboxCheckpoint(
            Guid.NewGuid(),
            "ap-mailbox",
            "INBOX",
            100);

        checkpoint.Advance(100, 7);
        checkpoint.Advance(100, 9);

        Assert.Equal(100, checkpoint.UidValidity);
        Assert.Equal(9, checkpoint.LastUid);

        Assert.Throws<InvalidOperationException>(
            () => checkpoint.Advance(100, 8));
    }

    [Fact]
    public void Reset_ChangesUidValidityAndStartsCursorFromZero()
    {
        var checkpoint = new ImapMailboxCheckpoint(
            Guid.NewGuid(),
            "ap-mailbox",
            "INBOX",
            100);

        checkpoint.Advance(100, 42);
        checkpoint.Reset(200);

        Assert.Equal(200, checkpoint.UidValidity);
        Assert.Equal(0, checkpoint.LastUid);

        checkpoint.Advance(200, 1);
        Assert.Equal(1, checkpoint.LastUid);
    }

    [Fact]
    public void Advance_RejectsStaleUidValidity()
    {
        var checkpoint = new ImapMailboxCheckpoint(
            Guid.NewGuid(),
            "ap-mailbox",
            "INBOX",
            100);

        Assert.Throws<InvalidOperationException>(
            () => checkpoint.Advance(101, 1));
    }
}
