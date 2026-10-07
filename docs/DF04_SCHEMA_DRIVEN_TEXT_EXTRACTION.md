# DF-04 — Generic Schema-Driven Text Extraction

## State

HANDOFF_READY

## Repository / branch

```text
avysotsky/DocFlow
DocFlow/df04-schema-driven-text-extraction
```

## Baseline

```text
2bbb18d2d056e87f0616569e46b011bb0e31668d
```

Last production DocFlow CI before this docs-only baseline:

```text
37607059797 — SUCCESS
```

## Purpose

Implement the first reusable concrete text-extraction orchestration layer on top of the integrated DF-03 boundary.

Target flow:

```text
NormalizedTextDocument
+ caller-supplied generic JSON Schema
+ injected provider-neutral backend
-> backend structured data
-> deterministic JSON Schema validation
-> existing StructuredExtractionResult
```

DF-04 must remain completely domain-neutral.

It must not know about earnings, finance, trading, fiscal periods, tickers, revenue, EPS, guidance, TradeOps, or ResearchDecision.

## Architecture decision

DF-03 already established:

```text
NormalizedTextDocument
-> TextStructuredExtractionEngine
-> StructuredExtractionResult
```

DF-04 adds a concrete implementation of that abstraction.

Recommended design:

```text
SchemaDrivenTextExtractionRequest
SchemaDrivenTextExtractionBackend
SchemaDrivenTextExtractionBackendResult
SchemaDrivenTextExtractionEngine : TextStructuredExtractionEngine
```

Exact names may vary if the implementation has a clearer naming scheme, but the ownership and semantics must remain the same.

The concrete engine is an orchestrator.

It must not contain a provider-specific client.

The backend is injected.

A future provider-specific slice may implement the backend protocol using an external model/provider.

## Dependency

Use a standard JSON Schema validator rather than implementing JSON Schema manually.

Add a bounded runtime dependency:

```text
jsonschema>=4
```

Use JSON Schema Draft 2020-12 unless an existing repository constraint requires otherwise.

Do not add an LLM/provider SDK in DF-04.

## Request contract

Create a strict/frozen request model representing caller-owned extraction configuration.

Recommended semantics:

```text
SchemaDrivenTextExtractionRequest
  schema_name
  schema_version
  json_schema
```

Requirements:

- `schema_name` is required, normalized, single-line, non-empty;
- `schema_version` is a positive integer;
- `json_schema` is required;
- schema root must describe a JSON object;
- the schema itself must be valid for the selected JSON Schema draft;
- request model rejects unknown members;
- no prompt/instruction field in this slice;
- no provider/model name in the request;
- no domain-specific metadata bag.

The caller owns the schema semantics.

DocFlow only validates that it is a valid JSON Schema and uses it to validate backend output.

## Backend contract

Create a provider-neutral injected backend abstraction.

Recommended semantics:

```python
class SchemaDrivenTextExtractionBackend(ABC):
    @property
    def name(self) -> str:
        ...

    async def extract(
        self,
        content: NormalizedTextDocument,
        *,
        request: SchemaDrivenTextExtractionRequest,
        document_name: str | None = None,
    ) -> SchemaDrivenTextExtractionBackendResult:
        ...
```

Backend result should be narrow:

```text
data: dict[str, Any]
confidence: float | None
```

Requirements:

- `data` must be a JSON object;
- confidence, when supplied, must be in [0, 1];
- backend result rejects unknown members;
- backend result contains no DocFlow validation status;
- schema compliance is owned by the orchestration engine, not trusted from backend output.

Do not make backend return a `StructuredExtractionResult`; otherwise schema validation can be bypassed.

## Concrete engine

Create a concrete:

```text
SchemaDrivenTextExtractionEngine
```

that implements the existing:

```text
TextStructuredExtractionEngine
```

The engine should be configured with:

- one injected backend;
- one immutable schema-driven extraction request.

Its existing DF-03 method remains:

```python
async def extract(
    self,
    content: NormalizedTextDocument,
    *,
    document_name: str | None = None,
) -> StructuredExtractionResult:
    ...
```

Do not change the DF-03 abstract method signature.

## Engine name

Engine identity must be deterministic and must expose that this is the schema-driven text orchestrator plus the concrete backend identity.

Recommended stable form:

```text
schema_driven_text_v1:<backend-name>
```

Do not include clock values, request IDs, random values, schema hashes, or document-specific values in the engine name.

## Schema validation

After backend extraction, validate the returned `data` with the caller-supplied JSON Schema.

Validation must be deterministic.

Sort reported schema-validation errors deterministically, for example by JSON path and message.

Do not mutate backend data to make it pass.

Do not:

- add missing properties;
- remove unknown properties;
- coerce strings to numbers;
- infer values;
- normalize financial/domain values;
- inject domain defaults.

The caller schema determines whether a field is required or allowed.

## StructuredExtractionResult mapping

Always reuse the existing:

```text
StructuredExtractionResult
StructuredValidationResult
ValidationCheckResult
```

Do not create a second result or validation family.

For schema-valid backend data:

```text
engine            = concrete engine name
document_type     = content.document_type
data              = backend data unchanged
confidence        = backend confidence
validation_status = "valid"
validation.status = "valid"
```

The validation object should include a deterministic generic check such as:

```text
json_schema
```

with status `passed`.

For schema-invalid backend data:

- return the existing `StructuredExtractionResult`;
- preserve the backend data unchanged for audit;
- `validation_status = "invalid"`;
- `validation.status = "invalid"`;
- include deterministic validation error details;
- do not throw merely because extracted data does not satisfy the caller schema.

Invalid caller schema/configuration is a programming/configuration error and should fail before extraction.

Backend execution failure is also an exception and must not be silently converted to valid/incomplete data.

## Confidence

Backend confidence is audit metadata only.

DF-04 must not reinterpret it.

Do not derive schema validity from confidence.

Do not calculate trading/domain decisions from confidence.

## Input integrity

The engine consumes the already validated/frozen `NormalizedTextDocument`.

It must not:

- renormalize text;
- reorder segments;
- change participant associations;
- regenerate document ID;
- regenerate segment IDs;
- regenerate fingerprint;
- alter source timestamps;
- infer missing source metadata.

Pass the original `NormalizedTextDocument` instance to the injected backend.

## Provider/network boundary

DF-04 contains no concrete network/provider implementation.

Production engine orchestration itself must not:

- import OpenAI/Anthropic SDKs;
- construct HTTP clients;
- read API keys;
- read provider environment variables;
- choose a provider/model;
- retry network requests.

The injected backend protocol is where a later provider-specific implementation will attach.

Tests use only deterministic in-memory fake backends.

## No automatic identity injection

DF-04 must not inject fields such as:

- document_id;
- fingerprint;
- source;
- segment IDs;
- schema version;

into backend data unless those fields were actually returned by the backend.

Why: output data belongs to the caller-provided schema. Generic DocFlow orchestration must not silently change the caller's object shape.

The backend receives `NormalizedTextDocument`, so a future backend implementation may deterministically copy document/segment identity into schema fields when the caller schema requires them.

## No domain schema bundled in DocFlow

Do not commit an earnings schema, supplier-specific schema, or TradeOps schema as part of DF-04.

Tests must use a synthetic generic schema, for example:

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": ["category", "score"],
  "properties": {
    "category": {"type": "string"},
    "score": {"type": "number"}
  }
}
```

A second synthetic test schema may include segment IDs to prove that arbitrary caller-defined evidence structures pass unchanged, but names must remain generic.

## Explicitly out of scope

Do not implement in DF-04:

- OpenAI client;
- Anthropic client;
- Azure OpenAI client;
- local model client;
- model selection;
- provider retries;
- API keys;
- prompt templates/framework;
- prompt registry;
- schema registry;
- persistence;
- caching;
- HTTP API/CLI integration;
- TradeOps dependency;
- earnings logic;
- financial units;
- revenue/EPS/guidance;
- instrument/fiscal-period mapping;
- ResearchDecision;
- portfolio/backtest/execution;
- OCR changes;
- PDF engine refactor;
- supplier quotation refactor;
- transcript acquisition;
- speech-to-text;
- summarization;
- sentiment.

## Existing contracts to preserve

Do not modify incompatibly:

- `TextStructuredExtractionEngine`;
- `StructuredExtractionEngine`;
- `StructuredExtractionResult`;
- `StructuredValidationResult`;
- `ValidationCheckResult`;
- `NormalizedTextDocument`;
- DF-02 document/segment ID and fingerprint semantics;
- PDF extraction contracts;
- deterministic supplier-quotation engine.

Additive exports are allowed.

## Required tests

At minimum cover:

1. valid caller JSON Schema request is accepted;
2. invalid JSON Schema is rejected before extraction;
3. non-object root schema is rejected;
4. request unknown fields fail closed;
5. backend result unknown fields fail closed;
6. deterministic fake backend receives the exact same `NormalizedTextDocument` instance;
7. backend receives the exact request configuration;
8. backend receives `document_name` unchanged;
9. valid backend data -> existing `StructuredExtractionResult`;
10. `result.data` is unchanged from backend data;
11. `result.document_type == content.document_type`;
12. deterministic engine name includes backend identity;
13. backend confidence is preserved unchanged;
14. schema-valid result returns `validation_status == "valid"`;
15. validation uses existing `StructuredValidationResult`;
16. schema-invalid backend data returns `validation_status == "invalid"`, not a second result type;
17. invalid result preserves backend data unchanged for audit;
18. validation error details are deterministic across identical runs;
19. `additionalProperties: false` is honored;
20. required-property validation is honored;
21. type validation is honored without coercion;
22. content ID/fingerprint/segments remain unchanged;
23. no production provider SDK/network client/API-key access introduced;
24. existing DF-02 tests remain green;
25. existing DF-03 tests remain green;
26. existing PDF/supplier-quotation tests remain green;
27. full Python worker suite passes.

Use only synthetic fixtures and deterministic fake backends.

## Privacy

Do not use personal client or prospective-client names anywhere in:

- code;
- docs;
- tests;
- fixtures;
- commits;
- PRs;
- issues.

Before handoff, scan all changed files against the orchestration privacy rule.

Use generic synthetic values only.

## Completion protocol

Before handoff update this file with:

- State;
- Current HEAD;
- changed files;
- public/shared contracts changed or not;
- dependency changes;
- tests;
- exact CI run + conclusion;
- privacy scan;
- blockers;
- next integration action.

Stop after this bounded slice.

Do not merge independently.

## Planned next step

After DF-04 is integrated, the Development Orchestrator should define the next cross-repository runnable slice that wires:

```text
NormalizedTextDocument
-> DF-04 schema-driven extraction
-> StructuredExtractionResult
-> integrated TradeOps VS-07 strict earnings consumer
-> EarningsEvent
-> existing deterministic research pipeline
```

That runnable integration belongs outside DF-04.


## Handoff status

### Current HEAD

CI-validated implementation HEAD:

`8e4db9f0e9dc2a0dec75cf09a4bcfac74d119d06`

The handoff documentation update is docs-only and follows that implementation HEAD.

### Changed files

- `docs/DF04_SCHEMA_DRIVEN_TEXT_EXTRACTION.md`
- `src/DocFlow.Extraction.Worker/docflow_worker/engines/__init__.py`
- `src/DocFlow.Extraction.Worker/docflow_worker/engines/schema_driven_text.py`
- `src/DocFlow.Extraction.Worker/pyproject.toml`
- `src/DocFlow.Extraction.Worker/tests/test_schema_driven_text_extraction_engine.py`

### Public/shared contracts

Changed additively:

- `SchemaDrivenTextExtractionRequest`
- `SchemaDrivenTextExtractionBackend`
- `SchemaDrivenTextExtractionBackendResult`
- `SchemaDrivenTextExtractionEngine`

The existing `TextStructuredExtractionEngine`, `StructuredExtractionEngine`,
`StructuredExtractionResult`, `StructuredValidationResult`,
`ValidationCheckResult`, `NormalizedTextDocument`, DF-02 identity/fingerprint
semantics, PDF extraction contracts, and deterministic supplier-quotation
contracts were not modified.

### Dependency changes

Added one bounded runtime dependency:

`jsonschema>=4`

No provider SDK, HTTP client, provider retry/configuration dependency, model
client, or domain-specific dependency was added.

### Tests

GitHub `Python Worker CI` executed:

- `python -m compileall -q docflow_worker main.py` — passed;
- `pytest -q` — `55 passed in 0.59s`.

The DF-04 tests cover request/schema validation, fail-closed unknown members,
backend confidence bounds, exact normalized-document and request propagation,
unchanged document identity/fingerprint/segments, document-name propagation,
existing result/validation contract reuse, deterministic engine identity,
valid/invalid schema outcomes, deterministic error details,
`additionalProperties: false`, required fields, strict type validation without
coercion, backend exception propagation, and absence of production
provider/network-client imports.

The full suite also covers the existing DF-02 normalization, DF-03 text
structured-extraction boundary, PDF/storage, deterministic supplier-quotation,
and supplier-quotation validation regressions.

### CI

Exact CI-validated implementation HEAD:

`8e4db9f0e9dc2a0dec75cf09a4bcfac74d119d06`

GitHub Actions:

`Python Worker CI` run `37611399701` (run number `160`) — `success`.

Draft integration PR: #4.

### Privacy scan

All five changed files were scanned against the orchestration privacy rule.
Only generic synthetic values are used in implementation/tests; no prohibited
personal client or prospective-client names were introduced. Commit messages
and the draft PR title/body are also generic.

### Blockers

None.

### Next integration action

Development Orchestrator should review draft PR #4 and, if accepted, integrate
DF-04 into `main`.

Do not start a provider-specific backend or cross-repository runnable slice from
this worker chat. Those belong to a separately orchestrated follow-up slice.
