# DocFlow — Next Chat Handoff After v1.1.1.22

Use this file as the starting state for the next DocFlow development chat.

## Repository state

Repository: `avysotsky/DocFlow`  
Completed branch: `DocFlow/v_1.1.1.22_IdempotencyCleanup`  
Previous branch: `DocFlow/v_1.1.1.21_IntakeIdempotency`

Authoritative implementation commit:

```text
4a5d16cdd431fb6470df6ed2de9171b84aa876b7
Add bounded idempotency record cleanup
```

Final validation:

```text
.NET CI #37 -> success (run 36901767125)
Automation E2E #113 -> success (run 36901767040)
```

Detailed handoff:

```text
docs/HANDOFF_v1.1.1.22_IdempotencyCleanup.md
```

## Current product state

DocFlow now supports:

```text
API-key authenticated tenant/client
  -> single PDF upload with persisted optional Idempotency-Key
  -> physical cleanup of expired idempotency records
  -> bounded multi-PDF partial-success batch intake
  -> shared validation/storage/persistence intake service
  -> PostgreSQL-backed startup recovery
  -> in-memory single-reader processing queue
  -> bounded technical retries + persisted diagnostics
  -> digital PDF / conditional Tesseract OCR
  -> invoice/quotation detection and deterministic extraction
  -> arithmetic/business validation
  -> PostgreSQL persistence
  -> tenant-scoped inbox
  -> original PDF streaming
  -> review/correction + authenticated API-client attribution
  -> CSV/XLSX export
  -> explicit terminal deletion
  -> optional document retention cleanup
  -> protected process-local operational metrics
```

Production container deployment, health/readiness checks and opt-in migrations remain in place.

Extraction/OCR baseline remains unchanged:

```text
17/17 public documents passed
98/98 checked business fields matched
17/17 document types correct
17/17 validation statuses correct
69 Python regression tests
```

No extraction/OCR behavior changed in `v1.1.1.22`.

## Single-upload idempotency state

Header:

```text
POST /api/documents
Idempotency-Key: <1..128 chars>
```

Persisted key namespace:

```text
(CustomerId, Key)
```

Behavior while unexpired:

```text
same key + same request -> replay original Accepted/Rejected result
same key + different request -> 409 Conflict
same key in another tenant -> independent namespace
concurrent same tenant/key -> PostgreSQL advisory lock serializes intake
replay header -> Idempotency-Replayed: true
```

Infrastructure failures are not recorded as completed outcomes.

The idempotency table intentionally has no FK to `Documents`, so document deletion does not immediately release the key.

## Idempotency expiry and cleanup

Configuration:

```json
{
  "Intake": {
    "Idempotency": {
      "RetentionHours": 24,
      "CleanupIntervalSeconds": 3600,
      "CleanupBatchSize": 500
    }
  }
}
```

`IntakeIdempotencyCleanupHostedService` physically removes expired rows in bounded sweeps.

For every candidate it acquires the same transaction advisory lock scope as intake and then re-checks `ExpiresAt <= cutoff` before deleting. This preserves correctness when cleanup races a reused expired key.

E2E #113 proved two expired records were drained across multiple sweeps with `CleanupBatchSize=1` while an unexpired record remained.

## Batch intake boundary

Endpoint:

```text
POST /api/documents/batch
multipart field: Files
```

Limits:

```text
max files: 10
max individual file: 20 MB
max aggregate file bytes: 50 MB
transport request ceiling: 60 MB
```

Batch processing is sequential and partial-success. Each item independently returns `Accepted`, `Rejected`, or `Failed` and preserves input order.

Batch intake currently does **not** have request-level idempotency.

This is now the strongest adjacent reliability gap, but it requires a separate contract rather than copying single-upload behavior.

## Recommended next milestone

Candidate: `v1.1.1.23_BatchIdempotency`.

Inspect before implementing:

```text
src/DocFlow.Api/Controllers/DocumentsController.cs
src/DocFlow.Api/Documents/DocumentIntakeService.cs
src/DocFlow.Domain/Entities/IntakeIdempotencyRecord.cs
src/DocFlow.Infrastructure/Persistence/DocFlowDbContext.cs
.github/scripts/verify_document_inbox.py
.github/workflows/automation-e2e.yml
```

First define semantics for a request that contains mixed outcomes.

Questions the implementation must answer deterministically:

```text
What is the batch request fingerprint?
Is the idempotency unit the whole ordered request or individual files?
How are accepted/rejected item results persisted for replay?
If one item has a retryable infrastructure failure, is the whole batch record considered incomplete and retryable?
Can a retry safely avoid duplicating items that were already accepted before the failure?
What status code and response snapshot are replayed?
How is same-key/different-batch conflict represented?
```

Preferred direction for inspection:

```text
request-level batch key
+ ordered request fingerprint
+ persisted item outcome snapshot
+ do not mark batch complete while any item has retryable infrastructure failure
+ reuse existing per-file intake semantics where possible
```

Do not choose this shape blindly; inspect the current batch controller and persistence boundaries first.

## Reliability boundary

DocFlow remains intentionally single-instance operationally except for PostgreSQL transaction-level correctness mechanisms:

```text
PostgreSQL persisted state
+ startup reconciliation
+ in-memory Channel<Guid>
+ bounded retries
+ periodic document retention
+ periodic idempotency cleanup
+ row locking for document delete
+ tenant/key advisory locks for intake/cleanup
+ process-local metrics
```

Do not add RabbitMQ/Kafka/Redis/distributed schedulers merely for architectural appearance. Add distributed ownership only when multiple active instances become a real requirement.

## CI discipline

Continue sparse CI:

- docs/intermediate work -> `[skip ci]`;
- coherent API/Application/Domain/Infrastructure changes -> `.NET CI` + Automation E2E;
- Deployment Smoke only for Docker/compose/health/deployment contract changes;
- Scanned OCR E2E only for OCR/extraction-runner changes;
- Public Reference Benchmark only for extraction-rule changes.
