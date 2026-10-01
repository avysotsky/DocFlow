# DocFlow — HardCases_2 completion handoff

Status: **COMPLETED**  
Completed branch: `DocFlow/v_1.1.1.6_HardCases_2`  
Next branch: `DocFlow/v_1.1.1.6_HardCases_3`

## 1. Scope closed in HardCases_2

HardCases_2 integrated two previously conflicting invoice extensions into one production path:

- Australian GST-inclusive multi-page retail invoices;
- French EN16931-style multi-rate VAT invoices with decimal-comma values and tax-category breakdowns.

The key regression introduced by the French commit was that `structured_pipeline.py` reverted from `DeterministicSupplierInvoiceMultipageEngine` to `DeterministicSupplierInvoiceDiscountEngine`, bypassing the GST-inclusive fallback. In the same merge, `tax_inclusive` and the associated validator paths had also been removed while `tax_breakdown` was added.

The final merged path preserves both capabilities:

```text
DeterministicSupplierInvoiceMultipageEngine
    -> existing discount/German logic
    -> Australian GST-inclusive/multi-page fallback
    -> French invoice fallback
    -> SupplierInvoiceData containing both tax_inclusive and tax_breakdown
    -> SupplierInvoiceValidator handling both tax-inclusive and multi-rate VAT cases
```

## 2. French real-layout failure and fix

The synthetic French regression passed, but the real public Facturalex PDF initially failed four top-level fields because the PDF text layout differs from the simplified fixture:

- invoice number appeared in a layout-preserved header sequence rather than directly next to the date;
- `TOTAL HT`, `TOTAL TVA`, and `TOTAL TTC` labels were represented as parallel columns rather than simple label/value lines.

The real benchmark already proved that the four VAT breakdown entries were extracted correctly. The final fix therefore changed only the real-layout header/summary extraction and added a regression fixture matching that layout.

Expected public Facturalex values:

```text
invoice_number: F20260023
currency:       EUR
subtotal:       100.00
vat_amount:     4.90
total:          104.90
validation:     incomplete

VAT breakdown:
S 20.00% base 11.00
E  0.00% base 60.00
S 10.00% base 27.00
K  0.00% base  2.00
```

`incomplete` remains intentional because current validation cannot fully reconcile line-item arithmetic from this source; it is not a parser failure.

## 3. Important commits

```text
a51b74d95c9fcc59041e506b1a1f652f59bde734
Restore tax-inclusive GST alongside French multi-VAT

c7be525ca244de589e09de07287bdd2a328d8c79
Restore multipage invoice engine in structured pipeline [skip ci]

97fc7f4084f433383866837cd00f1b22b90bf4e9
Handle French EN16931 real text layout [skip ci]

9270f24e6a802efe906c2defe11e87b5708a002a
Validate French real-layout extraction
```

## 4. Final validation evidence

Public Reference Benchmark **#72** on `9270f24e6a802efe906c2defe11e87b5708a002a` completed successfully.

```text
Python regression tests:       66 passed
public documents total:        12
public documents passed:       12
public documents failed:       0
document type correct:         12/12
validation status correct:     12/12
checked business fields:       71
matched business fields:       71
field accuracy on this corpus: 1.0
failure_reason_counts:         {}
```

Artifact ZIP SHA-256:

```text
0611b2a7c0ab83164bff7263b615174abf33f5aa4d62361f2c27d766f8573f76
```

This is regression evidence over the curated public corpus, not a general production-accuracy claim.

## 5. CI policy from this point

Do **not** trigger GitHub Actions after every parser edit.

Use the following loop:

```text
one larger engineering block
-> intermediate commits with [skip ci]
-> local/static inspection and targeted reasoning
-> one Public Reference Benchmark validation run at the end of the block
```

Milestone-level Automation E2E and Scanned OCR E2E should be reserved for milestone closure unless a change directly affects those layers.

## 6. Remaining 1.1.1.6 gaps

HardCases now covers:

- line-level discounts;
- document-level discounts;
- mixed native-text/image OCR;
- German locale and decimal comma;
- negative invoice values;
- Australian GST-inclusive arithmetic;
- genuine two-page continued item tables;
- French locale;
- multiple VAT rates;
- zero-rated/exempt VAT categories.

The largest remaining gaps are:

1. visibly degraded OCR: skew, low contrast, noise, damaged punctuation;
2. longer multi-page invoices beyond two pages;
3. wrapped item descriptions / repeated headers across several continuation pages;
4. public corpus breadth: the benchmark currently admits 12 documents because several legacy third-party source URLs are unavailable at runtime; target remains approximately 15+ stable unique PDFs.

## 7. Next engineering stage

Use branch:

```text
DocFlow/v_1.1.1.6_HardCases_3
```

Priority for HardCases_3:

```text
A. improve corpus breadth toward 15+ stable admitted PDFs;
B. add at least one real/public degraded-OCR invoice if a suitable stable source can be found;
C. classify any measured failures before production edits;
D. prefer generic OCR/layout fixes over source-specific parser branches;
E. perform one consolidated Public Reference Benchmark after the implementation block.
```

Do not introduce ONNX/LLM fallback unless the next measured failures demonstrate semantic ambiguity that deterministic OCR/layout/arithmetic handling cannot safely resolve.
