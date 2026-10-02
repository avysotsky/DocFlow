# DocFlow — handoff v1.1.1.27 Completion Outbox

Status: **COMPLETED**  
Repository: `avysotsky/DocFlow`  
Branch: `DocFlow/v_1.1.1.27_CompletionOutbox`  
Base: `DocFlow/v_1.1.1.26_StorageKeyDeprecation`

## Purpose

Create a reliable database transaction boundary for future completion notifications before adding outbound HTTP delivery.

## Implementation

Implementation commit:

```text
3a56f0dad62bf29b3dd7a3ff4de098b1e23717fe
Persist terminal document completion events
```

New domain/persistence pieces:

```text
DocumentCompletionEvent
DocumentCompletionEventConfiguration
DocumentCompletionOutbox table
migration 20261002094000_AddDocumentCompletionOutbox
DbSet<DocumentCompletionEvent>
```

Persisted event snapshot:

```text
Id
DocumentId
CustomerId
Status
DocumentType
ProcessingAttempts
OccurredAt
```

## Transaction semantics

`Processed` and `NeedsReview`:

```text
create ExtractionResult
mark Document terminal
add DocumentCompletionEvent
SaveChanges once
```

`Failed` after bounded retries:

```text
mark Document Failed
add DocumentCompletionEvent
SaveChanges once
```

This removes the crash window that would exist if an HTTP notification were sent directly from the processing worker after status persistence.

## Duplicate guard

The database has a unique index on:

```text
DocumentId + Status + ProcessingAttempts
```

Repeated enqueue of an already completed document therefore does not create another event for the same terminal transition.

A later manual reprocessing cycle after a failure can still produce a distinct completion transition because the cumulative processing-attempt count changes.

## Delete/retention boundary

The outbox intentionally has **no foreign key cascade to Documents**.

A document may be explicitly deleted or removed by retention after completion, but the persisted completion event must remain available for future delivery.

## Validation

Authoritative validation:

```text
.NET CI #41 -> success (run 36991292679)
Automation E2E #122 -> success (run 36991292541)
```

Automation E2E proves:

- normal quotation -> exactly one `Processed` event with attempt count 1;
- invalid arithmetic -> exactly one `NeedsReview` event with attempt count 1;
- exhausted missing-file processing -> exactly one `Failed` event with attempt count 3;
- repeated enqueue of the already completed quotation does not duplicate its event;
- migration chain applies successfully;
- restart/review/delete/retention/idempotency regressions remain green.

## Explicit non-scope

This milestone does not send outbound HTTP and does not add:

- callback URLs in upload requests;
- webhook destinations;
- webhook secrets/signatures;
- delivery attempts/backoff;
- RabbitMQ/Kafka;
- distributed scheduling.

Those belong to the next milestone on top of this durable event source.
