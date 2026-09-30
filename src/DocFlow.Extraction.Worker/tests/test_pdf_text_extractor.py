from pathlib import Path

import pymupdf
import pytest

from docflow_worker.pdf_content_extractor import PdfContentExtractor


def test_extracts_text_blocks_words_and_coordinates(tmp_path: Path) -> None:
    pdf_path = tmp_path / "sample.pdf"

    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), "DocFlow test invoice")
    document.save(pdf_path)
    document.close()

    content = PdfContentExtractor().extract(pdf_path)

    assert content.page_count == 1
    assert content.pages_with_text == 1
    assert content.empty_page_numbers == []
    assert content.needs_ocr is False
    assert content.ocr_applied is False
    assert content.ocr_page_numbers == []
    assert "DocFlow test invoice" in content.text

    page_content = content.pages[0]
    assert page_content.width > 0
    assert page_content.height > 0
    assert page_content.blocks
    assert page_content.words
    assert page_content.words[0].text == "DocFlow"
    assert page_content.words[0].bbox.x1 > page_content.words[0].bbox.x0
    assert page_content.words[0].bbox.y1 > page_content.words[0].bbox.y0


def test_extracts_grid_table(tmp_path: Path) -> None:
    pdf_path = tmp_path / "table.pdf"

    document = pymupdf.open()
    page = document.new_page()

    for y in (120, 160, 200):
        page.draw_line((72, y), (300, y))
    for x in (72, 180, 300):
        page.draw_line((x, 120), (x, 200))

    page.insert_text((82, 145), "Item")
    page.insert_text((190, 145), "Price")
    page.insert_text((82, 185), "AX-100")
    page.insert_text((190, 185), "12.50")

    document.save(pdf_path)
    document.close()

    content = PdfContentExtractor().extract(pdf_path)

    assert content.table_count == 1
    table = content.pages[0].tables[0]
    assert table.row_count == 2
    assert table.column_count == 2
    assert table.rows[0] == ["Item", "Price"]
    assert table.rows[1] == ["AX-100", "12.50"]


def test_marks_image_only_or_empty_pdf_for_ocr(tmp_path: Path) -> None:
    pdf_path = tmp_path / "scan.pdf"

    document = pymupdf.open()
    document.new_page()
    document.save(pdf_path)
    document.close()

    content = PdfContentExtractor().extract(pdf_path)

    assert content.page_count == 1
    assert content.pages_with_text == 0
    assert content.empty_page_numbers == [1]
    assert content.needs_ocr is True
    assert content.ocr_applied is False


def test_ocr_extracts_text_from_image_only_pdf(tmp_path: Path) -> None:
    try:
        tessdata = pymupdf.get_tessdata()
    except Exception:
        pytest.skip("Tesseract tessdata is not available in this environment.")

    source = pymupdf.open()
    source_page = source.new_page(width=595, height=842)
    source_page.insert_textbox(
        pymupdf.Rect(60, 100, 535, 220),
        "DOCFLOW SCANNED INVOICE\nInvoice No. INV-2026-091",
        fontsize=24,
    )
    pixmap = source_page.get_pixmap(dpi=200, alpha=False)
    source.close()

    pdf_path = tmp_path / "scanned-text.pdf"
    scanned = pymupdf.open()
    scanned_page = scanned.new_page(width=595, height=842)
    scanned_page.insert_image(scanned_page.rect, pixmap=pixmap)
    scanned.save(pdf_path)
    scanned.close()

    without_ocr = PdfContentExtractor().extract(pdf_path)
    assert without_ocr.needs_ocr is True

    content = PdfContentExtractor(
        enable_ocr=True,
        ocr_language="eng",
        ocr_dpi=300,
        tessdata=tessdata,
    ).extract(pdf_path)

    assert content.page_count == 1
    assert content.ocr_applied is True
    assert content.ocr_page_numbers == [1]
    assert content.needs_ocr is False
    assert "DOCFLOW" in content.text.upper()
    assert "INVOICE" in content.text.upper()
    assert content.pages[0].words
