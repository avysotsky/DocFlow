# DocFlow — handoff v1.1.1.23 Batch Idempotency

Status: **COMPLETED**  
Repository: `avysotsky/DocFlow`  
Branch: `DocFlow/v_1.1.1.23_BatchIdempotency`  
Base: `DocFlow/v_1.1.1.22_IdempotencyCleanup`

## 1. Milestone result

Batch intake now supports persisted request-level idempotency without replacing the existing partial-success semantics.

Authoritative implementation commit:

```text
cdd41a13f862b586be4024ac4c8f7b078061cda7
Add persisted batch intake idempotency
```

Final validation:

```text
.NET CI #38
run id: 36906324232
result: success

Automation E2E #114
run id: 36906324346
result: success
```

No Deployment Smoke, Scanned OCR E2E or Public Reference Benchmark was required because deployment/OCR/extraction behavior did not change.

## 2. API contract

`POST /api/documents/batch` accepts the same optional external header used by single-document intake:

```text
Idempotency-Key: <1..128 chars>
```

Without the header, the previous bounded partial-success behavior is unchanged.

Caller-supplied keys beginning with the reserved prefix are rejected:

```text
docflow-internal:
```

This namespace is reserved for DocFlow's internal durable item checkpoints.

## 3. Whole-request identity

Batch idempotency is defined over the whole **ordered** request.

Fingerprint:

```text
SHA-256(
  version marker
  + file count
  + for each item in request order:
      index
      filename
      content type
      length
      full file bytes
)
```

Therefore reordering files under the same tenant/key is a different request and returns `409 Conflict`.

## 4. Persisted manifest

New table:

```text
BatchIntakeIdempotencyRecords
```

Primary key:

```text
(CustomerId, Key)
```

Persisted fields:

```text
RequestFingerprint
GenerationId
ResponseJson (nullable until the batch completes)
CreatedAt
ExpiresAt
```

There is no FK to `Documents`; deleting a document does not immediately release or mutate the batch request key.

Migration:

```text
20261001182000_AddBatchIntakeIdempotencyRecords
```

## 5. Durable per-item checkpoints

Each manifest generation derives deterministic internal per-item keys:

```text
docflow-internal:batch:<GenerationId>:<item-index>
```

Those keys are processed by the existing single-document persisted idempotency engine. This deliberately reuses the already tested storage upload, database persistence, rollback and advisory-lock path rather than creating a second document-intake implementation.

Per-item behavior:

```text
Accepted -> durable single-item checkpoint and document id
Rejected -> durable deterministic rejection checkpoint
Failed infrastructure outcome -> no completed item checkpoint, retry remains possible
```

The batch manifest is marked complete only when `FailedCount == 0`.

If the manifest is still incomplete, a retry with the same tenant/key and identical ordered payload reuses the same `GenerationId`, so already accepted/rejected items replay and unfinished failed items can execute again.

## 6. Replay/conflict/concurrency

Within the configured idempotency retention window:

```text
same tenant + same key + completed identical batch
  -> replay completed batch snapshot
  -> Idempotency-Replayed: true

same tenant + same key + incomplete identical batch
  -> reuse same GenerationId and item checkpoints

same tenant + same key + different ordered batch
  -> 409 Conflict

same key + different tenant
  -> independent namespace
```

Batch manifest operations use a PostgreSQL transaction advisory lock with a separate batch lock scope. Individual items use the existing single-item advisory lock scope.

Two concurrent identical batch requests therefore share one generation and the same deterministic item keys. The E2E concurrency test proved that both requests returned the same response/document id and only one accepted durable document was created.

## 7. Completion durability

Accepted/rejected item checkpoints commit independently while a batch is processed.

When all items finish without an infrastructure `Failed` outcome, DocFlow persists the completed batch response snapshot under the batch advisory lock.

If final manifest snapshot persistence itself fails after item checkpoints are durable, the API logs the error and returns the current result. A later retry reuses the same generation/item checkpoints and can persist the completed manifest without duplicating accepted documents.

## 8. Cleanup

`IntakeIdempotencyCleanupHostedService` now cleans both:

```text
IntakeIdempotencyRecords
BatchIntakeIdempotencyRecords
```

Each record type is bounded by the configured `CleanupBatchSize` per sweep.

Single records acquire the existing single-key advisory lock. Batch manifests acquire the batch-key advisory lock. Both re-check `ExpiresAt <= cutoff` after locking before deletion.

Automation E2E #114 seeded two expired + one unexpired batch manifests with cleanup batch size 1 and proved the expired manifests were drained across sweeps while the unexpired manifest remained.

## 9. Single-intake hardening included

The milestone centralized external idempotency-key validation and reserved-prefix handling in `IntakeIdempotencyKey`.

It also fixed a scoped-DbContext edge case in rejected single-item persistence: if saving a newly created rejected idempotency record fails, that Added entity is now detached so a subsequent item in the same batch cannot accidentally retry the broken tracked entity.

## 10. E2E coverage

Automation E2E #114 proves:

```text
existing no-key batch behavior remains green
single-upload idempotency remains green
expired single idempotency records are cleaned
expired batch manifests are cleaned
mixed Accepted + Rejected batch completes
same key/same ordered batch -> exact response replay
replay header -> true
replay creates no duplicate accepted document
same key/reordered batch -> 409
same key across tenants -> independent accepted document
reserved internal prefix -> 400
2 concurrent same-key batches -> same response/document id
2 concurrent same-key batches -> only one accepted durable document
restart/review/retention regression remains green
```

The implementation supports resuming retryable failed items through durable item checkpoints. The current E2E suite does not deliberately inject a storage/database failure mid-batch; do not claim a fault-injection test that does not exist.

## 11. Reliability boundary

DocFlow still intentionally uses the existing operational model:

```text
PostgreSQL persisted state
+ startup reconciliation
+ in-memory single-reader processing Channel<Guid>
+ bounded processing retries
+ document retention sweep
+ idempotency cleanup sweep
+ row locking for delete
+ PostgreSQL advisory locks for intake/idempotency
+ process-local metrics
```

Do not add RabbitMQ/Kafka/Redis/distributed schedulers merely for architecture aesthetics. Add distributed ownership only when multiple active instances become a real deployment requirement.

## 12. Recommended next milestone

Strong next candidate: `v1.1.1.24_PerTenantRetentionPolicy`.

Current document retention has one deployment-wide configuration:

```text
Retention.Enabled
Retention.DefaultRetentionDays
```

For a commercial multi-tenant product, different customers may require different retention periods or no automatic retention at all. Inspect authenticated API-client/customer configuration and the document creation boundary before deciding the narrowest tenant-policy representation.

Preserve these rules:

```text
default deployment behavior remains backward compatible
retention decision is derived from trusted tenant identity/config, never request payload
Uploaded/Processing documents are never auto-deleted
terminal-only sweep safety remains unchanged
no distributed scheduler
```
