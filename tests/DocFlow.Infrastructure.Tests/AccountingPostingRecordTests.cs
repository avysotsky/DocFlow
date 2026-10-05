using DocFlow.Domain.Entities;
using DocFlow.Domain.Enums;
using Xunit;

namespace DocFlow.Infrastructure.Tests;

public sealed class AccountingPostingRecordTests
{
    [Fact]
    public void PostingLifecycle_CompletesWithExternalReference()
    {
        var record = CreateRecord();
        var startedAt = new DateTimeOffset(
            2026, 10, 5, 18, 30, 0, TimeSpan.Zero);
        var completedAt = startedAt.AddSeconds(2);

        record.MarkAttemptStarted(startedAt);
        record.MarkPosted(completedAt, "qb-bill-123");

        Assert.Equal(AccountingPostingStatus.Posted, record.Status);
        Assert.Equal(1, record.Attempts);
        Assert.Equal(startedAt, record.LastAttemptAt);
        Assert.Equal("qb-bill-123", record.ExternalReference);
        Assert.Null(record.NextAttemptAt);
        Assert.Null(record.LastError);
    }

    [Fact]
    public void RetryableFailure_ReturnsToPendingWithExponentialDelay()
    {
        var record = CreateRecord();
        var firstAttempt = new DateTimeOffset(
            2026, 10, 5, 18, 30, 0, TimeSpan.Zero);

        record.MarkAttemptStarted(firstAttempt);
        record.MarkAttemptFailed(
            firstAttempt.AddSeconds(1),
            "provider unavailable",
            maxAttempts: 3,
            baseRetryDelaySeconds: 10,
            maxRetryDelaySeconds: 60);

        Assert.Equal(AccountingPostingStatus.Pending, record.Status);
        Assert.Equal(1, record.Attempts);
        Assert.Equal(firstAttempt.AddSeconds(11), record.NextAttemptAt);

        var secondAttempt = firstAttempt.AddSeconds(11);
        record.MarkAttemptStarted(secondAttempt);
        record.MarkAttemptFailed(
            secondAttempt.AddSeconds(1),
            "provider still unavailable",
            maxAttempts: 3,
            baseRetryDelaySeconds: 10,
            maxRetryDelaySeconds: 60);

        Assert.Equal(AccountingPostingStatus.Pending, record.Status);
        Assert.Equal(2, record.Attempts);
        Assert.Equal(secondAttempt.AddSeconds(21), record.NextAttemptAt);
    }

    [Fact]
    public void FinalFailure_BecomesTerminal()
    {
        var record = CreateRecord();
        var now = DateTimeOffset.UtcNow;

        for (var attempt = 0; attempt < 3; attempt++)
        {
            record.MarkAttemptStarted(now.AddMinutes(attempt));
            record.MarkAttemptFailed(
                now.AddMinutes(attempt).AddSeconds(1),
                "permanent provider rejection",
                maxAttempts: 3,
                baseRetryDelaySeconds: 1,
                maxRetryDelaySeconds: 10);
        }

        Assert.Equal(AccountingPostingStatus.Failed, record.Status);
        Assert.Equal(3, record.Attempts);
        Assert.Null(record.NextAttemptAt);
        Assert.Equal("permanent provider rejection", record.LastError);

        Assert.Throws<InvalidOperationException>(
            () => record.MarkAttemptStarted(now.AddHours(1)));
    }

    [Fact]
    public void PostedRecord_CannotBeRetried()
    {
        var record = CreateRecord();
        var now = DateTimeOffset.UtcNow;

        record.MarkAttemptStarted(now);
        record.MarkPosted(now.AddSeconds(1), "xero-bill-42");

        Assert.Throws<InvalidOperationException>(
            () => record.MarkAttemptStarted(now.AddMinutes(1)));
    }

    private static AccountingPostingRecord CreateRecord()
    {
        return new AccountingPostingRecord(
            Guid.NewGuid(),
            Guid.NewGuid(),
            "fake-accounting",
            "tenant-ledger",
            "posting-key-1",
            "{"document_type":"supplier_invoice"}");
    }
}
