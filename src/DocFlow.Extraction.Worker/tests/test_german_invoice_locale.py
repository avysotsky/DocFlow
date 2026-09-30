import asyncio
from datetime import date
from decimal import Decimal

from docflow_worker.models import DocumentContent, PageContent
from docflow_worker.structured_pipeline import extract_structured_document
from docflow_worker.supplier_invoice_models import SupplierInvoiceData


CARGO_GERMAN_INVOICE_TEXT = """
Cargo International GmbH
Friedrich-Ebert-Straße 22
78054 Villingen-Schwenningen

Rechnung

Kundennummer: 75243         Rechnungsnummer: G59771         Rechnungsdatum: 04.06.2024
Leistungsdatum: 06/2024

Pos.     Beschreibung                     Preis in EUR       Preis in EUR
                                         (netto)             (brutto)
1        1520416                               -96,48            -114,81

Gesamt:                    Netto          MwSt.      MwSt. in %           Brutto
                                  -96,48            -18,33            19,00          -114,81

Rechnungsbetrag    -114,81
Zahlungsziel: 05.06.2024
""".strip()


def test_extracts_german_invoice_with_decimal_comma_and_negative_amounts() -> None:
    content = DocumentContent(
        pages=[
            PageContent(
                page_number=1,
                width=595,
                height=842,
                text=CARGO_GERMAN_INVOICE_TEXT,
                blocks=[],
                words=[],
                tables=[],
            )
        ]
    )

    result = asyncio.run(extract_structured_document(content))
    invoice = SupplierInvoiceData.model_validate(result.data)

    assert result.document_type == "supplier_invoice"
    assert result.engine == "deterministic_supplier_invoice_v2"
    assert result.validation_status == "incomplete"

    assert invoice.invoice_number == "G59771"
    assert invoice.invoice_date == date(2024, 6, 4)
    assert invoice.due_date == date(2024, 6, 5)
    assert invoice.currency == "EUR"
    assert invoice.subtotal == Decimal("-96.48")
    assert invoice.vat_amount == Decimal("-18.33")
    assert invoice.vat_rate == Decimal("19.00")
    assert invoice.total == Decimal("-114.81")

    assert result.validation is not None
    assert result.validation.checks["vat"].status == "passed"
    assert result.validation.checks["grand_total"].status == "passed"


def test_german_locale_decimal_supports_thousands_separator() -> None:
    from docflow_worker.engines.deterministic_supplier_invoice_discount import (
        DeterministicSupplierInvoiceDiscountEngine,
    )

    assert DeterministicSupplierInvoiceDiscountEngine._parse_locale_decimal(
        "1.234,56"
    ) == Decimal("1234.56")
