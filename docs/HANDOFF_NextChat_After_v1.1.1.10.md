# DocFlow — handoff for next chat after v1.1.1.10 DocumentReview

Status: **READY FOR NEW CHAT**  
Repository: `avysotsky/DocFlow`  
Current completed branch: `DocFlow/v_1.1.1.10_DocumentReview`

## 1. Current product state

DocFlow MVP currently supports:

```text
PDF upload
  -> automatic digital/scanned handling
  -> native text extraction or conditional Tesseract OCR
  -> automatic document-type detection
  -> deterministic supplier quotation/invoice extraction
  -> deterministic arithmetic validation
  -> PostgreSQL persistence
  -> document inbox/history
  -> human correction for NeedsReview documents
  -> CSV/XLSX export of effective reviewed data
```

ONNX/LLM extraction remains intentionally deferred because measured hard cases were solved deterministically and the current public benchmark is green.

## 2. Completed milestones relevant to continuation

### 1.1.1.6 HardCases
Completed real-document hard-case extraction work including multipage GST-inclusive invoice support and French multi-rate VAT.

### 1.1.1.7 DegradedOCR
Completed degraded-OCR recovery.

Validation baseline:

```text
Public Reference Benchmark #78: SUCCESS
69 Python regression tests
17/17 public documents passed
98/98 checked business fields matched
17/17 document types correct
17/17 validation statuses correct
Automation E2E #96: SUCCESS
Scanned OCR E2E #73: SUCCESS
```

### 1.1.1.8 Export
Completed persisted-result CSV/XLSX export.

### 1.1.1.9 DocumentInbox
Completed customer-scoped paginated document history/inbox with status/document-type filters and extraction summary.

Validation:

```text
Automation E2E #98: SUCCESS
```

### 1.1.1.10 DocumentReview
Completed human review/correction workflow.

Key behavior:

```text
NeedsReview document
  -> PUT /api/documents/{id}/review
  -> corrected data persisted in separate DocumentReview row
  -> original machine ExtractionResult remains immutable
  -> document becomes Processed
  -> GET extraction-result exposes effective reviewed data + review metadata
  -> CSV/XLSX export uses effective reviewed data
```

Persistence design:

- `ExtractionResult` remains immutable machine output.
- New `DocumentReview` entity stores:
  - `DocumentId`
  - `ExtractionResultId`
  - corrected `data` JSON (`jsonb`)
  - optional note
  - `ReviewedAt`
- one review per document/result in current MVP.
- no fabricated `ReviewedBy`; authentication/identity is not implemented yet.

Review endpoint:

```text
PUT /api/documents/{id}/review
```

Request shape:

```json
{
  "expectedExtractionResultId": "guid",
  "data": { "...": "corrected structured document data" },
  "note": "optional operator note"
}
```

Review conflict/error semantics:

```text
200 successful review
400 malformed request/non-object data
404 missing document/extraction result
409 stale extraction result, duplicate review or non-reviewable document
```

Final validation:

```text
Automation E2E #99: SUCCESS
.NET build: 0 warnings / 0 errors
EF migration AddDocumentReviews: SUCCESS
Document review E2E: SUCCESS
Existing upload/process/export/inbox scenarios: SUCCESS
```

Automation E2E #99 specifically verified:

- stale/malformed review writes rejected;
- `NeedsReview -> Processed` after human correction;
- original extraction result id preserved;
- reviewed data returned by GET;
- reviewed data exported to CSV/XLSX;
- duplicate/non-reviewable/missing review cases handled predictably.

Completed handoff for this milestone is also in:

```text
docs/HANDOFF_v1.1.1.10_DocumentReview.md
```

## 3. Current branch/head

Current completed branch:

```text
DocFlow/v_1.1.1.10_DocumentReview
```

Validation commit for Automation E2E #99:

```text
7dc25d20dcc16d935672eaf2af57ed6e3c3ca2d1
```

Completed-handoff commit:

```text
ca273f4d9c4ec6e515407f1bcfd69d3726ff215a
```

This next-chat handoff is intentionally committed with `[skip ci]`.

## 4. GitHub Actions discipline — IMPORTANT

The user explicitly requested reducing GitHub Actions frequency.

Continue with these rules:

1. Do **not** launch CI after every small fix.
2. Batch related changes into one coherent engineering block.
3. Use `[skip ci]` on intermediate commits.
4. Run the narrowest relevant workflow once at the end of the block.
5. Run Public Reference Benchmark only when extraction/OCR behavior changes or when a milestone explicitly requires it.
6. Run Scanned OCR E2E only when OCR behavior changes or at an appropriate major closure.
7. Do not mutate workflow comments merely to create repeated validation runs.
8. Polling an already-running workflow is fine, but avoid excessive polling.

## 5. What NOT to redo

Do not repeat already completed work unless new evidence reveals a regression:

- French multi-rate VAT;
- GST-inclusive multipage invoice parsing;
- degraded OCR recovery;
- CSV/XLSX export;
- document inbox;
- human review persistence/API/read/export overlay;
- Public Reference Benchmark #78 baseline.

## 6. Starting point for the new chat

No `1.1.1.11` branch had been defined at the moment this handoff was created.

Before creating a new branch:

1. search the repository for any newly existing `DocFlow/v_1.1.1.11_*` branch or roadmap/handoff;
2. if none exists, select the next milestone from a real product/operational gap, not from arbitrary extraction-rule expansion;
3. create the new branch from `DocFlow/v_1.1.1.10_DocumentReview` only after that check.

Potential next product gaps to evaluate, without treating this list as a pre-decided roadmap:

- authentication / tenant identity / authorization;
- review operator identity/audit expansion once auth exists;
- operational observability and processing failure/retry UX;
- document deletion/retention lifecycle;
- batch upload / batch processing;
- deployability/production configuration;
- customer-facing UI/API usability gaps.

The next milestone should be chosen based on the most important remaining MVP/business bottleneck.

## 7. First actions in the new chat

Use this sequence:

```text
1. Read this handoff.
2. Inspect repository branches for an existing 1.1.1.11 direction.
3. Inspect current README / architecture / relevant handoffs only as needed.
4. Choose or resume the next measured product milestone.
5. Create/update its handoff before substantial implementation.
6. Work in coherent blocks with [skip ci].
7. Run one narrow validation workflow at the end of the block.
```

Do not ask the user to restate repository context already contained here.
