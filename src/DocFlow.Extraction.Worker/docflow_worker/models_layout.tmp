from typing import Any

from pydantic import BaseModel, Field, computed_field


class BoundingBox(BaseModel):
    x0: float
    y0: float
    x1: float
    y1: float


class WordContent(BaseModel):
    text: str
    bbox: BoundingBox
    block_number: int
    line_number: int
    word_number: int


class TextBlockContent(BaseModel):
    block_number: int
    text: str
    bbox: BoundingBox


class TableContent(BaseModel):
    bbox: BoundingBox
    rows: list[list[str | None]]

    @computed_field
    @property
    def row_count(self) -> int:
        return len(self.rows)

    @computed_field
    @property
    def column_count(self) -> int:
        return max((len(row) for row in self.rows), default=0)


class PageContent(BaseModel):
    page_number: int
    width: float
    height: float
    text: str
    blocks: list[TextBlockContent]
    words: list[WordContent]
    tables: list[TableContent]

    @computed_field
    @property
    def has_text(self) -> bool:
        return bool(self.text.strip())


class DocumentContent(BaseModel):
    """Provider-neutral representation of a parsed document before semantic extraction."""

    pages: list[PageContent]

    @computed_field
    @property
    def page_count(self) -> int:
        return len(self.pages)

    @computed_field
    @property
    def text(self) -> str:
        return "\n\n\f\n\n".join(page.text for page in self.pages).strip()

    @computed_field
    @property
    def pages_with_text(self) -> int:
        return sum(1 for page in self.pages if page.has_text)

    @computed_field
    @property
    def empty_page_numbers(self) -> list[int]:
        return [page.page_number for page in self.pages if not page.has_text]

    @computed_field
    @property
    def needs_ocr(self) -> bool:
        return self.page_count > 0 and self.pages_with_text == 0

    @computed_field
    @property
    def table_count(self) -> int:
        return sum(len(page.tables) for page in self.pages)


class StructuredExtractionResult(BaseModel):
    """Provider-neutral result returned by a future ONNX or LLM extraction engine."""

    engine: str
    document_type: str | None = None
    data: dict[str, Any]
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
