import asyncio
from decimal import Decimal

from docflow_worker.engines import DeterministicSupplierInvoiceEngine
from docflow_worker.models import DocumentContent, PageContent
from docflow_worker.supplier_invoice_models import SupplierInvoiceData
from docflow_worker.validators import SupplierInvoiceValidator


def _extract_and_validate(text: str) -> tuple[SupplierInvoiceData, object]:
    content = DocumentContent(
        pages=[
            PageContent(
                page_number=1,
                width=595,
                height=842,
                text=text,
                words=[],
                blocks=[],
                tables=[],
            )
        ]
    )

    result = asyncio.run(DeterministicSupplierInvoiceEngine().extract(content))
    invoice = SupplierInvoiceData.model_validate(result.data)
    validation = SupplierInvoiceValidator().validate(invoice)
    return invoice, validation


def test_borderless_invoice_items_do_not_require_sku() -> None:
    invoice, validation = _extract_and_validate(
        "TAX INVOICE\n"
        "Invoice Number    INV-1021\n"
        "Description    Quantity    Unit Price    VAT    Amount GBP\n"
        "Professional services    1.00    210.00    20%    210.00\n"
        "Subtotal    210.00\n"
        "TOTAL VAT 20%    42.00\n"
        "TOTAL GBP    252.00\n"
    )

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


def test_ocr_split_descriptions_keep_numeric_columns_right_aligned() -> None:
    invoice, validation = _extract_and_validate(
        "TAX INVOICE\n"
        "Description    Quantity    Unit Price    VAT    Amount GBP\n"
        "June 25    (24th of the month) Monthly cleaning service -    1.00    307.66    20%    307.66\n"
        "Monthly sanitary provision    1.00    26.76    20%    26.76\n"
        "July 25    (24th of the month) Monthly cleaning service    -    1.00    307.66    20%    |    307.66\n"
        "Monthly sanitary provision    1.00    26.76    20%    26.76\n"
        "towels as requested bulk 1x box    Consumables for stock room    1.00    114.04    20%    114.04\n"
        "Subtotal    |    782.88\n"
        "TOTAL VAT 20%    156.57\n"
        "TOTAL GBP    |    939.45\n"
    )

    assert len(invoice.items) == 5
    assert sum(item.line_total or Decimal("0") for item in invoice.items) == Decimal("782.88")
    assert all(item.sku is None for item in invoice.items)
    assert validation.status == "valid"
    assert validation.confidence == 1.0


def test_ocr_items_reconcile_lost_quantity_and_decimal_separators() -> None:
    invoice, validation = _extract_and_validate(
        "PROFORMA INVOICE\n"
        "Invoice Na:    1056\n"
        "Curreuicy: EUR\n"
        "ivanov September - Octomber 2024    €65,00/    €    1. 560,00\n"
        "Service charge (Reporting, correspondence and communication)    2]    6000]    12000\n"
        "SUBTOTAL    €1 680.00\n"
        "VAT 20%    € 336,00\n"
        "GRANDTOTAL    €2 016,00\n"
    )

    assert len(invoice.items) == 2
    assert invoice.items[0].quantity == Decimal("24")
    assert invoice.items[0].unit_price == Decimal("65.00")
    assert invoice.items[0].line_total == Decimal("1560.00")
    assert invoice.items[1].quantity == Decimal("2")
    assert invoice.items[1].unit_price == Decimal("60")
    assert invoice.items[1].line_total == Decimal("120")
    assert sum(item.line_total or Decimal("0") for item in invoice.items) == Decimal("1680.00")
    assert validation.status == "valid"
    assert validation.confidence == 1.0
