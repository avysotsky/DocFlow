import ast
import asyncio
import inspect

import pytest
from pydantic import ValidationError

import docflow_worker.engines.schema_driven_text as schema_driven_text_module
from docflow_worker.engines import (
    SchemaDrivenTextExtractionBackend,
    SchemaDrivenTextExtractionBackendResult,
    SchemaDrivenTextExtractionEngine,
    SchemaDrivenTextExtractionRequest,
)
from docflow_worker.models import StructuredExtractionResult, StructuredValidationResult
from docflow_worker.text_document_models import NormalizedTextDocument, RawTextDocumentInput
from docflow_worker.text_document_normalizer import TextDocumentNormalizer


def _schema() -> dict:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": False,
        "required": ["category", "score"],
        "properties": {
            "category": {"type": "string"},
            "score": {"type": "number"},
        },
    }


def _request() -> SchemaDrivenTextExtractionRequest:
    return SchemaDrivenTextExtractionRequest(
        schema_name="sample classification",
        schema_version=1,
        json_schema=_schema(),
    )


def _normalized_document() -> NormalizedTextDocument:
    raw = RawTextDocumentInput.model_validate(
        {
            "title": "Sample text document",
            "document_type": "sample_transcript",
            "source": {
                "provider": "sample",
                "source_document_id": "sample-document-004",
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
                    "text": "Second generic segment.",
                },
                {
                    "sequence": 1,
                    "participant_id": "speaker-a",
                    "text": "First generic segment.",
                },
            ],
        }
    )
    return TextDocumentNormalizer().normalize(raw)


class _InMemoryBackend(SchemaDrivenTextExtractionBackend):
    def __init__(
        self,
        result: SchemaDrivenTextExtractionBackendResult,
        *,
        name: str = "in_memory_test",
    ) -> None:
        self._name = name
        self.result = result
        self.calls = 0
        self.received_content: NormalizedTextDocument | None = None
        self.received_request: SchemaDrivenTextExtractionRequest | None = None
        self.received_document_name: str | None = None

    @property
    def name(self) -> str:
        return self._name

    async def extract(
        self,
        content: NormalizedTextDocument,
        *,
        request: SchemaDrivenTextExtractionRequest,
        document_name: str | None = None,
    ) -> SchemaDrivenTextExtractionBackendResult:
        self.calls += 1
        self.received_content = content
        self.received_request = request
        self.received_document_name = document_name
        return self.result


class _RaisingBackend(SchemaDrivenTextExtractionBackend):
    @property
    def name(self) -> str:
        return "raising_test"

    async def extract(
        self,
        content: NormalizedTextDocument,
        *,
        request: SchemaDrivenTextExtractionRequest,
        document_name: str | None = None,
    ) -> SchemaDrivenTextExtractionBackendResult:
        raise RuntimeError("synthetic backend failure")


def _run(
    data: dict,
    *,
    confidence: float | None = 0.75,
) -> tuple[
    StructuredExtractionResult,
    _InMemoryBackend,
    SchemaDrivenTextExtractionRequest,
    NormalizedTextDocument,
]:
    backend_result = SchemaDrivenTextExtractionBackendResult(
        data=data,
        confidence=confidence,
    )
    backend = _InMemoryBackend(backend_result)
    request = _request()
    document = _normalized_document()
    engine = SchemaDrivenTextExtractionEngine(backend, request)
    result = asyncio.run(engine.extract(document, document_name="sample.txt"))
    return result, backend, request, document


def test_valid_json_schema_request_is_normalized_strict_and_frozen() -> None:
    request = SchemaDrivenTextExtractionRequest(
        schema_name="  sample schema  ",
        schema_version=1,
        json_schema=_schema(),
    )

    assert request.schema_name == "sample schema"
    assert set(request.__class__.model_fields) == {
        "schema_name",
        "schema_version",
        "json_schema",
    }

    with pytest.raises(ValidationError):
        request.schema_name = "other"


def test_invalid_json_schema_is_rejected_before_backend_call() -> None:
    backend = _InMemoryBackend(
        SchemaDrivenTextExtractionBackendResult(
            data={"category": "sample", "score": 1.0},
        )
    )

    with pytest.raises(ValidationError):
        SchemaDrivenTextExtractionRequest(
            schema_name="invalid schema",
            schema_version=1,
            json_schema={
                "type": "object",
                "properties": {"score": {"type": 123}},
            },
        )

    assert backend.calls == 0


def test_non_object_root_schema_is_rejected() -> None:
    with pytest.raises(ValidationError):
        SchemaDrivenTextExtractionRequest(
            schema_name="array schema",
            schema_version=1,
            json_schema={"type": "array", "items": {"type": "string"}},
        )


def test_request_unknown_field_is_rejected() -> None:
    with pytest.raises(ValidationError):
        SchemaDrivenTextExtractionRequest.model_validate(
            {
                "schema_name": "sample schema",
                "schema_version": 1,
                "json_schema": _schema(),
                "unexpected": "value",
            }
        )


def test_backend_result_is_narrow_and_rejects_unknown_fields() -> None:
    assert set(SchemaDrivenTextExtractionBackendResult.model_fields) == {
        "data",
        "confidence",
    }

    with pytest.raises(ValidationError):
        SchemaDrivenTextExtractionBackendResult.model_validate(
            {
                "data": {"category": "sample", "score": 1.0},
                "confidence": 0.5,
                "validation_status": "valid",
            }
        )


@pytest.mark.parametrize("confidence", [-0.01, 1.01])
def test_backend_result_rejects_confidence_outside_unit_interval(
    confidence: float,
) -> None:
    with pytest.raises(ValidationError):
        SchemaDrivenTextExtractionBackendResult(
            data={"category": "sample", "score": 1.0},
            confidence=confidence,
        )


def test_valid_backend_data_preserves_input_request_output_and_confidence() -> None:
    backend_data = {"category": "sample", "score": 0.75}
    backend = _InMemoryBackend(
        SchemaDrivenTextExtractionBackendResult(
            data=backend_data,
            confidence=0.83,
        )
    )
    request = _request()
    document = _normalized_document()
    serialized_before = document.model_dump_json()
    document_id_before = document.document_id
    fingerprint_before = document.fingerprint
    segment_ids_before = [segment.segment_id for segment in document.segments]
    engine = SchemaDrivenTextExtractionEngine(backend, request)

    result = asyncio.run(engine.extract(document, document_name="sample.txt"))

    assert backend.calls == 1
    assert backend.received_content is document
    assert backend.received_request is request
    assert backend.received_document_name == "sample.txt"

    assert type(result) is StructuredExtractionResult
    assert result.engine == "schema_driven_text_v1:in_memory_test"
    assert result.document_type == document.document_type
    assert result.data == backend_data
    assert set(result.data) == {"category", "score"}
    assert result.confidence == 0.83
    assert result.validation_status == "valid"
    assert type(result.validation) is StructuredValidationResult
    assert result.validation.status == "valid"
    assert result.validation.checks["json_schema"].status == "passed"
    assert result.validation.confidence == 1.0

    assert document.model_dump_json() == serialized_before
    assert document.document_id == document_id_before
    assert document.fingerprint == fingerprint_before
    assert [segment.segment_id for segment in document.segments] == segment_ids_before
    assert backend.received_content.segments is document.segments
    assert backend.received_content.participants is document.participants


def test_engine_name_is_stable_and_uses_backend_identity_only() -> None:
    backend = _InMemoryBackend(
        SchemaDrivenTextExtractionBackendResult(
            data={"category": "sample", "score": 1.0},
        ),
        name="deterministic_backend_v1",
    )

    first = SchemaDrivenTextExtractionEngine(backend, _request())
    second = SchemaDrivenTextExtractionEngine(backend, _request())

    assert first.name == "schema_driven_text_v1:deterministic_backend_v1"
    assert second.name == first.name


def test_invalid_data_returns_existing_result_and_preserves_backend_data() -> None:
    backend_data = {"category": 7, "extra": True}
    result, backend, _, _ = _run(backend_data)

    assert type(result) is StructuredExtractionResult
    assert result.data == backend_data
    assert backend.result.data == backend_data
    assert result.validation_status == "invalid"
    assert type(result.validation) is StructuredValidationResult
    assert result.validation.status == "invalid"
    assert result.validation.checks["json_schema"].status == "failed"
    assert result.validation.confidence == 0.0


def test_validation_error_details_are_deterministic() -> None:
    backend_result = SchemaDrivenTextExtractionBackendResult(
        data={"category": 7, "extra": True},
        confidence=0.5,
    )
    backend = _InMemoryBackend(backend_result)
    engine = SchemaDrivenTextExtractionEngine(backend, _request())
    document = _normalized_document()

    first = asyncio.run(engine.extract(document))
    second = asyncio.run(engine.extract(document))

    first_errors = first.validation.checks["json_schema"].details["errors"]
    second_errors = second.validation.checks["json_schema"].details["errors"]

    assert first_errors == second_errors
    assert first_errors == sorted(
        first_errors,
        key=lambda error: (
            error["path"],
            error["schema_path"],
            error["validator"],
            error["message"],
        ),
    )


def test_additional_properties_false_is_honored() -> None:
    result, _, _, _ = _run(
        {"category": "sample", "score": 0.5, "unexpected": "value"}
    )

    assert result.validation_status == "invalid"
    errors = result.validation.checks["json_schema"].details["errors"]
    assert any(error["validator"] == "additionalProperties" for error in errors)
    assert result.data["unexpected"] == "value"


def test_required_fields_are_honored() -> None:
    result, _, _, _ = _run({"category": "sample"})

    assert result.validation_status == "invalid"
    errors = result.validation.checks["json_schema"].details["errors"]
    assert any(error["validator"] == "required" for error in errors)


def test_types_are_honored_without_coercion() -> None:
    result, _, _, _ = _run({"category": "sample", "score": "0.75"})

    assert result.validation_status == "invalid"
    assert result.data["score"] == "0.75"
    assert isinstance(result.data["score"], str)
    errors = result.validation.checks["json_schema"].details["errors"]
    assert any(error["validator"] == "type" for error in errors)


def test_backend_exception_is_not_masked() -> None:
    engine = SchemaDrivenTextExtractionEngine(_RaisingBackend(), _request())

    with pytest.raises(RuntimeError, match="synthetic backend failure"):
        asyncio.run(engine.extract(_normalized_document()))


def test_df04_production_module_has_no_provider_or_network_client_imports() -> None:
    source = inspect.getsource(schema_driven_text_module)
    tree = ast.parse(source)
    imported_roots: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".", 1)[0])

    assert imported_roots.isdisjoint(
        {
            "aiohttp",
            "anthropic",
            "httpx",
            "openai",
            "requests",
            "socket",
            "urllib",
        }
    )
