# DocFlow — handoff v1.1.1.19 Operational Metrics

Status: **ACTIVE**  
Repository: `avysotsky/DocFlow`  
Branch: `DocFlow/v_1.1.1.19_OperationalMetrics`  
Base: `DocFlow/v_1.1.1.18_ReviewAuditIdentity`

## Why this milestone exists

DocFlow has health probes and structured logging, but operators cannot see process-local queue pressure or cumulative processing/review/retention outcomes without reading logs and querying individual documents.

Global operational metrics are not tenant data and must not be exposed through normal customer API-key authorization.

## Scope

Keep `v1.1.1.19` narrow and low-cardinality:

1. Add a process-local thread-safe operational metrics accumulator.
2. Track pending in-memory queue depth.
3. Track processing outcomes: completed, needs-review, terminal technical failures and retry events.
4. Track completed reviews.
5. Track retention deletions and retention deletion failures.
6. Add an opt-in operator metrics endpoint protected by a dedicated metrics key, not a tenant/customer key.
7. Do not include document ids, filenames, customer ids, API client names or other private/high-cardinality labels.
8. Extend Automation E2E rather than adding a new workflow.

## Access contract

Proposed configuration:

```json
{
  "Operations": {
    "Metrics": {
      "Enabled": false,
      "ApiKey": ""
    }
  }
}
```

When enabled:

```text
GET /operations/metrics
X-DocFlow-Metrics-Key: <operator-secret>
```

Rules:

```text
metrics disabled -> 404
missing/invalid metrics key -> 401
valid dedicated metrics key -> 200
normal tenant API key is not operator authorization
```

The endpoint is intentionally JSON for the current MVP; no Prometheus/OpenTelemetry backend is introduced in this milestone.

## Metric semantics

Process-local snapshot candidates:

```text
pendingQueueDepth
processingCompleted
processingNeedsReview
processingFailed
processingRetries
reviewsCompleted
retentionDeleted
retentionFailures
startedAt
uptimeSeconds
```

Counters reset when the process restarts. They are operational runtime telemetry, not persisted business/audit data.

## Non-goals

Do not add Prometheus, Grafana, OpenTelemetry Collector, distributed tracing, per-document/customer labels, persisted metrics storage, alerting rules or multi-instance aggregation.

## Acceptance

```text
metrics endpoint is disabled by default
separate operator key is required when enabled
queue depth is measured without changing queue ownership semantics
successful/NeedsReview/technical-failure/retry paths update counters
review completion updates counter
retention service records delete/failure outcomes
E2E verifies endpoint security plus representative counters
.NET CI + Automation E2E green
```
