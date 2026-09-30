# DocFlow real-world benchmark corpus

This directory contains the checked-in benchmark **format and instructions**, but not private supplier PDFs or local benchmark results.

## Local layout

Create the following files locally:

```text
benchmarks/
  manifest.example.json      # tracked example
  manifest.local.json        # ignored; your real expected values
  corpus/                    # ignored; real supplier PDFs
    ...
  results/                   # ignored; generated reports
    benchmark-report.json
```

The repository ignores `corpus/`, `results/` and `manifest.local.json` so supplier documents and expected business data are not pushed accidentally.

## Manifest

Copy the example:

```bash
cp benchmarks/manifest.example.json benchmarks/manifest.local.json
```

Each document entry specifies:

- a stable benchmark `id`;
- PDF path relative to the manifest file;
- `document_type`, normally `auto`;
- expected document type;
- optional expected validation status;
- field expectations using dot paths.

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

## Run

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

The report contains:

- `document_pass_rate` — a document passes only when type, requested validation status and every expected field match;
- `document_type_accuracy`;
- `validation_status_accuracy`;
- `field_accuracy`;
- per-document OCR usage;
- every expected/actual field comparison;
- processing errors without aborting the remaining corpus.

The CLI exits with code `0` only when all benchmark documents pass. Any failed document produces exit code `1` while still writing the complete report.

## Purpose

The benchmark is intended to answer an architectural question with evidence: which real supplier layouts fail the current deterministic+OCR pipeline, and why? Only after a representative corpus exposes systematic failure classes should DocFlow decide whether to extend deterministic rules or add an ONNX/LLM fallback.
