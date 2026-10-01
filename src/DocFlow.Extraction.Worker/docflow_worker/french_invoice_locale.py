import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

from docflow_worker.supplier_invoice_models import (
    SupplierInvoiceData,
    SupplierInvoiceTaxBreakdown,
)


_FRENCH_INVOICE_SIGNATURES = (
    "total ht",
    "total tva",
    "total ttc",
    "net a payer",
    "net à payer",
)


def apply_french_invoice_fallbacks(text: str, invoice: SupplierInvoiceData) -> None:
    """Recover common French invoice totals and multi-rate VAT summaries."""
    lower = text.lower()
    if "facture" not in lower or sum(marker in lower for marker in _FRENCH_INVOICE_SIGNATURES) < 2:
        return

    normalized = " ".join(text.split())

    if invoice.invoice_number is None:
        labelled_number = re.search(
            r"\bFACTURE\s+N[°ºO]?\s*:\s*(?P<number>F\d{8})(?!\d)",
            text,
            flags=re.IGNORECASE,
        )
        adjacent_number_and_date = re.search(
            r"\b(?P<number>F\d{8})(?!\d)\s+(?P<date>\d{2}/\d{2}/\d{4})\b",
            normalized,
            flags=re.IGNORECASE,
        )
        number_match = labelled_number or adjacent_number_and_date
        if number_match is not None:
            invoice.invoice_number = number_match.group("number")

        if invoice.invoice_date is None:
            date_match = re.search(
                r"\bDate\s*:\s*(?P<date>\d{2}/\d{2}/\d{4})\b",
                normalized,
                flags=re.IGNORECASE,
            )
            if date_match is None and adjacent_number_and_date is not None:
                date_match = adjacent_number_and_date
            if date_match is not None:
                invoice.invoice_date = _parse_french_date(date_match.group("date"))

    if invoice.due_date is None:
        due = re.search(
            r"date\s+d['’]échéance\s*:\s*(?P<date>\d{2}/\d{2}/\d{4})",
            normalized,
            flags=re.IGNORECASE,
        )
        if due is not None:
            invoice.due_date = _parse_french_date(due.group("date"))

    if invoice.currency is None and (
        "devise : euro (eur)" in lower or re.search(r"\bEUR\b", text)
    ):
        invoice.currency = "EUR"

    parallel_totals = _parallel_totals_summary(text)
    if parallel_totals is not None:
        subtotal, vat_amount, total = parallel_totals
    else:
        subtotal = _labeled_amount(normalized, r"TOTAL\s+HT")
        vat_amount = _labeled_amount(normalized, r"TOTAL\s+TVA")
        total = _labeled_amount(normalized, r"TOTAL\s+TTC")

    if subtotal is not None:
        invoice.subtotal = subtotal
    if vat_amount is not None:
        invoice.vat_amount = vat_amount
    if total is not None:
        invoice.total = total

    detail = re.search(
        r"détail\s+tva(?P<body>.*?)(?:TOTAL\s+TVA|date\s+d['’]échéance)",
        normalized,
        flags=re.IGNORECASE,
    )
    if detail is None:
        return

    entries: list[SupplierInvoiceTaxBreakdown] = []
    for match in re.finditer(
        r"(?<![A-Za-z0-9])(?P<code>[A-Z])\s+"
        r"(?P<rate>[-+]?\d[\d.,]*)\s*%\s+"
        r"(?P<base>[-+]?\d[\d.,]*)",
        detail.group("body"),
    ):
        rate = parse_french_decimal(match.group("rate"))
        base = parse_french_decimal(match.group("base"))
        if rate is None or base is None:
            continue
        entries.append(
            SupplierInvoiceTaxBreakdown(
                category_code=match.group("code"),
                rate=rate,
                taxable_amount=base,
            )
        )

    if entries:
        invoice.tax_breakdown = entries


def parse_french_decimal(value: str) -> Decimal | None:
    compact = re.sub(r"[^0-9,.+\-]", "", value)
    if not compact:
        return None
    if "," in compact and "." in compact:
        if compact.rfind(",") > compact.rfind("."):
            compact = compact.replace(".", "").replace(",", ".")
        else:
            compact = compact.replace(",", "")
    elif "," in compact:
        compact = compact.replace(",", ".")
    try:
        return Decimal(compact)
    except InvalidOperation:
        return None


def _parallel_totals_summary(
    text: str,
) -> tuple[Decimal, Decimal, Decimal] | None:
    """Parse aligned TOTAL HT / TOTAL TVA / TOTAL TTC columns from layout text."""
    lines = text.splitlines()
    for index, line in enumerate(lines):
        lower = line.lower()
        if not all(label in lower for label in ("total ht", "total tva", "total ttc")):
            continue

        # Layout-preserving PDF extraction can put the three labels on one row and
        # their three monetary values on a following row, with unrelated prose between.
        for candidate in lines[index + 1 : index + 5]:
            values = re.findall(
                r"[-+]?\d+(?:[ .]\d{3})*(?:,\d{1,2}|\.\d{1,2})",
                candidate,
            )
            if len(values) < 3:
                continue

            parsed = [parse_french_decimal(value) for value in values[:3]]
            if all(value is not None for value in parsed):
                return parsed[0], parsed[1], parsed[2]  # type: ignore[return-value]

    return None


def _labeled_amount(text: str, label_pattern: str) -> Decimal | None:
    match = re.search(
        rf"{label_pattern}\s+(?P<amount>[-+]?\d[\d.,]*)",
        text,
        flags=re.IGNORECASE,
    )
    if match is None:
        return None
    return parse_french_decimal(match.group("amount"))


def _parse_french_date(value: str):
    try:
        return datetime.strptime(value, "%d/%m/%Y").date()
    except ValueError:
        return None
