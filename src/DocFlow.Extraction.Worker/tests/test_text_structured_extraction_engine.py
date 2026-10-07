import asyncio
import inspect
import socket
import time

from docflow_worker.engines import StructuredExtractionEngine, TextStructuredExtractionEngine
from docflow_worker.models import DocumentContent, StructuredExtractionResult
from docflow_worker.text_document_models import NormalizedTextDocument, RawTextDocumentInput
from docflow_worker.text_document_normalizer import TextDocumentNormalizer


class _DeterministicTextEngine(TextStructuredExtractionEngine):
    def __init__(self) -> None:
        self.received_content: NormalizedTextDocument | None = None
        self.received_document_name: str | None = None

    @property
    def name(self) -> str:
        return "deterministic_text_test_v1"

    async def extract(
        self,
        content: NormalizedTextDocument,
        *,
        document_name: str | None = None,
    ) -> StructuredExtractionResult:
        self.received_content = content
        self.received_document_name = document_name

        return StructuredExtractionResult(
            engine=self.name,
            document_type=content.document_type,
            data={
                "document_id": content.document_id,
                "fingerprint": content.fingerprint,
                "segments": [
                    {
                        "sequence": segment.sequence,
                        "participant_id": segment.participant_id,
                        "segment_id": segment.segment_id,
                    }
                    for segment in content.segments
                ],
            },
            confidence=1.0,
        )


def _normalized_document() -> NormalizedTextDocument:
    raw = RawTextDocumentInput.model_validate(
        {
            "title": "Sample text document",
            "document_type": "sample_transcript",
            "source": {
                "provider": "sample",
                "source_document_id": "sample-document-001",
            },
            "participants": [
                {
                    "participant_id": "speaker-a",
                    "display_name": "Speaker A",
                    "role": "host",
                    "organization": "Sample Company",
                },
                {
                    "participant_id": "speaker-b",
                    "display_name": "Speaker B",
                    "role": "guest",
                    "organization": "Sample Company",
                },
            ],
            "segments": [
                {
                    "sequence": 2,
                    "participant_id": "speaker-b",
                    "text": "Second segment.",
                },
                {
                    "sequence": 1,
                    "participant_id": "speaker-a",
                    "text": "First segment.",
                },
                {
                    "sequence": 3,
                    "participant_id": None,
                    "text": "Speakerless narration.",
                },
            ],
        }
    )
    return TextDocumentNormalizer().normalize(raw)


def test_text_engine_preserves_normalized_document_exactly() -> None:
    document = _normalized_document()
    serialized_before = document.model_dump_json()
    engine = _DeterministicTextEngine()

    result = asyncio.run(engine.extract(document, document_name="sample.txt"))

    assert engine.received_content is document
    assert engine.received_content.segments is document.segments
    assert engine.received_content.participants is document.participants
    assert engine.received_document_name == "sample.txt"
    assert document.model_dump_json() == serialized_before

    assert document.document_id == result.data["document_id"]
    assert document.fingerprint == result.data["fingerprint"]
    assert [segment.sequence for segment in document.segments] == [1, 2, 3]
    assert [segment.participant_id for segment in document.segments] == [
        "speaker-a",
        "speaker-b",
        None,
    ]
    assert result.data["segments"] == [
        {
            "sequence": segment.sequence,
            "participant_id": segment.participant_id,
            "segment_id": segment.segment_id,
        }
        for segment in document.segments
    ]
    assert type(result) is StructuredExtractionResult


def test_text_engine_name_is_deterministic() -> None:
    assert _DeterministicTextEngine().name == "deterministic_text_test_v1"
    assert _DeterministicTextEngine().name == "deterministic_text_test_v1"


def test_text_and_pdf_engine_contracts_are_parallel() -> None:
    text_signature = inspect.signature(TextStructuredExtractionEngine.extract)
    pdf_signature = inspect.signature(StructuredExtractionEngine.extract)

    assert list(text_signature.parameters) == ["self", "content", "document_name"]
    assert text_signature.parameters["content"].annotation is NormalizedTextDocument
    assert (
        text_signature.parameters["document_name"].kind
        is inspect.Parameter.KEYWORD_ONLY
    )
    assert text_signature.return_annotation is StructuredExtractionResult

    assert list(pdf_signature.parameters) == ["self", "content", "document_name"]
    assert pdf_signature.parameters["content"].annotation is DocumentContent
    assert pdf_signature.parameters["document_name"].kind is inspect.Parameter.KEYWORD_ONLY
    assert pdf_signature.return_annotation is StructuredExtractionResult


def test_text_engine_boundary_requires_no_clock_or_network(monkeypatch) -> None:
    document = _normalized_document()
    engine = _DeterministicTextEngine()

    def _unexpected_dependency(*args, **kwargs):
        raise AssertionError("clock/network dependency is not allowed at this boundary")

    monkeypatch.setattr(time, "time", _unexpected_dependency)
    monkeypatch.setattr(socket, "create_connection", _unexpected_dependency)

    result = asyncio.run(engine.extract(document))

    assert result.engine == "deterministic_text_test_v1"
    assert result.document_type == document.document_type
