# DocFlow — Next Chat Handoff After v1.1.1.21

Use this file as the starting state for the next DocFlow development chat.

## Repository state

Repository: `avysotsky/DocFlow`  
Completed branch: `DocFlow/v_1.1.1.21_IntakeIdempotency`  
Previous branch: `DocFlow/v_1.1.1.20_BatchIntake`

Authoritative implementation state:

```text
ea7d0be3466982ecf2b838d62dcf89d7c8e736ad
Add persisted single-upload idempotency

9cce3e67f1c87d52b4ce348b12081f684ebb93f9
Align document timestamps with PostgreSQL precision
```

Final validation:

```text
.NET CI #36 -> success (run 36900028572)
Automation E2E #112 -> success (run 36900028254)
```

An earlier Automation E2E #111 was diagnostic and failed because PostgreSQL normalized a first-response `DateTimeOffset` from 100-ns ticks to microsecond precision on replay. The code was corrected at the domain timestamp boundary; #36/#112 are the authoritative final checks.

Detailed handoff:

```text
docs/HANDOFF_v1.1.1.21_IntakeIdempotency.md
```

## Current product state

DocFlow now supports:

```text
API-key authenticated tenant/client
  -> single PDF upload with optional persisted Idempotency-Key
  -> bounded multi-PDF batch intake
  -> shared validation/storage/persistence intake service
  -> optional future DeleteAt assignment
  -> PostgreSQL-backed restart reconciliation
  -> in-memory single-reader processing queue
  -> bounded technical-failure retry
  -> persisted processing diagnostics
  -> digital PDF or conditional Tesseract OCR
  -> invoice/quotation detection and deterministic extraction
  -> arithmetic/business validation
  -> PostgreSQL persistence
  -> tenant-scoped inbox
  -> original PDF streaming/download
  -> review/correction
  -> authenticated API-client review attribution
  -> CSV/XLSX export
  -> terminal document deletion
  -> optional retention cleanup
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

No extraction/OCR behavior changed in `v1.1.1.21`.

## Single-upload idempotency state

Optional header:

```text
POST /api/documents
Idempotency-Key: <1..128 chars>
```

No header preserves old behavior.

Keys are scoped by authenticated `CustomerId`.

Persisted table:

```text
IntakeIdempotencyRecords
PK: (CustomerId, Key)
index: ExpiresAt
```

The table intentionally has no FK to `Documents`. Deleting a document does not immediately release its old idempotency key.

Request fingerprint:

```text
SHA-256(
  version marker
  + filename
  + content type
  + length
  + full uploaded bytes
)
```

This is request identity, not semantic/content deduplication.

Concurrency:

```text
PostgreSQL transaction advisory lock on tenant + key
+ composite primary key persisted uniqueness
```

Lock acquisition happens before storage upload.

Behavior while record is unexpired:

```text
same key + same fingerprint -> replay Accepted/Rejected result
replay response -> Idempotency-Replayed: true
same key + different fingerprint -> 409
same key in different tenant -> independent
```

Rejected validation outcomes are persisted/replayed. Storage/database failures remain retryable and are not stored as successful completed outcomes.

Default expiry:

```text
Intake:Idempotency:RetentionHours = 24
```

Allowed startup range: 1..720 hours.

After expiry, the same tenant/key can be reused and the old row is replaced in-place.

## Known remaining gap

Expiry is currently **logical**, not physical cleanup.

A reused expired key is replaced correctly, but an expired key that is never reused remains in `IntakeIdempotencyRecords`. High-volume unique idempotency keys can therefore grow the table indefinitely.

This is not an intake correctness bug, but it is the next narrow operational lifecycle gap.

## Timestamp precision state

New `Document.CreatedAt` and constructor-provided `DeleteAt` values are normalized to PostgreSQL microsecond precision at creation time.

Do not revert this merely because .NET supports finer 100-ns ticks; the database is the durability boundary and API first-response/replay fidelity depends on using the same effective precision.

## Batch boundary

`POST /api/documents/batch` remains bounded partial-success intake and does **not** currently use request-level idempotency.

Do not bolt single-upload semantics onto batch without designing partial-result replay carefully. A batch can contain accepted, rejected and failed files, and a robust replay model must define whether the persisted unit is the whole request or each item.

## Reliability boundary

DocFlow remains intentionally single-instance operationally:

```text
PostgreSQL persisted state
+ startup recovery
+ in-memory Channel<Guid>
+ bounded retries
+ periodic retention sweep
+ row locking for delete
+ tenant/key advisory locking for single-upload idempotency
+ per-process metrics
```

Do not add RabbitMQ/Kafka/Redis/distributed scheduler merely for architectural appearance. Add distributed ownership when multiple active instances become a real requirement.

## CI discipline

Continue sparse CI:

- docs/intermediate work -> `[skip ci]`;
- coherent API/Application/Domain/Infrastructure changes -> `.NET CI` + Automation E2E;
- Deployment Smoke only for Docker/compose/health/deployment contract changes;
- Scanned OCR E2E only for OCR/extraction-runner changes;
- Public Reference Benchmark only for extraction-rule changes.

## Recommended next milestone

Create `v1.1.1.22` after inspecting idempotency options and current hosted cleanup patterns.

Strong candidate: **Idempotency Cleanup**.

Recommended narrow shape:

```text
configurable cleanup interval
bounded delete batch
only ExpiresAt <= now
single-instance hosted service
no Document FK/cascade changes
no distributed scheduler
E2E inserts/creates expired + unexpired rows
expired rows removed
unexpired rows preserved
normal idempotency replay remains green
```

Consider reusing conventions from `DocumentRetentionHostedService`, but keep business-document retention and idempotency-record housekeeping as separate concepts.

Other later candidates: batch idempotency, per-tenant retention policy, API versioning/deprecation for `StorageKey`, real human IAM if required, and external telemetry only when deployment requirements justify it.
