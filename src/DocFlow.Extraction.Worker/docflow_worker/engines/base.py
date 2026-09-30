from abc import ABC, abstractmethod

from docflow_worker.models import DocumentContent, StructuredExtractionResult


class StructuredExtractionEngine(ABC):
    """Abstraction implemented by deterministic, ONNX or external LLM engines."""

    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    async def extract(
        self,
        content: DocumentContent,
        *,
        document_name: str | None = None,
    ) -> StructuredExtractionResult:
        raise NotImplementedError
