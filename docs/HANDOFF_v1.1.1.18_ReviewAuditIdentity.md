# DocFlow — handoff v1.1.1.18 Review Audit Identity

Status: **ACTIVE**  
Repository: `avysotsky/DocFlow`  
Branch: `DocFlow/v_1.1.1.18_ReviewAuditIdentity`  
Base: `DocFlow/v_1.1.1.17_RetentionPolicy`

## Why this milestone exists

`DocumentReview` records corrected data, note and timestamp, but not the authenticated client that submitted the review. The current API-key principal identifies a tenant/integration client, not necessarily a human user.

## Scope

Keep `v1.1.1.18` semantically narrow:

1. Persist authenticated API client attribution as `ReviewedByClient` on new reviews.
2. Never accept review attribution from request JSON.
3. Do not call the value `ReviewedBy` or claim it identifies a human reviewer.
4. Preserve historical review rows by making the new database column nullable; do not backfill invented attribution.
5. Return `ReviewedByClient` in review/extraction responses and reviewed structured data/export.
6. Keep tenant ownership, stale-result protection and one-review-per-document behavior unchanged.
7. Extend existing Automation E2E review coverage.

## Identity semantics

The source is the authenticated API-key principal `NameIdentifier`, currently produced from the configured API client `Name` (falling back to customer id when no client name is configured).

This milestone provides **client audit attribution**, not human IAM.

## Non-goals

Do not add user/password accounts, OIDC, RBAC, reviewer display names supplied by callers, or claim that an API client equals a person.

## Acceptance

```text
new review persists ReviewedByClient from authenticated principal
review response exposes ReviewedByClient
GET extraction-result exposes reviewedByClient
human_review.reviewed_by_client is included in effective data/export
historical reviews remain valid with null attribution
request payload cannot choose attribution
.NET CI + Automation E2E green
```
