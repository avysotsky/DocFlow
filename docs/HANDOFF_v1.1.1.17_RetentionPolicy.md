# DocFlow — handoff v1.1.1.17 Retention Policy

Status: **ACTIVE**  
Repository: `avysotsky/DocFlow`  
Branch: `DocFlow/v_1.1.1.17_RetentionPolicy`  
Base: `DocFlow/v_1.1.1.16_OriginalPdfAccess`

## Why this milestone exists

DocFlow already supports explicit tenant-scoped deletion and the `Document` entity already stores nullable `DeleteAt`, but normal uploads leave `DeleteAt == null` and no automatic retention sweep exists.

## Scope

Keep `v1.1.1.17` narrow and single-instance:

1. Add opt-in retention configuration; disabled by default.
2. When enabled, assign `DeleteAt` to new uploads using a configurable default retention period.
3. Add one single-instance periodic hosted sweep.
4. Sweep only terminal `Processed`, `NeedsReview`, and `Failed` rows whose `DeleteAt <= now`.
5. Never auto-delete `Uploaded` or `Processing`; leave them for a later sweep after they become terminal.
6. Reuse `IDocumentDeletionService` for file/database cleanup and row-lock race handling.
7. Bound each sweep by a configurable batch size.
8. Extend existing Automation E2E/restart coverage rather than creating another workflow.

## Configuration contract

Proposed defaults:

```json
{
  "Retention": {
    "Enabled": false,
    "DefaultRetentionDays": 30,
    "SweepIntervalSeconds": 3600,
    "BatchSize": 100
  }
}
```

The policy is deliberately opt-in. Existing deployments must not begin deleting historical documents merely by upgrading.

## Safety semantics

```text
retention disabled -> new uploads keep DeleteAt = null; no sweep runs
retention enabled -> new uploads receive a future DeleteAt
expired terminal document -> automatic cleanup using existing deletion service
expired Uploaded/Processing -> skipped, not deleted
state race to active -> deletion service returns conflict; retain for later sweep
missing row -> harmless no-op for the sweep
per-document deletion failure -> log and continue with other candidates
```

No distributed scheduler/lease is introduced. This follows the current single-instance processing/deployment boundary.

## Non-goals

Do not add:

- per-tenant retention settings;
- legal hold;
- soft-delete/tombstones;
- admin retention API;
- distributed scheduler/leases;
- S3 lifecycle rules;
- changes to OCR/extraction;
- reviewer identity.

## Acceptance criteria

```text
retention is off by default
options are validated on startup
when enabled, API upload sets non-null future DeleteAt
periodic sweep removes expired terminal rows and stored PDF
related extraction/review rows still use existing cascades
expired active rows remain present
future/non-expiring rows remain present
existing explicit delete/file/restart/retry flows stay green
.NET CI and Automation E2E remain green
only relevant workflows run
```