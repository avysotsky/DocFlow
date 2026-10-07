from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Sequence

from docflow_worker.engines import OpenAiSchemaDrivenTextExtractionBackend
from docflow_worker.text_artifact_pipeline import (
    BackendFactory,
    TextArtifactPipelineResult,
    run_text_artifact_pipeline,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Normalize a raw text document and produce a schema-driven structured artifact."
        )
    )
    parser.add_argument("--input-raw-json", required=True)
    parser.add_argument("--schema-request", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--output-normalized-json", required=True)
    parser.add_argument("--output-structured-json", required=True)
    parser.add_argument("--document-name")
    return parser


def _openai_backend_factory(model: str):
    return OpenAiSchemaDrivenTextExtractionBackend(model)


def _bounded_summary(result: TextArtifactPipelineResult) -> dict[str, object]:
    return {
        "documentId": result.normalized_document.document_id,
        "fingerprint": result.normalized_document.fingerprint,
        "segmentCount": len(result.normalized_document.segments),
        "engine": result.structured_result.engine,
        "validationStatus": result.structured_result.validation_status,
        "outputNormalizedJson": str(result.normalized_artifact_path),
        "outputStructuredJson": str(result.structured_artifact_path),
    }


def main(
    argv: Sequence[str] | None = None,
    *,
    backend_factory: BackendFactory | None = None,
) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    factory = backend_factory or _openai_backend_factory

    try:
        result = asyncio.run(
            run_text_artifact_pipeline(
                input_raw_json=args.input_raw_json,
                schema_request=args.schema_request,
                model=args.model,
                output_normalized_json=args.output_normalized_json,
                output_structured_json=args.output_structured_json,
                backend_factory=factory,
                document_name=args.document_name,
            )
        )
    except Exception as error:
        summary = {
            "status": "error",
            "errorType": type(error).__name__,
            "outputNormalizedJson": args.output_normalized_json,
            "outputStructuredJson": args.output_structured_json,
        }
        print(json.dumps(summary, ensure_ascii=False), file=sys.stderr)
        return 1

    print(json.dumps(_bounded_summary(result), ensure_ascii=False, indent=2))

    if result.structured_result.validation_status == "invalid":
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
