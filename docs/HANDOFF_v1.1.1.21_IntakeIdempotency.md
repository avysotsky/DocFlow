# DocFlow — handoff v1.1.1.21 Intake Idempotency

Status: **ACTIVE**  
Repository: `avysotsky/DocFlow`  
Branch: `DocFlow/v_1.1.1.21_IntakeIdempotency`  
Base: `DocFlow/v_1.1.1.20_BatchIntake`

## Why this milestone exists

A client retry after an HTTP timeout can currently create another durable document and stored PDF even when the first request actually committed. This becomes more important after batch intake, but this milestone deliberately starts with the single-document endpoint so the persisted semantics remain small and deterministic.

## Scope

1. Add optional `Idempotency-Key` support to `POST /api/documents` only.
2. Scope keys by authenticated tenant/customer.
3. Compute a request fingerprint from file bytes plus upload metadata; this is request identity, not semantic file deduplication.
4. Persist idempotency outcome independently of the document lifecycle so later delete/retention does not make an old key immediately reusable.
5. Serialize concurrent same-tenant/same-key requests through a PostgreSQL transaction advisory lock and a database uniqueness constraint.
6. Same key + same fingerprint -> replay the original accepted/rejected result without creating another storage object/document.
7. Same key + different fingerprint -> `409 Conflict`.
8. Storage/database infrastructure failures remain retryable and do not become successful idempotency records.
9. Idempotency records expire after a configurable bounded window; default 24 hours. An expired key can be reused and its row replaced in-place.
10. Batch idempotency is explicitly deferred.

## API contract

```text
POST /api/documents
Idempotency-Key: <1..128 chars>
```

Header is optional. Without it, existing upload behavior is unchanged.

Replay responses retain the original HTTP semantics and include:

```text
Idempotency-Replayed: true
```

Different payload reuse returns `409`.

## Configuration

```json
{
  "Intake": {
    "Idempotency": {
      "RetentionHours": 24
    }
  }
}
```

## Non-goals

Do not add content-hash semantic deduplication, batch replay, Redis/distributed lock infrastructure, human IAM, or a new queue.

## Acceptance

```text
no header -> existing single upload behavior
same tenant/key/same request -> same response/document id, no duplicate document
same tenant/key/different request -> 409
same key in another tenant -> independent namespace
concurrent same tenant/key -> one durable intake
replay remains available after original document lifecycle changes until key expiry
batch endpoint unchanged
.NET CI + Automation E2E green
```
