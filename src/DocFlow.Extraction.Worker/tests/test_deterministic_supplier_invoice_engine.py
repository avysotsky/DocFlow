import asyncio
from datetime import date
from decimal import Decimal

from docflow_worker.engines import DeterministicSupplierInvoiceEngine
from docflow_worker.models import BoundingBox, DocumentContent, PageContent, TableContent, TextBlockContent
from docflow_worker.supplier_invoice_models import SupplierInvoiceData
from docflow_worker.validators import SupplierInvoiceValidator


def _bbox(y0: float = 0, y1: float = 10) -> BoundingBox:
    return BoundingBox(x0=0, y0=y0, x1=500, y1=y1)


def test_extracts_and_validates_supplier_invoice() -> None:
    content = DocumentContent(
        pages=[
            PageContent(
                page_number=1,
                width=595,
                height=842,
                text=(
                    "Invoice No. INV-2026-091 Currency EUR\n"
                    "Invoice Date 2026-09-30 Due Date 2026-10-30"
                ),
                words=[],
                blocks=[
                    TextBlockContent(
                        block_number=0,
                        text=(
                            "ACME Components Ltd.\n"
                            "VAT ID: DE314159265\n"
                            "billing@acme-components.example"
                        ),
                        bbox=_bbox(10, 40),
                    ),
                    TextBlockContent(
                        block_number=1,
                        text="Subtotal: 560.00 EUR",
                        bbox=_bbox(400, 420),
                    ),
                    TextBlockContent(
                        block_number=2,
                        text="VAT 20%: 112.00 EUR",
                        bbox=_bbox(420, 440),
                    ),
                    TextBlockContent(
                        block_number=3,
                        text="Total: 672.00 EUR",
                        bbox=_bbox(440, 460),
                    ),
                    TextBlockContent(
                        block_number=4,
                        text="Payment terms: Net 30",
                        bbox=_bbox(480, 500),
                    ),
                ],
                tables=[
                    TableContent(
                        bbox=_bbox(100, 180),
                        rows=[
                            ["Invoice No.", "INV-2026-091", "Currency", "EUR"],
                            ["Invoice Date", "2026-09-30", "Due Date", "2026-10-30"],
                            ["Customer Ref.", "PO-78421", "PO No.", "PO-78421"],
                        ],
                    ),
                    TableContent(
                        bbox=_bbox(200, 380),
                        rows=[
                            [
                                "SKU",
                                "Description",
                                "Qty",
                                "Unit",
                                "Unit Price (EUR)",
                                "Line Total (EUR)",
                            ],
                            ["AX-100", "Sensor bracket", "20", "pcs", "12.50", "250.00"],
                            ["BX-240", "Junction box", "8", "pcs", "38.75", "310.00"],
                        ],
                    ),
                ],
            )
        ]
    )

    result = asyncio.run(DeterministicSupplierInvoiceEngine().extract(content))
    invoice = SupplierInvoiceData.model_validate(result.data)
    validation = SupplierInvoiceValidator().validate(invoice)

    assert result.engine == "deterministic_supplier_invoice_v1"
    assert result.document_type == "supplier_invoice"
    assert invoice.supplier_name == "ACME Components Ltd."
    assert invoice.invoice_number == "INV-2026-091"
    assert invoice.invoice_date == date(2026, 9, 30)
    assert invoice.due_date == date(2026, 10, 30)
    assert invoice.currency == "EUR"
    assert invoice.customer_reference == "PO-78421"
    assert invoice.purchase_order_number == "PO-78421"
    assert invoice.payment_terms == "Net 30"

    assert len(invoice.items) == 2
    assert invoice.items[0].sku == "AX-100"
    assert invoice.items[0].quantity == Decimal("20")
    assert invoice.items[0].unit_price == Decimal("12.50")
    assert invoice.items[0].line_total == Decimal("250.00")

    assert invoice.subtotal == Decimal("560.00")
    assert invoice.vat_rate == Decimal("20")
    assert invoice.vat_amount == Decimal("112.00")
    assert invoice.total == Decimal("672.00")
    assert validation.status == "valid"
    assert validation.confidence == 1.0


def test_extracts_split_tzs_totals_from_public_proforma_text() -> None:
    content = DocumentContent(
        pages=[
            PageContent(
                page_number=1,
                width=595,
                height=842,
                text=(
                    "PROFORMA INVOICE\n"
                    "Unit Price(TZS)\n"
                    "Total(TZS)\n"
                    "SUB TOTAL(TZS)\n"
                    "60,762.71\n"
                    "VAT(TZS)\n"
                    "10,937.29\n"
                    "GRAND TOTAL(TZS)\n"
                    "71,700.00\n"
                ),
                words=[],
                blocks=[],
                tables=[],
            )
        ]
    )

    result = asyncio.run(DeterministicSupplierInvoiceEngine().extract(content))
    invoice = SupplierInvoiceData.model_validate(result.data)

    assert invoice.currency == "TZS"
    assert invoice.subtotal == Decimal("60762.71")
    assert invoice.vat_amount == Decimal("10937.29")
    assert invoice.total == Decimal("71700.00")


def test_extracts_symbol_currency_and_derives_missing_subtotal() -> None:
    content = DocumentContent(
        pages=[
            PageContent(
                page_number=1,
                width=595,
                height=842,
                text=(
                    "PROFORMA INVOICE TO:\n"
                    "COST OF VEHICLE £35,000.00\n"
                    "SCW SIDE STEP £ 2,000.00\n"
                    "VAT @ 20% £ 7,400.00\n"
                    "TOTAL £44,400.00\n"
                ),
                words=[],
                blocks=[],
                tables=[],
            )
        ]
    )

    result = asyncio.run(DeterministicSupplierInvoiceEngine().extract(content))
    invoice = SupplierInvoiceData.model_validate(result.data)

    assert invoice.currency == "GBP"
    assert invoice.subtotal == Decimal("37000.00")
    assert invoice.vat_rate == Decimal("20")
    assert invoice.vat_amount == Decimal("7400.00")
    assert invoice.total == Decimal("44400.00")
