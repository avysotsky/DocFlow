namespace DocFlow.Application.Observability;

public sealed class OperationalMetrics
{
    private readonly DateTimeOffset _startedAt = DateTimeOffset.UtcNow;

    private long _pendingQueueDepth;
    private long _processingCompleted;
    private long _processingNeedsReview;
    private long _processingFailed;
    private long _processingRetries;
    private long _reviewsCompleted;
    private long _retentionDeleted;
    private long _retentionFailures;

    public void RecordQueueEnqueued() => Interlocked.Increment(ref _pendingQueueDepth);

    public void RecordQueueDequeued()
    {
        while (true)
        {
            var current = Interlocked.Read(ref _pendingQueueDepth);
            if (current <= 0)
                return;

            if (Interlocked.CompareExchange(ref _pendingQueueDepth, current - 1, current) == current)
                return;
        }
    }

    public void RecordProcessingCompleted() => Interlocked.Increment(ref _processingCompleted);
    public void RecordProcessingNeedsReview() => Interlocked.Increment(ref _processingNeedsReview);
    public void RecordProcessingFailed() => Interlocked.Increment(ref _processingFailed);
    public void RecordProcessingRetry() => Interlocked.Increment(ref _processingRetries);
    public void RecordReviewCompleted() => Interlocked.Increment(ref _reviewsCompleted);
    public void RecordRetentionDeleted() => Interlocked.Increment(ref _retentionDeleted);
    public void RecordRetentionFailure() => Interlocked.Increment(ref _retentionFailures);

    public OperationalMetricsSnapshot Snapshot()
    {
        var now = DateTimeOffset.UtcNow;
        var uptimeSeconds = Math.Max(0L, (long)(now - _startedAt).TotalSeconds);

        return new OperationalMetricsSnapshot(
            _startedAt,
            uptimeSeconds,
            Math.Max(0L, Interlocked.Read(ref _pendingQueueDepth)),
            Interlocked.Read(ref _processingCompleted),
            Interlocked.Read(ref _processingNeedsReview),
            Interlocked.Read(ref _processingFailed),
            Interlocked.Read(ref _processingRetries),
            Interlocked.Read(ref _reviewsCompleted),
            Interlocked.Read(ref _retentionDeleted),
            Interlocked.Read(ref _retentionFailures));
    }
}

public sealed record OperationalMetricsSnapshot(
    DateTimeOffset StartedAt,
    long UptimeSeconds,
    long PendingQueueDepth,
    long ProcessingCompleted,
    long ProcessingNeedsReview,
    long ProcessingFailed,
    long ProcessingRetries,
    long ReviewsCompleted,
    long RetentionDeleted,
    long RetentionFailures);
