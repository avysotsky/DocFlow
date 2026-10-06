# DocFlow v1.1.1.34 — Accounting Posting Foundation

Status: **FOUNDATION VALIDATED**

Branch:

```text
DocFlow/v_1.1.1.34_AccountingPosting
```

Validated code head:

```text
a7f77b9c7c1459e59e9a79ec8e8ef6c5130fb1d6
```

## Completed in this slice

### Canonical accounting bill

Processed `supplier_invoice` documents are converted into a provider-neutral, versioned payload:

```text
accounting_bill_v1
```

The payload preserves:

- supplier name;
- invoice number;
- invoice date / due date;
- currency;
- customer / PO reference;
- normalized line items;
- invoice and line discounts;
- tax-inclusive flag;
- subtotal;
- tax rate;
- tax amount;
- grand total;
- tax breakdown;
- payment terms;
- notes.

Extraction-specific implementation details such as engine metadata, validation blocks and duplicate-check metadata are not passed to accounting adapters.

### Durable posting state

Accounting posting records persist:

- tenant;
- source document;
- provider;
- public target key;
- internal target account;
- idempotency key;
- canonical bill JSON;
- status;
- attempts;
- retry timestamps;
- last error;
- external provider reference.

The public API returns the tenant-safe target key and does not expose the internal provider account identifier.

### Idempotency

The durable uniqueness scope is:

```text
CustomerId + Provider + TargetAccount + IdempotencyKey
```

A true retry of the same request returns the existing posting. A reused key for a different document/payload returns conflict.

Persisted PostgreSQL `jsonb` is compared semantically rather than by raw JSON text, so property reordering by PostgreSQL does not turn a valid replay into a conflict.

### Tenant-scoped targets

Clients submit:

```json
{
  "documentId": "<id>",
  "targetKey": "primary-ledger",
  "idempotencyKey": "<stable-key>"
}
```

They cannot submit arbitrary provider realm/account ids.

Server-side configuration resolves:

```text
CustomerId + targetKey
-> provider
-> internal provider target account
```

Target discovery:

```text
GET /api/accounting-postings/targets
```

returns only public target keys and provider names for the authenticated tenant.

### Delivery / recovery

Posting delivery uses a provider adapter interface.

Current lifecycle:

```text
Pending -> Posting -> Posted
                  -> Pending (retryable failure)
                  -> Failed  (terminal failure)
```

The background worker processes due `Pending` records.

A stale `Posting` record is treated as an interrupted attempt and recovered for idempotent retry after `InProgressTimeoutSeconds`.

### Current adapter

`local-test` is deterministic and Development-only. It exists to prove the durable posting contract and recovery behavior.

It is not a real accounting-system integration.

## Validation

Latest successful gates for this slice:

```text
.NET CI
run: 37436553454
result: SUCCESS
```

```text
Automation E2E
run: 37436314071
result: SUCCESS
```

The E2E validates:

- database migrations;
- tenant target discovery;
- hidden internal target account;
- canonical bill persistence;
- successful posting;
- GET posting state;
- idempotent replay;
- conflict on reused idempotency key with a different request;
- cross-tenant isolation;
- background delivery of persisted Pending work;
- stale Posting recovery;
- all pre-existing document automation scenarios;
- application restart recovery.

## CI workflow improvement

`.NET CI` and `Automation E2E` now use branch-scoped GitHub Actions concurrency with `cancel-in-progress: true`. Superseded intermediate commits no longer build a long obsolete queue during active development.

## Not implemented yet

Do not claim these capabilities yet:

- QuickBooks Online adapter;
- Xero adapter;
- OAuth token acquisition/refresh;
- QBO realm configuration;
- Xero tenant/organization connection;
- supplier/vendor mapping to provider entity ids;
- expense/AP account mapping;
- tax-code mapping;
- live provider sandbox validation.

## Recommended next slice

The next implementation should add a provider-specific mapping layer behind the existing canonical bill boundary.

Recommended order:

1. provider target configuration model;
2. supplier/vendor mapping;
3. expense/AP account mapping;
4. tax-code mapping;
5. deterministic provider request builder tests;
6. HTTP adapter with token abstraction;
7. provider sandbox E2E only after credentials are available.

The canonical `accounting_bill_v1` contract should remain stable while provider-specific request models live behind the adapter boundary.
