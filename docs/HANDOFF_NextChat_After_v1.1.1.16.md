# DocFlow — Next Chat Handoff After v1.1.1.16

Use this file as the starting state for the next DocFlow development chat.

## Repository state

Repository: `avysotsky/DocFlow`  
Completed branch: `DocFlow/v_1.1.1.16_OriginalPdfAccess`  
Previous branch: `DocFlow/v_1.1.1.15_RetentionDelete`

Main implementation commit:

```text
35ec117537401b441e054fb4393acbfebc1c5db7
Add tenant-scoped original PDF access
```

Validation:

```text
.NET CI #29 -> success (run 36876459319)
Automation E2E #105 -> success (run 36876459466)
```

Only these two relevant workflows ran. Deployment Smoke, Scanned OCR E2E and Public Reference Benchmark were not triggered.

Detailed handoff:

```text
docs/HANDOFF_v1.1.1.16_OriginalPdfAccess.md
```

## Current product state

DocFlow now supports:

```text
API-key authenticated tenant
  -> PDF upload
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
  -> human review/correction
  -> CSV/XLSX export
  -> tenant-scoped terminal document deletion
```

Production container deployment, health/readiness checks and opt-in migrations remain in place.

Public-reference extraction baseline remains:

```text
17/17 public documents passed
98/98 checked business fields matched
17/17 document types correct
17/17 validation statuses correct
```

No extraction/OCR behavior changed in `v1.1.1.16`.

## Original PDF access state

Endpoint:

```text
GET /api/documents/{documentId}/file
```

Contract:

```text
owned document -> streamed application/pdf attachment
range requests -> supported / 206
cross-tenant or absent -> 404
missing backing file -> sanitized 500
successful prior deletion -> 404
```

The endpoint uses `IFileStorage.OpenReadAsync`, does not buffer the whole PDF, and sanitizes the attachment filename.

Automation E2E proves exact byte equality against the source fixture, content headers, range support, tenant isolation, sanitized missing-file failure and post-delete behavior.

## StorageKey decision

`GET /api/documents/{id}` still exposes `StorageKey` because removing an existing field would be a breaking DTO change. New clients should use `/file`; do not treat `StorageKey` as a public download URL.

If field removal is desired later, handle it as an explicit API version/deprecation task.

## Reliability boundary

Processing remains intentionally single-instance:

```text
PostgreSQL persisted state
+ startup recovery
+ in-memory Channel<Guid>
+ bounded retries
+ row locking for terminal delete
+ extraction-result idempotency
```

Do not introduce RabbitMQ/Kafka/database leases unless multiple active processing instances become a real requirement.

## CI discipline

Continue sparse CI:

- docs/intermediate maintenance -> `[skip ci]`;
- coherent implementation batch;
- `.NET CI` + Automation E2E for normal API/domain/persistence/lifecycle changes;
- Deployment Smoke only for Docker/compose/health/deployment-contract changes;
- Scanned OCR E2E only for OCR/extraction-runner/fixture changes;
- Public Reference Benchmark only for extraction-rule changes.

## Recommended next milestone

Create `v1.1.1.17` only after inspecting retention semantics.

Strong narrow candidate: **Retention Policy**.

Current facts:

- `Document.DeleteAt` is nullable;
- the `Document` constructor accepts an optional `deleteAt` but normal upload does not pass one;
- therefore uploaded documents currently have `DeleteAt == null`;
- explicit terminal deletion already exists and should be reused where practical;
- active `Uploaded` / `Processing` documents must not be automatically deleted.

Inspect before implementation:

- `Document` / `DocumentConfiguration` mapping of `DeleteAt`;
- upload construction path;
- deletion service API and whether an internal system deletion entry point is needed;
- hosted-service scheduling conventions;
- desired configurable retention period and whether retention should be opt-in by default.

A narrow retention milestone could provide:

```text
configurable default retention period
-> set DeleteAt on newly uploaded documents
-> periodic single-instance sweep
-> delete only terminal documents whose DeleteAt <= now
-> skip active documents and retry them on a later sweep
-> reuse the same file/database cleanup guarantees as explicit delete
```

Do not introduce a distributed scheduler or queue solely for retention. Keep the same single-instance MVP boundary unless deployment requirements change.

Reviewer/audit identity remains another later candidate. The current API-key identity is a tenant/integration identity and must not be represented as an authenticated human reviewer.
