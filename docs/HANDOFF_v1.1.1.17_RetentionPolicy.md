# DocFlow — handoff v1.1.1.17 Retention Policy

Status: **COMPLETED**  
Repository: `avysotsky/DocFlow`  
Branch: `DocFlow/v_1.1.1.17_RetentionPolicy`  
Base: `DocFlow/v_1.1.1.16_OriginalPdfAccess`

## 1. Milestone result

`v1.1.1.17` adds an opt-in automatic retention policy around the existing nullable `Document.DeleteAt` field without introducing a distributed scheduler or changing the current single-instance processing boundary.

Main implementation commit:

```text
d5aad1e030bb4c76a8d69f9ac9836c5458b60bca
Add opt-in document retention policy
```

Two staging commits prepared cumulative implementation/E2E content with `[skip ci]` before the validating commit:

```text
dc1881ea70e22668d2558ed986282ac0d96435be
70ecdf2b12189c3e35c111a26d6374659beab450
```

Validation:

```text
.NET CI #30
run id: 36878520692
result: success

Automation E2E #106
run id: 36878520631
result: success
```

Only these two relevant workflows ran. Deployment Smoke, Scanned OCR E2E and Public Reference Benchmark were not triggered.

## 2. Configuration

New configuration section:

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

Default is deliberately `Enabled=false` so an upgrade cannot silently begin deleting historical documents.

Startup validation enforces:

```text
DefaultRetentionDays: 1..3650
SweepIntervalSeconds: 1..86400
BatchSize: 1..1000
```

## 3. Upload behavior

When retention is disabled:

```text
DeleteAt = null
```

When retention is enabled, `DocumentsController` computes a future expiry using `DefaultRetentionDays` and passes it into the existing `Document` constructor.

`POST /api/documents` response now also includes nullable `DeleteAt`, allowing clients to see the scheduled lifecycle timestamp without another metadata request.

## 4. Retention hosted service

New files:

```text
src/DocFlow.Api/Retention/DocumentRetentionOptions.cs
src/DocFlow.Api/Retention/DocumentRetentionHostedService.cs
```

`DocumentRetentionHostedService` is registered after processing recovery and the normal queue consumer.

When disabled it exits immediately after logging that retention is disabled.

When enabled it runs a periodic single-instance sweep. Each sweep selects at most `BatchSize` documents satisfying:

```text
DeleteAt != null
DeleteAt <= now
Status == Processed || NeedsReview || Failed
```

Candidates are ordered by expiry/creation/id for deterministic bounded batches.

## 5. Safety behavior

`Uploaded` and `Processing` documents are not selected by the retention query, even when already past `DeleteAt`.

For every terminal candidate the hosted service resolves a fresh scoped `IDocumentDeletionService` and reuses the existing explicit-deletion implementation. This preserves:

```text
PostgreSQL FOR UPDATE state serialization
stored PDF cleanup
Document row deletion
ExtractionResult / DocumentReview cascades
active-state conflict protection
existing filesystem/database consistency semantics
```

If a candidate disappears or becomes active before deletion, it is skipped. A per-document exception is logged and does not abort the rest of the batch.

## 6. E2E proof

The existing restart/lifecycle script was extended rather than adding another workflow.

Automation E2E proves:

```text
repository default retention is off
core uploads made under default config have DeleteAt == null
explicit test retention can be enabled through environment variables
new upload receives non-null future DeleteAt
that upload still processes normally
restart recovery still works
original PDF streaming still works
explicit delete lifecycle still works
expired Processed document is automatically removed
expired Processed backing PDF is automatically removed
expired Uploaded document is not removed
future Processed document is not removed
```

The retention test uses a 1-second sweep interval only in the E2E process. Production defaults remain one hour and disabled.

## 7. Schema / migration impact

No database migration was required. `DeleteAt` already existed and was already nullable in the `Documents` table/model.

No new index was added in this milestone. If retention volume becomes large, measure the candidate query first and add an index based on actual database behavior rather than preemptively changing the schema.

## 8. Reliability boundary

Retention follows the existing single-instance MVP architecture:

```text
PostgreSQL state
+ one application instance
+ startup processing recovery
+ in-memory Channel<Guid>
+ bounded processing retries
+ periodic retention sweep
+ row-locked terminal deletion
```

Do not describe this as distributed scheduling or multi-instance retention ownership.

## 9. Explicit non-goals

Still not implemented:

- per-tenant retention policy;
- legal hold;
- soft delete/tombstones;
- retention admin API;
- distributed scheduler/leases;
- S3/object-storage lifecycle;
- human reviewer identity;
- OCR/extraction changes.

## 10. CI discipline

Continue:

- docs/intermediate changes -> `[skip ci]`;
- normal API/domain/persistence/lifecycle change -> `.NET CI` + Automation E2E;
- Deployment Smoke only for Docker/compose/health changes;
- Scanned OCR E2E only for OCR/extraction-runner changes;
- Public Reference Benchmark only for extraction-rule changes.

## 11. Recommended next gap

The strongest remaining narrow product/audit gap is **reviewer identity / review audit attribution**.

Current `DocumentReview` captures corrected JSON, note and `ReviewedAt`, but no authenticated human reviewer identity.

Important constraint: the existing API-key principal identifies a tenant/integration client. It must not be renamed or represented as a human reviewer without a real identity requirement and authentication model.
