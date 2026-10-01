import asyncio
from decimal import Decimal

from docflow_worker.models import BoundingBox, DocumentContent, PageContent, TableContent
from docflow_worker.structured_pipeline import extract_structured_document
from docflow_worker.supplier_invoice_models import SupplierInvoiceData


TEXT = """
INVOICE
Invoice Date 21 Jul 2024
Invoice Number INV-0055
Currency GBP

Subtotal 190.00
TOTAL NO VAT 0.00
TOTAL GBP 190.00
""".strip()


def test_explicit_no_vat_label_completes_zero_tax_arithmetic() -> None:
    content = DocumentContent(
        pages=[
            PageContent(
                page_number=1,
                width=595,
                height=842,
                text=TEXT,
                blocks=[],
                words=[],
                tables=[
                    TableContent(
                        bbox=BoundingBox(x0=0, y0=100, x1=500, y1=300),
                        rows=[
                            ["Description", "Quantity", "Unit Price", "Amount"],
                            ["Grass cutting", "1.00", "190.00", "190.00"],
                        ],
                    )
                ],
            )
        ]
    )

    result = asyncio.run(extract_structured_document(content))
    invoice = SupplierInvoiceData.model_validate(result.data)

    assert result.document_type == "supplier_invoice"
    assert result.validation_status == "valid"
    assert invoice.invoice_number == "INV-0055"
    assert invoice.currency == "GBP"
    assert invoice.subtotal == Decimal("190.00")
    assert invoice.vat_rate == Decimal("0")
    assert invoice.vat_amount == Decimal("0.00")
    assert invoice.total == Decimal("190.00")

    assert result.validation is not None
    assert result.validation.checks["line_totals"].status == "passed"
    assert result.validation.checks["subtotal"].status == "passed"
    assert result.validation.checks["vat"].status == "passed"
    assert result.validation.checks["grand_total"].status == "passed"
