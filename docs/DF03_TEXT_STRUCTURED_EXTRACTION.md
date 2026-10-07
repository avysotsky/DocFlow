# DF-03 — Generic Text Structured Extraction Boundary

## State

READY

## Repository / branch

```text
avysotsky/DocFlow
DocFlow/df03-text-structured-extraction
```

## Baseline

```text
0ff4d160fba375c7e1b5b5808bbfe8992a0ba5e1
```

## Purpose

Extend the integrated DF-02 normalized text pipeline with a generic semantic-extraction boundary without changing the existing PDF extraction contract.

Target flow:

```text
NormalizedTextDocument
-> text structured-extraction engine boundary
-> existing StructuredExtractionResult
```

This slice defines the reusable text-document extraction contract only. It does not implement earnings logic or a production LLM extractor.

## Architecture decision

The existing `StructuredExtractionEngine` is currently bound to PDF/layout-oriented `DocumentContent`:

```text
DocumentContent -> StructuredExtractionEngine -> StructuredExtractionResult
```

DF-03 must preserve this API unchanged.

Add a parallel text-document extraction abstraction whose input is the integrated DF-02 `NormalizedTextDocument` and whose output is the existing generic `StructuredExtractionResult`.

Recommended shape:

```python
class TextStructuredExtractionEngine(ABC):
    @property
    def name(self) -> str: ...

    async def extract(
        self,
        content: NormalizedTextDocument,
        *,
        document_name: str | None = None,
    ) -> StructuredExtractionResult: ...
```

Naming may vary if a clearer generic name is justified, but the boundary must remain parallel rather than changing the existing PDF engine signature.

## Existing contracts to preserve

Do not break or redefine:

- `DocumentContent`
- `PageContent`
- `TextBlockContent`
- `WordContent`
- `TableContent`
- `StructuredExtractionEngine`
- `StructuredExtractionResult`
- `NormalizedTextDocument`
- `TextDocumentSource`
- `TextDocumentParticipant`
- `TextDocumentSegment`
- `TextDocumentNormalizer`

DF-02 canonical IDs and SHA-256 fingerprint semantics are frozen for this slice.

Do not modify the DF-02 hashing/canonicalization algorithm.

## Required implementation

Create the smallest production abstraction needed for structured extraction from normalized text documents.

At minimum:

1. add a new abstract text structured-extraction engine contract;
2. input must be the existing `NormalizedTextDocument`;
3. output must be the existing `StructuredExtractionResult`;
4. export the new abstraction from the appropriate engine package;
5. keep the existing PDF `StructuredExtractionEngine` unchanged;
6. add unit tests proving the text boundary can be implemented by a deterministic test engine and preserves the exact normalized document passed to it;
7. keep the full existing PDF/supplier-quotation and DF-02 regression suite green.

A small generic runner/helper is allowed only if it materially improves the boundary and remains domain-neutral. Do not add framework machinery without a concrete need.

## Explicitly out of scope

Do not implement in DF-03:

- TradeOps dependency;
- earnings-specific extraction;
- revenue / EPS / guidance models;
- financial or trading metadata;
- fiscal periods;
- ticker / instrument mapping;
- `ResearchDecision`;
- provider acquisition;
- HTTP scraping;
- speech-to-text;
- OCR changes;
- persistence;
- LLM provider integration;
- ONNX model integration;
- sentiment analysis;
- summarization;
- schema registry;
- prompt management;
- a second text normalizer;
- changes to DF-02 document ID / segment ID / fingerprint semantics;
- refactoring the existing supplier-quotation engine to use the new text boundary.

## Boundary semantics

The new abstraction must consume an already validated `NormalizedTextDocument`.

It must not:

- renormalize participants;
- reorder segments;
- regenerate document or segment IDs;
- regenerate the DF-02 fingerprint;
- infer missing source metadata;
- access network or clock as part of the boundary itself.

Concrete future engines may perform semantic extraction, but this base contract must remain provider-neutral and domain-neutral.

## StructuredExtractionResult

Reuse the existing `StructuredExtractionResult`.

Do not create a second extraction-result type solely for text documents.

The existing result is already generic:

```text
engine
document_type
data
confidence
validation_status
validation
```

DF-03 should establish that both PDF/layout extraction engines and normalized-text extraction engines can converge on this same result boundary.

## Tests

At minimum cover:

1. a deterministic test implementation can accept `NormalizedTextDocument`;
2. the exact normalized document content/identity reaches the engine unchanged;
3. ordered segments remain unchanged;
4. participant associations remain unchanged;
5. engine returns existing `StructuredExtractionResult`;
6. engine name is deterministic;
7. no clock/network requirement in the base boundary;
8. existing `StructuredExtractionEngine` signature remains unchanged;
9. existing deterministic supplier-quotation tests remain green;
10. existing DF-02 normalization tests remain green;
11. full Python worker regression suite passes.

Use only synthetic fixtures.

## Cross-repository boundary

DocFlow must not reference TradeOps.

DF-03 must not depend on the TradeOps VS-06 branch or its `EarningsTranscriptResearchInput`.

VS-06 and DF-03 are intentionally parallel:

```text
DF-03: DocFlow generic text extraction capability
VS-06: TradeOps consumer adapter for DocFlow normalized artifacts
```

Their files and contracts must remain independent.

## Privacy

Do not use personal client or prospective-client names in code, docs, tests, fixtures, commits, PRs, or issues.

Use generic values such as:

- client
- prospective client
- sample
- Sample Company

Before handoff, search all changed files for prohibited personal names defined by the orchestration privacy rule.

## Completion protocol

Before handoff, update this file with:

- State
- Current HEAD
- changed files
- public/shared contracts changed or not
- tests
- exact CI run + conclusion
- blockers
- next integration action

Stop after this single bounded slice.

Do not merge independently.
