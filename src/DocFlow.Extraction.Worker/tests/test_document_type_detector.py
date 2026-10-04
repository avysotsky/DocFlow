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


@pytest.mark.parametrize(
    "title",
    [
        "PROFORMA INVOICE",
        "Pro-Forma Invoice",
    ],
)
def test_detects_proforma_invoice_as_supplier_invoice(title: str) -> None:
    content = _content(
        f"{title}\nReference PR-46039\nPayment 100% advance\nGrand Total 71,700.00"
    )

    assert detect_document_type(content) == "supplier_invoice"


def test_rejects_unknown_document_type() -> None:
    with pytest.raises(ValueError, match="could not be detected"):
        detect_document_type(_content("Generic supplier document"))


def test_detects_purchase_order_without_confusing_invoice_po_reference() -> None:
    content = _content(
        "Purchase Order Number\nP5084955\nPurchase Order\n"
        "Order Number and Date must be quoted on Invoices\n"
        "Date : 03-NOV-2023\nSupplier Name and Address:\nCSL - KPMG LLP\n"
        "Description Quantity Unit Price Total Price"
    )

    assert detect_document_type(content) == "purchase_order"


def test_invoice_with_purchase_order_reference_remains_invoice() -> None:
    content = _content(
        "INVOICE\nInvoice No. INV-1001\nInvoice Date 2026-10-01\n"
        "Due Date 2026-10-31\nPurchase Order Number PO-44"
    )

    assert detect_document_type(content) == "supplier_invoice"
