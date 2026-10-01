# DocFlow — completed handoff for 1.1.1.8 Export

Status: **COMPLETED**  
Completed branch: `DocFlow/v_1.1.1.8_Export`  
Started from completed milestone: `DocFlow/v_1.1.1.7_DegradedOCR`

## Completed capability

DocFlow now exports already persisted `ExtractionResult.StructuredDataJson` without rerunning OCR or Python extraction.

API:

```text
GET /api/documents/{id}/export?format=csv
GET /api/documents/{id}/export?format=xlsx
```

Generic flattening uses deterministic indexed dot paths across nested objects and arrays.

CSV:

```text
Path,Value
```

XLSX:

```text
worksheet: Extraction Result
columns: Path | Value
```

The XLSX workbook is generated as a minimal OOXML package using only .NET BCL APIs; no spreadsheet package dependency was introduced.

## Architecture

Added:

```text
DocFlow.Application/Abstractions/IExtractionResultExportService.cs
DocFlow.Infrastructure/Export/ExtractionResultExportService.cs
DocFlow.Infrastructure/Export/StructuredDataTabularExporter.cs
DocFlow.Api/Controllers/DocumentExportsController.cs
.github/scripts/verify_document_export.py
```

`Program.cs` registers the scoped export service.

No database migration was required.

## Verification

Automation E2E #97 on head `eac728b1e0f80cdb7bc67d44876bf0a64662d481` is fully green.

```text
.NET build: SUCCESS
0 warnings
0 errors

existing processing scenarios: SUCCESS
persisted supplier invoice: SUCCESS
CSV export: SUCCESS
XLSX export: SUCCESS
CSV/XLSX logical equivalence: SUCCESS
XLSX OOXML package validation: SUCCESS
400 unsupported format: SUCCESS
404 missing extraction result: SUCCESS
```

Runtime log confirmation:

```text
Export E2E passed: CSV/XLSX content, equivalent flattened rows,
unsupported format and missing-result behavior verified.
```

Extraction/OCR code was unchanged, so the existing Public Reference #78 baseline remains authoritative and was not rerun.

## Inherited extraction baseline

```text
Public Reference Benchmark #78: SUCCESS
69 Python tests
17/17 public documents
98/98 checked fields
17/17 document types
17/17 validation statuses
```

## Final status

Milestone `1.1.1.8 Export` is complete.

The initial end-to-end MVP path is now present:

```text
PDF upload
-> native text / conditional OCR
-> automatic document classification
-> deterministic structured extraction
-> deterministic validation
-> PostgreSQL persistence
-> CSV/XLSX export
```

ONNX/LLM fallback remains deferred because measured extraction failures to date were solved deterministically.
