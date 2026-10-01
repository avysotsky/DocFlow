# DocFlow — handoff v1.1.1.14 Restart Recovery

Status: **COMPLETED**  
Repository: `avysotsky/DocFlow`  
Branch: `DocFlow/v_1.1.1.14_RestartRecovery`  
Base: `DocFlow/v_1.1.1.13_ProcessingRetries`

## 1. Milestone result

`v1.1.1.14` closes the main single-instance restart-loss gap of the in-memory processing queue without adding an external broker or changing extraction behavior.

Main implementation commit:

```text
7463302b609cc301231e77d6602707ca35c3d822
Recover persisted document work after host restart
```

Validation:

```text
.NET CI #27
run id: 36871910152
result: success

Automation E2E #103
run id: 36871910065
result: success
```

Only these two relevant workflows ran. Deployment Smoke, Scanned OCR E2E and Public Reference Benchmark did not run.

## 2. Recovery model

A new startup hosted service exists:

```text
DocumentProcessingRecoveryHostedService
```

It is registered before `DocumentProcessingBackgroundService`.

On host startup it queries PostgreSQL for documents that satisfy:

```text
(Status == Uploaded || Status == Processing)
and no ExtractionResult exists
```

Candidate ids are ordered by `CreatedAt`, then `Id`, and re-enqueued into the existing `IDocumentProcessingQueue`.

The normal processing worker then consumes the recovered ids and reuses all existing behavior:

- persisted processing-attempt diagnostics;
- bounded retry policy;
- extraction-result idempotency/unique constraint;
- `Processed` / `NeedsReview` / final `Failed` state transitions.

No database migration was required for this milestone.

## 3. Why all Processing rows are recovered immediately

The ACTIVE handoff initially proposed a configurable stale-processing threshold. Code inspection showed that this is incorrect for the current single-instance architecture.

At the moment a new single application instance starts, any `Processing` row already persisted without an extraction result belongs to the previous process. That previous worker no longer exists.

A one-time startup scan with a positive stale threshold could therefore skip a recently interrupted document and leave it stranded until another future restart.

For the current single-instance MVP, the correct behavior is:

```text
existing Processing + no result at startup => orphaned => recover immediately
```

If overlapping/multi-instance deployments are introduced later, recovery must move to explicit distributed ownership/leases or a durable broker rather than adding an arbitrary age threshold to this single-instance reconciler.

## 4. Recovery exclusions

Startup recovery does not automatically enqueue:

- `Processed` documents;
- `NeedsReview` documents;
- `Failed` documents;
- any document that already has an `ExtractionResult`.

`Failed` remains an explicit terminal state after bounded retry exhaustion. A caller can still request processing again through the existing `/process` endpoint when appropriate.

## 5. Restart E2E proof

New script:

```text
.github/scripts/verify_restart_recovery.sh
```

Automation E2E now performs a dedicated restart scenario after the existing document-processing scenarios.

The test:

1. starts a healthy API host;
2. captures the attempt count of an already completed supplier invoice;
3. stops the host;
4. creates two persisted documents with valid stored PDFs but does not enqueue them through the API:
   - one `Uploaded` document with zero attempts;
   - one `Processing` document with one previous attempt;
5. starts the API again;
6. waits for both documents to become `Processed`;
7. verifies the recovered `Uploaded` document has `ProcessingAttempts == 1`;
8. verifies the recovered orphaned `Processing` document has `ProcessingAttempts == 2`;
9. verifies both have extraction results;
10. verifies the previously completed invoice attempt count did not change.

This proves recovery originates from persisted PostgreSQL state during startup rather than from a `/process` call or an in-memory queue entry surviving the restart.

## 6. Hosted-service ordering

The registrations are intentionally ordered:

```text
IDocumentProcessingQueue singleton
DocumentProcessingRecoveryHostedService
DocumentProcessingBackgroundService
```

ASP.NET Core starts hosted services in registration order. Recovery completes its startup reconciliation/enqueue phase before the normal background consumer starts.

## 7. CI state

The CI path-filter cleanup from `v1.1.1.13` worked as intended.

Implementation changes triggered only:

```text
.NET CI #27
Automation E2E #103
```

No container deployment/OCR benchmark workflow was spent on this milestone.

## 8. Important limitation

This is not a durable distributed queue.

The current design is deliberately scoped to one active DocFlow application instance:

```text
PostgreSQL persisted document state
+ in-memory Channel<Guid>
+ startup reconciliation
+ bounded retry
```

This now survives ordinary single-instance host restarts for `Uploaded` and interrupted `Processing` work.

If the product later requires multiple simultaneous workers/instances, horizontal scaling, stronger delivery guarantees or distributed scheduling, introduce explicit queue ownership semantics (for example a broker or database lease/job table). Do not claim the current startup reconciler provides that behavior.

## 9. Extraction baseline

No extraction or OCR behavior changed.

Baseline remains:

```text
17/17 public documents passed
98/98 checked business fields matched
17/17 document types correct
17/17 validation statuses correct
```

## 10. Next step

Choose one narrow commercial product gap for `v1.1.1.15`.

Best current candidates:

1. **Retention/delete** — tenant-visible document deletion and stored-file/database lifecycle; the domain already carries `DeleteAt` but there is no complete customer lifecycle operation.
2. **Reviewer/audit identity** — individual attribution for human corrections rather than tenant/client-level identity only.
3. **Distributed processing ownership** — only when actual multi-instance deployment becomes a requirement.

Retention/delete is currently the smallest practical next milestone. Inspect current file-storage and cascade behavior before implementing it.
