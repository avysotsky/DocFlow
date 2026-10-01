# DocFlow — active handoff for 1.1.1.6 HardCases_3

Status: **ACTIVE**  
Working branch: `DocFlow/v_1.1.1.6_HardCases_3`  
Previous completed branch: `DocFlow/v_1.1.1.6_HardCases_2`

## 1. Current measured baseline

Public Reference Benchmark **#74** on head:

```text
667979643bb49690476ad14d446f3637cf38b9c7
Validate wrapped item and settlement-total fixes
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

This is regression evidence over the current curated public corpus, not a general production-accuracy claim.

## 2. Corpus breadth block completed in HardCases_3

HardCases_3 expanded the admitted runtime corpus from 12 to 16 documents while deliberately reusing two stable public council source packs rather than adding four unrelated hosts.

New independently-ground-truthed invoices:

```text
ct-gardens-invoice-inv-0055  GBP 190.00 / VAT 0.00 / total 190.00
ct-gardens-invoice-inv-0065  GBP 190.00 / VAT 0.00 / total 190.00
ct-gardens-invoice-inv-0220  GBP 250.00 / VAT 0.00 / total 250.00
teec-invoice-inv-5383        GBP 30.00  / VAT 6.00 / total 36.00
```

The new acquisition helper is:

```text
.github/scripts/add_breadth_public_reference.py
```

It caches each source pack once and uses a generic invoice-page score when an invoice number appears on both a payment schedule and the actual invoice page. Invoice-like candidates are preferred by evidence such as `Tax Invoice`, `Invoice Number`, `Invoice Date`, and `Subtotal`; the selector does not rely on a supplier-specific page number.

## 3. Explicit NO VAT handling

Measured/static gap:

```text
TOTAL NO VAT 0.00
```

was not interpreted as an explicit zero-tax declaration, leaving otherwise complete invoices with missing VAT fields.

Generic fix:

```text
invoice_tax_fallbacks.apply_explicit_no_vat_fallback
```

activates only when a `TOTAL NO VAT` label is explicitly present. It sets:

```text
vat_rate   = 0
vat_amount = explicit amount, or 0 if the label has no amount
```

It never infers zero VAT merely because a tax row is missing.

Regression coverage:

```text
tests/test_no_vat_invoice.py
```

## 4. TEEC measured failure from Public Reference Benchmark #73

Benchmark #73 expanded the corpus successfully to 16 documents and produced:

```text
15/16 documents passed
16/16 document types correct
15/16 validation statuses correct
90/91 checked fields matched
```

The single failure was the real public TEEC invoice `INV-5383`.

The processed text contained:

```text
Description ... Quantity Unit Price VAT Amount GBP
Domain procurement request
              1.00 30.00 20% 30.00

Subtotal                30.00
Total VAT 20%            6.00
Invoice Total GBP       36.00
Total Net Payments GBP   0.00
Amount Due GBP          36.00
```

Two generic failure classes were measured.

### 4.1 Settlement total overwrote invoice total

`extract_preferred_invoice_total` treated a later `Total Net Payments GBP 0.00` row as an ordinary invoice total, allowing it to overwrite `Invoice Total GBP 36.00`.

Generic fix:

- settlement/payment summaries are excluded from gross invoice-total candidates;
- current exclusions include `Total Net Payment(s)`, `Total Payments`, and `Total Paid`;
- `Grand Total`, `Invoice Total`, and `Final Total` remain strong gross-total labels.

### 4.2 Borderless wrapped/split item row

The visual item row was represented as two physical text lines:

```text
description-only line
quantity unit-price VAT% amount
```

The normal table parser intentionally did not combine those lines, leaving no item and therefore incomplete arithmetic validation.

Generic fix:

```text
invoice_layout_fallbacks.apply_split_item_row_fallback
```

The fallback is conservative:

- runs only when the normal engine extracted no items;
- requires an explicit `Description / Quantity / Unit Price / Amount` header section;
- stops at the subtotal section;
- combines a description line with a following numeric-only item row;
- emits a normal `SupplierInvoiceItem` and then reuses existing arithmetic validation.

Regression coverage:

```text
tests/test_split_layout_invoice.py
```

The fixture also contains both `Invoice Total` and `Total Net Payments`, so the two measured TEEC regressions are covered together.

## 5. Final HardCases_3 evidence

Public Reference Benchmark #74 verified the complete merged behavior:

```text
68 Python tests passed
16/16 public documents passed
16/16 document types correct
16/16 validation statuses correct
91/91 checked business fields matched
```

The four new breadth documents, prior GST-inclusive Casterton case, French multi-rate Facturalex case, German Cargo case, discount cases, and OCR cases all remain green in the same run.

## 6. Current supported hard-case evidence

The public regression corpus now contains measured evidence for:

- line-level percentage discounts;
- document-level amount discounts;
- mixed native-text + image OCR;
- fully scanned/OCR documents;
- German invoice vocabulary;
- French invoice vocabulary;
- decimal comma / European grouping;
- negative invoice values;
- multiple VAT rates;
- zero-rated/exempt VAT categories;
- Australian GST-inclusive totals;
- genuine two-page item continuation and final-page totals;
- explicit `NO VAT` wording;
- invoice number repeated in payment-schedule/source-pack pages;
- wrapped/split borderless item rows;
- settlement/payment totals coexisting with gross invoice totals.

## 7. Remaining strongest coverage gap

The strongest unclosed HardCases class is now **degraded OCR quality**, specifically a real/public invoice with one or more of:

```text
visible skew/rotation
low contrast
scan noise / compression artifacts
faint print
broken decimal punctuation
mobile-camera-like geometry
```

Existing OCR documents prove the OCR path works, but they do not yet provide strong evidence for deliberate visual degradation.

The next document should be selected because it adds this difficulty class, not merely because it is another scanned invoice.

## 8. CI policy

Do not run GitHub Actions during source exploration or after each parser edit.

Use:

```text
research/select one real degraded-OCR source
-> independently transcribe ground truth
-> reproduce locally / inspect extracted text
-> classify measured failure(s)
-> implement one coherent generic fix block with [skip ci]
-> add regression tests
-> one consolidated Public Reference Benchmark
```

Automation E2E and Scanned OCR E2E remain reserved for milestone closure unless the production change directly requires them.

## 9. Benchmark infrastructure note

The legacy base source list currently contains five chronic runtime failures/unavailable sources (marker miss, 403, or 404). They do not block the admitted 16-document corpus, but they add roughly a minute of network/OCR overhead to each Public Reference Benchmark.

This should be cleaned up separately from parser work. Do not silently remove historical sources from the corpus policy merely to make CI faster; document any quarantine/replacement policy first.

## 10. Immediate next stage

HardCases_3 remains active.

Next engineering target:

```text
real/public visibly degraded invoice
+ independently transcribed business ground truth
+ measure current OCR/semantic output before changing production code
+ generic OCR/layout fix only if evidence requires it
```

No ONNX/LLM fallback is justified yet. Every measured hard-case failure through benchmark #74 has been closed deterministically or through the existing OCR pipeline.
