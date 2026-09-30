# Changelog

All notable changes to DocFlow are documented in this file.

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
