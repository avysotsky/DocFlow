import pytest

from docflow_worker.document_type_detector import detect_document_type
from docflow_worker.models import DocumentContent, PageContent


def _content(text: str) -> DocumentContent:
    return DocumentContent(
        pages=[
            PageContent(
                page_number=1,
                width=595,
                height=842,
                text=text,
                blocks=[],
                words=[],
                tables=[],
            )
        ]
    )


def test_detects_supplier_quotation() -> None:
    content = _content(
        "Quotation No. QT-2026-183\nQuotation Date 2026-09-30\nValid Until 2026-10-15"
    )

    assert detect_document_type(content) == "supplier_quotation"


def test_detects_supplier_invoice() -> None:
    content = _content(
        "Invoice No. INV-2026-091\nInvoice Date 2026-09-30\nDue Date 2026-10-30"
    )

    assert detect_document_type(content) == "supplier_invoice"


def test_rejects_unknown_document_type() -> None:
    with pytest.raises(ValueError, match="could not be detected"):
        detect_document_type(_content("Generic supplier document"))
