# DocFlow v1.1.1.32 — Reconciliation Review Workflow Market Update

Date: **2026-10-05**  
Status: **VALIDATED OPERATIONAL REVIEW MILESTONE**  
Repository: `avysotsky/DocFlow`  
Branch: `DocFlow/v_1.1.1.32_ReconciliationReviewWorkflow`  
Validated functional head: `52ec70f54cb6b762d4e3940b443de94e099d098d`

## Purpose

v1.1.1.32 turns the stateless invoice-to-PO comparison from v1.1.1.31 into an operational reconciliation workflow that can be used by a human reviewer.

The milestone closes the market gap identified in v1.1.1.30/v1.1.1.31 around:

- persisted reconciliation cases;
- explicit review/approval state;
- human decision audit trail;
- discrepancy evidence;
- customer-facing reconciliation reports.

It does **not** claim a complete AP product or accounting-system integration.

## Market requirements changed by this milestone

| Requirement | v1.1.1.31 | v1.1.1.32 | Evidence |
|---|---|---|---|
| Persisted reconciliation case | NOT BUILT | **DONE** | PostgreSQL `ReconciliationCases` |
| Reconciliation review state | NOT BUILT | **DONE** | Open / NeedsReview / Approved / Rejected / Resolved |
| Human approve/reject/resolve | NOT BUILT | **DONE** | authenticated decision API |
| Immutable review audit trail | NOT BUILT | **DONE** | append-only `ReconciliationCaseAuditEvents` |
| Reviewer attribution | NOT BUILT | **DONE** | API-key client name persisted on actions |
| Decision note | NOT BUILT | **DONE** | optional for Approve, required for Reject/Resolve |
| Reconciliation discrepancy evidence | API ONLY | **DONE + persisted** | values, delta, check status, messages retained in case report |
| Reconciliation CSV | NOT BUILT | **DONE** | one row per reconciliation check |
| Reconciliation XLSX | NOT BUILT | **DONE** | Case / Checks / Audit History |
| Tenant-isolated case access | NOT BUILT | **DONE** | customer-scoped create/read/export/decision |
| Terminal-state protection | NOT BUILT | **DONE** | repeat decisions return conflict |
| Dedicated graphical review UI | NOT BUILT | **NOT BUILT** | API/export workflow only |
| Multi-level approval hierarchy | NOT BUILT | **NOT BUILT** | one review decision layer |
| Accounting posting | NOT BUILT | **NOT BUILT** | QuickBooks/Xero still external integration work |

## Reconciliation case lifecycle

A reconciliation can now become a durable operational object.

Initial state:

```text
Reconciliation Match
-> ReviewStatus = Open

Reconciliation NeedsReview
-> ReviewStatus = NeedsReview
```

Allowed reviewer transitions:

```text
Open
-> Approved
-> Rejected

NeedsReview
-> Approved
-> Rejected
-> Resolved
```

Terminal states:

```text
Approved
Rejected
Resolved
```

A terminal case cannot be changed again through the current API.

This is intentionally conservative. There is no implicit reopen or silent status overwrite.

## Persisted data

### ReconciliationCases

Stores:

- tenant/customer id;
- invoice document id;
- purchase-order document id;
- reconciliation status;
- review status;
- full reconciliation report JSON;
- created/updated timestamps;
- creating client identity.

### ReconciliationCaseAuditEvents

Append-only decision history stores:

- case id;
- action;
- previous review status;
- new review status;
- note;
- client/reviewer identity;
- timestamp.

The audit table has an index on:

```text
(ReconciliationCaseId, OccurredAt)
```

## API surface

### Create persisted invoice/PO reconciliation case

```http
POST /api/reconciliation/invoice-po/cases
```

### Get case

```http
GET /api/reconciliation/cases/{caseId}
```

### Apply reviewer decision

```http
POST /api/reconciliation/cases/{caseId}/decision
```

Decisions:

- `Approve`;
- `Reject`;
- `Resolve`.

`Reject` and `Resolve` require a reviewer note.

### Business export

```http
GET /api/reconciliation/cases/{caseId}/export?format=reconciliation-csv

GET /api/reconciliation/cases/{caseId}/export?format=reconciliation-xlsx
```

Unknown formats return `400`.

A case owned by another tenant is indistinguishable from an absent case and returns `404`.

## Reconciliation CSV

The business CSV is one row per reconciliation check.

Columns include:

- case id;
- invoice document id;
- PO document id;
- reconciliation status;
- review status;
- check scope;
- invoice item index;
- PO item index;
- match method;
- invoice SKU;
- PO supplier reference;
- field;
- check status;
- invoice value;
- PO value;
- delta;
- evidence message;
- latest review action;
- latest decision note;
- latest reviewer;
- latest action time.

This is intended for operational reconciliation reporting, not as a raw technical JSON dump.

## Reconciliation XLSX

Workbook sheets:

```text
Case
Checks
Audit History
```

### Case

Contains case-level identifiers, status, check counts, timestamps and latest reviewer decision.

### Checks

Contains document and line-item checks, including:

- field;
- invoice value;
- PO value;
- delta;
- status;
- match method;
- source indexes/references;
- evidence message.

### Audit History

Contains every recorded case lifecycle event and reviewer decision.

## End-to-end validation

Final functional workflow:

```text
Automation E2E
run: 37321585590
head: 52ec70f54cb6b762d4e3940b443de94e099d098d
result: SUCCESS
```

The workflow validates:

1. real PostgreSQL migration application;
2. invoice processing;
3. PO processing;
4. exact Match reconciliation;
5. persisted Match case;
6. persisted NeedsReview mismatch case;
7. tenant isolation;
8. Match -> Approve;
9. NeedsReview -> Resolve;
10. NeedsReview -> Reject;
11. Reject without note -> 400;
12. second decision on terminal case -> 409;
13. audit history;
14. reviewer attribution;
15. business reconciliation CSV;
16. business reconciliation XLSX;
17. CSV mismatch values and deltas;
18. XLSX Case / Checks / Audit History sheets;
19. invalid export format -> 400;
20. cross-tenant export -> 404;
21. restart recovery regression.

The latest code-bearing API/export head also passed .NET CI:

```text
.NET CI
head: d2809eb8763fee638f10ed838fa35c4fb85d0dc1
result: SUCCESS
```

Commits after that head only added the export E2E verifier and workflow invocation.

## Verified discrepancy example

The mismatch scenario intentionally changes the first PO line:

```text
invoice unit price: 12.5
PO unit price:      13.5
delta:              -1

invoice line total: 250
PO line total:      270
delta:              -20
```

The case starts as:

```text
ReconciliationStatus = NeedsReview
ReviewStatus = NeedsReview
```

After reviewer resolution:

```text
ReviewStatus = Resolved
LatestAction = Resolve
Reviewer = e2e-primary
Note = Price difference accepted after supplier confirmation.
```

The same evidence is verified in both API and export surfaces.

## Honest commercial scope after v1.1.1.32

DocFlow can now demonstrate an operational invoice/PO exception workflow:

```text
invoice PDF / scanned PDF
+
purchase-order PDF
-> extraction
-> deterministic validation
-> duplicate suspicion
-> human correction
-> deterministic invoice-to-PO matching
-> persisted reconciliation case
-> exception evidence
-> reviewer approve / reject / resolve
-> audit trail
-> reconciliation CSV/XLSX
-> invoice CSV/XLSX
-> PO CSV/XLSX
-> API / webhook
```

This is materially closer to the live buyer requirement:

> review exceptions with evidence/calculations and produce spreadsheet output.

## Claims we must NOT make

Do not claim:

- three-way matching with receipts/GRNs;
- contract reconciliation;
- credit-memo processing;
- fuzzy/semantic item matching;
- universal invoice or PO accuracy;
- generic multi-level approval workflows;
- graphical AP review UI;
- QuickBooks/Xero posting;
- Outlook/Gmail OAuth integration;
- SharePoint/Google Drive ingestion;
- calibrated per-field AI confidence.

## Remaining market-backed gaps

After v1.1.1.32 the most important repeated gaps remain:

1. mailbox/email PDF intake;
2. QuickBooks Online / Xero posting;
3. SharePoint / Google Drive intake;
4. field-level extraction evidence/confidence;
5. receipt/GRN three-way reconciliation;
6. contract / credit-memo document families;
7. customer-facing review UI.

## Recommended next milestone

Recommended:

`DocFlow/v_1.1.1.33_MailboxIntake`

Reason:

- multiple live buyer workflows begin with invoices arriving by email;
- unlike QuickBooks/Xero, basic mail ingestion can be validated without customer accounting mappings;
- a provider-neutral mail boundary can be tested locally and kept outside extraction core;
- it gives DocFlow a complete operational entry path before any provider-specific posting adapter.

Recommended narrow scope:

1. ingest MIME/RFC822 email messages;
2. select PDF attachments only;
3. persist mailbox/message identity for idempotency;
4. submit accepted PDFs through the existing DocFlow intake pipeline;
5. retain source metadata such as sender, subject, message id and received time;
6. prove duplicate-message/duplicate-attachment prevention;
7. add a provider-neutral IMAP polling adapter validated against a local test mail server;
8. add retry/restart recovery;
9. do **not** claim Gmail/Outlook OAuth until tested against real provider credentials.

This scope is market-backed, testable, and does not require customer accounting credentials.
