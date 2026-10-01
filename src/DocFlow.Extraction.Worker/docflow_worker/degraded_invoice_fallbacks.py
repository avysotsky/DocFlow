from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from docflow_worker.models import DocumentContent
from docflow_worker.supplier_invoice_models import SupplierInvoiceData


_TEXTUAL_DATE = re.compile(
    r"\binvoice\s+date\b[^0-9\r\n]{0,180}"
    r"(?P<date>\d{1,2}[\s./-]+[A-Za-z]{3,9}[\s./-]+\d{2,4})\b",
    re.IGNORECASE,
)
_VAT_RATE = re.compile(
    r"\bvat(?:[a-z]{1,6})?\s*@?\s*(?P<rate>\d+(?:[.,]\d+)?)\s*%",
    re.IGNORECASE,
)
_CURRENCY_AMOUNT = re.compile(
    r"[£€₹¥$]\s*(?P<amount>[-+]?\d[\d,]*(?:\.\d+)?)"
)
_DECIMAL_AMOUNT = re.compile(r"[-+]?\d[\d,]*\.\d{2}\b")


def apply_degraded_invoice_fallbacks(
    content: DocumentContent,
    invoice: SupplierInvoiceData,
) -> None:
    """Recover high-confidence invoice fields from visibly degraded OCR text.

    The fallback is deliberately conservative:
    - textual dates are accepted only next to an explicit ``Invoice Date`` label;
    - VAT recovery requires an explicit VAT label plus percentage;
    - a missing subtotal is derived only when gross total and VAT amount are both known.

    It does not invent line items or promote the validation status. Documents without
    verifiable quantity/unit-price lines therefore remain ``incomplete`` under the
    normal invoice validator.
    """
    text = content.text

    if invoice.invoice_date is None:
        invoice.invoice_date = _extract_invoice_date(text)

    if invoice.vat_rate is None or invoice.vat_amount is None:
        rate, amount = _extract_vat_summary(text)
        if invoice.vat_rate is None and rate is not None:
            invoice.vat_rate = rate
        if invoice.vat_amount is None and amount is not None:
            invoice.vat_amount = amount

    if (
        invoice.subtotal is None
        and invoice.total is not None
        and invoice.vat_amount is not None
        and invoice.total >= invoice.vat_amount
    ):
        invoice.subtotal = invoice.total - invoice.vat_amount


def _extract_invoice_date(text: str) -> date | None:
    match = _TEXTUAL_DATE.search(text)
    if match is None:
        return None

    value = re.sub(r"[./\s]+", "-", match.group("date").strip())
    for date_format in ("%d-%b-%y", "%d-%b-%Y", "%d-%B-%y", "%d-%B-%Y"):
        try:
            return datetime.strptime(value, date_format).date()
        except ValueError:
            continue
    return None


def _extract_vat_summary(text: str) -> tuple[Decimal | None, Decimal | None]:
    for line in text.splitlines():
        rate_match = _VAT_RATE.search(line)
        if rate_match is None:
            continue

        rate = _decimal(rate_match.group("rate"))
        if rate is None or rate < 0 or rate > 100:
            continue

        without_rate = _VAT_RATE.sub("VAT ", line, count=1)
        currency_match = _CURRENCY_AMOUNT.search(without_rate)
        if currency_match is not None:
            amount = _decimal(currency_match.group("amount"))
            if amount is not None:
                return rate, amount

        # When the OCR loses the currency symbol, accept a conventional two-decimal
        # amount only if there is exactly one such candidate after removing the rate.
        amount_tokens = _DECIMAL_AMOUNT.findall(without_rate)
        amounts = [value for value in (_decimal(token) for token in amount_tokens) if value is not None]
        if len(amounts) == 1:
            return rate, amounts[0]

    return None, None


def _decimal(value: str) -> Decimal | None:
    normalized = value.replace(" ", "").replace(",", "")
    try:
        return Decimal(normalized)
    except InvalidOperation:
        return None
