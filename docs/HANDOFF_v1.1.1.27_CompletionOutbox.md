# DocFlow — handoff v1.1.1.27 Completion Outbox

Status: **ACTIVE**  
Repository: `avysotsky/DocFlow`  
Branch: `DocFlow/v_1.1.1.27_CompletionOutbox`  
Base: `DocFlow/v_1.1.1.26_StorageKeyDeprecation`

## Goal

Close the reliability gap before HTTP completion webhooks by persisting terminal document-completion events transactionally with the document status change.

This milestone does **not** send outbound HTTP yet.

## Why split the milestone

Sending a webhook directly from the processing worker would create an unsafe crash window:

```text
persist terminal status
-> process crashes
-> webhook never sent
```

Reversing the order creates the opposite risk:

```text
send webhook
-> persistence fails/retries
-> duplicate or inconsistent notification
```

Therefore the first reliable boundary is a persisted outbox/event row written in the same EF Core `SaveChanges` as the terminal state transition.

## Event-producing transitions

Create one persisted completion event when a document reaches:

```text
Processed
NeedsReview
Failed
```

- `Processed` / `NeedsReview`: event is inserted in the same SaveChanges that persists the ExtractionResult and terminal document status.
- `Failed`: event is inserted in the same SaveChanges that persists the final Failed status after bounded retries are exhausted.

## Event snapshot

Persist enough information for later delivery without needing the Document row to still exist:

```text
Id
DocumentId
CustomerId
Status
DocumentType
ProcessingAttempts
OccurredAt
```

Do not add a cascade FK to `Documents`. Explicit delete/retention must not erase an undelivered completion fact.

Use a uniqueness guard for the terminal transition identity so retry/repeated enqueue does not create duplicate outbox events for the same completion transition.

## Scope boundary

Do not add:

- request-supplied callback URLs;
- outbound HTTP delivery;
- arbitrary webhook destinations;
- signing secrets;
- RabbitMQ/Kafka;
- distributed scheduling.

Those belong to the next milestone after the durable event boundary is proven.

## Validation

Extend Automation E2E / PostgreSQL assertions to prove:

- one Processed completion event for a normally processed document;
- one NeedsReview event for invalid arithmetic;
- one Failed event after exhausted technical retries;
- repeated enqueue of an already completed document does not duplicate its event;
- existing restart/review/delete/retention/idempotency regressions remain green.

Expected CI: .NET CI + Automation E2E only.
