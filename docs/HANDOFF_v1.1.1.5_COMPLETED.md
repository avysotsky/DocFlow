# DocFlow — completed handoff for version 1.1.1.5 RealCorpus

Status: **COMPLETED**  
Working branch: `DocFlow/v_1.1.1.5_RealCorpus`  
Final verified implementation head: `7b10cefda5714d6c6c445e1fcd38382216894491`  
Completed on: `2026-09-30`

## 1. Milestone objective

Version 1.1.1.5 replaced synthetic-only confidence with measured evidence from real third-party supplier PDFs.

The milestone used a public-reference corpus so CI could repeatedly download original source documents without committing third-party PDFs to the repository.

Ground truth for business fields and validation status was recorded independently from DocFlow output.

## 2. Final public-reference corpus

The runtime source builder attempted 11 public sources:

```text
sources_total:      11
sources_downloaded: 8
sources_failed:     3
manifest_documents: 8
```

The final benchmark therefore contained 8 unique original PDF contents:

```text
digital PDFs: 5
scanned/OCR PDFs: 3
unique SHA-256 contents: 8
```

The corpus includes multiple supplier/layout families, Xero-style invoices, proforma invoices, OCR-only documents and a two-page bilingual commercial invoice.

Three candidate sources did not enter the final corpus because source acquisition/page selection failed:

- `gastech-tax-invoice-77057631` — marker not found after native-text/OCR search;
- `soft-tech-proforma-prof005` — marker not found in the configured bounded search;
- `aa-salt-invoice-inv-7077` — upstream HTTP 403.

These are source-acquisition failures, not benchmark extraction failures, because the corresponding PDFs were not admitted into the manifest.

## 3. Ground-truth boundary

Expected business values in the public-reference builder were independently transcribed from the public source documents.

Validation-status expectations were added separately through:

```text
.github/scripts/annotate_public_reference_validation.py
```

The annotation does not copy DocFlow output. It records whether the source document independently contains enough arithmetic structure for the deterministic validator to classify it as `valid` or whether required arithmetic inputs are genuinely absent and the correct status is `incomplete`.

The final benchmark enforces:

```text
validation_status_checked == documents_total
```

so a new public case cannot silently skip validation-status ground truth.

## 4. Measured failures found during the milestone

Enabling validation-status ground truth deliberately exposed two real parser weaknesses even though the previously checked business fields were already correct.

### 4.1 HCC Solutions — shifted OCR columns

Observed failure:

```text
expected validation: valid
actual validation:   invalid
```

Cause:

- the invoice uses a common `Description / Quantity / Unit Price / VAT / Amount` layout without SKU;
- OCR split long descriptions across additional cells and inserted separator artifacts;
- fixed header indexes no longer pointed to the numeric tail;
- only part of the item set was parsed, so item totals no longer reconciled to subtotal.

Fix:

- invoice items no longer require SKU;
- OCR/layout rows with shifted descriptions are parsed from their stable numeric tail from right to left;
- descriptions are reconstructed from the remaining leading cells.

### 4.2 Trea Kids — lost OCR quantity and decimal separators

Observed failure:

```text
expected validation: valid
actual validation:   incomplete
```

Cause:

OCR preserved the visible item arithmetic only imperfectly:

```text
6000  -> 60.00 candidate
12000 -> 120.00 candidate
```

and one item quantity was not preserved as a normal table column.

Fix:

- OCR monetary tokens can produce conservative decimal-scale alternatives;
- quantity may be inferred only when unit price and line total imply an exact positive integral quantity;
- candidate item rows are accepted only when their line totals reconcile exactly to the independently extracted invoice subtotal;
- dynamic programming over cents chooses at most one interpretation per OCR row and rejects non-reconciling alternatives.

This is a generic arithmetic constraint, not a supplier-id-specific correction.

## 5. Invoice model change

`SupplierInvoiceItem.sku` is now optional:

```text
str | None
```

This reflects real invoices that legitimately have no SKU/item-code column.

The quotation model remains unchanged.

## 6. CI benchmark hardening

The original public-reference workflow intentionally captured `real_corpus.py`'s non-zero exit code so reports could still be published, but then exited the benchmark step with zero. That made a future failed benchmark capable of producing a green workflow.

The workflow now:

1. runs the benchmark and captures its real exit code;
2. always publishes the summary;
3. always uploads benchmark artifacts;
4. requires a benchmark report;
5. requires validation ground truth for every admitted document;
6. finally propagates a non-zero benchmark result through `Enforce benchmark result`.

Therefore diagnostic artifacts remain available on failure while GitHub Actions correctly becomes red.

## 7. Final measured result

Final public-reference run on implementation head:

```text
documents_total:              8
documents_passed:             8
documents_failed:             0
document_pass_rate:           1.0

document_type_correct:        8
document_type_accuracy:       1.0

validation_status_checked:     8
validation_status_correct:     8
validation_status_accuracy:   1.0

fields_checked:                37
fields_matched:                37
field_accuracy:                1.0

failure_reason_counts:         {}
```

Corpus audit:

```text
errors:                        0
warnings:                      0
inventory_documents:           8
inventory_unique_contents:     8
manifest_documents:            8
represented_unique_contents:   8
```

Per-case validation result:

```text
Asar Ltd                         incomplete -> incomplete
H.W. Pickrell Ltd                incomplete -> incomplete
Trea Kids                        valid      -> valid
HCC Solutions                    valid      -> valid
Hugofox                          valid      -> valid
Rainford's Farm                  valid      -> valid
Mulberry LAS                     valid      -> valid
Jordan commercial invoice        incomplete -> incomplete
```

`incomplete` is a correct outcome when the source itself does not expose all arithmetic inputs required by the deterministic validator; it is not treated as a parser failure when the independently recorded expected status is also `incomplete`.

## 8. Regression coverage

The final invoice regressions cover:

- borderless invoice items without SKU;
- OCR rows whose long descriptions shift numeric columns;
- OCR monetary values with lost decimal separators;
- missing quantity recovery constrained by exact arithmetic;
- subtotal reconciliation before accepting OCR item candidates.

Final Python worker test result:

```text
51 passed
1 skipped
```

Final CI state on head `7b10cefda5714d6c6c445e1fcd38382216894491`:

```text
Python Worker CI:            success
Benchmark Smoke:             success
Automation E2E:              success
Scanned OCR E2E:             success
Public Reference Benchmark:  success
```

## 9. Architectural decision from the measured evidence

The measured failures in this initial corpus were explainable deterministic/OCR-layout failures and were corrected without introducing a model fallback.

There is currently no measured failure in this 8-document reference set that justifies adding ONNX or an external LLM to the production extraction path.

Therefore the architecture remains:

```text
PDF
 ↓
PyMuPDF/pdfplumber layout extraction
 ↓
conditional Tesseract OCR for scanned pages
 ↓
deterministic document-type detection
 ↓
deterministic supplier quotation/invoice extraction
 ↓
deterministic arithmetic validation
 ↓
.NET orchestration + PostgreSQL persistence
```

ONNX/LLM remains a future experiment only when a broader corpus produces a failure class that cannot be handled safely and economically with deterministic/OCR improvements.

## 10. What this result does and does not prove

This milestone provides real third-party regression evidence, not a production accuracy claim.

The result proves that the current pipeline correctly handles the 8 admitted public-reference documents and their independently recorded 37 business-field checks plus validation classifications.

It does **not** establish statistically meaningful accuracy for arbitrary supplier documents. The corpus is still small and partially curated by source availability.

Important remaining coverage gaps include:

- a larger number of independent suppliers;
- more languages and locale-specific number/date formats;
- discounts, shipping, multiple tax rates and tax-exempt cases;
- longer multi-page item tables;
- very noisy/mobile-camera scans;
- rotated/skewed pages;
- handwritten annotations;
- invoices whose semantics cannot be reconstructed from deterministic labels/layout/arithmetic.

## 11. Recommended next development direction

Do not add ONNX/LLM merely because 1.1.1.5 is complete.

The next evidence-driven stage should expand the external corpus and deliberately target the untested difficulty classes above. Any new failure should first be classified as one of:

```text
source acquisition/page selection
OCR/text recognition
layout/table reconstruction
document-type detection
field extraction
arithmetic validation
semantic ambiguity requiring a model experiment
```

Only the last class is evidence for introducing an ONNX/local model or external LLM fallback.

---

Version `1.1.1.5 RealCorpus`: **COMPLETED**.
