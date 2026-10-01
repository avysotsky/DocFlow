# DocFlow — Next Chat Handoff After v1.1.1.11

Use this file as the starting state for the next DocFlow development chat.

## Repository state

Repository: `avysotsky/DocFlow`  
Completed branch: `DocFlow/v_1.1.1.11_ApiKeyAuth`  
Previous branch: `DocFlow/v_1.1.1.10_DocumentReview`

Main implementation commit:

```text
0c9bbd0197c61109400e4f8cda52dfb14bf59a47
Add tenant API-key authentication and authorization
```

Primary validation:

```text
Automation E2E #100
run id: 36851050242
result: success
```

Detailed milestone handoff:

```text
docs/HANDOFF_v1.1.1.11_ApiKeyAuth.md
```

## Current product state

DocFlow currently supports:

```text
API-key authenticated tenant
  -> PDF upload
  -> digital PDF or conditional Tesseract OCR
  -> invoice/quotation detection
  -> deterministic extraction
  -> arithmetic/business validation
  -> PostgreSQL persistence
  -> tenant-scoped document inbox
  -> human correction/review
  -> tenant-scoped CSV/XLSX export
```

Public-reference extraction baseline remains the previously measured baseline:

```text
17/17 public documents passed
98/98 checked business fields matched
17/17 document types correct
17/17 validation statuses correct
```

No extraction/OCR logic was changed in `v1.1.1.11`.

## Security boundary now in place

Customer-facing document endpoints require:

```text
X-DocFlow-Api-Key: <secret>
```

A configured API client maps to a trusted `docflow:customer_id` claim.

Rules:

- missing/invalid API key -> `401`;
- customer ownership comes from authenticated identity;
- request-supplied `CustomerId` is not authoritative;
- cross-tenant access by document id -> `404`;
- multiple API clients/customers are supported;
- production secrets must not be committed.

This is tenant/client authentication, not individual human identity. Per-reviewer audit identity is still unresolved.

## CI state and discipline

`Automation E2E #100` is green for `v1.1.1.11`.

The Scanned OCR E2E trigger was narrowed after this milestone so ordinary API/auth changes do not launch the expensive OCR workflow. Its API calls were also updated to use the API-key boundary for the next legitimate OCR run.

Continue to use CI sparingly:

- documentation/intermediate maintenance commits -> `[skip ci]`;
- batch coherent implementation work;
- run the narrowest relevant workflow once at the end;
- do not run Public Reference Benchmark or Scanned OCR E2E unless extraction/OCR behavior changed.

## Do not re-open already completed work without evidence

Do not spend the next milestone on speculative extraction rules, ONNX, or LLM fallback. Current measured failures have not justified that complexity.

Do not replace API-key auth with a large IAM stack unless a real deployment/customer requirement demands it.

## Next milestone selection

Select one concrete product/operational gap and create a new version branch, likely `v1.1.1.12`.

Best current candidates:

1. **Reviewer/audit identity** — individual identity and attribution for human review.
2. **Deployability/configuration** — production container/config/secrets plus health/readiness behavior.
3. **Observability/retries** — failure visibility, durable retry policy, processing diagnostics.
4. **Retention/delete** — customer-visible document lifecycle and deletion.
5. **Batch intake** — only if real workflow requires multiple documents per operation.

Before selecting, inspect the current code and pick the smallest gap that most improves a usable commercial MVP. Keep the milestone narrow and measurable.
