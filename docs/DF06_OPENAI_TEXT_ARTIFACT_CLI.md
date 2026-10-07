# DF-06 — OpenAI Text Artifact CLI

## State

READY

## Repository / branch

```text
avysotsky/DocFlow
DocFlow/df06-openai-text-artifact-cli
```

## Baseline

```text
0fc59b75f53344c802a620b033c409334e145fd9
```

Production DF-05 post-merge CI:

```text
37615744590 — SUCCESS
```

## Purpose

Add the missing runnable producer boundary for provider-backed text extraction.

Target flow:

```text
RawTextDocumentInput JSON
+ caller-owned SchemaDrivenTextExtractionRequest JSON
+ explicit OpenAI model
-> existing TextDocumentNormalizer
-> NormalizedTextDocument JSON artifact
-> existing OpenAiSchemaDrivenTextExtractionBackend
-> existing SchemaDrivenTextExtractionEngine
-> StructuredExtractionResult JSON artifact
```

This slice is generic and domain-neutral.

It must not contain earnings, finance, trading, portfolio, ticker, fiscal-period, or ResearchDecision logic.

## Architecture decision

Do not change or repurpose the existing PDF-oriented `main.py` CLI.

Add a separate text-artifact runnable entry point and a small testable orchestration layer.

Recommended shape:

```text
docflow_worker/text_artifact_pipeline.py
text_artifact_main.py
```

Exact file names may vary if a clearer bounded layout is justified.

The pipeline must reuse unchanged:

- `RawTextDocumentInput`
- `TextDocumentNormalizer`
- `NormalizedTextDocument`
- `SchemaDrivenTextExtractionRequest`
- `SchemaDrivenTextExtractionEngine`
- `OpenAiSchemaDrivenTextExtractionBackend`
- `StructuredExtractionResult`

Do not create replacement normalization or structured-extraction contracts.

## CLI

Recommended invocation:

```text
python text_artifact_main.py
  --input-raw-json <path>
  --schema-request <path>
  --model <model>
  --output-normalized-json <path>
  --output-structured-json <path>
  [--document-name <name>]
```

Requirements:

- all four file paths above are required;
- model is required and has no default;
- paths are resolved explicitly from caller input;
- output parent directories may be created;
- no implicit working-directory file substitution;
- unknown CLI arguments fail;
- `--document-name` is optional and passed unchanged to the existing extraction engine/backend chain;
- no provider registry in this slice.

## Input parsing

Load the raw input using the existing strict Pydantic model:

```text
RawTextDocumentInput
```

Then call exactly the existing:

```text
TextDocumentNormalizer.normalize(...)
```

Do not manually normalize fields in the CLI.

Load the schema request using exactly:

```text
SchemaDrivenTextExtractionRequest
```

Do not parse or rewrite caller JSON Schema manually.

Invalid raw input or invalid schema request must fail before the provider call.

## Provider composition

Production CLI composition must be:

```text
backend = OpenAiSchemaDrivenTextExtractionBackend(model)
engine = SchemaDrivenTextExtractionEngine(backend, request)
result = await engine.extract(normalized_document, document_name=...)
```

Do not call the OpenAI SDK directly from the CLI.

Do not duplicate DF-04 schema validation.

Do not add a second prompt.

Do not add retries.

## Artifact writing

After normalization succeeds, write the canonical normalized document JSON using the existing Pydantic model serialization.

After the extraction engine returns, write the existing `StructuredExtractionResult` JSON.

Serialization must:

- be UTF-8;
- preserve exact model field names expected by the existing contracts;
- not add custom metadata envelopes;
- not alter document IDs, segment IDs, fingerprint, backend data, validation, or confidence;
- be deterministic for a deterministic backend result.

Do not inject domain fields into either artifact.

## Invalid structured result behavior

DF-04 may return:

```text
validation_status = "invalid"
```

for backend data that does not satisfy the caller JSON Schema.

For auditability:

- write the returned structured artifact unchanged;
- return a non-zero CLI exit code;
- print only a bounded error/status summary;
- do not discard the provider output;
- do not convert invalid to valid/incomplete.

Provider exceptions or configuration failures also return non-zero.

## Console / privacy behavior

Success output may include only bounded metadata such as:

- normalized document ID;
- fingerprint;
- segment count;
- structured engine name;
- validation status;
- output artifact paths.

Do not print:

- transcript text;
- full normalized JSON;
- full structured provider data;
- API key;
- raw OpenAI response.

## Testability / dependency injection

Automated tests must not use the network.

Structure the orchestration so tests can inject either:

- a deterministic `SchemaDrivenTextExtractionBackend`; or
- a backend factory.

Production defaults to the integrated OpenAI backend only at the CLI composition edge.

Do not weaken DF-05 solely for testing this CLI.

## Optional real-provider smoke

A manual opt-in smoke is allowed but not required for CI/integration.

If included, it must:

- be skipped by default;
- require explicit opt-in;
- use `OPENAI_API_KEY` only through the official SDK;
- use a tiny synthetic raw text document;
- use a generic synthetic schema;
- make one bounded request;
- never use client/proprietary transcript data.

## Required tests

At minimum cover:

1. valid raw JSON parses through existing `RawTextDocumentInput`;
2. normalization uses existing `TextDocumentNormalizer`;
3. normalized output re-parses as `NormalizedTextDocument`;
4. document ID/fingerprint/segment IDs are preserved in output;
5. valid schema request parses through existing `SchemaDrivenTextExtractionRequest`;
6. invalid schema request rejects before backend invocation;
7. explicit model is required by CLI;
8. injected fake backend receives the same normalized document instance used by the pipeline;
9. existing `SchemaDrivenTextExtractionEngine` is used;
10. document_name passes unchanged;
11. valid fake backend result writes existing `StructuredExtractionResult`;
12. structured output re-parses as the existing result model;
13. backend data is not rewritten;
14. valid result -> exit 0;
15. schema-invalid result is still written and -> non-zero;
16. provider exception -> non-zero;
17. missing input/schema file -> non-zero;
18. output directories can be created;
19. CLI console does not contain transcript text;
20. no secret/API-key logging;
21. no direct OpenAI SDK call outside the existing DF-05 backend;
22. legacy PDF `main.py` behavior remains unchanged;
23. DF-02/DF-03/DF-04/DF-05 regressions remain green;
24. full Python worker suite passes.

## Explicitly out of scope

Do not add:

- domain-specific schema files;
- earnings schema;
- source acquisition/scraping;
- HTTP transcript download;
- audio/STT;
- provider/model registry;
- multi-provider routing;
- persistence/database;
- queue worker integration;
- web API;
- cross-repository process invocation;
- trading logic.

DF-06 stops after producing normalized and structured JSON artifacts.

## Privacy

Use only synthetic generic test content.

Before handoff scan all changed files against the orchestration privacy rule.

Do not mention prohibited personal names even in absence statements.

## Completion protocol

Before handoff update this file with:

- State;
- Current HEAD;
- changed files;
- public/shared contracts;
- CLI command;
- tests;
- exact CI;
- optional real-provider smoke status;
- privacy scan;
- blockers;
- next integration action.

Stop after this bounded slice.

Do not merge independently.
