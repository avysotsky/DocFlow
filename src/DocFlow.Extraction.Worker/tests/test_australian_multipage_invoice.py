import asyncio
from datetime import date
from decimal import Decimal

from docflow_worker.models import DocumentContent, PageContent
from docflow_worker.structured_pipeline import extract_structured_document
from docflow_worker.supplier_invoice_models import SupplierInvoiceData


PAGE_1 = """
TAX INVOICE
Invoice #: 02706
DATE 14/05/2024

# Item                                               Price  Subtotal Adjustments             Subtotal
                                                            ordered                        as packed
3     2  Best Buy Bread White Sandwich 700g                 2.90        5.80                                5.80
3  0.534  Champagne Ham                                  17.99        9.00                                9.61

Invoice #: 02706 - Page 1 of 2
""".strip()

PAGE_2 = """
# Item                                               Price  Subtotal Adjustments             Subtotal
                                                            ordered                        as packed
3     1  Fab Fresh Frangipani Laundry Powder Detergent 1kg        6.50        6.50                                6.50
3     1  Free Delivery                                        0.00        0.00                                0.00

Total (inc GST)      21.91
Total includes GST of 1.99
Paid      21.91
Balance Due         0.00

Invoice #: 02706 - Page 2 of 2
""".strip()


def test_extracts_tax_inclusive_retail_invoice_across_pages() -> None:
    content = DocumentContent(
        pages=[
            PageContent(
                page_number=1,
                width=595,
                height=842,
                text=PAGE_1,
                blocks=[],
                words=[],
                tables=[],
            ),
            PageContent(
                page_number=2,
                width=595,
                height=842,
                text=PAGE_2,
                blocks=[],
                words=[],
                tables=[],
            ),
        ]
    )

    result = asyncio.run(extract_structured_document(content))
    invoice = SupplierInvoiceData.model_validate(result.data)

    assert result.document_type == "supplier_invoice"
    assert result.engine == "deterministic_supplier_invoice_v2"
    assert result.validation_status == "valid"

    assert invoice.invoice_number == "02706"
    assert invoice.invoice_date == date(2024, 5, 14)
    assert invoice.tax_inclusive is True
    assert invoice.subtotal == Decimal("19.92")
    assert invoice.vat_amount == Decimal("1.99")
    assert invoice.total == Decimal("21.91")

    assert len(invoice.items) == 4
    assert invoice.items[0].description == "Best Buy Bread White Sandwich 700g"
    assert invoice.items[1].quantity == Decimal("0.534")
    assert invoice.items[1].line_total == Decimal("9.61")
    assert invoice.items[2].description.startswith("Fab Fresh")

    assert result.validation is not None
    assert result.validation.checks["line_totals"].status == "passed"
    assert result.validation.checks["subtotal"].status == "passed"
    assert result.validation.checks["vat"].status == "passed"
    assert result.validation.checks["grand_total"].status == "passed"
