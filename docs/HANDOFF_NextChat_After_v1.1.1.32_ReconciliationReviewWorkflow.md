# DocFlow — Next Chat Handoff After v1.1.1.32 Reconciliation Review Workflow

Status: **COMPLETED MILESTONE / CONTINUE WITH v1.1.1.33**  
Repository: `avysotsky/DocFlow`  
Completed branch: `DocFlow/v_1.1.1.32_ReconciliationReviewWorkflow`  
Validated functional head: `52ec70f54cb6b762d4e3940b443de94e099d098d`

## What v1.1.1.32 accomplished

v1.1.1.31 proved deterministic invoice-to-PO reconciliation.

v1.1.1.32 turned that comparison into an operational, persisted human-review workflow.

Completed:

- persisted reconciliation cases;
- review states;
- Approve / Reject / Resolve decisions;
- decision note rules;
- append-only audit history;
- reviewer/client attribution;
- tenant isolation;
- reconciliation CSV;
- reconciliation XLSX;
- E2E validation of the full lifecycle.

## Persistence model

### ReconciliationCases

Stores:

- CustomerId;
- InvoiceDocumentId;
- PurchaseOrderDocumentId;
- ReconciliationStatus;
- ReviewStatus;
- ReportJson;
- CreatedAt;
- UpdatedAt;
- CreatedByClient.

### ReconciliationCaseAuditEvents

Stores:

- ReconciliationCaseId;
- Action;
- PreviousStatus;
- NewStatus;
- Note;
- PerformedByClient;
- OccurredAt.

Audit events are append-only in the current service model.

## Review state machine

Initial state:

```text
Match       -> Open
NeedsReview -> NeedsReview
```

Transitions:

```text
Open -> Approved | Rejected

NeedsReview -> Approved | Rejected | Resolved
```

Terminal states cannot be changed again.

`Reject` and `Resolve` require a note.

## API

Create persisted case:

```http
POST /api/reconciliation/invoice-po/cases
```

Get case:

```http
GET /api/reconciliation/cases/{caseId}
```

Review decision:

```http
POST /api/reconciliation/cases/{caseId}/decision
```

Business export:

```http
GET /api/reconciliation/cases/{caseId}/export?format=reconciliation-csv
GET /api/reconciliation/cases/{caseId}/export?format=reconciliation-xlsx
```

## Business reconciliation export

### CSV

One row per reconciliation check.

Contains:

- case identifiers/status;
- check scope;
- item indexes;
- match method;
- invoice SKU;
- PO reference;
- field;
- check status;
- invoice value;
- PO value;
- delta;
- evidence message;
- latest reviewer action/note/identity/time.

### XLSX

Sheets:

```text
Case
Checks
Audit History
```

## Final validation

Functional gate:

```text
Automation E2E
run: 37321585590
head: 52ec70f54cb6b762d4e3940b443de94e099d098d
result: SUCCESS
```

Code-bearing export/API head:

```text
.NET CI
head: d2809eb8763fee638f10ed838fa35c4fb85d0dc1
result: SUCCESS
```

The final E2E proves:

- migrations;
- existing invoice/PO processing;
- persisted case creation;
- tenant isolation;
- Approve;
- Resolve;
- Reject;
- note validation;
- terminal-state conflict;
- audit history;
- reconciliation CSV;
- reconciliation XLSX;
- mismatched values and deltas;
- cross-tenant export denial;
- restart recovery.

## Current commercial workflow

DocFlow can now honestly demonstrate:

```text
PDF/scanned invoice
+
Purchase Order PDF
-> extract
-> validate
-> review/correct extraction
-> duplicate suspicion
-> deterministic reconciliation
-> persist exception case
-> reviewer decision
-> audit trail
-> reconciliation CSV/XLSX
-> invoice CSV/XLSX
-> PO CSV/XLSX
-> API/webhook
```

## Important non-capabilities

Still not built:

- mailbox/email intake;
- Gmail/Outlook OAuth;
- SharePoint/Drive intake;
- QuickBooks/Xero posting;
- receipt/GRN three-way matching;
- contract reconciliation;
- credit memos;
- fuzzy item matching;
- graphical review UI;
- generic multi-level approval engine;
- calibrated field confidence.

## Recommended next milestone

Create:

`DocFlow/v_1.1.1.33_MailboxIntake`

Recommended first scope:

1. MIME/RFC822 message parser;
2. PDF attachment filtering;
3. message/attachment idempotency;
4. source email metadata persistence;
5. feed attachments through existing document intake;
6. local IMAP adapter;
7. retry/restart recovery;
8. E2E against a local mail server;
9. no provider OAuth claims yet.

Why mailbox next:

- repeated live jobs start with shared mailbox/email;
- it is upstream of the already working DocFlow processing/reconciliation pipeline;
- it is fully testable without a QuickBooks/Xero customer realm;
- it creates a more complete commercial AP automation demo.

## Branch strategy

Do not merge to historically lagging `main` just to continue.

Start the next branch from the completed v1.1.1.32 closure HEAD after the documentation commits.
