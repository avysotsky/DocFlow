# DocFlow — Next Chat Handoff After v1.1.1.28

Use this file as the starting state for the next DocFlow development chat.

## Repository state

Repository: `avysotsky/DocFlow`  
Completed branch: `DocFlow/v_1.1.1.28_WebhookDelivery`  
Previous branch: `DocFlow/v_1.1.1.27_CompletionOutbox`

Implementation:

```text
bf201a5be29a02d393a856137d5177b564452b01
Deliver completion outbox events to signed tenant webhooks
```

Validation:

```text
.NET CI #42 -> success (run 36996511036)
Automation E2E #123 -> success (run 36996511044)
```

Detailed handoff:

```text
docs/HANDOFF_v1.1.1.28_WebhookDelivery.md
```

## Current completion notification flow

```text
terminal document transition
-> same-transaction DocumentCompletionOutbox event
-> async webhook delivery worker
-> HMAC-signed JSON POST
-> 2xx => DeliveredAt
-> failure => persisted bounded exponential retry
-> max attempts => DeliveryAbandonedAt
```

Tenant destinations come only from trusted deployment configuration.

Production SSRF boundary includes HTTPS-only configuration, redirects/proxy disabled and runtime resolved-address validation in the actual connection callback.

## Recommended next milestone

Candidate: `v1.1.1.29_WebhookDeliveryRecovery`.

Current gap:

```text
event reaches DeliveryAbandonedAt
-> automatic retries stop correctly
-> there is no supported API to inspect/re-drive the tenant's failed delivery
-> recovery requires direct database changes
```

Inspect before implementing:

```text
src/DocFlow.Domain/Entities/DocumentCompletionEvent.cs
src/DocFlow.Api/Notifications/WebhookDeliveryHostedService.cs
src/DocFlow.Api/Authentication/ApiKeyAuthentication.cs
src/DocFlow.Api/Observability/OperationsMetricsController.cs
src/DocFlow.Api/Program.cs
.github/workflows/automation-e2e.yml
```

Preferred scope:

- provide tenant-scoped read-only delivery history/status for the authenticated `CustomerId`;
- expose event id, document id, terminal status, occurred time, attempt count, next-attempt time, delivered/abandoned timestamps and safe last error;
- never expose webhook URL or secret;
- provide an explicit tenant-scoped re-drive action for an abandoned event;
- re-drive must only reset delivery state for the same persisted event; do not create a second outbox event;
- cross-tenant event ids return 404;
- delivered events should not be re-driven accidentally;
- define whether non-abandoned pending events can be accelerated or only abandoned events can be re-driven (prefer abandoned-only for the first milestone);
- keep the current configured destination/secret authoritative at re-drive time;
- add E2E proving abandoned -> re-drive -> successful delivery without duplicate outbox row.

Do not broaden this into a generic admin console or webhook-management API.

## Later candidates

- outbox delivery-history retention/cleanup policy;
- named-human reviewer IAM;
- external/persistent telemetry;
- distributed queue/webhook ownership when multi-instance deployment becomes real;
- explicit versioned removal of legacy `storageKey`.

## CI discipline

Continue sparse CI:

- docs/intermediate work -> `[skip ci]`;
- coherent C# changes -> .NET CI + Automation E2E;
- deployment/OCR/public benchmark workflows only when their contracts change.
