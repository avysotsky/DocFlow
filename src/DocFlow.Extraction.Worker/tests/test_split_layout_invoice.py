import asyncio
from decimal import Decimal

from docflow_worker.models import DocumentContent, PageContent
from docflow_worker.structured_pipeline import extract_structured_document
from docflow_worker.supplier_invoice_models import SupplierInvoiceData


TEXT = """
TAX INVOICE
Invoice Date                    20 Aug 2025
Invoice Number                  INV-5383
VAT Number                      GB926762203

Description                     Quantity         Unit Price       VAT          Amount GBP

Domain procurement request
                                1.00             30.00            20%          30.00
Additional wrapped description text

Subtotal                        30.00
Total VAT 20%                   6.00
Invoice Total GBP               36.00
Total Net Payments GBP          0.00
Amount Due GBP                  36.00
""".strip()


def test_split_description_row_and_settlement_total_do_not_break_invoice() -> None:
    content = DocumentContent(
        pages=[
            PageContent(
                page_number=1,
                width=595,
                height=842,
                text=TEXT,
                blocks=[],
                words=[],
                tables=[],
            )
        ]
    )

    result = asyncio.run(extract_structured_document(content))
    invoice = SupplierInvoiceData.model_validate(result.data)

    assert result.document_type == "supplier_invoice"
    assert result.validation_status == "valid"
    assert invoice.invoice_number == "INV-5383"
    assert invoice.subtotal == Decimal("30.00")
    assert invoice.vat_rate == Decimal("20")
    assert invoice.vat_amount == Decimal("6.00")
    assert invoice.total == Decimal("36.00")

    assert len(invoice.items) == 1
    assert invoice.items[0].description == "Domain procurement request"
    assert invoice.items[0].quantity == Decimal("1.00")
    assert invoice.items[0].unit_price == Decimal("30.00")
    assert invoice.items[0].line_total == Decimal("30.00")

    assert result.validation is not None
    assert result.validation.checks["line_totals"].status == "passed"
    assert result.validation.checks["subtotal"].status == "passed"
    assert result.validation.checks["vat"].status == "passed"
    assert result.validation.checks["grand_total"].status == "passed"
