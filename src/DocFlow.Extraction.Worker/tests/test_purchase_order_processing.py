import asyncio
from datetime import date
from decimal import Decimal

from docflow_worker.engines.deterministic_purchase_order import DeterministicPurchaseOrderEngine
from docflow_worker.models import DocumentContent, PageContent
from docflow_worker.purchase_order_models import PurchaseOrderData, PurchaseOrderItem
from docflow_worker.structured_pipeline import extract_structured_document
from docflow_worker.validators import PurchaseOrderValidator


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


def test_extracts_ukhsa_purchase_order_from_layout_text() -> None:
    content = _content(
        """
Purchase Order Number
P5084955
Purchase Order
Order Number and Date must be quoted on Invoices,
Delivery Notes and any other Correspondence.
Page Number: 1 of 1
Date : 03-NOV-2023
Supplier Name and Address:
CSL - KPMG LLP
15 CANADA SQUARE
LONDON
E14 5GL

Your Reference  Description  Unit Of Measure  Quantity  Unit Price (excl. VAT)  Total Price (excl. VAT)
DAS Group - Data Operations - Agile Project Management Foundation & Practitioner
Method of delivery: Virtual, Delegate: Elaine Nock
Need by Date 29-Mar-2024
Each  1  1,722.00  1,722.00
DAS Group - Data Operations - Agile Project Management Foundation & Practitioner
Method of delivery: Virtual, Delegate: Chris Sunny
Need by Date 29-Mar-2024
Each  1  1,722.00  1,722.00
Order Total GBP 3,444.00
"""
    )

    result = asyncio.run(DeterministicPurchaseOrderEngine().extract(content))
    po = PurchaseOrderData.model_validate(result.data)

    assert result.document_type == "purchase_order"
    assert po.purchase_order_number == "P5084955"
    assert po.order_date == date(2023, 11, 3)
    assert po.supplier_name == "CSL - KPMG LLP"
    assert po.currency == "GBP"
    assert len(po.items) == 2
    assert po.items[0].quantity == Decimal("1")
    assert po.items[0].unit == "Each"
    assert po.items[0].unit_price == Decimal("1722.00")
    assert po.items[0].line_total == Decimal("1722.00")
    assert po.items[0].need_by_date == date(2024, 3, 29)
    assert po.items[1].line_total == Decimal("1722.00")
    assert po.subtotal == Decimal("3444.00")
    assert po.total == Decimal("3444.00")


def test_extracts_vat_breakdown_purchase_order() -> None:
    content = _content(
        """
PURCHASE ORDER
ORDER NUMBER MOJ-2025-1009
ORDER DATE 30-JAN-2025
To :
STORAGE ON SITE LTD#ZANZIBAR
Line  DESCRIPTION - ORDER DETAIL  QUANTITY  UNIT PRICE  TOTAL
1  Storage services  1  22420.00  22420.00
TOTAL (Excluding VAT) 22,420.00
TOTAL VAT 4,484.00
ORDER TOTAL GBP 26,904.00
"""
    )

    result = asyncio.run(extract_structured_document(content, document_type="auto"))
    po = PurchaseOrderData.model_validate(result.data)

    assert result.document_type == "purchase_order"
    assert result.validation_status == "valid"
    assert po.purchase_order_number == "MOJ-2025-1009"
    assert po.order_date == date(2025, 1, 30)
    assert po.supplier_name == "STORAGE ON SITE LTD"
    assert po.currency == "GBP"
    assert len(po.items) == 1
    assert po.items[0].quantity == Decimal("1")
    assert po.items[0].unit_price == Decimal("22420.00")
    assert po.items[0].line_total == Decimal("22420.00")
    assert po.subtotal == Decimal("22420.00")
    assert po.tax_amount == Decimal("4484.00")
    assert po.total == Decimal("26904.00")


def test_purchase_order_validator_routes_incomplete_rows_to_review() -> None:
    po = PurchaseOrderData(
        purchase_order_number="PO-44",
        items=[
            PurchaseOrderItem(
                description="Consulting",
                quantity=Decimal("2"),
                unit_price=None,
                line_total=Decimal("200.00"),
            )
        ],
        subtotal=Decimal("200.00"),
        total=Decimal("200.00"),
    )

    validation = PurchaseOrderValidator().validate(po)

    assert validation.status == "incomplete"
    assert validation.checks["line_totals"].status == "skipped"
    assert validation.checks["subtotal"].status == "passed"
    assert validation.checks["grand_total"].status == "passed"


def test_purchase_order_validator_detects_price_mismatch() -> None:
    po = PurchaseOrderData(
        items=[
            PurchaseOrderItem(
                description="Hardware",
                quantity=Decimal("2"),
                unit_price=Decimal("50.00"),
                line_total=Decimal("120.00"),
            )
        ],
        subtotal=Decimal("120.00"),
        total=Decimal("120.00"),
    )

    validation = PurchaseOrderValidator().validate(po)

    assert validation.status == "invalid"
    assert validation.checks["line_totals"].status == "failed"


def test_recovers_ukhsa_po_number_supplier_and_partial_item() -> None:
    content = _content(
        """
Purchase Order                             Purchase Order Number
                          P5084955
Page Number: 1 of 2
Date : 03-NOV-23

Supplier Name and Address:            Delivery Address:            All Invoices To Be Sent To:
CSL - KPMG LLP                        UKHSA SOUTH OFFICE            UKHSA ACCOUNTS

Your Reference  Description  Unit Of Measure  Quantity  Unit Price (excl. VAT)  Total Price (excl. VAT)
100 x GraphPad Prism licences for PHE staff to be recharged back to relevant cost centres.    Each
Need by Date 25-Aug-2022

Order Total GBP 12,864.00
"""
    )

    result = asyncio.run(DeterministicPurchaseOrderEngine().extract(content))
    po = PurchaseOrderData.model_validate(result.data)

    assert po.purchase_order_number == "P5084955"
    assert po.supplier_name == "CSL - KPMG LLP"
    assert len(po.items) == 1
    assert po.items[0].description == (
        "100 x GraphPad Prism licences for PHE staff to be recharged back to relevant cost centres."
    )
    assert po.items[0].unit == "Each"
    assert po.items[0].need_by_date == date(2022, 8, 25)
    assert po.items[0].quantity is None
    assert po.items[0].unit_price is None


def test_detects_and_extracts_ukri_help_scout_purchase_order() -> None:
    content = _content(
        """
Purchase Order
4070408506,0
COPY
Order                  4070408506
Order Date              02-MAY-2025
Revision                0
Supplier:    Help Scout PBC
Line     Part Number/Description               Delivery        Quantity  UOM      Unit Price    Tax      Net Amount
                                                Date                                 (USD)                  (USD)
1          Supplier Item:                      02-MAY-2025             Each                                 15,955.20
           Help Scout Renewal for Centre for
           Environmental Data Analysis
Grand Total                 15,955.20
"""
    )

    result = asyncio.run(extract_structured_document(content, document_type="auto"))
    po = PurchaseOrderData.model_validate(result.data)

    assert result.document_type == "purchase_order"
    assert po.purchase_order_number == "4070408506"
    assert po.order_date == date(2025, 5, 2)
    assert po.supplier_name == "Help Scout PBC"
    assert po.currency == "USD"
    assert po.total == Decimal("15955.20")
