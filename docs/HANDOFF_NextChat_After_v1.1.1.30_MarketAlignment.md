# DocFlow — Next Chat Handoff After v1.1.1.30 Market Alignment

Status: **COMPLETED MILESTONE / CONTINUE WITH v1.1.1.31**  
Repository: `avysotsky/DocFlow`  
Completed branch: `DocFlow/v_1.1.1.30_MarketAlignment`

## Why v1.1.1.30 exists

The previous invoice-hardening milestone proved invoice extraction on two commercial corpora. v1.1.1.30 moved from extraction-only validation to direct market alignment against live invoice/AP automation jobs.

## Live market evidence

The repository contains:

`docs/MARKET_REQUIREMENTS_v1.1.1.30.md`

It records eight live Upwork jobs and maps recurring buyer requirements to actual DocFlow capabilities.

Repeated requirements confirmed in live jobs:

- PDF/scanned invoice intake;
- accurate invoice headers and line items;
- VAT/totals validation;
- duplicate prevention/detection;
- manual review/correction;
- business-ready CSV/XLSX;
- audit/status/retries;
- original document access;
- accounting/workflow integrations;
- email/SharePoint/Drive intake;
- PO processing/reconciliation.

## Completed technical work

### Second independent market corpus

Five new public invoices selected after v1.1.1.29:

- bilingual invoice;
- wrapped QuickBooks-style layout;
- zero-VAT membership invoice;
- four-line VAT table;
- line-discount invoice.

Final validated metrics:

```text
documents: 5
processing errors: 0
overall semantic accuracy: 100%
header semantic accuracy: 100%
line-item semantic accuracy: 100%
strict overall accuracy: 93.33%
strict line-item accuracy: 94.59%
```

### Existing corpora remain green

Independent commercial holdout:

```text
documents: 9
processing errors: 0
overall semantic accuracy: 99.05%
header semantic accuracy: 100%
line-item semantic accuracy: 97.14%
```

Blind commercial corpus:

```text
documents: 12
overall field accuracy: 95.96%
header micro accuracy: 92.13%
line-item micro accuracy: 99.08%
```

### Business-ready invoice export

Added explicit customer-facing formats:

```text
invoice-csv
invoice-xlsx
```

CSV is one row per invoice line item with business columns.

XLSX contains:

- Invoice worksheet;
- Line Items worksheet.

The legacy technical Path/Value CSV/XLSX export remains available.

### Duplicate invoice handling

Added tenant-scoped suspected duplicate detection based on supplier/invoice business identity.

Suspected duplicates are routed to review rather than silently posted.

Business exports expose duplicate review state.

### Regression protection

The v1.1.1.30 branch runs:

- Python Worker CI;
- Benchmark Smoke;
- Scanned OCR E2E;
- Automation E2E;
- Public Reference Benchmark;
- Blind Commercial Invoice Validation;
- Commercial Invoice Holdout Validation;
- Market Alignment Invoice Validation.

Final runs at the validated extraction head were successful.

## Current honest commercial scope

DocFlow can currently support:

```text
PDF / scanned English invoice
-> invoice classification
-> supplier / invoice number / dates / currency / PO reference
-> line items
-> subtotal / VAT / total
-> deterministic validation
-> duplicate suspicion
-> NeedsReview / correction
-> business CSV / XLSX / JSON / API
-> original PDF access
-> webhook completion
```

Do not claim universal invoice accuracy. Customer documents must still be sampled before quoting production automation.

## Remaining market gaps

High-value gaps confirmed by live jobs:

1. separate Purchase Order document extraction;
2. invoice-to-PO reconciliation;
3. QuickBooks/Xero posting adapters;
4. mailbox / Outlook / Gmail / IMAP ingestion;
5. SharePoint / Google Drive ingestion;
6. field-level confidence/evidence;
7. multi-level approval UI/workflow.

Provider-specific integrations must not be called complete without provider/sandbox validation.

## Next milestone

Start:

`v1.1.1.31_PurchaseOrderProcessing`

Justification:

- live USD 4,750 invoice + PO automation job;
- invoice/contract reconciliation buyer explicitly requests PO extraction/matching;
- AP reconciliation jobs repeatedly require document matching;
- unlike QuickBooks/email adapters, PO extraction and deterministic reconciliation can be fully validated now using public documents without customer credentials.

Recommended scope:

1. `purchase_order` document type;
2. PO data model;
3. PO header + line-item extraction;
4. deterministic PO arithmetic validation;
5. public PO corpus;
6. invoice ↔ PO match model;
7. quantity / unit-price / line-total discrepancy reporting;
8. NeedsReview routing for mismatches;
9. no generic procurement UI yet.
