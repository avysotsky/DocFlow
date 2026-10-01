# DocFlow — handoff v1.1.1.11 ApiKeyAuth

Status: **ACTIVE**  
Repository: `avysotsky/DocFlow`  
Branch: `DocFlow/v_1.1.1.11_ApiKeyAuth`  
Base: `DocFlow/v_1.1.1.10_DocumentReview`

## 1. Why this milestone exists

The current API already stores `Document.CustomerId` and the document inbox is customer-scoped, but the customer identity is supplied by the caller in request data. Other document endpoints accept only a `documentId` and do not verify tenant ownership.

That means tenant isolation is not yet an authentication/authorization boundary.

This milestone closes that MVP product gap before adding more extraction rules or UI features.

## 2. Scope

Implement a minimal provider-agnostic API-key authentication boundary for customer-facing document APIs.

Target behavior:

```text
X-DocFlow-Api-Key
  -> authenticate configured API client
  -> trusted customer_id claim
  -> document upload/list/read/process/result/review/export
     are limited to that customer
```

Rules:

- `CustomerId` is derived from authenticated identity, not accepted as authoritative request input.
- Cross-tenant access by `documentId` returns `404` so resource existence is not disclosed.
- Missing/invalid API key returns `401`.
- API keys are configuration/secrets, never committed with real values.
- Multiple configured API clients/customers are supported.
- No user/password system, OAuth/OIDC provider, refresh tokens, UI login, RBAC administration, or customer-management UI in this milestone.
- An API-key client identifies a tenant/client integration, not necessarily an individual human reviewer. Do not fabricate `ReviewedBy` from it.

## 3. Planned implementation block

1. Add API-key authentication handler/options/claims helper in `DocFlow.Api`.
2. Register authentication + authorization in `Program.cs`.
3. Protect document, export, and review controllers with `[Authorize]`.
4. Remove request-supplied `CustomerId` from upload/list as the ownership source.
5. Add tenant ownership filters for id-based reads/actions.
6. Update Automation E2E and its helper scripts to send API keys and verify:
   - unauthenticated request -> `401`;
   - primary tenant sees only its documents;
   - primary tenant cannot read another tenant document -> `404`;
   - second tenant can read its own document;
   - existing upload/process/export/review flows remain green.
7. Run one Automation E2E validation at the end of the block.

## 4. Configuration contract

Expected configuration shape:

```json
{
  "Authentication": {
    "ApiKey": {
      "HeaderName": "X-DocFlow-Api-Key",
      "Clients": [
        {
          "Name": "customer-a",
          "CustomerId": "11111111-1111-1111-1111-111111111111",
          "ApiKey": "<secret>"
        }
      ]
    }
  }
}
```

Repository `appsettings.json` must not contain real API keys. Runtime secrets should come from environment variables, user-secrets, or a production secret store.

## 5. Out of scope / later hardening

- OIDC/Auth0/Entra/Keycloak integration;
- end-user accounts and password lifecycle;
- per-user review audit identity;
- API-key provisioning/rotation endpoints;
- roles/permissions beyond tenant ownership;
- rate limiting;
- moving internal processing callbacks to a separate service-auth policy.

## 6. Validation discipline

Follow the existing project rule: batch the implementation and run the narrowest relevant workflow once. Do not run Public Reference Benchmark or Scanned OCR E2E because extraction/OCR behavior is unchanged.
