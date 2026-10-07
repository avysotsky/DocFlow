# DF-06 — OpenAI Text Artifact CLI

## State

READY_FOR_INTEGRATION

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


## Handoff status

### Live state verified before implementation

```text
main: 0fc59b75f53344c802a620b033c409334e145fd9
initial branch HEAD: 500754e7bb92a2a83c51b82dd45675cc5b68b035
initial compare: ahead 1 / behind 0
initial branch CI: no workflow run on the specification-only HEAD
production baseline Python Worker CI: 37615744590 — SUCCESS
```

The branch had not advanced beyond the supplied initial HEAD before implementation began.

### CI-validated implementation HEAD

`4991dda534bf7b98caf2ec19d437fab07e3d6645`

This handoff documentation update is docs-only and follows that CI-validated implementation HEAD. The final docs-only commit SHA is reported by the worker handoff because a Git commit cannot contain its own SHA.

### Changed files

- `docs/DF06_OPENAI_TEXT_ARTIFACT_CLI.md`
- `src/DocFlow.Extraction.Worker/docflow_worker/text_artifact_pipeline.py`
- `src/DocFlow.Extraction.Worker/text_artifact_main.py`
- `src/DocFlow.Extraction.Worker/tests/test_text_artifact_cli.py`

The legacy PDF-oriented `src/DocFlow.Extraction.Worker/main.py` is not changed.

No dependency or workflow file is changed.

### Public/shared contracts

Existing DF-02/DF-03/DF-04/DF-05 contracts are reused unchanged:

- `RawTextDocumentInput`
- `TextDocumentNormalizer`
- `NormalizedTextDocument`
- `SchemaDrivenTextExtractionRequest`
- `SchemaDrivenTextExtractionBackend`
- `OpenAiSchemaDrivenTextExtractionBackend`
- `SchemaDrivenTextExtractionEngine`
- `StructuredExtractionResult`

DF-06 adds only a bounded runnable orchestration surface:

- `BackendFactory` for network-free dependency injection;
- `TextArtifactPipelineResult` for in-process orchestration status;
- `run_text_artifact_pipeline(...)`;
- standalone `text_artifact_main.py`.

The CLI does not call the provider SDK directly and does not add a second JSON Schema validator.

### CLI

```text
python text_artifact_main.py \
  --input-raw-json <path> \
  --schema-request <path> \
  --model <model> \
  --output-normalized-json <path> \
  --output-structured-json <path> \
  [--document-name <name>]
```

`--model` is required and has no default.

Behavior:

- raw JSON is parsed by `RawTextDocumentInput`;
- normalization is performed only by `TextDocumentNormalizer`;
- the canonical `NormalizedTextDocument` JSON artifact is written immediately after successful normalization;
- the caller schema request is parsed by `SchemaDrivenTextExtractionRequest`;
- production composition constructs `OpenAiSchemaDrivenTextExtractionBackend(model)`;
- extraction is performed by the existing `SchemaDrivenTextExtractionEngine`;
- the existing `StructuredExtractionResult` is written without a custom envelope;
- a schema-invalid structured result is still written and returns exit code 2;
- provider/configuration/file/parsing failures return non-zero;
- console output is bounded to IDs/count/status/engine/artifact paths or an error type.

### Tests

All automated tests are network-free and use an injected deterministic fake backend/factory.

DF-06 coverage includes:

- existing raw model parsing;
- existing normalizer use;
- normalized artifact round-trip through `NormalizedTextDocument`;
- exact document ID, fingerprint, and segment ID preservation;
- existing schema-request parsing;
- invalid schema rejection before backend factory/provider invocation;
- required model and unknown-argument failure;
- the same normalized object instance reaching the backend through the existing engine;
- unchanged `document_name` forwarding;
- valid structured artifact round-trip;
- backend data/confidence/validation preservation;
- schema-invalid artifact write plus non-zero exit;
- provider exception and missing-file non-zero behavior;
- output-directory creation;
- bounded console output with no transcript/secret echo;
- no direct provider SDK use in the DF-06 CLI/pipeline;
- separation from the legacy PDF CLI;
- DF-02/DF-03/DF-04/DF-05 regressions through the full worker suite.

Final CI-validated suite:

```text
86 passed in 1.04s
```

### Exact CI

GitHub `Python Worker CI`:

```text
run: 37620518654
event: pull_request
PR: #6 (draft, CI harness only)
HEAD: 4991dda534bf7b98caf2ec19d437fab07e3d6645
conclusion: SUCCESS
tests: 86 passed
```

Earlier red runs were limited to DF-06 test-harness defects; the final CI above is the authoritative implementation result.

### Optional real-provider smoke

Not run.

The optional real-provider smoke remains explicit opt-in only and is not part of CI.

### Privacy scan

PASS.

All changed implementation/test content uses synthetic generic data. No credentials, client/proprietary transcript content, or real-person test data are introduced. Console failure handling emits only the exception type and artifact paths rather than exception messages or payloads.

### Blockers

None.

### Next integration action

Development Orchestrator should review the bounded diff and draft PR #6, then integrate `DocFlow/df06-openai-text-artifact-cli` into `main` if accepted and verify the post-merge `Python Worker CI`.

This worker does not merge the branch independently.
