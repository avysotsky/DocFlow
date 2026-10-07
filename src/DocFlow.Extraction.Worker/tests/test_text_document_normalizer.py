import json
from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import ValidationError

from docflow_worker.text_document_models import NormalizedTextDocument, RawTextDocumentInput
from docflow_worker.text_document_normalizer import TextDocumentNormalizer


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "sample_transcript.json"


def _fixture_payload() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _normalize(payload: dict | None = None) -> NormalizedTextDocument:
    raw = RawTextDocumentInput.model_validate(payload or _fixture_payload())
    return TextDocumentNormalizer().normalize(raw)


def test_valid_raw_transcript_normalizes_deterministically() -> None:
    document = _normalize()

    assert document.document_id.startswith("textdoc:")
    assert len(document.document_id) == len("textdoc:") + 64
    assert len(document.segments) == 5
    assert document.segments[2].participant_id is None
    assert all(segment.segment_id.startswith("textseg:") for segment in document.segments)
    assert len(document.fingerprint) == 64
    assert document.fingerprint == document.fingerprint.lower()


def test_crlf_and_lf_are_equivalent() -> None:
    left = _fixture_payload()
    right = deepcopy(left)
    left["segments"][1]["text"] = "Line one\r\nLine two"
    right["segments"][1]["text"] = "Line one\nLine two"

    assert _normalize(left) == _normalize(right)


def test_surrounding_whitespace_is_equivalent() -> None:
    left = _fixture_payload()
    right = deepcopy(left)
    right["title"] = "  Sample quarterly business call \n"
    right["participants"][0]["display_name"] = "  Moderator  "
    right["segments"][0]["text"] = "  Welcome to the sample quarterly business call. \r\n"

    assert _normalize(left) == _normalize(right)


def test_meaningful_text_change_changes_segment_id_and_fingerprint() -> None:
    left = _normalize()
    payload = _fixture_payload()
    payload["segments"][1]["text"] += " Additional detail."
    right = _normalize(payload)

    assert left.document_id == right.document_id
    assert left.segments[1].segment_id != right.segments[1].segment_id
    assert left.fingerprint != right.fingerprint


def test_same_logical_input_has_same_ids_and_fingerprint() -> None:
    left = _normalize()
    right = _normalize()

    assert left.document_id == right.document_id
    assert [segment.segment_id for segment in left.segments] == [
        segment.segment_id for segment in right.segments
    ]
    assert left.fingerprint == right.fingerprint


def test_segments_are_sorted_by_sequence() -> None:
    payload = _fixture_payload()
    payload["segments"] = list(reversed(payload["segments"]))

    document = _normalize(payload)

    assert [segment.sequence for segment in document.segments] == [1, 2, 3, 4, 5]


def test_duplicate_participant_id_is_rejected() -> None:
    payload = _fixture_payload()
    payload["participants"][1]["participant_id"] = payload["participants"][0]["participant_id"]

    with pytest.raises(ValueError, match="participant_id values must be unique"):
        _normalize(payload)


def test_duplicate_segment_sequence_is_rejected() -> None:
    payload = _fixture_payload()
    payload["segments"][1]["sequence"] = 1

    with pytest.raises(ValueError, match="segment sequence values must be unique"):
        _normalize(payload)


def test_non_positive_sequence_is_rejected() -> None:
    payload = _fixture_payload()
    payload["segments"][0]["sequence"] = 0

    with pytest.raises(ValueError, match="positive integers"):
        _normalize(payload)


def test_empty_document_is_rejected() -> None:
    payload = _fixture_payload()
    payload["segments"] = []

    with pytest.raises(ValueError, match="at least one segment"):
        _normalize(payload)


def test_empty_segment_is_rejected() -> None:
    payload = _fixture_payload()
    payload["segments"][0]["text"] = " \r\n "

    with pytest.raises(ValueError, match="segment text must contain meaningful text"):
        _normalize(payload)


def test_unknown_participant_reference_is_rejected() -> None:
    payload = _fixture_payload()
    payload["segments"][0]["participant_id"] = "missing-speaker"

    with pytest.raises(ValueError, match="unknown participant_id"):
        _normalize(payload)


def test_speakerless_segment_is_supported() -> None:
    document = _normalize()

    assert document.segments[2].participant_id is None


def test_same_display_name_with_different_ids_remains_distinct() -> None:
    payload = _fixture_payload()
    payload["participants"][1]["display_name"] = "Same Name"
    payload["participants"][2]["display_name"] = "Same Name"

    document = _normalize(payload)

    same_name = [p for p in document.participants if p.display_name == "Same Name"]
    assert [p.participant_id for p in same_name] == ["speaker-a", "speaker-b"]


def test_source_timestamp_after_published_at_is_rejected() -> None:
    payload = _fixture_payload()
    payload["source"]["source_timestamp"] = "2026-09-30T16:00:00Z"

    with pytest.raises(ValidationError, match="timestamps must satisfy"):
        _normalize(payload)


def test_published_at_after_retrieved_at_is_rejected() -> None:
    payload = _fixture_payload()
    payload["source"]["published_at"] = "2026-10-01T09:00:00Z"

    with pytest.raises(ValidationError, match="timestamps must satisfy"):
        _normalize(payload)


def test_optional_timestamps_are_supported_without_using_a_clock() -> None:
    payload = _fixture_payload()
    payload["source"]["source_timestamp"] = None
    payload["source"]["published_at"] = None
    payload["source"]["retrieved_at"] = None

    document = _normalize(payload)

    assert document.source.source_timestamp is None
    assert document.source.published_at is None
    assert document.source.retrieved_at is None


def test_json_round_trip_revalidates_normalized_artifact() -> None:
    document = _normalize()
    serialized = document.model_dump_json()

    restored = NormalizedTextDocument.model_validate_json(serialized)

    assert restored == document


def test_unknown_field_in_normalized_artifact_is_rejected() -> None:
    payload = _normalize().model_dump(mode="json")
    payload["unexpected"] = "not allowed"

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        NormalizedTextDocument.model_validate(payload)


def test_tampered_document_id_is_rejected() -> None:
    payload = _normalize().model_dump(mode="json")
    payload["document_id"] = "textdoc:" + "0" * 64

    with pytest.raises(ValidationError, match="document_id does not match"):
        NormalizedTextDocument.model_validate(payload)


def test_tampered_segment_id_is_rejected() -> None:
    payload = _normalize().model_dump(mode="json")
    payload["segments"][0]["segment_id"] = "textseg:" + "0" * 64

    with pytest.raises(ValidationError, match="segment_id for sequence 1"):
        NormalizedTextDocument.model_validate(payload)


def test_tampered_fingerprint_is_rejected() -> None:
    payload = _normalize().model_dump(mode="json")
    payload["fingerprint"] = "0" * 64

    with pytest.raises(ValidationError, match="fingerprint does not match"):
        NormalizedTextDocument.model_validate(payload)


def test_source_identity_change_changes_document_id_and_fingerprint() -> None:
    left = _normalize()
    payload = _fixture_payload()
    payload["source"]["source_document_id"] = "sample-call-2026-q3-revised"
    right = _normalize(payload)

    assert left.document_id != right.document_id
    assert left.fingerprint != right.fingerprint


def test_timestamp_representation_with_same_instant_is_equivalent() -> None:
    left = _fixture_payload()
    right = deepcopy(left)
    right["source"]["source_timestamp"] = "2026-09-30T17:00:00+03:00"
    right["source"]["published_at"] = "2026-09-30T18:00:00+03:00"
    right["source"]["retrieved_at"] = "2026-10-01T11:30:00+03:00"

    assert _normalize(left) == _normalize(right)


def test_segment_sequence_content_association_change_changes_fingerprint() -> None:
    left = _normalize()
    payload = _fixture_payload()
    payload["segments"][0]["sequence"], payload["segments"][1]["sequence"] = (
        payload["segments"][1]["sequence"],
        payload["segments"][0]["sequence"],
    )
    right = _normalize(payload)

    assert left.fingerprint != right.fingerprint
    assert [segment.text for segment in left.segments[:2]] != [
        segment.text for segment in right.segments[:2]
    ]


def test_normalized_json_rejects_non_utc_timestamp_representation() -> None:
    payload = _normalize().model_dump(mode="json")
    payload["source"]["source_timestamp"] = "2026-09-30T17:00:00+03:00"

    with pytest.raises(ValidationError, match="must be normalized to UTC"):
        NormalizedTextDocument.model_validate(payload)
