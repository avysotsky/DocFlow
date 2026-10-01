# DocFlow — 1.1.1.6 HardCases completion handoff

Status: **COMPLETED**  
Final branch: `DocFlow/v_1.1.1.6_HardCases_3`  
Recommended next branch: `DocFlow/v_1.1.1.7_DegradedOCR`

## 1. Milestone objective

Version 1.1.1.6 deliberately expanded the real/public supplier-document corpus and used measured failures to harden the existing deterministic + OCR extraction pipeline before introducing ONNX or LLM fallback.

Engineering loop used throughout the milestone:

```text
real/public hard document
-> independent ground truth
-> current pipeline
-> measured failure
-> root-cause classification
-> generic deterministic/OCR/layout fix
-> regression test
-> complete public corpus rerun
```

No production fallback was added merely because a document failed. Every production change in this milestone corresponds to a measured failure class.

## 2. Final public-reference baseline

Public Reference Benchmark **#74** on implementation/validation head:

```text
667979643bb49690476ad14d446f3637cf38b9c7
```

completed successfully.

```text
Python regression tests:       68 passed
public documents total:        16
public documents passed:       16
public documents failed:       0
document type correct:         16/16
validation status correct:     16/16
checked business fields:       91
matched business fields:       91
field accuracy on this corpus: 1.0
failure_reason_counts:         {}
```

Artifact ZIP SHA-256:

```text
66421297c940e9760b028ddc2ad8c71c73360e8197a2403ce97fb9aa1b2dcce6
```

This is engineering regression evidence over a small curated public corpus. It is **not** a claim of 100% production accuracy on arbitrary invoices.

## 3. Milestone-level end-to-end validation

Final milestone validation was triggered once from commit:

```text
b338bd7d7e991f0a931198365779b68201375bb5
Run milestone-level E2E validation
```

The commit changed only comments in the two E2E workflow files so both required milestone workflows were triggered by one push without re-running the public-reference benchmark.

### Automation E2E

GitHub Actions run:

```text
Automation E2E #95
run id: 36836146773
result: SUCCESS
```

Verified end to end:

- .NET solution build;
- PostgreSQL migrations;
- valid quotation automatic processing;
- repeated enqueue/idempotency;
- invalid arithmetic -> `NeedsReview`;
- technical worker failure -> `Failed`;
- borderless quotation processing;
- supplier invoice automatic detection, extraction, validation and persistence.

### Scanned OCR E2E

GitHub Actions run:

```text
Scanned OCR E2E #72
run id: 36836146901
result: SUCCESS
```

Verified end to end:

- image-only PDF fixture;
- Tesseract OCR path;
- upload -> background processing -> OCR -> semantic extraction -> validation -> persistence;
- final document status `Processed`;
- expected quotation fields and arithmetic persisted correctly.

## 4. Hard-case classes closed in 1.1.1.6

### 4.1 Line-level percentage discounts

The invoice model and validator now support explicit item discount percentages and validate:

```text
quantity * unit_price * (1 - discount_rate / 100)
```

without confusing unrelated VAT percentages with discounts.

### 4.2 Document-level amount discounts

Explicit document discounts are represented separately from item discounts and reconciled conservatively when arithmetic evidence agrees.

### 4.3 Mixed native-text + image OCR

Pages with little native text but embedded invoice images can still enter the OCR path while preserving useful native text.

### 4.4 German locale

Added constrained German invoice detection and locale-aware fallbacks for:

- `Rechnung` vocabulary;
- invoice/date/due-date fields;
- decimal comma and European grouping;
- negative money values;
- German net/VAT/gross summaries.

### 4.5 Genuine two-page continued item table

Casterton Foodworks invoice 02706 added real evidence for:

- one invoice spanning two physical pages;
- continued item rows;
- final totals on page 2;
- Australian `TAX INVOICE` / `Invoice #` vocabulary;
- `DD/MM/YYYY` date;
- GST-inclusive totals.

The model preserves `tax_inclusive` semantics so GST is not incorrectly added twice.

### 4.6 French multi-rate VAT

Facturalex invoice F20260023 added:

- French invoice vocabulary;
- decimal comma;
- multiple VAT rates;
- zero-rated/exempt tax categories;
- tax summary structure preserved in `tax_breakdown`.

Ground truth:

```text
invoice_number: F20260023
currency:       EUR
subtotal:       100.00
vat_amount:     4.90
total:          104.90

VAT breakdown:
S 20.00% base 11.00
E  0.00% base 60.00
S 10.00% base 27.00
K  0.00% base  2.00
```

Its expected validation status remains intentionally `incomplete` because the real source does not expose enough line-item arithmetic for all validator checks.

### 4.7 Explicit NO VAT wording

Invoices containing an explicit line such as:

```text
TOTAL NO VAT 0.00
```

now produce explicit zero VAT fields instead of becoming incomplete merely because the conventional `VAT 0%` wording is absent.

The fallback never assumes zero VAT from a missing tax line; the explicit `NO VAT` label is required.

### 4.8 Source-pack page disambiguation

The corpus now supports cases where an invoice number appears both on a payment schedule and on the actual invoice page. Candidate pages are ranked by invoice evidence rather than accepting the first textual match.

This allowed four additional independently-ground-truthed invoices to be admitted from two stable public council packs without multiplying external hosts.

### 4.9 Settlement/payment totals vs gross invoice total

A real TEEC invoice exposed this structure:

```text
Invoice Total GBP       36.00
Total Net Payments GBP   0.00
Amount Due GBP          36.00
```

The generic total selector previously allowed the later settlement total to overwrite the gross invoice total. Settlement/payment summaries are now excluded from gross invoice-total candidates.

### 4.10 Wrapped/split borderless item rows

The same real invoice represented one visual item as:

```text
description-only physical line
quantity unit-price VAT% amount physical line
```

A conservative fallback now reconstructs this layout only when:

- normal item extraction found no items;
- an explicit Description/Quantity/Unit Price/Amount header exists;
- the numeric row follows a description line;
- parsing remains inside the item section before subtotal.

Existing arithmetic validation then validates the recovered normal `SupplierInvoiceItem`.

## 5. Corpus breadth achieved

Final admitted public corpus contains 16 documents, exceeding the approximate 15+ target for this milestone.

The corpus contains both digital and OCR-backed documents and evidence across multiple languages, tax structures, discount structures and layout classes.

The four breadth additions in HardCases_3 are:

```text
ct-gardens-invoice-inv-0055
ct-gardens-invoice-inv-0065
ct-gardens-invoice-inv-0220
teec-invoice-inv-5383
```

## 6. CI strategy established

HardCases development demonstrated that launching CI after every small parser edit is wasteful and obscures the engineering signal.

The retained strategy is:

```text
one coherent engineering block
-> intermediate [skip ci] commits
-> inspect/measure locally or from an existing failed artifact
-> add regressions
-> one consolidated Public Reference Benchmark
```

Full Automation E2E / Scanned OCR E2E are milestone-level gates rather than per-edit gates.

## 7. Explicit remaining limitations

### 7.1 Visibly degraded OCR

The strongest remaining extraction-evidence gap is a real/public invoice with deliberate real-world visual degradation such as:

- skew/rotation;
- low contrast or faded print;
- scan noise/compression artifacts;
- damaged punctuation;
- mobile-camera-like geometry.

The current corpus proves image-only OCR and mixed image/native-text processing, but it does **not** yet provide strong evidence for heavily degraded scans.

A suitable real/public source was not admitted merely to satisfy a checklist; ordinary clean scans do not count as this class.

### 7.2 Public-source availability

Five historical external source definitions are chronically unavailable or fail page-selection at runtime (404, 403, or marker miss). They do not block the 16 admitted documents but increase benchmark runtime and network noise.

A future infrastructure pass should define an explicit quarantine/replacement policy rather than silently removing historical source definitions.

### 7.3 Corpus size

Sixteen curated public documents are useful regression evidence but still far below the diversity required for a statistically meaningful production-accuracy estimate.

## 8. ONNX / LLM decision

**No measured evidence from 1.1.1.6 justifies introducing ONNX or an external LLM into the production extraction path yet.**

Every observed failure through Public Reference Benchmark #74 was resolved by one of:

- OCR policy;
- locale-aware deterministic parsing;
- document-type detection;
- layout/table reconstruction;
- tax/discount semantics;
- arithmetic validation;
- source-page selection.

The next model experiment should only be introduced after a future corpus exposes a failure class that these deterministic mechanisms cannot handle safely.

## 9. Recommended next milestone

Recommended branch:

```text
DocFlow/v_1.1.1.7_DegradedOCR
```

Purpose:

1. obtain at least one legitimate real/public visibly degraded supplier invoice;
2. independently transcribe its ground truth before processing it;
3. quantify current OCR output and extraction failure;
4. determine whether generic image preprocessing (deskew, contrast normalization, denoise, adaptive thresholding, rotation/orientation handling) materially improves extraction;
5. avoid adding preprocessing globally unless measurements show benefit without regression;
6. retain the same block-level CI discipline established in HardCases;
7. revisit ONNX/LLM only if the measured failure is semantic rather than visual/OCR/layout related.

---

**1.1.1.6 HardCases is complete.** Final evidence: Public Reference #74 green at 16/16 documents and 91/91 checked fields; Automation E2E #95 green; Scanned OCR E2E #72 green. Remaining degraded-OCR coverage is explicitly deferred to 1.1.1.7 rather than being hidden or simulated as a real-source result.
