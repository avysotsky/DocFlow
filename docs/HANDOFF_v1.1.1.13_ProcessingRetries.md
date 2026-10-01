# DocFlow — handoff v1.1.1.13 Processing Retries

Status: **COMPLETED**  
Repository: `avysotsky/DocFlow`  
Branch: `DocFlow/v_1.1.1.13_ProcessingRetries`  
Base: `DocFlow/v_1.1.1.12_Deployability`

## 1. Milestone result

`v1.1.1.13` adds bounded technical-failure retries plus persisted processing diagnostics without introducing a durable broker or changing extraction/OCR behavior.

Main implementation commit:

```text
c51ad25cdd34da98c4bc3446e05194fa9247958c
Add bounded processing retries and persisted diagnostics
```

Validation:

```text
.NET CI #26
run id: 36869555535
result: success

Automation E2E #102
run id: 36869555594
result: success

Deployment Smoke #2
run id: 36869555520
result: success

Scanned OCR E2E #75
run id: 36869555532
result: success
```

Deployment Smoke and Scanned OCR E2E were unintentionally triggered by path filters that were still broader than the milestone required. Both remained green. Their push filters are narrowed in the closing `[skip ci]` commit so ordinary retry/DB/API work does not launch them in the future.

Public Reference Benchmark was not run because extraction behavior did not change.

## 2. Retry policy

New configuration section:

```json
{
  "Processing": {
    "Retry": {
      "MaxAttempts": 3,
      "RetryDelayMilliseconds": 250
    }
  }
}
```

Startup validation requires:

- `MaxAttempts` between 1 and 10;
- `RetryDelayMilliseconds` between 0 and 60000.

For one dequeued document job, `DocumentProcessingBackgroundService` now retries a technical processing exception until the configured attempt limit is reached.

Behavior:

```text
attempt succeeds -> return
attempt fails and attempts remain -> warning + delay + retry
final attempt fails -> persist Failed + error log
host shutdown cancellation -> stop without fabricating a technical failure
```

This is a bounded in-process retry policy. It is deliberately not presented as durable distributed retry infrastructure.

## 3. Persisted processing diagnostics

`Document` now persists:

```text
ProcessingAttempts
LastProcessingAttemptAt
LastProcessingFailureAt
LastProcessingError
```

Migration:

```text
20261001133000_AddDocumentProcessingDiagnostics
```

Every actual extraction attempt increments `ProcessingAttempts` and stores `LastProcessingAttemptAt`.

Technical exceptions persist a bounded, sanitized failure summary. Full raw exception detail remains in application logs.

A successful `Processed` or `NeedsReview` result clears the last failure summary/timestamp while retaining the cumulative attempt count and last-attempt timestamp.

The document is marked `Failed` only after the configured attempts for that dequeued job are exhausted.

## 4. Tenant-scoped diagnostics API

New endpoint:

```text
GET /api/documents/{documentId}/processing-diagnostics
```

Response includes:

```text
DocumentId
Status
ProcessingAttempts
LastProcessingAttemptAt
LastProcessingFailureAt
LastProcessingError
```

The endpoint uses the existing API-key tenant identity. Cross-tenant document ids return `404`.

The initial ACTIVE handoff proposed putting the fields directly on `GET /api/documents/{id}`. Implementation uses a dedicated diagnostics endpoint instead, keeping the normal document representation stable while still providing the required tenant-scoped read contract.

## 5. E2E proof

The existing Automation E2E technical-failure fixture inserts a document whose storage file does not exist.

The inbox/auth verifier now proves:

```text
successful supplier invoice -> ProcessingAttempts == 1
successful document -> no last processing failure
missing-file technical failure -> final status Failed
failed document -> ProcessingAttempts == 3
failed document -> last attempt timestamp exists
failed document -> last failure timestamp exists
failed document -> sanitized failure summary persisted
cross-tenant diagnostics request -> 404
```

Repeated enqueue idempotency and all previous quotation/invoice/review/export scenarios remain green.

## 6. Important limitation still open

`DocumentProcessingQueue` is still an in-memory `Channel<Guid>`.

Therefore bounded retry solves transient failures while the host is alive, but an application restart can still lose queued work. Persisted document state makes a narrow restart-recovery mechanism possible without immediately introducing RabbitMQ/Kafka.

Do not describe `v1.1.1.13` as durable queueing.

## 7. CI hygiene correction

After observing the implementation run:

- Deployment Smoke no longer triggers merely because `Program.cs` changes;
- Scanned OCR E2E no longer triggers for general processing-service/background-queue changes;
- OCR E2E remains tied to the extraction worker, `PythonDocumentExtractionRunner`, OCR fixtures/scripts, and its workflow file.

Use `[skip ci]` for documentation/CI-maintenance commits and keep extraction benchmarks reserved for actual extraction changes.

## 8. Next step

Best next milestone: **restart recovery for persisted processing work**, likely `v1.1.1.14_RestartRecovery`.

Before adding an external broker, inspect the document-state transitions and implement the smallest safe recovery contract, for example:

- on host startup find persisted `Uploaded` documents without extraction results;
- identify stale `Processing` documents without extraction results;
- re-enqueue those ids into the existing in-memory queue;
- rely on the existing extraction-result uniqueness/idempotency guard;
- define a staleness threshold so active work is not blindly duplicated.

Keep RabbitMQ/Kafka, distributed leasing, and multi-instance workers out of that milestone unless evidence requires them.
