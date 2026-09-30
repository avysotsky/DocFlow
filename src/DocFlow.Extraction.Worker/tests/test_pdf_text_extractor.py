from pathlib import Path

import pymupdf

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
