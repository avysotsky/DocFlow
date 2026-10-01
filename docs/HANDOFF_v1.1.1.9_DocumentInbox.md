# DocFlow — completed handoff for 1.1.1.9 DocumentInbox

Status: **COMPLETED**  
Completed branch: `DocFlow/v_1.1.1.9_DocumentInbox`  
Started from completed milestone: `DocFlow/v_1.1.1.8_Export`

## 1. Starting baseline

```text
Public Reference Benchmark #78: SUCCESS
69 Python tests
17/17 public documents
98/98 checked fields

Automation E2E #97: SUCCESS
.NET build: 0 warnings / 0 errors
CSV/XLSX persisted-result export: verified
```

Extraction/OCR/export serialization remained out of scope and unchanged.

## 2. Product capability added

DocFlow now exposes a customer-scoped document inbox endpoint:

```text
GET /api/documents?customerId={guid}&page=1&pageSize=50
```

Optional filters:

```text
status=Uploaded|Processing|Processed|NeedsReview|Failed
documentType=supplier_invoice
```

`customerId` is mandatory for this milestone. It scopes the query but is not an authentication or authorization mechanism; tenant authorization remains a separate security concern.

## 3. Response contract

The endpoint returns:

```text
page
pageSize
totalCount
totalPages
items[]
```

Each item includes:

```text
id
customerId
originalFileName
size
documentType
documentStatus
createdAt
processedAt
extractionResultId
validationStatus
confidence
```

`StorageKey` is deliberately not exposed by the collection endpoint.

A non-null `extractionResultId` tells clients that persisted extraction/export operations are available without an additional lookup.

## 4. Query implementation

The collection query:

- requires non-empty `customerId`;
- uses 1-based paging;
- limits `pageSize` to 1..100, default 50;
- parses status case-insensitively and rejects undefined `DocumentStatus` values;
- trims/lower-cases `documentType` before exact persisted comparison;
- orders deterministically by `CreatedAt DESC`, then `Id DESC`;
- computes `totalCount` after filters and before paging;
- uses `AsNoTracking()` for read-only access;
- joins `ExtractionResults` with a left join so extraction summary data is returned without N+1 calls;
- leaves documents without extraction results visible with null extraction fields.

No database migration was required. Existing indexes continue to support the principal access path:

```text
(CustomerId, CreatedAt)
Status
```

## 5. Validation behavior

The endpoint returns `400 Bad Request` for:

- empty customerId;
- page < 1;
- pageSize < 1 or > 100;
- unknown status;
- documentType longer than the persisted 100-character schema limit;
- page offsets that exceed the supported integer range.

A valid customer query with no matching documents returns `200` with an empty `items` array, `totalCount = 0`, and `totalPages = 0`.

## 6. E2E verifier

Added `.github/scripts/verify_document_inbox.py` and wired it into the existing Automation E2E flow.

The verifier covers:

- customer isolation using a second customer fixture;
- deterministic newest-first ordering;
- status filtering, including `NeedsReview`;
- case-normalized document-type filtering;
- persisted extraction result id / validation / confidence summary;
- visibility of failed/uploaded documents without extraction results;
- pagination metadata and disjoint page slicing;
- empty valid customer result;
- invalid query handling;
- absence of `StorageKey` from collection items.

## 7. Final validation

Automation E2E #98 on head `db90a86dbc5f0832d256f243fe7b9774ab6f7351` is fully green.

```text
.NET build: SUCCESS
0 warnings
0 errors
Database migrations: SUCCESS
Synthetic fixtures: SUCCESS
Existing processing scenarios: SUCCESS
CSV/XLSX export regression: SUCCESS
Document inbox E2E: SUCCESS
```

The runtime verifier reported:

```text
Document inbox E2E passed: customer isolation, deterministic ordering,
status/document-type filters, extraction summary, pagination and query validation verified.
```

The full Automation E2E ended with:

```text
Automation E2E passed: quotations, idempotency, review/failure routing,
borderless layout, supplier invoice, CSV/XLSX export and document inbox verified.
```

## 8. Extraction baseline

No extraction/OCR production code changed in this milestone, so Public Reference Benchmark #78 remains the authoritative extraction baseline and was intentionally not rerun:

```text
69 Python tests
17/17 public documents
98/98 checked fields
17/17 document types
17/17 validation statuses
```

Scanned OCR E2E was also not rerun because the inbox change does not affect OCR ingestion or extraction.

## 9. Acceptance criteria status

All DocumentInbox acceptance criteria are met:

1. customer document history can be recovered through the collection API;
2. customer isolation is enforced by the required customerId query filter;
3. newest-first ordering is deterministic;
4. status filtering works for review/failure states;
5. documentType filtering works against persisted classification;
6. paging metadata and slicing are correct;
7. extraction summary fields are included when present;
8. documents without extraction results remain visible with null summary fields;
9. invalid query parameters return 400;
10. existing upload/process/export scenarios remain green;
11. development used `[skip ci]` intermediate commits and one final Automation E2E run.

Milestone `1.1.1.9 DocumentInbox` is complete.
