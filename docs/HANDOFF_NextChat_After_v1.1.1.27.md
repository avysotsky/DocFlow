# DocFlow — Next Chat Handoff After v1.1.1.27

Use this file as the starting state for the next DocFlow development chat.

## Repository state

Repository: `avysotsky/DocFlow`  
Completed branch: `DocFlow/v_1.1.1.27_CompletionOutbox`  
Previous branch: `DocFlow/v_1.1.1.26_StorageKeyDeprecation`

Implementation:

```text
3a56f0dad62bf29b3dd7a3ff4de098b1e23717fe
Persist terminal document completion events
```

Validation:

```text
.NET CI #41 -> success (run 36991292679)
Automation E2E #122 -> success (run 36991292541)
```

Detailed handoff:

```text
docs/HANDOFF_v1.1.1.27_CompletionOutbox.md
```

## Current reliable completion boundary

Terminal processing transitions now atomically persist an outbox event:

```text
Processed / NeedsReview
  -> ExtractionResult + Document status + DocumentCompletionEvent
  -> one SaveChanges

Failed after exhausted retries
  -> Document Failed + DocumentCompletionEvent
  -> one SaveChanges
```

Outbox rows survive document deletion/retention because there is no cascade FK to `Documents`.

Duplicate transition guard:

```text
unique(DocumentId, Status, ProcessingAttempts)
```

## Recommended next milestone

Candidate: `v1.1.1.28_WebhookDelivery`.

Before implementing, inspect:

```text
src/DocFlow.Domain/Entities/DocumentCompletionEvent.cs
src/DocFlow.Infrastructure/Persistence/Configurations/DocumentCompletionEventConfiguration.cs
src/DocFlow.Api/Authentication/ApiKeyAuthentication.cs
src/DocFlow.Api/Program.cs
src/DocFlow.Api/appsettings.json
.github/workflows/automation-e2e.yml
```

Preferred narrow contract:

- webhook destinations are configured per trusted tenant/customer, never supplied on individual upload requests;
- configuration should be opt-in and allow tenants without webhooks;
- reject unsafe destination forms; explicitly address SSRF before allowing arbitrary external URLs;
- use HTTPS outside Development;
- sign each request with an HMAC secret unique to the configured destination/tenant;
- include an immutable event id so receivers can deduplicate at-least-once delivery;
- delivery must happen from the persisted outbox asynchronously, not inline with document processing;
- persist delivery attempt count, next-attempt time, last safe error summary and delivered timestamp;
- use bounded retry/backoff;
- do not delete an outbox row before successful delivery;
- do not add RabbitMQ/Kafka solely for webhook delivery;
- define what happens when a tenant has no webhook configuration before starting the worker.

A practical implementation may need to add delivery-state columns to `DocumentCompletionOutbox` and a single-instance hosted delivery service. Keep the existing single-instance boundary explicit.

## Security items to settle before coding

- URL allow/deny rules and SSRF protection;
- HTTPS requirement outside Development;
- redirect behavior (prefer disabled);
- request timeout and response-size limits;
- HMAC canonical payload/header format;
- secret handling and startup validation.

## Later candidates

- named-human reviewer IAM only when needed;
- external/persistent telemetry;
- distributed processing/webhook ownership when multiple active instances become a deployment requirement;
- explicit versioned removal of legacy `storageKey`.

## CI discipline

Continue sparse CI:

- docs/intermediate work -> `[skip ci]`;
- coherent C# changes -> .NET CI + Automation E2E;
- Deployment Smoke only for Docker/compose/health/deployment-contract changes;
- OCR/Public benchmark workflows only for extraction-related changes.
