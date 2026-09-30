# DocFlow — completed handoff for version 1.1.1.4 Benchmarking

Date completed: 2026-09-30  
Implementation branch: `DocFlow/v_1.1.1.4_Benchmarking`

## 1. Milestone result

Version 1.1.1.4 adds a repeatable benchmark harness for measuring the current deterministic + OCR extraction pipeline against a local corpus without committing private supplier documents to Git.

This milestone does **not** claim production accuracy on real supplier documents. It provides the infrastructure required to measure that accuracy once a representative private corpus is supplied.

## 2. Benchmark corpus layout

Tracked benchmark documentation and example manifest:

```text
benchmarks/
  README.md
  manifest.example.json
```

Local/private benchmark inputs are intentionally ignored by Git:

```text
benchmarks/
  manifest.local.json
  corpus/
  results/
```

This keeps real supplier PDFs, expected business values and generated reports out of the repository.

## 3. Benchmark CLI

Entry point:

```text
src/DocFlow.Extraction.Worker/benchmark.py
```

Example:

```bash
cd src/DocFlow.Extraction.Worker
python benchmark.py \
  --manifest ../../benchmarks/manifest.local.json \
  --output ../../benchmarks/results/benchmark-report.json
```

Supported OCR controls:

```text
--disable-ocr
--ocr-language
--ocr-dpi
--tessdata
```

The CLI exits with code `0` only when all benchmark cases pass. Failed cases do not abort processing of the rest of the corpus; the complete report is still written.

## 4. Shared structured extraction pipeline

A shared structured pipeline was extracted so the normal worker CLI and benchmark runner execute the same document-type detection, semantic extraction and validation logic.

The benchmark therefore measures the same deterministic/OCR extraction behavior used by the application path rather than a parallel test-only implementation.

## 5. Manifest model

Each benchmark case contains:

- stable benchmark `id`;
- PDF path relative to the manifest;
- requested document type (`auto`, quotation or invoice);
- expected detected document type;
- optional expected validation status;
- expected field values expressed as dot paths.

Examples:

```text
data.quotation_number
data.invoice_number
data.currency
data.items.0.sku
data.items.0.quantity
data.subtotal
data.vat_amount
data.total
confidence
```

Numeric segments address array elements.

## 6. Report metrics

The generated JSON report includes:

- `documents_total`;
- `documents_passed`;
- `documents_failed`;
- `document_pass_rate`;
- `document_type_accuracy`;
- `validation_status_accuracy`;
- `field_accuracy`;
- per-document confidence;
- per-document OCR usage and OCR page numbers;
- every expected/actual field comparison;
- processing errors without aborting the remaining corpus.

## 7. Failure classification

Benchmark failures are classified into explicit reasons so the next architectural decision can be based on failure classes rather than a single accuracy percentage.

Current categories:

```text
processing_error
document_type_mismatch
validation_status_mismatch
missing_field
field_mismatch
```

Each failed document contains its own `failure_reasons`, and report metrics aggregate them in `failure_reason_counts`.

This allows a real corpus to answer questions such as:

- are failures mainly OCR/processing failures?
- is type detection the weak point?
- are documents parsed but arithmetic validation disagrees?
- are specific expected fields missing?
- are fields present but extracted with the wrong value?

## 8. Tests and CI

Python unit coverage includes:

- nested dot-path and array field comparison;
- missing-field and mismatch reporting;
- duplicate manifest-id rejection;
- accuracy metrics;
- failure-reason classification and aggregation.

`Python Worker CI` compiles both worker entry points:

```text
main.py
benchmark.py
```

and executes the pytest suite.

A dedicated workflow was added:

```text
.github/workflows/benchmark-smoke.yml
```

The smoke workflow:

1. installs the worker in a clean Python 3.11 environment;
2. generates a synthetic supplier quotation;
3. generates a synthetic supplier invoice;
4. creates a temporary benchmark manifest;
5. runs the real `benchmark.py` CLI;
6. verifies the generated JSON metrics.

Verified smoke result:

```text
documents_total: 2
documents_passed: 2
documents_failed: 0
document_pass_rate: 1.0
document_type_accuracy: 1.0
validation_status_accuracy: 1.0
fields_checked: 14
fields_matched: 14
field_accuracy: 1.0
failure_reason_counts: {}
```

The final benchmark smoke run passed successfully.

## 9. Architectural decisions retained

- Benchmarking reuses the production extraction pipeline.
- Private supplier documents are not committed to Git.
- Deterministic + OCR behavior is measured before adding ML/LLM fallback.
- The benchmark records field-level evidence and failure categories, not only pass/fail.
- A processing error for one document does not prevent remaining corpus cases from running.
- Existing .NET orchestration and PostgreSQL persistence architecture is unchanged by this milestone.

## 10. What is still not proven

No representative real supplier corpus has been supplied yet, so the following remain unknown:

- real document pass rate;
- real field accuracy;
- distribution of failure reasons;
- OCR performance on noisy scans;
- multi-page item-table reliability;
- multilingual supplier-document accuracy;
- handling of discounts, freight, surcharges and complex tax layouts;
- how often deterministic rules are sufficient;
- whether ONNX or LLM fallback is justified and for which exact failure classes.

Synthetic smoke results must not be interpreted as production accuracy.

## 11. Next milestone

Recommended next branch:

```text
DocFlow/v_1.1.1.5_RealCorpus
```

Goal: populate and evaluate a representative **private** real-world corpus using the benchmark infrastructure from this version.

Suggested workflow:

1. collect real supplier quotation/invoice PDFs locally;
2. assign stable anonymized benchmark ids;
3. create `benchmarks/manifest.local.json` with expected values;
4. run the benchmark without committing corpus data;
5. inspect `failure_reason_counts` and per-field mismatches;
6. group failures by supplier/layout/OCR/type-detection/semantic rule;
7. only then decide whether each failure class should be addressed with deterministic rules, OCR improvements, ONNX or an external LLM fallback.

---

Version 1.1.1.4 closes the benchmark-infrastructure stage. The next missing evidence is not another synthetic capability; it is measured accuracy on representative real supplier documents.
