# DocFlow v1.1.1.30 — Market Requirements Matrix

Date: **2026-10-04**  
Status: **ACTIVE MARKET-ALIGNMENT REFERENCE**  
Repository: `avysotsky/DocFlow`  
Branch: `DocFlow/v_1.1.1.30_MarketAlignment`

## Purpose

This document ties DocFlow technical work to concrete buyer requirements observed in live Upwork invoice/document-automation jobs.

The goal is not to imitate every technology named in a job post. The goal is to distinguish:

1. business capabilities that repeat across buyers;
2. capabilities DocFlow already proves end-to-end;
3. capabilities that remain customer-specific integration work;
4. job-specific stack requirements that affect freelancer fit even when DocFlow can solve the business problem.

## Live market evidence reviewed

### 1. AI Developer: Invoice and Contract Reconciliation Tool

Upwork job id: `2103504922917816214`  
Status observed: ACTIVE  
URL: https://www.upwork.com/jobs/~022103504922917816214

Buyer asks for:

- PDF / CSV / Excel document intake;
- optional Google Drive / SharePoint intake;
- invoice, contract, PO and credit-memo classification;
- supplier, invoice number, dates, SKU, quantity, unit price, surcharges and totals;
- duplicate invoices/payments;
- invoice vs contract price;
- invoice vs PO / receipt matching;
- review UI with evidence and calculations;
- spreadsheet export;
- security/access controls;
- AI API experience.

### 2. Financial Workflow Expert

Upwork job id: `2103089430254780977`  
Status observed: ACTIVE, already hired one freelancer  
URL: https://www.upwork.com/jobs/~022103089430254780977

Buyer asks for:

- invoice review and approval;
- Xero integration;
- clear Excel billing reports;
- reconciliation;
- automated tests;
- maintainable documentation.

### 3. Power Platform Invoice Automation

Upwork job id: `2105279357194150944`  
Status observed: ACTIVE, historical hire visible  
URL: https://www.upwork.com/jobs/~022105279357194150944

Buyer asks for:

- Outlook shared-mailbox intake;
- SharePoint document storage;
- invoice records linked to original documents;
- duplicate-processing prevention;
- field mapping from document extraction;
- missing / uncertain data to staff review;
- two approval levels;
- corrections;
- original-document access;
- tests for duplicates and failed extraction;
- handoff documentation.

### 4. Email Inbox Ingestion + AI PDF Parsing

Upwork job id: `2100648447821780212`  
Status observed: ACTIVE  
URL: https://www.upwork.com/jobs/~022100648447821780212

Buyer asks for:

- IMAP/OAuth email ingestion;
- PDF attachment handling;
- duplicate email-thread prevention;
- structured JSON;
- MySQL persistence;
- audit history and processing statuses;
- fixed-schema CSV;
- missing-field failure/manual review;
- operational cleanup and deployment documentation.

### 5. PDF Invoice -> QuickBooks

Upwork job id: `2105235116095997959`  
Status observed: ACTIVE  
URL: https://www.upwork.com/jobs/~022105235116095997959

Buyer asks for:

- PDF invoice extraction;
- accurate field mapping;
- QuickBooks integration;
- reliable end-to-end data flow;
- reduction of manual invoice entry.

### 6. Invoice Processing Automation Specialist

Upwork job id: `2103898219652024756`  
Status observed: ACTIVE  
URL: https://www.upwork.com/jobs/~022103898219652024756

Buyer asks for:

- reliable invoice automation;
- accurate invoice data handling;
- reduced manual effort;
- faster turnaround;
- scalable ongoing operation.

### 7. AI-Assisted AP Reconciliation

Upwork job id: `2105237195828734688`  
Status observed: ACTIVE  
URL: https://www.upwork.com/jobs/~022105237195828734688

Buyer asks for:

- invoices arriving by email;
- B/L and shipping documents;
- matching multiple invoices to one shipment;
- document extraction;
- confidence scoring;
- human approval;
- eventual QuickBooks Online posting;
- reliable end-to-end workflow.

### 8. Invoice + PO Processing Automation

Upwork job id: `2100421528346026931`  
Status observed: ACTIVE  
Budget observed: USD 4,750 fixed  
URL: https://www.upwork.com/jobs/~022100421528346026931

Buyer asks for:

- invoice processing;
- purchase-order processing;
- workflow automation via APIs/RPA/scripts;
- data accuracy;
- timely processing.

## Repeating buyer requirements vs DocFlow

| Requirement | Market signal | v1.1.1.30 state | Evidence / decision |
|---|---|---|---|
| PDF invoice intake | Very high | **DONE** | Single + bounded batch upload |
| Digital PDF extraction | Very high | **DONE** | Multi-corpus validation |
| Scanned PDF OCR | High | **DONE for tested English scans** | Tesseract English + scanned E2E |
| Invoice header fields | Very high | **DONE for current invoice scope** | public/blind/holdout/market corpora |
| Line items | Very high | **DONE for current invoice scope** | independent corpora and arithmetic reconciliation |
| Subtotal / VAT / total | Very high | **DONE** | deterministic validation |
| Arithmetic/business validation | High | **DONE** | validator + NeedsReview |
| Missing/invalid data to review | High | **DONE** | NeedsReview + review/correction endpoint |
| Original document access | Medium-high | **DONE** | authenticated PDF streaming |
| Business-ready CSV | High | **DONE in v1.1.1.30** | one row per invoice line item |
| Business-ready XLSX | High | **DONE in v1.1.1.30** | Invoice + Line Items worksheets |
| Duplicate invoice detection | High | **DONE in v1.1.1.30 for pilot scope** | tenant-scoped supplier + invoice number, suspected duplicate -> NeedsReview |
| Request idempotency | High operational value | **DONE** | single/batch persisted idempotency |
| Processing audit/status | High | **DONE** | status, attempts, diagnostics, persistence |
| Retries/recovery | High | **DONE** | retries + restart recovery |
| Webhook integration boundary | Medium-high | **DONE** | transactional completion outbox + signed webhooks |
| Tenant isolation/API auth | High | **DONE** | API-key tenant isolation |
| Custom target-column mapping | High | **PARTIAL** | canonical business export exists; customer-specific schema still scoped per pilot |
| Field-level uncertainty/confidence | High in AI workflows | **PARTIAL** | document/validation confidence + NeedsReview; not calibrated per-field confidence/evidence |
| Email mailbox ingestion | High | **NOT BUILT** | customer/provider-specific adapter |
| Google Drive / SharePoint ingestion | Medium-high | **NOT BUILT** | customer/provider-specific adapter |
| QuickBooks Online posting | High | **NOT BUILT** | customer-specific connector/OAuth/mapping required |
| Xero posting | Medium | **NOT BUILT** | customer-specific connector/OAuth/mapping required |
| Approval workflow levels | Medium | **PARTIAL** | human correction/review exists; not generic multi-level approval engine |
| Separate PO document extraction | Medium-high | **NOT BUILT** | current document families are invoice + quotation |
| Invoice-to-PO matching | Medium-high | **NOT BUILT** | customer-driven reconciliation capability |
| Contracts / credit memos / B/L | Medium | **NOT BUILT** | outside current narrow document family |
| CSV / Excel as input documents | Medium | **NOT BUILT** | current document intake is PDF |
| Direct JPG/PNG intake | Medium | **NOT BUILT** | scanned PDF is supported; direct image upload is not |
| LLM/API extraction fallback | Common in AI-branded jobs | **NOT BUILT** | current extractor is deterministic by design |
| React/Power Apps review UI | Some jobs | **NOT BUILT** | API backend/review flow exists; UI is customer-specific |

## Current extraction evidence

DocFlow must not rely on one tuned corpus.

The current validation model uses four distinct evidence layers:

1. original public-reference corpus;
2. blind commercial corpus;
3. independent commercial holdout;
4. second market-alignment holdout selected after v1.1.1.29.

The second market-alignment corpus contains:

- bilingual invoice layout;
- wrapped QuickBooks-style description;
- zero-VAT membership invoice;
- multi-line four-item VAT table;
- discounted invoice line.

At the validated extraction head before later .NET-only workflow work:

```text
market-alignment documents: 5
processing errors: 0

overall semantic accuracy: 100%
header semantic accuracy: 100%
line-item semantic accuracy: 100%

strict line-item accuracy: 94.59%
```

Semantic comparison normalizes harmless typography differences such as Unicode dash variants. It does not ignore missing or incorrect business data.

## Important job-fit distinction

A job can be a strong **business-problem fit** for DocFlow and still be a weak **freelancer-stack fit**.

Examples:

- a buyer that explicitly requires Python + Claude/OpenAI extraction may value exactly the workflow DocFlow solves, but a C#/.NET deterministic implementation does not prove the requested Python/LLM experience;
- a Power Platform job can validate demand for duplicate review, SharePoint and approvals but does not mean DocFlow should become a Power Apps product;
- a QuickBooks job is a direct product extension opportunity, but the live connector still requires customer-specific OAuth, vendor/account mapping and posting rules.

Do not claim direct compliance with a required stack unless the implementation actually provides it.

## Technical priorities justified by market evidence

### Completed in v1.1.1.30

1. broader unseen-invoice extraction hardening;
2. second independent market holdout;
3. business-ready CSV/XLSX;
4. suspected duplicate invoice detection;
5. cross-corpus regression workflows.

### Next customer-driven integration candidates

Priority A — **QuickBooks Online adapter**

Justification: repeated live jobs explicitly request PDF invoice -> mapped QuickBooks entry.

Do not implement blindly without defining:

- Bill vs Expense vs Invoice target;
- vendor lookup/mapping policy;
- item/account mapping;
- tax code mapping;
- duplicate posting policy;
- OAuth/refresh-token ownership;
- sandbox/company realm for E2E validation.

Priority B — **Mailbox ingestion adapter**

Justification: multiple workflows start with Outlook/Gmail/IMAP PDF attachments.

Keep it outside extraction core:

```text
mailbox adapter
-> DocFlow PDF intake API
-> extraction/validation/review
```

Priority C — **PO + reconciliation vertical**

Justification: higher-budget jobs repeatedly ask for invoice/PO/receipt/contract matching.

This is not a minor parser change. It requires:

- separate PO data model;
- PO extraction;
- match identity/rules;
- quantity/price/tax tolerances;
- exception evidence;
- approval semantics.

Only start once this is the selected commercial direction or a real pilot requires it.

## Commercial scope we can honestly sell now

**Supplier Invoice Data Extraction & Validation**

```text
PDF / scanned PDF
-> invoice classification
-> supplier / number / dates / currency
-> line items
-> subtotal / VAT / total
-> arithmetic validation
-> duplicate suspicion check
-> NeedsReview / correction
-> business CSV / XLSX / JSON / API
-> original document access
-> webhook completion
```

Required customer validation remains:

```text
3 representative customer invoices
-> measured extraction result
-> confirm target output schema
-> confirm review exceptions
-> only then quote production/pilot integration
```

## Claims we must NOT make

Do not claim today that DocFlow already provides:

- generic QuickBooks or Xero posting;
- Outlook/Gmail/SharePoint/Google Drive ingestion;
- separate PO processing;
- invoice-to-PO or invoice-to-contract matching;
- handwriting recognition;
- universal multilingual OCR;
- calibrated field-level AI confidence;
- LLM-based extraction;
- arbitrary document-family support.

These are market-proven opportunities, not completed capabilities.
