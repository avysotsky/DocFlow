from typing import Any

from pydantic import BaseModel, Field


class StructuredExtractionResult(BaseModel):
    """Provider-neutral result returned by a future ONNX or LLM extraction engine."""

    engine: str
    document_type: str | None = None
    data: dict[str, Any]
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
