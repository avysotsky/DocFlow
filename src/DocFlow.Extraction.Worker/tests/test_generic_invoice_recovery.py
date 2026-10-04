from datetime import date
from decimal import Decimal

from docflow_worker.document_type_detector import detect_document_type
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
User (Board Members/Executives) 69                    368.13             25,400.97
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
