import re
from decimal import Decimal, InvalidOperation

from docflow_worker.supplier_invoice_models import SupplierInvoiceData


_EXPLICIT_NO_VAT = re.compile(
    r"(?im)^\s*total\s+no\s+vat\b(?P<tail>[^\r\n]*)$"
)
_NUMBER = re.compile(r"[-+]?\d[\d,]*(?:\.\d+)?")


def apply_explicit_no_vat_fallback(text: str, invoice: SupplierInvoiceData) -> None:
    """Normalize invoices that explicitly declare a zero-VAT total.

    Some supplier layouts use labels such as ``TOTAL NO VAT 0.00`` rather than
    ``VAT 0% 0.00``. The generic total parser correctly reads the surrounding subtotal
    and grand total, but this wording otherwise leaves VAT arithmetic incomplete.

    Activate only on the explicit NO VAT label; do not infer zero VAT from a missing
    tax line.
    """
    match = _EXPLICIT_NO_VAT.search(text)
    if match is None:
        return

    invoice.vat_rate = Decimal("0")

    amount = _last_decimal(match.group("tail"))
    invoice.vat_amount = amount if amount is not None else Decimal("0")


def _last_decimal(text: str) -> Decimal | None:
    values = _NUMBER.findall(text)
    if not values:
        return None
    try:
        return Decimal(values[-1].replace(",", ""))
    except InvalidOperation:
        return None
