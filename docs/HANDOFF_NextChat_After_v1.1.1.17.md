# DocFlow — Next Chat Handoff After v1.1.1.17

Use this file as the starting state for the next DocFlow development chat.

## Repository state

Repository: `avysotsky/DocFlow`  
Completed branch: `DocFlow/v_1.1.1.17_RetentionPolicy`  
Previous branch: `DocFlow/v_1.1.1.16_OriginalPdfAccess`

Main implementation commit:

```text
d5aad1e030bb4c76a8d69f9ac9836c5458b60bca
Add opt-in document retention policy
```

Implementation staging commits, both `[skip ci]`:

```text
dc1881ea70e22668d2558ed986282ac0d96435be
70ecdf2b12189c3e35c111a26d6374659beab450
```

Validation:

```text
.NET CI #30 -> success (run 36878520692)
Automation E2E #106 -> success (run 36878520631)
```

Only those two relevant workflows ran. Deployment Smoke, Scanned OCR E2E and Public Reference Benchmark were not triggered.

Detailed handoff:

```text
docs/HANDOFF_v1.1.1.17_RetentionPolicy.md
```

## Current product state

DocFlow now supports:

```text
API-key authenticated tenant
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
  -> human review/correction
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
```

No extraction/OCR behavior changed in `v1.1.1.17`.

## Retention state

Configuration:

```json
{
  "Retention": {
    "Enabled": false,
    "DefaultRetentionDays": 30,
    "SweepIntervalSeconds": 3600,
    "BatchSize": 100
  }
}
```

Rules:

```text
Enabled=false -> uploads keep DeleteAt=null and no retention loop runs
Enabled=true -> new upload gets future DeleteAt
expired Processed/NeedsReview/Failed -> eligible for automatic deletion
expired Uploaded/Processing -> never selected; retained until a later sweep
future DeleteAt -> retained
```

Retention reuses `IDocumentDeletionService`, so automatic cleanup uses the same row-lock/file/database-cascade semantics as explicit `DELETE /api/documents/{id}`.

The sweep is batch-limited and per-document errors do not abort the rest of a batch.

No migration was added because `DeleteAt` already existed.

## Reliability boundary

The application is still intentionally single-instance for processing and retention ownership:

```text
PostgreSQL persisted state
+ startup recovery
+ in-memory Channel<Guid>
+ bounded retries
+ single periodic retention sweep
+ row locking for terminal delete
+ extraction-result idempotency
```

Do not introduce RabbitMQ/Kafka/database leases/distributed scheduler solely for architecture aesthetics. Add them only when multiple active application instances become a real requirement.

## CI discipline

Continue sparse CI:

- docs/intermediate maintenance -> `[skip ci]`;
- coherent implementation validation -> `.NET CI` + Automation E2E;
- Deployment Smoke only for Docker/compose/health/deployment-contract changes;
- Scanned OCR E2E only for OCR/extraction-runner/fixture changes;
- Public Reference Benchmark only for extraction-rule changes.

## Recommended next milestone

Create `v1.1.1.18` only after inspecting review audit semantics.

Strong candidate: **Review Audit Identity**.

Current facts:

- `DocumentReview` stores `DocumentId`, `ExtractionResultId`, corrected JSON, optional note and `ReviewedAt`;
- it does not store who performed the review;
- `DocumentReviewsController` requires the tenant API-key principal;
- `ApiKeyAuthenticationHandler` has a configured client name/name-identifier plus trusted customer id;
- that API-key client is an integration/tenant identity, not necessarily a human reviewer.

Before implementation inspect:

- `DocumentReview` entity/configuration/migration history;
- `DocumentReviewsController` request/response;
- API-key claims and client-name semantics;
- whether the commercial workflow actually requires human reviewer identity now, or only authenticated client audit attribution;
- whether a proper user identity provider is required before calling anything `ReviewedBy`.

A narrow safe milestone, if human IAM is not yet required, may record **authenticated client audit attribution** under an explicit name such as `ReviewedByClient`, without claiming that the client is a human reviewer.

If actual named human accountability is required, stop and design the authentication boundary rather than trusting a caller-supplied reviewer name.

Other later candidates include metrics/operational observability, per-tenant retention configuration, batch intake and API versioning/deprecation for `StorageKey`.
