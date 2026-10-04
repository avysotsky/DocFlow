from datetime import date
from decimal import Decimal

from docflow_worker.deterministic_text_fields import extract_totals_from_text
from docflow_worker.document_type_detector import detect_document_type
from docflow_worker.engines.deterministic_supplier_invoice import DeterministicSupplierInvoiceEngine
from docflow_worker.generic_invoice_recovery import apply_generic_invoice_recovery
from docflow_worker.models import DocumentContent, PageContent
from docflow_worker.supplier_invoice_models import SupplierInvoiceData


def _content(*pages: str, ocr: bool = False) -> DocumentContent:
    return DocumentContent(
        pages=[
            PageContent(
                page_number=index,
                width=595,
                height=842,
                text=text,
                words=[],
                blocks=[],
                tables=[],
                ocr_applied=ocr,
            )
            for index, text in enumerate(pages, start=1)
        ]
    )


def test_recovers_zero_value_row_and_invoice_metadata_from_layout_columns() -> None:
    content = _content(
        """
Date                            Invoice
July 16, 2021                   INV307504
Terms                           Due Date
Net 30                          August 15, 2021
Customer VAT No.                PO #                  Billing Frequency
GB232327983                     275026403              Annual
Description                     Quantity              Rate               Amount
Sites                           1                     1,295.38           1,295.38
Administrators                  3                     368.13             1,104.39
Committees- No Charge           15                    0.00                0.00
User (Board Members/Executives)  69                    368.13             25,400.97
Subtotal                        27,800.74
VAT (20%)                       5,560.15
Total                           33,360.89
"""
    )
    invoice = SupplierInvoiceData(
        subtotal=Decimal("27800.74"),
        vat_rate=Decimal("20"),
        vat_amount=Decimal("5560.15"),
        total=Decimal("33360.89"),
    )

    apply_generic_invoice_recovery(content, invoice)

    assert invoice.invoice_number == "INV307504"
    assert invoice.invoice_date == date(2021, 7, 16)
    assert invoice.due_date == date(2021, 8, 15)
    assert invoice.purchase_order_number == "275026403"
    assert len(invoice.items) == 4
    assert invoice.items[2].description == "Committees- No Charge"
    assert invoice.items[2].line_total == Decimal("0.00")


def test_recovers_multi_page_activity_rows_with_no_vat_items() -> None:
    content = _content(
        """
ACTIVITY                              QTY               RATE        VAT        AMOUNT
Catering booked to room              1                 238.83      20.0% S    238.83
Catering for the PCN event
Room Rental - commercial             18                25.00       No VAT     450.00
Hire of Bennett Room by PCN for May and
June 2022
""",
        """
ACTIVITY                              QTY               RATE        VAT        AMOUNT
Rebill                                1                 80.40       No VAT     80.40
Vaccination leaflets
SUBTOTAL                                                                  769.23
"""
    )
    invoice = SupplierInvoiceData(subtotal=Decimal("769.23"))

    apply_generic_invoice_recovery(content, invoice)

    assert [item.quantity for item in invoice.items] == [
        Decimal("1"),
        Decimal("18"),
        Decimal("1"),
    ]
    assert [item.line_total for item in invoice.items] == [
        Decimal("238.83"),
        Decimal("450.00"),
        Decimal("80.40"),
    ]


def test_repairs_suspicious_ocr_unit_price_from_clean_line_total() -> None:
    content = _content(
        """
Quantity Description                         Each      Net Amount    FC
1.00     SITE CHARGE                         30.00     30.00         T1
4.00     ALL IN EXTINGUISHER SERVICE         5:75      15.00         T1
NETT                                                     45.00
VAT                                                       9.00
TOTAL DUE                                                54.00
""",
        ocr=True,
    )
    invoice = SupplierInvoiceData(
        subtotal=Decimal("45.00"),
        vat_amount=Decimal("9.00"),
        total=Decimal("54.00"),
    )

    apply_generic_invoice_recovery(content, invoice)

    assert len(invoice.items) == 2
    assert invoice.items[1].quantity == Decimal("4.00")
    assert invoice.items[1].unit_price == Decimal("3.75")
    assert invoice.items[1].line_total == Decimal("15.00")


def test_recovers_meter_copy_rows_and_summary_totals() -> None:
    content = _content(
        """
Prev Meter      Curr Meter    Used    @            Charge
Black Pages     59729         60605   876          0.4700       £4.12
Scans           3846          3936    90           0.2500       £0.23
Colour Pages    42143         42557   414          3.6200       £14.99
Colour Scans    13396         13442   46           0.2500       £0.12
Delivery To                                    Inv Goods     Invoice Vat       Inv Total
                                               £19.46        £3.89             £23.35
VAT Rate 20.00%
"""
    )
    invoice = SupplierInvoiceData()

    apply_generic_invoice_recovery(content, invoice)

    assert len(invoice.items) == 4
    assert invoice.items[0].description == "Black Pages"
    assert invoice.items[0].quantity == Decimal("876")
    assert invoice.items[3].line_total == Decimal("0.12")
    assert invoice.subtotal == Decimal("19.46")
    assert invoice.vat_amount == Decimal("3.89")
    assert invoice.total == Decimal("23.35")
    assert invoice.vat_rate == Decimal("20.00")


def test_recovers_degraded_invoice_type_and_ocr_item_row() -> None:
    content = _content(
        """
(M)12 Arden Road               finvaiceNo      20794
| Unit Price    NetAmt  VAT%   VATQuantity  Description
1:00  Annual Support Cost Year 6 (min 4 years)  135.00  135.00  20.C0  27,00
Total Net Amount        £ 135.00
Total Tax               £ 27.00
Invoice Total           £ 162.00
""",
        ocr=True,
    )

    assert detect_document_type(content) == "supplier_invoice"

    invoice = SupplierInvoiceData(
        currency="GBP",
        vat_rate=Decimal("20"),
        total=Decimal("162.00"),
    )
    apply_generic_invoice_recovery(content, invoice)

    assert invoice.invoice_number == "20794"
    assert len(invoice.items) == 1
    assert invoice.items[0].quantity == Decimal("1.00")
    assert invoice.items[0].unit_price == Decimal("135.00")
    assert invoice.items[0].line_total == Decimal("135.00")
    assert invoice.subtotal == Decimal("135.00")
    assert invoice.vat_amount == Decimal("27.00")


def test_recovers_vertically_emitted_quickbooks_item() -> None:
    content = _content(
        """
ACTIVITY
QTY
RATE
AMOUNT
Labour, Equipment and Fuel
1
1,200.00
1,200.00
SUBTOTAL
1,200.00
VAT TOTAL
240.00
TOTAL
1,440.00
"""
    )
    invoice = SupplierInvoiceData(
        subtotal=Decimal("1200.00"),
        vat_amount=Decimal("240.00"),
        total=Decimal("1440.00"),
    )

    apply_generic_invoice_recovery(content, invoice)

    assert len(invoice.items) == 1
    assert invoice.items[0].description == "Labour, Equipment and Fuel"
    assert invoice.items[0].quantity == Decimal("1")
    assert invoice.items[0].unit_price == Decimal("1200.00")
    assert invoice.items[0].line_total == Decimal("1200.00")


def test_recovers_vertical_header_dates_and_activity_description_columns() -> None:
    content = _content(
        """
INVOICE NO.
DATE
TOTAL DUE
DUE DATE
TERMS
ENCLOSED
12271
19/05/2025
£480.00
18/06/2025
Net 30
DATE
ACTIVITY
DESCRIPTION
VAT
QTY
RATE
AMOUNT
Title Plan Overlay
Survey at Shedfield
20
1
400.00
400.00
SUBTOTAL
400.00
VAT TOTAL
80.00
TOTAL
480.00
"""
    )
    invoice = SupplierInvoiceData(
        subtotal=Decimal("400.00"),
        vat_amount=Decimal("80.00"),
        total=Decimal("480.00"),
    )

    apply_generic_invoice_recovery(content, invoice)

    assert invoice.invoice_number == "12271"
    assert invoice.invoice_date == date(2025, 5, 19)
    assert invoice.due_date == date(2025, 6, 18)
    assert len(invoice.items) == 1
    assert invoice.items[0].description == "Survey at Shedfield"
    assert invoice.items[0].quantity == Decimal("1")
    assert invoice.items[0].unit_price == Decimal("400.00")
    assert invoice.items[0].line_total == Decimal("400.00")


def test_recovers_vertical_wiltshire_style_item() -> None:
    content = _content(
        """
Description
Qty
Unit Price
(£)
Net Amount
(£)
VAT
Rate (%)
VAT
Amount (£)
1
Dropped kerbs at
Chestnut Drive &
Northfields, Bulkington
1.00
1,164.74
1,164.74
0
0.00
Net Total
1,164.74
"""
    )
    invoice = SupplierInvoiceData(subtotal=Decimal("1164.74"))

    apply_generic_invoice_recovery(content, invoice)

    assert len(invoice.items) == 1
    assert invoice.items[0].description == "Dropped kerbs at Chestnut Drive & Northfields, Bulkington"
    assert invoice.items[0].quantity == Decimal("1.00")
    assert invoice.items[0].unit_price == Decimal("1164.74")
    assert invoice.items[0].line_total == Decimal("1164.74")


def test_recovers_vertical_halc_style_item() -> None:
    content = _content(
        """
Quantity
Description
Unit
Price
Net
Amount
£
VAT
%
VAT
£
1
.
Completion of the Internal Audit for 2019/20
200.00
200.00
.
20.00
.
40.00
Total Net Amount
200.00
VAT @ 20%
40.00
Invoice Total
240.00
"""
    )
    invoice = SupplierInvoiceData(
        subtotal=Decimal("200.00"),
        vat_rate=Decimal("20"),
        vat_amount=Decimal("40.00"),
        total=Decimal("240.00"),
    )

    apply_generic_invoice_recovery(content, invoice)

    assert len(invoice.items) == 1
    assert invoice.items[0].description == "Completion of the Internal Audit for 2019/20"
    assert invoice.items[0].quantity == Decimal("1")
    assert invoice.items[0].unit_price == Decimal("200.00")
    assert invoice.items[0].line_total == Decimal("200.00")


def test_recovers_vertical_zoho_item_and_po_number() -> None:
    content = _content(
        """
Invoice#
80030622834
P.O.#
2000941218324
#
Item
Description
Qty
Rate
Amount
1
319702F
Service : Zoho Assist
Plan : Free Plan
Start 26 June 2025 End 25 July 2025
1.00
9.20
9.20
Sub Total
9.20
UK VAT (20%)
1.84
Total
£11.04
"""
    )
    invoice = SupplierInvoiceData(
        subtotal=Decimal("9.20"),
        vat_amount=Decimal("1.84"),
        total=Decimal("11.04"),
    )

    apply_generic_invoice_recovery(content, invoice)

    assert invoice.purchase_order_number == "2000941218324"
    assert len(invoice.items) == 1
    assert invoice.items[0].quantity == Decimal("1.00")
    assert invoice.items[0].unit_price == Decimal("9.20")
    assert invoice.items[0].line_total == Decimal("9.20")
    assert invoice.vat_rate == Decimal("20")


def test_recovers_vertical_microsoft_charge() -> None:
    content = _content(
        """
Microsoft 365 Business Standard - One-Year commitment for monthly/yearly billing
Purchases
Charge Start Date - Charge End Date
Unit
Price
(GBP)
Qty
Charges/
Credits
(GBP)
Tax Rate
Total (excluding Tax)
(GBP)
Tax Line
Indicator
28/12/2025-27/01/2026
10.08
1
10.08
20.00%
10.08
A
Subtotal
10.08
Tax
2.02
Total
GBP 12.10
"""
    )
    invoice = SupplierInvoiceData(
        subtotal=Decimal("10.08"),
        vat_rate=Decimal("20"),
        vat_amount=Decimal("2.02"),
        total=Decimal("12.10"),
    )

    apply_generic_invoice_recovery(content, invoice)

    assert len(invoice.items) == 1
    assert invoice.items[0].quantity == Decimal("1")
    assert invoice.items[0].unit_price == Decimal("10.08")
    assert invoice.items[0].line_total == Decimal("10.08")


def test_compact_vat_number_is_not_treated_as_tax_amount() -> None:
    content = _content(
        """
Vat.No.GB392232306
Sub Total
9.20
UK VAT (20%)
1.84
Total
£11.04
"""
    )

    totals = extract_totals_from_text(
        content,
        lambda value: Decimal(value.replace(",", "").replace(" ", "")) if value else None,
    )

    assert totals["vat_amount"] != Decimal("392232306")
    assert totals["total"] == Decimal("11.04")
