# DocFlow — completed handoff for version 1.1.1.2 Automation

Date completed: 2026-09-30  
Implementation branch: `DocFlow/v_1.1.1.2_Automation`

## 1. Milestone result

Version 1.1.1.2 removes the manual bridge that existed in 1.1.1.1 between document upload, Python extraction and .NET persistence.

The production flow is now:

```text
POST /api/documents
        ↓
file saved through IFileStorage
        ↓
Document persisted with Status = Uploaded
        ↓
DocumentId enqueued in IDocumentProcessingQueue
        ↓
HTTP 201 returned to caller
        ↓
DocumentProcessingBackgroundService dequeues DocumentId
        ↓
new DI scope
        ↓
IDocumentProcessingService
        ↓
Document = Processing
        ↓
IDocumentExtractionRunner
        ↓
PythonDocumentExtractionRunner
        ↓
existing Python deterministic supplier quotation CLI
        ↓
StructuredExtractionResult JSON
        ↓
IExtractionResultService
        ↓
ExtractionResult persisted in PostgreSQL
        ↓
Processed / NeedsReview
```

A technical processing exception is handled as:

```text
processing exception
        ↓
Document = Failed
        ↓
error logged by background worker
        ↓
worker continues with next queued document
```

The user no longer needs to run the Python CLI manually or POST the structured extraction JSON manually through Swagger.

## 2. New application abstractions

### `IExtractionResultService`

Location:

```text
src/DocFlow.Application/Abstractions/IExtractionResultService.cs
```

Responsibilities:

- persist one extraction result for a document;
- detect document-not-found;
- detect already-existing extraction result;
- set `Processed` for a valid result;
- set `NeedsReview` for invalid/incomplete results.

### `IDocumentExtractionRunner`

Location:

```text
src/DocFlow.Application/Abstractions/IDocumentExtractionRunner.cs
```

Boundary between .NET orchestration and the external extraction implementation.

Returns:

- raw `StructuredDataJson`;
- `DocumentType`;
- `Confidence`;
- .NET `ValidationStatus`.

### `IDocumentProcessingService`

Location:

```text
src/DocFlow.Application/Abstractions/IDocumentProcessingService.cs
```

Owns one processing operation for a `DocumentId`.

### `IDocumentProcessingQueue`

Location:

```text
src/DocFlow.Application/Abstractions/IDocumentProcessingQueue.cs
```

Provides:

```text
EnqueueAsync(DocumentId)
DequeueAsync()
```

## 3. Infrastructure implementations

### `ExtractionResultService`

Location:

```text
src/DocFlow.Infrastructure/Processing/ExtractionResultService.cs
```

Behavior:

1. loads `Document`;
2. checks for an existing `ExtractionResult`;
3. creates the new `ExtractionResult`;
4. maps valid → `MarkProcessed(documentType)`;
5. maps non-valid → `MarkNeedsReview(documentType)`;
6. calls `SaveChangesAsync`.

### `PythonDocumentExtractionRunner`

Location:

```text
src/DocFlow.Infrastructure/Processing/PythonDocumentExtractionRunner.cs
```

Invokes the existing Python worker using `ProcessStartInfo`.

CLI shape:

```text
main.py
  --storage-root <storage-root>
  --storage-key <document-storage-key>
  --document-type supplier_quotation
  --output-structured-json <temporary-output-name>
```

The runner:

- redirects stdout/stderr;
- checks the process exit code;
- supports cancellation and kills the process tree on cancellation;
- reads structured JSON from the worker output directory;
- validates the minimum result contract;
- maps `valid`, `invalid`, `incomplete` to .NET validation states;
- deletes the temporary structured output file in `finally`;
- supports explicit Python executable configuration;
- otherwise discovers `.venv/Scripts/python.exe` on Windows or `.venv/bin/python` on Unix before falling back to system `python` / `python3`.

### `DocumentProcessingService`

Location:

```text
src/DocFlow.Infrastructure/Processing/DocumentProcessingService.cs
```

Behavior:

```text
DocumentId
  ↓
load Document
  ↓
if ExtractionResult already exists → no-op
  ↓
MarkProcessing + SaveChanges
  ↓
run Python extraction
  ↓
save extraction result
  ↓
Processed / NeedsReview
```

On a non-cancellation technical exception it clears the current EF change tracker, reloads the document and attempts to mark it `Failed`, preserving the original exception.

### `DocumentProcessingQueue`

Location:

```text
src/DocFlow.Infrastructure/Processing/DocumentProcessingQueue.cs
```

Implementation:

```text
System.Threading.Channels
```

Current configuration:

- unbounded channel;
- one reader;
- multiple writers;
- asynchronous continuations.

This is intentionally an in-process MVP queue, not durable distributed messaging.

## 4. Background worker

Location:

```text
src/DocFlow.Api/BackgroundServices/DocumentProcessingBackgroundService.cs
```

The hosted service:

1. waits for a `DocumentId`;
2. creates a new DI scope;
3. resolves scoped `IDocumentProcessingService`;
4. processes the document;
5. logs success or failure;
6. continues with the next queue item.

Important lifetime rule:

> The singleton background service does not hold a `DocFlowDbContext`. A new scoped processing service/DbContext is resolved per dequeued document.

## 5. API behavior

Existing endpoints remain:

```http
POST /api/documents
GET  /api/documents/{id}
POST /api/documents/{id}/extraction-result
GET  /api/documents/{id}/extraction-result
```

New endpoint:

```http
POST /api/documents/{id}/process
```

Purpose:

- manual retry;
- development/debugging;
- enqueue an already stored document without re-upload.

Returns:

```text
404  document does not exist
202  document accepted into processing queue
```

`POST /api/documents` now:

1. validates the PDF;
2. stores the file;
3. persists `Document`;
4. enqueues `Document.Id`;
5. returns HTTP 201 without waiting for Python processing.

The returned status can therefore still be `Uploaded`; processing continues asynchronously.

## 6. Status transitions

Verified behavior:

```text
Uploaded
  ↓
Processing
  ├── valid       → Processed
  ├── invalid     → NeedsReview
  ├── incomplete  → NeedsReview
  └── exception   → Failed
```

`Processed` is set only as part of successful extraction-result persistence.

## 7. Idempotency

There are two layers:

### Application layer

`DocumentProcessingService` checks whether an extraction result already exists and returns without running extraction again.

`ExtractionResultService` separately returns `AlreadyExists` if a result is already present.

### Database layer

The unique index on:

```text
ExtractionResults.DocumentId
```

remains the final database constraint enforcing one extraction result per document.

Repeated enqueue of an already processed document was verified not to create a second result.

## 8. Configuration

API configuration now includes:

```json
"ExtractionWorker": {
  "RootPath": "../DocFlow.Extraction.Worker"
}
```

Optional override:

```text
ExtractionWorker:PythonExecutable
```

`FileStorage:RootPath` remains the storage root shared by .NET storage and the Python runner.

## 9. CI changes

### `.NET CI`

Runs on push to:

```text
main
DocFlow/v_1.1.1.2_Automation
```

and supports `workflow_dispatch`.

### `Python Worker CI`

Runs on the same active automation branch for worker changes and supports `workflow_dispatch`.

### `Automation E2E`

Location:

```text
.github/workflows/automation-e2e.yml
```

A clean GitHub runner performs:

```text
PostgreSQL 16 service
  ↓
.NET 8 setup
  ↓
Python 3.11 setup
  ↓
Python worker installation
  ↓
.NET restore/build
  ↓
EF migration
  ↓
generate synthetic PDF fixtures
  ↓
start API
  ↓
exercise real HTTP/background/Python/PostgreSQL flow
```

## 10. Verified acceptance scenarios

The final Automation E2E acceptance run is green.

### Scenario 1 — valid quotation

Expected and verified:

```text
Upload response status: Uploaded
Final document status: Processed
Document type: supplier_quotation
Engine: deterministic_supplier_quotation_v1
Validation status: Valid
Confidence: 1.0
Subtotal: 1457.00 EUR
VAT rate: 20%
VAT amount: 291.40 EUR
Total: 1748.40 EUR
Items: 5
```

### Scenario 2 — repeated enqueue

The processed document is manually queued twice through:

```http
POST /api/documents/{id}/process
```

Verified:

- both enqueue requests are accepted;
- original `ExtractionResult.Id` remains unchanged;
- no second extraction result is created;
- document remains `Processed`.

### Scenario 3 — invalid arithmetic

The synthetic quotation total is changed to:

```text
1748.42 EUR
```

instead of expected:

```text
1748.40 EUR
```

The difference is intentionally greater than the validator tolerance of `0.01`.

Verified:

```text
Structured validation: invalid
.NET ValidationStatus: Invalid
Document status: NeedsReview
grand_total check: failed
```

### Scenario 4 — Python technical failure

A test document points to a deliberately missing storage file and is queued through the manual process endpoint.

Verified:

```text
Document status: Failed
ExtractionResult: not created
GET extraction-result: 404
```

## 11. Important non-goals retained

Version 1.1.1.2 still does not add:

- RabbitMQ;
- Kafka;
- Redis;
- Kubernetes;
- ONNX semantic extraction;
- external LLM extraction;
- OCR;
- invoice extractor;
- S3 migration;
- authentication/billing;
- frontend/review UI.

## 12. Current limitations

The queue is intentionally in-process. Therefore queued items are not durable across API process restarts. This is acceptable for this local MVP milestone but must be revisited before a production deployment that requires durable job delivery.

The extraction runner is currently hard-wired to the already proven:

```text
supplier_quotation
```

path. Document-type routing is a later concern.

The current successful fixture is a clean digital supplier quotation. Real-world robustness has not yet been established for borderless, scanned or dirty supplier documents.

## 13. Next development stage

Do not add distributed infrastructure yet.

Recommended robustness order:

1. digital supplier quotation without table borders;
2. supplier invoice;
3. scanned supplier document + OCR;
4. dirty/real supplier PDFs;
5. measure deterministic extraction failure modes;
6. only then introduce ONNX/LLM fallback where evidence shows deterministic extraction is insufficient.

The architectural invariant remains:

> Python performs extraction/validation; .NET owns application orchestration, statuses and persistence.
