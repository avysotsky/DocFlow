# DocFlow — handoff v1.1.1.12 Deployability

Status: **ACTIVE**  
Repository: `avysotsky/DocFlow`  
Branch: `DocFlow/v_1.1.1.12_Deployability`  
Base: `DocFlow/v_1.1.1.11_ApiKeyAuth`

## Why this milestone exists

The commercial MVP has authenticated tenant-scoped document processing, review, persistence and export, but it still lacks a reproducible production deployment contract.

The current gap is operational rather than extraction-related: a clean checkout does not yet produce one self-contained runtime image with the .NET API, Python extraction worker and Tesseract OCR, and there is no readiness endpoint or explicit startup configuration policy.

## Scope

`v1.1.1.12` is intentionally limited to deployability/configuration:

1. Build a production Docker image containing the .NET 8 API, Python worker dependencies and Tesseract OCR.
2. Add `GET /health/live` and `GET /health/ready`.
3. Readiness must verify PostgreSQL connectivity plus the configured storage/worker runtime paths.
4. Require at least one valid API-key client outside Development and fail startup on invalid tenant-key configuration.
5. Add an explicit `Database:ApplyMigrationsOnStartup` flag; default behavior remains opt-in rather than silently migrating every deployment.
6. Add a Docker Compose deployment contract using environment-supplied secrets and persistent PostgreSQL/document-storage volumes.
7. Add one narrow deployment smoke workflow proving the image boots, migrations can be applied, readiness becomes healthy, anonymous document access remains `401`, and authenticated tenant access works.

## Non-goals

Do not add in this milestone:

- reviewer/user IAM;
- retry/observability redesign;
- document retention/delete;
- batch upload;
- new extraction/OCR rules;
- ONNX/LLM fallback;
- Kubernetes manifests or cloud-specific infrastructure.

## Acceptance criteria

The milestone is complete when one implementation commit proves all of the following in CI:

```text
docker build succeeds
Python worker imports inside image
Tesseract exists inside image
PostgreSQL starts
DocFlow production container starts
opt-in EF migrations complete
GET /health/live -> 200 Healthy
GET /health/ready -> 200 Healthy
GET /api/documents without API key -> 401
GET /api/documents with configured tenant key -> 200
```

Existing API/processing behavior must remain covered by the normal narrow CI triggered by the implementation change. Public Reference Benchmark and Scanned OCR E2E must not be run because extraction/OCR behavior is unchanged.
