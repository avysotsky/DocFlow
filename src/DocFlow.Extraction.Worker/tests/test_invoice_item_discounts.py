from decimal import Decimal

from docflow_worker.engines.deterministic_supplier_invoice import (
    DeterministicSupplierInvoiceEngine,
)
from docflow_worker.models import BoundingBox, TableContent


def test_extracts_invoice_item_discount_rate() -> None:
    table = TableContent(
        bbox=BoundingBox(x0=0, y0=0, x1=500, y1=100),
        rows=[
            ["Description", "Qty", "Unit Price", "Discount", "Amount"],
            ["Magazine subscription", "1", "69.00", "30%", "48.30"],
        ],
    )

    items = DeterministicSupplierInvoiceEngine._extract_invoice_items(table)

    assert len(items) == 1
    assert items[0].quantity == Decimal("1")
    assert items[0].unit_price == Decimal("69.00")
    assert items[0].discount_rate == Decimal("30")
    assert items[0].line_total == Decimal("48.30")
