# DocFlow — handoff v1.1.1.16 Original PDF Access

Status: **ACTIVE**  
Repository: `avysotsky/DocFlow`  
Branch: `DocFlow/v_1.1.1.16_OriginalPdfAccess`  
Base: `DocFlow/v_1.1.1.15_RetentionDelete`

## Why this milestone exists

Human review and tenant-scoped document metadata already exist, but the authenticated API cannot stream the original uploaded PDF. Reviewers therefore cannot retrieve the source document through DocFlow itself.

## Scope

Keep `v1.1.1.16` narrow:

1. Add `GET /api/documents/{id}/file`.
2. Enforce the existing API-key tenant boundary; cross-tenant or absent ids return `404`.
3. Stream the stored PDF through `IFileStorage.OpenReadAsync` without loading the full file into memory.
4. Return `application/pdf` and a safe attachment filename derived from `OriginalFileName`.
5. If the database row exists but the backing file is missing, return a controlled sanitized server response without exposing filesystem/storage paths.
6. Remove `StorageKey` from the public `GET /api/documents/{id}` response because clients no longer need the internal storage locator.
7. Extend the existing Automation E2E/restart script to prove exact bytes, headers, tenant isolation, missing-file behavior and deleted-document behavior.

## Non-goals

Do not add:

- S3/object storage;
- signed URLs;
- CDN/range proxy infrastructure beyond normal ASP.NET Core stream/range support;
- file replacement/versioning;
- preview/image rendering;
- reviewer identity;
- extraction/OCR changes.

## Acceptance criteria

```text
GET /api/documents/{id}/file -> exact original PDF bytes
Content-Type -> application/pdf
Content-Disposition -> safe attachment filename
range processing enabled
cross-tenant/absent -> 404
missing backing file -> controlled sanitized 500 response
public document metadata no longer exposes StorageKey
deleted document -> 404
.NET CI and Automation E2E remain green
```
