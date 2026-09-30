# Changelog

All notable changes to DocFlow are documented in this file.

## [1.1.1.2] - 2026-09-30

Automatic background processing milestone for the already verified supplier quotation pipeline.

### Added

- `IExtractionResultService` application abstraction and `ExtractionResultService` infrastructure implementation.
  - document lookup
  - duplicate extraction-result check
  - `ExtractionResult` creation
  - final `Document` status update
  - EF Core persistence
- `IDocumentExtractionRunner` application abstraction.
- `PythonDocumentExtractionRunner` infrastructure adapter.
  - launches the existing Python CLI through `ProcessStartInfo`
  - passes storage root and storage key
  - writes structured extraction output to a temporary worker output file
  - captures stdout/stderr and exit code
  - maps Python validation status to .NET `ValidationStatus`
  - cleans temporary structured output after reading it
  - supports configured Python executable and local `.venv` discovery on Windows/Linux
- `IDocumentProcessingService` and `DocumentProcessingService` orchestration.
  - `Uploaded`/retryable document lookup
  - `Processing` transition before extraction
  - Python extraction invocation
  - extraction result persistence
  - `Processed` / `NeedsReview` final state
  - `Failed` on technical processing errors
  - no-op when an extraction result already exists
- `IDocumentProcessingQueue` and `DocumentProcessingQueue` based on `System.Threading.Channels`.
- `DocumentProcessingBackgroundService`.
  - single queue consumer
  - a new DI scope per document
  - scoped `DocFlowDbContext` per processing operation
  - errors are logged without stopping subsequent queue processing
- Automatic enqueue after successful `POST /api/documents` persistence.
- Manual/retry endpoint:
  - `POST /api/documents/{id}/process`
  - returns `202 Accepted` when an existing document is queued
- Extraction worker configuration through `ExtractionWorker:RootPath` and optional `ExtractionWorker:PythonExecutable`.
- Automation E2E GitHub Actions workflow with PostgreSQL 16, .NET 8 and Python 3.11.
- Synthetic supplier quotation generator for E2E verification.
- `.NET CI` and `Python Worker CI` execution on the `DocFlow/v_1.1.1.2_Automation` branch and manual `workflow_dispatch` support.

### Changed

- `DocumentsController.SaveExtractionResult()` no longer owns EF persistence/orchestration logic; it validates the HTTP payload, delegates to `IExtractionResultService`, and maps application outcomes to HTTP responses.
- Upload now returns after the document has been stored and queued; Python extraction runs in the background instead of blocking the request.
- The worker invocation boundary is isolated from controllers and application orchestration behind `IDocumentExtractionRunner`.

### Verified

The automatic flow now requires only the upload request:

```text
POST /api/documents
  ↓
Document = Uploaded
  ↓
in-process queue
  ↓
Document = Processing
  ↓
Python deterministic supplier quotation extraction
  ↓
deterministic validation
  ↓
.NET ExtractionResult persistence
  ↓
Processed / NeedsReview / Failed
```

The valid synthetic supplier quotation completed automatically with:

```text
Document status: Processed
Document type: supplier_quotation
Engine: deterministic_supplier_quotation_v1
Validation status: Valid
Confidence: 1.0
Subtotal: 1457.00 EUR
VAT 20%: 291.40 EUR
Total: 1748.40 EUR
Items checked: 5
```

Automation E2E also verifies:

- repeated manual enqueue does not create a second `ExtractionResult`;
- an arithmetic mismatch outside the validator tolerance produces `ValidationStatus = Invalid` and `Document.Status = NeedsReview`;
- a Python technical failure produces `Document.Status = Failed` and no persisted extraction result;
- database migrations, .NET build and Python worker installation work in a clean CI environment.

### Architectural decisions

- Python worker still does not write directly to PostgreSQL; .NET remains the persistence owner.
- The MVP processing queue is intentionally in-process and uses `System.Threading.Channels`.
- RabbitMQ, Kafka and Redis remain deferred until durability/distribution requirements justify them.
- A background singleton never retains a scoped `DbContext`; each dequeued document is processed in a newly created DI scope.
- Worker execution is isolated in Infrastructure; controller/application orchestration does not construct `ProcessStartInfo` directly.
- The one-to-zero-or-one database constraint on `Document` → `ExtractionResult` remains the final database guard for idempotency, with application-level duplicate checks providing normal retry behavior.

### Development handoff

The active implementation plan that produced this milestone is stored at:

```text
docs/HANDOFF_v1.1.1.2_Automation.md
```

The completed-state handoff is stored at:

```text
docs/HANDOFF_v1.1.1.2_COMPLETED.md
```

The next robustness stage should validate increasingly difficult document inputs before adding heavier infrastructure or ML/LLM extraction:

1. digital supplier quotation without table borders;
2. supplier invoice;
3. scanned PDF with OCR;
4. dirty/real supplier PDFs;
5. only then decide where deterministic extraction needs ONNX/LLM fallback.

## [1.1.1.1] - 2026-09-30

Initial end-to-end MVP milestone for supplier quotation processing.

### Added

- .NET 8 solution with projects:
  - `DocFlow.Api`
  - `DocFlow.Application`
  - `DocFlow.Domain`
  - `DocFlow.Infrastructure`
  - `DocFlow.Extraction.Worker`
- ASP.NET Core Web API with Swagger/OpenAPI.
- PostgreSQL 16 persistence through EF Core 8 and Npgsql.
- `Document` and `ExtractionResult` domain entities.
- `DocumentStatus` and `ValidationStatus` state models.
- `IFileStorage` abstraction and local file storage implementation.
- PDF upload endpoint:
  - `POST /api/documents`
  - customer id validation
  - non-empty file validation
  - 20 MB size limit
  - `.pdf` extension validation
  - `application/pdf` content type validation
  - `%PDF-` signature validation
  - storage compensation when database persistence fails
- Document metadata endpoint:
  - `GET /api/documents/{id}`
- Extraction result persistence endpoint:
  - `POST /api/documents/{id}/extraction-result`
- Extraction result read endpoint:
  - `GET /api/documents/{id}/extraction-result`
- One-to-zero-or-one relationship between `Document` and `ExtractionResult`.
- `StructuredDataJson` persisted as PostgreSQL `jsonb`.
- Python 3.11 extraction worker with PyMuPDF, pdfplumber, Pydantic v2 and pytest.
- Provider-neutral document layout model:
  - pages
  - text blocks
  - words
  - bounding boxes
  - tables
  - page/text statistics
  - OCR-needed detection
- PDF layout extraction from digital PDFs.
- Provider-neutral `StructuredExtractionEngine` abstraction.
- Deterministic supplier quotation engine:
  - `deterministic_supplier_quotation_v1`
- Supplier quotation semantic model with:
  - supplier metadata
  - quotation metadata
  - currency
  - customer reference
  - Incoterms
  - line items
  - subtotal
  - VAT
  - total
  - payment terms
  - delivery
  - warranty
  - notes
  - prepared-by field
  - quote status
- Deterministic arithmetic validation for:
  - item line totals
  - subtotal
  - VAT amount
  - grand total
- Structured validation result with:
  - `valid`
  - `invalid`
  - `incomplete`
  - detailed check results
  - confidence value
- Python CLI support for semantic extraction and structured JSON output.
- Dedicated local worker output directory:
  - `src/DocFlow.Extraction.Worker/output/`
  - simple output file names are automatically written there
  - generated extraction artifacts are excluded from Git
- Python package metadata directories (`*.egg-info/`) are excluded from Git.
- GitHub Actions CI for both .NET and Python worker.

### Verified

A synthetic digital supplier quotation was processed successfully through the complete manual pipeline:

```text
PDF upload
  ↓
file storage + Document metadata
  ↓
Python layout extraction
  ↓
deterministic semantic extraction
  ↓
deterministic validation
  ↓
StructuredExtractionResult
  ↓
.NET API persistence
  ↓
ExtractionResults in PostgreSQL
  ↓
GET result back from PostgreSQL
```

The verified quotation produced:

```text
Document type: supplier_quotation
Engine: deterministic_supplier_quotation_v1
Validation status: valid
Confidence: 1.0
Subtotal: 1457.00 EUR
VAT 20%: 291.40 EUR
Total: 1748.40 EUR
Items checked: 5
```

The persisted document finished with status `Processed`.

### Architectural decisions

- Python worker does not write directly to PostgreSQL.
- .NET owns application flow and persistence.
- Semantic extraction is separated from deterministic validation.
- Structured extraction consumes `DocumentContent` with blocks/tables instead of relying only on raw page text.
- Runtime extraction artifacts are separated from source code and kept in the ignored worker `output/` directory.
- Heavy infrastructure such as RabbitMQ, Kafka, Redis and Kubernetes is intentionally deferred until justified by the system requirements.

### Known limitations

The following are not part of version 1.1.1.1:

- automatic worker invocation after document upload
- background processing orchestration
- OCR implementation
- ONNX semantic extraction
- external LLM extraction
- hybrid fallback logic
- borderless quotation support validation
- invoice extraction
- scanned/dirty real supplier document benchmarks
- human review UI
- authentication/authorization
- billing
- Excel/CSV export
- production S3-compatible storage

### Development handoff

The complete technical handoff for continuing development after this version is stored at:

```text
docs/HANDOFF_v1.1.1.1.md
```

It contains:

- current project architecture and stack
- database entities and statuses
- API endpoints
- Python extraction and validation pipeline
- verified test document identifiers and results
- local development commands
- current limitations
- architectural constraints
- the recommended next development stage
- acceptance criteria for the next stage

The next planned milestone is automatic processing orchestration: removing the manual steps between PDF upload, Python extraction/validation and .NET persistence.
