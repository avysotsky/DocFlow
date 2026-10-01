# DocFlow — Next Chat Handoff After v1.1.1.18

Use this file as the starting state for the next DocFlow development chat.

## Repository state

Repository: `avysotsky/DocFlow`  
Completed branch: `DocFlow/v_1.1.1.18_ReviewAuditIdentity`  
Previous branch: `DocFlow/v_1.1.1.17_RetentionPolicy`

Main implementation commit:

```text
9a2795f2699c32097e1318b3d415166a19834c2e
Add authenticated client attribution to document reviews
```

Validation:

```text
.NET CI #31 -> success (run 36881312537)
Automation E2E #107 -> success (run 36881312573)
```

Only those two relevant workflows ran. Deployment Smoke, Scanned OCR E2E and Public Reference Benchmark were not triggered.

Detailed handoff:

```text
docs/HANDOFF_v1.1.1.18_ReviewAuditIdentity.md
```

## Current product state

DocFlow now supports:

```text
API-key authenticated tenant/client
  -> PDF upload
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
  -> optional automatic retention cleanup of expired terminal documents
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

No extraction/OCR behavior changed in `v1.1.1.18`.

## Review audit state

New reviews persist:

```text
ReviewedByClient
```

The value comes from trusted authenticated claim:

```text
docflow:client_name
```

The claim is produced by the API-key authentication handler from the configured API client name (customer id fallback).

Important semantics:

```text
ReviewedByClient == authenticated client/integration identity
ReviewedByClient != guaranteed human reviewer identity
```

Do not rename it to `ReviewedBy` or describe it as a person unless a real human user authentication layer is introduced.

Migration:

```text
20261001150500_AddDocumentReviewClientAttribution
```

The DB field is nullable to preserve historical reviews without inventing audit attribution. New review creation requires a non-empty authenticated client value.

The attribution is visible in:

```text
PUT review response
GET extraction-result review metadata
structuredData.human_review.reviewed_by_client
CSV/XLSX effective-data export
```

Automation E2E sends a spoofed request property `reviewedByClient=spoofed-human` and proves the server stores/returns the trusted configured client `e2e-primary` instead.

## Retention / reliability boundary

Retention remains opt-in/default-off. Processing and retention remain intentionally single-instance:

```text
PostgreSQL persisted state
+ startup recovery
+ in-memory Channel<Guid>
+ bounded retries
+ single periodic retention sweep
+ row locking for terminal delete
+ extraction-result idempotency
```

Do not add distributed queue/leases/scheduler without a real multiple-active-instance requirement.

## CI discipline

Continue sparse CI:

- docs/intermediate maintenance -> `[skip ci]`;
- coherent API/domain/persistence changes -> `.NET CI` + Automation E2E;
- Deployment Smoke only for Docker/compose/health/deployment-contract changes;
- Scanned OCR E2E only for OCR/extraction-runner/fixture changes;
- Public Reference Benchmark only for extraction-rule changes.

## Recommended next milestone

Create `v1.1.1.19` after inspecting operational visibility.

Strong narrow candidate: **Operational Metrics / Observability**.

Inspect before implementation:

- `DocumentProcessingQueue` and whether queue depth can be exposed without changing ownership semantics;
- `DocumentProcessingBackgroundService` retry/outcome paths;
- `DocumentRetentionHostedService` outcomes;
- review completion path;
- current `HealthController` and logging;
- existing package dependencies before choosing OpenTelemetry/Prometheus or a simpler in-process metrics surface.

Prefer a small set of useful low-cardinality measurements, for example:

```text
processing completed / needs-review / failed counts
technical retry/failure count
pending in-memory queue depth
reviews completed count
retention deletions/failures
```

Avoid labels containing document ids, filenames, customer ids or other high-cardinality/private values.

Do not introduce a large observability backend solely for architecture aesthetics. A narrow `/metrics` or standard .NET metrics/OpenTelemetry instrumentation is sufficient if it materially improves operation of the current MVP.

Other later candidates: per-tenant retention policy, batch upload/intake, API versioning/deprecation for `StorageKey`, and real human IAM if named-human accountability becomes an actual requirement.
