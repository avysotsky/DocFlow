import asyncio
from decimal import Decimal

from docflow_worker.models import DocumentContent, PageContent
from docflow_worker.structured_pipeline import extract_structured_document
from docflow_worker.supplier_invoice_models import SupplierInvoiceData


FRENCH_MULTI_VAT_TEXT = """
LE FOURNISSEUR
FACTURE N° :
F20260023
31/01/2026
DEVISE : EURO (EUR)

Détail TVA (motif si exonération, code E, O, K, AE) Code Taux Base TVA
S 20,00% 11,00
E 0,00% 60,00
S 10,00% 27,00
K 0,00% 2,00
TOTAL TVA
4,90

Date d'échéance : 02/03/2026
TOTAL TTC
104,90
TOTAL HT
100,00
NET A PAYER 104,90 EUR
""".strip()


def test_extracts_french_multi_rate_vat_summary() -> None:
    content = DocumentContent(
        pages=[PageContent(page_number=1, width=595, height=842, text=FRENCH_MULTI_VAT_TEXT, blocks=[], words=[], tables=[])]
    )

    result = asyncio.run(extract_structured_document(content))
    invoice = SupplierInvoiceData.model_validate(result.data)

    assert result.document_type == "supplier_invoice"
    assert result.validation_status == "incomplete"
    assert invoice.invoice_number == "F20260023"
    assert invoice.currency == "EUR"
    assert invoice.subtotal == Decimal("100.00")
    assert invoice.vat_amount == Decimal("4.90")
    assert invoice.total == Decimal("104.90")
    assert [(entry.category_code, entry.rate, entry.taxable_amount) for entry in invoice.tax_breakdown] == [
        ("S", Decimal("20.00"), Decimal("11.00")),
        ("E", Decimal("0.00"), Decimal("60.00")),
        ("S", Decimal("10.00"), Decimal("27.00")),
        ("K", Decimal("0.00"), Decimal("2.00")),
    ]

    assert result.validation is not None
    assert result.validation.checks["vat"].status == "passed"
    assert result.validation.checks["grand_total"].status == "passed"
