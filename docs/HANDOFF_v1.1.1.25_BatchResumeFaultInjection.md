# DocFlow — handoff v1.1.1.25 Batch Resume Fault Injection

Status: **ACTIVE**  
Repository: `avysotsky/DocFlow`  
Branch: `DocFlow/v_1.1.1.25_BatchResumeFaultInjection`  
Base: `DocFlow/v_1.1.1.24_PerTenantRetentionPolicy`

## Goal

Prove the existing idempotent batch resume contract under a real deterministic mid-batch infrastructure failure, without adding production fault-injection behavior.

## Selected test strategy

Use the existing Automation E2E PostgreSQL service to install a temporary `BEFORE INSERT` trigger on `Documents`.

The trigger raises an exception only when `OriginalFileName` matches one unique middle-item filename in the test batch.

Test batch shape:

```text
item 0 -> valid PDF -> Accepted
item 1 -> invalid non-PDF -> Rejected
item 2 -> valid PDF -> injected PostgreSQL INSERT failure -> Failed
item 3 -> valid PDF -> Accepted
```

Expected first request:

```text
AcceptedCount = 2
RejectedCount = 1
FailedCount = 1
batch manifest remains incomplete
durable item checkpoints exist for 0, 1 and 3
checkpoint for failed item 2 does not exist
```

Then the test removes the PostgreSQL trigger and repeats the exact same ordered batch with the same external `Idempotency-Key`.

Expected resume:

```text
items 0, 1 and 3 reuse their durable checkpoints
item 2 executes again and becomes Accepted
original accepted DocumentIds are preserved
no duplicate accepted Documents are created
batch manifest becomes complete
```

A third identical request must be an exact completed replay with:

```text
Idempotency-Replayed: true
same response snapshot
```

## Safety

- no production configuration flag;
- no random failure;
- no filesystem-permission trick;
- no second storage/intake implementation;
- trigger is unique to the test filename and removed in a `finally` cleanup path;
- existing Automation E2E workflow is reused;
- no extraction/OCR behavior changes.

## CI discipline

This milestone is test-only. Updating the existing `.github/scripts/verify_batch_idempotency.py` should trigger Automation E2E only; do not force an unnecessary .NET CI run when product code has not changed.
