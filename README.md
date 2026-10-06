# DocFlow

DocFlow is a private commercial project for automated processing of business documents such as supplier quotations and invoices.

The system converts digital or scanned PDF documents into validated structured data, persists the result in PostgreSQL, exposes a tenant-scoped review inbox, allows authenticated retrieval of original source PDFs, and exports reviewed/persisted data to CSV/XLSX for downstream business use.

## Current MVP flow

```text
Authenticated customer API or configured IMAP mailbox
  -> RFC822 PDF attachment intake or direct PDF upload/bounded batch intake
  -> optional tenant-scoped Idempotency-Key for single and batch intake
  -> shared validation/storage/persistence intake service
  -> startup recovery of orphaned Uploaded/Processing work
  -> bounded background processing attempts
  -> automatic digital/scanned handling
  -> native text extraction or conditional Tesseract OCR
  -> automatic document-type detection
  -> deterministic supplier quotation/invoice extraction
  -> deterministic arithmetic validation
  -> PostgreSQL persistence
  -> transactional terminal-completion outbox
  -> signed tenant-configured webhook delivery
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

## Mailbox / IMAP intake

DocFlow can ingest RFC822/MIME email messages, retain source-message metadata, select PDF attachments, and submit accepted attachments through the same internal document-intake pipeline used by API uploads.

The provider-neutral IMAP poller is configured under `Mailbox:Imap`. Each configured mailbox maps to a DocFlow tenant and persists an independent checkpoint keyed by tenant, mailbox name and folder. The checkpoint stores IMAP `UIDVALIDITY` and the last completed UID. On restart, polling resumes after the persisted UID; when `UIDVALIDITY` changes, the cursor resets for the new mailbox generation.

Mailbox message identity and attachment persistence provide idempotent replay behavior. A message with the same stable identity and identical MIME payload replays the existing result; conflicting payload under the same identity is rejected rather than silently creating a second document.

Automation E2E validates the real protocol path:

```text
SMTP -> GreenMail -> IMAP/MailKit -> RFC822 ingestion
     -> PDF attachment -> Document -> extraction
     -> persisted IMAP checkpoint -> API restart
     -> second message -> checkpoint advances
```

The current implementation is generic IMAP with username/password credentials. Gmail OAuth, Microsoft Graph/Outlook OAuth and provider-specific mailbox APIs are **not** implemented or claimed.

## Accounting posting

DocFlow can turn a processed `supplier_invoice` into a provider-neutral canonical accounting bill and persist an idempotent posting record before delivery to an accounting adapter.

Public clients select a tenant-scoped `targetKey`; they do not submit provider realm/account identifiers directly. Server configuration resolves the target key to a provider and provider account.

Example configuration:

```json
{
  "AccountingPosting": {
    "Targets": [
      {
        "CustomerId": "11111111-1111-1111-1111-111111111111",
        "Key": "primary-ledger",
        "Provider": "local-test",
        "TargetAccount": "internal-provider-account-id"
      }
    ]
  }
}
```

Available public targets:

```text
GET /api/accounting-postings/targets
```

The response exposes the public key and provider only; the resolved external account identifier remains internal.

Create a posting:

```text
POST /api/accounting-postings
{
  "documentId": "<processed supplier invoice id>",
  "targetKey": "primary-ledger",
  "idempotencyKey": "<caller-stable key>"
}
```

The persisted payload uses the versioned `accounting_bill_v1` schema rather than raw extraction JSON. It carries supplier/invoice identity, dates, currency, PO reference, normalized line items, discounts, tax data, total, payment terms and notes.

Posting attempts are durable. Retryable failures return to `Pending` with bounded backoff; stale `Posting` attempts are recovered after the configured timeout and retried with the same idempotency key. `Posted` and terminal `Failed` records cannot be retried accidentally.

The `local-test` adapter is registered only in Development. QuickBooks Online has a deterministic Bill mapper, HTTP adapter and OAuth connection subsystem. When QuickBooks OAuth is explicitly enabled, connected targets use encrypted access/refresh tokens with refresh-token rotation and the QBO adapter is registered. The complete flow is validated against a local fake Intuit server; a real Intuit sandbox Bill creation has **not** been validated yet. Xero live posting is also not implemented or claimed.

QuickBooks connection endpoints:

```text
POST /api/accounting-connections/quickbooks-online/targets/{targetKey}/authorize
GET  /api/accounting-connections/quickbooks-online/callback
GET  /api/accounting-connections/quickbooks-online/targets/{targetKey}
```

OAuth state is stored only as a SHA-256 hash and is single-use. QBO access/refresh tokens are encrypted with ASP.NET Core Data Protection; enabling OAuth requires a persistent key ring. Public connection responses do not expose tokens or the QBO realm id.

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

Single-document and batch uploads share the same scoped intake service, so PDF validation, storage, persistence rollback, retention timestamp assignment and processing enqueue are not duplicated across endpoints.

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

## Intake idempotency

Single and batch intake accept an optional HTTP header:

```text
Idempotency-Key: <1..128 chars>
```

Keys are scoped by authenticated tenant. The reserved prefix `docflow-internal:` is rejected for caller-supplied keys because DocFlow uses that namespace for durable batch-item checkpoints.

### Single upload

For `POST /api/documents`, DocFlow persists the request fingerprint and accepted/rejected response snapshot in `IntakeIdempotencyRecords`.

Within the retention window:

```text
same tenant + same key + same request -> replay original response
same tenant + same key + different request -> 409 Conflict
same key + different tenant -> independent namespace
```

Replay responses include:

```text
Idempotency-Replayed: true
```

Concurrent same-key requests are serialized with a PostgreSQL transaction advisory lock before storage upload, preventing duplicate durable documents. Deterministic validation rejections are persisted and replayed; storage/database infrastructure failures remain retryable and are not recorded as completed outcomes.

### Batch upload

For `POST /api/documents/batch`, idempotency is defined over the **whole ordered request**. The batch fingerprint includes file count and, in order, each file index, filename, content type, length and full bytes. Reordering otherwise-identical files therefore produces a different request and conflicts under the same key.

DocFlow persists a `BatchIntakeIdempotencyRecord` manifest containing the external tenant/key fingerprint, a `GenerationId`, an optional completed response snapshot, and expiry metadata. Each item is then processed through the existing single-file idempotency engine under a deterministic internal key:

```text
docflow-internal:batch:<GenerationId>:<item-index>
```

This makes each accepted/rejected item a durable checkpoint without duplicating storage or document-persistence logic. If an item has a retryable infrastructure `Failed` outcome, the batch manifest remains incomplete; a retry with the same key and identical ordered payload reuses the same generation, replays already completed items and retries the unfinished item. Once every item is `Accepted` or `Rejected`, the complete batch response is persisted and subsequent requests replay it with `Idempotency-Replayed: true`.

Concurrent identical batches share the same manifest generation and item keys. Batch-manifest locking plus per-item advisory locking prevents duplicate accepted documents.

Automation E2E also verifies incomplete-batch recovery under a real deterministic PostgreSQL persistence failure. The test leaves the batch manifest incomplete, confirms durable checkpoints for the unaffected items, retries the identical request after removing the fault, verifies that existing DocumentIds are reused and only the failed item is executed again, then proves that a third request is an exact completed replay. No production fault-injection path is present.

### Expiry and cleanup

Default configuration:

```json
{
  "Intake": {
    "Idempotency": {
      "RetentionHours": 24,
      "CleanupIntervalSeconds": 3600,
      "CleanupBatchSize": 500
    }
  }
}
```

Expired single records and batch manifests are physically removed by `IntakeIdempotencyCleanupHostedService` in bounded sweeps. Before deleting a candidate, cleanup acquires the corresponding PostgreSQL advisory lock and re-checks expiry, so it cannot delete a key that intake has just renewed. Cleanup remains part of the current single-instance operational model; the PostgreSQL locks protect key-level transaction correctness, not a general distributed scheduler.

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

## Completion event outbox

Whenever processing reaches a terminal state, DocFlow persists a durable completion event in `DocumentCompletionOutbox`:

```text
Processed
NeedsReview
Failed
```

For `Processed` and `NeedsReview`, the event is inserted in the same EF Core `SaveChanges` that persists the `ExtractionResult` and terminal document status. For exhausted technical failures, the `Failed` event is inserted in the same `SaveChanges` that persists the final failed status.

Each event snapshots:

```text
event id
document id
customer id
terminal status
document type
processing-attempt count
occurred timestamp
```

The outbox intentionally has no cascade foreign key to `Documents`. Explicit delete or retention cleanup must not erase a completion fact before a future delivery policy has handled it.

A unique transition key over document, terminal status and processing-attempt count prevents repeated enqueue/retry paths from creating duplicate events for the same completion transition.

This milestone establishes only the durable transaction boundary. Outbound webhook delivery, signing, destination configuration and delivery retry state are intentionally separate concerns.

## Completion webhooks

Terminal completion events are delivered asynchronously from the persisted `DocumentCompletionOutbox`; document processing never performs outbound HTTP inline.

Webhook destinations are deployment configuration scoped by trusted `CustomerId`. Individual upload requests cannot supply callback URLs.

Delivery is **at least once**. Payloads include an immutable `eventId` so receivers can deduplicate a rare duplicate caused by a process crash after receiver success but before `DeliveredAt` is persisted.

Payload fields:

```text
eventId
eventType = document.completed
occurredAt
documentId
customerId
status
documentType
processingAttempts
```

Requests include:

```text
X-DocFlow-Event-Id: <event id>
X-DocFlow-Signature: sha256=<HMAC-SHA256 over exact request bytes>
```

Delivery state is persisted on the outbox row:

```text
DeliveryAttempts
NextDeliveryAttemptAt
LastDeliveryAttemptAt
LastDeliveryError
DeliveredAt
DeliveryAbandonedAt
```

Failures use bounded exponential backoff. After the configured maximum attempts the event is marked abandoned and automatic attempts stop.

Security boundaries:

- production destinations require HTTPS;
- redirects are disabled;
- proxy use is disabled;
- DNS is resolved inside the connection callback and the actual connected address is checked;
- loopback/private/link-local/multicast/reserved destination ranges are blocked outside Development;
- request timeout is bounded;
- response bodies are not consumed;
- secrets remain deployment configuration and are never persisted in the outbox.

Development can explicitly enable HTTP/private destinations for deterministic local E2E only.

The delivery worker remains within DocFlow's current **single-instance MVP** boundary. It does not provide distributed ownership across multiple active application replicas.

## Original PDF access

Authenticated tenants can retrieve the original source PDF through:

```text
GET /api/documents/{id}/file
```

The endpoint streams from `IFileStorage` rather than buffering the full file in memory. It returns `application/pdf`, uses a sanitized attachment filename derived from `OriginalFileName`, and enables ASP.NET Core range processing so clients can issue byte-range requests.

Cross-tenant and absent documents return `404`. If a database row exists but its backing storage file is missing, the API returns a sanitized `500` problem response without exposing filesystem or storage-key details; the underlying exception is logged server-side.

`GET /api/documents/{id}` now returns a stable relative `sourceFileUrl` such as `/api/documents/{id}/file`. New clients should use that API path for source-file access.

The legacy `storageKey` JSON property is still returned for backward compatibility, but generated OpenAPI marks it `deprecated: true` and directs clients to `sourceFileUrl`. It remains an internal storage locator, not a supported retrieval path. Removing the field entirely would still be a breaking contract change and should happen only behind an explicit future versioning decision.

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

- **DocFlow.Api** — authenticated single/batch intake, single/batch idempotency coordination, operator metrics surface, source-file streaming, lifecycle/delete, retention scheduling, processing diagnostics, startup recovery, health probes and background-service host.
- **DocFlow.Application** — processing/export/review/deletion abstractions plus process-local operational metric state.
- **DocFlow.Domain** — document, extraction-result, review and idempotency entities.
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

Completed MVP milestones include automated processing, conditional OCR, real-corpus benchmarking, hard-case extraction, degraded-OCR recovery, persisted-result CSV/XLSX export, tenant-scoped document inbox, human review, API-key tenant isolation, reproducible container deployment with health/readiness checks, bounded technical-failure retries with persisted processing diagnostics, single-instance restart recovery from PostgreSQL, tenant-scoped terminal document deletion with file/database cleanup, tenant-scoped original PDF streaming with range support, opt-in automatic retention for expired terminal documents, authenticated API-client attribution for review audit records, protected low-cardinality process-local operational metrics, bounded partial-success multi-PDF batch intake, persisted single-upload idempotency with physical cleanup, and persisted whole-request batch idempotency with durable per-item checkpoints.

Per-tenant retention overrides, fault-injected batch-resume verification, backward-compatible `StorageKey` deprecation, transactional completion outbox, and signed tenant-configured webhook delivery are now complete. The next operational gap is visibility and safe re-drive for abandoned webhook events: bounded retries stop correctly, but recovery currently requires direct database intervention.

Production code remains private. A separate public portfolio repository may be created later.
