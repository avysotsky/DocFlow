# DocFlow — handoff v1.1.1.12 Deployability

Status: **COMPLETED**  
Repository: `avysotsky/DocFlow`  
Branch: `DocFlow/v_1.1.1.12_Deployability`  
Base: `DocFlow/v_1.1.1.11_ApiKeyAuth`

## 1. Milestone result

`v1.1.1.12` closes the main MVP deployability/configuration gap without changing extraction/OCR behavior.

Main implementation commit:

```text
d9e47607d9374d3596b61fac172e5ccd0cb98579
Add production container deployability and health probes
```

Validation:

```text
.NET CI #25
result: success

Deployment Smoke #1
run id: 36852307434
result: success

Automation E2E #101
run id: 36852307379
result: success
```

Only the three relevant workflows ran. Public Reference Benchmark and Scanned OCR E2E were not triggered because extraction/OCR behavior was unchanged.

## 2. Production image

A root-level `Dockerfile` now builds one runtime image containing:

- published .NET 8 API;
- Python extraction worker;
- worker Python dependencies in `/opt/docflow-venv`;
- Tesseract OCR and English language data;
- persistent file-storage path `/data/storage`;
- non-root runtime user.

The container listens on port `8080` and has a liveness `HEALTHCHECK` against `/health/live`.

## 3. Health and readiness

Public deployment probes now exist:

```text
GET /health/live
GET /health/ready
```

`/health/live` confirms the web process is responsive.

`/health/ready` returns healthy only when:

- PostgreSQL is reachable;
- configured storage root exists;
- extraction worker `main.py` exists;
- an explicitly configured absolute Python executable exists when one is supplied.

Probe failures return `503` without exposing internal exception details.

## 4. Production configuration rules

Outside Development, API-key options are validated on startup:

- at least one API client must exist;
- each client must have non-empty `CustomerId` and `ApiKey`;
- API keys must be unique.

Invalid production tenant-key configuration fails startup instead of leaving a silently unusable API.

Database migration-on-start is explicit:

```text
Database:ApplyMigrationsOnStartup=true|false
```

The default remains false when the setting is absent. This avoids silently applying migrations in every deployment environment.

## 5. Docker Compose contract

Root `compose.yaml` provides a production-like local deployment with:

- PostgreSQL 16;
- persistent PostgreSQL volume;
- persistent document-storage volume;
- environment-supplied database/API secrets;
- PostgreSQL health dependency;
- DocFlow readiness healthcheck;
- explicit startup migrations for this single-instance MVP deployment.

`.env.example` contains only placeholders/non-secret defaults. `.env` remains ignored by git.

Typical startup:

```bash
cp .env.example .env
# replace secret placeholders
docker compose up --build -d
```

## 6. Deployment smoke proof

`.github/workflows/deployment-smoke.yml` proves from a clean checkout that:

```text
compose config is valid
Docker image builds
Python worker imports in the image
Tesseract exists in the image
PostgreSQL becomes healthy
production DocFlow container starts
opt-in EF migrations apply
GET /health/live -> Healthy
GET /health/ready -> Healthy
GET /api/documents without key -> 401
GET /api/documents with configured tenant key -> 200
```

The existing Automation E2E also remained green, so deployment changes did not regress the document-processing/review/export flow.

## 7. Deliberately not added

This milestone did not add:

- human reviewer IAM/audit identity;
- durable retry redesign or operational diagnostics;
- retention/delete APIs;
- batch intake;
- new extraction rules;
- ONNX/LLM fallback;
- Kubernetes/cloud-specific infrastructure.

## 8. Next step

Choose one measured post-deployability gap for `v1.1.1.13`.

Best current candidates:

1. **Observability/retries** — processing failure diagnostics, retry behavior and operational visibility.
2. **Reviewer/audit identity** — individual attribution for human corrections.
3. **Retention/delete** — customer-visible lifecycle and deletion semantics.
4. **Batch intake** — only if a real customer workflow requires multi-document submission.

Inspect the current processing/background-service behavior before selecting. Keep the next milestone narrow and measurable.
