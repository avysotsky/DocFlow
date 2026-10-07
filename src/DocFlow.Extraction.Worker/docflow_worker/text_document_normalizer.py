from __future__ import annotations

from docflow_worker.text_document_models import (
    NormalizedTextDocument,
    RawTextDocumentInput,
    TextDocumentParticipant,
    TextDocumentSegment,
    TextDocumentSource,
    build_document_fingerprint,
    build_document_id,
    build_segment_id,
    normalize_datetime,
    normalize_identifier,
    normalize_optional_identifier,
    normalize_optional_text,
    normalize_required_text,
)


class TextDocumentNormalizer:
    """Deterministically validates and normalizes already-obtained textual documents."""

    def normalize(self, raw: RawTextDocumentInput) -> NormalizedTextDocument:
        title = normalize_required_text(raw.title, "title")
        document_type = normalize_required_text(raw.document_type, "document_type")

        source = TextDocumentSource(
            provider=normalize_required_text(raw.source.provider, "provider"),
            source_uri=normalize_optional_identifier(raw.source.source_uri, "source_uri"),
            source_document_id=normalize_optional_identifier(
                raw.source.source_document_id,
                "source_document_id",
            ),
            source_timestamp=normalize_datetime(
                raw.source.source_timestamp,
                "source_timestamp",
            ),
            published_at=normalize_datetime(raw.source.published_at, "published_at"),
            retrieved_at=normalize_datetime(raw.source.retrieved_at, "retrieved_at"),
        )

        participants = tuple(
            TextDocumentParticipant(
                participant_id=normalize_identifier(
                    participant.participant_id,
                    "participant_id",
                ),
                display_name=normalize_required_text(
                    participant.display_name,
                    "display_name",
                ),
                role=normalize_optional_text(participant.role),
                organization=normalize_optional_text(participant.organization),
            )
            for participant in raw.participants
        )

        participant_ids = [participant.participant_id for participant in participants]
        if len(participant_ids) != len(set(participant_ids)):
            raise ValueError("participant_id values must be unique.")
        participant_id_set = set(participant_ids)

        if not raw.segments:
            raise ValueError("document must contain at least one segment.")

        normalized_segments: list[tuple[int, str | None, str]] = []
        seen_sequences: set[int] = set()
        for segment in raw.segments:
            if segment.sequence <= 0:
                raise ValueError("segment sequence values must be positive integers.")
            if segment.sequence in seen_sequences:
                raise ValueError("segment sequence values must be unique.")
            seen_sequences.add(segment.sequence)

            participant_id = normalize_optional_identifier(
                segment.participant_id,
                "participant_id",
            )
            if participant_id is not None and participant_id not in participant_id_set:
                raise ValueError(
                    f"segment {segment.sequence} references unknown participant_id "
                    f"{participant_id!r}."
                )

            text = normalize_required_text(segment.text, "segment text")
            normalized_segments.append((segment.sequence, participant_id, text))

        normalized_segments.sort(key=lambda item: item[0])

        document_id = build_document_id(source)
        segments = tuple(
            TextDocumentSegment(
                sequence=sequence,
                participant_id=participant_id,
                text=text,
                segment_id=build_segment_id(
                    document_id,
                    sequence,
                    participant_id,
                    text,
                ),
            )
            for sequence, participant_id, text in normalized_segments
        )

        fingerprint = build_document_fingerprint(
            title=title,
            document_type=document_type,
            source=source,
            participants=participants,
            segments=segments,
        )

        return NormalizedTextDocument(
            document_id=document_id,
            title=title,
            document_type=document_type,
            source=source,
            participants=participants,
            segments=segments,
            fingerprint=fingerprint,
        )
