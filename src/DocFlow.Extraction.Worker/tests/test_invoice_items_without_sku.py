import asyncio
from decimal import Decimal

from docflow_worker.engines import DeterministicSupplierInvoiceEngine
from docflow_worker.models import DocumentContent, PageContent
from docflow_worker.supplier_invoice_models import SupplierInvoiceData
from docflow_worker.validators import SupplierInvoiceValidator


def test_borderless_invoice_items_do_not_require_sku() -> None:
    content = DocumentContent(
        pages=[
            PageContent(
                page_number=1,
                width=595,
                height=842,
                text=(
                    "TAX INVOICE\n"
                    "Invoice Number    INV-1021\n"
                    "Description    Quantity    Unit Price    VAT    Amount GBP\n"
                    "Professional services    1.00    210.00    20%    210.00\n"
                    "Subtotal    210.00\n"
                    "TOTAL VAT 20%    42.00\n"
                    "TOTAL GBP    252.00\n"
                ),
                words=[],
                blocks=[],
                tables=[],
            )
        ]
    )

    result = asyncio.run(DeterministicSupplierInvoiceEngine().extract(content))
    invoice = SupplierInvoiceData.model_validate(result.data)
    validation = SupplierInvoiceValidator().validate(invoice)

    assert len(invoice.items) == 1
    assert invoice.items[0].sku is None
    assert invoice.items[0].description == "Professional services"
    assert invoice.items[0].quantity == Decimal("1.00")
    assert invoice.items[0].unit_price == Decimal("210.00")
    assert invoice.items[0].line_total == Decimal("210.00")
    assert invoice.subtotal == Decimal("210.00")
    assert invoice.vat_rate == Decimal("20")
    assert invoice.vat_amount == Decimal("42.00")
    assert invoice.total == Decimal("252.00")
    assert validation.status == "valid"
    assert validation.confidence == 1.0
