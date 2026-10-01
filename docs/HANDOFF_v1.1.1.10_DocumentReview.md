# DocFlow — completed handoff for 1.1.1.10 DocumentReview

Status: **COMPLETED**  
Completed branch: `DocFlow/v_1.1.1.10_DocumentReview`  
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

Extraction/OCR rules were intentionally unchanged in this milestone.

## 2. Product capability added

DocFlow can now complete the previously terminal workflow:

```text
upload -> extraction -> NeedsReview -> human correction -> Processed
```

Review endpoint:

```text
PUT /api/documents/{documentId}/review
```

Request:

```json
{
  "expectedExtractionResultId": "guid",
  "data": { "...": "corrected structured document data" },
  "note": "optional operator note"
}
```

The client can correct only the structured `data`. Extraction engine, document type, machine validation status and confidence remain server/machine-owned evidence.

## 3. Audit-preserving persistence design

The original `ExtractionResult` is never overwritten.

A separate one-per-document `DocumentReview` entity stores:

```text
Id
DocumentId
ExtractionResultId
CorrectedDataJson
Note
ReviewedAt
```

`CorrectedDataJson` is persisted as PostgreSQL `jsonb`.

Unique indexes on `DocumentId` and `ExtractionResultId` enforce one accepted review for the current MVP flow. The review has a foreign key to `Document`; `ExtractionResultId` is a unique reference/concurrency key whose correspondence is verified by the service.

Migration:

```text
20261001102000_AddDocumentReviews
```

The original machine extraction remains immutable evidence. No duplicated `OriginalStructuredDataJson` snapshot is necessary because the original `ExtractionResult.StructuredDataJson` itself remains untouched.

## 4. Application/service behavior

Added `IDocumentReviewService` / `DocumentReviewService`.

A review succeeds only when:

- the document exists;
- an extraction result exists;
- `expectedExtractionResultId` matches the persisted result;
- the document is currently `NeedsReview`;
- it has not already been reviewed;
- corrected `data` is an object-valued JSON payload.

On success the review record and document transition are persisted atomically and the document becomes `Processed`.

Concurrent duplicate inserts are converted from the PostgreSQL unique violation into the deterministic `AlreadyReviewed` outcome rather than surfacing as HTTP 500.

## 5. HTTP semantics

Verified behavior:

```text
200  successful review
400  malformed/non-object review data
404  missing document/extraction result
409  stale extraction id
409  document not reviewable
409  duplicate/already reviewed document
```

The review endpoint does not rerun OCR or Python extraction.

## 6. Effective reviewed data

Added `ReviewedStructuredDataComposer`.

For an unreviewed document, GET/export use the original machine JSON unchanged.

For a reviewed document, the effective response preserves the original extraction envelope while replacing only:

```text
data = corrected review data
```

and adding:

```json
"human_review": {
  "review_id": "guid",
  "reviewed_at": "ISO-8601 timestamp",
  "note": "..."
}
```

`GET /api/documents/{id}/extraction-result` additionally exposes:

```text
reviewId
reviewedAt
reviewNote
```

CSV/XLSX export uses the same effective reviewed structure, so export reflects the human correction immediately without rerunning extraction.

The outer persisted machine `ValidationStatus` remains the original machine result by design. Human acceptance is represented by `Document.Status = Processed` plus review metadata, rather than rewriting automated validation history.

## 7. E2E coverage

Added `.github/scripts/verify_document_review.py` and wired it into Automation E2E after the existing upload/process/export/inbox scenarios.

The verifier proves:

- stale extraction-result id is rejected with 409;
- malformed non-object data is rejected with 400;
- a real invalid quotation in `NeedsReview` can be corrected;
- document moves to `Processed`;
- original extraction result id is preserved;
- reviewed GET data contains the corrected total and human-review metadata;
- CSV export contains the corrected data and review id;
- duplicate review is rejected with 409;
- already-Processed document is not reviewable;
- missing document returns 404.

## 8. Final validation

Automation E2E #99, run id `36848664647`, head `7dc25d20dcc16d935672eaf2af57ed6e3c3ca2d1`: **SUCCESS**.

Build evidence:

```text
Build succeeded.
0 Warning(s)
0 Error(s)
```

EF migration evidence:

```text
Applying migration '20260929174244_InitialCreate'.
Applying migration '20261001102000_AddDocumentReviews'.
Done.
```

Regression evidence:

```text
Export E2E passed: CSV/XLSX content, equivalent flattened rows,
unsupported format and missing-result behavior verified.

Document inbox E2E passed: customer isolation, deterministic ordering,
status/document-type filters, extraction summary, pagination and query validation verified.
```

Review evidence:

```text
Document review E2E passed: stale/malformed writes rejected,
NeedsReview corrected to Processed, original extraction id preserved,
reviewed data returned and exported,
duplicate/non-reviewable/missing reviews handled predictably.
```

Final workflow result:

```text
Automation E2E passed: quotations, idempotency, review/failure routing,
borderless layout, supplier invoice, CSV/XLSX export,
document inbox and human review verified.
```

## 9. Extraction baseline

Because no extraction/OCR production code changed, Public Reference Benchmark #78 remains authoritative and was intentionally not rerun:

```text
69 Python tests
17/17 public documents
98/98 checked fields
17/17 document types
17/17 validation statuses
```

Scanned OCR E2E was also intentionally not rerun.

## 10. Acceptance criteria status

All `1.1.1.10 DocumentReview` acceptance criteria are met:

1. NeedsReview documents can be corrected through the API;
2. successful review transitions the document to Processed;
3. engine/document type/machine validation remain immutable machine evidence;
4. original structured extraction is retained unchanged;
5. reviewed data is returned by GET;
6. CSV/XLSX export reflects reviewed data;
7. stale/concurrent/duplicate writes are rejected predictably;
8. non-reviewable/missing documents are handled correctly;
9. upload/process/export/inbox regressions remain green;
10. extraction benchmark was not unnecessarily rerun;
11. intermediate commits used `[skip ci]` and one final Automation E2E run validated the coherent block.

Milestone `1.1.1.10 DocumentReview` is complete.
