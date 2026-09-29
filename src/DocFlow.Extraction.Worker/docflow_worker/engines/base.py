from abc import ABC, abstractmethod

from docflow_worker.models import StructuredExtractionResult


class StructuredExtractionEngine(ABC):
    """Abstraction implemented later by local ONNX and external LLM engines."""

    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    async def extract(
        self,
        text: str,
        *,
        document_name: str | None = None,
    ) -> StructuredExtractionResult:
        raise NotImplementedError
