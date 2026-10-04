# DocFlow — Next Chat Handoff: Commercial Validation After v1.1.1.29

Status: **ACTIVE HANDOFF FOR NEXT CHAT**  
Repository: `avysotsky/DocFlow`  
Completed technical branch: `DocFlow/v_1.1.1.29_CommercialInvoiceHardening`  
Parent technical branch: `DocFlow/v_1.1.1.28_WebhookDelivery`

## Why v1.1.1.29 exists

v1.1.1.28 was intentionally frozen for business validation.

A concrete commercial-readiness test then exposed a real missing capability: unseen supplier invoice layouts produced weak line-item extraction. That is a valid customer/business-driven reason to resume coding under the decision rule from the prior handoff.

v1.1.1.29 is therefore not general feature expansion. It is **commercial invoice extraction hardening based on measured failures**.

## Validation methodology

Two runtime-downloaded public corpora are now retained as regression evidence. Third-party PDFs are **not committed**.

### Blind commercial corpus

12 public supplier invoices not used by the previous 17-document public-reference baseline.

Final GitHub Actions run:

- workflow: `Blind Commercial Invoice Validation`
- run id: `37215280311`
- head: `b3e52d97c891a80a4a2e9c11e13c79e81d06eba3`
- conclusion: `success`

Final metrics:

```text
documents: 12
checked fields: 198
overall field accuracy: 96.46%
header accuracy: 93.26%
line-item accuracy: 99.08%
line-item fields: 108 / 109
```

### Independent holdout corpus

A separate frozen 9-invoice corpus was created after the first blind corpus so that improvements could be checked for overfitting.

Final GitHub Actions run:

- workflow: `Commercial Invoice Holdout Validation`
- run id: `37215280335`
- head: `b3e52d97c891a80a4a2e9c11e13c79e81d06eba3`
- conclusion: `success`

Final metrics:

```text
documents: 9
processing errors: 0

overall strict accuracy: 96.19%
overall semantic accuracy: 98.10%

header strict accuracy: 97.14%
header semantic accuracy: 100%

line-item strict accuracy: 94.29%
line-item semantic accuracy: 94.29%
```

Commercial gate:

```text
header >= 90%: PASS
line items >= 90%: PASS
processing errors == 0: PASS
```

## What changed

The extraction worker now contains a deterministic generic invoice recovery layer for additional real-world layout families.

Major improvements include:

- horizontal and vertically emitted invoice tables;
- tables with row ordinals before business quantity;
- ACTIVITY / QTY / RATE / AMOUNT layouts;
- mixed VAT/non-VAT layouts;
- meter/copy-charge style invoices;
- compact service-charge tables;
- multi-line item descriptions;
- OCR-degraded numeric cells;
- invoice number/date/due-date recovery;
- purchase-order number recovery;
- VAT rate/amount recovery;
- compact VAT registration identifiers no longer mistaken for VAT money;
- deterministic arithmetic reconciliation before accepting recovered items.

The implementation remains deterministic. No LLM/ONNX extraction fallback was introduced.

## Regression protection

Validation tooling added:

```text
.github/scripts/build_blind_commercial_invoice_corpus.py
.github/workflows/blind-commercial-invoice-validation.yml

.github/scripts/build_commercial_holdout_invoice_corpus.py
.github/workflows/commercial-invoice-holdout-validation.yml
```

The holdout workflow now runs when `src/DocFlow.Extraction.Worker/**` changes.

Existing Python regression tests also run before both commercial validation workflows.

## Remaining known imperfections

The independent holdout still contains two strict line-item description mismatches:

1. Somerset Web Services:
   expected full wrapped description, current result preserves the main first description line.

2. Stubbington:
   expected the Description column only (`Survey at Shedfield`), while current result also includes neighboring Activity/VAT text.

The numeric business fields for those items are correct.

These two description differences do not prevent the commercial gate from passing.

Do **not** continue tuning these cases just to maximize benchmark score unless a real prospect/customer requires that exact description fidelity.

## Business conclusion

The earlier business-validation result was initially negative:

```text
header/totals ~47%
line items ~9%
```

After measured, layout-general hardening and an independent holdout test, DocFlow now passes the commercial readiness gate for the current narrow scope:

**English supplier invoice extraction and validation, including line items, on the tested layout families.**

This does not justify a claim of universal invoice accuracy.

Do not market the benchmark as a guaranteed customer accuracy rate. Every prospect should still begin with a small sample of their own documents.

## Commercial offer now allowed to test

Primary offer:

**Supplier Invoice Data Extraction & Validation Pilot**

Suggested funnel:

```text
free sample: up to 3 representative customer invoices

if sample is viable:
paid pilot: 20-50 invoices
fixed-price hypothesis: about $299

deliver:
- structured header/totals
- line items
- deterministic arithmetic validation
- NeedsReview/exception identification
- customer-specific CSV/XLSX/JSON output
- measured accuracy on the customer's own corpus
```

Do not promise:

- arbitrary document types;
- handwriting;
- universal multilingual OCR;
- purchase-order documents as a separate supported family;
- invoice-to-PO matching;
- QuickBooks integration unless scoped and built for that customer;
- 99% production accuracy for unknown customer documents.

## Technical freeze resumes

Do not continue extraction tuning or add product features simply because another benchmark improvement is possible.

The next required evidence is:

```text
real prospect
-> 3 sample invoices
-> DocFlow processes them
-> measured result
-> prospect agrees workflow saves work
-> paid pilot
```

Only resume coding when a real prospect/pilot exposes a concrete missing capability.

## Repository note

The repository's `main` branch is historically far behind the milestone branches.

A temporary PR to `main` was intentionally closed without merge after GitHub showed a 371-commit / 211-file historical delta.

Do not use `main` as the base for this milestone unless the repository branch strategy is deliberately changed.

## Recommended next task

Return to commercial execution:

1. prepare a clean customer-facing XLSX/CSV pilot output;
2. prepare 90-150 second demo;
3. use Upwork/direct outreach;
4. offer a 3-document sample;
5. acquire the first real customer corpus;
6. quote the first paid 20-50-document pilot;
7. code only against customer-discovered gaps.
