# DocFlow — handoff v1.1.1.15 Retention / Delete

Status: **ACTIVE**  
Repository: `avysotsky/DocFlow`  
Branch: `DocFlow/v_1.1.1.15_RetentionDelete`  
Base: `DocFlow/v_1.1.1.14_RestartRecovery`

## Why this milestone exists

DocFlow persists uploaded PDF files plus document/extraction/review records, but customers currently have no explicit lifecycle operation to remove a document. `Document.DeleteAt` exists in the domain but is not used by the current flow.

## Scope

Keep `v1.1.1.15` narrow:

1. Add tenant-scoped explicit document deletion.
2. Allow deletion only for terminal `Processed`, `NeedsReview`, and `Failed` documents.
3. Reject `Uploaded` and `Processing` deletion with `409 Conflict` to avoid races with the current in-memory worker/queue.
4. Remove the stored PDF and the `Document` record; rely on existing EF/PostgreSQL cascade delete for `ExtractionResult` and `DocumentReview`.
5. Cross-tenant ids remain `404`.
6. After successful deletion the resource remains invisible (`404` on subsequent reads/actions).
7. Extend Automation E2E to prove database/file cleanup and active-document conflict behavior.

## Consistency model

Deletion is limited to terminal documents, so the processing worker does not own them.

For the local filesystem + PostgreSQL pair, there is no distributed transaction. The implementation will use a database transaction around the row delete and perform file deletion before committing the database transaction. If storage deletion fails, the database transaction is rolled back. A database commit failure after successful file deletion remains a rare residual consistency risk and must not be represented as a fully atomic cross-resource transaction.

## Non-goals

Do not add in this milestone:

- automatic scheduled retention;
- soft-delete/tombstone state;
- background storage garbage collection;
- cancellation of queued/processing jobs;
- distributed locking;
- batch delete;
- reviewer identity;
- extraction/OCR changes.

## Acceptance criteria

```text
DELETE /api/documents/{id} is tenant-scoped
Processed/NeedsReview/Failed can be deleted
Uploaded/Processing -> 409
cross-tenant id -> 404
document row disappears
related ExtractionResult/DocumentReview rows disappear by cascade
stored PDF disappears
subsequent GET/export/review/diagnostics for deleted id -> 404
existing processing/restart/retry flows remain green
.NET CI and Automation E2E remain green
```
