# DocFlow — handoff v1.1.1.24 Per-Tenant Retention Policy

Status: **COMPLETED**  
Repository: `avysotsky/DocFlow`  
Branch: `DocFlow/v_1.1.1.24_PerTenantRetentionPolicy`  
Base: `DocFlow/v_1.1.1.23_BatchIdempotency`

## Implementation

Authoritative implementation commit:

```text
13d9b60ffa357e844b46aefbebe99ee299a4d3e9
Add per-tenant retention policy overrides
```

No database migration was required.

## Retention configuration

Deployment-wide defaults remain authoritative fallbacks:

```json
{
  "Retention": {
    "Enabled": false,
    "DefaultRetentionDays": 30,
    "SweepIntervalSeconds": 3600,
    "BatchSize": 100,
    "TenantOverrides": []
  }
}
```

A tenant override is keyed only by trusted `CustomerId`:

```json
{
  "CustomerId": "11111111-1111-1111-1111-111111111111",
  "Enabled": true,
  "RetentionDays": 90
}
```

`Enabled` and `RetentionDays` are independently optional.

Effective policy:

```text
Enabled = tenant.Enabled ?? global.Enabled
RetentionDays = tenant.RetentionDays ?? global.DefaultRetentionDays
```

The request body never controls retention.

## Persistence semantics

`DocumentIntakeService` resolves the effective tenant policy when an accepted document is created and persists the resulting `DeleteAt` on the `Document`.

Existing documents are intentionally not recalculated when configuration changes. Their persisted `DeleteAt` remains the lifecycle decision honored by retention cleanup.

Single and batch intake both use the same `DocumentIntakeService`, so the tenant retention policy applies consistently to both paths.

## Startup validation

The host now rejects invalid tenant override configuration when:

```text
CustomerId is empty
CustomerId appears more than once
RetentionDays is outside 1..3650
an override sets neither Enabled nor RetentionDays
```

## Sweep behavior

The retention hosted service starts when either:

```text
global Retention.Enabled == true
or at least one tenant override explicitly has Enabled == true
```

This allows a tenant to opt into retention even while the deployment default is disabled.

The deletion query itself remains unchanged and only considers persisted rows where:

```text
DeleteAt <= now
and Status in (Processed, NeedsReview, Failed)
```

`Uploaded` and `Processing` documents are never automatically deleted.

A tenant that disables retention affects newly accepted documents by receiving `DeleteAt = null`. Existing documents that already have `DeleteAt` keep it and remain eligible when it expires.

## E2E proof

Automation E2E restart/lifecycle configuration used:

```text
global Enabled = true
global DefaultRetentionDays = 7
primary tenant override RetentionDays = 2, Enabled inherited
second tenant override Enabled = false
```

The test proved:

```text
primary upload -> future DeleteAt approximately +2 days
second-tenant upload -> DeleteAt == null
previous default-off documents remained without DeleteAt
both tenant uploads processed successfully
existing restart recovery still passed
terminal-only retention sweep still passed
```

## Final validation

```text
.NET CI #39 -> success (run 36908516866)
Automation E2E #115 -> success (run 36908516614)
```

No Deployment Smoke, Scanned OCR E2E or Public Reference Benchmark was triggered because deployment/extraction behavior did not change.

## Scope boundary

This is configuration-backed tenant policy, not a tenant administration subsystem. There is no customer-facing endpoint for changing retention and no DB policy table. That remains appropriate for the current API-key tenant model.
