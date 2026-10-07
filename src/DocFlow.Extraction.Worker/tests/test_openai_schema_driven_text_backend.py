import ast
import asyncio
import copy
import inspect
import json

import pytest

import docflow_worker.engines.openai_schema_driven_text as openai_backend_module
from docflow_worker.engines import (
    OpenAiSchemaDrivenTextExtractionBackend,
    OpenAiSchemaDrivenTextExtractionError,
    SchemaDrivenTextExtractionBackend,
    SchemaDrivenTextExtractionEngine,
    SchemaDrivenTextExtractionRequest,
)
from docflow_worker.text_document_models import RawTextDocumentInput
from docflow_worker.text_document_normalizer import TextDocumentNormalizer


class _FakeResponse:
    def __init__(self, *, status: str = "completed", output_text: str = "{}") -> None:
        self.status = status
        self.output_text = output_text


class _FakeResponses:
    def __init__(
        self,
        response: _FakeResponse | None = None,
        *,
        error: Exception | None = None,
    ) -> None:
        self.response = response or _FakeResponse()
        self.error = error
        self.calls: list[dict] = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.response


class _FakeClient:
    def __init__(
        self,
        response: _FakeResponse | None = None,
        *,
        error: Exception | None = None,
    ) -> None:
        self.responses = _FakeResponses(response, error=error)


def _schema() -> dict:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": False,
        "required": ["category", "score", "evidence"],
        "properties": {
            "category": {"type": "string"},
            "score": {"type": "number"},
            "evidence": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["segment_id"],
                    "properties": {
                        "segment_id": {"type": "string"},
                    },
                },
            },
        },
    }


def _request() -> SchemaDrivenTextExtractionRequest:
    return SchemaDrivenTextExtractionRequest(
        schema_name="generic extraction",
        schema_version=1,
        json_schema=_schema(),
    )


def _document():
    raw = RawTextDocumentInput.model_validate(
        {
            "title": "Synthetic document",
            "document_type": "generic_transcript",
            "source": {
                "provider": "synthetic",
                "source_uri": "https://example.test/document/5",
                "source_document_id": "synthetic-005",
                "source_timestamp": "2026-10-01T10:00:00+00:00",
                "published_at": "2026-10-01T10:01:00+00:00",
                "retrieved_at": "2026-10-01T10:02:00+00:00",
            },
            "participants": [
                {
                    "participant_id": "speaker-a",
                    "display_name": "Speaker A",
                    "role": "host",
                    "organization": "Synthetic Org",
                },
                {
                    "participant_id": "speaker-b",
                    "display_name": "Speaker B",
                    "role": "guest",
                    "organization": "Synthetic Org",
                },
            ],
            "segments": [
                {
                    "sequence": 2,
                    "participant_id": "speaker-b",
                    "text": "Second supported statement.",
                },
                {
                    "sequence": 1,
                    "participant_id": "speaker-a",
                    "text": "First supported statement.",
                },
            ],
        }
    )
    return TextDocumentNormalizer().normalize(raw)


def _backend(
    output_text: str = '{"category":"sample","score":0.5,"evidence":[]}',
    *,
    status: str = "completed",
):
    client = _FakeClient(_FakeResponse(status=status, output_text=output_text))
    return OpenAiSchemaDrivenTextExtractionBackend("gpt-test", client=client), client


def test_backend_implements_df04_abstraction_and_requires_explicit_model() -> None:
    backend, _ = _backend()

    assert isinstance(backend, SchemaDrivenTextExtractionBackend)
    assert backend.name == "openai_responses_v1:gpt-test"

    with pytest.raises(TypeError, match="model must be a string"):
        OpenAiSchemaDrivenTextExtractionBackend(None, client=_FakeClient())

    with pytest.raises(ValueError):
        OpenAiSchemaDrivenTextExtractionBackend("   ", client=_FakeClient())


def test_model_is_normalized_and_backend_name_is_deterministic() -> None:
    first = OpenAiSchemaDrivenTextExtractionBackend(
        "  gpt-test  ",
        client=_FakeClient(),
    )
    second = OpenAiSchemaDrivenTextExtractionBackend(
        "gpt-test",
        client=_FakeClient(),
    )

    assert first.name == "openai_responses_v1:gpt-test"
    assert second.name == first.name


def test_default_client_uses_official_sdk_standard_configuration(monkeypatch) -> None:
    calls = []

    def fake_async_openai(*args, **kwargs):
        calls.append((args, kwargs))
        return _FakeClient()

    monkeypatch.setattr(openai_backend_module, "AsyncOpenAI", fake_async_openai)

    backend = OpenAiSchemaDrivenTextExtractionBackend("gpt-test")

    assert backend.name == "openai_responses_v1:gpt-test"
    assert calls == [((), {})]


def test_responses_request_uses_exact_schema_strict_mode_store_false_and_no_tools() -> None:
    backend, client = _backend()
    request = _request()
    schema_before = copy.deepcopy(request.json_schema)

    asyncio.run(backend.extract(_document(), request=request, document_name="synthetic.txt"))

    assert len(client.responses.calls) == 1
    call = client.responses.calls[0]
    assert call["model"] == "gpt-test"
    assert call["store"] is False
    assert call["text"]["format"]["type"] == "json_schema"
    assert call["text"]["format"]["name"] == "docflow_schema"
    assert call["text"]["format"]["strict"] is True
    assert call["text"]["format"]["schema"] is request.json_schema
    assert request.json_schema == schema_before
    assert "tools" not in call
    assert "tool_choice" not in call
    assert "previous_response_id" not in call
    assert "conversation" not in call
    assert "metadata" not in call


def test_document_serialization_is_complete_deterministic_and_does_not_mutate_input() -> None:
    backend, client = _backend()
    request = _request()
    document = _document()
    before = document.model_dump_json()

    asyncio.run(backend.extract(document, request=request))
    asyncio.run(backend.extract(document, request=request))

    first_input = client.responses.calls[0]["input"]
    second_input = client.responses.calls[1]["input"]
    expected = json.dumps(
        document.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )

    assert first_input == expected
    assert second_input == expected

    payload = json.loads(first_input)
    assert payload == document.model_dump(mode="json")
    assert payload["document_id"] == document.document_id
    assert payload["title"] == document.title
    assert payload["document_type"] == document.document_type
    assert payload["source"] == document.source.model_dump(mode="json")
    assert payload["participants"] == [
        participant.model_dump(mode="json") for participant in document.participants
    ]
    assert payload["segments"] == [
        segment.model_dump(mode="json") for segment in document.segments
    ]
    assert [item["segment_id"] for item in payload["segments"]] == [
        segment.segment_id for segment in document.segments
    ]
    assert payload["fingerprint"] == document.fingerprint
    assert document.model_dump_json() == before


def test_successful_object_parse_preserves_json_and_sets_confidence_none() -> None:
    output = {
        "category": "sample",
        "score": 3.25,
        "evidence": [
            {
                "segment_id": "textseg:synthetic",
                "details": {
                    "enabled": True,
                    "values": [1, 2.5, "three", None],
                },
            }
        ],
    }
    backend, _ = _backend(json.dumps(output, separators=(",", ":")))

    result = asyncio.run(backend.extract(_document(), request=_request()))

    assert result.data == output
    assert result.confidence is None


@pytest.mark.parametrize("output_text", ["", "   ", "not-json", "[1,2,3]", '"text"', "null"])
def test_empty_invalid_and_non_object_output_is_rejected(output_text: str) -> None:
    backend, _ = _backend(output_text)

    with pytest.raises(OpenAiSchemaDrivenTextExtractionError):
        asyncio.run(backend.extract(_document(), request=_request()))


@pytest.mark.parametrize("status", ["failed", "incomplete", "cancelled"])
def test_non_completed_provider_status_is_rejected(status: str) -> None:
    backend, _ = _backend(status=status)

    with pytest.raises(
        OpenAiSchemaDrivenTextExtractionError,
        match="response was not completed",
    ):
        asyncio.run(backend.extract(_document(), request=_request()))


def test_provider_exception_is_wrapped_without_provider_message_or_document_dump() -> None:
    client = _FakeClient(error=ValueError("synthetic provider detail"))
    backend = OpenAiSchemaDrivenTextExtractionBackend("gpt-test", client=client)
    document = _document()

    with pytest.raises(OpenAiSchemaDrivenTextExtractionError) as captured:
        asyncio.run(backend.extract(document, request=_request()))

    message = str(captured.value)
    assert "ValueError" in message
    assert "synthetic provider detail" not in message
    assert document.segments[0].text not in message


def test_backend_does_not_validate_schema_output_but_df04_engine_does() -> None:
    schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["count"],
        "properties": {"count": {"type": "integer"}},
    }
    request = SchemaDrivenTextExtractionRequest(
        schema_name="count extraction",
        schema_version=1,
        json_schema=schema,
    )
    client = _FakeClient(_FakeResponse(output_text='{"count":"7"}'))
    backend = OpenAiSchemaDrivenTextExtractionBackend("gpt-test", client=client)
    document = _document()

    backend_result = asyncio.run(backend.extract(document, request=request))
    assert backend_result.data == {"count": "7"}

    engine = SchemaDrivenTextExtractionEngine(backend, request)
    engine_result = asyncio.run(engine.extract(document))

    assert engine_result.data == {"count": "7"}
    assert engine_result.validation_status == "invalid"
    assert engine_result.validation.status == "invalid"
    assert engine_result.validation.checks["json_schema"].status == "failed"


def test_production_backend_has_no_domain_logic_clock_random_or_logging() -> None:
    source = inspect.getsource(openai_backend_module)
    lowered = source.lower()

    for token in (
        "earnings",
        "revenue",
        "trading",
        "portfolio",
        "tradeops",
        "researchdecision",
    ):
        assert token not in lowered

    tree = ast.parse(source)
    imported_roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".", 1)[0])

    assert imported_roots.isdisjoint({"datetime", "logging", "random", "time", "uuid"})
    assert "print(" not in source
