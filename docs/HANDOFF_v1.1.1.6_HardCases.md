# DocFlow — active handoff for version 1.1.1.6 HardCases

Status: **ACTIVE**  
Working branch: `DocFlow/v_1.1.1.6_HardCases`  
Started from completed milestone: `DocFlow/v_1.1.1.5_RealCorpus`

## 1. Purpose

Version 1.1.1.5 established a real public-reference baseline of 8/8 passing documents. Version 1.1.1.6 expands that evidence with deliberately difficult real/public supplier documents before introducing ONNX or LLM fallback.

The engineering loop is:

```text
real hard document
→ independent ground truth
→ current pipeline
→ measured failure
→ root-cause classification
→ generic deterministic/OCR fix
→ regression test
→ complete public corpus rerun
```

Public third-party PDFs are downloaded at CI runtime and are not committed to the repository. Expected values must be independently transcribed from the source, never copied from DocFlow output.

## 2. Failure classes

Every new failure is classified before production code is edited:

```text
source acquisition/page selection
OCR/text recognition
layout/table reconstruction
document-type detection
field extraction
arithmetic validation
semantic ambiguity
```

Production fixes must address a generic failure class. Supplier-specific behavior is allowed only in corpus acquisition when selecting a source page/document; it must not leak into the extraction engine.

## 3. Completed hard cases

### 3.1 Town House Publishing invoice 0023902 — line-level discounts

Measured failures:

- subtotal text contained a parenthetical discount amount that could overwrite the real subtotal;
- percentage-discounted rows violated the inherited `quantity × unit price == line total` assumption;
- VAT percentages could be mistaken for discounts by right-aligned fallback parsing.

Generic fixes:

- subtotal extraction ignores monetary values inside parenthetical notes when selecting the actual subtotal;
- `SupplierInvoiceItem` has optional `discount_rate`;
- `Discount/Disc` table columns are supported;
- invoice validation uses `quantity × unit_price × (1 - discount_rate / 100)`;
- right-aligned percentages are discounts only when the table schema explicitly contains a discount column.

Real document status: **green**.

### 3.2 Phoenix Petroleum invoice 472557 — mixed-page OCR + document-level discount

Measured failures:

1. the page contained little native text while the invoice itself was an embedded image, so the old policy skipped OCR;
2. the invoice had gross line value `158.65`, explicit document discount `19.00`, VAT `0.00`, net subtotal/total `139.65`;
3. OCR distorted the printed total while a remittance area repeated a gross-looking amount.

Generic fixes:

- pages with very little native text plus embedded images are OCR candidates;
- mixed-page OCR preserves native text while OCRing image regions;
- `SupplierInvoiceData` has optional `discount_amount`;
- invoice engine v2 performs conservative document-level discount reconciliation only when explicit discount and arithmetic evidence agree;
- item-level percentage discounts and document-level amount discounts remain distinct concepts.

Verified arithmetic:

```text
gross:     158.65 GBP
discount:   19.00 GBP
VAT:         0.00 GBP
subtotal:  139.65 GBP
total:     139.65 GBP
validation: valid
OCR:        applied
```

Real document status: **green**.

### 3.3 Cargo International invoice G59771 — German locale + decimal comma + negative money

Initial measured failure:

```text
processing_error
ValueError: The document type could not be detected deterministically.
```

Independent source values:

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

Generic fixes:

- deterministic German invoice vocabulary (`Rechnung`, `Rechnungsnummer`, `Rechnungsdatum`, `Rechnungsbetrag`, `Zahlungsziel`);
- German number/date/total fallbacks;
- locale-aware decimal conversion including `1.234,56 -> 1234.56` and negative values;
- locale path activates only when German invoice vocabulary is present.

Public Reference Benchmark #65 verified all seven checked Cargo fields. `incomplete` is intentional because the source does not expose enough item arithmetic for every validator check.

Real document status: **green**.

### 3.4 Casterton Foodworks invoice 02706 — genuine two-page continued item table + Australian GST

This is a real digital two-page tax invoice. The original PDF is retained as one benchmark document rather than reducing it to a single selected page.

Coverage added:

```text
2 physical pages belonging to one invoice
item table continues onto page 2
final totals appear on page 2
Australian TAX INVOICE vocabulary
Invoice #: identifier syntax
DD/MM/YYYY date
GST-inclusive total semantics
```

Initial measured failure in Public Reference Benchmark #66:

```text
processing_error
document type could not be detected deterministically
```

The corpus acquisition itself was correct: both pages were present. The failure was therefore in the production semantic path, not source selection.

Generic fixes implemented as one logical block:

- deterministic invoice detection accepts strong `TAX INVOICE` + `Invoice #` evidence;
- invoice model can distinguish tax-inclusive totals;
- invoice engine v2 supports the Australian `Invoice #` and day/month/year form used by this document;
- GST-inclusive retail totals such as `Total (inc GST)` and `Total includes GST of` are normalized without pretending GST is an additional amount on top of an already tax-inclusive total;
- item rows are reconstructed across multiple pages instead of assuming the first matching table/page is the complete invoice;
- GST-inclusive validation verifies the tax-inclusive arithmetic independently of the ordinary VAT-additive path;
- regression coverage includes a two-page continued-table fixture.

Implementation commit:

```text
bcb510d75eac869574494029d1580f1f5dd213cd
Support GST-inclusive multi-page invoices [skip ci]
```

Validation is consolidated into the Public Reference Benchmark workflow so the same run first executes the full Python unit suite and then the real public corpus.

Public Reference Benchmark #68 on validation head `91b27348ee9072314005ce71c79dc464bebfc1ad` verified:

```text
Python tests:              64 passed
Casterton pages:           2
source kind:               digital
document type:             supplier_invoice
validation status:         valid
invoice number:            02706
invoice date:              2024-05-14
GST amount:                5.82
total incl GST:            255.90
OCR applied:               false
Casterton checked fields:  4/4 matched
```

Real document status: **green**.

## 4. Current measured public-reference baseline

Public Reference Benchmark #68 produced:

```text
documents_total:             11
documents_passed:            11
documents_failed:            0
document_type_correct:       11/11
validation_status_correct:   11/11
fields_checked:              54
fields_matched:              54
field_accuracy:              1.0
failure_reason_counts:       {}
```

The artifact SHA-256 is:

```text
172320f925d25ec3dc0ff1f4e3dac052dcba5f00b2f67a7b66f7732cc5603cac
```

This is engineering regression evidence over a small curated corpus, **not** a production accuracy percentage.

The source pack is externally hosted, so unrelated source URLs can fail transiently. The workflow therefore requires active hard cases explicitly while retaining a minimum viable corpus threshold.

## 5. CI strategy

To avoid excessive GitHub Actions usage, HardCases work now follows this pattern:

```text
prepare one coherent implementation block
→ one implementation commit, optionally [skip ci]
→ one validation commit
→ one Public Reference Benchmark run
```

That validation workflow now runs the Python regression suite before the real public corpus, so a separate Python Worker CI run is not necessary for every hard-case iteration.

Full cross-stack workflows remain available for milestone/final validation, but are not intentionally triggered after every parser edit.

## 6. ML/LLM decision rule

Do not add ONNX or an external LLM merely because a new document fails.

Model fallback becomes justified only when measured failures demonstrate semantic ambiguity that cannot be handled safely by:

- OCR policy improvements;
- locale-aware deterministic parsing;
- layout/table reconstruction;
- arithmetic reconciliation;
- document-type detection;
- deterministic field-label rules.

Town House, Phoenix, Cargo and Casterton were all closed with deterministic/OCR/layout changes. There is still no measured evidence requiring an ONNX/LLM production fallback.

## 7. Remaining coverage gaps

The milestone now has real evidence for:

- line-level discounts;
- document-level discounts;
- mixed native-text + image OCR;
- German labels;
- decimal comma / European grouping;
- negative invoice values;
- Australian GST-inclusive arithmetic;
- genuine two-page item continuation and final-page totals.

Remaining useful gaps:

- multiple VAT/GST/tax rates in one document;
- a second non-English language family beyond German;
- broader degraded OCR (skew/low contrast/noisy scan);
- longer multi-page documents beyond the current two-page case;
- wrapped item descriptions or repeated table headers across several continuation pages.

## 8. Engineering target

Target for closing 1.1.1.6 remains approximately:

```text
15+ admitted unique PDFs
at least 4 newly represented hard-case classes
both digital and OCR documents retained
at least 2 locale/language variants beyond dominant English layouts
at least 1 genuine multi-page item-table case
```

The hard-case-class and multi-page requirements are now satisfied. Corpus breadth and second-language/tax-structure coverage still need expansion.

## 9. Completion criteria

Version 1.1.1.6 can close when:

1. corpus difficulty coverage is materially broader than 1.1.1.5;
2. new ground truth is independently recorded;
3. audit has no unresolved errors;
4. measured failures have documented root causes;
5. generic fixes have regression tests;
6. consolidated Python regression + Public Reference Benchmark is green;
7. milestone-level Automation E2E and Scanned OCR E2E are green before closure;
8. remaining unsupported cases, if any, are explicitly documented;
9. the milestone records whether evidence now justifies an ONNX/LLM experiment.

## 10. Immediate next stage

Do not add another document that merely repeats the Casterton multi-page class.

Preferred next hard-case class:

```text
real supplier invoice
+ multiple tax/VAT/GST rates in one document
+ preferably a non-English language family other than German
+ independently transcribed totals/tax structure
```

If a suitable document cannot be obtained quickly, the fallback priority is a visibly degraded OCR invoice, because OCR degradation remains less represented than discounts/layout/locale arithmetic.

---

Current status: **1.1.1.6 HardCases ACTIVE; Town House, Phoenix, Cargo and Casterton are closed. Current real public regression baseline is 11/11 documents, 54/54 checked fields, 64 Python tests green. Next focus: multiple tax rates / second language family / degraded OCR.**
