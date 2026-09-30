from decimal import Decimal

from docflow_worker.supplier_quotation_models import (
    SupplierQuotationData,
    SupplierQuotationItem,
)
from docflow_worker.validators import SupplierQuotationValidator


def _valid_quotation() -> SupplierQuotationData:
    return SupplierQuotationData(
        supplier_name="ACME Components Ltd.",
        quotation_number="QT-2026-183",
        currency="EUR",
        items=[
            SupplierQuotationItem(
                sku="AX-100",
                description="Stainless steel sensor bracket",
                quantity=Decimal("20"),
                unit="pcs",
                unit_price=Decimal("12.50"),
                lead_time_days=5,
                line_total=Decimal("250.00"),
            ),
            SupplierQuotationItem(
                sku="BX-240",
                description="IP67 junction box, 240 x 180 mm",
                quantity=Decimal("8"),
                unit="pcs",
                unit_price=Decimal("38.75"),
                lead_time_days=7,
                line_total=Decimal("310.00"),
            ),
            SupplierQuotationItem(
                sku="CBL-M12-05",
                description="M12 shielded cable, 5 m",
                quantity=Decimal("30"),
                unit="pcs",
                unit_price=Decimal("9.80"),
                lead_time_days=4,
                line_total=Decimal("294.00"),
            ),
            SupplierQuotationItem(
                sku="PSU-24V-120",
                description="DIN rail power supply 24 V / 120 W",
                quantity=Decimal("6"),
                unit="pcs",
                unit_price=Decimal("46.00"),
                lead_time_days=10,
                line_total=Decimal("276.00"),
            ),
            SupplierQuotationItem(
                sku="SNS-PT100",
                description="PT100 temperature probe, Class A",
                quantity=Decimal("12"),
                unit="pcs",
                unit_price=Decimal("27.25"),
                lead_time_days=14,
                line_total=Decimal("327.00"),
            ),
        ],
        subtotal=Decimal("1457.00"),
        vat_rate=Decimal("20"),
        vat_amount=Decimal("291.40"),
        total=Decimal("1748.40"),
    )


def test_validates_consistent_supplier_quotation() -> None:
    result = SupplierQuotationValidator().validate(_valid_quotation())

    assert result.status == "valid"
    assert result.confidence == 1.0
    assert result.checks["line_totals"].status == "passed"
    assert result.checks["subtotal"].status == "passed"
    assert result.checks["vat"].status == "passed"
    assert result.checks["grand_total"].status == "passed"


def test_detects_incorrect_line_total_and_subtotal() -> None:
    quotation = _valid_quotation()
    quotation.items[0].line_total = Decimal("251.00")

    result = SupplierQuotationValidator().validate(quotation)

    assert result.status == "invalid"
    assert result.confidence == 0.5
    assert result.checks["line_totals"].status == "failed"
    assert result.checks["subtotal"].status == "failed"
    assert result.checks["vat"].status == "passed"
    assert result.checks["grand_total"].status == "passed"


def test_marks_validation_incomplete_when_values_are_missing() -> None:
    quotation = _valid_quotation()
    quotation.items[0].unit_price = None

    result = SupplierQuotationValidator().validate(quotation)

    assert result.status == "incomplete"
    assert result.confidence == 0.75
    assert result.checks["line_totals"].status == "skipped"
    assert result.checks["subtotal"].status == "passed"
    assert result.checks["vat"].status == "passed"
    assert result.checks["grand_total"].status == "passed"
