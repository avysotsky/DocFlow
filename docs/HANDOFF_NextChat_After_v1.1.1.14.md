# DocFlow — Next Chat Handoff After v1.1.1.14

Use this file as the starting state for the next DocFlow development chat.

## Repository state

Repository: `avysotsky/DocFlow`  
Completed branch: `DocFlow/v_1.1.1.14_RestartRecovery`  
Previous branch: `DocFlow/v_1.1.1.13_ProcessingRetries`

Main implementation commit:

```text
7463302b609cc301231e77d6602707ca35c3d822
Recover persisted document work after host restart
```

Validation:

```text
.NET CI #27 -> success (run 36871910152)
Automation E2E #103 -> success (run 36871910065)
```

Only these two relevant workflows ran. Deployment Smoke, Scanned OCR E2E and Public Reference Benchmark were not triggered.

Detailed milestone handoff:

```text
docs/HANDOFF_v1.1.1.14_RestartRecovery.md
```

## Current product state

DocFlow currently supports:

```text
API-key authenticated tenant
  -> PDF upload
  -> PostgreSQL-backed restart reconciliation
  -> in-memory processing queue
  -> bounded technical-failure retry
  -> digital PDF or conditional Tesseract OCR
  -> invoice/quotation detection and deterministic extraction
  -> arithmetic/business validation
  -> PostgreSQL persistence
  -> tenant-scoped inbox
  -> human review/correction
  -> CSV/XLSX export
```

Production container deployment, health/readiness checks and opt-in migrations remain in place.

Public-reference extraction baseline remains:

```text
17/17 public documents passed
98/98 checked business fields matched
17/17 document types correct
17/17 validation statuses correct
```

No extraction/OCR behavior changed in `v1.1.1.14`.

## Restart recovery state

Startup hosted-service order:

```text
DocumentProcessingRecoveryHostedService
DocumentProcessingBackgroundService
```

Recovery selects persisted documents where:

```text
Status is Uploaded or Processing
and no ExtractionResult exists
```

Those ids are re-enqueued before the normal single-reader consumer starts.

Important architecture rule: all such `Processing` rows are recovered immediately. A stale-age threshold was deliberately not implemented because in the current single-instance architecture any `Processing` row that already exists when the new host starts belongs to the dead previous process. A one-shot threshold could strand recent work until another restart.

`Processed`, `NeedsReview`, `Failed`, and documents that already have extraction results are not automatically recovered.

Automation E2E proves a persisted `Uploaded` row and an orphaned `Processing` row both complete after a real API restart without calling `/process`, while an already completed invoice is not reprocessed.

## Processing reliability boundary

The queue remains an in-memory `Channel<Guid>`.

The current single-instance reliability model is now:

```text
PostgreSQL persisted state
+ startup recovery
+ bounded in-process retries
+ persisted attempt/failure diagnostics
+ extraction-result idempotency
```

This handles ordinary single-instance process restarts but is not a distributed job queue. Do not introduce RabbitMQ/Kafka or database leases unless horizontal/multi-instance processing becomes a real requirement.

## CI discipline

Continue sparse CI:

- docs/intermediate maintenance -> `[skip ci]`;
- coherent implementation batch;
- `.NET CI` + Automation E2E for normal API/domain/persistence/processing changes;
- Deployment Smoke only for actual Docker/compose/health deployment-contract changes;
- Scanned OCR E2E only for OCR/extraction-runner/fixture changes;
- Public Reference Benchmark only for extraction-rule changes.

## Recommended next milestone

Create `v1.1.1.15` after inspecting the current document/file lifecycle.

Strongest narrow candidate: **Retention / Delete**.

Inspect:

- `Document.DeleteAt` and whether it is currently used anywhere;
- `IFileStorage.DeleteAsync`;
- EF cascade relationships for `ExtractionResult` and `DocumentReview`;
- tenant ownership checks in `DocumentsController`;
- behavior when deletion races with queued/processing work.

A useful narrow milestone would likely provide tenant-scoped explicit deletion with safe file/database cleanup and clear terminal/race semantics. Only add automatic scheduled retention if it can be kept small and deterministic; manual deletion is enough to close the first customer lifecycle gap.

Other later candidates remain reviewer/audit identity and distributed processing ownership when scaling actually requires it.
