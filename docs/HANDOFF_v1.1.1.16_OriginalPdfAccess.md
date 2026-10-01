# DocFlow — handoff v1.1.1.16 Original PDF Access

Status: **COMPLETED**  
Repository: `avysotsky/DocFlow`  
Branch: `DocFlow/v_1.1.1.16_OriginalPdfAccess`  
Base: `DocFlow/v_1.1.1.15_RetentionDelete`

## 1. Milestone result

`v1.1.1.16` adds tenant-scoped streaming access to the original uploaded PDF without introducing object storage, signed URLs or a new file subsystem.

Main implementation commit:

```text
35ec117537401b441e054fb4393acbfebc1c5db7
Add tenant-scoped original PDF access
```

Validation:

```text
.NET CI #29
run id: 36876459319
result: success

Automation E2E #105
run id: 36876459466
result: success
```

Only those two relevant workflows ran. Deployment Smoke, Scanned OCR E2E and Public Reference Benchmark were not triggered.

## 2. New file endpoint

Route:

```text
GET /api/documents/{documentId}/file
```

Behavior:

```text
valid tenant-owned document -> streamed PDF
missing/invalid API key -> 401
cross-tenant document -> 404
absent/deleted document -> 404
owned row with missing backing file -> sanitized 500 problem response
```

The endpoint queries only the authenticated tenant's document row, then opens the stored object through `IFileStorage.OpenReadAsync`.

## 3. Streaming contract

The endpoint returns:

```text
Content-Type: application/pdf
Content-Disposition: attachment; filename=<safe original filename>
```

It uses ASP.NET Core `FileStreamResult` with range processing enabled. The file is streamed from the underlying `FileStream`; the controller does not read the whole PDF into memory.

The E2E test proves a `Range: bytes=0-4` request returns `206 Partial Content` with `%PDF-`.

## 4. Safe download filename

`CreateSafeDownloadName` normalizes both slash styles, takes only the final filename component, removes control/path/quote characters, trims whitespace and falls back to `document.pdf` when needed.

The E2E fixture deliberately stores an unsafe-looking original name:

```text
../restart-uploaded.pdf
```

The returned attachment filename is:

```text
restart-uploaded.pdf
```

## 5. Missing backing-file behavior

If PostgreSQL contains the document but the local backing file or directory is missing, `DocumentFilesController` catches `FileNotFoundException` / `DirectoryNotFoundException`, logs the server-side exception and returns:

```text
500
Source document file is unavailable.
```

The response does not expose the storage root or `StorageKey`. Automation E2E explicitly checks that neither path is present in the response body.

## 6. E2E proof

The existing `.github/scripts/verify_restart_recovery.sh` was extended rather than creating another workflow.

It proves:

```text
retrieved PDF bytes exactly match the persisted source fixture
Content-Type is application/pdf
Content-Disposition is attachment with sanitized filename
Range request returns 206 and correct bytes
cross-tenant file access returns 404
missing backing file returns sanitized 500
successful document deletion makes /file return 404
restart recovery remains green
delete lifecycle remains green
all existing Automation E2E scenarios remain green
```

## 7. StorageKey compatibility decision

The initial ACTIVE scope proposed removing `StorageKey` from `GET /api/documents/{id}` once `/file` existed.

That change was deliberately not made in this milestone. Removing an existing response property is a breaking public API change and is not required to implement safe file access.

Current rule:

```text
StorageKey remains for backward compatibility.
New clients should use GET /api/documents/{id}/file.
```

If `StorageKey` is removed later, do it as an explicit API-versioning/deprecation change rather than silently changing an established DTO.

## 8. Extraction baseline

No extraction/OCR behavior changed.

Baseline remains:

```text
17/17 public documents passed
98/98 checked business fields matched
17/17 document types correct
17/17 validation statuses correct
```

## 9. Current MVP flow

```text
API-key authenticated tenant
  -> PDF upload
  -> persisted restart reconciliation
  -> bounded processing retries + diagnostics
  -> digital extraction / conditional OCR
  -> quotation/invoice detection and deterministic extraction
  -> validation + PostgreSQL persistence
  -> tenant inbox
  -> original PDF download
  -> human review/correction
  -> CSV/XLSX export
  -> terminal document deletion
```

## 10. Remaining lifecycle gap

`Document.DeleteAt` still exists as nullable metadata, but the normal upload flow does not currently set it; the constructor defaults it to `null`. There is no automatic retention sweeper.

A future retention milestone should first define an explicit policy rather than assuming `DeleteAt` is already meaningful. Active `Uploaded`/`Processing` work must never be silently deleted by a scheduler.
