# DocFlow v1.1.1.34 — QuickBooks Online OAuth Connection

Status: **LOCAL END-TO-END VALIDATED / REAL INTUIT SANDBOX STILL REQUIRED**

Branch:

```text
DocFlow/v_1.1.1.34_AccountingPosting
```

Validated product-code head:

```text
46f9c97399b3e3c1ce898b41e4d4eec72cd2c7d2
```

Final local OAuth/QBO E2E workflow head:

```text
28dcb4809e3e9b975d9f2864f5416e5b45276d05
```

## Implemented OAuth flow

DocFlow now supports the QuickBooks Online authorization-code lifecycle:

```text
authenticated tenant
-> POST authorize target
-> random one-time state
-> Intuit authorization URL
-> anonymous callback
-> authorization-code token exchange
-> encrypted connection persistence
-> access-token refresh / refresh-token rotation
-> QBO accounting adapter
```

Authorization endpoint:

```text
POST /api/accounting-connections/quickbooks-online/targets/{targetKey}/authorize
```

Callback:

```text
GET /api/accounting-connections/quickbooks-online/callback
```

Connection status:

```text
GET /api/accounting-connections/quickbooks-online/targets/{targetKey}
```

Public connection responses expose neither OAuth tokens nor the QBO realm id.

## OAuth state security

Authorization state is generated from 32 cryptographically random bytes.

DocFlow persists only:

```text
SHA-256(state)
```

together with:

- CustomerId;
- TargetKey;
- CreatedAt;
- ExpiresAt;
- ConsumedAt.

The raw state exists only in the authorization URL returned to the caller.

State records are:

- short-lived;
- single-use;
- atomically marked consumed before token exchange;
- rejected after expiry;
- periodically cleaned when new authorization flows begin.

## Realm binding

The callback `realmId` must exactly match the server-side accounting target's internal target account.

This prevents an OAuth callback from silently connecting a configured target to an unexpected QBO company.

## Token storage

QBO tokens are stored in:

```text
QuickBooksOnlineConnections
```

per:

```text
CustomerId + TargetKey
```

Persisted data includes:

- realm id;
- encrypted access token;
- access-token expiry;
- encrypted refresh token;
- refresh-token expiry;
- connected / updated timestamps;
- disconnected timestamp.

Tokens are protected with ASP.NET Core Data Protection using the purpose:

```text
DocFlow.QuickBooksOnline.OAuthTokens.v1
```

When OAuth is enabled, a persistent Data Protection key-ring path is mandatory. This prevents encrypted refresh tokens from becoming unreadable after process restart.

## Refresh-token rotation

`QuickBooksOnlineAccessTokenProvider` returns the stored access token while it is outside the configured refresh-skew window.

When refresh is required it:

1. starts a database transaction;
2. locks the tenant/target QBO connection row using PostgreSQL `FOR UPDATE`;
3. decrypts the current refresh token;
4. calls the Intuit token endpoint;
5. stores the newly returned access token;
6. stores the latest returned refresh token;
7. updates both expiry timestamps;
8. commits the transaction;
9. returns the new access token.

The row lock prevents concurrent workers from racing refresh-token rotation for the same QBO connection.

An `invalid_grant` refresh response marks the connection disconnected rather than retrying the stale refresh token indefinitely.

A new OAuth authorization can reconnect the same target and replace realm/tokens safely.

## Intuit OAuth contract

Default endpoints:

```text
Authorization:
https://appcenter.intuit.com/connect/oauth2

Token:
https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer
```

Required accounting scope:

```text
com.intuit.quickbooks.accounting
```

The token client supports:

```text
grant_type=authorization_code
grant_type=refresh_token
```

and authenticates the app to the token endpoint using HTTP Basic client credentials.

DocFlow stores the latest refresh token returned by refresh, as required for QBO refresh-token rotation.

## Production endpoint safety

Outside Development:

- OAuth token endpoint must be the official Intuit token host;
- QBO API base URL must be an official Intuit API host;
- redirect URI must be HTTPS;
- development endpoint overrides cannot be enabled;
- persistent Data Protection key-ring path is required when OAuth is enabled.

Development has an explicit opt-in override for local fake endpoints used only by automated tests.

## Local full-path E2E

The CI fake Intuit server implements:

- authorization-code token exchange;
- refresh-token exchange;
- refresh-token rotation;
- QBO Bill POST;
- deterministic Bill response;
- stable provider `requestid` handling;
- commit-with-lost-response simulation;
- replay of the same provider request without creating a second logical Bill.

The full E2E proves:

```text
authorize endpoint
-> hashed state persisted
-> callback
-> token exchange
-> encrypted token persistence
-> connection status without realm/token leakage
-> access token considered near expiry
-> refresh token exchange
-> rotated refresh token encrypted
-> refreshed bearer token used
-> POST QBO Bill with stable requestid derived from DocFlow posting id
-> Bill.Id -> ExternalReference
-> DocFlow replay returns existing posting
-> no duplicate QBO Bill HTTP call
-> simulated provider commit followed by lost network response
-> posting returns to Pending
-> worker retries the same posting with the same requestid
-> fake provider returns the already-created Bill
-> DocFlow records the existing Bill.Id
```

The fake server additionally validates:

- OAuth Basic client credentials;
- authorization-code grant;
- refresh-token grant;
- bearer token after refresh;
- mapped VendorRef;
- mapped APAccountRef;
- expected invoice DocNumber.

## Validation

Latest .NET gate covering OAuth source and unit tests:

```text
.NET CI
run: 37455415360
result: SUCCESS
```

Final full local integration gate:

```text
Automation E2E
run: 37455593991
result: SUCCESS
```

The same E2E also keeps the existing ingestion, extraction, mailbox, accounting-posting worker and restart-recovery scenarios green.

## Capability boundary

Implemented and locally validated:

```text
supplier invoice
-> accounting_bill_v1
-> QBO mappings
-> OAuth connection
-> encrypted tokens
-> token refresh / rotation
-> QBO HTTP Bill adapter
-> provider response
-> ExternalReference
```

Locally proven for unknown outcomes:

- every QBO Bill POST carries a stable provider `requestid` derived from the immutable DocFlow posting id;
- a retry of the same durable posting reuses the same `requestid`;
- the fake provider can commit a Bill and intentionally drop the HTTP response;
- DocFlow treats that transport loss as retryable;
- the background worker retries the same posting;
- the fake provider returns the already-created Bill for the repeated `requestid`;
- DocFlow finishes as `Posted` with two attempts and one logical provider Bill.

Still not proven against Intuit:

- real Intuit user authorization;
- real Intuit sandbox token exchange;
- real QBO sandbox Bill creation;
- actual sandbox vendor/account/tax ids;
- that QBO v3 Bill create honors `requestid` with the same duplicate-suppression semantics modeled by the local fake provider.

Therefore do not claim production-ready or live QuickBooks Online integration yet.

## Next milestone slice

The next step is no longer another internal abstraction.

Use a real Intuit sandbox:

1. create/configure an Intuit development app;
2. configure its redirect URI;
3. provide Development client id/client secret through secrets, not source control;
4. connect one sandbox company through the DocFlow authorize endpoint;
5. populate real sandbox vendor/AP/expense/tax mappings;
6. create one sandbox Bill through DocFlow;
7. verify returned Bill id in both DocFlow and QBO;
8. repeat the same QBO create using the same provider `requestid` and verify Intuit returns/reconciles the same logical Bill rather than creating a duplicate;
9. simulate a lost-response/unknown-outcome case in sandbox before calling the integration production-ready.
