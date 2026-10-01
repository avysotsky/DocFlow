# DocFlow — active handoff for 1.1.1.9 DocumentInbox

Status: **ACTIVE**  
Working branch: `DocFlow/v_1.1.1.9_DocumentInbox`  
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

Extraction/OCR/export serialization are out of scope unless the inbox implementation exposes a concrete contract defect.

## 2. Product gap

The API currently exposes document operations only by a known document GUID:

```text
GET /api/documents/{id}
GET /api/documents/{id}/extraction-result
GET /api/documents/{id}/export?format=...
```

There is no collection endpoint. A UI or external integration therefore cannot recover a customer's document history, processing state, review state, or export availability after losing its in-memory upload response.

This is a direct product-usability blocker for the initial MVP.

## 3. Target API

```text
GET /api/documents?customerId={guid}&page=1&pageSize=50
```

Optional filters:

```text
status=Uploaded|Processing|Processed|NeedsReview|Failed
documentType=supplier_invoice
```

`customerId` is mandatory for this milestone. This is not an authentication/authorization mechanism; real tenant authorization remains a separate security milestone.

## 4. Response contract

Return a paginated envelope:

```text
page
pageSize
totalCount
totalPages
items[]
```

Each item should contain enough information for an inbox/list UI without additional N+1 API calls:

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

Do not expose `StorageKey` in collection responses.

`extractionResultId != null` also tells the client that persisted-result/export operations are available.

## 5. Query semantics

- require non-empty `customerId`;
- page is 1-based;
- pageSize range: 1..100, default 50;
- status filter is case-insensitive but must be a defined `DocumentStatus`;
- documentType is trimmed/lower-cased before exact comparison;
- ordering is deterministic: `CreatedAt DESC`, then `Id DESC`;
- totalCount is computed after customer/status/documentType filters and before paging;
- use `AsNoTracking()` for read-only queries;
- include extraction summary through one SQL query / left join, not N+1 lookups.

Existing indexes already support the principal access path:

```text
(CustomerId, CreatedAt)
Status
```

No database migration is expected for the initial inbox implementation.

## 6. HTTP validation

Return `400 Bad Request` for:

- empty customerId;
- page < 1;
- pageSize < 1 or > 100;
- unknown status;
- documentType longer than the persisted 100-character schema limit.

A valid query with no matching documents returns `200` with an empty `items` array and `totalCount = 0`.

## 7. Acceptance criteria

1. A customer can retrieve their uploaded documents after the original upload response is gone.
2. Documents from a different customer are not returned by the customerId filter.
3. Newest-first ordering is deterministic.
4. Status filter works for processing/review/failure states.
5. documentType filter works against persisted classification.
6. Pagination metadata and page slicing are correct.
7. Each item includes persisted validation/confidence when an extraction result exists.
8. A document without an extraction result remains visible with null extraction fields.
9. Invalid query parameters return 400.
10. Existing upload/process/export scenarios remain green.
11. Intermediate commits use `[skip ci]`; run one Automation E2E after the coherent inbox block.

## 8. Immediate implementation plan

Add the collection GET to `DocumentsController`, then extend the existing Automation E2E with a focused verifier that checks customer isolation, filters, paging, extraction summary, and invalid query handling.
