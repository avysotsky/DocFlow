# DocFlow — handoff v1.1.1.13 Processing Retries

Status: **ACTIVE**  
Repository: `avysotsky/DocFlow`  
Branch: `DocFlow/v_1.1.1.13_ProcessingRetries`  
Base: `DocFlow/v_1.1.1.12_Deployability`

## Why this milestone exists

The deployable MVP currently processes documents through an in-memory background queue. A technical extraction failure is logged and the document is immediately marked `Failed`. There is no bounded automatic retry policy and no persisted processing-attempt diagnostics.

## Scope

Keep `v1.1.1.13` narrow:

1. Add configurable bounded retries for one dequeued document job.
2. Persist processing attempt count and timestamps on `Document`.
3. Persist a bounded last technical failure summary for operational diagnosis.
4. Keep the final document state `Failed` only after retry attempts are exhausted.
5. Expose safe processing diagnostics on the tenant-scoped document read API.
6. Extend Automation E2E so the synthetic technical-failure scenario proves the configured retry count and persisted failure diagnostics.
7. Preserve existing idempotency and successful document behavior.

## Non-goals

Do not add in this milestone:

- RabbitMQ/Kafka or another durable broker;
- distributed retry scheduling;
- OpenTelemetry/Prometheus/Grafana;
- dead-letter infrastructure;
- reviewer identity;
- retention/delete;
- extraction/OCR rule changes;
- ONNX/LLM fallback.

## Acceptance criteria

The milestone is complete when CI proves:

```text
normal documents still process once successfully
repeated enqueue remains idempotent
technical failure is attempted a bounded configured number of times
final technical failure -> Failed
processing attempt count is persisted
last attempt/failure timestamps are persisted
bounded failure summary is persisted and returned by GET /api/documents/{id}
Automation E2E remains green
.NET build remains green
```

No Public Reference Benchmark or Scanned OCR E2E should run because extraction/OCR behavior is unchanged.
