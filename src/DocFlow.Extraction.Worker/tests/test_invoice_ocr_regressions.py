import asyncio
from decimal import Decimal

from docflow_worker.engines import DeterministicSupplierInvoiceEngine
from docflow_worker.models import DocumentContent, PageContent
from docflow_worker.structured_pipeline import extract_structured_document
from docflow_worker.supplier_invoice_models import SupplierInvoiceData


def _content(text: str) -> DocumentContent:
    return DocumentContent(
        pages=[
            PageContent(
                page_number=1,
                width=595,
                height=842,
                text=text,
                words=[],
                blocks=[],
                tables=[],
                ocr_applied=True,
            )
        ]
    )


def test_trea_ocr_recovers_invoice_number_and_compact_grand_total() -> None:
    content = _content(
        """
Trea Kids PROFORMA INVOICE
Invoice Na: 1056
Curreuicy: EUR
SUBTOTAL €1 680.00
VAT 20% € 336,00
GRANDTOTAL €2 016,00
"""
    )

    result = asyncio.run(DeterministicSupplierInvoiceEngine().extract(content))
    invoice = SupplierInvoiceData.model_validate(result.data)

    assert invoice.invoice_number == "1056"
    assert invoice.currency == "EUR"
    assert invoice.subtotal == Decimal("1680.00")
    assert invoice.vat_amount == Decimal("336.00")
    assert invoice.total == Decimal("2016.00")


def test_jordan_ocr_prefers_currency_label_and_monetary_total_due() -> None:
    content = _content(
        """
Commercial Invoice
Invoice no./foreign-label 2019014782
Sub total 27,372.74
Total amount in words: Twenty-eight thousand six hundred seventy-two and 74 / 100 USD
Currency/ foreign-label: usD
Payment terms/ foreign-label: 100% CAD
Total due 28,672.74
"""
    )

    result = asyncio.run(DeterministicSupplierInvoiceEngine().extract(content))
    invoice = SupplierInvoiceData.model_validate(result.data)

    assert invoice.invoice_number == "2019014782"
    assert invoice.currency == "USD"
    assert invoice.subtotal == Decimal("27372.74")
    assert invoice.total == Decimal("28672.74")


def test_gross_total_still_beats_paid_balance() -> None:
    content = _content(
        """
TAX INVOICE
Invoice Number INV-23226
Subtotal 2.49
VAT 20% 0.50
TOTAL GBP 2.99
AMOUNT DUE GBP 0.00
"""
    )

    result = asyncio.run(DeterministicSupplierInvoiceEngine().extract(content))
    invoice = SupplierInvoiceData.model_validate(result.data)

    assert invoice.total == Decimal("2.99")


def test_degraded_ocr_recovers_textual_date_and_corrupted_vat_summary() -> None:
    content = _content(
        """
TAX INVOICE
Invoice No: WIR00286
Invoice Date: 18-Dec-13
Waste and Recycling £548,377.77
Street Cleansing £293,471.08
Bank Holiday £22,934.26
Sweeper refund £4,615.38 -
Sub Total FROeT a].
Terms: 28 days from invoice date
VATaoe@ 20% - i eee£172,033.55 ° 20| Cae
TOTAL £1,032,201.28
"""
    )

    result = asyncio.run(
        extract_structured_document(content, document_type="supplier_invoice")
    )
    invoice = SupplierInvoiceData.model_validate(result.data)

    assert invoice.invoice_number == "WIR00286"
    assert invoice.invoice_date.isoformat() == "2013-12-18"
    assert invoice.currency == "GBP"
    assert invoice.subtotal == Decimal("860167.73")
    assert invoice.vat_rate == Decimal("20")
    assert invoice.vat_amount == Decimal("172033.55")
    assert invoice.total == Decimal("1032201.28")
    assert result.validation_status == "incomplete"
