# DocFlow — active handoff for 1.1.1.8 Export

Status: **ACTIVE**  
Working branch: `DocFlow/v_1.1.1.8_Export`  
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

Do not modify extraction/OCR behavior as part of this milestone unless an export test exposes an actual persistence-contract defect.

## 2. Purpose

Complete the remaining output leg of the initial MVP: export persisted structured extraction results to machine-usable CSV and Excel-compatible XLSX files.

Export must use the already persisted `ExtractionResult.StructuredDataJson`; it must **not** rerun OCR or Python extraction.

## 3. API contract

Target endpoint:

```text
GET /api/documents/{id}/export?format=csv
GET /api/documents/{id}/export?format=xlsx
```

Expected behavior:

- `200` with downloadable file when an extraction result exists;
- `400` for unsupported export format;
- `404` when the document has no persisted extraction result;
- deterministic filename based on original document name / document id;
- explicit content type and attachment filename.

## 4. Export representation

The persisted structured JSON is schema-flexible across quotations, invoices, hard cases and future document types. Export must therefore be generic rather than hard-coded to one supplier schema.

Canonical flattening rule:

```text
scalar object field       -> dot path
nested object field       -> parent.child
array scalar              -> parent.0, parent.1, ...
array object              -> parent.0.child, parent.1.child, ...
null                      -> empty value
```

Example paths:

```text
data.invoice_number
data.total
data.items.0.description
data.items.0.quantity
data.tax_breakdown.2.rate
```

CSV initial shape:

```text
Path,Value
```

XLSX initial shape:

```text
worksheet: Extraction Result
columns: Path | Value
```

This representation is deliberately lossless with respect to scalar leaf values and works across current/future structured schemas. A later product milestone may add business-specific tabular templates if required.

## 5. Architecture

- `DocFlow.Application`: export abstraction/result/format contract.
- `DocFlow.Infrastructure`: persisted-result lookup + deterministic CSV/XLSX serialization.
- `DocFlow.Api`: thin HTTP endpoint and status/content-type mapping.
- no Python worker involvement.
- no database schema migration expected.

Prefer no new third-party spreadsheet dependency if a small standards-compliant OOXML writer is sufficient for the two-column workbook.

## 6. Acceptance criteria

1. CSV export returns all scalar leaves from persisted structured data using deterministic dot paths.
2. CSV quoting handles commas, quotes, CR/LF and Unicode safely.
3. XLSX is a valid OOXML ZIP package and contains the same logical path/value rows as CSV.
4. Export preserves numbers/booleans/text as their JSON textual value without locale-dependent formatting.
5. Missing extraction result returns 404.
6. Unsupported format returns 400 without querying/reprocessing Python.
7. Existing upload/extraction persistence behavior remains unchanged.
8. Unit/integration coverage is added for flattening and both output formats.
9. Run CI only after a coherent export block; use `[skip ci]` for intermediate commits.

## 7. Immediate next action

Inspect current DI registration and test project structure, then implement the application export contract and infrastructure serializer/service.
