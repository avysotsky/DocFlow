# DocFlow — handoff v1.1.1.14 Restart Recovery

Status: **ACTIVE**  
Repository: `avysotsky/DocFlow`  
Branch: `DocFlow/v_1.1.1.14_RestartRecovery`  
Base: `DocFlow/v_1.1.1.13_ProcessingRetries`

## Why this milestone exists

DocFlow now has bounded in-process retries and persisted processing diagnostics, but the processing queue is still an in-memory `Channel<Guid>`. A host restart can therefore lose queued work or leave a document in `Processing` after the worker process disappears.

## Scope

Keep `v1.1.1.14` narrow:

1. Add startup reconciliation before the main processing worker starts.
2. Re-enqueue persisted `Uploaded` documents that have no extraction result.
3. Re-enqueue stale `Processing` documents that have no extraction result.
4. Make the stale-processing threshold configurable and validated at startup.
5. Reuse the existing in-memory queue, bounded retry behavior, processing diagnostics and extraction-result idempotency.
6. Extend Automation E2E with a deterministic restart-recovery scenario.
7. Keep the implementation single-instance; do not imply distributed leasing/locking semantics.

## Non-goals

Do not add in this milestone:

- RabbitMQ/Kafka or another external broker;
- distributed locks, leases or multi-instance workers;
- recurring scheduler/poller;
- dead-letter infrastructure;
- reviewer identity;
- retention/delete;
- extraction/OCR changes;
- ONNX/LLM fallback.

## Acceptance criteria

The milestone is complete when CI proves:

```text
startup reconciler runs before the normal queue consumer
Uploaded document without extraction result is recovered after restart
stale Processing document without extraction result is recovered after restart
fresh Processing document is not recovered
existing Processed/NeedsReview documents are not reprocessed
recovered jobs reuse existing bounded retries/idempotency
Automation E2E remains green
.NET build remains green
```

No Deployment Smoke, Scanned OCR E2E or Public Reference Benchmark should run unless their specific path filters are touched.