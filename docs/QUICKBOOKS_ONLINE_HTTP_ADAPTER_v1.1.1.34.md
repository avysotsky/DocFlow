# DocFlow v1.1.1.34 — QuickBooks Online HTTP Adapter

Status: **HTTP ADAPTER VALIDATED / OAUTH IMPLEMENTED LATER IN THIS MILESTONE**

The OAuth/token subsystem described as missing below was subsequently implemented and locally validated. See `QUICKBOOKS_ONLINE_OAUTH_v1.1.1.34.md` for the current capability boundary.

Branch:

```text
DocFlow/v_1.1.1.34_AccountingPosting
```

Validated code head:

```text
bb6e68e5bebb6319a8d5886bc8a5a919ecdf1c19
```

## What this slice adds

DocFlow now contains a QuickBooks Online accounting adapter behind the existing:

```text
IAccountingPostingAdapter
```

contract.

Provider name:

```text
quickbooks-online
```

The adapter uses the already validated:

```text
accounting_bill_v1
-> QuickBooksOnlineBillRequestBuilder
-> QBO Bill JSON
```

mapping pipeline.

## HTTP contract

The adapter posts to:

```text
POST {BaseUrl}/v3/company/{realmId}/bill
```

Supported official base URLs:

```text
https://sandbox-quickbooks.api.intuit.com
https://quickbooks.api.intuit.com
```

The internal accounting target account currently supplies the QBO realm/company id.

Requests include:

- Bearer authorization;
- `Accept: application/json`;
- `Content-Type: application/json`;
- deterministic Bill JSON from the provider mapping layer.

A successful response must contain:

```json
{
  "Bill": {
    "Id": "<qbo-bill-id>"
  }
}
```

The QBO Bill id becomes DocFlow's accounting posting `ExternalReference`.

## Access-token boundary

The adapter depends on:

```text
IQuickBooksOnlineAccessTokenProvider
```

with tenant + target-key context.

No production implementation is registered yet.

This is intentional: static long-lived bearer tokens are not treated as a production OAuth solution, and DocFlow does not claim live QBO connectivity at this stage.

## Error handling

QBO `Fault.Error[]` responses are normalized into DocFlow posting errors.

Permanent failures include ordinary client/mapping responses such as:

```text
400
403
404
409
422
```

Retryable transport/provider responses include:

```text
401
408
425
429
5xx
```

A successful HTTP response without a QBO Bill id is treated as retryable rather than falsely marked `Posted`.

Transport failures, request timeouts and response-body timeouts are retryable.

## Provider-directed retry

`AccountingPostingAdapterResult` now carries optional:

```text
RetryAfterSeconds
```

The durable posting state machine uses the longer of:

- DocFlow's exponential retry delay;
- provider-requested retry delay;

bounded by the configured maximum retry interval.

For QBO `429 Too Many Requests`:

- an HTTP `Retry-After` value is honored when supplied;
- otherwise the adapter requests a 60-second retry delay.

## HTTP configuration

Configuration:

```json
{
  "AccountingPosting": {
    "QuickBooksOnline": {
      "Http": {
        "BaseUrl": "https://sandbox-quickbooks.api.intuit.com",
        "RequestTimeoutSeconds": 30
      }
    }
  }
}
```

Startup validation requires:

- an absolute HTTPS URL;
- an official Intuit API host;
- timeout from 1 through 120 seconds.

The configuration does not contain an `Enabled` flag because the HTTP adapter must not appear live before a real OAuth token provider is installed.

## Automated validation

Latest unit/build gate:

```text
.NET CI
run: 37441262138
result: SUCCESS
```

Tests validate:

- QBO Bill POST URL and realm id;
- bearer-token propagation;
- request JSON;
- successful `Bill.Id` extraction;
- QBO ValidationFault -> permanent failure;
- HTTP 401/408/429/5xx retry classification;
- default 60-second QBO throttling delay;
- explicit `Retry-After` handling;
- no HTTP call after deterministic mapping failure;
- success response without Bill id -> retryable failure;
- provider retry delay propagation through the durable posting execution policy.

Full regression gate:

```text
Automation E2E
run: 37441128450
result: SUCCESS
```

Existing ingestion, extraction, accounting-posting worker, tenant isolation, IMAP and restart-recovery scenarios remain green.

## Remaining production gap

The HTTP transport exists, but the adapter is not registered for live posting because OAuth is not complete.

Next production-critical work:

1. persistent QBO connection entity per tenant/target;
2. authorization-code callback flow;
3. encrypted refresh-token storage;
4. refresh-token rotation;
5. access-token provider implementation;
6. live adapter registration;
7. real Intuit sandbox Bill creation;
8. unknown-outcome recovery test.

The last item is important. If QBO accepts a Bill but DocFlow loses the response before persisting the external Bill id, a retry must not silently create a duplicate. That behavior must be proven against the real sandbox before live QBO posting can be considered complete.
