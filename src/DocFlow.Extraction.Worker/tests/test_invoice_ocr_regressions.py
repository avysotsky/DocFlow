import asyncio
from decimal import Decimal

from docflow_worker.engines import DeterministicSupplierInvoiceEngine
from docflow_worker.models import DocumentContent, PageContent
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
