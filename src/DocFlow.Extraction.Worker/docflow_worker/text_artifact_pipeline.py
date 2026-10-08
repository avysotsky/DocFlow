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
    normalized = normalize_text_document(raw)

    normalized_path = _write_model_json(output_normalized_json, normalized)

    request = SchemaDrivenTextExtractionRequest.model_validate_json(
        _read_utf8(schema_request)
    )

    structured = await extract_normalized_text(
        normalized, request, model=model,
        backend_factory=backend_factory, document_name=document_name,
    )

    structured_path = _write_model_json(output_structured_json, structured)

    return TextArtifactPipelineResult(
        normalized_document=normalized,
        structured_result=structured,
        normalized_artifact_path=normalized_path,
        structured_artifact_path=structured_path,
    )


def normalize_text_document(raw: RawTextDocumentInput) -> NormalizedTextDocument:
    """Application normalization used by both file-based CLI and HTTP transport."""
    return TextDocumentNormalizer().normalize(raw)


async def extract_normalized_text(
    normalized: NormalizedTextDocument,
    request: SchemaDrivenTextExtractionRequest,
    *,
    model: str,
    backend_factory: BackendFactory,
    document_name: str | None = None,
) -> StructuredExtractionResult:
    """The single provider-neutral application extraction boundary."""
    if not isinstance(model, str) or not model.strip():
        raise ValueError("An explicit model is required.")
    backend = backend_factory(model)
    engine = SchemaDrivenTextExtractionEngine(backend, request)
    return await engine.extract(normalized, document_name=document_name)


async def extract_text_document(
    raw: RawTextDocumentInput,
    request: SchemaDrivenTextExtractionRequest,
    *,
    model: str,
    backend_factory: BackendFactory,
    document_name: str | None = None,
) -> tuple[NormalizedTextDocument, StructuredExtractionResult]:
    """In-memory entrypoint for HTTP and future in-process composition."""
    normalized = normalize_text_document(raw)
    result = await extract_normalized_text(
        normalized, request, model=model,
        backend_factory=backend_factory, document_name=document_name,
    )
    return normalized, result
