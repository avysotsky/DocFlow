# DF-07 — Groq Schema-Driven Text Extraction Backend

## State

READY

## Repository / branch

```text
avysotsky/DocFlow
DocFlow/df07-groq-schema-backend
```

## Baseline

```text
88d0bf7d0ff20208c2992fa43bac1f32414e0b8d
```

Latest validated production baseline:

```text
DF-06 post-merge CI: 37621390275 — SUCCESS
```

## Purpose

Add a free-tier cloud provider path for the existing generic schema-driven text extraction pipeline without changing any TradeOps/domain contract.

Target:

```text
RawTextDocumentInput JSON
+ caller SchemaDrivenTextExtractionRequest JSON
+ --provider groq
+ explicit Groq model
+ GROQ_API_KEY from environment
-> existing TextDocumentNormalizer
-> GroqSchemaDrivenTextExtractionBackend
-> existing SchemaDrivenTextExtractionEngine
-> existing StructuredExtractionResult JSON
```

The OpenAI path must remain intact and backward-compatible.

## Current provider contract decision

Groq's current official API is OpenAI-compatible at:

```text
https://api.groq.com/openai/v1
```

Use the already installed `openai` Python package. Do not add a Groq SDK dependency.

For guaranteed schema compliance, use Groq Chat Completions Structured Outputs with:

```text
response_format.type = json_schema
response_format.json_schema.strict = true
```

Do not use the Groq Responses API for this bounded slice because its current compatibility contract does not support the OpenAI `store` request field used by DF-05, while Groq documents strict Structured Outputs explicitly through Chat Completions.

## Production backend

Add:

```text
src/DocFlow.Extraction.Worker/docflow_worker/engines/groq_schema_driven_text.py
```

Recommended public surface:

```python
class GroqSchemaDrivenTextExtractionError(RuntimeError):
    ...

class GroqSchemaDrivenTextExtractionBackend(
    SchemaDrivenTextExtractionBackend
):
    ...
```

Backend name:

```text
groq_chat_completions_v1:<model>
```

Model must be explicit. No default model.

Normalize/validate the model identifier using the same existing identifier normalization rules used by DF-05.

## Client construction

When no test client is injected, construct:

```python
AsyncOpenAI(
    api_key=<GROQ_API_KEY from environment>,
    base_url="https://api.groq.com/openai/v1",
)
```

Requirements:

- credential name is exactly `GROQ_API_KEY`;
- never accept API key through CLI arguments;
- never log or return the key;
- if the key is missing/blank, fail closed with a bounded provider-specific configuration error;
- do not copy the key into metadata, output artifacts, exceptions, or prompt text.

An injected async client must allow all automated tests to remain network-free.

## Prompt/instructions

Use the same generic extraction semantics already established by DF-05:

```text
Extract only information supported by the normalized document.
Return only data matching the supplied caller schema.
Do not invent unsupported facts.
If the schema requests document, segment, or evidence identifiers,
copy the exact identifiers from the normalized document without
translating or altering them.
```

Do not add finance/earnings/trading-specific prompt content.

Do not change the DF-05 OpenAI prompt in this slice unless required by a clearly documented shared refactor. Prefer leaving DF-05 untouched.

## Document serialization

Serialize the complete existing `NormalizedTextDocument` deterministically exactly as DF-05 does:

- `model_dump(mode="json")`;
- UTF-8 JSON semantics;
- `ensure_ascii=False`;
- sorted keys;
- compact separators.

Do not omit participants, segments, source/provenance, IDs, or fingerprint.

Do not mutate the input document.

## Groq request

Use:

```python
await client.chat.completions.create(...)
```

with:

- explicit model;
- exactly one generic system instruction message;
- exactly one user message containing the deterministic serialized normalized document;
- `response_format`:
  - `type = "json_schema"`
  - `json_schema.name = "docflow_schema"`
  - `json_schema.strict = True`
  - `json_schema.schema = request.json_schema`.

Do not add:

- tools;
- tool choice;
- web search;
- MCP;
- temperature tuning;
- reasoning settings;
- retries;
- streaming;
- provider metadata.

The caller's JSON Schema object must be passed unchanged.

## Response parsing

Read the first completion choice's assistant message content.

Requirements:

- one response choice is sufficient;
- missing choices -> fail closed;
- missing/blank content -> fail closed;
- invalid JSON -> fail closed;
- non-object JSON -> fail closed;
- provider exception -> wrap in `GroqSchemaDrivenTextExtractionError` without leaking provider message, document text, or credential.

Return:

```python
SchemaDrivenTextExtractionBackendResult(
    data=<parsed object>,
    confidence=None,
)
```

Do not perform JSON Schema validation in the provider backend. Existing DF-04 `SchemaDrivenTextExtractionEngine` remains authoritative.

## Supported model semantics

Do not hard-code a model allowlist in production.

The CLI model remains explicit because provider model availability can change.

Tests may document that current Groq strict Structured Outputs support includes models such as:

```text
openai/gpt-oss-20b
openai/gpt-oss-120b
qwen/qwen3.8-27b
```

but production must not reject a future compatible model merely because it is not in a static local list.

## CLI provider selection

Extend the existing:

```text
src/DocFlow.Extraction.Worker/text_artifact_main.py
```

Add:

```text
--provider openai|groq
```

Backward compatibility:

```text
default provider = openai
```

Existing invocation without `--provider` must preserve the current DF-06 OpenAI behavior.

Groq invocation:

```text
python text_artifact_main.py \
  --provider groq \
  --model <explicit-groq-model> \
  --input-raw-json <path> \
  --schema-request <path> \
  --output-normalized-json <path> \
  --output-structured-json <path> \
  [--document-name <name>]
```

Do not add `--api-key`.

Do not change the pipeline's provider-neutral JSON artifact format.

## Testability / existing backend_factory

Preserve the existing network-free injection boundary.

The current `backend_factory: Callable[[str], SchemaDrivenTextExtractionBackend]` may remain unchanged.

When a caller injects `backend_factory`, tests must not require any real provider credential.

Provider resolution is only the default CLI composition edge.

Do not make DF-04/DF-06 generic pipeline code provider-aware unless strictly necessary.

## Exports

Export the new Groq backend/error from:

```text
docflow_worker/engines/__init__.py
```

No new package dependency should be needed.

## Required tests — Groq backend

At minimum cover:

1. implements existing `SchemaDrivenTextExtractionBackend`;
2. explicit model required;
3. deterministic backend name;
4. default client uses `AsyncOpenAI` with exact Groq base URL;
5. default client reads `GROQ_API_KEY` from environment;
6. missing/blank `GROQ_API_KEY` rejects before a provider request;
7. injected client does not require environment credential;
8. exact Chat Completions endpoint surface is used;
9. request has one system + one user message;
10. system instructions stay generic/domain-neutral;
11. user message contains complete deterministic normalized document JSON;
12. caller JSON Schema object is passed unchanged;
13. `response_format.type == "json_schema"`;
14. schema name == `docflow_schema`;
15. `strict == True`;
16. no tools/web/MCP/retries/streaming/provider metadata;
17. successful JSON object parses unchanged;
18. confidence remains null;
19. empty content rejected;
20. invalid JSON rejected;
21. non-object JSON rejected;
22. missing/empty choices rejected;
23. provider exception wrapped without raw provider detail;
24. provider exception does not leak transcript text or API key;
25. backend itself does not perform JSON Schema validation;
26. existing DF-04 engine still marks schema-invalid backend data invalid;
27. no finance/trading/TradeOps/domain logic;
28. no clock/random/logging side effects.

## Required tests — CLI

At minimum cover:

1. existing CLI without `--provider` still selects OpenAI;
2. `--provider openai` selects existing OpenAI backend;
3. `--provider groq` selects new Groq backend;
4. unknown provider fails parsing;
5. model remains required for both providers;
6. no API-key CLI option exists;
7. injected backend factory remains network/credential independent;
8. existing output artifact serialization is unchanged;
9. schema-invalid result still writes artifact and returns exit code 2;
10. bounded console output does not contain transcript/API key;
11. legacy PDF `main.py` remains untouched;
12. existing DF-02/03/04/05/06 tests remain green;
13. full Python worker suite passes.

## Optional real-provider smoke

The worker may run a real Groq smoke only if its execution environment already contains:

```text
GROQ_API_KEY
```

and an explicit model is available from user/orchestration context.

Do not request or print the key.

Do not invent a model choice for the worker.

If not available in the worker environment, record:

```text
real Groq smoke: NOT RUN — local operator credential/model required
```

This is not a CI/integration blocker.

The user's locally saved key is expected to be used later from their own workstation after DF-07 integration.

## Explicitly out of scope

Do not add:

- Gemini;
- Ollama;
- provider registry/service discovery;
- automatic provider fallback;
- retries;
- model registry;
- provider pricing logic;
- transcript acquisition;
- finance-specific schemas;
- TradeOps dependency;
- database/persistence;
- web API;
- queue integration;
- secret storage service;
- modifications to the legacy PDF CLI.

## Privacy

Use only generic synthetic test documents.

Before handoff scan all changed files against the orchestration privacy rule.

Do not mention prohibited personal/client names even in absence statements.

## Completion protocol

Before handoff update this file with:

- State;
- Current HEAD;
- changed files;
- public/shared contracts;
- provider request semantics;
- CLI provider behavior;
- tests;
- exact CI;
- real Groq smoke status separately;
- privacy/secret scan;
- blockers;
- next integration action.

Stop after this bounded slice.

Do not merge independently.
