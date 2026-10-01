# DocFlow — handoff v1.1.1.22 Idempotency Cleanup

Status: **ACTIVE**  
Repository: `avysotsky/DocFlow`  
Branch: `DocFlow/v_1.1.1.22_IdempotencyCleanup`  
Base: `DocFlow/v_1.1.1.21_IntakeIdempotency`

## Why this milestone exists

`v1.1.1.21` added logical expiry for persisted single-upload idempotency records. Expired keys can be reused correctly, but one-off expired rows that are never reused remain in `IntakeIdempotencyRecords`, so high-volume unique keys can grow the table indefinitely.

## Scope

1. Add a dedicated single-instance hosted cleanup service for expired `IntakeIdempotencyRecords`.
2. Reuse the existing `Intake:Idempotency` configuration section with a configurable cleanup interval and bounded cleanup batch size.
3. Delete only rows whose `ExpiresAt <= now`.
4. For every candidate, acquire the same PostgreSQL transaction advisory lock scope used by intake (`CustomerId + Key`) before deleting.
5. Re-check expiry after the lock is acquired so a key concurrently renewed by intake is not deleted.
6. Keep document retention and idempotency housekeeping separate.
7. Do not add a distributed scheduler, Redis, queue, or new database schema.
8. Extend Automation E2E to prove expired rows are removed, unexpired rows remain, bounded repeated sweeps work, and existing intake idempotency remains green.

## Configuration target

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

Cleanup is always available because persisted idempotency itself is optional per request; with no records the hourly query is effectively idle.

## Concurrency contract

Cleanup must not race an expired-key reuse into a `DbUpdateConcurrencyException` or delete a newly renewed row.

For each candidate:

```text
begin DB transaction
-> acquire pg_advisory_xact_lock(hash(customer + key))
-> DELETE WHERE CustomerId/Key match AND ExpiresAt <= cutoff
-> commit
```

The lock scope string and SQL semantics must match `DocumentIntakeService`.

## Acceptance

```text
expired records are physically removed
unexpired records are preserved
cleanup is bounded by configured batch size per sweep
multiple sweeps eventually drain more than one batch
normal Idempotency-Key replay/conflict/concurrency remains green
no document rows/files are touched
.NET CI + Automation E2E green
```
