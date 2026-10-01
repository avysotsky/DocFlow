# DocFlow

DocFlow is a private commercial project for automated processing of business documents such as supplier quotations and invoices.

The system converts digital or scanned PDF documents into validated structured data, persists the result in PostgreSQL, exposes a tenant-scoped review inbox, allows authenticated retrieval of original source PDFs, and exports reviewed/persisted data to CSV/XLSX for downstream business use.

## Current MVP flow

```text
Authenticated customer API
  -> single PDF upload or bounded multi-PDF batch intake
  -> shared validation/storage/persistence intake service
  -> startup recovery of orphaned Uploaded/Processing work
  -> bounded background processing attempts
  -> automatic digital/scanned handling
  -> native text extraction or conditional Tesseract OCR
  -> automatic document-type detection
  -> deterministic supplier quotation/invoice extraction
  -> deterministic arithmetic validation
  -> PostgreSQL persistence
  -> tenant-scoped inbox / human review
  -> authenticated client audit attribution for review submissions
  -> original PDF retrieval
  -> CSV/XLSX export
  -> explicit terminal document deletion
  -> optional automatic retention cleanup
  -> optional protected operational metrics
```

Measured public-reference baseline:

```text
Public Reference Benchmark #78
69 Python regression tests
17/17 public documents passed
98/98 checked business fields matched
17/17 document types correct
17/17 validation statuses correct
```

ONNX/LLM extraction fallback is intentionally deferred. Real measured failure classes so far have been recoverable with deterministic layout/OCR rules, so model inference has not yet justified its additional cost and nondeterminism.

## API authentication and tenant boundary

Customer-facing document endpoints require an API key in:

```text
X-DocFlow-Api-Key: <secret>
```

Configured API clients map to a trusted `customer_id` claim. Document ownership is derived from that authenticated identity; callers do not choose the authoritative `CustomerId` in request data.

Missing or invalid credentials return `401`. Access to a document owned by another customer returns `404`, so the API does not disclose cross-tenant resource existence.

Configuration shape:

```json
{
  "Authentication": {
    "ApiKey": {
      "HeaderName": "X-DocFlow-Api-Key",
      "Clients": [
        {
          "Name": "customer-a",
          "CustomerId": "11111111-1111-1111-1111-111111111111",
          "ApiKey": "<secret>"
        }
      ]
    }
  }
}
```

Do not commit production API keys. Supply them with environment variables, user-secrets, or a production secret store. Outside Development the application fails startup unless at least one valid API-key client is configured.

## Batch intake

Single-document and batch uploads now share the same scoped intake service, so PDF validation, storage, persistence rollback, retention timestamp assignment and processing enqueue are not duplicated across endpoints.

Single upload:

```text
POST /api/documents
```

Bounded batch upload:

```text
POST /api/documents/batch
multipart field: Files
```

Batch limits:

```text
maximum files: 10
maximum individual file: 20 MB
maximum aggregate file bytes: 50 MB
endpoint transport request ceiling: 60 MB
```

The 60 MB transport limit exists only to allow multipart headers/boundaries around the 50 MB aggregate business limit; the global API request limit is not expanded.

Batch-level zero-file, file-count and aggregate-size violations return `400` before any file is persisted. Inside an accepted batch, files are handled sequentially and independently, preserving input order. Per-file outcomes are `Accepted`, `Rejected`, or `Failed`; valid files can be persisted/enqueued even when another file in the same batch fails validation.

A database failure rolls back that file's storage object when possible and detaches the failed Added entity from the scoped EF Core context before processing the next batch item.

## Review audit attribution

New document reviews persist the authenticated API client name as `ReviewedByClient`. The value comes from the trusted API-key principal (`docflow:client_name`) and is never accepted as authoritative review identity from the request payload.

The attribution is exposed in the review response, `GET /api/documents/{id}/extraction-result`, the effective `human_review.reviewed_by_client` structured data, and CSV/XLSX export.

The database column is nullable only for backward compatibility with reviews created before this audit field existed; historical rows are not backfilled with invented identities. New reviews require a non-empty authenticated client attribution.

`ReviewedByClient` identifies an authenticated tenant/integration client. It must not be interpreted as a named human reviewer. If named-human accountability becomes a product requirement, add a real user identity/IAM boundary rather than trusting a caller-supplied name or re-labeling the API client.

## Processing retries and diagnostics

Background processing uses a bounded retry policy for technical processing failures. Default configuration:

```json
{
  "Processing": {
    "Retry": {
      "MaxAttempts": 3,
      "RetryDelayMilliseconds": 250
    }
  }
}
```

Each real processing attempt is persisted on the document. A document is moved to `Failed` only after the configured attempts for that dequeued job are exhausted. Successful processing clears the last failure summary while retaining the attempt count and last-attempt timestamp.

Tenant-scoped safe diagnostics are available through:

```text
GET /api/documents/{id}/processing-diagnostics
```

The response includes the current status, persisted processing-attempt count, last attempt/failure timestamps, and a bounded sanitized technical failure summary. Full exception detail remains in application logs rather than being exposed to API clients.

## Restart recovery

The runtime queue is still an in-memory single-reader `Channel<Guid>`, but queued work is reconciled from PostgreSQL whenever the host starts.

Before the normal queue consumer starts, DocFlow discovers documents that:

```text
Status == Uploaded or Processing
and no ExtractionResult exists
```

Those document ids are re-enqueued in created order. This covers both work that was queued but never started and work that was interrupted while `Processing` when the previous process stopped.

Completed `Processed`/`NeedsReview` documents are not re-enqueued, and `Failed` documents remain failed unless a caller explicitly requests processing again.

This recovery contract is intentionally scoped to the current **single-instance MVP**. It is not a distributed queue, lease or multi-worker coordination mechanism. If DocFlow later runs multiple active application instances, introduce explicit distributed ownership/queue semantics rather than relying on startup reconciliation alone.

## Original PDF access

Authenticated tenants can retrieve the original source PDF through:

```text
GET /api/documents/{id}/file
```

The endpoint streams from `IFileStorage` rather than buffering the full file in memory. It returns `application/pdf`, uses a sanitized attachment filename derived from `OriginalFileName`, and enables ASP.NET Core range processing so clients can issue byte-range requests.

Cross-tenant and absent documents return `404`. If a database row exists but its backing storage file is missing, the API returns a sanitized `500` problem response without exposing filesystem or storage-key details; the underlying exception is logged server-side.

`StorageKey` remains in the existing document metadata DTO for compatibility with current clients. New clients should use `/file` rather than treating the storage key as a retrievable path. Removing or deprecating that field is a separate API-versioning decision.

## Document deletion and lifecycle

Tenant-scoped explicit deletion is available through:

```text
DELETE /api/documents/{id}
```

Deletion is allowed for terminal `Processed`, `NeedsReview`, and `Failed` documents. `Uploaded` and `Processing` return `409 Conflict` so the API does not remove a file while the current background worker may own it.

The deletion service locks the document row with PostgreSQL `FOR UPDATE`, removes the database row inside a transaction, deletes the stored PDF, and then commits. Existing foreign-key cascades remove the associated `ExtractionResult` and `DocumentReview` records.

Cross-tenant ids return `404`. After successful deletion all normal document, file, diagnostics, extraction, review and export access returns `404`.

Local filesystem and PostgreSQL do not form a distributed transaction. A storage failure rolls the database transaction back; a rare database commit failure after successful file deletion remains a residual cross-resource consistency risk.

## Retention policy

Automatic retention is opt-in and disabled by default, so upgrading an existing deployment does not start deleting historical documents.

Default configuration:

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

When retention is enabled, new uploads receive a future `DeleteAt` timestamp. A single-instance background sweep periodically selects only expired terminal documents:

```text
DeleteAt <= now
and Status in (Processed, NeedsReview, Failed)
```

Expired `Uploaded` and `Processing` documents are deliberately not selected. They remain available for processing and can be reconsidered by a later sweep after reaching a terminal state.

Each retention deletion reuses the same `IDocumentDeletionService` as the explicit customer delete API, including row locking, stored-file cleanup and existing database cascades. Sweeps are batch-limited, per-document failures are logged without aborting the remaining candidates, and options are validated on application startup.

This scheduler follows the same **single-instance MVP** boundary as processing recovery. It is not a distributed retention lease/scheduler.

## Operational metrics

DocFlow maintains a small set of thread-safe, process-local operational counters and gauges. Metrics are opt-in and disabled by default:

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

When explicitly enabled, operators can read the snapshot through:

```text
GET /operations/metrics
X-DocFlow-Metrics-Key: <operator-secret>
```

The operator credential is deliberately separate from customer `X-DocFlow-Api-Key` credentials. Global process telemetry must not be exposed through tenant authorization.

The snapshot contains only low-cardinality runtime values:

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

No metric contains a document id, filename, customer id or API client identity. Counters reset on process restart and are not aggregated across application instances.

`PendingQueueDepth` is updated with publication-safe ordering: the gauge is reserved before an id is made visible to the channel reader and rolled back if channel publication fails.

This is intentionally a narrow JSON operational surface, not a Prometheus/OpenTelemetry backend. Add external collection/aggregation only when deployment requirements justify it.

## Production deployment

The repository includes a production `Dockerfile` and `compose.yaml`.

The runtime image contains:

- the published .NET 8 API;
- the Python extraction worker and its dependencies;
- Tesseract OCR with English language data;
- persistent document storage mounted at `/data/storage`.

Local production-like startup:

```bash
cp .env.example .env
# Replace DOCFLOW_POSTGRES_PASSWORD and DOCFLOW_API_KEY in .env.
docker compose up --build -d
```

Docker Compose starts PostgreSQL and DocFlow, uses persistent database/document volumes, and enables EF Core migrations explicitly through:

```text
Database__ApplyMigrationsOnStartup=true
```

Outside Compose, migration-on-start remains opt-in and is disabled unless explicitly configured.

Deployment probes:

```text
GET /health/live
GET /health/ready
```

`/health/live` reports process liveness. `/health/ready` requires PostgreSQL connectivity plus the configured storage and extraction-worker runtime paths.

## API capabilities

Current customer document flow includes:

```text
POST   /api/documents
POST   /api/documents/batch
GET    /api/documents?status=...&documentType=...&page=1&pageSize=50
POST   /api/documents/{id}/process
GET    /api/documents/{id}
GET    /api/documents/{id}/file
GET    /api/documents/{id}/processing-diagnostics
GET    /api/documents/{id}/extraction-result
PUT    /api/documents/{id}/review
GET    /api/documents/{id}/export?format=csv
GET    /api/documents/{id}/export?format=xlsx
DELETE /api/documents/{id}
```

Operator-only optional surface:

```text
GET /operations/metrics
```

Export uses the already persisted effective extraction result and does not rerun OCR or extraction.

## Solution structure

```text
DocFlow.sln
src/
  DocFlow.Api/
  DocFlow.Application/
  DocFlow.Domain/
  DocFlow.Infrastructure/
  DocFlow.Extraction.Worker/
```

Main responsibility split:

- **DocFlow.Api** — authenticated single/batch intake, operator metrics surface, source-file streaming, lifecycle/delete, retention scheduling, processing diagnostics, startup recovery, health probes and background-service host.
- **DocFlow.Application** — processing/export/review/deletion abstractions plus process-local operational metric state.
- **DocFlow.Domain** — document, extraction-result and review entities/enums.
- **DocFlow.Infrastructure** — EF Core/PostgreSQL persistence, file storage, Python runner, processing/review/deletion and export implementation.
- **DocFlow.Extraction.Worker** — Python PDF/OCR parsing, deterministic semantic extraction, validation and benchmark tooling.

## Export

For a document with a persisted extraction result:

```text
GET /api/documents/{id}/export?format=csv
GET /api/documents/{id}/export?format=xlsx
```

Both formats expose the structured JSON as deterministic indexed dot paths, for example:

```text
data.invoice_number
data.total
data.items.0.description
data.items.0.quantity
```

CSV uses `Path,Value`; XLSX contains the same logical rows on an `Extraction Result` worksheet.

## Project status

Completed MVP milestones include automated processing, conditional OCR, real-corpus benchmarking, hard-case extraction, degraded-OCR recovery, persisted-result CSV/XLSX export, tenant-scoped document inbox, human review, API-key tenant isolation, reproducible container deployment with health/readiness checks, bounded technical-failure retries with persisted processing diagnostics, single-instance restart recovery from PostgreSQL, tenant-scoped terminal document deletion with file/database cleanup, tenant-scoped original PDF streaming with range support, opt-in automatic retention for expired terminal documents, authenticated API-client attribution for review audit records, protected low-cardinality process-local operational metrics, and bounded partial-success multi-PDF batch intake through the same single-document intake service.

A strong next reliability gap is HTTP intake idempotency. A client retry after a network timeout can currently create duplicate durable documents, and batch retry can multiply the problem. Inspect tenant-scoped persisted idempotency-key semantics before adding broader ingestion channels or distributed infrastructure.

Production code remains private. A separate public portfolio repository may be created later.
