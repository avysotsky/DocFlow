# DocFlow — handoff v1.1.1.11 ApiKeyAuth

Status: **COMPLETED**  
Repository: `avysotsky/DocFlow`  
Branch: `DocFlow/v_1.1.1.11_ApiKeyAuth`  
Base: `DocFlow/v_1.1.1.10_DocumentReview`

## 1. Milestone result

`v1.1.1.11` closes the MVP tenant/authentication gap that remained after the customer-scoped document inbox and review flow.

Before this milestone, `Document.CustomerId` existed in persistence but the caller supplied customer identity in request data, while several document-id endpoints did not verify tenant ownership. That was not a security boundary.

The customer-facing document API now uses this boundary:

```text
X-DocFlow-Api-Key
  -> configured API client
  -> trusted docflow:customer_id claim
  -> tenant-scoped document API
```

Implementation commit:

```text
0c9bbd0197c61109400e4f8cda52dfb14bf59a47
Add tenant API-key authentication and authorization
```

Validation:

```text
Automation E2E #100
GitHub Actions run 36851050242
conclusion: success
head: 0c9bbd0197c61109400e4f8cda52dfb14bf59a47
```

## 2. Implemented behavior

### Authentication

- Customer-facing document endpoints require `X-DocFlow-Api-Key`.
- Missing key -> `401`.
- Invalid key -> `401`.
- Multiple configured API clients/customers are supported.
- Keys are compared with a fixed-time comparison.
- Repository `appsettings.json` contains no real API keys.
- Runtime keys should come from environment variables, user-secrets, or a production secret store.

### Trusted tenant identity

Each configured API client maps to a `CustomerId`. Successful authentication creates the trusted claim:

```text
docflow:customer_id
```

Upload and inbox/list derive customer ownership from that claim. Request-supplied `CustomerId` is no longer authoritative.

### Tenant authorization

The following customer-facing operations are tenant-scoped:

```text
POST /api/documents
GET  /api/documents
GET  /api/documents/{id}
POST /api/documents/{id}/process
GET  /api/documents/{id}/extraction-result
POST /api/documents/{id}/extraction-result
PUT  /api/documents/{id}/review
GET  /api/documents/{id}/export
```

For id-based operations, a document belonging to another customer is treated as not found:

```text
cross-tenant document id -> 404
```

This avoids disclosing whether another tenant's resource exists.

## 3. Main code changes

### `DocFlow.Api`

Added:

```text
Authentication/ApiKeyAuthentication.cs
```

It contains:

- authentication scheme constants;
- API-key configuration models;
- API-key authentication handler;
- `docflow:customer_id` claim creation;
- `ClaimsPrincipal.GetRequiredCustomerId()` helper.

Updated:

```text
Program.cs
Controllers/DocumentsController.cs
Controllers/DocumentReviewsController.cs
Controllers/DocumentExportsController.cs
appsettings.json
```

`Program.cs` now registers authentication/authorization and runs both middleware components before controller mapping.

## 4. E2E coverage added

Automation E2E now proves all of the following in one workflow:

- unauthenticated document request -> `401`;
- invalid API key -> `401`;
- primary customer sees only primary-customer documents;
- adding a `customerId` query parameter cannot switch tenant identity;
- primary customer GET of another tenant's document -> `404`;
- second tenant can read its own document;
- second tenant's inbox is isolated;
- existing quotation/invoice processing remains functional;
- idempotent processing remains functional;
- `NeedsReview` and `Failed` routing remains functional;
- CSV/XLSX export remains functional;
- human review remains functional.

Updated E2E helpers authenticate all API requests:

```text
.github/scripts/verify_document_export.py
.github/scripts/verify_document_inbox.py
.github/scripts/verify_document_review.py
```

## 5. CI hygiene discovered during this milestone

The legacy `Scanned OCR E2E` path filter was broad enough that an API-auth-only change triggered the expensive OCR workflow even though OCR behavior was unchanged.

The closing maintenance commit narrows that workflow to extraction/processing/OCR-related files instead of all API/Application/Domain/Infrastructure files. It also authenticates the scanned E2E API calls so the workflow remains compatible with the new mandatory API-key boundary when it is legitimately triggered later.

Do not use Scanned OCR E2E as a validation gate for ordinary auth/API/UI work. Run it when the OCR/extraction processing path changes.

## 6. Deliberately out of scope

This is intentionally an MVP integration/tenant authentication boundary, not a full identity platform.

Still out of scope:

- OIDC/Auth0/Entra/Keycloak;
- end-user username/password accounts;
- refresh/access-token lifecycle;
- per-human reviewer identity;
- RBAC/permissions administration;
- API-key provisioning or rotation endpoints;
- rate limiting;
- service-to-service authentication policies separate from customer auth.

In particular, an API-key client represents a tenant/client integration, not necessarily an individual human reviewer. Do not populate `ReviewedBy` with the API client name and call that user-level audit identity.

## 7. Current MVP state after v1.1.1.11

DocFlow now has a coherent end-to-end MVP path:

```text
authenticated tenant
  -> upload PDF
  -> digital/OCR processing
  -> detect invoice/quotation
  -> deterministic extraction + validation
  -> persistence
  -> tenant-scoped inbox
  -> optional human review
  -> tenant-scoped CSV/XLSX export
```

## 8. Recommended next milestone selection

Do not automatically add more extraction rules without measured failures.

Choose the next block from an actual product/operational gap. Strong candidates are:

1. **Reviewer/audit identity** — if human review must be attributable to individual users.
2. **Deployability/configuration** — production container/config/secret setup and health/readiness behavior.
3. **Observability/retries** — durable failure visibility and controlled retry behavior.
4. **Retention/delete** — explicit document lifecycle and data deletion.
5. **Batch intake** — only if real customer workflow requires multi-document ingestion.

Preserve the CI discipline from the previous handoffs: make coherent implementation blocks, use `[skip ci]` for documentation/intermediate maintenance commits, and run the narrowest relevant validation once at the end.
