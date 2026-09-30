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

_CURRENCY_SYMBOLS = (
    ("£", "GBP"),
    ("€", "EUR"),
    ("₹", "INR"),
    ("¥", "JPY"),
)

_NUMBER_PATTERN = re.compile(r"[-+]?\d[\d\s.,]*")
_SUBTOTAL_PATTERN = re.compile(r"^sub[\s-]*total\b", re.IGNORECASE)
_VAT_PATTERN = re.compile(r"^(?:vat|tax)\b", re.IGNORECASE)
_TOTAL_PATTERN = re.compile(r"^(?:grand\s+total|total)\b", re.IGNORECASE)


def infer_currency(content: DocumentContent) -> str | None:
    text = "\n".join(_text_fragments(content))

    for code in _CURRENCY_CODES:
        if re.search(rf"\b{re.escape(code)}\b", text, re.IGNORECASE):
            return code

    for symbol, code in _CURRENCY_SYMBOLS:
        if symbol in text:
            return code

    # A bare dollar sign is ambiguous globally. In the absence of an explicit ISO
    # code DocFlow treats it as USD, matching the current supplier-document scope.
    if "$" in text:
        return "USD"

    return None


def extract_totals_from_text(
    content: DocumentContent,
    parse_decimal: Callable[[str | None], Decimal | None],
) -> dict[str, Decimal | None]:
    lines = [
        line.strip()
        for fragment in _text_fragments(content)
        for line in fragment.splitlines()
        if line.strip()
    ]

    subtotal: Decimal | None = None
    vat_rate: Decimal | None = None
    vat_amount: Decimal | None = None
    total: Decimal | None = None

    for index, line in enumerate(lines):
        normalized = " ".join(line.lower().split())
        numbers = _numbers(line, parse_decimal)

        if _SUBTOTAL_PATTERN.match(normalized):
            amount = _amount_for_labeled_line(lines, index, numbers, parse_decimal)
            if amount is not None:
                subtotal = amount
            continue

        if _VAT_PATTERN.match(normalized):
            amount = _amount_for_labeled_line(lines, index, numbers, parse_decimal)
            if amount is not None:
                vat_amount = amount

            percent_match = re.search(r"([-+]?\d+(?:[.,]\d+)?)\s*%", line)
            if percent_match:
                vat_rate = parse_decimal(percent_match.group(1))
            continue

        if _TOTAL_PATTERN.match(normalized):
            # "Total VAT" and "Total Tax" are tax summaries, not invoice totals.
            if normalized.startswith("total vat") or normalized.startswith("total tax"):
                continue

            amount = _amount_for_labeled_line(lines, index, numbers, parse_decimal)
            if amount is not None:
                total = amount

    # Some real proformas print only line values, VAT and grand total. If net total is
    # omitted, total - VAT is a deterministic recovery of the pre-tax amount.
    if subtotal is None and total is not None and vat_amount is not None:
        subtotal = total - vat_amount

    return {
        "subtotal": subtotal,
        "vat_rate": vat_rate,
        "vat_amount": vat_amount,
        "total": total,
    }


def _text_fragments(content: DocumentContent) -> Iterable[str]:
    for page in content.pages:
        if page.text:
            yield page.text
        for block in page.blocks:
            if block.text:
                yield block.text


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


def _amount_for_labeled_line(
    lines: list[str],
    index: int,
    numbers: list[Decimal],
    parse_decimal: Callable[[str | None], Decimal | None],
) -> Decimal | None:
    if numbers:
        return numbers[-1]

    if index + 1 >= len(lines):
        return None

    next_line = lines[index + 1]
    next_numbers = _numbers(next_line, parse_decimal)
    if not next_numbers:
        return None

    # Only accept a following line when it is amount-like, not normal prose or an
    # item description. This covers layouts such as "SUB TOTAL(TZS)" then "60,762.71".
    stripped = re.sub(r"[A-Za-z]{3}", "", next_line)
    stripped = re.sub(r"[£€₹¥$\s]", "", stripped)
    if not re.fullmatch(r"[-+]?\d[\d.,]*", stripped):
        return None

    return next_numbers[-1]
