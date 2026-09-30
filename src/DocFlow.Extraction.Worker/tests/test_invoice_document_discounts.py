import asyncio
from decimal import Decimal

from docflow_worker.engines.deterministic_supplier_invoice_discount import (
    DeterministicSupplierInvoiceDiscountEngine,
)
from docflow_worker.models import DocumentContent, PageContent
from docflow_worker.supplier_invoice_models import SupplierInvoiceData, SupplierInvoiceItem
from docflow_worker.validators import SupplierInvoiceValidator


def _phoenix_like_content() -> DocumentContent:
    return DocumentContent(
        pages=[
            PageContent(
                page_number=1,
                width=595,
                height=842,
                text=(
                    "INVOICE\n"
                    "Invoice no : 472557\n"
                    "Description             Del. Amount  Unit Price  Value (£)  VAT rate\n"
                    "GAS OIL                      950.0    l       16.70p      158.65     00.00\n"
                    "Less discount of £ 19.00\n"
                    "Total VAT : £ 0.00\n"
                    # Deliberately mimic an OCR error in the printed total. The engine
                    # must prefer reconciled arithmetic over this misread value.
                    "Total £ 139.45\n"
                ),
                blocks=[],
                words=[],
                tables=[],
                ocr_applied=True,
            )
        ]
    )


def test_extracts_invoice_level_discount_and_reconciles_net_totals() -> None:
    result = asyncio.run(
        DeterministicSupplierInvoiceDiscountEngine().extract(_phoenix_like_content())
    )
    invoice = SupplierInvoiceData.model_validate(result.data)

    assert result.engine == "deterministic_supplier_invoice_v2"
    assert invoice.discount_amount == Decimal("19.00")
    assert len(invoice.items) == 1
    assert invoice.items[0].description == "GAS OIL"
    assert invoice.items[0].quantity == Decimal("950.0")
    assert invoice.items[0].unit == "l"
    assert invoice.items[0].unit_price == Decimal("0.167")
    assert invoice.items[0].line_total == Decimal("158.65")
    assert invoice.vat_rate == Decimal("0.00")
    assert invoice.vat_amount == Decimal("0.00")
    assert invoice.subtotal == Decimal("139.65")
    assert invoice.total == Decimal("139.65")


def test_validates_invoice_level_discount_arithmetic() -> None:
    invoice = SupplierInvoiceData(
        items=[
            SupplierInvoiceItem(
                description="GAS OIL",
                quantity=Decimal("950"),
                unit="l",
                unit_price=Decimal("0.167"),
                line_total=Decimal("158.65"),
            )
        ],
        discount_amount=Decimal("19.00"),
        subtotal=Decimal("139.65"),
        vat_rate=Decimal("0.00"),
        vat_amount=Decimal("0.00"),
        total=Decimal("139.65"),
    )

    validation = SupplierInvoiceValidator().validate(invoice)

    assert validation.status == "valid"
    assert validation.confidence == 1.0
    assert validation.checks["line_totals"].status == "passed"
    assert validation.checks["subtotal"].status == "passed"
    assert validation.checks["vat"].status == "passed"
    assert validation.checks["grand_total"].status == "passed"
