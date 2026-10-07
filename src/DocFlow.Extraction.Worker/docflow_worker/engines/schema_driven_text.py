from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from docflow_worker.engines.text_base import TextStructuredExtractionEngine
from docflow_worker.models import (
    StructuredExtractionResult,
    StructuredValidationResult,
    ValidationCheckResult,
)
from docflow_worker.text_document_models import (
    NormalizedTextDocument,
    normalize_identifier,
)


class _StrictFrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class SchemaDrivenTextExtractionRequest(_StrictFrozenModel):
    """Caller-owned generic schema configuration for text extraction."""

    schema_name: str
    schema_version: int = Field(gt=0)
    json_schema: dict[str, Any]

    @field_validator("schema_name")
    @classmethod
    def _normalize_schema_name(cls, value: str) -> str:
        return normalize_identifier(value, "schema_name")

    @model_validator(mode="after")
    def _validate_json_schema(self) -> "SchemaDrivenTextExtractionRequest":
        try:
            Draft202012Validator.check_schema(self.json_schema)
        except SchemaError as error:
            raise ValueError(
                "json_schema must be a valid JSON Schema Draft 2020-12 schema: "
                f"{error.message}"
            ) from error

        if self.json_schema.get("type") != "object":
            raise ValueError('json_schema root must declare type "object".')

        return self


class SchemaDrivenTextExtractionBackendResult(_StrictFrozenModel):
    """Provider-neutral structured data returned before DocFlow validation."""

    data: dict[str, Any]
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class SchemaDrivenTextExtractionBackend(ABC):
    """Injected backend that produces caller-schema-shaped data from normalized text."""

    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    async def extract(
        self,
        content: NormalizedTextDocument,
        *,
        request: SchemaDrivenTextExtractionRequest,
        document_name: str | None = None,
    ) -> SchemaDrivenTextExtractionBackendResult:
        raise NotImplementedError


class SchemaDrivenTextExtractionEngine(TextStructuredExtractionEngine):
    """Validate backend data deterministically against a caller-supplied JSON Schema."""

    def __init__(
        self,
        backend: SchemaDrivenTextExtractionBackend,
        request: SchemaDrivenTextExtractionRequest,
    ) -> None:
        backend_name = backend.name
        if not isinstance(backend_name, str):
            raise TypeError("backend name must be a string.")

        normalized_backend_name = normalize_identifier(backend_name, "backend name")
        if normalized_backend_name != backend_name:
            raise ValueError("backend name must already be normalized.")

        self._backend = backend
        self._request = request
        self._validator = Draft202012Validator(request.json_schema)
        self._name = f"schema_driven_text_v1:{backend_name}"

    @property
    def name(self) -> str:
        return self._name

    async def extract(
        self,
        content: NormalizedTextDocument,
        *,
        document_name: str | None = None,
    ) -> StructuredExtractionResult:
        backend_result = await self._backend.extract(
            content,
            request=self._request,
            document_name=document_name,
        )

        errors = sorted(
            self._validator.iter_errors(backend_result.data),
            key=self._validation_error_sort_key,
        )

        if errors:
            check = ValidationCheckResult(
                status="failed",
                message="Backend data does not satisfy the caller JSON Schema.",
                details={
                    "errors": [
                        {
                            "path": self._instance_path(error.absolute_path),
                            "schema_path": self._schema_path(error.absolute_schema_path),
                            "validator": str(error.validator),
                            "message": error.message,
                        }
                        for error in errors
                    ]
                },
            )
            validation_status = "invalid"
            validation_confidence = 0.0
        else:
            check = ValidationCheckResult(
                status="passed",
                message="Backend data satisfies the caller JSON Schema.",
            )
            validation_status = "valid"
            validation_confidence = 1.0

        validation = StructuredValidationResult(
            status=validation_status,
            checks={"json_schema": check},
            confidence=validation_confidence,
        )

        return StructuredExtractionResult(
            engine=self.name,
            document_type=content.document_type,
            data=backend_result.data,
            confidence=backend_result.confidence,
            validation_status=validation_status,
            validation=validation,
        )

    @classmethod
    def _validation_error_sort_key(cls, error) -> tuple[str, str, str, str]:
        return (
            cls._instance_path(error.absolute_path),
            cls._schema_path(error.absolute_schema_path),
            str(error.validator),
            error.message,
        )

    @staticmethod
    def _instance_path(path) -> str:
        result = "$"
        for part in path:
            if isinstance(part, int):
                result += f"[{part}]"
            else:
                result += f"[{json.dumps(str(part), ensure_ascii=False)}]"
        return result

    @staticmethod
    def _schema_path(path) -> str:
        parts = [
            str(part).replace("~", "~0").replace("/", "~1")
            for part in path
        ]
        return "#" if not parts else "#/" + "/".join(parts)
