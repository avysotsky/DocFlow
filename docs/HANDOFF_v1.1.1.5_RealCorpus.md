# DocFlow — active handoff for version 1.1.1.5 RealCorpus

Status: **ACTIVE — tooling ready, real supplier corpus not yet evaluated**  
Working branch: `DocFlow/v_1.1.1.5_RealCorpus`  
Started from completed milestone: `DocFlow/v_1.1.1.4_Benchmarking`

## 1. Objective

Version 1.1.1.5 exists to replace synthetic-only confidence with measured evidence from representative third-party supplier documents.

This milestone must **not** be marked completed until a real corpus and independently recorded ground truth have been evaluated.

Target evidence:

```text
private supplier PDFs
        ↓
corpus inventory
        ↓
manifest + manually recorded ground truth
        ↓
corpus audit
        ↓
current deterministic + OCR pipeline
        ↓
benchmark report
        ↓
overall + grouped accuracy
        ↓
failure classes
        ↓
architectural decision based on measured failures
```

## 2. Privacy boundary

Real supplier PDFs, expected business values and generated reports remain local/private and are not committed to Git.

Ignored paths:

```text
benchmarks/corpus/
benchmarks/results/
benchmarks/manifest.local.json
```

Tracked repository content contains only tooling, schemas, instructions and synthetic CI fixtures.

## 3. Corpus inventory

Core module:

```text
src/DocFlow.Extraction.Worker/docflow_worker/corpus_inventory.py
```

CLI:

```text
src/DocFlow.Extraction.Worker/corpus_inventory.py
```

Inventory records technical corpus metadata only:

- corpus root;
- relative path;
- stable suggested id;
- SHA-256;
- file size;
- page count;
- pages with native PDF text;
- source kind: `digital`, `scanned`, `mixed`, `unknown`;
- duplicate-content relationship;
- PDF inspection errors.

Duplicate detection is based on SHA-256 content, not filenames.

## 4. Real-corpus manifest

Tracked example:

```text
benchmarks/manifest.example.json
```

Local working manifest:

```text
benchmarks/manifest.local.json
```

Entries support:

```json
{
  "id": "supplier-a-invoice-001",
  "file": "corpus/supplier-a-invoice-001.pdf",
  "sha256": "...",
  "metadata": {
    "supplier": "supplier-a",
    "source_kind": "digital",
    "layout_class": "multi-page-table",
    "language": "en",
    "tags": ["invoice", "vat"]
  },
  "document_type": "auto",
  "expected": {
    "document_type": "supplier_invoice",
    "validation_status": "valid",
    "fields": {
      "data.invoice_number": "...",
      "data.currency": "EUR",
      "data.total": "..."
    }
  }
}
```

Ground truth must be read independently from the source PDF. Do not copy DocFlow output into `expected.fields`.

## 5. SHA-256 integrity

The benchmark verifies the actual PDF digest before parsing it.

A manifest/file mismatch becomes:

```text
corpus_integrity_error
```

and extraction is skipped for that case.

## 6. Corpus audit

Core module:

```text
src/DocFlow.Extraction.Worker/docflow_worker/corpus_audit.py
```

CLI:

```text
src/DocFlow.Extraction.Worker/corpus_audit.py
```

The audit works by **unique PDF content SHA**, not by a filename selected as a canonical copy.

If several files contain identical bytes:

- inventory reports duplicate copies;
- any one copy may represent that SHA in the manifest;
- extra copies are warnings;
- representing the same SHA more than once in the manifest is an error.

Audit errors include:

- manifest PDF missing from inventory;
- a unique corpus SHA absent from manifest;
- missing real-corpus SHA-256;
- SHA mismatch;
- same content SHA benchmarked more than once;
- source-kind mismatch;
- PDF inspection failure;
- same path repeated in manifest.

Audit warnings include:

- duplicate copies in the corpus;
- missing supplier/layout/language metadata;
- source kind not recorded in manifest;
- no field-level ground truth.

## 7. Benchmark report

Benchmark CLI:

```text
src/DocFlow.Extraction.Worker/benchmark.py
```

Overall metrics:

```text
document_pass_rate
document_type_accuracy
validation_status_accuracy
field_accuracy
failure_reason_counts
```

Failure classes:

```text
corpus_integrity_error
processing_error
document_type_mismatch
validation_status_mismatch
missing_field
field_mismatch
```

Grouped metrics:

```text
breakdowns.by_supplier
breakdowns.by_source_kind
breakdowns.by_layout_class
breakdowns.by_language
```

The grouped metrics are required to distinguish systematic failure classes such as OCR failures, one supplier template, one layout type or one language.

## 8. Unified local runner

User-facing entry point:

```text
src/DocFlow.Extraction.Worker/real_corpus.py
```

Once `manifest.local.json` contains independently recorded ground truth, the complete workflow can be run with one command:

```bash
cd src/DocFlow.Extraction.Worker
python real_corpus.py \
  --corpus ../../benchmarks/corpus \
  --manifest ../../benchmarks/manifest.local.json \
  --results ../../benchmarks/results
```

The runner performs:

```text
inventory
  ↓
write corpus-inventory.json
  ↓
stop if PDF inspection errors exist
  ↓
audit manifest against inventory
  ↓
write corpus-audit.json
  ↓
stop if audit errors exist
  ↓
benchmark current deterministic + OCR pipeline
  ↓
write benchmark-report.json
```

Options include:

```text
--fail-on-warnings
--disable-ocr
--ocr-language
--ocr-dpi
--tessdata
```

Exit behavior:

```text
0  benchmark completed and every case passed
1  benchmark completed with failed cases
2  inventory contained PDF inspection errors
3  audit blocked the benchmark
```

The individual `corpus_inventory.py`, `corpus_audit.py` and `benchmark.py` CLIs remain available for diagnostics.

## 9. CI state

The real-corpus tooling is covered by unit tests and synthetic smoke CI.

Verified after content-hash audit semantics were finalized:

```text
Python Worker CI: success
Benchmark Smoke: success
Automation E2E: success
Scanned OCR E2E: success
```

Benchmark Smoke covers the same stages expected locally:

```text
generate quotation/invoice + duplicate copy
        ↓
inventory
        ↓
manifest pinned to inventory SHA values
        ↓
audit
        ↓
benchmark
        ↓
verify overall metrics + metadata breakdowns
```

The smoke workflow has also been updated to execute the unified `real_corpus.py` entry point directly.

## 10. Required real input before this milestone can close

The remaining dependency is external evidence:

1. representative real supplier quotation/invoice PDFs;
2. one manifest case per unique content SHA;
3. independently transcribed expected fields;
4. useful metadata (`supplier`, `source_kind`, `layout_class`, `language`);
5. Tesseract language data for scanned non-English documents.

A useful first batch should prefer **diversity over volume**.

Suggested initial target:

```text
10–20 unique documents
5+ supplier/layout families
quotation + invoice
some digital PDFs
some scanned/OCR PDFs
at least one multi-page document if available
```

This is a practical starting point, not a statistical production-accuracy claim.

## 11. Completion criteria for 1.1.1.5

Do not create the next architecture branch merely because the tooling is green.

Version 1.1.1.5 can be considered complete when:

1. a representative real corpus has been inventoried;
2. audit has no unresolved errors;
3. ground truth was entered independently from DocFlow output;
4. the real benchmark has run to completion;
5. overall metrics are recorded;
6. supplier/source/layout/language breakdowns are recorded;
7. dominant failure classes are identified;
8. concrete failed documents/fields are reviewed;
9. there is enough evidence to choose the next response per failure class:
   - deterministic rule improvement;
   - OCR improvement;
   - document-type detection improvement;
   - ONNX/local model experiment;
   - external LLM fallback experiment.

## 12. Immediate next action

Populate locally:

```text
benchmarks/corpus/
```

Run `corpus_inventory.py` once to obtain SHA values/source kinds, enter independent ground truth in `manifest.local.json`, then use:

```bash
python real_corpus.py \
  --corpus ../../benchmarks/corpus \
  --manifest ../../benchmarks/manifest.local.json \
  --results ../../benchmarks/results
```

After `corpus-inventory.json`, `corpus-audit.json` and `benchmark-report.json` exist, analyze measured failure clusters rather than adding extraction technology speculatively.

---

Current status: **technical preparation for real-corpus measurement is green; real-corpus evidence is still missing.**
