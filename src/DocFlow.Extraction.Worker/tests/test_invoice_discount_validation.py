from decimal import Decimal

from docflow_worker.supplier_invoice_models import SupplierInvoiceData, SupplierInvoiceItem
from docflow_worker.validators import SupplierInvoiceValidator


def test_validates_discounted_invoice_line_total() -> None:
    invoice = SupplierInvoiceData(
        items=[
            SupplierInvoiceItem(
                description="Magazine subscription",
                quantity=Decimal("1"),
                unit_price=Decimal("69.00"),
                discount_rate=Decimal("30"),
                line_total=Decimal("48.30"),
            )
        ],
        subtotal=Decimal("48.30"),
        vat_rate=Decimal("20"),
        vat_amount=Decimal("9.66"),
        total=Decimal("57.96"),
    )

    validation = SupplierInvoiceValidator().validate(invoice)

    assert validation.status == "valid"
    assert validation.confidence == 1.0
    assert validation.checks["line_totals"].status == "passed"
