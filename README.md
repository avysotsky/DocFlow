# DocFlow

DocFlow is a private commercial project for automated processing of business documents such as supplier quotations and invoices.

The system converts digital or scanned PDF documents into validated structured data, persists the result in PostgreSQL, exposes a tenant-scoped review inbox, and exports reviewed/persisted data to CSV/XLSX for downstream business use.

## Current MVP flow

```text
Authenticated customer API
  -> PDF upload
  -> bounded background processing attempts
  -> automatic digital/scanned handling
  -> native text extraction or conditional Tesseract OCR
  -> automatic document-type detection
  -> deterministic supplier quotation/invoice extraction
  -> deterministic arithmetic validation
  -> PostgreSQL persistence
  -> tenant-scoped inbox / human review
  -> CSV/XLSX export
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

The queue itself is still in-memory. Bounded retry improves transient-failure handling but does not yet provide durable job recovery across process restarts.

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
POST /api/documents
GET  /api/documents?status=...&documentType=...&page=1&pageSize=50
POST /api/documents/{id}/process
GET  /api/documents/{id}
GET  /api/documents/{id}/processing-diagnostics
GET  /api/documents/{id}/extraction-result
PUT  /api/documents/{id}/review
GET  /api/documents/{id}/export?format=csv
GET  /api/documents/{id}/export?format=xlsx
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

- **DocFlow.Api** — authenticated HTTP endpoints, processing diagnostics, health probes and background-service host.
- **DocFlow.Application** — processing/export/review abstractions and orchestration contracts.
- **DocFlow.Domain** — document, extraction-result and review entities/enums.
- **DocFlow.Infrastructure** — EF Core/PostgreSQL persistence, file storage, Python runner, processing/review and export implementation.
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

Completed MVP milestones include automated processing, conditional OCR, real-corpus benchmarking, hard-case extraction, degraded-OCR recovery, persisted-result CSV/XLSX export, tenant-scoped document inbox, human review, API-key tenant isolation, reproducible container deployment with health/readiness checks, and bounded technical-failure retries with persisted processing diagnostics.

The next operational gap is restart recovery for the still in-memory processing queue. A narrow recovery milestone should be considered before introducing a full external broker: on startup, safely reconcile persisted `Uploaded`/stale `Processing` documents and re-enqueue work using the existing idempotency guarantees.

Production code remains private. A separate public portfolio repository may be created later.
