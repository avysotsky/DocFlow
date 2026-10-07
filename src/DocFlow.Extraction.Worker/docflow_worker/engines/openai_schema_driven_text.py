from __future__ import annotations

import json
from typing import Any

from openai import AsyncOpenAI

from docflow_worker.engines.schema_driven_text import (
    SchemaDrivenTextExtractionBackend,
    SchemaDrivenTextExtractionBackendResult,
    SchemaDrivenTextExtractionRequest,
)
from docflow_worker.text_document_models import (
    NormalizedTextDocument,
    normalize_identifier,
)


_EXTRACTION_INSTRUCTIONS = (
    "Extract only information supported by the normalized document. "
    "Return only data matching the supplied caller schema. "
    "Do not invent unsupported facts. "
    "If the schema requests document, segment, or evidence identifiers, copy the exact "
    "identifiers from the normalized document without translating or altering them."
)
_RESPONSE_FORMAT_NAME = "docflow_schema"


class OpenAiSchemaDrivenTextExtractionError(RuntimeError):
    """Fail-closed provider boundary error for OpenAI schema-driven extraction."""


class OpenAiSchemaDrivenTextExtractionBackend(SchemaDrivenTextExtractionBackend):
    """OpenAI Responses API backend for caller-supplied structured extraction schemas."""

    def __init__(self, model: str, *, client: Any | None = None) -> None:
        if not isinstance(model, str):
            raise TypeError("model must be a string.")

        self._model = normalize_identifier(model, "model")
        self._client = client if client is not None else AsyncOpenAI()
        self._name = f"openai_responses_v1:{self._model}"

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
        del document_name

        serialized_document = self._serialize_document(content)

        try:
            response = await self._client.responses.create(
                model=self._model,
                instructions=_EXTRACTION_INSTRUCTIONS,
                input=serialized_document,
                text={
                    "format": {
                        "type": "json_schema",
                        "name": _RESPONSE_FORMAT_NAME,
                        "strict": True,
                        "schema": request.json_schema,
                    }
                },
                store=False,
            )
        except Exception as error:
            raise OpenAiSchemaDrivenTextExtractionError(
                "OpenAI Responses API request failed "
                f"({type(error).__name__})."
            ) from None

        status = getattr(response, "status", None)
        if status != "completed":
            raise OpenAiSchemaDrivenTextExtractionError(
                "OpenAI Responses API response was not completed "
                f"(status={status!r})."
            )

        output_text = getattr(response, "output_text", None)
        if not isinstance(output_text, str) or not output_text.strip():
            raise OpenAiSchemaDrivenTextExtractionError(
                "OpenAI Responses API returned no structured output."
            )

        try:
            data = json.loads(output_text)
        except json.JSONDecodeError:
            raise OpenAiSchemaDrivenTextExtractionError(
                "OpenAI Responses API returned invalid JSON output."
            ) from None

        if not isinstance(data, dict):
            raise OpenAiSchemaDrivenTextExtractionError(
                "OpenAI Responses API structured output must be a JSON object."
            )

        return SchemaDrivenTextExtractionBackendResult(
            data=data,
            confidence=None,
        )

    @staticmethod
    def _serialize_document(content: NormalizedTextDocument) -> str:
        return json.dumps(
            content.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
