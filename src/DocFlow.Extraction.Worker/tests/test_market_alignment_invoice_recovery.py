from datetime import date
from decimal import Decimal

from docflow_worker.generic_invoice_recovery import apply_generic_invoice_recovery
from docflow_worker.models import DocumentContent, PageContent
from docflow_worker.supplier_invoice_models import SupplierInvoiceData, SupplierInvoiceItem


def _content(text: str) -> DocumentContent:
    return DocumentContent(
        pages=[
            PageContent(
                page_number=1,
                width=595,
                height=842,
                text=text,
                blocks=[],
                words=[],
                tables=[],
            )
        ]
    )


def test_recovers_bilingual_description_and_numeric_item_row() -> None:
    content = _content(
        """
ANFONEB / INVOICE
Rhif yr Anfoneb / Invoice No. 210395591
Dyddiad yr Anfoneb / Invoice Date 21/05/2025

Disgrifiad / Description                                    TAW %      PRIS NET /
                                                           VAT %      NET PRICE

Event Support Grant for Prom Xtra 10/05/2025
1.00     Uned/Unit(s)                                 £12,733.00     20.00     12,733.00

DYDDIAD DYLEDUS / DUE DATE 04/06/2025
CYFANSWM NET / NET TOTAL 12,733.00
TAW / VAT 2,546.60
CYFANSWM YR ANFONEB / INVOICE TOTAL £15,279.60
"""
    )
    invoice = SupplierInvoiceData(
        invoice_number="210395591",
        invoice_date=date(2025, 5, 21),
        due_date=date(2025, 6, 4),
        subtotal=Decimal("12733.00"),
        vat_rate=Decimal("20"),
        vat_amount=Decimal("2546.60"),
        total=Decimal("15279.60"),
    )

    apply_generic_invoice_recovery(content, invoice)

    assert len(invoice.items) == 1
    assert invoice.items[0].description == "Event Support Grant for Prom Xtra 10/05/2025"
    assert invoice.items[0].quantity == Decimal("1.00")
    assert invoice.items[0].unit_price == Decimal("12733.00")
    assert invoice.items[0].line_total == Decimal("12733.00")


def test_recovers_split_invoice_labels_ordinal_dates_and_zero_vat_items() -> None:
    content = _content(
        """
ESALC Limited
Invoice
Number: 2031
Date: 1st Apr '25
Due By: 30th Jun '25

Qty    Descrip on                                                   Rate      Total
1      ESALC membership 1st April 2025 - 31st March 2026            172.01    172.01
1      NALC membership 1st April 2025 - 31st March 2026              49.62     49.62

Net: £221.63
VAT @ NA%: £0.00
TOTAL: £221.63
"""
    )
    invoice = SupplierInvoiceData(
        invoice_number="umber",
        currency="GBP",
        subtotal=Decimal("221.63"),
        vat_amount=Decimal("0.00"),
        total=Decimal("221.63"),
    )

    apply_generic_invoice_recovery(content, invoice)

    assert invoice.invoice_number == "2031"
    assert invoice.invoice_date == date(2025, 4, 1)
    assert invoice.due_date == date(2025, 6, 30)
    assert len(invoice.items) == 2
    assert invoice.items[0].description == "ESALC membership 1st April 2025 - 31st March 2026"
    assert invoice.items[0].unit_price == Decimal("172.01")
    assert invoice.items[1].description == "NALC membership 1st April 2025 - 31st March 2026"
    assert invoice.items[1].line_total == Decimal("49.62")


def test_expands_wrapped_activity_description_without_changing_numbers() -> None:
    content = _content(
        """
ACTIVITY                           QTY                  RATE          VAT           AMOUNT
PAYROLLM1                             1                      10.00      20.0% S      10.00
Monthly Payroll & Auto Enrolment
Services - 1 Employee

SUBTOTAL 10.00
VAT TOTAL 2.00
TOTAL 12.00
"""
    )
    invoice = SupplierInvoiceData(
        items=[
            SupplierInvoiceItem(
                description="PAYROLLM1",
                quantity=Decimal("1"),
                unit_price=Decimal("10.00"),
                line_total=Decimal("10.00"),
            )
        ],
        subtotal=Decimal("10.00"),
        vat_rate=Decimal("20"),
        vat_amount=Decimal("2.00"),
        total=Decimal("12.00"),
    )

    apply_generic_invoice_recovery(content, invoice)

    assert len(invoice.items) == 1
    assert invoice.items[0].description == (
        "PAYROLLM1 Monthly Payroll & Auto Enrolment Services - 1 Employee"
    )


def test_does_not_append_post_table_marketing_note_to_last_item() -> None:
    content = _content(
        """
Quantity   Description                                        Unit Price   Net Amount   VAT %   VAT £
1          HALC Affiliation Fee 1st April 2025 to 31st March  275.00  275.00  20.00  55.00
           2026
3000       HALC Subscription Fee 2025/26                       0.60    1800.00 20.00  360.00
4793       HALC Subscription Fee 2025/26                       0.04    191.72  20.00  38.34
7793       NALC Subscription Fee 2025/26                       0.0834  649.94  20.00  129.99
If paid by 31st March 2025 the Parish Council will be
entitled to two free training places (Councillors only)
valued at £60.00 each.
Total Net Amount 2916.66
VAT @ 20% 583.33
Invoice Total 3499.99
"""
    )
    invoice = SupplierInvoiceData(
        subtotal=Decimal("2916.66"),
        vat_rate=Decimal("20"),
        vat_amount=Decimal("583.33"),
        total=Decimal("3499.99"),
    )

    apply_generic_invoice_recovery(content, invoice)

    assert len(invoice.items) == 4
    assert invoice.items[3].description == "NALC Subscription Fee 2025/26"


def test_recovers_wrapped_discount_item_and_invoice_discount_amount() -> None:
    content = _content(
        """
Description                                              Quantity           Unit Price      Discount        VAT       Amount GBP
Provision of Internal Audit Services - Year End          1.00               395.00          5.00%           20%       375.25
Audit 2024-25

Subtotal (includes a discount of 19.75) 375.25
TOTAL VAT 20% 75.05
TOTAL GBP 450.30
"""
    )
    invoice = SupplierInvoiceData(
        items=[
            SupplierInvoiceItem(
                description="Provision of Internal Audit Services - Year End",
                quantity=Decimal("1.00"),
                unit_price=Decimal("395.00"),
                discount_rate=Decimal("5.00"),
                line_total=Decimal("375.25"),
            )
        ],
        subtotal=Decimal("375.25"),
        vat_rate=Decimal("20"),
        vat_amount=Decimal("75.05"),
        total=Decimal("450.30"),
    )

    apply_generic_invoice_recovery(content, invoice)

    assert invoice.discount_amount is None
    assert invoice.items[0].discount_rate == Decimal("5.00")
    assert invoice.items[0].description == (
        "Provision of Internal Audit Services - Year End Audit 2024-25"
    )
