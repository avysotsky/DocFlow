# DocFlow — handoff v1.1.1.24 Per-Tenant Retention Policy

Status: **ACTIVE**  
Repository: `avysotsky/DocFlow`  
Branch: `DocFlow/v_1.1.1.24_PerTenantRetentionPolicy`  
Base: `DocFlow/v_1.1.1.23_BatchIdempotency`

## Goal

Allow trusted tenant-specific retention policy overrides without introducing a general tenant-management subsystem.

## Selected contract

Deployment-wide defaults remain:

```text
Retention.Enabled
Retention.DefaultRetentionDays
```

Optional configuration overrides are keyed by trusted `CustomerId`:

```json
"TenantOverrides": [
  {
    "CustomerId": "...",
    "Enabled": true,
    "RetentionDays": 90
  }
]
```

Both override fields are optional. Effective policy is:

```text
effective Enabled = tenant.Enabled ?? global.Enabled
effective RetentionDays = tenant.RetentionDays ?? global.DefaultRetentionDays
```

The request payload never controls retention.

## Persistence semantics

The effective policy is evaluated only when a new document is accepted. `DeleteAt` remains the durable decision stored on the document.

Existing documents are not recalculated when configuration changes. A persisted `DeleteAt` continues to be honored by the existing terminal-only retention sweep.

## Safety

- validate non-empty unique override CustomerIds;
- validate optional RetentionDays in the existing 1..3650 range;
- reject empty/no-op override entries;
- run the retention hosted service when the global policy is enabled or any tenant explicitly enables retention;
- keep automatic deletion limited to terminal `Processed`, `NeedsReview`, and `Failed` rows with expired `DeleteAt`;
- do not add DB tenant configuration or request-level retention controls.

## Acceptance

- no override preserves current global behavior;
- tenant can override retention days while inheriting global enabled state;
- tenant can explicitly disable automatic retention while global retention is enabled;
- upload response/persisted document receives the effective `DeleteAt`;
- existing documents keep existing `DeleteAt`;
- restart/retention regression remains green;
- .NET CI + Automation E2E green.
