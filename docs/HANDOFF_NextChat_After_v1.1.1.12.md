# DocFlow — Next Chat Handoff After v1.1.1.12

Use this file as the starting state for the next DocFlow development chat.

## Repository state

Repository: `avysotsky/DocFlow`  
Completed branch: `DocFlow/v_1.1.1.12_Deployability`  
Previous branch: `DocFlow/v_1.1.1.11_ApiKeyAuth`

Main implementation commit:

```text
d9e47607d9374d3596b61fac172e5ccd0cb98579
Add production container deployability and health probes
```

Validation:

```text
.NET CI #25 -> success
Deployment Smoke #1 -> success (run 36852307434)
Automation E2E #101 -> success (run 36852307379)
```

Detailed handoff: `docs/HANDOFF_v1.1.1.12_Deployability.md`.

## Current state

DocFlow is now runnable as a production container with PostgreSQL, persistent document storage, Python extraction worker and Tesseract OCR. The customer document API remains tenant-scoped and authenticated. Human review and CSV/XLSX export remain available.

Health endpoints:

```text
GET /health/live
GET /health/ready
```

Production startup validates tenant credentials. EF migrations are opt-in through `Database:ApplyMigrationsOnStartup`; the supplied Compose deployment enables that flag for the single-instance MVP.

Extraction baseline is unchanged:

```text
17/17 public documents passed
98/98 checked business fields matched
17/17 document types correct
17/17 validation statuses correct
```

No extraction/OCR logic changed in `v1.1.1.12`, so OCR/public-reference benchmarks were not run.

## CI discipline

Use `[skip ci]` for documentation/intermediate maintenance, batch implementation work, and validate with the narrowest relevant workflow. Do not run extraction/OCR benchmarks unless extraction behavior changes.

## Next milestone

Create `v1.1.1.13` after inspecting current processing/background-service behavior.

Current candidates:

1. Observability/retries — controlled retry behavior, useful failure diagnostics and operational visibility.
2. Reviewer/audit identity — individual attribution for human review actions.
3. Retention/delete — customer-visible lifecycle and deletion semantics.
4. Batch intake — only if required by a real workflow.

Observability/retries is the strongest current candidate because the MVP is now deployable and the next operational risk is handling failed background processing safely. Confirm that against the code before starting the milestone.
