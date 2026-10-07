import ast
import asyncio
import copy
import inspect
import json
from types import SimpleNamespace

import pytest

import docflow_worker.engines.groq_schema_driven_text as groq_backend_module
from docflow_worker.engines import (
    GroqSchemaDrivenTextExtractionBackend,
    GroqSchemaDrivenTextExtractionError,
    SchemaDrivenTextExtractionBackend,
    SchemaDrivenTextExtractionEngine,
    SchemaDrivenTextExtractionRequest,
)
from docflow_worker.text_document_models import RawTextDocumentInput
from docflow_worker.text_document_normalizer import TextDocumentNormalizer


class _FakeCompletions:
    def __init__(self, response=None, *, error: Exception | None = None) -> None:
        self.response = response if response is not None else _response("{}")
        self.error = error
        self.calls: list[dict] = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.response


class _FakeClient:
    def __init__(self, response=None, *, error: Exception | None = None) -> None:
        self.chat = SimpleNamespace(
            completions=_FakeCompletions(response, error=error)
        )


def _response(content: str | None, *, choices: list | None = None):
    if choices is not None:
        return SimpleNamespace(choices=choices)
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )


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
                    "properties": {"segment_id": {"type": "string"}},
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
                "source_uri": "https://example.test/document/7",
                "source_document_id": "synthetic-007",
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


def _backend(output_text: str = '{"category":"sample","score":0.5,"evidence":[]}'):
    client = _FakeClient(_response(output_text))
    return GroqSchemaDrivenTextExtractionBackend("groq-test", client=client), client


def test_backend_implements_df04_abstraction_and_requires_explicit_model() -> None:
    backend, _ = _backend()

    assert isinstance(backend, SchemaDrivenTextExtractionBackend)
    assert backend.name == "groq_chat_completions_v1:groq-test"

    with pytest.raises(TypeError, match="model must be a string"):
        GroqSchemaDrivenTextExtractionBackend(None, client=_FakeClient())

    with pytest.raises(ValueError):
        GroqSchemaDrivenTextExtractionBackend("   ", client=_FakeClient())


def test_model_is_normalized_and_backend_name_is_deterministic() -> None:
    first = GroqSchemaDrivenTextExtractionBackend(
        "  groq-test  ",
        client=_FakeClient(),
    )
    second = GroqSchemaDrivenTextExtractionBackend(
        "groq-test",
        client=_FakeClient(),
    )

    assert first.name == "groq_chat_completions_v1:groq-test"
    assert second.name == first.name


def test_default_client_uses_exact_base_url_and_environment_key(monkeypatch) -> None:
    calls = []

    def fake_async_openai(*args, **kwargs):
        calls.append((args, kwargs))
        return _FakeClient()

    monkeypatch.setenv("GROQ_API_KEY", "gsk-synthetic-key")
    monkeypatch.setattr(groq_backend_module, "AsyncOpenAI", fake_async_openai)

    backend = GroqSchemaDrivenTextExtractionBackend("groq-test")

    assert backend.name == "groq_chat_completions_v1:groq-test"
    assert calls == [
        (
            (),
            {
                "api_key": "gsk-synthetic-key",
                "base_url": "https://api.groq.com/openai/v1",
            },
        )
    ]


@pytest.mark.parametrize("api_key", [None, "", "   "])
def test_missing_or_blank_environment_key_fails_closed(monkeypatch, api_key) -> None:
    if api_key is None:
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
    else:
        monkeypatch.setenv("GROQ_API_KEY", api_key)

    def unexpected_client(*args, **kwargs):
        raise AssertionError("provider client must not be constructed")

    monkeypatch.setattr(groq_backend_module, "AsyncOpenAI", unexpected_client)

    with pytest.raises(
        GroqSchemaDrivenTextExtractionError,
        match="GROQ_API_KEY is required",
    ):
        GroqSchemaDrivenTextExtractionBackend("groq-test")


def test_injected_client_does_not_require_environment_credential(monkeypatch) -> None:
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    backend = GroqSchemaDrivenTextExtractionBackend(
        "groq-test",
        client=_FakeClient(),
    )

    assert backend.name == "groq_chat_completions_v1:groq-test"


def test_chat_completions_request_is_exact_strict_and_schema_is_unchanged() -> None:
    backend, client = _backend()
    request = _request()
    schema_before = copy.deepcopy(request.json_schema)

    asyncio.run(backend.extract(_document(), request=request, document_name="synthetic.txt"))

    assert len(client.chat.completions.calls) == 1
    call = client.chat.completions.calls[0]
    assert set(call) == {"model", "messages", "response_format"}
    assert call["model"] == "groq-test"
    assert len(call["messages"]) == 2
    assert call["messages"][0]["role"] == "system"
    assert call["messages"][1]["role"] == "user"
    assert "supported by the normalized document" in call["messages"][0]["content"]
    assert "supplied caller schema" in call["messages"][0]["content"]
    response_format = call["response_format"]
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["name"] == "docflow_schema"
    assert response_format["json_schema"]["strict"] is True
    assert response_format["json_schema"]["schema"] is request.json_schema
    assert request.json_schema == schema_before

    for forbidden in (
        "tools",
        "tool_choice",
        "stream",
        "temperature",
        "metadata",
        "reasoning_effort",
        "reasoning_format",
        "web_search",
        "mcp",
        "retries",
    ):
        assert forbidden not in call


def test_document_serialization_is_complete_deterministic_and_does_not_mutate_input() -> None:
    backend, client = _backend()
    document = _document()
    before = document.model_dump_json()

    asyncio.run(backend.extract(document, request=_request()))
    asyncio.run(backend.extract(document, request=_request()))

    first_input = client.chat.completions.calls[0]["messages"][1]["content"]
    second_input = client.chat.completions.calls[1]["messages"][1]["content"]
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
                "details": {"enabled": True, "values": [1, 2.5, "three", None]},
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

    with pytest.raises(GroqSchemaDrivenTextExtractionError):
        asyncio.run(backend.extract(_document(), request=_request()))


@pytest.mark.parametrize(
    "response",
    [
        SimpleNamespace(choices=None),
        SimpleNamespace(choices=[]),
        SimpleNamespace(choices=[SimpleNamespace(message=None)]),
    ],
)
def test_missing_choices_or_message_is_rejected(response) -> None:
    backend = GroqSchemaDrivenTextExtractionBackend(
        "groq-test",
        client=_FakeClient(response),
    )

    with pytest.raises(GroqSchemaDrivenTextExtractionError):
        asyncio.run(backend.extract(_document(), request=_request()))


def test_provider_exception_is_sanitized_without_provider_document_or_key_detail() -> None:
    api_key = "gsk-synthetic-secret"
    document = _document()
    provider_detail = f"provider failed with {api_key} and {document.segments[0].text}"
    client = _FakeClient(error=ValueError(provider_detail))
    backend = GroqSchemaDrivenTextExtractionBackend("groq-test", client=client)

    with pytest.raises(GroqSchemaDrivenTextExtractionError) as captured:
        asyncio.run(backend.extract(document, request=_request()))

    message = str(captured.value)
    assert "ValueError" in message
    assert provider_detail not in message
    assert api_key not in message
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
    client = _FakeClient(_response('{"count":"7"}'))
    backend = GroqSchemaDrivenTextExtractionBackend("groq-test", client=client)
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
    source = inspect.getsource(groq_backend_module)
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
