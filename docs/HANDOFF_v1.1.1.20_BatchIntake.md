# DocFlow — handoff v1.1.1.20 Batch Intake

Status: **COMPLETED**  
Repository: `avysotsky/DocFlow`  
Branch: `DocFlow/v_1.1.1.20_BatchIntake`  
Base: `DocFlow/v_1.1.1.19_OperationalMetrics`

## 1. Milestone result

`v1.1.1.20` adds bounded multi-document intake while preserving the existing independent document lifecycle.

Main validating implementation commit:

```text
6cdf27cb0bd5d664291493fdf0d7d235992b3c08
Complete bounded batch intake implementation
```

Final validation:

```text
.NET CI #34
run id: 36889076653
result: success

Automation E2E #110
run id: 36889076198
result: success
```

Only those two relevant workflows ran. Deployment Smoke, Scanned OCR E2E and Public Reference Benchmark were not triggered.

## 2. Reusable intake path

Single-document validation/storage/persistence/rollback/retention/enqueue logic now lives in:

```text
DocFlow.Api.Documents.DocumentIntakeService
```

Both single upload and batch upload use the same service.

Per-file validation preserves the existing rules:

```text
non-empty file
<= 20 MB
.pdf extension
application/pdf content type
%PDF- signature
```

The service uploads to storage, creates the `Document`, persists it, then enqueues the durable document id. If database persistence fails, the uploaded storage object is deleted when possible and the failed Added entity is detached from the scoped `DbContext` so a later batch item is not contaminated by stale tracking state.

## 3. Batch API

New endpoint:

```text
POST /api/documents/batch
Content-Type: multipart/form-data
Files=<pdf>
Files=<pdf>
...
```

Batch limits:

```text
maximum files: 10
maximum aggregate file bytes: 50 MB
maximum individual file: 20 MB
endpoint transport request limit: 60 MB
```

The 60 MB transport ceiling is deliberately larger than the 50 MB business limit only to allow multipart boundary/header overhead. The global API request limit was not expanded.

Batch-level zero-file, file-count and aggregate-size violations return `400` before any file is persisted.

## 4. Per-file partial-failure semantics

Within an accepted batch, files are processed sequentially and independently in input order.

Possible item outcomes:

```text
Accepted
Rejected
Failed
```

`Accepted` means the document row was durably persisted. It receives its own document id and normal downstream processing lifecycle.

`Rejected` means file-level validation failed. No storage/database row is created for that file.

`Failed` means storage or database intake failed for that specific file. The response exposes only a sanitized failure reason; processing continues with remaining files unless the HTTP request itself is cancelled.

Response shape includes:

```text
totalCount
acceptedCount
rejectedCount
failedCount
items[]
```

Each item preserves the original zero-based input index and filename, plus document metadata when accepted.

## 5. Existing single-upload behavior

`POST /api/documents` now delegates to `DocumentIntakeService` rather than duplicating validation/storage/persistence code.

Existing successful upload response and per-file validation semantics remain compatible. Infrastructure intake failures now return a sanitized `500` problem response instead of leaking an unhandled storage/database exception.

## 6. E2E coverage

Automation E2E #110 extends the existing inbox/auth verifier and proves:

```text
empty batch -> 400
11-file batch -> 400
mixed 2-file batch -> 200
valid PDF -> Accepted
invalid .txt -> Rejected
accepted item preserves index/name/id/status
rejected item has no document id
accepted batch document reaches Processed
accepted document is visible to owning tenant
accepted document returns cross-tenant 404
existing inbox/auth/diagnostics/review/restart/retention scenarios remain green
```

The 50 MB aggregate arithmetic is enforced directly in the controller before per-file intake. E2E does not transmit a synthetic 50+ MB payload solely to prove the numeric guard, avoiding unnecessary CI bandwidth/cost.

## 7. Explicit non-goals

This milestone does not add:

- ZIP/archive ingestion;
- email/mailbox ingestion;
- S3/blob polling;
- asynchronous batch-job entities;
- all-or-nothing batch transactions;
- parallel batch intake;
- distributed queue/work ownership.

Each accepted PDF remains a normal independent DocFlow document.

## 8. CI discipline

Continue sparse CI:

- docs/intermediate maintenance -> `[skip ci]`;
- coherent API/Application/Infrastructure changes -> `.NET CI` + Automation E2E;
- Deployment Smoke only for Docker/compose/health/deployment-contract changes;
- Scanned OCR E2E only for OCR/extraction-runner/fixture changes;
- Public Reference Benchmark only for extraction-rule changes.

## 9. Next direction

The strongest narrow next candidate is **intake idempotency**.

Now that one HTTP request can accept multiple files, a client retry after a timeout can create duplicate durable documents. Before implementation inspect whether idempotency should be request-level, per-file, or both, and design a tenant-scoped persisted key contract with deterministic replay/conflict behavior.

Do not implement content-hash deduplication as a substitute for request idempotency unless the product explicitly requires semantic duplicate detection.
