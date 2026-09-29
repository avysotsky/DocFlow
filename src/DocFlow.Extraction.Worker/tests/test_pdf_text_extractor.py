from pathlib import Path

import pymupdf

from docflow_worker.pdf_text_extractor import PdfTextExtractor


def test_extracts_text_from_text_pdf(tmp_path: Path) -> None:
    pdf_path = tmp_path / "sample.pdf"

    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), "DocFlow test invoice")
    document.save(pdf_path)
    document.close()

    result = PdfTextExtractor().extract(pdf_path)

    assert result.page_count == 1
    assert result.pages_with_text == 1
    assert result.empty_page_numbers == []
    assert result.needs_ocr is False
    assert "DocFlow test invoice" in result.text


def test_marks_image_only_or_empty_pdf_for_ocr(tmp_path: Path) -> None:
    pdf_path = tmp_path / "scan.pdf"

    document = pymupdf.open()
    document.new_page()
    document.save(pdf_path)
    document.close()

    result = PdfTextExtractor().extract(pdf_path)

    assert result.page_count == 1
    assert result.pages_with_text == 0
    assert result.empty_page_numbers == [1]
    assert result.needs_ocr is True
