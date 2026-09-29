from pathlib import Path

import pymupdf
from pydantic import BaseModel


class PdfTextExtractionResult(BaseModel):
    text: str
    page_count: int
    pages_with_text: int
    empty_page_numbers: list[int]
    needs_ocr: bool


class PdfTextExtractor:
    """Extracts the embedded text layer from a PDF without OCR."""

    def extract(self, pdf_path: str | Path) -> PdfTextExtractionResult:
        path = Path(pdf_path)

        if path.suffix.lower() != ".pdf":
            raise ValueError("Only PDF files are supported.")
        if not path.is_file():
            raise FileNotFoundError(path)

        page_texts: list[str] = []
        empty_page_numbers: list[int] = []

        with pymupdf.open(path) as document:
            for page_number, page in enumerate(document, start=1):
                text = page.get_text("text", sort=True).strip()
                page_texts.append(text)

                if not text:
                    empty_page_numbers.append(page_number)

            page_count = document.page_count

        pages_with_text = page_count - len(empty_page_numbers)
        combined_text = "\n\n\f\n\n".join(page_texts).strip()

        return PdfTextExtractionResult(
            text=combined_text,
            page_count=page_count,
            pages_with_text=pages_with_text,
            empty_page_numbers=empty_page_numbers,
            needs_ocr=page_count > 0 and pages_with_text == 0,
        )
