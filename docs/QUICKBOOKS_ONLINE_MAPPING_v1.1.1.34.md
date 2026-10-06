# DocFlow v1.1.1.34 — QuickBooks Online Bill Mapping

Status: **MAPPING LAYER VALIDATED / NO LIVE QBO HTTP YET**

Branch:

```text
DocFlow/v_1.1.1.34_AccountingPosting
```

Validated code head:

```text
d4b4d39821ab4bd635b763fc27596ad5f65fe197
```

## Purpose

This slice adds the provider-specific mapping boundary between DocFlow's stable:

```text
accounting_bill_v1
```

payload and the JSON shape required to create a QuickBooks Online Bill.

It deliberately does **not** perform OAuth or HTTP calls.

## Provider mapping configuration

Configuration section:

```text
AccountingPosting:QuickBooksOnline
```

Mappings are tenant + target scoped and contain:

- CustomerId;
- TargetKey;
- QuickBooks AP account id;
- default expense account id;
- supplier name -> QBO vendor id;
- optional SKU -> QBO expense account id;
- tax rate -> QBO tax-code id.

The existing generic accounting target still owns the internal provider target account / future realm id.

## Mapping rules

A canonical bill is converted to a QBO Bill request with:

```text
SupplierName   -> VendorRef.value
InvoiceNumber  -> DocNumber
InvoiceDate    -> TxnDate
DueDate        -> DueDate
Currency       -> CurrencyRef.value
Notes          -> PrivateNote

configured AP account
               -> APAccountRef.value

line SKU mapping
               -> AccountBasedExpenseLineDetail.AccountRef.value

fallback expense account
               -> AccountBasedExpenseLineDetail.AccountRef.value

invoice tax rate
               -> AccountBasedExpenseLineDetail.TaxCodeRef.value
```

Every canonical source line becomes an:

```text
AccountBasedExpenseLineDetail
```

QBO line.

Line amount precedence:

1. canonical `LineTotal`;
2. otherwise `Quantity * UnitPrice`;
3. apply line discount rate when the amount is calculated;
4. reject a line that cannot produce a positive posting amount.

## Deterministic failures

The builder returns explicit mapping failures for:

- unknown tenant/target mapping;
- supplier without a vendor mapping;
- tax rate without a tax-code mapping;
- invalid/missing line posting amount.

No outbound provider request is attempted in this slice.

## QuickBooks request JSON

Provider reference objects serialize in Intuit's expected form:

```json
{
  "VendorRef": {
    "value": "vendor-41"
  },
  "APAccountRef": {
    "value": "ap-33"
  }
}
```

Top-level QuickBooks object names preserve their API casing while reference `value` is lower-case.

## Validation

Latest successful gates:

```text
.NET CI
run: 37438654649
result: SUCCESS
```

The unit suite validates:

- supplier -> VendorRef;
- AP account mapping;
- SKU-specific expense account mapping;
- default expense account fallback;
- tax rate -> TaxCodeRef;
- invoice number, dates and currency;
- calculated discounted line amount;
- exact QBO reference JSON casing;
- unmapped vendor failure;
- unmapped tax failure;
- unknown tenant target failure.

Full application regression gate:

```text
Automation E2E
run: 37438597097
result: SUCCESS
```

The pre-existing processing, accounting-posting and restart-recovery scenarios remain green with the QBO mapping layer registered.

## Capability boundary

Implemented:

```text
DocFlow supplier invoice
-> accounting_bill_v1
-> tenant QBO mappings
-> deterministic QBO Bill request model / JSON
-> QBO HTTP adapter implementation
-> POST /v3/company/{realmId}/bill
-> response/fault parsing
-> retryable/permanent HTTP classification
-> provider-directed Retry-After propagation
```

The HTTP adapter is intentionally **not registered as a live provider** yet. It depends on `IQuickBooksOnlineAccessTokenProvider`, for which no production OAuth/token-storage implementation exists in this milestone.

Not implemented yet:

- Intuit OAuth 2.0 authorization flow;
- encrypted access/refresh token storage;
- refresh-token rotation;
- live adapter registration;
- real QBO sandbox request;
- provider-side recovery after an unknown-outcome POST;
- vendor/account/tax discovery from QBO;
- automatic creation of missing provider entities.

Do not claim live QuickBooks Online integration until a real QBO sandbox request has succeeded.

## Recommended next slice

Add the OAuth connection/token subsystem and only then register `QuickBooksOnlineAccountingAdapter` as an `IAccountingPostingAdapter`.

Recommended sequence:

1. durable tenant/target QBO connection record;
2. encrypted refresh-token storage;
3. OAuth authorization/callback flow;
4. access-token refresh provider implementing `IQuickBooksOnlineAccessTokenProvider`;
5. live adapter registration for connected targets;
6. sandbox Bill POST;
7. verify recovery/idempotency behavior for the case where QBO accepts a Bill but DocFlow loses the response.
