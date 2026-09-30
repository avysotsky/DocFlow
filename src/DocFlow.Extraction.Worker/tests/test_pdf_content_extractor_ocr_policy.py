from docflow_worker.pdf_content_extractor import PdfContentExtractor


def test_empty_page_requires_ocr() -> None:
    assert PdfContentExtractor._should_apply_ocr("", has_images=False)


def test_sparse_native_text_with_image_requires_ocr() -> None:
    caption = "Figure 6a Planned delivery receipt"

    assert PdfContentExtractor._should_apply_ocr(caption, has_images=True)


def test_sparse_native_text_without_image_does_not_require_ocr() -> None:
    caption = "Short native-text page"

    assert not PdfContentExtractor._should_apply_ocr(caption, has_images=False)


def test_rich_native_text_with_image_does_not_require_ocr() -> None:
    native_text = "A" * PdfContentExtractor._sparse_native_text_threshold

    assert not PdfContentExtractor._should_apply_ocr(native_text, has_images=True)
