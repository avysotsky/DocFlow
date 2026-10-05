using DocFlow.Domain.Entities;
using Xunit;

namespace DocFlow.Infrastructure.Tests;

public sealed class MailboxMessageRecordTests
{
    [Fact]
    public void Constructor_NormalizesReceivedAtToUtcForPostgreSql()
    {
        var localReceivedAt = new DateTimeOffset(
            2026,
            10,
            5,
            14,
            0,
            0,
            TimeSpan.FromHours(3));

        var message = new MailboxMessageRecord(
            Guid.NewGuid(),
            "message-id:test@example.com",
            new string('a', 64),
            "test@example.com",
            "billing@example.com",
            "Invoice",
            localReceivedAt);

        Assert.Equal(TimeSpan.Zero, message.ReceivedAt!.Value.Offset);
        Assert.Equal(
            new DateTimeOffset(2026, 10, 5, 11, 0, 0, TimeSpan.Zero),
            message.ReceivedAt.Value);
    }
}
