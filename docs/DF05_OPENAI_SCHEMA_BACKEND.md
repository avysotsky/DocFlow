# DF-05 — OpenAI Schema-Driven Text Extraction Backend

## State

INTEGRATED

## Repository / branch

```text
avysotsky/DocFlow
DocFlow/df05-openai-schema-backend
```

## Baseline

```text
604062cfe948b380fabd22ee222295e5a2c02a95
```

DF-04 production post-merge CI:

```text
37612364691 — SUCCESS
```

## Purpose

Implement the first real provider backend for the integrated DF-04 protocol using the OpenAI Responses API with Structured Outputs.

Target:

```text
NormalizedTextDocument
+ SchemaDrivenTextExtractionRequest
-> OpenAI Responses API
   with caller JSON Schema as structured output format
-> JSON object
-> SchemaDrivenTextExtractionBackendResult
-> existing DF-04 SchemaDrivenTextExtractionEngine
-> existing StructuredExtractionResult
```

DF-05 is provider-specific but remains domain-neutral.

It must not contain earnings, finance, trading, fiscal-period, ticker, revenue, EPS, guidance, TradeOps, or ResearchDecision logic.

## Current API basis

Use the official OpenAI Python SDK and the Responses API.

Do not use the retired Assistants API.

At slice definition time, the current official Python package is in the 3.x line and the Responses API supports Structured Outputs through a JSON Schema response format.

The implementation worker must verify the exact current SDK call shape from official OpenAI documentation before committing code.

Recommended dependency range:

```text
openai>=3.26.0,<4
```

Do not use unofficial clients.

## Existing DF-04 contracts to implement

Reuse unchanged:

- `SchemaDrivenTextExtractionBackend`
- `SchemaDrivenTextExtractionBackendResult`
- `SchemaDrivenTextExtractionRequest`
- `SchemaDrivenTextExtractionEngine`
- `NormalizedTextDocument`

Do not change DF-04 public signatures merely to fit OpenAI.

If provider-specific limitations exist, handle them in DF-05 or fail clearly.

## Provider backend

Recommended class:

```text
OpenAiSchemaDrivenTextExtractionBackend
```

It implements:

```text
SchemaDrivenTextExtractionBackend
```

Constructor requirements:

- model is required and normalized non-empty;
- model has no hardcoded default;
- optional injected OpenAI async client for testing;
- when no client is injected, create the official async client using its standard environment-based API-key behavior;
- do not store or log the API key.

The backend name must be deterministic.

Recommended:

```text
openai_responses_v1:<model>
```

No timestamps, request IDs, random suffixes, document IDs, or schema hashes in the backend name.

## API call

Use the Responses API.

Use Structured Outputs / JSON Schema, not legacy JSON mode.

The request must pass the caller's `request.json_schema` unchanged as the response schema.

Use strict structured output when supported by the current official API shape.

Do not rewrite the schema to make it provider-compatible.

If the provider rejects a valid DF-04 Draft 2020-12 schema because OpenAI strict Structured Outputs supports only a subset, propagate a clear provider-specific failure.

Do not silently relax or modify the caller schema.

## Response-format name

OpenAI's structured-output format name has provider-specific character/length restrictions.

Do not mutate `request.schema_name` and pretend it is unchanged.

Use a stable provider-local response format identifier independent of business/domain semantics, e.g.:

```text
docflow_schema
```

or another deterministic compliant identifier.

The caller schema name/version remain part of the DF-04 request and are passed to the backend contract unchanged.

## Prompt / instructions

DF-05 may contain one fixed generic extraction instruction because it is a concrete model backend.

Do not create a prompt framework or prompt registry.

The instruction must remain domain-neutral.

Required semantic intent:

- extract only information supported by the normalized document;
- return only data matching the supplied schema;
- do not invent unsupported facts;
- when the caller schema requests source/evidence identifiers, copy exact IDs from the normalized document;
- do not translate or alter IDs.

Do not mention earnings, revenue, EPS, trading, portfolio, or TradeOps.

## Document serialization

Serialize the entire `NormalizedTextDocument` deterministically for model input, including:

- document_id;
- title;
- document_type;
- source metadata;
- participants;
- ordered segments;
- segment IDs;
- fingerprint.

Use deterministic JSON serialization:

- UTF-8;
- stable key order where practical;
- no clock/random values.

Do not flatten away segment IDs.

Do not renormalize or reorder content.

The same `NormalizedTextDocument` instance passed to the backend must remain unchanged.

## Privacy / API storage

Set the Responses request to non-persistent mode where the current API supports it, e.g. `store=False`.

Do not enable web search, file search, code interpreter, MCP, or any other tool.

Do not send extra repository/user metadata.

Do not log:

- transcript content;
- API key;
- raw provider response;
- schema payload by default.

Errors may include bounded provider status/type information but should avoid dumping transcript content.

## Response handling

For a successful completed response:

1. read the SDK's supported aggregate structured/text output accessor;
2. require non-empty output;
3. parse it as JSON;
4. require the root to be a JSON object;
5. return:
   ```text
   SchemaDrivenTextExtractionBackendResult(
       data=<parsed object>,
       confidence=None
   )
   ```

Do not invent confidence because OpenAI does not provide a generic extraction confidence compatible with DF-04.

DF-04 remains responsible for deterministic schema validation.

Do not set `validation_status` in the backend.

## Failure handling

Fail clearly for:

- non-completed/incomplete/cancelled/failed response;
- refusal with no structured object;
- empty output;
- invalid JSON output;
- non-object JSON root;
- provider exception;
- invalid/missing model configuration.

Do not convert provider failures into an empty successful object.

Do not retry in application code in this slice.

If the SDK has implicit retries, do not add a second retry layer.

## Dependency / configuration

Add the bounded official SDK dependency.

No secret files.

No committed API key.

No client-specific endpoint.

No hardcoded model.

A real manual smoke may use:

```text
OPENAI_API_KEY
```

through the official SDK's standard configuration.

CI must not require a real API key.

## Tests

All automated tests must be network-free.

Use an injected fake/mock async OpenAI client.

At minimum cover:

1. backend implements existing DF-04 backend abstraction;
2. model is required/non-empty/normalized;
3. deterministic backend name includes supplied model;
4. exact `NormalizedTextDocument` is not mutated;
5. deterministic document serialization includes document/fingerprint/segments/segment IDs;
6. exact caller JSON Schema is sent unchanged;
7. provider-local response format name is compliant and deterministic;
8. strict JSON Schema structured-output mode is requested;
9. no tools are enabled;
10. non-persistent/store-disabled mode requested where supported;
11. successful response JSON object -> backend result;
12. backend result confidence is null;
13. JSON numbers/strings/arrays are preserved;
14. empty output rejects;
15. invalid JSON rejects;
16. non-object root rejects;
17. provider incomplete/failed status rejects;
18. provider exception propagates/wraps clearly without transcript dump;
19. caller schema is not rewritten;
20. backend does not perform schema validation itself;
21. DF-04 engine still performs final schema validation around this backend;
22. no earnings/trading/domain terms in production backend;
23. no clock/random ID use;
24. no API key or transcript logging;
25. existing DF-02/DF-03/DF-04 regression tests remain green;
26. full Python worker suite passes.

## Optional manual smoke

A manual opt-in smoke helper/test is allowed if it:

- is skipped by default;
- requires explicit environment opt-in;
- requires `OPENAI_API_KEY`;
- uses a tiny synthetic document only;
- uses a generic synthetic schema;
- makes one bounded request;
- never runs in normal CI.

Do not use real client transcripts in smoke tests.

## Explicitly out of scope

Do not implement:

- earnings-specific schema;
- TradeOps dependency;
- provider/model registry;
- multi-provider routing;
- fallback provider;
- retries/backoff layer;
- streaming;
- batch API;
- conversation persistence;
- prompt registry;
- web/file/tools;
- transcript acquisition;
- CLI/API integration;
- persistence/cache;
- cost accounting;
- sentiment/summarization;
- ResearchDecision.

## Privacy

Use only synthetic generic values in tests/docs.

Before handoff scan all changed files against the orchestration privacy rule.

Do not mention prohibited names even in an absence statement.

## Completion protocol

Before handoff update this file with:

- State;
- Current HEAD;
- changed files;
- dependency changes;
- API surface;
- tests;
- exact CI run + conclusion;
- optional manual smoke status separately;
- privacy scan;
- blockers;
- next integration action.

Stop after this bounded slice.

Do not merge independently.


## Handoff status

### CI-validated implementation HEAD

`e89b175bb6e453108fe8903e87ab31b5ec1dfeb2`

This handoff documentation update is docs-only and follows that implementation HEAD.

### Changed files

- `docs/DF05_OPENAI_SCHEMA_BACKEND.md`
- `src/DocFlow.Extraction.Worker/docflow_worker/engines/__init__.py`
- `src/DocFlow.Extraction.Worker/docflow_worker/engines/openai_schema_driven_text.py`
- `src/DocFlow.Extraction.Worker/pyproject.toml`
- `src/DocFlow.Extraction.Worker/tests/test_openai_schema_driven_text_backend.py`

### Dependency

Added the bounded official SDK dependency:

```text
openai>=3.26.0,<4
```

The exact CI install resolved `openai 3.26.0`.

### API surface

Added:

- `OpenAiSchemaDrivenTextExtractionBackend`
- `OpenAiSchemaDrivenTextExtractionError`

The backend:

- requires an explicit model and exposes deterministic name `openai_responses_v1:<model>`;
- supports an injected async client for network-free tests;
- otherwise constructs the official `AsyncOpenAI` client with standard SDK configuration;
- uses `responses.create`;
- sends the caller schema unchanged through strict `text.format` JSON Schema Structured Outputs;
- uses provider-local response-format name `docflow_schema`;
- sends `store=False`;
- enables no tools and no conversation persistence;
- serializes the complete `NormalizedTextDocument` deterministically;
- accepts only a completed response with non-empty JSON-object output;
- returns `SchemaDrivenTextExtractionBackendResult(data=..., confidence=None)`;
- leaves final JSON Schema validation exclusively to the existing DF-04 engine.

No DF-04 public signatures were changed.

### OpenAI API verification

Before implementation, the current official API documentation and official Python SDK were checked. The current Responses API supports Structured Outputs via `text.format` with `type="json_schema"`, `strict=True`, and caller-supplied `schema`; `store=False` is supported. The current official Python package release is `3.26.0`.

### Tests

All automated tests are network-free and use an injected fake async client.

Coverage includes:

- backend abstraction implementation;
- explicit/normalized model and deterministic backend name;
- standard no-argument official SDK client construction when no client is injected;
- exact caller schema object sent unchanged;
- strict Structured Outputs and deterministic provider-local format name;
- `store=False`, no tools, no conversation/persistence metadata;
- deterministic complete normalized-document serialization with exact IDs and fingerprint;
- input immutability;
- successful JSON object parsing and JSON value preservation;
- `confidence=None`;
- empty, invalid JSON, and non-object output rejection;
- failed, incomplete, and cancelled response rejection;
- provider exception wrapping without input/raw-provider dump;
- backend intentionally not performing schema validation;
- existing DF-04 engine performing final deterministic validation;
- absence of domain-specific production logic, clock/random dependencies, and logging;
- DF-02/DF-03/DF-04 and existing worker regressions through the full suite.

GitHub `Python Worker CI`:

```text
run: 37614034193
run number: 163
conclusion: SUCCESS
implementation HEAD: e89b175bb6e453108fe8903e87ab31b5ec1dfeb2
python -m compileall -q docflow_worker main.py — passed
pytest -q — 73 passed in 0.87s
```

Draft integration PR: #5.

### Optional manual smoke

Not run.

The optional real-provider smoke is not required for this bounded slice and remains explicitly opt-in. CI does not require `OPENAI_API_KEY` and made no provider network calls.

### Privacy scan

All five changed files were scanned before handoff. The scan passed: only generic synthetic fixture values are present and no committed secret was found.

### Blockers

None.

### Integration result

DF-05 was accepted and integrated.

```text
final PR head: 7cf5e0b235c88c3615059af06f1629e0dba0a82d
exact-head CI: 37614234502 — SUCCESS
PR: #5
merge commit: 2cc1a2c17e27200e708314d6196891837eb6ad8f
post-merge CI: 37615744590 — SUCCESS
```

Architecture, API-shape, privacy, and secret review passed. The backend remains domain-neutral, preserves the integrated DF-04 contract, uses the OpenAI Responses API Structured Outputs path, and keeps deterministic schema validation in DF-04.

The optional real-provider smoke was not required for integration and was not run.

Next orchestration step: integrate the independent VS-08 runnable transcript-to-research slice, then define a provider-backed end-to-end transcript research demo that composes the two integrated boundaries without introducing a cross-repository package dependency.
