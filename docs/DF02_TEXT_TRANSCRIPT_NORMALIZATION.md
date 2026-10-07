# DF-02 — Generic Text / Transcript Normalization

## State

INTEGRATED

## Branch

`DocFlow/transcript-normalization-boundary`

## Baseline

`82ce2fdc22b79fb0add3f849509df887ca9c2a2e`

## Goal

Provide a deterministic generic boundary for textual documents that have already been obtained by a caller:

`raw textual document -> validation -> normalization -> normalized participants -> ordered segments -> deterministic IDs -> SHA-256 fingerprint -> JSON -> NormalizedTextDocument`

This slice stops at normalized document representation. It does not perform semantic extraction.

## Architecture boundary

The new text/transcript representation is parallel to the existing PDF `DocumentContent` representation. The existing `DocumentContent`, PDF extractor, `StructuredExtractionEngine` signature, deterministic supplier-quotation engine, and validators are not refactored by DF-02.

**DocFlow has no dependency on TradeOps.**

**NormalizedTextDocument is generic document-intelligence output, not an earnings/trading contract.**

No TradeOps types, namespaces, financial metadata, trading metadata, or earnings-specific business rules are used.

## Models added

- `RawTextDocumentInput`
- `RawTextDocumentSource`
- `RawTextDocumentParticipant`
- `RawTextDocumentSegment`
- `NormalizedTextDocument`
- `TextDocumentSource`
- `TextDocumentParticipant`
- `TextDocumentSegment`
- `TextDocumentNormalizer`

`document_type` is a free-form normalized string rather than a domain-specific enum.

Participant IDs are explicit caller-provided identities in this slice. DF-02 does not infer identities and does not merge participants by display name. Equal display names with different participant IDs remain distinct.

A segment may have `participant_id = null` for narration, unknown-speaker text, or system/operator text.

## Normalization semantics

The normalizer is deterministic and performs no network or clock access.

- CRLF and CR line endings are converted to LF.
- Accidental surrounding whitespace is trimmed.
- Meaningful internal text is preserved.
- Required scalar fields must contain meaningful text.
- Participant IDs are normalized and must be unique.
- Segment sequence values must be positive and unique.
- Segments are sorted deterministically by sequence.
- Empty documents and empty segments are rejected.
- Non-null segment participant references must resolve to a declared participant.
- Speaker identity is never inferred.
- Text is not summarized or semantically rewritten.

No generic metadata bag was added because this bounded slice does not require one.

## Time / source semantics

`provider` is required. At least one stable source locator is required: `source_uri` or `source_document_id`.

`source_timestamp`, `published_at`, and `retrieved_at` are optional because generic meeting/interview/plain-text inputs may not naturally have every timestamp. Supplied timestamps must be timezone-aware and are normalized to UTC.

For every supplied pair, semantic ordering is enforced:

`source_timestamp <= published_at <= retrieved_at`

Unknown timestamps remain `null`. DF-02 never substitutes the current time and never calls `datetime.now()` or `utcnow()`.

## ID semantics

`DocumentId` is deterministic and has the form:

`textdoc:<sha256>`

Its canonical identity payload contains:

- provider
- source document ID
- source URI

It excludes processing time and other volatile values.

`SegmentId` is deterministic and has the form:

`textseg:<sha256>`

Its canonical payload contains:

- DocumentId
- sequence
- participant ID or null
- normalized segment text

Meaningful text changes therefore change the segment ID. Equivalent CRLF/LF or surrounding-whitespace differences normalize to the same segment ID.

## Fingerprint semantics

`fingerprint` is lowercase SHA-256 hex, exactly 64 characters.

The canonical fingerprint payload contains:

- normalized title
- normalized document type
- source identity and supplied evidence timestamps
- ordered participants
- ordered normalized segments
- segment sequence/participant/text associations

Canonical JSON uses sorted object keys and fixed separators. The fingerprint therefore does not depend on JSON property order or dictionary insertion order. Input line endings and surrounding whitespace are normalized before hashing.

Meaningful content changes or sequence/content-association changes produce a different fingerprint.

## JSON semantics

Pydantic v2 is used; no serialization dependency was added.

Supported path:

`raw JSON -> RawTextDocumentInput -> TextDocumentNormalizer -> NormalizedTextDocument -> JSON -> NormalizedTextDocument`

Normalized artifacts are fail-closed:

- unknown fields are rejected;
- DocumentId is recomputed and validated;
- every SegmentId is recomputed and validated;
- fingerprint is recomputed and validated;
- participant and sequence integrity is revalidated on deserialization.

## Sample fixture

`src/DocFlow.Extraction.Worker/tests/fixtures/sample_transcript.json`

The fixture is fully synthetic and uses only fictional names/content. It contains a moderator, two speakers, a questioner, and one speakerless narration segment.

## Changed files

- `src/DocFlow.Extraction.Worker/docflow_worker/__init__.py`
- `src/DocFlow.Extraction.Worker/docflow_worker/text_document_models.py`
- `src/DocFlow.Extraction.Worker/docflow_worker/text_document_normalizer.py`
- `src/DocFlow.Extraction.Worker/tests/test_text_document_normalizer.py`
- `src/DocFlow.Extraction.Worker/tests/fixtures/sample_transcript.json`
- `docs/DF02_TEXT_TRANSCRIPT_NORMALIZATION.md`

## Existing PDF compatibility

DF-02 does not change:

- `docflow_worker/models.py`
- `PdfContentExtractor`
- `DocumentContent`
- `StructuredExtractionEngine`
- deterministic supplier-quotation extraction contracts

Existing PDF, storage, supplier-quotation extraction, and supplier-quotation validation tests remain part of the regression suite.

## Tests

Local worker regression result before GitHub push: `35 passed`.

Coverage includes the requested deterministic cases: valid normalization, CRLF/LF equivalence, surrounding-whitespace equivalence, meaningful text changes, stable IDs/fingerprint, sequence sorting and validation, participant validation, speakerless segments, same-name distinct participants, time ordering, optional timestamps without clock usage, JSON round trip, unknown-field rejection, and tamper detection for DocumentId/SegmentId/fingerprint.

## CI

Exact pre-merge HEAD `a1b543ad4c8f4920c27baf2db7d7251d162bb87d` passed GitHub `Python Worker CI` run `37602859254` (run number `154`). PR #2 was merged into `main` as `3e0cbb0499069667ae04984e0bb5a71d6f366cb5`. Post-merge GitHub `Python Worker CI` run `37603127313` (run number `155`) completed with `success`.

## Blockers

None.

## Next integration action

DF-02 is integrated. Generic text/transcript normalization remains owned by DocFlow. The next cross-repository step must be a separate bounded earnings-research adapter from `NormalizedTextDocument` into TradeOps consumer contracts; do not add TradeOps dependencies to DocFlow.
