# DocFlow — Next Chat Handoff After v1.1.1.19

Use this file as the starting state for the next DocFlow development chat.

## Repository state

Repository: `avysotsky/DocFlow`  
Completed branch: `DocFlow/v_1.1.1.19_OperationalMetrics`  
Previous branch: `DocFlow/v_1.1.1.18_ReviewAuditIdentity`

Implementation commits:

```text
e59d07e680c873c7118d44e8a875b2a7c3172f2e
Add protected process-local operational metrics

3d6c74c7c890a2b0230e6aab33d86c9b5cf7540e
Fix operational queue-depth publication race
```

Final validation:

```text
.NET CI #33 -> success (run 36884608529)
Automation E2E #109 -> success (run 36884608517)
```

The second implementation commit is the authoritative final code state. An initial CI pair from the first commit was superseded after a queue-depth concurrency race was found and fixed.

Detailed handoff:

```text
docs/HANDOFF_v1.1.1.19_OperationalMetrics.md
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

No extraction/OCR behavior changed in `v1.1.1.19`.

## Operational metrics state

Default configuration:

```json
{
  "Operations": {
    "Metrics": {
      "Enabled": false,
      "ApiKey": ""
    }
  }
}
```

When explicitly enabled:

```text
GET /operations/metrics
X-DocFlow-Metrics-Key: <operator-secret>
```

This is a separate operator boundary. Do not reuse or reinterpret tenant `X-DocFlow-Api-Key` authorization for global metrics.

Process-local snapshot:

```text
startedAt
uptimeSeconds
pendingQueueDepth
processingCompleted
processingNeedsReview
processingFailed
processingRetries
reviewsCompleted
retentionDeleted
retentionFailures
```

Counters reset on restart and are per-process/per-instance. There are no document/customer/client labels.

Queue depth is publication-order safe: the gauge is reserved before an item becomes visible to the channel reader and rolled back if publication fails.

Automation E2E #109 runs with metrics disabled by default and proves `/operations/metrics` returns `404`. The enabled operator-key branch is implemented and startup-validated; no operator secret is committed to the repository.

## Existing identity boundary

Review audit attribution remains:

```text
ReviewedByClient == authenticated API client/integration identity
ReviewedByClient != guaranteed human reviewer identity
```

Do not relabel it as a human reviewer without real human IAM.

## Reliability boundary

Processing and retention remain intentionally single-instance:

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

Do not introduce RabbitMQ/Kafka/database leases/distributed scheduler or metrics aggregation solely for architecture aesthetics. Add distributed ownership only when multiple active instances become a real requirement.

## CI discipline

Continue sparse CI:

- docs/intermediate maintenance -> `[skip ci]`;
- coherent API/Application/Infrastructure changes -> `.NET CI` + Automation E2E;
- Deployment Smoke only for Docker/compose/health/deployment-contract changes;
- Scanned OCR E2E only for OCR/extraction-runner/fixture changes;
- Public Reference Benchmark only for extraction-rule changes.

## Recommended next milestone

Create `v1.1.1.20` only after inspecting current upload semantics.

Strong candidate: **Batch Intake**.

Current facts:

- `POST /api/documents` accepts exactly one PDF;
- validation, storage upload, `Document` creation, rollback and queue enqueue are currently implemented directly in `DocumentsController.Upload`;
- each document remains independently processed and independently reviewable/exportable/deletable;
- the processing queue is already capable of receiving many ids;
- current operational metrics can expose queue pressure while a batch is being accepted/processed.

Before implementation decide:

- maximum files per batch and aggregate byte limit;
- whether invalid files reject the whole batch or produce per-file outcomes;
- rollback semantics for storage/DB failure part-way through a batch;
- whether to extract a reusable single-document intake service first;
- response shape for accepted/rejected files;
- whether enqueue happens only after each individual document is durably persisted.

Recommended narrow shape:

```text
POST /api/documents/batch
multipart files[]
small bounded batch
independent per-file validation/result
valid files persist/enqueue independently
invalid files return explicit per-file rejection
```

Do not add ZIP ingestion, email/mailbox ingestion, S3/blob polling or asynchronous batch-job orchestration in the same milestone.

Other later candidates: per-tenant retention policy, API versioning/deprecation for `StorageKey`, real human IAM if required, and external metrics/tracing only when deployment requirements justify them.
