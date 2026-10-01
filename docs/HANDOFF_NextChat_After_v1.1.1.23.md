# DocFlow — Next Chat Handoff After v1.1.1.23

Use this file as the starting state for the next DocFlow development chat.

## Repository state

Repository: `avysotsky/DocFlow`  
Completed branch: `DocFlow/v_1.1.1.23_BatchIdempotency`  
Previous branch: `DocFlow/v_1.1.1.22_IdempotencyCleanup`

Authoritative implementation commit:

```text
cdd41a13f862b586be4024ac4c8f7b078061cda7
Add persisted batch intake idempotency
```

Final validation:

```text
.NET CI #38 -> success (run 36906324232)
Automation E2E #114 -> success (run 36906324346)
```

Detailed handoff:

```text
docs/HANDOFF_v1.1.1.23_BatchIdempotency.md
```

## Current product state

DocFlow now supports:

```text
API-key authenticated tenant/client
  -> single PDF upload with optional persisted Idempotency-Key
  -> bounded multi-PDF partial-success batch intake with request-level Idempotency-Key
  -> physical cleanup of expired single and batch idempotency state
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

Production container deployment, health/readiness checks and opt-in migrations remain in place.

Extraction/OCR baseline remains unchanged:

```text
17/17 public documents passed
98/98 checked business fields matched
17/17 document types correct
17/17 validation statuses correct
69 Python regression tests
```

No extraction/OCR behavior changed in `v1.1.1.23`.

## Batch idempotency state

Endpoint:

```text
POST /api/documents/batch
Idempotency-Key: <1..128 chars>   # optional
```

No key preserves the old batch behavior.

Caller-supplied keys using this prefix are rejected:

```text
docflow-internal:
```

That namespace is reserved for deterministic internal item checkpoints.

### Whole-request identity

Batch fingerprint is ordered and includes:

```text
version marker
file count
for each item in order:
  item index
  filename
  content type
  length
  full bytes
```

Reordering items therefore changes the request fingerprint.

### Persisted manifest

Table:

```text
BatchIntakeIdempotencyRecords
PK: (CustomerId, Key)
index: ExpiresAt
```

Fields:

```text
RequestFingerprint
GenerationId
ResponseJson nullable
CreatedAt
ExpiresAt
```

No FK to Documents.

### Durable item checkpoints

For an idempotent batch, each item uses the existing single-intake idempotency engine under:

```text
docflow-internal:batch:<GenerationId>:<index>
```

Behavior:

```text
Accepted item -> durable checkpoint/document id
Rejected item -> durable deterministic checkpoint
Failed infrastructure item -> no completed checkpoint, retryable
```

The batch manifest completes only when `FailedCount == 0`.

Retry of an incomplete identical batch reuses the same GenerationId and item keys, so completed items replay while unfinished items can execute again.

### Replay/conflict

```text
completed same tenant/key/request -> stored response replay + Idempotency-Replayed: true
incomplete same tenant/key/request -> resume same generation
same tenant/key/different ordered request -> 409
same key/different tenant -> independent namespace
```

Manifest-level and item-level PostgreSQL advisory locks protect concurrent same-key correctness.

Automation E2E #114 proved completed replay, order conflict, cross-tenant namespace, reserved-prefix rejection and concurrent identical batch deduplication. It did not inject a synthetic storage/database failure mid-batch; the incomplete-resume path is implemented by checkpoint semantics but has not had explicit infrastructure fault injection yet.

## Idempotency cleanup

`IntakeIdempotencyCleanupHostedService` cleans both:

```text
IntakeIdempotencyRecords
BatchIntakeIdempotencyRecords
```

Cleanup is bounded per record type by `Intake:Idempotency:CleanupBatchSize` and re-checks expiry under the matching advisory lock.

Default configuration remains:

```json
{
  "Intake": {
    "Idempotency": {
      "RetentionHours": 24,
      "CleanupIntervalSeconds": 3600,
      "CleanupBatchSize": 500
    }
  }
}
```

## Reliability boundary

DocFlow remains intentionally single-instance operationally except for PostgreSQL transaction-level correctness mechanisms:

```text
PostgreSQL persisted state
+ startup reconciliation
+ in-memory Channel<Guid>
+ bounded retries
+ periodic document retention
+ periodic idempotency cleanup
+ row locking for document delete
+ tenant/key advisory locks for single/batch intake
+ process-local metrics
```

Do not add RabbitMQ/Kafka/Redis/distributed schedulers merely for architectural appearance. Add distributed ownership only when multiple active instances become a real requirement.

## CI discipline

Continue sparse CI:

- docs/intermediate work -> `[skip ci]`;
- coherent API/Application/Domain/Infrastructure changes -> `.NET CI` + Automation E2E;
- Deployment Smoke only for Docker/compose/health/deployment contract changes;
- Scanned OCR E2E only for OCR/extraction-runner changes;
- Public Reference Benchmark only for extraction-rule changes.

## Recommended next milestone

Candidate: `v1.1.1.24_PerTenantRetentionPolicy`.

Inspect before implementing:

```text
src/DocFlow.Api/Authentication/ApiKeyAuthentication.cs
src/DocFlow.Api/Retention/DocumentRetentionOptions.cs
src/DocFlow.Api/Retention/DocumentRetentionHostedService.cs
src/DocFlow.Api/Documents/DocumentIntakeService.cs
src/DocFlow.Api/appsettings.json
.github/scripts/verify_restart_recovery.sh
.github/workflows/automation-e2e.yml
```

Current retention is deployment-wide:

```text
Retention.Enabled
Retention.DefaultRetentionDays
```

The commercial multi-tenant question is whether a customer can have a different retention period or automatic retention disabled while another customer retains the deployment default.

Preferred inspection direction:

```text
trusted CustomerId -> optional retention policy override
fallback to existing global default
new uploads calculate DeleteAt from trusted tenant policy
request payload never controls authoritative retention
terminal-only cleanup query stays unchanged
existing documents keep their persisted DeleteAt
```

Do not introduce a general tenant-management subsystem merely to solve this policy override. Prefer the smallest configuration/persistence representation that is operationally honest for the current API-key tenant model.

Other later candidates: API versioning/deprecation for `StorageKey`, explicit fault-injection coverage for incomplete batch resume, named-human IAM if actually required, and external telemetry only when deployment requirements justify it.
