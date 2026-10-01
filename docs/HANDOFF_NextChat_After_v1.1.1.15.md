# DocFlow — Next Chat Handoff After v1.1.1.15

Use this file as the starting state for the next DocFlow development chat.

## Repository state

Repository: `avysotsky/DocFlow`  
Completed branch: `DocFlow/v_1.1.1.15_RetentionDelete`  
Previous branch: `DocFlow/v_1.1.1.14_RestartRecovery`

Main implementation commit:

```text
1fae49251a9950e5d45d8feb4d5bad25c86e062c
Add tenant-scoped terminal document deletion
```

Validation:

```text
.NET CI #28 -> success (run 36874261923)
Automation E2E #104 -> success (run 36874261696)
```

Only those two relevant workflows ran. Deployment Smoke, Scanned OCR E2E and Public Reference Benchmark were not triggered.

Detailed handoff:

```text
docs/HANDOFF_v1.1.1.15_RetentionDelete.md
```

## Current product state

DocFlow currently supports:

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

No extraction/OCR behavior changed in `v1.1.1.15`.

## Delete lifecycle state

Endpoint:

```text
DELETE /api/documents/{documentId}
```

Behavior:

```text
Processed/NeedsReview/Failed -> delete -> 204
Uploaded/Processing -> 409
cross-tenant/absent -> 404
```

Deletion uses a PostgreSQL transaction plus `SELECT ... FOR UPDATE` to serialize the state decision against background processing. It deletes the database row, removes the stored PDF, then commits. `ExtractionResult` and `DocumentReview` are removed by existing database cascades.

If file deletion fails, the database transaction is rolled back. Filesystem + PostgreSQL are not a true distributed transaction, so a database commit failure after successful file deletion remains a rare residual inconsistency risk.

Queued ids that refer to a document successfully deleted before processing now become a no-op rather than a retrying technical failure.

`Document.DeleteAt` still exists but automatic scheduled retention is not implemented.

## Reliability boundary

The system remains intentionally single-instance for processing ownership:

```text
PostgreSQL persisted state
+ startup recovery
+ in-memory Channel<Guid>
+ bounded retries
+ row locking for terminal delete
+ extraction-result idempotency
```

Do not add RabbitMQ/Kafka/database leasing solely for architectural completeness. Add distributed ownership only if multiple active processing instances become a real requirement.

## CI discipline

Continue sparse CI:

- docs/intermediate maintenance -> `[skip ci]`;
- coherent implementation batch;
- `.NET CI` + Automation E2E for normal API/domain/persistence/processing/lifecycle changes;
- Deployment Smoke only for Docker/compose/health/deployment-contract changes;
- Scanned OCR E2E only for OCR/extraction-runner/fixture changes;
- Public Reference Benchmark only for extraction-rule changes.

## Recommended next milestone

Create `v1.1.1.16` after inspecting source-file access.

Strongest narrow candidate: **Original PDF Access**.

Reason: human review already exists, but the authenticated customer API has no endpoint that streams the original source PDF. `IFileStorage.OpenReadAsync` already exists internally; `GET /api/documents/{id}` only returns metadata and a storage key.

Inspect:

- `IFileStorage.OpenReadAsync` / `LocalFileStorage`;
- tenant ownership patterns in document/export controllers;
- ASP.NET Core `FileStreamResult` / content-disposition behavior;
- how missing storage files should map to API responses;
- whether `StorageKey` should continue being exposed in the document DTO once a proper file endpoint exists.

A likely narrow API:

```text
GET /api/documents/{id}/file
```

Acceptance should prove:

```text
correct tenant can retrieve exact PDF bytes
Content-Type is application/pdf
Content-Disposition uses safe original filename
cross-tenant id -> 404
missing document -> 404
missing backing file -> controlled response (do not leak filesystem path)
deleted document -> 404
```

Do not add signed URLs/object storage/S3 in this milestone unless the existing local-storage abstraction genuinely blocks the implementation.

Reviewer/audit identity remains a later product candidate. `DocumentReview` still has no reviewer identity, but the current API-key client is an integration/tenant identity and must not be represented as a human reviewer.
