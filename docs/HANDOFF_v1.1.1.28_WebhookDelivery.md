# DocFlow — handoff v1.1.1.28 Webhook Delivery

Status: **COMPLETED**  
Repository: `avysotsky/DocFlow`  
Branch: `DocFlow/v_1.1.1.28_WebhookDelivery`  
Base: `DocFlow/v_1.1.1.27_CompletionOutbox`

## Implementation

Implementation commit:

```text
bf201a5be29a02d393a856137d5177b564452b01
Deliver completion outbox events to signed tenant webhooks
```

## Delivery model

Webhook targets are configured per trusted `CustomerId` under:

```text
Notifications:Webhooks
```

No upload/request API accepts callback URLs.

Tenants without a configured webhook are excluded from the delivery query and their completion events remain pending without consuming delivery attempts.

## Persisted delivery state

`DocumentCompletionOutbox` now stores:

```text
DeliveryAttempts
NextDeliveryAttemptAt
LastDeliveryAttemptAt
LastDeliveryError
DeliveredAt
DeliveryAbandonedAt
```

Migration:

```text
20261002103000_AddWebhookDeliveryState
```

Existing outbox rows are initialized with `NextDeliveryAttemptAt = OccurredAt`.

## Retry semantics

Default production-oriented settings:

```text
PollIntervalSeconds = 5
RequestTimeoutSeconds = 10
MaxAttempts = 5
BaseRetryDelaySeconds = 30
MaxRetryDelaySeconds = 3600
BatchSize = 50
```

Each failed delivery stores a bounded safe error summary and schedules exponential backoff capped at `MaxRetryDelaySeconds`.

After `MaxAttempts`, `DeliveryAbandonedAt` is set and automatic retries stop.

Successful 2xx delivery sets `DeliveredAt`.

The contract is intentionally **at least once**. A process crash after remote success but before database persistence can cause a duplicate, so the immutable event id is part of the receiver contract.

## Payload and signing

Payload:

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
X-DocFlow-Event-Id
X-DocFlow-Signature: sha256=<lowercase HMAC-SHA256>
```

The HMAC covers the exact UTF-8 request body bytes.

## SSRF/network protection

Outside Development:

- webhook URL must be absolute HTTPS;
- development HTTP/private-network escape hatches must be disabled;
- IP-literal private/non-public destinations fail startup validation;
- DNS names are resolved in `SocketsHttpHandler.ConnectCallback`;
- the actual connection is opened only to an allowed resolved address;
- loopback, private, link-local, multicast and documented/reserved test ranges are blocked;
- redirects, cookies and proxy use are disabled;
- request timeout is bounded;
- response body is not consumed.

Development may explicitly enable HTTP/private addresses only for deterministic local tests.

## E2E proof

A local test receiver verifies HMAC over exact request bytes and records every attempt.

Automation E2E proves:

- normal `Processed` event -> 204 on first attempt -> `DeliveryAttempts=1`, delivered;
- `NeedsReview` event -> deterministic 500 then 204 -> `DeliveryAttempts=2`, delivered;
- previous safe HTTP 500 error remains persisted in `LastDeliveryError`;
- synthetic permanent-failure event -> three HTTP 500 responses -> abandoned at configured max attempts;
- tenant with no webhook configuration -> zero attempts and no receiver traffic;
- event id header matches payload event id;
- all delivered requests have valid HMAC signatures;
- existing intake/idempotency/review/restart/delete/retention regressions remain green.

## Validation

```text
.NET CI #42 -> success (run 36996511036)
Automation E2E #123 -> success (run 36996511044)
```

No deployment, OCR or public-reference workflow was triggered.

## Current boundary

The webhook delivery worker follows the project's current single-instance operational model.

It is not safe to claim distributed multi-instance delivery ownership yet.

Abandoned events currently require direct database intervention to re-drive; that is the recommended next operational gap.
