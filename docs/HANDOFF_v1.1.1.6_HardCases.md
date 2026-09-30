# DocFlow — active handoff for version 1.1.1.6 HardCases

Status: **ACTIVE**  
Working branch: `DocFlow/v_1.1.1.6_HardCases`  
Started from completed milestone: `DocFlow/v_1.1.1.5_RealCorpus`

## 1. Why this milestone exists

Version 1.1.1.5 established a real public-reference baseline:

```text
8/8 documents passed
8/8 document types correct
8/8 validation statuses correct
37/37 checked business fields correct
5 digital PDFs
3 scanned/OCR PDFs
audit: 0 errors, 0 warnings
```

That is useful regression evidence, but it is not a production-accuracy claim. The corpus is still small and does not cover several document classes that commonly break deterministic/OCR extraction.

Version 1.1.1.6 therefore expands evidence **before** adding ONNX or LLM fallback.

## 2. Objective

Deliberately add real/public supplier documents that stress previously underrepresented difficulty classes, run them through the existing benchmark, classify every failure, and fix only failure classes that are supported by measured evidence.

Target loop:

```text
new hard real document
        ↓
independent ground truth
        ↓
corpus audit
        ↓
current pipeline
        ↓
measured failure
        ↓
classify root cause
        ↓
minimal generic fix
        ↓
regression test
        ↓
rerun complete public corpus
```

## 3. Priority hard-case classes

Priority is based on remaining coverage gaps from 1.1.1.5.

### A. Locale and language variation

Examples:

- decimal comma and thousands separators;
- non-US date formats;
- currency symbols/codes placed differently;
- at least one non-English or bilingual invoice where Tesseract language support is practical.

### B. Tax/total variation

Examples:

- discount before tax;
- shipping/freight line;
- multiple VAT/tax rates;
- zero-rated or tax-exempt item;
- invoice where tax is summarized separately from item rows.

### C. Table/layout variation

Examples:

- long multi-page item table;
- repeated table header on later pages;
- borderless multi-page table;
- item descriptions wrapping over multiple physical lines;
- totals appearing on a final page separate from the first item page.

### D. OCR degradation

Examples:

- visibly noisy scan;
- skew/rotation;
- low contrast;
- scan with separators/decimal punctuation damaged by OCR;
- mobile-camera-like document if a legitimate public source is available.

## 4. Corpus policy

Public third-party PDFs continue to be downloaded at CI runtime and are not committed to the repository.

Every admitted document must have:

- a stable id;
- public source URL;
- SHA-256 pinned by the generated manifest;
- supplier/source metadata;
- source kind;
- layout class;
- language;
- independently transcribed expected business fields;
- independently reviewed expected validation status when applicable.

Do not derive expected values from DocFlow output.

## 5. Benchmark gate

The hardened public-reference workflow is inherited and now also tolerates unrelated third-party source outages without allowing the hard case under test to disappear silently.

A run must fail when:

- the audit fails;
- the benchmark returns non-zero;
- an admitted document fails expected fields/type/status;
- a benchmark report is missing;
- validation-status ground truth is missing for any admitted document;
- the required current hard-case document is missing from the generated manifest.

Reports must still upload on failure for diagnosis.

## 6. Failure classification

For every failing hard case, classify the primary root cause before editing extraction code:

```text
source acquisition/page selection
OCR/text recognition
layout/table reconstruction
document-type detection
field extraction
arithmetic validation
semantic ambiguity
```

A fix must be generic to the failure class. Do not add supplier-id-specific extraction branches merely to turn one benchmark green.

Source-specific logic is acceptable only inside the public corpus acquisition tooling when it is needed to select the intended original page from a larger public pack; it must not leak into the production extraction engine.

## 7. Completed hard-case evidence in this milestone

### 7.1 Town House Publishing invoice 0023902 — line-level discounts

Measured failure classes:

- subtotal label containing a parenthetical discount amount was able to overwrite the real subtotal;
- invoice items with explicit percentage discounts failed the inherited `quantity × unit price == line total` invariant;
- right-aligned OCR fallback initially risked treating VAT percentages as item discounts.

Generic fixes:

- subtotal extraction ignores monetary values inside parenthetical notes when choosing the actual subtotal;
- `SupplierInvoiceItem` has optional `discount_rate`;
- invoice table extraction understands `Discount/Disc` columns;
- invoice line validation uses `quantity × unit_price × (1 - discount_rate / 100)`;
- right-aligned percent values become discounts only when the table schema explicitly indicates a discount column.

The real Town House document now passes the complete public-reference benchmark.

### 7.2 Phoenix Petroleum invoice 472557 — mixed-page OCR + document-level discount

The selected source page contained only about 90 characters of native PDF text while the actual invoice was an embedded image.

Measured failure classes:

1. **OCR policy** — the old extractor skipped OCR whenever any native text existed, so only the figure caption reached document-type detection.
2. **Document-level arithmetic** — the invoice has gross line value `158.65`, explicit `Less discount 19.00`, VAT `0.00`, and net amount `139.65`; the old invoice model only represented item-level percentage discounts.
3. **OCR total ambiguity** — the printed net total was imperfectly OCRed while a remittance area repeated a gross-looking amount, so generic total-label extraction could not safely choose the business total by text alone.

Generic fixes:

- pages with very little native text plus embedded images are OCR candidates even when not text-empty;
- mixed-page OCR preserves native text while OCRing image regions;
- `SupplierInvoiceData` has optional document-level `discount_amount`;
- supplier invoice engine v2 performs conservative discount reconciliation only when explicit discount and arithmetic evidence agree;
- line-level percentage discounts and document-level amount discounts remain separate concepts;
- synthetic and real regression tests cover the new behavior.

Verified Phoenix arithmetic:

```text
gross line value: 158.65 GBP
document discount: 19.00 GBP
VAT:               0.00 GBP
net subtotal:      139.65 GBP
net total:         139.65 GBP
validation:        valid
OCR applied:       yes
```

## 8. Current measured public-reference baseline

After the Town House and Phoenix fixes, Public Reference Benchmark run #63 on implementation head `ef75677056cab61e959cc13a8abfb5168c08b008` produced:

```text
documents_total: 9
documents_passed: 9
documents_failed: 0
document_type_correct: 9/9
validation_status_correct: 9/9
fields_checked: 43
fields_matched: 43
field_accuracy: 1.0
audit_errors: 0
audit_warnings: 0
```

The source pack remains externally hosted and therefore some unrelated source URLs can transiently fail. The benchmark gate requires the active hard case while retaining a minimum viable public corpus so third-party outages do not masquerade as extraction regressions.

This is engineering regression evidence over a small curated corpus, **not** a production accuracy percentage.

## 9. Current CI state

Current hard-case implementation has been verified through:

- Python Worker CI — green;
- Benchmark Smoke — green;
- Scanned OCR E2E — green;
- Public Reference Benchmark — green, including Phoenix;
- Automation E2E — green after updating its expected invoice engine contract to `deterministic_supplier_invoice_v2`.

Automation E2E run #91 verifies that the engine-version update did not break the .NET upload → worker → persistence path.

## 10. ML/LLM decision rule

Do not add ONNX or an external LLM simply because a new document fails.

Model fallback becomes justified only when measured failures demonstrate semantic ambiguity that cannot be handled safely by:

- better OCR;
- locale-aware deterministic parsing;
- layout/table reconstruction;
- arithmetic reconciliation;
- clearer document-type detection;
- deterministic field-label rules.

The hard cases fixed so far required deterministic/OCR improvements only. There is still no measured evidence that an ONNX/LLM production fallback is required.

If such a failure class appears, first create an isolated benchmark experiment. Do not replace the current deterministic production path immediately.

## 11. Remaining coverage gaps

The current public-reference corpus is still predominantly English. Version 1.1.1.6 remains active because the following intended coverage is not yet demonstrated:

- decimal-comma / European numeric formats;
- non-English or bilingual invoice labels;
- at least one genuine multi-page item-table case;
- multiple VAT/tax-rate summaries;
- broader OCR degradation beyond the current scans and mixed-page example.

## 12. Engineering target

A useful target for this milestone remains:

```text
15+ admitted unique PDFs
at least 4 newly represented hard-case classes
both digital and OCR documents retained
at least 2 locale/language variants beyond the current dominant English layouts
at least 1 genuinely multi-page item-table case
```

These numbers are engineering coverage targets, not statistical accuracy claims.

## 13. Completion criteria

Version 1.1.1.6 can close when:

1. the corpus has materially broader difficulty coverage than 1.1.1.5;
2. new ground truth is independently recorded;
3. audit has no unresolved errors;
4. every new measured failure has a documented root-cause class;
5. generic deterministic/OCR fixes have regression tests;
6. complete Python Worker CI is green;
7. Benchmark Smoke is green;
8. Automation E2E is green;
9. Scanned OCR E2E is green;
10. Public Reference Benchmark is green or any remaining intentionally unsupported cases are explicitly documented with evidence and architecture consequences;
11. the milestone records whether there is now evidence for an ONNX/LLM experiment.

## 14. Immediate next stage

Target a document that expands **different** difficulty classes rather than another discount variant.

Preferred next admission combines as many of these as possible:

```text
German/European invoice
+ decimal comma / thousands separators
+ non-US date format
+ non-English labels
+ multi-page item layout if available
+ multiple VAT/tax summaries if present
```

The next batch should remain small enough that any failure can still be attributed to a concrete root cause, but related extraction/test changes should be committed as one logical engineering unit rather than many microcommits.

---

Current status: **1.1.1.6 HardCases ACTIVE; Town House and Phoenix hard-case classes are closed, current real public regression baseline is 9/9 green, next focus is locale + multi-page coverage.**
