# DocFlow — handoff v1.1.1.28 Webhook Delivery

Status: **ACTIVE**  
Repository: `avysotsky/DocFlow`  
Branch: `DocFlow/v_1.1.1.28_WebhookDelivery`  
Base: `DocFlow/v_1.1.1.27_CompletionOutbox`

## Goal

Deliver persisted `DocumentCompletionOutbox` events to trusted tenant-configured HTTP webhooks with explicit security and bounded at-least-once retry semantics.

## Selected delivery contract

Webhook destinations are deployment configuration keyed by trusted `CustomerId`; upload requests never supply callback URLs.

Configuration shape:

```text
Notifications:Webhooks
  PollIntervalSeconds
  RequestTimeoutSeconds
  MaxAttempts
  BaseRetryDelaySeconds
  Tenants[]
    CustomerId
    Url
    Secret
```

Tenants without webhook configuration retain their outbox rows and are not selected for delivery.

## Delivery state

Extend `DocumentCompletionOutbox` with persisted state:

```text
DeliveryAttempts
NextDeliveryAttemptAt
LastDeliveryAttemptAt
LastDeliveryError
DeliveredAt
DeliveryAbandonedAt
```

Successful HTTP 2xx marks `DeliveredAt`.

Retryable failure increments `DeliveryAttempts`, stores a bounded safe summary and schedules exponential backoff.

After `MaxAttempts`, mark `DeliveryAbandonedAt` and stop automatic attempts.

A process crash after receiver success but before `DeliveredAt` persistence can cause a duplicate delivery; the contract is therefore intentionally **at least once**.

## Payload and signature

Payload is deterministic JSON containing:

```text
eventId
eventType = document.completed
occurredAt
documentId
customerId
status
documentType
processingAttempts
```

Headers:

```text
X-DocFlow-Event-Id: <event id>
X-DocFlow-Signature: sha256=<lowercase hex HMAC-SHA256 over exact request body>
```

The immutable event id allows receiver-side deduplication.

## SSRF/security

Outside Development:

- destination must be absolute HTTPS;
- redirects disabled;
- runtime DNS resolution is validated before connect;
- loopback, private, link-local, multicast, unspecified and other non-public destination ranges are rejected;
- webhook secret is required;
- no response body is consumed;
- request timeout is bounded.

Development may opt in to localhost/private destinations only for deterministic E2E.

## Operational boundary

- delivery is asynchronous from processing;
- no RabbitMQ/Kafka;
- current hosted worker remains explicitly single-instance;
- no arbitrary per-request callback URLs;
- no deletion of outbox rows in this milestone.

## Validation

Automation E2E should start a local test receiver and prove:

- Processed/NeedsReview/Failed events are delivered;
- payload event id/status/tenant/document fields are correct;
- HMAC signature verifies over exact payload bytes;
- 2xx marks delivered with attempt count 1;
- a deterministic receiver 500 is retried and eventually succeeds;
- retry count/backoff state persists;
- repeated processing does not create/deliver duplicate completion events;
- tenant without webhook config is not delivered;
- existing restart/review/delete/retention/idempotency regression remains green.

Expected CI: .NET CI + Automation E2E only.
