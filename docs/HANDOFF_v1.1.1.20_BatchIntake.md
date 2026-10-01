# DocFlow — handoff v1.1.1.20 Batch Intake

Status: **ACTIVE**  
Repository: `avysotsky/DocFlow`  
Branch: `DocFlow/v_1.1.1.20_BatchIntake`  
Base: `DocFlow/v_1.1.1.19_OperationalMetrics`

## Why this milestone exists

The customer API currently accepts one PDF per request. The processing queue can already handle many independent document ids, but upload validation, storage, persistence rollback, retention timestamp assignment and enqueue are implemented directly in the single-upload controller action.

## Scope

1. Extract the existing single-document intake path into one reusable scoped service.
2. Keep existing single-upload behavior and validation semantics.
3. Add `POST /api/documents/batch` using multipart `Files`.
4. Bound a batch to at most 10 files and 50 MB aggregate payload size; retain the existing 20 MB per-file limit.
5. Batch-level count/aggregate-size violations reject the request before any file is persisted.
6. Within an accepted batch, each file is independent:
   - valid file -> persisted then enqueued and reported `Accepted`;
   - file validation failure -> `Rejected` with a safe reason;
   - storage/database failure for that file -> cleanup when possible and report `Failed` without aborting remaining files.
7. Enqueue each document only after its database row is durable.
8. Do not add ZIP, email/mailbox, cloud polling or asynchronous batch-job orchestration.

## Response contract

Return one result per submitted file, preserving input order, plus accepted/rejected/failed counts. Batch processing itself is sequential to keep memory and storage pressure bounded for the current single-instance MVP.

## Acceptance

```text
single upload uses the same intake service as batch
batch auth/tenant boundary unchanged
0 or >10 files -> 400
aggregate size >50 MB -> 400 before persistence
valid + invalid files can coexist in one request
valid files are independently persisted/enqueued
invalid files do not block valid files
response preserves per-file outcomes/input order
existing processing/review/restart/retention behavior remains green
.NET CI + Automation E2E green
```
