from __future__ import annotations

import re
from decimal import Decimal
from typing import Callable, Iterable

from docflow_worker.models import DocumentContent


_CURRENCY_CODES = (
    "AED",
    "AUD",
    "CAD",
    "CHF",
    "CNY",
    "EUR",
    "GBP",
    "INR",
    "JPY",
    "KES",
    "PLN",
    "TZS",
    "USD",
    "ZAR",
)

_NUMBER_PATTERN = re.compile(r"[-+]?\d[\d\s.,]*")
_INVOICE_LABEL_PATTERN = re.compile(
    r"\binvoice\s+n(?:umber|o|a|0)?\.?\s*[:#]?\s*([A-Z0-9][A-Z0-9._/-]{2,})\b",
    re.IGNORECASE,
)


def extract_ocr_invoice_identifier(content: DocumentContent) -> str | None:
    """Recover invoice identifiers when OCR slightly corrupts the visual label.

    A common Tesseract substitution is ``Invoice No`` -> ``Invoice Na``. Keep this
    fallback label-driven so arbitrary short numbers elsewhere in a document are not
    mistaken for invoice identifiers.
    """
    for line in _lines(content):
        match = _INVOICE_LABEL_PATTERN.search(line)
        if match:
            return match.group(1).strip()
    return None


def infer_labeled_currency(content: DocumentContent) -> str | None:
    """Prefer an explicit Currency label over incidental OCR three-letter tokens."""
    for line in _lines(content):
        if not re.search(r"\bcurrenc\w*\b", line, re.IGNORECASE):
            continue
        for code in _CURRENCY_CODES:
            if re.search(rf"\b{code}\b", line, re.IGNORECASE):
                return code
    return None


def extract_preferred_invoice_total(
    content: DocumentContent,
    parse_decimal: Callable[[str | None], Decimal | None],
) -> Decimal | None:
    """Extract the best gross invoice total from OCR text using label priorities.

    This deliberately excludes non-monetary ``Total ...`` rows such as total quantity,
    total gross weight and ``Total amount in words``. It also ranks a gross/grand total
    above a remaining balance such as ``Amount due``.
    """
    best_priority = -1
    best_value: Decimal | None = None

    for line in _lines(content):
        normalized = " ".join(
            re.sub(r"[^a-z0-9%]+", " ", line.lower()).split()
        )
        compact = normalized.replace(" ", "")

        if compact.startswith(
            (
                "subtotal",
                "totalvat",
                "totaltax",
                "totalqty",
                "totalquantity",
                "totalnetweight",
                "totalgrossweight",
                "totalamountinwords",
            )
        ):
            continue

        priority = -1
        if compact.startswith(("grandtotal", "invoicetotal", "finaltotal")):
            priority = 5
        elif normalized.startswith("total due"):
            priority = 4
        elif normalized == "total" or normalized.startswith("total "):
            priority = 5
        elif normalized.startswith("amount due"):
            priority = 1

        if priority < 0:
            continue

        numbers = _numbers(line, parse_decimal)
        if not numbers:
            continue

        value = numbers[-1]
        if priority >= best_priority:
            best_priority = priority
            best_value = value

    return best_value


def _lines(content: DocumentContent) -> Iterable[str]:
    for page in content.pages:
        if page.text:
            for line in page.text.splitlines():
                stripped = line.strip()
                if stripped:
                    yield stripped
        for block in page.blocks:
            if block.text:
                for line in block.text.splitlines():
                    stripped = line.strip()
                    if stripped:
                        yield stripped


def _numbers(
    text: str,
    parse_decimal: Callable[[str | None], Decimal | None],
) -> list[Decimal]:
    values: list[Decimal] = []
    for match in _NUMBER_PATTERN.finditer(text):
        value = parse_decimal(match.group())
        if value is not None:
            values.append(value)
    return values
