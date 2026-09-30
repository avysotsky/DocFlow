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

### 7.3 Cargo International invoice G59771 — German locale + decimal comma + negative values

This real German invoice expanded the corpus beyond English-only labels and positive Anglo-style money formatting.

Measured initial failure:

```text
processing_error
ValueError: The document type could not be detected deterministically.
```

The PDF itself was digital and readable. The failure was therefore a locale/document-type issue rather than OCR.

Independent ground truth:

```text
Rechnungsnummer: G59771
Rechnungsdatum:  04.06.2024
currency:         EUR
Netto:            -96,48
MwSt.:            -18,33
MwSt. in %:       19,00
Brutto:           -114,81
expected status:  incomplete
```

`incomplete` is intentional: the real document exposes the invoice totals clearly but does not provide a line structure that allows all current item/subtotal validation checks to be completed.

Generic fixes:

- deterministic document-type detection now recognizes a constrained German invoice vocabulary (`Rechnung`, `Rechnungsnummer`, `Rechnungsdatum`, `Rechnungsbetrag`, `Zahlungsziel`);
- invoice engine v2 has German field fallbacks for invoice number, invoice date and due date;
- German `Gesamt: Netto / MwSt. / MwSt. in % / Brutto` summaries are parsed deterministically;
- locale-aware decimal parsing handles negative decimal-comma values and European grouping, including `1.234,56 -> 1234.56`;
- the German path activates only when German invoice vocabulary is present, leaving unrelated English documents on the existing behavior;
- regression tests exercise the full structured pipeline and locale numeric conversion.

Public Reference Benchmark run #65 verified the real document:

```text
actual document type:      supplier_invoice
actual validation status:  incomplete
invoice number:             G59771
invoice date:               2024-06-04
currency:                   EUR
subtotal:                   -96.48
VAT rate:                   19.00
VAT amount:                 -18.33
total:                      -114.81
OCR applied:                false
```

All seven checked Cargo business fields matched independent ground truth.

## 8. Current measured public-reference baseline

After Town House, Phoenix and Cargo fixes, Public Reference Benchmark run #65 on implementation head `694dbcb51d6d79eda187694694c4e37f0e3162c8` produced:

```text
documents_total: 10
documents_passed: 10
documents_failed: 0
document_type_correct: 10/10
validation_status_correct: 10/10
fields_checked: 50
fields_matched: 50
field_accuracy: 1.0
failure_reason_counts: {}
```

The source pack remains externally hosted and therefore some unrelated source URLs can transiently fail. The benchmark gate requires the active hard cases while retaining a minimum viable public corpus so third-party outages do not masquerade as extraction regressions.

This is engineering regression evidence over a small curated corpus, **not** a production accuracy percentage.

## 9. Current CI state

Current hard-case implementation head `694dbcb51d6d79eda187694694c4e37f0e3162c8` has been verified through:

- Python Worker CI #107 — green;
- Benchmark Smoke #68 — green;
- Automation E2E #92 — green;
- Scanned OCR E2E #69 — green;
- Public Reference Benchmark #65 — green, including Cargo, Phoenix and Town House.

The .NET upload → worker → persistence path remains green with supplier invoice engine `deterministic_supplier_invoice_v2`.

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

Version 1.1.1.6 remains active because the following intended coverage is not yet demonstrated strongly enough:

- at least one genuine multi-page item-table case;
- repeated table headers across pages / totals on a later page;
- multiple VAT/tax-rate summaries;
- a second locale/language family beyond English and German;
- broader OCR degradation beyond the current scans and mixed-page example.

Decimal-comma, negative money, German invoice labels and German day-month-year dates are now represented by the real Cargo International document.

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

The next admitted hard case should expand **layout continuity across pages**, not another single-page locale variant.

Preferred characteristics:

```text
real public supplier invoice
+ 2+ pages belonging to the same invoice
+ item table continuing onto later page(s)
+ repeated or missing table header on continuation pages
+ totals appearing on final page
+ independent ground truth for identifying fields and totals
```

If a real public multi-page supplier invoice cannot be obtained reliably, use a clearly labeled controlled multi-page fixture only as a secondary engineering test; it must not be counted as new real-world evidence.

Related extraction/test changes should continue to be committed as one logical engineering unit rather than many microcommits.

---

Current status: **1.1.1.6 HardCases ACTIVE; Town House, Phoenix and Cargo hard-case classes are closed, current real public regression baseline is 10/10 green, next focus is genuine multi-page item-table coverage.**
