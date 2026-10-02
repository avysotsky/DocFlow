# DocFlow — Next Chat Handoff After v1.1.1.26

Use this file as the starting state for the next DocFlow development chat.

## Repository state

Repository: `avysotsky/DocFlow`  
Completed branch: `DocFlow/v_1.1.1.26_StorageKeyDeprecation`  
Previous branch: `DocFlow/v_1.1.1.25_BatchResumeFaultInjection`

Implementation:

```text
dc9c71d7fb02671a19c8821f85f1bdadd997fe01
Deprecate StorageKey in document metadata contract
```

Final test-harness state:

```text
19b3141a8cc8a61872b227c3c8453c883f88a630
Fix binary source-file compatibility assertion
```

Validation:

```text
.NET CI #40 -> success (run 36989497543)
Automation E2E #121 -> success (run 36989710997)
```

Detailed handoff:

```text
docs/HANDOFF_v1.1.1.26_StorageKeyDeprecation.md
```

## Current product state

DocFlow now supports:

```text
API-key authenticated tenant/client
  -> single and bounded batch PDF intake
  -> persisted single/batch idempotency
  -> proven incomplete-batch resume after DB failure
  -> startup recovery + bounded processing retries
  -> deterministic digital/OCR invoice/quotation extraction
  -> PostgreSQL persistence
  -> tenant-scoped inbox
  -> stable sourceFileUrl + authenticated original PDF streaming
  -> legacy storageKey retained but OpenAPI-deprecated
  -> review/correction + authenticated client audit attribution
  -> CSV/XLSX export
  -> explicit terminal deletion
  -> global/per-tenant retention policy
  -> protected process-local operational metrics
```

Extraction/OCR baseline remains unchanged:

```text
17/17 public documents passed
98/98 checked business fields matched
17/17 document types correct
17/17 validation statuses correct
69 Python regression tests
```

## Storage-key compatibility boundary

`GET /api/documents/{id}` returns:

```text
storageKey    -> legacy compatibility field, deprecated in OpenAPI
sourceFileUrl -> supported relative API retrieval path
```

Do not remove `storageKey` silently in an unversioned response.

## Recommended next milestone

Candidate: `v1.1.1.27_CompletionNotifications`.

Current customer-flow gap:

```text
upload document
-> processing happens asynchronously
-> client must poll document/inbox to discover completion
```

A commercial integration may need push notification when a document reaches a terminal state.

Before implementing, inspect:

```text
src/DocFlow.Infrastructure/Processing/DocumentProcessingService.cs
src/DocFlow.Api/BackgroundServices/DocumentProcessingBackgroundService.cs
src/DocFlow.Domain/Entities/Document.cs
src/DocFlow.Api/Authentication/ApiKeyAuthentication.cs
src/DocFlow.Api/Program.cs
compose.yaml
.github/workflows/automation-e2e.yml
```

Preferred investigation:

- determine whether notifications should be tenant-configured webhooks rather than request-supplied callback URLs;
- do not allow arbitrary per-request callback URLs without addressing SSRF/security;
- decide whether reliable delivery requires a persisted outbox before sending HTTP;
- terminal events of interest are likely `Processed`, `NeedsReview`, and `Failed`;
- ensure retries/restarts do not produce uncontrolled duplicate notifications;
- use an explicit event/delivery id if receivers may need idempotency;
- sign webhook payloads if a webhook contract is selected;
- keep webhook delivery asynchronous from document processing;
- do not introduce RabbitMQ/Kafka solely for this milestone.

The first task in the next chat should be architecture inspection. If a safe reliable webhook requires too much scope for one milestone, split it into persisted completion-event outbox first and HTTP delivery second.

## Other later candidates

- named-human reviewer IAM only when actual user accountability is required;
- persistent/external telemetry when deployment requirements justify it;
- distributed processing ownership only when multiple active API instances become a real deployment requirement;
- explicit versioned removal of `storageKey` only when a breaking API version is warranted.

## CI discipline

Continue sparse CI:

- docs/intermediate work -> `[skip ci]`;
- coherent C# API/Application/Domain/Infrastructure changes -> .NET CI + Automation E2E;
- Deployment Smoke only for Docker/compose/health/deployment-contract changes;
- Scanned OCR E2E only for OCR/extraction-runner changes;
- Public Reference Benchmark only for extraction-rule changes.
