# DocFlow — Next Chat Handoff After v1.1.1.33 MailboxIntake

Status: **COMPLETED MILESTONE / READY FOR v1.1.1.34**  
Repository: `avysotsky/DocFlow`  
Completed branch: `DocFlow/v_1.1.1.33_MailboxIntake`  
Validated functional head: `2219e6b0b17a8c5ad97f287fe62667bed237967e`

## What v1.1.1.33 accomplished

v1.1.1.33 added a provider-neutral mailbox entry path in front of the existing DocFlow document-processing pipeline.

Completed:

- RFC822/MIME message parsing;
- PDF attachment filtering;
- source email metadata persistence;
- mailbox message identity and MIME-payload conflict detection;
- attachment-to-Document linking through the existing intake service;
- replay/repair behavior without duplicate Document creation;
- persistent IMAP `UIDVALIDITY` / `LastUid` checkpoints;
- background IMAP polling with restart recovery;
- GreenMail SMTP + IMAP end-to-end validation;
- full extraction validation for mailbox-delivered supplier invoices.

## IMAP runtime contract

Configuration section:

```text
Mailbox:Imap
```

Each account supplies:

- Name;
- CustomerId;
- Host;
- Port;
- UseSsl;
- Username;
- Password;
- Folder.

Checkpoint identity:

```text
CustomerId + MailboxKey + FolderName
```

Polling reads UIDs strictly above the persisted `LastUid`. The checkpoint advances only after mailbox ingestion reaches a terminal outcome. A changed server `UIDVALIDITY` resets the cursor for the new mailbox generation.

## GreenMail E2E

GitHub Actions:

```text
Automation E2E
run: 37354803158
head: 2219e6b0b17a8c5ad97f287fe62667bed237967e
result: SUCCESS
```

The E2E proves:

1. GreenMail SMTP and IMAP protocols are ready;
2. an RFC822 invoice is delivered over SMTP;
3. DocFlow reads it over IMAP using MailKit;
4. the PDF enters normal document intake and extraction;
5. invoice `INV-IMAP-001` reaches `Processed`;
6. a positive UID checkpoint is persisted;
7. the API process is stopped;
8. a second RFC822 invoice is delivered;
9. the API restarts;
10. invoice `INV-IMAP-002` is processed;
11. `UIDVALIDITY` remains stable and `LastUid` advances;
12. the first attachment is not duplicated.

## Honest capability boundary

Built and validated:

```text
generic IMAP mailbox
-> RFC822/MIME
-> PDF attachments
-> DocFlow intake
-> extraction / validation
-> persistence / review / reconciliation
```

Not built:

- Gmail OAuth;
- Outlook/Microsoft Graph OAuth;
- provider-specific mailbox webhooks;
- SharePoint / Google Drive intake;
- QuickBooks Online posting;
- Xero posting;
- receipt/GRN three-way matching;
- customer-facing graphical review UI.

## Recommended next milestone

Create:

```text
DocFlow/v_1.1.1.34_AccountingPosting
```

Market-backed next gap:

```text
QuickBooks Online / Xero posting
```

Recommended first scope is deliberately provider-neutral:

1. define an accounting-posting request/target contract;
2. persist a durable posting record/status before any external call;
3. support idempotent posting attempts and bounded retry metadata;
4. expose tenant-scoped posting state through the API;
5. keep provider adapters behind an interface;
6. start with a deterministic local fake adapter and E2E;
7. add real QuickBooks/Xero OAuth only when real provider credentials and mappings are available.

Do not claim live QuickBooks/Xero integration until a real provider sandbox/realm has been exercised.

## Branch strategy

Start `v1.1.1.34` from the completed documentation head of `v1.1.1.33`, not from historically lagging `main`.
