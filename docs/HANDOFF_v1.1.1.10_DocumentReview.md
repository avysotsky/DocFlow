# DocFlow — active handoff for 1.1.1.10 DocumentReview

Status: **ACTIVE**  
Working branch: `DocFlow/v_1.1.1.10_DocumentReview`  
Started from completed milestone: `DocFlow/v_1.1.1.9_DocumentInbox`

## 1. Starting baseline

```text
Public Reference Benchmark #78: SUCCESS
69 Python tests
17/17 public documents
98/98 checked business fields
17/17 document types
17/17 validation statuses

Automation E2E #98: SUCCESS
.NET build: 0 warnings / 0 errors
CSV/XLSX export: SUCCESS
Document inbox: SUCCESS
```

Extraction/OCR rules are out of scope unless the review implementation reveals a concrete contract defect.

## 2. Product gap

DocFlow can already route uncertain or invalid extraction to `NeedsReview`, and the inbox exposes that status. However there is no supported operation for a human/operator to correct the persisted structured data and confirm the document.

Current flow can therefore stop permanently at:

```text
upload -> extraction -> NeedsReview
```

That is a direct MVP workflow gap. A document requiring review cannot be repaired through the API, and downstream export would continue to expose the uncorrected extraction result.

## 3. Milestone objective

Add a minimal deterministic human-review API over the existing persisted `ExtractionResult`.

The review operation must:

1. operate only on an existing document/extraction result;
2. accept corrected structured `data` without rerunning OCR/Python extraction;
3. preserve the original extraction metadata needed for traceability;
4. mark the result as human-reviewed;
5. move a reviewed document out of `NeedsReview` into `Processed` only after a valid correction payload is persisted;
6. make CSV/XLSX export immediately reflect the reviewed persisted result;
7. remain idempotent/reject conflicting stale review writes predictably.

## 4. Proposed API contract

Initial endpoint:

```text
PUT /api/documents/{id}/review
```

Request:

```json
{
  "expectedExtractionResultId": "guid",
  "data": { "...": "corrected structured document data" },
  "note": "optional operator note"
}
```

`expectedExtractionResultId` is an optimistic-concurrency guard for the MVP. The request is rejected if the persisted extraction result changed since the client loaded it.

The endpoint does not accept arbitrary engine/document-type/validation fields from the client. Those remain server-owned.

## 5. Persistence design

Prefer preserving review evidence rather than overwriting without traceability.

Minimal additional persisted review metadata should record at least:

```text
ReviewedAt
ReviewNote
OriginalStructuredDataJson (or equivalent immutable review snapshot)
```

The exact shape should be selected after inspecting the current `ExtractionResult` entity/configuration. A database migration is expected if review metadata is added to the existing result.

No user identity is available yet, so `ReviewedBy` should not be fabricated. Authentication/tenant identity is a separate security milestone.

## 6. Server-side review semantics

For the first MVP review operation:

- document must exist;
- extraction result must exist;
- document must currently be `NeedsReview` (or a narrowly justified equivalent state);
- `expectedExtractionResultId` must match the persisted result;
- `data` must be a JSON object;
- the corrected result keeps the existing engine and document type;
- review does not rerun extraction;
- corrected persisted result becomes the source used by existing GET/export endpoints;
- resulting document status becomes `Processed`;
- review metadata is persisted atomically with the corrected result;
- repeated/stale/conflicting review requests return a deterministic conflict response rather than silently overwriting newer state.

## 7. HTTP behavior to verify

Expected outcomes:

```text
200  successful review
400  malformed/non-object data or invalid request
404  document or extraction result does not exist
409  document is not reviewable or expectedExtractionResultId is stale
```

## 8. Acceptance criteria

1. A real `NeedsReview` document can be corrected through the API.
2. The document becomes `Processed` after successful review.
3. Existing extraction engine/document type remain server-owned and unchanged.
4. Original structured data is retained for traceability before the first human correction.
5. Reviewed data is returned by `GET /extraction-result`.
6. CSV/XLSX export reflects the reviewed data without rerunning extraction.
7. Stale/concurrent review attempts are rejected predictably.
8. Non-reviewable/missing documents are handled with 404/409 as appropriate.
9. Existing upload/process/inbox/export scenarios remain green.
10. No Public Reference rerun unless extraction code changes.
11. Intermediate commits use `[skip ci]`; one Automation E2E is run after the coherent review block.

## 9. Immediate engineering plan

1. Inspect `ExtractionResult` entity, EF configuration and save/export services.
2. Choose the smallest traceable persistence change and migration.
3. Add a review application service rather than putting persistence mutation directly in the controller.
4. Add `PUT /api/documents/{id}/review`.
5. Extend Automation E2E with one `NeedsReview -> reviewed -> Processed -> export` scenario plus stale-write/error checks.
6. Run one final Automation E2E for the complete block.
