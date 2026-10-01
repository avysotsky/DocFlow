# DocFlow — completed handoff for 1.1.1.8 Export

Status: **COMPLETED**  
Completed branch: `DocFlow/v_1.1.1.8_Export`  
Started from completed milestone: `DocFlow/v_1.1.1.7_DegradedOCR`

## 1. Starting baseline

```text
Public Reference Benchmark #78: SUCCESS
69 Python tests
17/17 public documents
98/98 checked fields
17/17 document types
17/17 validation statuses

Automation E2E #96: SUCCESS
Scanned OCR E2E #73: SUCCESS
```

Extraction/OCR behavior was intentionally left unchanged throughout this milestone.

## 2. Purpose

Complete the output leg of the initial MVP: export already persisted structured extraction results to machine-usable CSV and Excel-compatible XLSX files.

Export reads `ExtractionResult.StructuredDataJson` from PostgreSQL. It does **not** rerun OCR, document detection, Python extraction, or validation.

## 3. Delivered API contract

```text
GET /api/documents/{id}/export?format=csv
GET /api/documents/{id}/export?format=xlsx
```

Verified behavior:

- `200` with attachment when a persisted extraction result exists;
- `400` for an unsupported format;
- `404` when no persisted extraction result exists;
- explicit content type;
- deterministic attachment filename based on the original document filename, with sanitization/fallback to document id.

## 4. Generic export representation

Export is schema-independent and works over the persisted structured JSON rather than being hard-coded to quotation or invoice DTOs.

Canonical flattening rule:

```text
scalar object field       -> dot path
nested object field       -> parent.child
array scalar              -> parent.0, parent.1, ...
array object              -> parent.0.child, parent.1.child, ...
null                      -> empty value
```

Examples:

```text
data.invoice_number
data.total
data.items.0.description
data.items.0.quantity
data.tax_breakdown.2.rate
```

Object properties are ordered ordinally during flattening, producing deterministic output.

## 5. CSV implementation

CSV format:

```text
Path,Value
```

Implementation properties:

- UTF-8 with BOM for spreadsheet compatibility;
- CRLF row endings;
- every cell is quoted;
- embedded quotes are doubled according to CSV escaping rules;
- Unicode is preserved;
- JSON numbers use their stored textual representation rather than locale-specific formatting;
- booleans are emitted as `true` / `false`;
- null is emitted as an empty value.

## 6. XLSX implementation

XLSX format:

```text
worksheet: Extraction Result
columns: Path | Value
```

A minimal OOXML workbook is generated directly using .NET `System.IO.Compression` and `XmlWriter`; no spreadsheet NuGet dependency was added.

The package contains the required workbook parts:

```text
[Content_Types].xml
_rels/.rels
xl/workbook.xml
xl/_rels/workbook.xml.rels
xl/worksheets/sheet1.xml
```

Values are stored as inline strings, preserving the same logical path/value representation as CSV.

## 7. Architecture delivered

### Application

Added:

```text
IExtractionResultExportService
ExtractionResultExportFormat
ExtractionResultExportFile
```

### Infrastructure

Added:

```text
Export/ExtractionResultExportService.cs
Export/StructuredDataTabularExporter.cs
```

The export service performs an `AsNoTracking()` lookup of the persisted `ExtractionResult` and original document filename, then serializes the stored JSON.

### API

Added:

```text
DocumentExportsController
```

The controller is intentionally thin: query-format parsing, service invocation, HTTP status mapping and `File(...)` response only.

### DI

Registered:

```text
IExtractionResultExportService -> ExtractionResultExportService
```

No database migration was required.

## 8. Integration verification

Added:

```text
.github/scripts/verify_document_export.py
```

Automation E2E Scenario 7 uses an invoice that has already passed the normal upload -> extraction -> validation -> PostgreSQL persistence flow and then verifies export from the persisted result.

The verifier checks:

- CSV download and content type;
- XLSX download and content type;
- attachment filenames;
- key persisted invoice fields;
- indexed item-array paths such as `data.items.0.*`;
- CSV/XLSX logical row equivalence;
- XLSX ZIP/OOXML structure and worksheet XML;
- unsupported format -> `400`;
- document without extraction result -> `404`.

## 9. Final validation

Exactly one CI run was used for the coherent Export block:

```text
Automation E2E #97: SUCCESS
head: eac728b1e0f80cdb7bc67d44876bf0a64662d481
```

Build result:

```text
Build succeeded.
0 Warning(s)
0 Error(s)
```

Runtime evidence:

```text
Export E2E passed: CSV/XLSX content, equivalent flattened rows,
unsupported format and missing-result behavior verified.

Automation E2E passed: quotations, idempotency, review/failure routing,
borderless layout, supplier invoice and CSV/XLSX export verified.
```

Public Reference Benchmark and Scanned OCR E2E were intentionally not rerun because this milestone did not modify extraction/OCR code.

## 10. Acceptance criteria status

- persisted structured JSON exports through deterministic dot paths: **met**;
- CSV escaping/UTF-8 implementation: **met**;
- XLSX valid OOXML ZIP package: **met**;
- CSV and XLSX expose equivalent logical rows: **met**;
- locale-independent scalar serialization: **met**;
- missing extraction result -> 404: **met**;
- unsupported format -> 400: **met**;
- existing processing/persistence flow unchanged and green: **met**;
- integration coverage for both formats: **met**;
- CI batching discipline: **met**.

## 11. Final milestone baseline

```text
Public Reference Benchmark #78: SUCCESS (inherited, extraction unchanged)
69 Python tests
17/17 public documents
98/98 checked fields

Automation E2E #97: SUCCESS
.NET build: 0 warnings / 0 errors
CSV export: verified
XLSX export: verified
400 unsupported format: verified
404 missing extraction result: verified
```

Milestone `1.1.1.8 Export` is complete.
