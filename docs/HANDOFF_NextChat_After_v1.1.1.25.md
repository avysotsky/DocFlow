# DocFlow — Next Chat Handoff After v1.1.1.25

Use this file as the starting state for the next DocFlow development chat.

## Repository state

Repository: `avysotsky/DocFlow`  
Completed branch: `DocFlow/v_1.1.1.25_BatchResumeFaultInjection`  
Previous branch: `DocFlow/v_1.1.1.24_PerTenantRetentionPolicy`

Authoritative reliability-test commit:

```text
3bb4c7b5a6d06f256957e6986df6b9c49260614e
Match persisted batch checkpoint key format
```

Final validation:

```text
Automation E2E #119 -> success (run 36987322882)
```

Detailed handoff:

```text
docs/HANDOFF_v1.1.1.25_BatchResumeFaultInjection.md
```

## Current product state

DocFlow supports:

```text
API-key authenticated tenant/client
  -> single PDF upload with persisted optional Idempotency-Key
  -> bounded partial-success multi-PDF batch intake
  -> persisted whole-request batch idempotency
  -> durable per-item batch checkpoints
  -> proven incomplete-batch resume after real DB failure
  -> cleanup of expired single/batch idempotency state
  -> trusted per-tenant retention overrides
  -> startup recovery of orphaned processing work
  -> bounded technical processing retries + diagnostics
  -> digital PDF / conditional Tesseract OCR
  -> deterministic invoice/quotation extraction + validation
  -> tenant-scoped inbox
  -> original PDF streaming
  -> human correction/review + API-client audit attribution
  -> CSV/XLSX export
  -> explicit terminal delete
  -> optional terminal retention cleanup
  -> protected process-local operational metrics
```

Extraction/OCR baseline remains:

```text
17/17 public documents passed
98/98 checked business fields matched
17/17 document types correct
17/17 validation statuses correct
69 Python regression tests
```

## Batch reliability boundary

Automation E2E #119 now proves the previously untested incomplete-resume path:

```text
partial batch succeeds around one injected DB failure
-> unaffected item checkpoints persist
-> batch manifest remains incomplete
-> retry same external key/payload
-> unaffected items replay
-> failed item executes successfully
-> manifest completes
-> third request is exact completed replay
-> no duplicate accepted documents
```

The injected failure exists only in E2E through a temporary PostgreSQL trigger. Production code contains no fault-injection feature.

## Recommended next milestone

Candidate: `v1.1.1.26_StorageKeyDeprecation`.

Inspect before implementing:

```text
src/DocFlow.Api/Controllers/DocumentsController.cs
src/DocFlow.Api/Controllers/DocumentFilesController.cs
src/DocFlow.Api/Program.cs
.github/scripts/verify_document_inbox.py
README.md
```

Current issue:

```text
document metadata still exposes StorageKey
GET /api/documents/{id}/file already provides the supported source-file access path
new clients should not depend on internal storage layout
silently removing StorageKey would be a breaking API change
```

Preferred direction:

- inventory every response that exposes `StorageKey`;
- preserve the current JSON field for compatibility in the existing contract;
- expose a stable source-file link/path if useful to clients;
- mark the legacy field as deprecated in OpenAPI if Swashbuckle can represent that cleanly;
- if removal requires a versioned contract, introduce the smallest explicit versioning boundary rather than changing existing responses silently;
- extend E2E/OpenAPI assertions so the compatibility and deprecation contract is intentional;
- do not build a broad API gateway/version-management subsystem just for this field.

If inspection shows that a clean deprecation cannot be expressed without disproportionate framework work, document the compatibility decision and choose the next concrete customer-facing gap instead of adding architecture for appearance.

## Other later candidates

- outbound completion notifications/webhooks if customers need push instead of polling;
- named-human reviewer IAM only when actual human accountability is required;
- persistent/external telemetry when deployment requirements justify it;
- distributed processing ownership only when multiple active instances become a real requirement.

## CI discipline

Continue sparse CI:

- docs/intermediate work -> `[skip ci]`;
- C# API/Application/Domain/Infrastructure changes -> .NET CI + Automation E2E;
- test-only E2E changes -> only the relevant E2E workflow;
- Deployment Smoke only for Docker/compose/health/deployment-contract changes;
- Scanned OCR E2E only for OCR/extraction-runner changes;
- Public Reference Benchmark only for extraction-rule changes.
