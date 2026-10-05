# DocFlow v1.1.1.31 — Market Requirements Update

Date: **2026-10-05**  
Status: **PURCHASE ORDER + RECONCILIATION MILESTONE VALIDATED**  
Repository: `avysotsky/DocFlow`  
Branch: `DocFlow/v_1.1.1.31_PurchaseOrderProcessing`  
Validated technical head: `dfb04742d7e3cc818c3a4d9e0a5bd6dd2a904f73`

## Purpose

v1.1.1.31 closes two market gaps identified in `MARKET_REQUIREMENTS_v1.1.1.30.md`:

1. separate Purchase Order extraction;
2. deterministic invoice-to-PO reconciliation with auditable discrepancy evidence.

This milestone does **not** claim generic procurement automation, three-way matching, accounting posting, or universal PO extraction.

## Market requirements changed by this milestone

| Requirement | v1.1.1.30 | v1.1.1.31 | Evidence |
|---|---|---|---|
| Separate PO document extraction | NOT BUILT | **DONE for tested public layout families** | PO model, auto detection, deterministic extractor, validator, two benchmark gates |
| PO header fields | NOT BUILT | **DONE for current scope** | supplier, PO number, order date, currency, totals where present |
| PO line items | NOT BUILT | **DONE for current scope** | reference, description, need-by date, quantity, UOM, unit price, line total where present |
| Sparse PO handling | NOT BUILT | **DONE** | absent values remain null; document becomes incomplete/NeedsReview |
| PO arithmetic validation | NOT BUILT | **DONE** | line/subtotal/total checks without invented values |
| Business PO CSV/XLSX | NOT BUILT | **DONE** | `po-csv`, `po-xlsx` |
| Invoice-to-PO matching | NOT BUILT | **DONE for deterministic pilot scope** | tenant-scoped reconciliation service + API |
| PO number / currency checks | NOT BUILT | **DONE** | document-level reconciliation checks |
| SKU/reference line matching | NOT BUILT | **DONE** | invoice SKU ↔ PO supplier_reference exact normalized match |
| Description fallback matching | NOT BUILT | **DONE, exact only** | normalized exact description fallback |
| Quantity / unit price / line total comparison | NOT BUILT | **DONE** | expected/actual/delta evidence, 0.01 numeric tolerance |
| Mismatch to human review | NOT BUILT | **DONE** | overall `NeedsReview` if required checks cannot pass |
| Reconciliation evidence/calculations | NOT BUILT | **PARTIAL / API DONE** | structured checks with values/deltas; no dedicated UI or persisted case yet |
| Multi-invoice partial PO fulfillment | NOT BUILT | **SUPPORTED conservatively** | unmatched PO lines are reported but do not automatically fail one invoice |
| Human corrections used in reconciliation | NOT BUILT | **DONE** | reconciliation composes reviewed structured data |
| Reconciliation spreadsheet report | NOT BUILT | **NOT BUILT** | current reconciliation result is JSON/API |
| Persisted reconciliation case / approval | NOT BUILT | **NOT BUILT** | computed on request; no generic approval workflow |
| Receipt / GRN three-way matching | NOT BUILT | **NOT BUILT** | invoice ↔ PO only |
| Fuzzy/AI item matching | NOT BUILT | **NOT BUILT by design** | avoids false-positive matching until separately validated |
| QuickBooks / Xero posting | NOT BUILT | **NOT BUILT** | still customer/provider-specific |
| Mailbox / SharePoint / Drive intake | NOT BUILT | **NOT BUILT** | still adapter work |

## Purchase Order data model

Current PO extraction can represent:

- supplier name;
- purchase-order number;
- order date;
- currency;
- line number;
- supplier reference;
- description;
- need-by date;
- quantity;
- UOM;
- unit price;
- line total;
- subtotal;
- tax amount;
- total;
- payment terms;
- notes.

Missing fields are not fabricated. Sparse public orders remain `incomplete` and require review rather than being forced to `valid`.

## Purchase Order validation evidence

### Primary public PO benchmark

Workflow: **Purchase Order Public Benchmark**  
Validated run: `37281402155`

Result:

```text
documents: 6/6 passed
checked fields: 141
matched fields: 141

header fields: 29/29
line-item fields: 112/112

overall accuracy: 100%
header accuracy: 100%
line-item accuracy: 100%
```

This corpus covers priced, zero-price, sparse, multipage and UKRI-style public PO layouts.

### Independent frozen PO benchmark

The second PO set was selected after the initial PO parser work. It was first run as an untouched discovery holdout, exposed real gaps, and was then frozen with ground truth and SHA-256 source checks.

Workflow: **Purchase Order Independent Benchmark**  
Validated run: `37281402218`

Result:

```text
documents: 5/5 passed
checked fields: 52
matched fields: 52

header fields: 26/26
line-item fields: 26/26

overall accuracy: 100%
header accuracy: 100%
line-item accuracy: 100%
```

Frozen documents:

- KPMG `P5039687`;
- IDEXX `P5058264`;
- Minster `P5063409`;
- Edwards public PO;
- UKRI `UKR10015660`.

Every source PDF is guarded by its expected SHA-256. If the remote source changes, corpus construction fails instead of silently validating a different document.

### Combined evidence

Across the two separate PO benchmark gates:

```text
documents: 11
checked fields: 193
matched fields: 193
header fields: 55/55
line-item fields: 138/138
```

These numbers apply only to the explicitly checked ground-truth fields and tested public layout families. They are not a universal PO accuracy claim.

## Important parser gaps found by the independent holdout

The independent corpus materially changed the parser:

- UKRI title-style PO identifiers such as `Purchase Order UKR10015660.0`;
- slash-month dates such as `19/AUG/2025`;
- vertical `Net Amount` layouts;
- VAT percentages no longer being misread as money;
- vertically emitted `Grand Total`;
- sparse rows with blank Quantity/UOM;
- referenced UKHSA rows where `Each` and quantity are far-right columns;
- prevention of delivery/quote continuation text becoming a second pseudo-item.

This is why the independent benchmark is kept separate from the original public benchmark.

## Invoice-to-PO reconciliation contract

Endpoint:

```http
POST /api/reconciliation/invoice-po
```

Request identifies:

- invoice document ID;
- purchase-order document ID.

Current deterministic checks:

1. correct tenant and document families;
2. invoice PO number vs PO number;
3. invoice currency vs PO currency;
4. invoice line SKU vs PO supplier reference;
5. fallback to normalized exact description;
6. quantity;
7. unit price;
8. line total.

Numeric comparison uses a `0.01` tolerance.

The service uses reviewed/corrected structured data where human review exists.

## Reconciliation outcome semantics

`Match` is returned only when:

- the invoice has line items;
- all required document-level checks pass;
- every invoice line is deterministically paired;
- all required item checks pass.

`NeedsReview` is returned when:

- a required identity/value is missing;
- a line cannot be paired deterministically;
- quantity / unit price / line total differs;
- document-level identity checks fail.

Unmatched PO lines are reported separately and do not automatically fail the invoice because a PO may be fulfilled across several invoices.

No fuzzy or LLM-based pairing is performed.

## Reconciliation E2E evidence

`Automation E2E` verifies both:

### Exact match

Synthetic invoice + PO `PO-78421`:

- five invoice lines;
- five PO lines;
- all paired by SKU/reference;
- document checks passed;
- no review checks;
- outcome `Match`.

### Intentional discrepancy

The first PO line is changed from:

```text
unit price 12.50 -> 13.50
line total 250.00 -> 270.00
```

Expected result:

- outcome `NeedsReview`;
- unit-price mismatch evidence present;
- line-total mismatch evidence present;
- remaining four invoice lines pass.

Validated workflow at technical head:

- Automation E2E: `37281402142` — success;
- Scanned OCR E2E: `37281402259` — success;
- Python Worker CI: `37281402241` — success;
- Benchmark Smoke: `37281402198` — success;
- Purchase Order Public Benchmark: `37281402155` — success;
- Purchase Order Independent Benchmark: `37281402218` — success;
- Purchase Order Independent Holdout Discovery: `37281402239` — success;
- Purchase Order Discovery Corpus: `37281402213` — success.

## Business-ready PO exports

Explicit export formats:

```text
po-csv
po-xlsx
```

CSV is one row per PO line.

XLSX contains:

- Purchase Order sheet;
- Line Items sheet.

Export E2E is part of the green Automation E2E workflow.

## Commercial scope after v1.1.1.31

DocFlow can now honestly demonstrate this pilot workflow:

```text
invoice PDF / scanned PDF
+
purchase-order PDF
-> classify
-> extract invoice + PO business data
-> deterministic validation
-> suspected duplicate handling
-> human correction when required
-> deterministic invoice-to-PO reconciliation
-> discrepancy evidence
-> invoice CSV/XLSX
-> PO CSV/XLSX
-> JSON/API
-> original PDF access
-> webhook completion
```

This is directly relevant to buyers asking for invoice + PO processing and reconciliation.

## Claims we must NOT make

Do not claim:

- universal PO extraction accuracy;
- generic three-way invoice/PO/receipt matching;
- fuzzy semantic item matching;
- contract or credit-memo reconciliation;
- QuickBooks/Xero posting;
- Outlook/Gmail/SharePoint/Drive ingestion;
- generic multi-level approval UI;
- persisted reconciliation cases;
- calibrated field-level extraction confidence;
- arbitrary document-family support.

A customer pilot must still begin with representative source documents and explicit mapping/reconciliation rules.

## Recommended next technical milestone

Do **not** build a QuickBooks/Xero connector blindly without a sandbox/company and mapping rules.

The next fully testable market-backed extension should be a **reconciliation review package**, for example:

1. persisted reconciliation case/result;
2. explicit review/approval state;
3. business reconciliation CSV/XLSX containing matched key, expected value, actual value, delta and status;
4. API to accept/resolve a reconciliation exception;
5. audit history for that decision.

That would close more of the buyer requirement “review UI with evidence/calculations” without pretending a customer-specific accounting integration is generic.
