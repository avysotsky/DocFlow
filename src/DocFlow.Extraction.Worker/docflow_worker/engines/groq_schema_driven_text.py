from __future__ import annotations

import json
import os
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
_GROQ_BASE_URL = "https://api.groq.com/openai/v1"
_GROQ_API_KEY_ENV = "GROQ_API_KEY"


class GroqSchemaDrivenTextExtractionError(RuntimeError):
    """Fail-closed provider boundary error for Groq schema-driven extraction."""


class GroqSchemaDrivenTextExtractionBackend(SchemaDrivenTextExtractionBackend):
    """Groq Chat Completions backend for caller-supplied extraction schemas."""

    def __init__(self, model: str, *, client: Any | None = None) -> None:
        if not isinstance(model, str):
            raise TypeError("model must be a string.")

        self._model = normalize_identifier(model, "model")
        self._client = client if client is not None else self._build_default_client()
        self._name = f"groq_chat_completions_v1:{self._model}"

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
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": _EXTRACTION_INSTRUCTIONS},
                    {"role": "user", "content": serialized_document},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": _RESPONSE_FORMAT_NAME,
                        "strict": True,
                        "schema": request.json_schema,
                    },
                },
            )
        except Exception as error:
            raise GroqSchemaDrivenTextExtractionError(
                "Groq Chat Completions request failed "
                f"({type(error).__name__})."
            ) from None

        choices = getattr(response, "choices", None)
        if not choices:
            raise GroqSchemaDrivenTextExtractionError(
                "Groq Chat Completions returned no choices."
            )

        try:
            message = choices[0].message
        except (AttributeError, IndexError, KeyError, TypeError):
            raise GroqSchemaDrivenTextExtractionError(
                "Groq Chat Completions returned no assistant message."
            ) from None

        output_text = getattr(message, "content", None)
        if not isinstance(output_text, str) or not output_text.strip():
            raise GroqSchemaDrivenTextExtractionError(
                "Groq Chat Completions returned no structured output."
            )

        try:
            data = json.loads(output_text)
        except json.JSONDecodeError:
            raise GroqSchemaDrivenTextExtractionError(
                "Groq Chat Completions returned invalid JSON output."
            ) from None

        if not isinstance(data, dict):
            raise GroqSchemaDrivenTextExtractionError(
                "Groq Chat Completions structured output must be a JSON object."
            )

        return SchemaDrivenTextExtractionBackendResult(
            data=data,
            confidence=None,
        )

    @staticmethod
    def _build_default_client():
        api_key = os.environ.get(_GROQ_API_KEY_ENV)
        if api_key is None or not api_key.strip():
            raise GroqSchemaDrivenTextExtractionError(
                "GROQ_API_KEY is required for the Groq backend."
            )

        return AsyncOpenAI(
            api_key=api_key,
            base_url=_GROQ_BASE_URL,
        )

    @staticmethod
    def _serialize_document(content: NormalizedTextDocument) -> str:
        return json.dumps(
            content.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
