from abc import ABC, abstractmethod

from docflow_worker.models import StructuredExtractionResult
from docflow_worker.text_document_models import NormalizedTextDocument


class TextStructuredExtractionEngine(ABC):
    """Abstraction for semantic extraction from a validated normalized text document."""

    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    async def extract(
        self,
        content: NormalizedTextDocument,
        *,
        document_name: str | None = None,
    ) -> StructuredExtractionResult:
        raise NotImplementedError
