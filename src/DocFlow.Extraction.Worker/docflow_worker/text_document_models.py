from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


def normalize_line_endings(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n")


def normalize_required_text(value: str, field_name: str) -> str:
    normalized = normalize_line_endings(value).strip()
    if not normalized:
        raise ValueError(f"{field_name} must contain meaningful text.")
    return normalized


def normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = normalize_line_endings(value).strip()
    return normalized or None


def normalize_identifier(value: str, field_name: str) -> str:
    normalized = normalize_required_text(value, field_name)
    if "\n" in normalized:
        raise ValueError(f"{field_name} must be a single-line identifier.")
    return normalized


def normalize_optional_identifier(value: str | None, field_name: str) -> str | None:
    normalized = normalize_optional_text(value)
    if normalized is None:
        return None
    if "\n" in normalized:
        raise ValueError(f"{field_name} must be a single-line identifier.")
    return normalized


def normalize_datetime(value: datetime | None, field_name: str) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must include a timezone offset.")
    return value.astimezone(timezone.utc)


def canonical_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    normalized = normalize_datetime(value, "timestamp")
    assert normalized is not None
    return normalized.isoformat().replace("+00:00", "Z")


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def sha256_hex(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


class RawTextDocumentSource(_StrictModel):
    provider: str
    source_uri: str | None = None
    source_document_id: str | None = None
    source_timestamp: datetime | None = None
    published_at: datetime | None = None
    retrieved_at: datetime | None = None


class RawTextDocumentParticipant(_StrictModel):
    participant_id: str
    display_name: str
    role: str | None = None
    organization: str | None = None


class RawTextDocumentSegment(_StrictModel):
    sequence: int
    participant_id: str | None = None
    text: str


class RawTextDocumentInput(_StrictModel):
    title: str
    document_type: str
    source: RawTextDocumentSource
    participants: list[RawTextDocumentParticipant] = Field(default_factory=list)
    segments: list[RawTextDocumentSegment]


class TextDocumentSource(_StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: str
    source_uri: str | None = None
    source_document_id: str | None = None
    source_timestamp: datetime | None = None
    published_at: datetime | None = None
    retrieved_at: datetime | None = None

    @field_validator("provider")
    @classmethod
    def _provider_is_normalized(cls, value: str) -> str:
        normalized = normalize_required_text(value, "provider")
        if normalized != value:
            raise ValueError("provider must already be normalized.")
        return value

    @field_validator("source_uri", "source_document_id")
    @classmethod
    def _optional_identity_is_normalized(cls, value: str | None, info) -> str | None:
        normalized = normalize_optional_identifier(value, info.field_name)
        if normalized != value:
            raise ValueError(f"{info.field_name} must already be normalized.")
        return value

    @field_validator("source_timestamp", "published_at", "retrieved_at")
    @classmethod
    def _timestamp_is_utc(cls, value: datetime | None, info) -> datetime | None:
        if value is None:
            return None
        normalize_datetime(value, info.field_name)
        if value.utcoffset() != timedelta(0):
            raise ValueError(f"{info.field_name} must be normalized to UTC.")
        return value

    @model_validator(mode="after")
    def _validate_identity_and_time_order(self) -> "TextDocumentSource":
        if self.source_uri is None and self.source_document_id is None:
            raise ValueError("source_uri or source_document_id is required.")

        ordered = [self.source_timestamp, self.published_at, self.retrieved_at]
        known = [(index, value) for index, value in enumerate(ordered) if value is not None]
        for left_index, (semantic_index, timestamp) in enumerate(known):
            for later_semantic_index, later_timestamp in known[left_index + 1 :]:
                if semantic_index < later_semantic_index and timestamp > later_timestamp:
                    raise ValueError(
                        "timestamps must satisfy source_timestamp <= published_at <= retrieved_at "
                        "for every supplied pair."
                    )
        return self


class TextDocumentParticipant(_StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    participant_id: str
    display_name: str
    role: str | None = None
    organization: str | None = None

    @field_validator("participant_id")
    @classmethod
    def _participant_id_is_normalized(cls, value: str) -> str:
        normalized = normalize_identifier(value, "participant_id")
        if normalized != value:
            raise ValueError("participant_id must already be normalized.")
        return value

    @field_validator("display_name")
    @classmethod
    def _display_name_is_normalized(cls, value: str) -> str:
        normalized = normalize_required_text(value, "display_name")
        if normalized != value:
            raise ValueError("display_name must already be normalized.")
        return value

    @field_validator("role", "organization")
    @classmethod
    def _optional_scalar_is_normalized(cls, value: str | None, info) -> str | None:
        normalized = normalize_optional_text(value)
        if normalized != value:
            raise ValueError(f"{info.field_name} must already be normalized.")
        return value


class TextDocumentSegment(_StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    sequence: int = Field(gt=0)
    participant_id: str | None = None
    text: str
    segment_id: str

    @field_validator("participant_id")
    @classmethod
    def _participant_id_is_normalized(cls, value: str | None) -> str | None:
        normalized = normalize_optional_identifier(value, "participant_id")
        if normalized != value:
            raise ValueError("participant_id must already be normalized.")
        return value

    @field_validator("text")
    @classmethod
    def _text_is_normalized(cls, value: str) -> str:
        normalized = normalize_required_text(value, "segment text")
        if normalized != value:
            raise ValueError("segment text must already be normalized.")
        return value


class NormalizedTextDocument(_StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    document_id: str
    title: str
    document_type: str
    source: TextDocumentSource
    participants: tuple[TextDocumentParticipant, ...]
    segments: tuple[TextDocumentSegment, ...]
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("title", "document_type")
    @classmethod
    def _required_scalar_is_normalized(cls, value: str, info) -> str:
        normalized = normalize_required_text(value, info.field_name)
        if normalized != value:
            raise ValueError(f"{info.field_name} must already be normalized.")
        return value

    @model_validator(mode="after")
    def _validate_integrity(self) -> "NormalizedTextDocument":
        if not self.segments:
            raise ValueError("normalized document must contain at least one segment.")

        participant_ids = [participant.participant_id for participant in self.participants]
        if len(participant_ids) != len(set(participant_ids)):
            raise ValueError("participant_id values must be unique.")
        participant_id_set = set(participant_ids)

        sequences = [segment.sequence for segment in self.segments]
        if len(sequences) != len(set(sequences)):
            raise ValueError("segment sequence values must be unique.")
        if sequences != sorted(sequences):
            raise ValueError("segments must be ordered by sequence.")

        for segment in self.segments:
            if segment.participant_id is not None and segment.participant_id not in participant_id_set:
                raise ValueError(
                    f"segment {segment.sequence} references unknown participant_id "
                    f"{segment.participant_id!r}."
                )

        expected_document_id = build_document_id(self.source)
        if self.document_id != expected_document_id:
            raise ValueError("document_id does not match canonical source identity.")

        for segment in self.segments:
            expected_segment_id = build_segment_id(
                self.document_id,
                segment.sequence,
                segment.participant_id,
                segment.text,
            )
            if segment.segment_id != expected_segment_id:
                raise ValueError(
                    f"segment_id for sequence {segment.sequence} does not match canonical content."
                )

        expected_fingerprint = build_document_fingerprint(
            title=self.title,
            document_type=self.document_type,
            source=self.source,
            participants=self.participants,
            segments=self.segments,
        )
        if self.fingerprint != expected_fingerprint:
            raise ValueError("fingerprint does not match canonical normalized document content.")

        return self


def _source_payload(source: TextDocumentSource) -> dict[str, Any]:
    return {
        "provider": source.provider,
        "sourceUri": source.source_uri,
        "sourceDocumentId": source.source_document_id,
        "sourceTimestamp": canonical_datetime(source.source_timestamp),
        "publishedAt": canonical_datetime(source.published_at),
        "retrievedAt": canonical_datetime(source.retrieved_at),
    }


def build_document_id(source: TextDocumentSource) -> str:
    identity = {
        "provider": source.provider,
        "sourceDocumentId": source.source_document_id,
        "sourceUri": source.source_uri,
    }
    return f"textdoc:{sha256_hex(identity)}"


def build_segment_id(
    document_id: str,
    sequence: int,
    participant_id: str | None,
    text: str,
) -> str:
    payload = {
        "documentId": document_id,
        "sequence": sequence,
        "participantId": participant_id,
        "text": text,
    }
    return f"textseg:{sha256_hex(payload)}"


def build_document_fingerprint(
    *,
    title: str,
    document_type: str,
    source: TextDocumentSource,
    participants: tuple[TextDocumentParticipant, ...],
    segments: tuple[TextDocumentSegment, ...],
) -> str:
    payload = {
        "title": title,
        "documentType": document_type,
        "source": _source_payload(source),
        "participants": [
            {
                "participantId": participant.participant_id,
                "displayName": participant.display_name,
                "role": participant.role,
                "organization": participant.organization,
            }
            for participant in participants
        ],
        "segments": [
            {
                "sequence": segment.sequence,
                "participantId": segment.participant_id,
                "text": segment.text,
            }
            for segment in segments
        ],
    }
    return sha256_hex(payload)
