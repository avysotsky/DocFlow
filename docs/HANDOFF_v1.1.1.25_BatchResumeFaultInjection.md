# DocFlow — handoff v1.1.1.25 Batch Resume Fault Injection

Status: **COMPLETED**  
Repository: `avysotsky/DocFlow`  
Branch: `DocFlow/v_1.1.1.25_BatchResumeFaultInjection`  
Base: `DocFlow/v_1.1.1.24_PerTenantRetentionPolicy`

## Purpose

This milestone did not change production/runtime behavior. It closed the remaining evidence gap in persisted batch idempotency by proving incomplete-batch resume under a real deterministic database failure.

## Authoritative test state

Final validating commit:

```text
3bb4c7b5a6d06f256957e6986df6b9c49260614e
Match persisted batch checkpoint key format
```

Authoritative validation:

```text
Automation E2E #119
run 36987322882
success
```

No .NET CI run is required for the authoritative state because this milestone changes only the E2E helper and documentation; no `.cs`, `.csproj` or `.sln` file changed.

## Fault strategy

The existing Automation E2E PostgreSQL service temporarily installs a `BEFORE INSERT` trigger on `Documents`.

The trigger raises an exception only for one unique middle-item filename. It is removed in a `finally` cleanup path before the resume request.

No production fault-injection flag, random failure, alternative storage implementation or chaos subsystem was added.

## Proven scenario

The idempotent batch contains:

```text
item 0 -> valid PDF -> Accepted
item 1 -> invalid non-PDF -> Rejected
item 2 -> valid PDF -> injected PostgreSQL INSERT failure -> Failed
item 3 -> valid PDF -> Accepted
```

The first request proves:

```text
AcceptedCount = 2
RejectedCount = 1
FailedCount = 1
batch manifest ResponseJson is NULL
three durable item checkpoints exist
failed item index 2 has no completed checkpoint
```

After removing the trigger, the exact same external `Idempotency-Key` and ordered payload are submitted again.

The resume proves:

```text
item 0 replays with its original DocumentId
item 1 replays its deterministic rejection
item 2 executes again and becomes Accepted
item 3 replays with its original DocumentId
checkpoint count becomes 4
batch manifest becomes complete
only 3 accepted Documents exist for the 3 valid filenames
```

A third identical request proves:

```text
exact stored batch response replay
Idempotency-Replayed: true
no duplicate accepted Documents
```

All accepted documents are allowed to reach terminal `Processed` status before the helper returns, so the following restart-recovery regression is not polluted by test-created queued work.

## Regression coverage

Automation E2E #119 also completed the existing restart/review/delete/retention regression after the new fault scenario.

Extraction/OCR behavior was not changed and no extraction-specific workflow was triggered.

## Diagnostic runs

Two earlier test iterations were intentionally not accepted as validation:

```text
Automation E2E #116 -> failure
  test SQL function delimiter was malformed

Automation E2E #118 -> failure
  checkpoint assertion used PostgreSQL UUID text with hyphens,
  while internal item keys use Guid:N without hyphens
```

These were defects in the new E2E test itself, not failures of the production batch-resume implementation. The final helper normalizes the GenerationId to the actual internal key format and passes in #119.
