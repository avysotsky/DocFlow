# DocFlow — Next Chat Handoff After v1.1.1.13

Use this file as the starting state for the next DocFlow development chat.

## Repository state

Repository: `avysotsky/DocFlow`  
Completed branch: `DocFlow/v_1.1.1.13_ProcessingRetries`  
Previous branch: `DocFlow/v_1.1.1.12_Deployability`

Main implementation commit:

```text
c51ad25cdd34da98c4bc3446e05194fa9247958c
Add bounded processing retries and persisted diagnostics
```

Validation:

```text
.NET CI #26 -> success (run 36869555535)
Automation E2E #102 -> success (run 36869555594)
Deployment Smoke #2 -> success (run 36869555520)
Scanned OCR E2E #75 -> success (run 36869555532)
```

Deployment Smoke and Scanned OCR E2E were triggered unnecessarily by broad path filters. Their filters were narrowed in the closing `[skip ci]` maintenance commit. Do not interpret those extra runs as a new CI cadence.

Detailed milestone handoff:

```text
docs/HANDOFF_v1.1.1.13_ProcessingRetries.md
```

## Current product state

DocFlow currently supports:

```text
API-key authenticated tenant
  -> PDF upload
  -> in-memory processing queue
  -> bounded technical-failure retry
  -> digital PDF or conditional Tesseract OCR
  -> invoice/quotation detection and deterministic extraction
  -> arithmetic/business validation
  -> PostgreSQL persistence
  -> tenant-scoped inbox
  -> human review/correction
  -> CSV/XLSX export
```

Production container deployment, health/readiness checks and opt-in migrations remain in place.

Public-reference extraction baseline is unchanged:

```text
17/17 public documents passed
98/98 checked business fields matched
17/17 document types correct
17/17 validation statuses correct
```

No extraction/OCR behavior changed in `v1.1.1.13`.

## Processing retry state

Default retry configuration:

```text
Processing:Retry:MaxAttempts = 3
Processing:Retry:RetryDelayMilliseconds = 250
```

Persisted document diagnostics:

```text
ProcessingAttempts
LastProcessingAttemptAt
LastProcessingFailureAt
LastProcessingError
```

Tenant-scoped diagnostics endpoint:

```text
GET /api/documents/{documentId}/processing-diagnostics
```

Final `Failed` status is written only after the configured attempts for a dequeued job are exhausted.

Important: the queue is still `DocumentProcessingQueue` backed by an in-memory `Channel<Guid>`. Retry is bounded and persisted diagnostics exist, but queued work is not durable across host restarts.

## CI discipline

Continue sparse CI:

- docs/intermediate maintenance -> `[skip ci]`;
- batch coherent code changes;
- `.NET CI` + Automation E2E for normal API/processing changes;
- Deployment Smoke only for actual container/deployment-contract changes;
- Scanned OCR E2E only for extraction/OCR runner/fixture changes;
- Public Reference Benchmark only for extraction-rule changes.

## Recommended next milestone

Create `v1.1.1.14` after inspecting the persisted document state transitions and startup/background-service behavior.

Strongest current gap: **restart recovery**.

A narrow commercial-MVP improvement is preferable to adding a broker immediately:

1. On startup discover persisted `Uploaded` documents without extraction results.
2. Recover stale `Processing` documents without extraction results after a configurable threshold.
3. Re-enqueue those ids into the existing single-reader in-memory queue.
4. Reuse existing idempotency/unique extraction-result protection.
5. Add a focused E2E proving work survives an API process restart.

Do not add RabbitMQ/Kafka, distributed locks/leasing, multi-instance workers, or a full scheduler unless the recovery implementation demonstrates that they are actually required.

Other later candidates remain reviewer/audit identity and retention/delete.
