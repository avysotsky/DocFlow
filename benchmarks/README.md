# DocFlow real-world benchmark corpus

This directory contains the checked-in benchmark **format and instructions**, but not private supplier PDFs, local expected values or benchmark results.

## Local layout

Create the following files locally:

```text
benchmarks/
  manifest.example.json      # tracked example
  manifest.local.json        # ignored; your real expected values
  corpus/                    # ignored; real supplier PDFs
    ...
  results/                   # ignored; generated reports
    corpus-inventory.json
    corpus-audit.json
    benchmark-report.json
```

The repository ignores `corpus/`, `results/` and `manifest.local.json` so supplier documents and expected business data are not pushed accidentally.

## Step 1 — inventory the private corpus

Before creating expected values, scan the local PDF directory:

```bash
cd src/DocFlow.Extraction.Worker
python corpus_inventory.py \
  --corpus ../../benchmarks/corpus \
  --output ../../benchmarks/results/corpus-inventory.json
```

The inventory does **not** extract quotation/invoice business fields. It records only corpus-level technical information:

- local corpus root;
- relative PDF path;
- stable suggested benchmark id;
- SHA-256 digest;
- file size;
- page count;
- number of pages containing native PDF text;
- inferred source kind: `digital`, `scanned`, `mixed`, or `unknown`;
- duplicate-content relationship;
- PDF inspection errors.

Use `--fail-on-duplicates` when duplicate PDF contents should make the command fail:

```bash
python corpus_inventory.py \
  --corpus ../../benchmarks/corpus \
  --output ../../benchmarks/results/corpus-inventory.json \
  --fail-on-duplicates
```

The inventory exits non-zero when PDF inspection errors exist. With `--fail-on-duplicates`, duplicate contents also produce a non-zero exit code.

## Step 2 — create the local manifest

Copy the example:

```bash
cp benchmarks/manifest.example.json benchmarks/manifest.local.json
```

Each document entry can specify:

- a stable benchmark `id`;
- PDF path relative to the manifest file;
- expected `sha256` copied from the corpus inventory;
- corpus metadata;
- `document_type`, normally `auto`;
- expected document type;
- optional expected validation status;
- field expectations using dot paths.

For a real corpus, SHA-256 is treated as required by the audit even though the underlying benchmark schema keeps it optional for synthetic/legacy cases.

The metadata object supports:

```json
{
  "supplier": "supplier-a",
  "source_kind": "digital",
  "layout_class": "multi-page-borderless",
  "language": "en",
  "tags": ["quotation", "vat", "purchase-order"]
}
```

`source_kind` accepts:

```text
digital
scanned
mixed
unknown
```

The benchmark verifies `sha256` before parsing the PDF. A changed/replaced file is reported as `corpus_integrity_error` rather than being silently benchmarked against stale expected values.

Example field paths:

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

Array indexes are numeric path segments.

Ground truth should be recorded manually from the source document, not copied from DocFlow output. Otherwise the benchmark would be validating the extractor against itself.

## Step 3 — audit inventory against manifest

Run the consistency audit before measuring accuracy:

```bash
python corpus_audit.py \
  --inventory ../../benchmarks/results/corpus-inventory.json \
  --manifest ../../benchmarks/manifest.local.json \
  --output ../../benchmarks/results/corpus-audit.json
```

The audit fails on structural problems such as:

- manifest PDF missing from the inventory;
- unique corpus PDF missing from the manifest;
- missing real-corpus SHA-256;
- SHA-256 mismatch;
- a duplicate-content PDF being included in the manifest;
- source-kind mismatch between inventory and manifest;
- PDF inspection errors;
- the same PDF path appearing multiple times in the manifest.

Warnings identify benchmark-quality gaps that do not necessarily prevent a run:

- duplicate content exists in the corpus directory but is excluded from the manifest;
- `supplier`, `layout_class`, or `language` metadata is missing;
- source kind was not copied from the inventory;
- a document has no field-level expected values.

To treat warnings as failures:

```bash
python corpus_audit.py \
  --inventory ../../benchmarks/results/corpus-inventory.json \
  --manifest ../../benchmarks/manifest.local.json \
  --output ../../benchmarks/results/corpus-audit.json \
  --fail-on-warnings
```

## Step 4 — run the benchmark

From `src/DocFlow.Extraction.Worker` after installing the worker environment:

```bash
python benchmark.py \
  --manifest ../../benchmarks/manifest.local.json \
  --output ../../benchmarks/results/benchmark-report.json
```

For scanned documents, Tesseract and the requested language data must be installed. OCR is enabled by default. It can be disabled for a digital-only benchmark:

```bash
python benchmark.py \
  --manifest ../../benchmarks/manifest.local.json \
  --disable-ocr
```

## Metrics

The report contains overall metrics:

- `document_pass_rate` — a document passes only when type, requested validation status and every expected field match;
- `document_type_accuracy`;
- `validation_status_accuracy`;
- `field_accuracy`;
- `failure_reason_counts` aggregated over the corpus.

It also contains grouped metrics under `breakdowns`:

```text
breakdowns.by_supplier
breakdowns.by_source_kind
breakdowns.by_layout_class
breakdowns.by_language
```

Each group contains the same document/type/validation/field/failure metrics as the overall report. This is intended to expose systematic patterns such as “digital PDFs pass but scans fail” or “one supplier layout accounts for most missing fields”.

Per-document evidence includes:

- SHA-256;
- metadata;
- confidence;
- OCR usage/page numbers;
- every expected/actual field comparison;
- `failure_reasons`;
- processing error text when processing could not complete.

The benchmark classifies failures into these deterministic categories:

```text
corpus_integrity_error
  PDF SHA-256 differs from the manifest expectation

processing_error
  the document could not be processed at all

document_type_mismatch
  detected document type differs from the manifest expectation

validation_status_mismatch
  deterministic validation result differs from the manifest expectation

missing_field
  an expected field path is absent from the structured result

field_mismatch
  an expected field exists but contains a different value
```

One document can have several semantic failure reasons at the same time. `processing_error` and `corpus_integrity_error` are terminal for that document because there is no trustworthy structured result to compare.

The CLI exits with code `0` only when all benchmark documents pass. Any failed document produces exit code `1` while still writing the complete report.

## Corpus guidance

For useful architectural evidence, the local corpus should contain supplier documents from several independent templates rather than many copies of one layout.

Useful dimensions to vary include:

- quotation vs invoice;
- digital text vs scan/OCR vs mixed PDFs;
- bordered vs borderless item tables;
- single-page vs multi-page documents;
- supplier template/layout;
- language;
- date and numeric formats;
- tax/VAT presentation;
- optional fields such as PO number, Incoterms and payment terms.

Use anonymized supplier identifiers in `metadata.supplier` if the real supplier name itself is sensitive. Do not commit confidential supplier PDFs, expected business values or generated reports. Keep them under the ignored local corpus/manifest/results paths.

## Purpose

The benchmark is intended to answer an architectural question with evidence: which real supplier layouts fail the current deterministic+OCR pipeline, and why? Only after a representative corpus exposes systematic failure classes should DocFlow decide whether to extend deterministic rules or add an ONNX/LLM fallback.
