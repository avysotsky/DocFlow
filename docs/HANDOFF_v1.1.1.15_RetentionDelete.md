# DocFlow — handoff v1.1.1.15 Retention / Delete

Status: **COMPLETED**  
Repository: `avysotsky/DocFlow`  
Branch: `DocFlow/v_1.1.1.15_RetentionDelete`  
Base: `DocFlow/v_1.1.1.14_RestartRecovery`

## 1. Milestone result

`v1.1.1.15` adds tenant-scoped explicit deletion for terminal documents, including stored-file cleanup and database cascade cleanup, without adding scheduled retention or new queue infrastructure.

Main implementation commit:

```text
1fae49251a9950e5d45d8feb4d5bad25c86e062c
Add tenant-scoped terminal document deletion
```

Validation:

```text
.NET CI #28
run id: 36874261923
result: success

Automation E2E #104
run id: 36874261696
result: success
```

Only these two relevant workflows ran. Deployment Smoke, Scanned OCR E2E and Public Reference Benchmark were not triggered.

## 2. Delete API

New route:

```text
DELETE /api/documents/{documentId}
```

Authentication and tenant rules are unchanged:

```text
missing/invalid API key -> 401
cross-tenant or absent document -> 404
```

Deletion outcomes:

```text
Processed   -> 204 No Content
NeedsReview -> 204 No Content
Failed      -> 204 No Content
Uploaded    -> 409 Conflict
Processing  -> 409 Conflict
```

`Uploaded` and `Processing` are deliberately rejected because the single-instance background worker/queue may still own those documents.

## 3. Concurrency/race handling

`DocumentDeletionService` begins a PostgreSQL transaction and reads the owned document using:

```sql
SELECT ... FOR UPDATE
```

The row lock serializes the terminal-state decision against processing state changes.

Important race behavior:

- if processing has already changed the row to `Processing`, delete observes that state and returns `409`;
- if delete locks/removes the row first, a queued worker later sees the document as absent and treats that as a successful no-op;
- a queued id for a legitimately deleted document therefore does not generate repeated technical-failure retries.

`DocumentProcessingService.ProcessAsync` was adjusted so a missing document is a no-op, and an extraction save that loses a race to explicit deletion is also treated as authoritative deletion rather than an attempt to recreate/fail the resource.

## 4. File/database cleanup

The deletion transaction performs:

```text
lock owned terminal Document
-> delete Document row (uncommitted)
-> delete stored PDF
-> commit PostgreSQL transaction
```

Existing cascade relationships remove:

```text
ExtractionResult
DocumentReview
```

If file deletion fails, the database transaction is rolled back.

There is no distributed transaction between the local filesystem and PostgreSQL. A rare database commit failure after the file was successfully deleted remains a residual consistency risk. Do not describe this as fully atomic cross-resource deletion.

## 5. E2E proof

The existing restart-recovery script was extended instead of creating another workflow.

Automation E2E proves:

```text
cross-tenant DELETE -> 404
Uploaded DELETE -> 409
Processing DELETE -> 409
active conflict rows remain in database
Processed DELETE -> 204
Failed DELETE -> 204
stored PDF is physically removed
Document row is removed
ExtractionResult row is removed by cascade
DocumentReview row is removed by cascade
GET deleted document -> 404
GET deleted diagnostics -> 404
GET deleted extraction result -> 404
GET deleted export -> 404
PUT review after delete -> 404
repeated DELETE -> 404
restart recovery remains green
all previous automation scenarios remain green
```

A synthetic `DocumentReview` is attached to the recovery document before deletion so the database cascade is explicitly tested, not merely inferred from EF configuration.

## 6. DeleteAt / retention state

`Document.DeleteAt` already exists but remains unused by the product flow.

This milestone intentionally implements **explicit customer deletion only**. It does not add:

- automatic scheduled retention;
- background retention sweeps;
- soft-delete/tombstone state;
- storage garbage collection.

Those can be added later if there is a concrete retention requirement.

## 7. CI discipline

The narrowed CI filters continue to work correctly.

This implementation triggered only:

```text
.NET CI #28
Automation E2E #104
```

No extraction/OCR behavior changed.

Public-reference baseline remains:

```text
17/17 public documents passed
98/98 checked business fields matched
17/17 document types correct
17/17 validation statuses correct
```

## 8. Current product state

The coherent single-instance MVP now includes:

```text
API-key tenant auth
PDF upload
restart reconciliation
bounded retries + persisted failure diagnostics
digital PDF / conditional OCR
quotation/invoice detection + deterministic extraction
validation + PostgreSQL persistence
review inbox + human correction
CSV/XLSX export
explicit terminal document deletion
container deployment + health/readiness
```

## 9. Recommended next gap

A stronger next narrow product gap than reviewer identity is **authenticated original-PDF access**.

Human review already exists, but there is no customer endpoint that streams the stored source PDF. `IFileStorage.OpenReadAsync` exists internally, and `GET /api/documents/{id}` currently exposes only metadata/storage key.

A likely `v1.1.1.16` should inspect and add a tenant-scoped source-document endpoint, for example:

```text
GET /api/documents/{id}/file
```

with correct content type, download filename, tenant isolation and `404` behavior. It should not expose filesystem/storage paths directly.

Reviewer/audit identity remains a later candidate. Current API-key client identity is a tenant/integration identity and must not be mislabeled as an individual human reviewer.
