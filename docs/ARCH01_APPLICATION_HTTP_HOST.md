# ARCH-01 — DocFlow Application Boundary → HTTP Host

## State
VALIDATION — DRAFT PR #8; exact-head CI pending

## Ownership
- Repository: `avysotsky/DocFlow`
- Worker branch: `DocFlow/arch01-application-http-host`
- Initial baseline: `be957f139cae0eafff3cd47241a5d7dd6beca855`
- Orchestrator canonical roadmap: `avysotsky/TradeOps/docs/orchestration/DUAL_TOPOLOGY_ARCHITECTURE_PLAN.md`
- Status owner: ARCH-01 worker. Merge owner: Development Orchestrator.

## Goal
Expose the existing, provider-neutral DocFlow extraction application flow as a standalone HTTP service, while preserving equivalent direct, CLI, and future in-process calls through reusable application code. This workstream must not implement TradeOps business logic.

## Required architecture
```
HTTP request → thin DocFlow.Api endpoint → DocFlow reusable application flow
                                      → normalization/schema extraction
                                      → selected provider/infrastructure adapter
```

- HTTP is a transport/host adapter, not a separate implementation of extraction.
- Existing CLI/provider paths must remain supported; no large-bang repository layout rewrite.
- Generic DocFlow contracts only. No `ResearchDecision`, portfolio, risk, broker, orders, backtest, or TradeOps reference.
- A future in-process host must invoke the same reusable application flow without loopback HTTP.

## First action (mandatory live review)
1. Fetch current DocFlow and TradeOps `main`, branch HEAD and compare.
2. Inspect current tests, workflows, existing Python package/CLI layout, generic extraction DTOs and DI/composition options.
3. Read `docs/DF04_SCHEMA_DRIVEN_TEXT_EXTRACTION.md`, `docs/DF05_OPENAI_SCHEMA_BACKEND.md`, `docs/DF06_OPENAI_TEXT_ARTIFACT_CLI.md`, `docs/DF07_GROQ_SCHEMA_BACKEND.md`.
4. Read the TradeOps canonical dual-topology roadmap and workstream protocol.
5. Record a bounded implementation proposal in this document before major moves. Avoid assuming this Python repository already contains .NET projects.
6. Confirm branch has not advanced before modifying files.

## Bounded implementation
- Introduce a reusable application entrypoint that can be used by HTTP and CLI without duplicating orchestration or extraction logic.
- Add a standalone HTTP host using the repository's existing language/runtime conventions. Do not introduce .NET into DocFlow just to match conceptual package names.
- Define a versioned generic request/response contract for the existing proven text normalization + schema-based structured extraction flow.
- Preserve explicit provider selection and explicit model requirements where provider-backed calls are requested; credentials only through server-side environment variables.
- Provide a simple health endpoint and clearly distinguish liveness from dependencies/readiness.
- Keep HTTP handlers thin, translate errors into bounded/sanitized responses, reject invalid inputs early and enforce bounded request size/time/cancellation where supported.
- Do not leak provider responses, prompt payloads, keys, or exception internals in HTTP errors/logs.
- No new asynchronous persistent job subsystem unless justified by existing functionality.

## Acceptance
1. HTTP host starts as a standalone deployable service.
2. Same generic extraction application code is called from CLI/non-HTTP and HTTP.
3. CLI and provider behavior remains backward compatible.
4. Versioned HTTP contract is strict, documented and generic (no TradeOps semantics).
5. Offline fixture-based HTTP integration tests cover success, schema validation, malformed input, invalid provider/model, and safe error handling.
6. Existing DocFlow suite remains green; exact-HEAD CI passes.
7. No TradeOps imports/dependencies, no credentials or private data committed.
8. Provide runnable local host instructions, environment configuration, and sample sanitized request/response.
9. Include explicit evidence of the same deterministic fixture producing equivalent structured facts through HTTP and a direct application invocation (provider network tests not required in CI).

## Non-goals
- No TradeOps.Api, TradeOps-owned port, HTTP client adapter or in-process adapter (ARCH-02/03/04).
- No monorepo or third repository.
- No NuGet/package publishing or generic shared core.
- No broker mutation or IBKR dependency.
- Do not delete existing CLI/child-process regression harnesses.

## Completion handoff
Update this file with final HEAD, changed files, architecture/contract decisions, tests, exact CI run, limitations, privacy/security check, blockers and next integration action. Open a **draft PR** to DocFlow main. Do not merge from the worker chat.

## Implementation checkpoint — 2026-10-08

- Initial baseline: `be957f139cae0eafff3cd47241a5d7dd6beca855`.
- HTTP/application implementation HEAD before this status update: `2f1df13fa1c46975a2d7d6f10b1e097051eb8d4d`.
- Draft PR: https://github.com/avysotsky/DocFlow/pull/8
- Implemented in-memory `normalize_text_document`, `extract_normalized_text`, `extract_text_document` entrypoints in the existing provider-neutral pipeline.
- The existing CLI reuses those routines while retaining artifact output order/semantics.
- Added `docflow_worker.http_api:create_app` with versioned `POST /api/v1/extractions`, `GET /health/live`, `GET /health/ready`.
- Run locally after installing the worker package: `uvicorn docflow_worker.http_api:app --host 127.0.0.1 --port 8081` from `src/DocFlow.Extraction.Worker`.
- HTTP accepts `schemaVersion=1`, `rawDocument`, `schemaRequest`, `provider=openai|groq`, explicit `model`, and optional `documentName`. Provider credentials are server environment only. Request maximum: 1 MiB.
- Response includes canonical `normalizedDocument` and `structuredResult` under `schemaVersion=1`; extraction validation status remains canonical and is not silently changed.
- Tests added for deterministic in-memory ↔ HTTP parity, malformed input, provider-failure redaction, health metadata, and body limits.
- Public/DocFlow extraction domain models and provider backends unchanged. No TradeOps dependencies.
- Real provider smoke: NOT RUN; optional operator-only. Post-merge CI: NOT RUN.
- Exact PR-head CI: PENDING; do not mark this workstream integrated without successful CI.
- Privacy: synthetic fixtures only; no credentials committed or accepted in HTTP contract.
- Integration: orchestrator review after exact-head checks, no worker merge.
