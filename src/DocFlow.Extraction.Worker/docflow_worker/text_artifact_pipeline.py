from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from docflow_worker.engines import (
    SchemaDrivenTextExtractionBackend,
    SchemaDrivenTextExtractionEngine,
    SchemaDrivenTextExtractionRequest,
)
from docflow_worker.models import StructuredExtractionResult
from docflow_worker.text_document_models import (
    NormalizedTextDocument,
    RawTextDocumentInput,
)
from docflow_worker.text_document_normalizer import TextDocumentNormalizer


BackendFactory = Callable[[str], SchemaDrivenTextExtractionBackend]


@dataclass(frozen=True)
class TextArtifactPipelineResult:
    normalized_document: NormalizedTextDocument
    structured_result: StructuredExtractionResult
    normalized_artifact_path: Path
    structured_artifact_path: Path


def _read_utf8(path: str | Path) -> str:
    return Path(path).read_text(encoding="utf-8")


def _write_model_json(path: str | Path, model) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(model.model_dump_json(indent=2), encoding="utf-8")
    return output_path


async def run_text_artifact_pipeline(
    *,
    input_raw_json: str | Path,
    schema_request: str | Path,
    model: str,
    output_normalized_json: str | Path,
    output_structured_json: str | Path,
    backend_factory: BackendFactory,
    document_name: str | None = None,
) -> TextArtifactPipelineResult:
    """Normalize raw text and produce schema-driven structured JSON artifacts."""

    raw = RawTextDocumentInput.model_validate_json(_read_utf8(input_raw_json))
    normalized = TextDocumentNormalizer().normalize(raw)

    normalized_path = _write_model_json(output_normalized_json, normalized)

    request = SchemaDrivenTextExtractionRequest.model_validate_json(
        _read_utf8(schema_request)
    )

    backend = backend_factory(model)
    engine = SchemaDrivenTextExtractionEngine(backend, request)
    structured = await engine.extract(
        normalized,
        document_name=document_name,
    )

    structured_path = _write_model_json(output_structured_json, structured)

    return TextArtifactPipelineResult(
        normalized_document=normalized,
        structured_result=structured,
        normalized_artifact_path=normalized_path,
        structured_artifact_path=structured_path,
    )
