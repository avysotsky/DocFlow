import ast
import importlib.util
import json
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

import docflow_worker.text_artifact_pipeline as pipeline_module


def _load_cli_module():
    path = Path(__file__).resolve().parents[1] / "text_artifact_main.py"
    spec = importlib.util.spec_from_file_location("df06_text_artifact_main", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


cli_module = _load_cli_module()
from docflow_worker.engines import (
    SchemaDrivenTextExtractionBackend,
    SchemaDrivenTextExtractionBackendResult,
    SchemaDrivenTextExtractionRequest,
)
from docflow_worker.models import StructuredExtractionResult
from docflow_worker.text_document_models import (
    NormalizedTextDocument,
    RawTextDocumentInput,
)
from docflow_worker.text_document_normalizer import TextDocumentNormalizer


def _raw_payload(*, secret: str = "PRIVATE-SYNTHETIC-TEXT") -> dict:
    return {
        "title": "  Synthetic document  ",
        "document_type": " generic_transcript ",
        "source": {
            "provider": " synthetic ",
            "source_document_id": " synthetic-006 ",
            "source_timestamp": "2026-10-01T10:00:00+03:00",
            "published_at": "2026-10-01T10:01:00+03:00",
            "retrieved_at": "2026-10-01T10:02:00+03:00",
        },
        "participants": [
            {
                "participant_id": " speaker-a ",
                "display_name": " Speaker A ",
                "role": " host ",
                "organization": " Synthetic Org ",
            }
        ],
        "segments": [
            {
                "sequence": 2,
                "participant_id": " speaker-a ",
                "text": f" Second segment with {secret}. ",
            },
            {
                "sequence": 1,
                "participant_id": " speaker-a ",
                "text": " First segment. ",
            },
        ],
    }


def _schema_payload() -> dict:
    return {
        "schema_name": "generic extraction",
        "schema_version": 1,
        "json_schema": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "additionalProperties": False,
            "required": ["category", "score"],
            "properties": {
                "category": {"type": "string"},
                "score": {"type": "number"},
            },
        },
    }


def _write_inputs(tmp_path: Path) -> tuple[Path, Path]:
    raw_path = tmp_path / "input" / "raw.json"
    schema_path = tmp_path / "input" / "schema.json"
    raw_path.parent.mkdir(parents=True)
    raw_path.write_text(json.dumps(_raw_payload()), encoding="utf-8")
    schema_path.write_text(json.dumps(_schema_payload()), encoding="utf-8")
    return raw_path, schema_path


class _FakeBackend(SchemaDrivenTextExtractionBackend):
    def __init__(
        self,
        data: dict | None = None,
        *,
        error: Exception | None = None,
    ) -> None:
        self.data = data or {"category": "sample", "score": 0.75}
        self.error = error
        self.calls = 0
        self.received_content: NormalizedTextDocument | None = None
        self.received_request: SchemaDrivenTextExtractionRequest | None = None
        self.received_document_name: str | None = None

    @property
    def name(self) -> str:
        return "df06_fake_backend"

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
        if self.error is not None:
            raise self.error
        return SchemaDrivenTextExtractionBackendResult(
            data=self.data,
            confidence=None,
        )


class _Factory:
    def __init__(self, backend: _FakeBackend) -> None:
        self.backend = backend
        self.models: list[str] = []

    def __call__(self, model: str) -> SchemaDrivenTextExtractionBackend:
        self.models.append(model)
        return self.backend


def _run_cli(
    tmp_path: Path,
    factory: _Factory,
    *,
    document_name: str | None = "synthetic.txt",
) -> tuple[int, Path, Path]:
    raw_path, schema_path = _write_inputs(tmp_path)
    normalized_path = tmp_path / "artifacts" / "normalized.json"
    structured_path = tmp_path / "artifacts" / "structured.json"
    argv = [
        "--input-raw-json",
        str(raw_path),
        "--schema-request",
        str(schema_path),
        "--model",
        "gpt-test-explicit",
        "--output-normalized-json",
        str(normalized_path),
        "--output-structured-json",
        str(structured_path),
    ]
    if document_name is not None:
        argv.extend(["--document-name", document_name])

    exit_code = cli_module.main(argv, backend_factory=factory)
    return exit_code, normalized_path, structured_path


def test_existing_raw_model_and_normalizer_drive_exact_normalized_artifact(
    tmp_path: Path,
) -> None:
    backend = _FakeBackend()
    factory = _Factory(backend)

    exit_code, normalized_path, _ = _run_cli(tmp_path, factory)

    raw = RawTextDocumentInput.model_validate(_raw_payload())
    expected = TextDocumentNormalizer().normalize(raw)
    actual = NormalizedTextDocument.model_validate_json(
        normalized_path.read_text(encoding="utf-8")
    )

    assert exit_code == 0
    assert actual == expected
    assert actual.document_id == expected.document_id
    assert actual.fingerprint == expected.fingerprint
    assert [segment.segment_id for segment in actual.segments] == [
        segment.segment_id for segment in expected.segments
    ]


def test_schema_request_parsing_and_same_normalized_instance_reach_existing_engine(
    tmp_path: Path,
) -> None:
    backend = _FakeBackend()
    factory = _Factory(backend)
    exit_code, normalized_path, structured_path = _run_cli(
        tmp_path,
        factory,
        document_name="artifact-source.txt",
    )

    normalized = NormalizedTextDocument.model_validate_json(
        normalized_path.read_text(encoding="utf-8")
    )
    structured = StructuredExtractionResult.model_validate_json(
        structured_path.read_text(encoding="utf-8")
    )

    assert exit_code == 0
    assert factory.models == ["gpt-test-explicit"]
    assert backend.calls == 1
    assert backend.received_content is not None
    assert backend.received_content == normalized
    assert backend.received_content.document_id == normalized.document_id
    assert backend.received_request == SchemaDrivenTextExtractionRequest.model_validate(
        _schema_payload()
    )
    assert backend.received_document_name == "artifact-source.txt"
    assert structured.engine == "schema_driven_text_v1:df06_fake_backend"
    assert structured.validation_status == "valid"
    assert structured.data == backend.data


def test_pipeline_passes_same_normalized_object_instance_to_backend(
    tmp_path: Path,
) -> None:
    backend = _FakeBackend()
    factory = _Factory(backend)
    raw_path, schema_path = _write_inputs(tmp_path)

    result = __import__("asyncio").run(
        pipeline_module.run_text_artifact_pipeline(
            input_raw_json=raw_path,
            schema_request=schema_path,
            model="gpt-test-explicit",
            output_normalized_json=tmp_path / "normalized.json",
            output_structured_json=tmp_path / "structured.json",
            backend_factory=factory,
            document_name="same-instance.txt",
        )
    )

    assert backend.received_content is result.normalized_document
    assert result.structured_result.engine == "schema_driven_text_v1:df06_fake_backend"


def test_invalid_schema_rejects_before_backend_factory_or_invocation(
    tmp_path: Path,
) -> None:
    raw_path, schema_path = _write_inputs(tmp_path)
    schema_path.write_text(
        json.dumps(
            {
                "schema_name": "invalid schema",
                "schema_version": 1,
                "json_schema": {
                    "type": "object",
                    "properties": {"score": {"type": 123}},
                },
            }
        ),
        encoding="utf-8",
    )
    backend = _FakeBackend()
    factory = _Factory(backend)

    with pytest.raises(ValidationError):
        __import__("asyncio").run(
            pipeline_module.run_text_artifact_pipeline(
                input_raw_json=raw_path,
                schema_request=schema_path,
                model="gpt-test-explicit",
                output_normalized_json=tmp_path / "normalized.json",
                output_structured_json=tmp_path / "structured.json",
                backend_factory=factory,
            )
        )

    assert factory.models == []
    assert backend.calls == 0
    assert (tmp_path / "normalized.json").exists()
    assert not (tmp_path / "structured.json").exists()


def test_model_is_required_and_unknown_arguments_fail() -> None:
    parser = cli_module.build_parser()
    common = [
        "--input-raw-json",
        "raw.json",
        "--schema-request",
        "schema.json",
        "--output-normalized-json",
        "normalized.json",
        "--output-structured-json",
        "structured.json",
    ]

    with pytest.raises(SystemExit) as missing_model:
        parser.parse_args(common)
    assert missing_model.value.code == 2

    with pytest.raises(SystemExit) as unknown:
        parser.parse_args(common + ["--model", "gpt-test", "--unexpected"])
    assert unknown.value.code == 2


def test_valid_result_creates_output_directories_and_writes_existing_result(
    tmp_path: Path,
) -> None:
    backend_data = {"category": "preserved", "score": 4.25}
    backend = _FakeBackend(backend_data)
    exit_code, normalized_path, structured_path = _run_cli(
        tmp_path,
        _Factory(backend),
    )

    result = StructuredExtractionResult.model_validate_json(
        structured_path.read_text(encoding="utf-8")
    )

    assert exit_code == 0
    assert normalized_path.parent.exists()
    assert structured_path.parent.exists()
    assert result.data == backend_data
    assert result.confidence is None
    assert result.validation_status == "valid"


def test_schema_invalid_result_is_written_unchanged_and_returns_nonzero(
    tmp_path: Path,
) -> None:
    backend_data = {"category": 7, "extra": True}
    backend = _FakeBackend(backend_data)
    exit_code, _, structured_path = _run_cli(tmp_path, _Factory(backend))

    result = StructuredExtractionResult.model_validate_json(
        structured_path.read_text(encoding="utf-8")
    )

    assert exit_code != 0
    assert result.data == backend_data
    assert result.validation_status == "invalid"
    assert result.validation is not None
    assert result.validation.status == "invalid"
    assert result.validation.checks["json_schema"].status == "failed"


@pytest.mark.parametrize("missing", ["raw", "schema"])
def test_missing_input_or_schema_file_returns_nonzero(
    tmp_path: Path,
    capsys,
    missing: str,
) -> None:
    raw_path, schema_path = _write_inputs(tmp_path)
    if missing == "raw":
        raw_path.unlink()
    else:
        schema_path.unlink()

    exit_code = cli_module.main(
        [
            "--input-raw-json",
            str(raw_path),
            "--schema-request",
            str(schema_path),
            "--model",
            "gpt-test-explicit",
            "--output-normalized-json",
            str(tmp_path / "normalized.json"),
            "--output-structured-json",
            str(tmp_path / "structured.json"),
        ],
        backend_factory=_Factory(_FakeBackend()),
    )

    captured = capsys.readouterr()
    assert exit_code != 0
    assert '"status": "error"' in captured.err


def test_provider_exception_returns_nonzero_without_secret_or_transcript_logging(
    tmp_path: Path,
    capsys,
) -> None:
    transcript_secret = "PRIVATE-SYNTHETIC-TEXT"
    provider_secret = "sk-synthetic-secret"
    backend = _FakeBackend(
        error=RuntimeError(
            f"provider failed with {provider_secret} and {transcript_secret}"
        )
    )

    exit_code, _, structured_path = _run_cli(tmp_path, _Factory(backend))
    captured = capsys.readouterr()
    combined = captured.out + captured.err

    assert exit_code != 0
    assert not structured_path.exists()
    assert transcript_secret not in combined
    assert provider_secret not in combined
    assert "RuntimeError" in captured.err


def test_console_success_is_bounded_and_contains_only_allowed_summary(
    tmp_path: Path,
    capsys,
) -> None:
    exit_code, normalized_path, structured_path = _run_cli(
        tmp_path,
        _Factory(_FakeBackend()),
    )
    captured = capsys.readouterr()

    assert exit_code == 0
    summary = json.loads(captured.out)
    assert set(summary) == {
        "documentId",
        "fingerprint",
        "segmentCount",
        "engine",
        "validationStatus",
        "outputNormalizedJson",
        "outputStructuredJson",
    }
    assert summary["outputNormalizedJson"] == str(normalized_path)
    assert summary["outputStructuredJson"] == str(structured_path)
    assert "PRIVATE-SYNTHETIC-TEXT" not in captured.out
    assert "sk-" not in captured.out


def test_cli_and_pipeline_do_not_import_or_call_openai_sdk_directly() -> None:
    for module in (cli_module, pipeline_module):
        source = Path(module.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported_roots: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_roots.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_roots.add(node.module.split(".", 1)[0])

        assert "openai" not in imported_roots
        assert ".responses.create(" not in source
        assert "AsyncOpenAI(" not in source


def test_legacy_pdf_main_remains_separate_from_text_artifact_cli() -> None:
    main_path = Path(__file__).resolve().parents[1] / "main.py"
    source = main_path.read_text(encoding="utf-8")

    assert "text_artifact" not in source
    assert "TextArtifact" not in source
