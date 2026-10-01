# DocFlow

DocFlow is a private commercial project for automated processing of business documents such as supplier quotations and invoices.

The system converts digital or scanned PDF documents into validated structured data, persists the result in PostgreSQL, exposes a tenant-scoped review inbox, and exports reviewed/persisted data to CSV/XLSX for downstream business use.

## Current MVP flow

```text
Authenticated customer API
  -> PDF upload
  -> startup recovery of orphaned Uploaded/Processing work
  -> bounded background processing attempts
  -> automatic digital/scanned handling
  -> native text extraction or conditional Tesseract OCR
  -> automatic document-type detection
  -> deterministic supplier quotation/invoice extraction
  -> deterministic arithmetic validation
  -> PostgreSQL persistence
  -> tenant-scoped inbox / human review
  -> CSV/XLSX export
  -> explicit terminal document deletion
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

## Document deletion and lifecycle

Tenant-scoped explicit deletion is available through:

```text
DELETE /api/documents/{id}
```

Deletion is allowed for terminal `Processed`, `NeedsReview`, and `Failed` documents. `Uploaded` and `Processing` return `409 Conflict` so the API does not remove a file while the current background worker may own it.

The deletion service locks the document row with PostgreSQL `FOR UPDATE`, removes the database row inside a transaction, deletes the stored PDF, and then commits. Existing foreign-key cascades remove the associated `ExtractionResult` and `DocumentReview` records.

Cross-tenant ids return `404`. After successful deletion all normal document, diagnostics, extraction, review and export access returns `404`.

Local filesystem and PostgreSQL do not form a distributed transaction. A storage failure rolls the database transaction back; a rare database commit failure after successful file deletion remains a residual cross-resource consistency risk.

`Document.DeleteAt` still exists as retention metadata but automatic scheduled retention is not implemented yet.

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
GET    /api/documents?status=...&documentType=...&page=1&pageSize=50
POST   /api/documents/{id}/process
GET    /api/documents/{id}
GET    /api/documents/{id}/processing-diagnostics
GET    /api/documents/{id}/extraction-result
PUT    /api/documents/{id}/review
GET    /api/documents/{id}/export?format=csv
GET    /api/documents/{id}/export?format=xlsx
DELETE /api/documents/{id}
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

- **DocFlow.Api** — authenticated HTTP endpoints, lifecycle/delete, processing diagnostics, startup recovery, health probes and background-service host.
- **DocFlow.Application** — processing/export/review/deletion abstractions and orchestration contracts.
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

Completed MVP milestones include automated processing, conditional OCR, real-corpus benchmarking, hard-case extraction, degraded-OCR recovery, persisted-result CSV/XLSX export, tenant-scoped document inbox, human review, API-key tenant isolation, reproducible container deployment with health/readiness checks, bounded technical-failure retries with persisted processing diagnostics, single-instance restart recovery from PostgreSQL, and tenant-scoped terminal document deletion with file/database cleanup.

A strong next narrow product gap is authenticated access to the original stored PDF. Human review exists, but the API currently exposes metadata/structured data without a tenant-scoped file-download endpoint, so a reviewer cannot retrieve the source document through the API itself.

Production code remains private. A separate public portfolio repository may be created later.
