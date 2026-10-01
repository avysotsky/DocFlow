# DocFlow — handoff v1.1.1.18 Review Audit Identity

Status: **COMPLETED**  
Repository: `avysotsky/DocFlow`  
Branch: `DocFlow/v_1.1.1.18_ReviewAuditIdentity`  
Base: `DocFlow/v_1.1.1.17_RetentionPolicy`

## 1. Milestone result

`v1.1.1.18` adds authenticated **API-client audit attribution** to document reviews without pretending that an integration/API-key identity is a human reviewer.

Main implementation commit:

```text
9a2795f2699c32097e1318b3d415166a19834c2e
Add authenticated client attribution to document reviews
```

Validation:

```text
.NET CI #31
run id: 36881312537
result: success

Automation E2E #107
run id: 36881312573
result: success
```

Only those two relevant workflows ran. Deployment Smoke, Scanned OCR E2E and Public Reference Benchmark were not triggered.

## 2. Identity semantics

The API-key authentication handler now emits a dedicated trusted claim:

```text
docflow:client_name
```

It is populated from the configured API client `Name`, falling back to that client's trusted customer id when no name is configured.

`ClaimsPrincipalExtensions.GetRequiredClientName()` is used by the review endpoint. Review attribution does not come from request JSON.

This value means **authenticated client/integration identity**. It is not a named human identity.

## 3. Persisted review attribution

`DocumentReview` now contains:

```text
ReviewedByClient
```

New reviews require a non-empty client attribution and limit it to 200 characters.

Migration:

```text
20261001150500_AddDocumentReviewClientAttribution
```

The database column is nullable deliberately. Reviews created before this milestone have no trustworthy client attribution and are left as `NULL`; the migration does not fabricate historical audit data.

## 4. API / effective-data behavior

Successful `PUT /api/documents/{id}/review` returns `ReviewedByClient`.

`GET /api/documents/{id}/extraction-result` now returns nullable `ReviewedByClient` at the review metadata level.

Reviewed effective structured data includes:

```json
{
  "human_review": {
    "review_id": "...",
    "reviewed_at": "...",
    "reviewed_by_client": "customer-client-name",
    "note": "..."
  }
}
```

Because exports use the effective structured data, CSV/XLSX include the audit path as well.

## 5. Caller spoofing protection

The review request DTO still exposes only:

```text
ExpectedExtractionResultId
Data
Note
```

Automation E2E deliberately sends an extra JSON property:

```json
"reviewedByClient": "spoofed-human"
```

The authenticated test client is configured as `e2e-primary`. The runtime test verifies the persisted/returned/exported attribution is `e2e-primary`, not `spoofed-human`.

## 6. Preserved behavior

The existing review contract remains intact:

```text
tenant ownership enforced
stale extraction result -> 409
malformed corrected data -> 400
one review per document
non-reviewable document -> 409
successful NeedsReview correction -> Processed
effective corrected data returned/exported
```

Restart recovery, original-PDF access, explicit deletion and retention regression coverage also remained green in Automation E2E #107.

## 7. Explicit boundary

This milestone does **not** add:

- human user accounts;
- OIDC/Auth0/Entra/Keycloak;
- roles/RBAC;
- human reviewer names supplied in request data;
- an assertion that an API client corresponds to a person.

If the commercial workflow requires named-human accountability, design a real user authentication boundary rather than renaming `ReviewedByClient`.

## 8. CI discipline

Continue sparse CI:

- documentation/intermediate maintenance -> `[skip ci]`;
- coherent API/domain/persistence changes -> `.NET CI` + Automation E2E;
- Deployment Smoke only for deployment/health/container changes;
- Scanned OCR E2E only for OCR/extraction-runner changes;
- Public Reference Benchmark only for extraction-rule changes.

## 9. Next direction

The strongest narrow next candidate is **operational metrics / observability**. Inspect current structured logging, processing queue visibility, retry/failure state, retention sweep and health endpoints first.

Useful measurements may include processing outcomes, failures/retries, pending queue depth, review count and retention cleanup outcomes, but do not install a broad telemetry stack solely for architecture completeness.

Other later candidates: per-tenant retention settings, batch intake, explicit API versioning/deprecation of `StorageKey`, and real human IAM if customer requirements justify it.
