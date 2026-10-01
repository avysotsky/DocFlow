# DocFlow — handoff v1.1.1.23 Batch Idempotency

Status: **ACTIVE**  
Repository: `avysotsky/DocFlow`  
Branch: `DocFlow/v_1.1.1.23_BatchIdempotency`  
Base: `DocFlow/v_1.1.1.22_IdempotencyCleanup`

## Why this milestone exists

`POST /api/documents/batch` is bounded and partial-success, but a client retry after a timeout can create duplicate documents for every previously accepted item. Single-upload idempotency already solves this for `POST /api/documents`; batch needs a separate contract because one request can contain accepted, rejected and retryable failed items.

## Contract selected after inspection

Idempotency is request-level and optional through the existing `Idempotency-Key` header.

The ordered batch request has one persisted manifest:

```text
(CustomerId, external key)
+ ordered request fingerprint
+ GenerationId
+ optional completed response snapshot
+ CreatedAt / ExpiresAt
```

Each batch item uses the already-proven single-upload idempotency engine under a deterministic internal key:

```text
docflow-internal:batch:<GenerationId>:<item-index>
```

External callers may not use the reserved `docflow-internal:` prefix.

## Why item-level internal keys are used

This makes each item a durable checkpoint without duplicating document/storage persistence logic:

```text
Accepted item -> persisted/replayed, no duplicate document on retry
Rejected item -> persisted/replayed
Failed infrastructure item -> no completed idempotency record, so retry executes it again
```

A batch manifest is only marked complete when no item outcome is `Failed`. Until then, a retry with the same external key and identical ordered payload reuses the same GenerationId and therefore resumes through the same item keys.

## Fingerprint

The batch fingerprint is SHA-256 over a version marker, file count and each file in request order, including filename, content type, length and full bytes. Reordering files changes the fingerprint.

## Replay/conflict semantics

```text
same tenant + key + completed same batch -> exact response replay + Idempotency-Replayed: true
same tenant + key + incomplete same batch -> resume item checkpoints
same tenant + key + different ordered batch -> 409 Conflict
same key in another tenant -> independent namespace
no Idempotency-Key -> existing batch behavior unchanged
```

Concurrent identical requests share the same manifest generation. Internal per-item PostgreSQL advisory locks serialize each item, preventing duplicate durable documents.

## Persistence

Add a dedicated `BatchIntakeIdempotencyRecord`; do not overload the single-document record. It has no FK to `Documents`.

Expired batch manifests must participate in the existing bounded idempotency cleanup. Existing internal item records are already cleaned by the single-record cleanup path.

## Non-goals

Do not add semantic content deduplication, Redis, external locks, a distributed queue, ZIP/email ingestion, or multi-instance scheduling.

## Acceptance

```text
no key -> existing batch behavior
mixed Accepted + Rejected batch completes and can replay equivalent response
replay does not create another accepted document
ordered payload change under same key -> 409
same key across tenants -> independent
concurrent same-key identical batches -> one durable accepted document per accepted item
incomplete manifest can resume through durable item checkpoints
batch manifest expiry/cleanup remains bounded
single-upload idempotency remains green
.NET CI + Automation E2E green
```
