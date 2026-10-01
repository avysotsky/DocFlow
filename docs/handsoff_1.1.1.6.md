# DocFlow — handsoff 1.1.1.6 HardCases continuation

Status: **ACTIVE / MOVE TO NEW CHAT**  
Repository: `avysotsky/DocFlow`  
Source branch at handoff: `DocFlow/v_1.1.1.6_HardCases`  
Recommended continuation branch: `DocFlow/v_1.1.1.6_HardCases_2`  
Milestone remains **1.1.1.6**. Do **not** advance to 1.1.1.7 yet.

This file is the authoritative continuation point for the next chat. Read it before changing code.

---

## 1. Architecture / project rules that must not change casually

- .NET owns API/orchestration/PostgreSQL persistence.
- Python worker owns PDF extraction/OCR/deterministic semantic parsing/validation.
- Python does not write PostgreSQL directly.
- MVP uses in-process `Channel`; no RabbitMQ/Kafka/Redis yet.
- Do not add ONNX/LLM because a document is difficult. First measure a real failure and exhaust reasonable deterministic/OCR/layout fixes.
- Public third-party PDFs are downloaded at CI runtime and are not committed to the repository.
- Ground truth must be independently transcribed/reviewed, not copied from DocFlow output.
- Synthetic tests prove behavior, not production accuracy.

## 2. Work-process rules requested by the user

These rules are important and should be followed in the next chat:

- One work stage should take **no more than ~10 minutes**.
- Stages can be roughly **twice as large** as the very small stages used earlier in this chat.
- Prefer one meaningful engineering unit per stage rather than microsteps.
- **Use GitHub Actions sparingly.**
- Prefer one CI run per substantial stage, not one run per file/edit.
- Avoid dozens of tiny commits.
- Prefer one logical implementation commit, or at most 2–3 commits for a substantial stage.
- When implementation changes should not trigger the full workflow immediately, `[skip ci]` may be used, followed by one validation commit/run when the block is ready.
- Do not repeatedly poll Actions. Check once when enough time has elapsed.
- If the chat context becomes too large again, create a new handoff before continuing.

## 3. Historical baseline before HardCases

Version 1.1.1.5 RealCorpus established the first real public-reference baseline:

```text
8/8 documents passed
8/8 document types correct
8/8 validation statuses correct
all checked fields matched
5 digital PDFs
3 scanned/OCR PDFs
audit: 0 errors, 0 warnings
```

This is regression evidence over a small corpus, not a production accuracy claim.

## 4. Hard cases already closed in 1.1.1.6

### 4.1 Town House Publishing invoice 0023902 — line-level percentage discounts

Real failure classes:

- parenthetical discount note could overwrite subtotal;
- item discount percentages broke inherited `quantity × unit price == line total` validation;
- right-aligned fallback initially risked treating VAT percentage as discount.

Implemented generic fixes:

- ignore parenthetical monetary notes when extracting actual subtotal;
- `SupplierInvoiceItem.discount_rate`;
- discount-column parsing (`Discount/Disc`);
- discounted line-total validation;
- right-aligned percent becomes discount only when table schema indicates discount.

Real public document passes benchmark.

### 4.2 Phoenix Petroleum invoice 472557 — mixed-page OCR + document-level discount

Real failure classes:

- page had only ~90 native-text chars (caption) while invoice itself was embedded image;
- OCR policy skipped OCR merely because some native text existed;
- invoice had explicit document-level discount amount, not item-level percentage;
- OCR made printed total ambiguous while remittance area repeated a gross-looking amount.

Implemented generic fixes:

- low-native-text pages containing images can trigger OCR;
- mixed-page OCR preserves native text while OCRing image areas;
- `SupplierInvoiceData.discount_amount`;
- conservative document-level discount reconciliation;
- separate item-level percentage discounts from document-level amount discounts.

Verified arithmetic:

```text
gross:     158.65 GBP
discount:   19.00 GBP
VAT:         0.00 GBP
net total: 139.65 GBP
status: valid
```

### 4.3 Cargo International invoice G59771 — German locale

Covered:

- German invoice vocabulary;
- `Rechnung`, `Rechnungsnummer`, `Rechnungsdatum`, `Zahlungsziel`;
- decimal comma;
- European grouping (`1.234,56`);
- negative monetary values;
- German total summary `Netto / MwSt. / MwSt. in % / Brutto`.

Verified real values:

```text
invoice: G59771
date: 2024-06-04
currency: EUR
subtotal: -96.48
VAT rate: 19.00
VAT amount: -18.33
total: -114.81
status: incomplete (intentional: item arithmetic is not fully reconstructable)
```

### 4.4 Casterton Foodworks invoice 02706 — genuine two-page continuation + Australian GST

This is a real two-page public invoice. The whole original PDF is preserved as the benchmark unit.

Covered:

- `TAX INVOICE` + `Invoice #:`;
- `DD/MM/YYYY`;
- item table continues onto page 2;
- totals appear on final page;
- GST-inclusive totals (`Total (inc GST)` / `Total includes GST of`);
- multi-page item collection;
- `tax_inclusive` invoice validation.

Last confirmed green public benchmark before current French work: **Public Reference Benchmark #68**.

Metrics from run #68:

```text
Python regression tests: 64 passed
public documents: 11/11 passed
document types: 11/11 correct
validation statuses: 11/11 correct
fields: 54/54 matched
failures: 0
```

Casterton independent ground truth:

```text
invoice: 02706
date: 2024-05-14
GST: 5.82
total: 255.90
status: valid
pages: 2
```

Important commits around this baseline:

```text
91b27348ee9072314005ce71c79dc464bebfc1ad
  Validate worker before public hard-case benchmark
  Public Reference Benchmark #68 GREEN

77f80b1c2bf966a5b8d17dbf3586c21fcedf019e
  Document multi-page hard case baseline
  docs-only; no new CI required
```

## 5. Current unfinished stage — French multi-rate VAT

The next selected hard case is a public French EN16931 standards sample from Facturalex:

```text
id: facturalex-french-multivat-f20260023
invoice: F20260023
language: fr-FR
currency: EUR
source: public EN16931 sample
```

Source URL currently configured in the runtime corpus script:

```text
https://www.facturalex.com/files/Facture_F20260023-LE_FOURNISSEUR-POUR-LE_CLIENT_EN_16931.pdf
```

Important qualification: this is a **public standards-based sample invoice**, not evidence of a real commercial transaction. Keep that distinction in docs/claims.

Independent ground truth configured for this sample:

```text
invoice_number: F20260023
currency: EUR
TOTAL HT:  100.00
TOTAL TVA:   4.90
TOTAL TTC: 104.90
expected validation status: incomplete
```

Tax breakdown expected:

```text
S 20.00%  taxable base 11.00
E  0.00%  taxable base 60.00
S 10.00%  taxable base 27.00
K  0.00%  taxable base  2.00
```

The intended generic capability is:

- French invoice detection;
- French labels (`FACTURE`, `TOTAL HT`, `TOTAL TVA`, `TOTAL TTC`, `NET A PAYER`, date d'échéance);
- French decimal comma;
- multiple VAT/tax categories/rates;
- zero/exempt/intracommunity-style categories;
- total VAT validation as sum of tax breakdown arithmetic.

## 6. Current implementation state for French multi-VAT

Current source branch HEAD before this handoff file was created:

```text
fd7aa33c8d2fa8ef5894d9ae01891886b0649c7d
Validate French multi-rate VAT hard case
```

The branch was intentionally squashed so that since baseline `77f80b1...` there are only two logical commits:

1. implementation block:

```text
ff3b9d62bf6d0388a367a6455fe90993c9abcec3
```

2. validation commit:

```text
fd7aa33c8d2fa8ef5894d9ae01891886b0649c7d
```

Files involved in the current French block:

```text
.github/scripts/add_french_multivat_public_reference.py
.github/workflows/public-reference-benchmark.yml
src/DocFlow.Extraction.Worker/docflow_worker/document_type_detector.py
src/DocFlow.Extraction.Worker/docflow_worker/french_invoice_locale.py
src/DocFlow.Extraction.Worker/docflow_worker/structured_pipeline.py
src/DocFlow.Extraction.Worker/docflow_worker/supplier_invoice_models.py
src/DocFlow.Extraction.Worker/docflow_worker/validators/supplier_invoice.py
src/DocFlow.Extraction.Worker/tests/test_french_multi_vat_invoice.py
```

New model added:

```text
SupplierInvoiceTaxBreakdown
- category_code
- rate
- taxable_amount
- tax_amount (optional)
```

New invoice field intended:

```text
tax_breakdown: list[SupplierInvoiceTaxBreakdown]
```

## 7. CRITICAL CURRENT FAILURE — start the next chat here

Public Reference Benchmark **#69**:

```text
run id: 36827420919
head: fd7aa33c8d2fa8ef5894d9ae01891886b0649c7d
result: FAILURE
```

The workflow failed **before corpus build / French public benchmark** because the unit suite failed:

```text
1 failed, 64 passed
```

Exact failing test:

```text
tests/test_australian_multipage_invoice.py::
test_extracts_tax_inclusive_retail_invoice_across_pages
```

Exact mismatch:

```text
expected validation_status: valid
actual validation_status:   incomplete
```

The corpus build and actual French benchmark were skipped, so do **not** claim that F20260023 has been validated on the real PDF yet.

### Root cause has already been identified

Do not spend the next chat rediscovering it.

While adding `tax_breakdown`, the French implementation accidentally overwrote parts of the already-green Australian GST implementation.

At the green baseline commit `77f80b1...`, `SupplierInvoiceData` contained:

```python
tax_inclusive: bool = False
```

At current HEAD, that field was accidentally dropped while `tax_breakdown` was added.

Likewise, at the green baseline the invoice validator contained special tax-inclusive branches:

```text
_validate_subtotal:
    if invoice.tax_inclusive:
        validate tax-inclusive line-total sum against invoice.total

_validate_vat:
    if invoice.tax_inclusive:
        validate subtotal + GST == total
```

Those branches were accidentally replaced by the new multi-rate-VAT implementation.

### Correct fix direction

Merge the behaviors; do NOT choose one or the other.

`SupplierInvoiceData` must contain **both**:

```python
tax_inclusive: bool = False
tax_breakdown: list[SupplierInvoiceTaxBreakdown] = Field(default_factory=list)
```

Validator logic should preserve this precedence:

```text
_validate_subtotal:
    1. if tax_inclusive -> existing Australian GST logic
    2. elif document-level discount -> discount logic
    3. else -> inherited normal subtotal logic

_validate_vat:
    1. if tax_inclusive -> existing Australian GST reconciliation
    2. elif tax_breakdown -> new French multi-rate VAT reconciliation
    3. else -> inherited single-rate VAT logic
```

Do not remove any already-green Town House / Phoenix / Cargo / Casterton behavior.

After fixing this merge, first run the Python tests (or the single unified validation workflow) and expect the Australian regression to return to green. Only then let the public corpus stage run and inspect the **real French F20260023 result**.

## 8. Public Reference workflow policy

Current workflow:

```text
.github/workflows/public-reference-benchmark.yml
```

It now runs Python regression tests before downloading the public corpus. This was intentional to avoid wasting external-download/benchmark time when unit regressions already exist.

Current workflow is also configured to require existing important hard cases in the manifest. French admission was added to the same runtime corpus path and should be treated as required for the French validation stage.

Do not create separate full CI runs for every edit. Preferred sequence:

```text
fix related code + tests as one block
        ↓
one implementation commit (optionally [skip ci])
        ↓
one validation commit/run
        ↓
inspect result once
```

If the unified Public Reference workflow already runs all Python tests plus public corpus, do not additionally launch redundant Python Worker/Smoke/E2E workflows unless a change specifically requires them.

## 9. Current corpus / milestone target

Last confirmed green baseline before French admission:

```text
11 admitted documents
11/11 green
54/54 checked fields
```

French F20260023 should become the next admitted document if its real runtime PDF passes after the regression fix.

Milestone engineering target remains roughly:

```text
15+ admitted unique PDFs
4+ newly represented hard-case classes
both digital and OCR documents
2+ locale/language variants beyond dominant English layouts
1+ genuine multi-page item-table case
```

Already represented hard-case classes now include:

```text
line-level discounts
document-level discounts
mixed native-text + image OCR
German labels / decimal comma / negative values
genuine multi-page item continuation
Australian GST-inclusive totals
```

French multi-rate VAT is **in progress**, not yet closed.

Remaining useful coverage after French is green:

- broader OCR degradation (noise/skew/low contrast), preferably real public document;
- additional real documents to move corpus toward 15+;
- possibly another tax-layout variation if it adds genuinely new evidence rather than duplicate coverage.

There is still no measured evidence requiring ONNX/LLM fallback.

## 10. First actions in the new chat

Do these in order:

1. Work on continuation branch `DocFlow/v_1.1.1.6_HardCases_2`.
2. Read this file and inspect current model/validator only as needed.
3. Restore `tax_inclusive` to `SupplierInvoiceData` while keeping `tax_breakdown`.
4. Merge the previous Australian GST validator branches with the new French multi-rate VAT branch using the precedence described above.
5. Do not change unrelated parsers.
6. Run **one** validation workflow, not a cascade of Actions.
7. If unit tests are green, inspect the real French F20260023 public benchmark result.
8. Fix only the measured remaining French failure, if any, in one connected block.
9. When French passes, update the handoff/baseline and proceed toward degraded-OCR / 15+ corpus coverage.

## 11. Useful known-good reference commit

If unsure how Australian GST validation looked before the accidental overwrite, compare current code against:

```text
77f80b1c2bf966a5b8d17dbf3586c21fcedf019e
```

Specifically inspect:

```text
src/DocFlow.Extraction.Worker/docflow_worker/supplier_invoice_models.py
src/DocFlow.Extraction.Worker/docflow_worker/validators/supplier_invoice.py
```

Do not revert the entire branch to this commit because that would remove French multi-VAT work. Merge the missing behavior forward.

---

## Final state at chat handoff

```text
Milestone: 1.1.1.6 HardCases ACTIVE
Last fully green real baseline: 11/11, 54/54 fields, run #68
Current feature in progress: French multi-rate VAT / fr-FR
Current validation run #69: FAILED at unit regression before corpus build
Failure: Casterton tax-inclusive invoice became incomplete
Root cause: French model/validator overwrite dropped existing tax_inclusive behavior
Next move: merge tax_inclusive + tax_breakdown support, then one validation run
Do not start 1.1.1.7 yet
```
