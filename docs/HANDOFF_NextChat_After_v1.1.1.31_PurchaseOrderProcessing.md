# DocFlow — Next Chat Handoff After v1.1.1.31 Purchase Order Processing

Status: **COMPLETED TECHNICAL MILESTONE / READY FOR NEXT SCOPE DECISION**  
Repository: `avysotsky/DocFlow`  
Completed branch: `DocFlow/v_1.1.1.31_PurchaseOrderProcessing`  
Validated technical head: `dfb04742d7e3cc818c3a4d9e0a5bd6dd2a904f73`

## What v1.1.1.31 added

v1.1.1.31 moved DocFlow from invoice-only AP processing to a validated invoice + Purchase Order workflow.

Completed capabilities:

- `purchase_order` document type;
- PO auto detection;
- deterministic PO extraction;
- PO arithmetic/business validation;
- sparse PO -> incomplete/NeedsReview behavior;
- business `po-csv` and `po-xlsx` exports;
- deterministic invoice ↔ PO reconciliation;
- auditable mismatch values/deltas;
- independent public PO validation;
- frozen SHA-guarded PO benchmark;
- E2E match and mismatch scenarios.

## Current PO model

Supported fields:

- supplier name;
- PO number;
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

Missing values remain missing. Do not infer values just to make a PO “valid”.

## Validation evidence

### Primary PO benchmark

```text
6/6 documents passed
141/141 checked fields matched
29/29 header fields
112/112 line-item fields
```

Run: `37281402155`

### Independent frozen PO benchmark

Selected after initial PO parser work, first used as untouched holdout, then frozen after the exposed parser gaps were corrected.

```text
5/5 documents passed
52/52 checked fields matched
26/26 header fields
26/26 line-item fields
```

Run: `37281402218`

Every source has a fixed SHA-256 guard.

### Combined tested PO evidence

```text
11 documents
193/193 checked business fields
55/55 header fields
138/138 line-item fields
```

This is evidence for tested public layout families only, not a universal accuracy claim.

## Reconciliation implementation

API:

```http
POST /api/reconciliation/invoice-po
```

Core implementation:

- `src/DocFlow.Application/Abstractions/IInvoicePurchaseOrderReconciliationService.cs`
- `src/DocFlow.Infrastructure/Processing/InvoicePurchaseOrderReconciliationService.cs`
- `src/DocFlow.Api/Controllers/ReconciliationController.cs`

Matching rules:

1. tenant-scoped document loading;
2. invoice and PO document-family checks;
3. reviewed structured data participates;
4. PO number check;
5. currency check;
6. invoice SKU ↔ PO supplier reference exact normalized match;
7. fallback exact normalized description match;
8. quantity / unit price / line-total checks;
9. 0.01 numeric tolerance;
10. no fuzzy guessing.

Unpaired invoice lines cause review.

Unmatched PO lines are reported but do not automatically fail one invoice because partial PO fulfillment is legitimate.

## Reconciliation E2E

Automation E2E proves:

### Match case

- PO `PO-78421`;
- five invoice lines;
- five PO lines;
- 5/5 SKU/reference matches;
- outcome `Match`.

### Mismatch case

First line intentionally differs:

```text
unit price: 12.50 -> 13.50
line total: 250.00 -> 270.00
```

Expected:

- overall `NeedsReview`;
- mismatch evidence contains both values;
- remaining four lines pass.

## Business exports

Invoice:

- `invoice-csv`;
- `invoice-xlsx`.

Purchase Order:

- `po-csv`;
- `po-xlsx`.

Legacy technical Path/Value exports remain.

## Final validated CI at technical head

All green:

```text
Python Worker CI                       37281402241
Benchmark Smoke                        37281402198
Purchase Order Public Benchmark        37281402155
Purchase Order Independent Benchmark   37281402218
PO Independent Holdout Discovery       37281402239
Purchase Order Discovery Corpus        37281402213
Scanned OCR E2E                        37281402259
Automation E2E                         37281402142
```

## Important parser lessons from the independent holdout

Do not remove the independent benchmark. It caught real issues not exposed by the first PO corpus:

- title-style UKRI PO number;
- slash-month dates;
- VAT percentage misread as money;
- vertical Net Amount columns;
- vertical Grand Total;
- blank Quantity/UOM handling;
- supplier-reference rows with far-right UOM/quantity;
- false pseudo-items from delivery/quotation continuation text.

## Current honest commercial demo

DocFlow can now demonstrate:

```text
Supplier invoice PDF
+
Purchase Order PDF
-> extraction
-> deterministic validation
-> review/correction
-> duplicate suspicion
-> deterministic reconciliation
-> discrepancy evidence
-> business CSV/XLSX
-> API/webhook
```

This is materially closer to the live invoice/PO automation and AP reconciliation jobs captured in the market matrix.

## Still NOT built

- receipt/GRN three-way matching;
- contract reconciliation;
- credit memos;
- fuzzy/semantic item matching;
- persisted reconciliation cases;
- reconciliation approval workflow;
- reconciliation CSV/XLSX report;
- QuickBooks/Xero posting;
- mailbox ingestion;
- SharePoint/Google Drive ingestion;
- customer-facing review UI;
- calibrated field-level extraction confidence.

## Recommended next milestone

Proposed name:

`DocFlow/v_1.1.1.32_ReconciliationReviewWorkflow`

Recommended scope:

1. persist a reconciliation result/case;
2. store case status: Open / NeedsReview / Approved / Rejected or equivalent;
3. preserve field/item discrepancy evidence;
4. add business `reconciliation-csv` and `reconciliation-xlsx`;
5. allow a reviewer to resolve/approve exceptions;
6. retain an audit trail;
7. add E2E for create -> review -> export.

Why this next:

- it is directly supported by the live requirement for review with evidence/calculations;
- it is fully testable without external customer credentials;
- it turns the current on-demand JSON reconciliation into a customer-usable operational workflow;
- it avoids pretending generic QuickBooks/Xero/OAuth mappings can be validated without a real sandbox/customer.

Do not start QuickBooks/Xero/mailbox work unless either:

- a real pilot supplies credentials/mapping rules; or
- the commercial strategy explicitly chooses that provider-specific investment.

## Branch strategy

Do not merge directly into historically lagging `main` merely to continue development.

For the next milestone, branch from the completed `DocFlow/v_1.1.1.31_PurchaseOrderProcessing` head after the documentation-only closure commits.
