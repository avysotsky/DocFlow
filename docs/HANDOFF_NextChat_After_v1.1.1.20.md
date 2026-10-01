# DocFlow — Next Chat Handoff After v1.1.1.20

Use this file as the starting state for the next DocFlow development chat.

## Repository state

Repository: `avysotsky/DocFlow`  
Completed branch: `DocFlow/v_1.1.1.20_BatchIntake`  
Previous branch: `DocFlow/v_1.1.1.19_OperationalMetrics`

Main validating implementation commit:

```text
6cdf27cb0bd5d664291493fdf0d7d235992b3c08
Complete bounded batch intake implementation
```

Validation:

```text
.NET CI #34 -> success (run 36889076653)
Automation E2E #110 -> success (run 36889076198)
```

Only those two relevant workflows ran. Deployment Smoke, Scanned OCR E2E and Public Reference Benchmark were not triggered.

Detailed handoff:

```text
docs/HANDOFF_v1.1.1.20_BatchIntake.md
```

## Current product state

DocFlow now supports:

```text
API-key authenticated tenant/client
  -> single PDF upload OR bounded multi-PDF batch intake
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
  -> authenticated API-client audit attribution on new reviews
  -> CSV/XLSX export
  -> tenant-scoped terminal document deletion
  -> optional automatic retention cleanup
  -> opt-in protected process-local operational metrics
```

Production container deployment, health/readiness checks and opt-in migrations remain in place.

Public-reference extraction baseline remains unchanged:

```text
17/17 public documents passed
98/98 checked business fields matched
17/17 document types correct
17/17 validation statuses correct
69 Python regression tests
```

No extraction/OCR behavior changed in `v1.1.1.20`.

## Intake state

Shared scoped service:

```text
DocFlow.Api.Documents.DocumentIntakeService
```

Both endpoints use it:

```text
POST /api/documents
POST /api/documents/batch
```

Per-file validation:

```text
non-empty
<=20 MB
.pdf
application/pdf
%PDF- signature
```

Batch contract:

```text
multipart field: Files
maximum 10 files
maximum 50 MB aggregate file bytes
60 MB endpoint-only transport ceiling for multipart overhead
sequential independent intake
```

Batch-level count/aggregate limits are checked before any item is persisted.

Per-file outcomes:

```text
Accepted -> durable Document exists and is normally enqueued
Rejected -> validation failure, no document created
Failed   -> sanitized storage/database intake failure for that item
```

A failed database save detaches the failed Added entity before later batch files are processed, preventing EF tracking contamination across items.

Automation E2E #110 proves empty/too-many rejection plus a mixed valid+invalid batch, downstream processing to `Processed`, owner access and cross-tenant `404`.

## Existing operational boundaries

Processing/retention/metrics remain intentionally single-instance:

```text
PostgreSQL persisted state
+ startup recovery
+ in-memory Channel<Guid>
+ bounded retries
+ single periodic retention sweep
+ row locking for terminal delete
+ extraction-result idempotency
+ per-process operational counters
```

Do not add distributed queue/leases/scheduler solely for architecture aesthetics.

Review attribution remains client identity, not human IAM:

```text
ReviewedByClient == authenticated API client/integration identity
ReviewedByClient != guaranteed human reviewer identity
```

## CI discipline

Continue sparse CI:

- docs/intermediate maintenance -> `[skip ci]`;
- coherent API/Application/Infrastructure changes -> `.NET CI` + Automation E2E;
- Deployment Smoke only for Docker/compose/health/deployment-contract changes;
- Scanned OCR E2E only for OCR/extraction-runner/fixture changes;
- Public Reference Benchmark only for extraction-rule changes.

## Recommended next milestone

Create `v1.1.1.21` only after inspecting retry semantics around HTTP intake.

Strong candidate: **Intake Idempotency**.

Why now:

- single and batch intake create new durable document ids on every successful POST;
- a real client may retry after a network timeout without knowing whether the first request committed;
- batch retry can multiply duplicates more severely than single upload;
- extraction-result idempotency does not prevent duplicate `Document` rows/files from repeated intake requests.

Inspect before implementation:

- whether one `Idempotency-Key` should identify the whole HTTP request, each file, or both;
- how keys are tenant-scoped;
- how long persisted idempotency records should live;
- request fingerprinting needed to detect key reuse with different payload metadata;
- replay response behavior for completed original requests;
- concurrency handling for two simultaneous requests with the same key;
- interaction with partial batch outcomes;
- whether storage upload must occur only after idempotency ownership is established.

Recommended narrow direction:

```text
single-upload request-level idempotency first
persist tenant + key + request fingerprint + resulting document id/outcome
same tenant/key/same request -> replay original result
same tenant/key/different request -> 409
concurrent same key -> one durable intake
```

Only extend the same design to batch in that milestone if partial-result replay remains simple and deterministic. Do not use file-content hash deduplication as a substitute for HTTP idempotency unless product requirements explicitly call for semantic duplicate detection.

Other later candidates: per-tenant retention policy, API versioning/deprecation for `StorageKey`, real human IAM if required, and external metrics/tracing when deployment requirements justify them.
