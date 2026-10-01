# DocFlow — handoff v1.1.1.22 Idempotency Cleanup

Status: **COMPLETED**  
Repository: `avysotsky/DocFlow`  
Branch: `DocFlow/v_1.1.1.22_IdempotencyCleanup`  
Base: `DocFlow/v_1.1.1.21_IntakeIdempotency`

## 1. Milestone result

Expired `IntakeIdempotencyRecords` are now physically removed by a dedicated bounded single-instance hosted cleanup service.

Implementation commit:

```text
4a5d16cdd431fb6470df6ed2de9171b84aa876b7
Add bounded idempotency record cleanup
```

Final validation:

```text
.NET CI #37
run id: 36901767125
result: success

Automation E2E #113
run id: 36901767040
result: success
```

No database migration was required.

## 2. Runtime cleanup

New hosted service:

```text
IntakeIdempotencyCleanupHostedService
```

Default configuration:

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

Startup validation:

```text
RetentionHours: 1..720
CleanupIntervalSeconds: 1..86400
CleanupBatchSize: 1..5000
```

The service runs one sweep immediately after startup and then delays for the configured interval.

Each sweep selects at most `CleanupBatchSize` records where:

```text
ExpiresAt <= cutoff
```

Candidates are ordered by expiry, tenant and key for deterministic bounded work.

## 3. Concurrency safety

Cleanup coordinates with normal idempotent intake rather than deleting expired rows blindly.

For every selected candidate it opens a database transaction and acquires the same PostgreSQL transaction advisory lock scope used by `DocumentIntakeService`:

```text
{CustomerId:N}:{IdempotencyKey}
```

using:

```text
pg_advisory_xact_lock(hashtextextended(lockScope, 0))
```

Only after the lock is acquired does cleanup execute a conditional delete that re-checks:

```text
CustomerId == candidate.CustomerId
Key == candidate.Key
ExpiresAt <= original sweep cutoff
```

Therefore:

```text
cleanup wins lock first -> expired row is deleted; later intake inserts a fresh row
intake wins lock first and renews row -> cleanup re-check deletes 0 rows and skips it
```

This avoids deleting a newly renewed record and avoids an expired-key reuse racing into an EF concurrency failure.

## 4. Lifecycle boundary

Idempotency cleanup is intentionally separate from business-document retention.

It does not:

- delete `Documents`;
- delete source PDFs;
- use `IDocumentDeletionService`;
- alter document `DeleteAt`;
- introduce a foreign key from idempotency records to documents.

The idempotency table remains independent of the document lifecycle, preserving replay after document deletion until the key itself expires.

## 5. E2E coverage

Automation E2E #113 configures:

```text
CleanupIntervalSeconds = 1
CleanupBatchSize = 1
```

The test seeds:

```text
2 expired idempotency rows
1 unexpired idempotency row
```

With a batch size of one, multiple sweeps are required to drain both expired rows. The final assertion requires:

```text
expired rows remaining = 0
unexpired rows remaining = 1
```

The same E2E run then executes the existing single-upload idempotency tests, including replay, different-payload `409`, tenant isolation, rejected replay, concurrent same-key intake and replay after document deletion. Restart recovery regression also remained green.

## 6. Scope boundary

Still intentionally deferred:

- batch request idempotency;
- semantic/content deduplication;
- Redis/external lock infrastructure;
- distributed queue/leases/schedulers;
- per-tenant retention policy;
- named-human IAM;
- external metrics/tracing aggregation.

## 7. Recommended next milestone

Strong next candidate: `v1.1.1.23_BatchIdempotency`.

Do not simply reuse the single-upload response snapshot shape. Batch intake is partial-success: one request can contain accepted, rejected and failed files. First define a persisted request-level replay contract covering item order, per-item results, retryable infrastructure failures and whether a partially failed original batch is replayable or retryable.
