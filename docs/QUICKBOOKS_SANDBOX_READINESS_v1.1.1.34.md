# DocFlow v1.1.1.34 — QuickBooks Online Sandbox Readiness

Status: **SANDBOX BOOTSTRAP READY / REAL INTUIT SANDBOX EXECUTION STILL REQUIRED**

## Purpose

This package prepares DocFlow for a real QuickBooks Online sandbox without committing Intuit credentials or provider ids to git.

The bootstrap is intentionally split into two phases:

```text
Phase 1
OAuth connection + read-only reference discovery

Phase 2
Posting mappings + first sandbox Bill
```

This avoids the circular requirement of knowing QBO Vendor/AP/Expense/Tax ids before DocFlow can connect to the sandbox that owns those ids.

## Files

```text
.env.example
compose.quickbooks-sandbox.yaml
compose.quickbooks-sandbox-posting.yaml
scripts/quickbooks_sandbox_probe.py
```

The repository ignores:

```text
.env
.env.*
appsettings.Development.local.json
```

except the committed `.env.example` template.

Never commit a real Intuit Client Secret, access token or refresh token.

## Phase 1 — configure sandbox connection

Copy:

```text
.env.example
-> .env
```

Set at least:

```text
DOCFLOW_POSTGRES_PASSWORD
DOCFLOW_API_KEY
DOCFLOW_CUSTOMER_ID

DOCFLOW_QBO_ENABLED=true
DOCFLOW_QBO_TARGET_KEY=qbo-sandbox
DOCFLOW_QBO_REALM_ID=<sandbox company realm id>
DOCFLOW_QBO_CLIENT_ID=<Intuit development client id>
DOCFLOW_QBO_CLIENT_SECRET=<Intuit development client secret>
DOCFLOW_QBO_REDIRECT_URI=https://<public-host>/api/accounting-connections/quickbooks-online/callback
```

The configured realm id is a safety binding. The realm returned by the OAuth callback must match `DOCFLOW_QBO_REALM_ID`.

The redirect URI must be the same HTTPS callback registered in the Intuit development app.

Start DocFlow with the connection/discovery overlay:

```bash
docker compose \
  -f compose.yaml \
  -f compose.quickbooks-sandbox.yaml \
  up -d --build
```

This overlay:

- registers a tenant QBO target;
- enables QBO OAuth;
- uses Intuit sandbox API;
- persists ASP.NET Data Protection keys in a Docker volume;
- does not require Vendor/AP/Expense/Tax mappings yet.

## Start OAuth authorization

Request an authorization URL:

```bash
curl -sS \
  -H "X-DocFlow-Api-Key: <DOCFLOW_API_KEY>" \
  -X POST \
  http://127.0.0.1:8080/api/accounting-connections/quickbooks-online/targets/qbo-sandbox/authorize
```

The response contains:

```json
{
  "authorizationUrl": "https://appcenter.intuit.com/connect/oauth2?...",
  "expiresAt": "..."
}
```

Open `authorizationUrl` in a browser and authorize the configured sandbox company.

Intuit redirects to the DocFlow callback. DocFlow then:

1. validates the one-time OAuth state;
2. verifies the returned realm id;
3. exchanges the authorization code;
4. encrypts access and refresh tokens;
5. persists the connection.

## Check connection status

```bash
curl -sS \
  -H "X-DocFlow-Api-Key: <DOCFLOW_API_KEY>" \
  http://127.0.0.1:8080/api/accounting-connections/quickbooks-online/targets/qbo-sandbox
```

The public response does not expose:

- realm id;
- access token;
- refresh token.

## Read-only provider reference discovery

Endpoint:

```text
GET /api/accounting-connections/quickbooks-online/targets/{targetKey}/references
```

It queries the connected QBO company for:

- Vendor;
- Account;
- TaxCode.

The response exposes only mapping-safe provider metadata.

Example shape:

```json
{
  "vendors": [
    {
      "id": "41",
      "displayName": "Supplier Name",
      "active": true
    }
  ],
  "accounts": [
    {
      "id": "33",
      "name": "Accounts Payable",
      "fullyQualifiedName": "Accounts Payable",
      "accountType": "Accounts Payable",
      "accountSubType": "AccountsPayable",
      "active": true
    }
  ],
  "taxCodes": [
    {
      "id": "TAX",
      "name": "VAT / tax code",
      "active": true
    }
  ]
}
```

A tenant cannot discover references for another tenant's QBO connection.

## Read-only probe command

Run:

```bash
python scripts/quickbooks_sandbox_probe.py \
  --base-url http://127.0.0.1:8080 \
  --api-key "<DOCFLOW_API_KEY>" \
  --target-key qbo-sandbox
```

The script performs no accounting writes.

It prints:

- connection state;
- active vendors;
- active accounts;
- active tax codes;
- current posting-mapping validation result.

During Phase 1, `mappingValidation.isValid` is expected to be false with `mapping_not_configured` because the posting overlay has not been enabled yet.

Use the reference output to select the real provider ids.

## Mapping selection

Choose:

### Vendor

Match the supplier used by the DocFlow canonical invoice to the intended QBO Vendor id.

```text
DOCFLOW_QBO_VENDOR_NAME=<DocFlow supplier name>
DOCFLOW_QBO_VENDOR_ID=<QBO Vendor id>
```

### AP account

Choose the correct Accounts Payable account.

```text
DOCFLOW_QBO_AP_ACCOUNT_ID=<QBO AP Account id>
```

### Default expense account

Choose the account to use when no SKU-specific expense mapping exists.

```text
DOCFLOW_QBO_DEFAULT_EXPENSE_ACCOUNT_ID=<QBO Expense Account id>
```

### Tax code

Choose the actual QBO purchase tax code appropriate for the sandbox/company locale.

```text
DOCFLOW_QBO_TAX_RATE=20
DOCFLOW_QBO_TAX_CODE_ID=<QBO TaxCode id>
```

Do not infer tax semantics from the displayed name alone. QBO tax behavior differs by company locale/configuration. If the sandbox does not expose a tax model compatible with the current rate-to-tax-code mapping, stop before creating a Bill and adapt the mapping layer first.

## Phase 2 — enable posting mappings

After the provider ids have been selected, restart with the posting overlay:

```bash
docker compose \
  -f compose.yaml \
  -f compose.quickbooks-sandbox.yaml \
  -f compose.quickbooks-sandbox-posting.yaml \
  up -d --build
```

The posting overlay configures:

- tenant + target QBO mapping;
- AP account id;
- default expense account id;
- supplier -> Vendor id;
- tax rate -> TaxCode id.

SKU-specific expense mappings remain optional and can be added later.

## Validate configured mappings against QBO

After restarting with the posting overlay, validate the configured provider ids before creating any Bill:

```bash
curl -sS \
  -H "X-DocFlow-Api-Key: <DOCFLOW_API_KEY>" \
  http://127.0.0.1:8080/api/accounting-connections/quickbooks-online/targets/qbo-sandbox/mapping-validation
```

Expected result:

```json
{
  "isValid": true,
  "issues": []
}
```

Validation checks the live connected QBO company and rejects/warns through explicit issue codes when:

- configured AP account is missing, inactive or not Accounts Payable;
- default/SKU expense account is missing, inactive or not expense-like;
- configured Vendor id is missing or inactive;
- configured TaxCode id is missing or inactive;
- posting mappings are not configured;
- the QBO connection is unavailable.

Do not create the first sandbox Bill until `isValid` is true.

## First real sandbox Bill

Use a processed `supplier_invoice` document and a fresh idempotency key:

```bash
curl -sS \
  -H "X-DocFlow-Api-Key: <DOCFLOW_API_KEY>" \
  -H "Content-Type: application/json" \
  -X POST \
  -d '{
    "documentId": "<processed-document-id>",
    "targetKey": "qbo-sandbox",
    "idempotencyKey": "sandbox-bill-001"
  }' \
  http://127.0.0.1:8080/api/accounting-postings
```

Expected DocFlow result:

```text
status = Posted
provider = quickbooks-online
targetKey = qbo-sandbox
externalReference = <real QBO Bill id>
```

Then verify that the same Bill exists in the Intuit sandbox UI/API.

## Unknown-outcome check

DocFlow sends QBO Bill create requests with a stable provider `requestid` derived from the immutable DocFlow posting id.

Local E2E already proves:

```text
provider commits Bill
-> response is lost
-> DocFlow marks retryable
-> same posting is retried
-> same requestid is reused
-> fake provider returns same logical Bill
-> DocFlow becomes Posted
```

Before production use, reproduce equivalent behavior against the real Intuit sandbox and verify that repeated Bill creation with the same `requestid` does not create a second Bill.

## Automated validation

Reference-discovery + mapping-validation source/build gate:

```text
.NET CI
run: 37461121846
result: SUCCESS
```

Reference-discovery full integration gate:

```text
Automation E2E
run: 37460280316
result: SUCCESS
```

A newer full E2E additionally validates configured QBO mappings against the fake provider before Bill creation; record its run id in this document after that workflow completes.

The E2E proves:

- connected QBO tenant can query Vendor, Account and TaxCode;
- QBO access token is used for the queries;
- discovery results are normalized;
- another tenant receives 404 for the same target key;
- existing OAuth, token rotation, Bill posting, unknown-outcome recovery and restart scenarios remain green.

Deployment smoke validates both the base compose file and QBO sandbox overlays with placeholder secrets.

## Remaining external dependencies

DocFlow code no longer needs a new internal abstraction before sandbox testing.

The remaining requirements are external:

1. Intuit developer app;
2. sandbox company;
3. real development Client ID / Client Secret;
4. registered public HTTPS redirect URI;
5. known sandbox realm id;
6. one real OAuth authorization;
7. discovered real QBO mapping ids;
8. one real sandbox Bill;
9. real sandbox validation of repeated `requestid` behavior.
