# DocFlow — handoff v1.1.1.19 Operational Metrics

Status: **COMPLETED**  
Repository: `avysotsky/DocFlow`  
Branch: `DocFlow/v_1.1.1.19_OperationalMetrics`  
Base: `DocFlow/v_1.1.1.18_ReviewAuditIdentity`

## 1. Milestone result

`v1.1.1.19` adds low-cardinality, process-local operational metrics without introducing Prometheus/OpenTelemetry infrastructure or weakening the tenant boundary.

Implementation commits:

```text
e59d07e680c873c7118d44e8a875b2a7c3172f2e
Add protected process-local operational metrics

3d6c74c7c890a2b0230e6aab33d86c9b5cf7540e
Fix operational queue-depth publication race
```

The second commit is the final validated implementation state. A queue-depth publication race was found during implementation review and fixed before milestone closure.

Final validation:

```text
.NET CI #33
run id: 36884608529
result: success

Automation E2E #109
run id: 36884608517
result: success
```

An earlier validation pair was triggered by the first implementation commit and was superseded by the final pair after the queue-depth race fix. Deployment Smoke, Scanned OCR E2E and Public Reference Benchmark were not triggered.

## 2. Metrics model

New thread-safe singleton:

```text
DocFlow.Application.Observability.OperationalMetrics
```

Snapshot fields:

```text
StartedAt
UptimeSeconds
PendingQueueDepth
ProcessingCompleted
ProcessingNeedsReview
ProcessingFailed
ProcessingRetries
ReviewsCompleted
RetentionDeleted
RetentionFailures
```

All counters are process-local and reset when the application restarts. They are runtime telemetry, not persisted business/audit data.

No metric contains document ids, filenames, customer ids, API client names or other private/high-cardinality labels.

## 3. Queue-depth semantics

`DocumentProcessingQueue` now updates the process-local pending queue gauge.

The increment occurs before publishing an item to the `Channel<Guid>`. If channel publication fails, the reservation is rolled back. A successful dequeue decrements the gauge.

This ordering is deliberate: incrementing only after `WriteAsync` could allow the single reader to dequeue first and leave the gauge permanently one item too high.

The queue remains the same in-memory, unbounded, single-reader channel; observability does not change ownership or recovery semantics.

## 4. Processing counters

Counters are updated at durable state transitions:

```text
ValidationStatus.Valid save      -> ProcessingCompleted++
non-valid extraction save        -> ProcessingNeedsReview++
retry decision before reattempt  -> ProcessingRetries++
terminal Failed state persisted  -> ProcessingFailed++
```

`ProcessingCompleted` / `ProcessingNeedsReview` count newly persisted extraction outcomes, including the existing API save path because it uses the same `ExtractionResultService`.

`ProcessingFailed` increments only after the terminal `Failed` state is successfully persisted; deleted/already-completed no-op paths do not fabricate failure counts.

## 5. Review / retention counters

A successfully persisted review increments:

```text
ReviewsCompleted
```

Retention increments:

```text
RetentionDeleted  -> successful automatic deletion
RetentionFailures -> per-document deletion exception or sweep-level exception
```

Skipped/not-found/active-conflict retention candidates are not counted as failures.

## 6. Operator endpoint and security boundary

Configuration:

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

Endpoint when enabled:

```text
GET /operations/metrics
X-DocFlow-Metrics-Key: <operator-secret>
```

Security rules:

```text
Enabled=false -> 404
Enabled=true + missing/invalid metrics key -> 401
Enabled=true + valid dedicated metrics key -> 200 JSON snapshot
```

The endpoint uses a dedicated operator credential and is intentionally not authorized by `X-DocFlow-Api-Key`. Tenant API keys must not grant access to global process telemetry.

Startup options validation requires a non-empty operator key whenever metrics are enabled.

## 7. E2E coverage

The existing Automation E2E remains on repository defaults (`Operations:Metrics:Enabled=false`). Its review scenario now verifies:

```text
GET /operations/metrics -> 404
```

This proves an ordinary tenant runtime does not expose operator metrics merely because the route exists.

The enabled/operator-key branch is implemented and startup-validated but the repository does not commit a test or production operator secret. No dedicated metrics backend or additional workflow was added.

Existing processing, retry, review, restart recovery, original-file access, deletion and retention scenarios all remained green in Automation E2E #109.

## 8. Explicit boundaries

This milestone does **not** add:

- Prometheus/Grafana;
- OpenTelemetry Collector/exporters;
- distributed tracing;
- persisted metrics storage;
- alerting rules;
- per-tenant or per-document metric labels;
- cross-instance aggregation;
- a new operator/user IAM system.

If DocFlow later runs multiple active application instances, these process-local counters are per-instance and need an external aggregation/telemetry layer.

## 9. CI discipline

Continue sparse CI:

- documentation/intermediate maintenance -> `[skip ci]`;
- coherent API/Application/Infrastructure changes -> `.NET CI` + Automation E2E;
- Deployment Smoke only for Docker/compose/health/deployment-contract changes;
- Scanned OCR E2E only for OCR/extraction-runner/fixture changes;
- Public Reference Benchmark only for extraction-rule changes.

## 10. Next direction

A strong next commercial-product candidate is **Batch Intake**. The current API accepts one PDF per upload request, while document-automation customers commonly submit groups of invoices/quotations.

Before implementing batch intake, inspect the current controller-embedded upload logic and define deterministic partial-failure semantics. Prefer extracting/reusing a single-document upload operation rather than duplicating file validation/storage/DB/queue logic.

Do not add ZIP parsing, mailbox ingestion or cloud-bucket polling in the same milestone unless an actual requirement appears.
