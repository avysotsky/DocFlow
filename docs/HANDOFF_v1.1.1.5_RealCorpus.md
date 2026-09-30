# DocFlow — active handoff for version 1.1.1.5 RealCorpus

Status: **ACTIVE — infrastructure ready, real corpus not yet evaluated**  
Working branch: `DocFlow/v_1.1.1.5_RealCorpus`  
Started from completed milestone: `DocFlow/v_1.1.1.4_Benchmarking`

## 1. Objective

Version 1.1.1.5 exists to replace synthetic-only confidence with measured evidence from representative third-party supplier documents.

This milestone must **not** be marked completed until a real corpus and independently recorded ground truth have been evaluated.

The target evidence is:

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

Run:

```bash
cd src/DocFlow.Extraction.Worker
python corpus_inventory.py \
  --corpus ../../benchmarks/corpus \
  --output ../../benchmarks/results/corpus-inventory.json
```

Inventory records only technical corpus metadata, not supplier business fields:

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

Real-corpus entries support:

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

If the manifest pins one SHA and the local file has another, the case becomes:

```text
corpus_integrity_error
```

and extraction is skipped for that document.

This prevents accidentally benchmarking a replaced/edited PDF against stale expected values.

## 6. Corpus audit

Core module:

```text
src/DocFlow.Extraction.Worker/docflow_worker/corpus_audit.py
```

CLI:

```text
src/DocFlow.Extraction.Worker/corpus_audit.py
```

Run:

```bash
python corpus_audit.py \
  --inventory ../../benchmarks/results/corpus-inventory.json \
  --manifest ../../benchmarks/manifest.local.json \
  --output ../../benchmarks/results/corpus-audit.json
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

Existing benchmark CLI:

```text
src/DocFlow.Extraction.Worker/benchmark.py
```

Run after audit:

```bash
python benchmark.py \
  --manifest ../../benchmarks/manifest.local.json \
  --output ../../benchmarks/results/benchmark-report.json
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

## 8. Grouped real-world metrics

The report now also contains the same metrics grouped by:

```text
breakdowns.by_supplier
breakdowns.by_source_kind
breakdowns.by_layout_class
breakdowns.by_language
```

This is required for architectural analysis. An overall percentage alone cannot distinguish, for example:

- digital success vs OCR failure;
- one problematic supplier template;
- one layout class causing missing fields;
- one language causing type-detection/extraction failures.

## 9. CI state

The real-corpus tooling is covered by unit tests and synthetic smoke CI.

Verified after the content-hash audit semantics were finalized:

### Python Worker CI

```text
compile: success
pytest: success
```

### Benchmark Smoke

The workflow executes:

```text
generate synthetic quotation/invoice + duplicate
        ↓
corpus_inventory.py
        ↓
manifest built from inventory SHA values
        ↓
corpus_audit.py
        ↓
benchmark.py
        ↓
verify overall metrics + metadata breakdowns
```

Result: **success**.

### Regression E2E

Also verified after the corpus changes:

```text
Automation E2E: success
Scanned OCR E2E: success
```

Therefore the corpus tooling has not broken the existing upload/background/OCR production path.

## 10. Required real input before this milestone can close

The repository now has enough tooling to run the real benchmark. The missing input is external evidence:

1. representative real supplier quotation/invoice PDFs;
2. one manifest case per unique document content SHA;
3. independently transcribed expected fields;
4. useful metadata (`supplier`, `source_kind`, `layout_class`, `language`);
5. Tesseract language data for any scanned non-English documents.

A useful first batch should prefer **diversity over volume**. Ten different supplier/layout combinations are more informative than fifty copies of one template.

Suggested initial corpus target:

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

Then run:

```text
corpus_inventory.py
        ↓
create/edit manifest.local.json with independent ground truth
        ↓
corpus_audit.py
        ↓
benchmark.py
```

After the resulting `corpus-inventory.json`, `corpus-audit.json` and `benchmark-report.json` are available, analysis should focus on measured failure clusters rather than adding new extraction technology speculatively.

---

Current status: **technical preparation for real-corpus measurement is green; real-corpus evidence is still missing.**
