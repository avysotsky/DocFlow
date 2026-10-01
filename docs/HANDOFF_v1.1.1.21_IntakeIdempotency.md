# DocFlow — handoff v1.1.1.21 Intake Idempotency

Status: **COMPLETED**  
Repository: `avysotsky/DocFlow`  
Branch: `DocFlow/v_1.1.1.21_IntakeIdempotency`  
Base: `DocFlow/v_1.1.1.20_BatchIntake`

## 1. Milestone result

Single-document intake now supports persisted tenant-scoped HTTP idempotency through an optional `Idempotency-Key` header.

Implementation commits:

```text
ea7d0be3466982ecf2b838d62dcf89d7c8e736ad
Add persisted single-upload idempotency

9cce3e67f1c87d52b4ce348b12081f684ebb93f9
Align document timestamps with PostgreSQL precision
```

The second commit is the authoritative code state.

Final validation:

```text
.NET CI #36
run id: 36900028572
result: success

Automation E2E #112
run id: 36900028254
result: success
```

An earlier Automation E2E #111 run failed only because the first in-memory upload response contained a 100-ns `DateTimeOffset` fraction while PostgreSQL persisted/replayed timestamps at microsecond precision. The implementation was corrected by normalizing new document `CreatedAt`/`DeleteAt` values to PostgreSQL precision before the first response. The test was not weakened.

## 2. API contract

Idempotency is optional and applies only to:

```text
POST /api/documents
Idempotency-Key: <1..128 chars>
```

No header preserves the pre-existing single-upload behavior.

Batch intake is unchanged and does not interpret `Idempotency-Key` in this milestone.

## 3. Persisted model

New table:

```text
IntakeIdempotencyRecords
```

Primary key:

```text
(CustomerId, Key)
```

Persisted fields include:

```text
request fingerprint
accepted/rejected outcome
response snapshot fields
timestamps
expiry
```

The record deliberately has **no foreign key to Document**. A document can be deleted by the customer or retention policy while the old idempotency key remains protected until expiry.

Migration:

```text
20261001172000_AddIntakeIdempotencyRecords
```

## 4. Request identity and concurrency

The request fingerprint is SHA-256 over a version marker plus filename, content type, length and the complete uploaded bytes. It identifies an HTTP intake request; it is not semantic document deduplication.

Concurrent same-tenant/same-key requests are serialized with a PostgreSQL transaction advisory lock derived from tenant + key. The database composite primary key remains the persisted uniqueness boundary.

The lock is acquired before storage upload. Therefore the losing concurrent request waits for the first transaction and replays its result rather than creating a second stored PDF/document.

## 5. Replay/conflict semantics

Within the configured retention window:

```text
same tenant + same key + same fingerprint
  -> original Accepted/Rejected result is replayed
  -> no duplicate document/storage object
  -> Idempotency-Replayed: true

same tenant + same key + different fingerprint
  -> 409 Conflict

same key + different tenant
  -> independent namespace
```

Validation rejections are deterministic completed outcomes and are persisted/replayed.

Storage/database infrastructure failures are not recorded as successful completed idempotency outcomes, so clients may retry them.

## 6. Expiry

Default configuration:

```json
{
  "Intake": {
    "Idempotency": {
      "RetentionHours": 24
    }
  }
}
```

Startup validation allows 1..720 hours.

After expiry, reuse of the same tenant/key replaces the expired record in-place with the new request/outcome.

Important: expired records are logically reusable but are not yet periodically deleted. Unique one-off keys can therefore accumulate in the table. This is the recommended next operational gap.

## 7. Timestamp precision correction

PostgreSQL `timestamp with time zone` persists microsecond precision while .NET `DateTimeOffset` can represent 100-ns ticks. New `Document.CreatedAt` and constructor-provided `DeleteAt` values are now truncated to PostgreSQL timestamp precision at creation time.

This keeps first-write API responses stable across persistence/replay and avoids observable sub-microsecond drift.

## 8. E2E coverage

Automation E2E #112 proves:

```text
same request/key -> same response/document id
replay header -> true only on replay
different payload/key reuse -> 409
same key across tenants -> independent accepted documents
Rejected outcome -> replayed
2 concurrent same-key uploads -> one document id, one replay
original document deletion -> idempotency replay still returns original snapshot
batch intake remains unchanged
restart/review/retention regression remains green
```

## 9. Scope boundary

Still intentionally deferred:

- batch request idempotency;
- semantic/content deduplication;
- Redis/external lock infrastructure;
- distributed queue/leases;
- human IAM;
- external tracing/metrics aggregation.

## 10. Recommended next milestone

Strong next milestone: `v1.1.1.22_IdempotencyCleanup`.

Add bounded cleanup of expired `IntakeIdempotencyRecords` so unique one-off keys do not grow the table indefinitely. Reuse the current single-instance operational model; do not add a distributed scheduler solely for cleanup.
