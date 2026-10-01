# DocFlow — Next Chat Handoff After v1.1.1.24

Use this file as the starting state for the next DocFlow development chat.

## Repository state

Repository: `avysotsky/DocFlow`  
Completed branch: `DocFlow/v_1.1.1.24_PerTenantRetentionPolicy`  
Previous branch: `DocFlow/v_1.1.1.23_BatchIdempotency`

Authoritative implementation commit:

```text
13d9b60ffa357e844b46aefbebe99ee299a4d3e9
Add per-tenant retention policy overrides
```

Final validation:

```text
.NET CI #39 -> success (run 36908516866)
Automation E2E #115 -> success (run 36908516614)
```

Detailed handoff:

```text
docs/HANDOFF_v1.1.1.24_PerTenantRetentionPolicy.md
```

## Current product state

DocFlow now supports:

```text
API-key authenticated tenant/client
  -> single PDF upload with optional persisted Idempotency-Key
  -> bounded multi-PDF partial-success batch intake with request-level Idempotency-Key
  -> physical cleanup of expired single and batch idempotency state
  -> trusted per-tenant retention override with deployment fallback
  -> shared validation/storage/persistence intake service
  -> PostgreSQL-backed startup recovery
  -> in-memory single-reader processing queue
  -> bounded technical retries + persisted diagnostics
  -> digital PDF / conditional Tesseract OCR
  -> invoice/quotation detection and deterministic extraction
  -> arithmetic/business validation
  -> PostgreSQL persistence
  -> tenant-scoped inbox
  -> original PDF streaming
  -> review/correction + authenticated API-client attribution
  -> CSV/XLSX export
  -> explicit terminal deletion
  -> optional document retention cleanup
  -> protected process-local operational metrics
```

Extraction/OCR baseline remains unchanged:

```text
17/17 public documents passed
98/98 checked business fields matched
17/17 document types correct
17/17 validation statuses correct
69 Python regression tests
```

No extraction/OCR behavior changed in `v1.1.1.24`.

## Per-tenant retention state

Configuration:

```json
{
  "Retention": {
    "Enabled": false,
    "DefaultRetentionDays": 30,
    "SweepIntervalSeconds": 3600,
    "BatchSize": 100,
    "TenantOverrides": [
      {
        "CustomerId": "11111111-1111-1111-1111-111111111111",
        "Enabled": true,
        "RetentionDays": 90
      }
    ]
  }
}
```

Effective policy is resolved from trusted `CustomerId` only:

```text
Enabled = tenant.Enabled ?? global.Enabled
RetentionDays = tenant.RetentionDays ?? global.DefaultRetentionDays
```

New accepted documents persist `DeleteAt` from the effective policy. Existing documents keep their existing `DeleteAt`; configuration changes do not rewrite lifecycle history.

The retention sweep starts when the global policy is enabled or any tenant explicitly enables retention, but it still deletes only expired terminal documents with persisted `DeleteAt`.

## Batch idempotency boundary

Batch idempotency uses a persisted manifest plus deterministic internal item keys:

```text
docflow-internal:batch:<GenerationId>:<index>
```

Accepted/rejected items are durable checkpoints. Retryable infrastructure failures do not produce completed item records, so an incomplete batch is designed to resume without duplicating prior accepted items.

Automation E2E #114 covered completed replay, ordering conflict, tenant isolation, reserved-prefix rejection and concurrency. It did **not** inject a real storage/database failure into the middle of an idempotent batch.

## Recommended next milestone

Candidate: `v1.1.1.25_BatchResumeFaultInjection`.

This is primarily a reliability-proof milestone, not a feature expansion.

Inspect before implementing:

```text
src/DocFlow.Api/Documents/DocumentBatchIntakeService.cs
src/DocFlow.Api/Documents/DocumentIntakeService.cs
src/DocFlow.Infrastructure/Storage/LocalFileStorage.cs
src/DocFlow.Application/Abstractions/IFileStorage.cs
.github/scripts/verify_batch_idempotency.py
.github/workflows/automation-e2e.yml
```

Goal:

```text
force one deterministic infrastructure failure on a middle batch item
verify earlier accepted/rejected checkpoints survive
retry same external Idempotency-Key and identical ordered payload
verify completed items replay with original DocumentIds
verify failed item is retried and completes
verify final batch manifest becomes complete
verify subsequent retry is an exact completed replay
verify no duplicate accepted Documents were created
```

Preferred direction:

- introduce the smallest explicitly test-only/fault-injection seam that does not weaken production behavior;
- do not add random failures or environment-dependent filesystem tricks;
- keep production default with fault injection disabled;
- do not create a second storage/intake implementation solely for testing;
- use the existing Automation E2E workflow rather than adding another workflow.

Before adding code, inspect whether the failure can be injected cleanly through the existing `IFileStorage` abstraction or a narrow intake test option. Avoid contaminating normal production configuration with a broad chaos-testing subsystem.

## Other later candidates

- API versioning/deprecation for public `StorageKey`;
- named-human reviewer IAM only if actual product requirements demand it;
- persistent/external operational telemetry when deployment requirements justify it;
- distributed processing ownership only when multiple active API instances become a real requirement.

## CI discipline

Continue sparse CI:

- docs/intermediate work -> `[skip ci]`;
- coherent API/Application/Domain/Infrastructure changes -> `.NET CI` + Automation E2E;
- Deployment Smoke only for Docker/compose/health/deployment contract changes;
- Scanned OCR E2E only for OCR/extraction-runner changes;
- Public Reference Benchmark only for extraction-rule changes.
