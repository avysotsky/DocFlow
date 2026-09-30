from pathlib import Path

import pymupdf

from docflow_worker.models import (
    BoundingBox,
    DocumentContent,
    PageContent,
    TableContent,
    TextBlockContent,
    WordContent,
)


class PdfContentExtractor:
    """Extracts layout-aware content and optionally OCRs pages without native text."""

    def __init__(
        self,
        *,
        enable_ocr: bool = False,
        ocr_language: str = "eng",
        ocr_dpi: int = 300,
        tessdata: str | None = None,
    ) -> None:
        if not ocr_language.strip():
            raise ValueError("OCR language is required when OCR is configured.")
        if ocr_dpi <= 0:
            raise ValueError("OCR DPI must be greater than zero.")

        self._enable_ocr = enable_ocr
        self._ocr_language = ocr_language.strip()
        self._ocr_dpi = ocr_dpi
        self._tessdata = tessdata

    def extract(self, pdf_path: str | Path) -> DocumentContent:
        path = Path(pdf_path)

        if path.suffix.lower() != ".pdf":
            raise ValueError("Only PDF files are supported.")
        if not path.is_file():
            raise FileNotFoundError(path)

        pages: list[PageContent] = []

        with pymupdf.open(path) as document:
            for page_number, page in enumerate(document, start=1):
                native_text = page.get_text("text", sort=True).strip()
                textpage = None
                ocr_applied = False

                if self._enable_ocr and not native_text:
                    try:
                        textpage = page.get_textpage_ocr(
                            language=self._ocr_language,
                            dpi=self._ocr_dpi,
                            full=True,
                            tessdata=self._tessdata,
                        )
                        ocr_applied = True
                    except Exception as exc:
                        raise RuntimeError(
                            f"OCR failed for page {page_number}. "
                            "Ensure Tesseract-OCR and the requested language data are installed."
                        ) from exc

                text = (
                    page.get_text("text", sort=True, textpage=textpage).strip()
                    if textpage is not None
                    else native_text
                )

                pages.append(
                    PageContent(
                        page_number=page_number,
                        width=float(page.rect.width),
                        height=float(page.rect.height),
                        text=text,
                        blocks=self._extract_blocks(page, textpage=textpage),
                        words=self._extract_words(page, textpage=textpage),
                        tables=self._extract_tables(page),
                        ocr_applied=ocr_applied,
                    )
                )

        return DocumentContent(pages=pages)

    @staticmethod
    def _bbox(values: tuple[float, float, float, float] | list[float]) -> BoundingBox:
        return BoundingBox(
            x0=float(values[0]),
            y0=float(values[1]),
            x1=float(values[2]),
            y1=float(values[3]),
        )

    def _extract_blocks(
        self,
        page: pymupdf.Page,
        *,
        textpage=None,
    ) -> list[TextBlockContent]:
        blocks: list[TextBlockContent] = []

        for raw_block in page.get_text("blocks", sort=True, textpage=textpage):
            # Text blocks have block_type == 0. Image blocks are intentionally skipped here.
            if len(raw_block) >= 7 and raw_block[6] != 0:
                continue

            text = str(raw_block[4]).strip()
            if not text:
                continue

            blocks.append(
                TextBlockContent(
                    block_number=int(raw_block[5]),
                    text=text,
                    bbox=self._bbox(raw_block[:4]),
                )
            )

        return blocks

    def _extract_words(
        self,
        page: pymupdf.Page,
        *,
        textpage=None,
    ) -> list[WordContent]:
        words: list[WordContent] = []

        for raw_word in page.get_text("words", sort=True, textpage=textpage):
            words.append(
                WordContent(
                    text=str(raw_word[4]),
                    bbox=self._bbox(raw_word[:4]),
                    block_number=int(raw_word[5]),
                    line_number=int(raw_word[6]),
                    word_number=int(raw_word[7]),
                )
            )

        return words

    def _extract_tables(self, page: pymupdf.Page) -> list[TableContent]:
        tables: list[TableContent] = []
        table_finder = page.find_tables(strategy="lines")

        for table in table_finder.tables:
            rows: list[list[str | None]] = []
            for raw_row in table.extract():
                rows.append(
                    [
                        cell.strip() if isinstance(cell, str) and cell.strip() else None
                        for cell in raw_row
                    ]
                )

            tables.append(
                TableContent(
                    bbox=self._bbox(table.bbox),
                    rows=rows,
                )
            )

        return tables
