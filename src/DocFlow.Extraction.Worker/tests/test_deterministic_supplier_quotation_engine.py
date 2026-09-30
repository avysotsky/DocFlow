import asyncio
from datetime import date
from decimal import Decimal

from docflow_worker.engines import DeterministicSupplierQuotationEngine
from docflow_worker.models import (
    BoundingBox,
    DocumentContent,
    PageContent,
    TableContent,
    TextBlockContent,
)


def _bbox(y0: float = 0, y1: float = 10) -> BoundingBox:
    return BoundingBox(x0=0, y0=y0, x1=500, y1=y1)


def test_extracts_supplier_quotation_from_tables_and_blocks() -> None:
    content = DocumentContent(
        pages=[
            PageContent(
                page_number=1,
                width=595,
                height=842,
                text="Supplier quotation test",
                words=[],
                blocks=[
                    TextBlockContent(
                        block_number=0,
                        text=(
                            "ACME Components Ltd.\n"
                            "VAT ID: DE314159265\n"
                            "sales@acme-components.example"
                        ),
                        bbox=_bbox(10, 40),
                    ),
                    TextBlockContent(
                        block_number=1,
                        text="Subtotal\n1457.00 EUR",
                        bbox=_bbox(400, 420),
                    ),
                    TextBlockContent(
                        block_number=2,
                        text="VAT 20%\n291.40 EUR",
                        bbox=_bbox(420, 440),
                    ),
                    TextBlockContent(
                        block_number=3,
                        text="Total\n1748.40 EUR",
                        bbox=_bbox(440, 460),
                    ),
                    TextBlockContent(
                        block_number=4,
                        text="Payment terms: 30% advance, 70% before shipment.",
                        bbox=_bbox(500, 520),
                    ),
                    TextBlockContent(
                        block_number=5,
                        text="Prepared by: Martin Keller\nQuote status: Issued",
                        bbox=_bbox(520, 540),
                    ),
                ],
                tables=[
                    TableContent(
                        bbox=_bbox(100, 180),
                        rows=[
                            ["Quotation No.", "QT-2026-183", "Currency", "EUR"],
                            [
                                "Quotation Date",
                                "2026-09-30",
                                "Valid Until",
                                "2026-10-15",
                            ],
                            [
                                "Customer Ref.",
                                "RFQ-78421",
                                "Incoterms",
                                "DAP Odesa, Ukraine",
                            ],
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
                                "Unit Price\n(EUR)",
                                "Lead Time\n(days)",
                                "Line Total\n(EUR)",
                            ],
                            [
                                "AX-100",
                                "Stainless steel sensor bracket",
                                "20",
                                "pcs",
                                "12.50",
                                "5",
                                "250.00",
                            ],
                            [
                                "BX-240",
                                "IP67 junction box, 240 x 180 mm",
                                "8",
                                "pcs",
                                "38.75",
                                "7",
                                "310.00",
                            ],
                        ],
                    ),
                ],
            )
        ]
    )

    result = asyncio.run(DeterministicSupplierQuotationEngine().extract(content))

    assert result.engine == "deterministic_supplier_quotation_v1"
    assert result.document_type == "supplier_quotation"
    assert result.confidence is None

    data = result.data
    assert data["supplier_name"] == "ACME Components Ltd."
    assert data["quotation_number"] == "QT-2026-183"
    assert data["quotation_date"] == date(2026, 9, 30)
    assert data["valid_until"] == date(2026, 10, 15)
    assert data["currency"] == "EUR"
    assert data["customer_reference"] == "RFQ-78421"
    assert data["incoterms"] == "DAP Odesa, Ukraine"

    assert len(data["items"]) == 2
    assert data["items"][0]["sku"] == "AX-100"
    assert data["items"][0]["quantity"] == Decimal("20")
    assert data["items"][0]["unit_price"] == Decimal("12.50")
    assert data["items"][0]["lead_time_days"] == 5
    assert data["items"][0]["line_total"] == Decimal("250.00")

    assert data["subtotal"] == Decimal("1457.00")
    assert data["vat_rate"] == Decimal("20")
    assert data["vat_amount"] == Decimal("291.40")
    assert data["total"] == Decimal("1748.40")
    assert data["payment_terms"] == "30% advance, 70% before shipment."
    assert data["prepared_by"] == "Martin Keller"
    assert data["quote_status"] == "Issued"
