from __future__ import annotations

import re
from decimal import Decimal
from typing import Callable, Iterable, Sequence

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
_PERCENT_PATTERN = re.compile(r"[-+]?\d+(?:[.,]\d+)?\s*%")
_SUBTOTAL_PATTERN = re.compile(r"^sub[\s-]*total\b", re.IGNORECASE)
_VAT_PATTERN = re.compile(r"^(?:vat|tax)\b", re.IGNORECASE)
_TOTAL_PATTERN = re.compile(
    r"^(?:grand\s+total|invoice\s+total|final\s+total(?:\s+with\s+vat)?|total\s+due|amount\s+due|total)\b",
    re.IGNORECASE,
)
_AMOUNT_IN_WORDS_PATTERN = re.compile(r"^amount\s+in\s+words\b", re.IGNORECASE)
_VAT_IDENTIFIER_PATTERN = re.compile(
    r"^(?:vat|tax)\s+(?:number|no\.?|id|reg(?:istration)?(?:\s+no\.?)?)\b",
    re.IGNORECASE,
)


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


def extract_labeled_text_value(
    content: DocumentContent,
    labels: Sequence[str],
) -> str | None:
    """Read a textual value printed after a label or on the following line."""
    lines = _lines(content)
    normalized_labels = [(_normalize_label(label), label) for label in labels]

    for index, line in enumerate(lines):
        normalized_line = _normalize_label(line)
        for normalized_label, _ in normalized_labels:
            if normalized_line == normalized_label:
                if index + 1 < len(lines):
                    return lines[index + 1].strip() or None
                continue

            # Same-line forms such as "Invoice Number: INV-2180" or
            # "Invoice No. INV-2180".
            lowered = line.strip().lower()
            for raw_label in labels:
                pattern = re.compile(
                    rf"^{re.escape(raw_label)}\s*[:.#-]?\s*(.+)$",
                    re.IGNORECASE,
                )
                match = pattern.match(line.strip())
                if match:
                    value = match.group(1).strip()
                    if value:
                        return value

    return None


def extract_totals_from_text(
    content: DocumentContent,
    parse_decimal: Callable[[str | None], Decimal | None],
) -> dict[str, Decimal | None]:
    lines = _lines(content)

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

        # Registration identifiers such as "VAT Number 156359683" are not money.
        if _VAT_IDENTIFIER_PATTERN.match(normalized):
            continue

        if normalized.startswith("total vat") or normalized.startswith("total tax"):
            amount = _tax_amount_for_labeled_line(lines, index, line, parse_decimal)
            if amount is not None:
                vat_amount = amount
            rate = _percentage(line, parse_decimal)
            if rate is not None:
                vat_rate = rate
            continue

        if _VAT_PATTERN.match(normalized):
            amount = _tax_amount_for_labeled_line(lines, index, line, parse_decimal)
            if amount is not None:
                vat_amount = amount
            rate = _percentage(line, parse_decimal)
            if rate is not None:
                vat_rate = rate
            continue

        if _TOTAL_PATTERN.match(normalized):
            amount = _amount_for_labeled_line(lines, index, numbers, parse_decimal)
            if amount is not None:
                total = amount

    # Some legacy proformas expose the final numeric amount beside/after the
    # "Amount in Words" section rather than using a dedicated TOTAL label.
    if total is None:
        for index, line in enumerate(lines):
            if _AMOUNT_IN_WORDS_PATTERN.match(line):
                amount = _amount_for_labeled_line(
                    lines,
                    index,
                    _numbers(line, parse_decimal),
                    parse_decimal,
                )
                if amount is not None:
                    total = amount
                    break

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


def _lines(content: DocumentContent) -> list[str]:
    return [
        line.strip()
        for fragment in _text_fragments(content)
        for line in fragment.splitlines()
        if line.strip()
    ]


def _normalize_label(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text.lower()).split())


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


def _percentage(
    text: str,
    parse_decimal: Callable[[str | None], Decimal | None],
) -> Decimal | None:
    match = _PERCENT_PATTERN.search(text)
    if not match:
        return None
    return parse_decimal(match.group().replace("%", "").strip())


def _tax_amount_for_labeled_line(
    lines: list[str],
    index: int,
    line: str,
    parse_decimal: Callable[[str | None], Decimal | None],
) -> Decimal | None:
    # Remove the percentage before looking for the monetary value. Otherwise a line
    # such as "TOTAL VAT 20%" would incorrectly produce 20 as the VAT amount.
    without_percent = _PERCENT_PATTERN.sub("", line)
    amount_numbers = _numbers(without_percent, parse_decimal)
    return _amount_for_labeled_line(
        lines,
        index,
        amount_numbers,
        parse_decimal,
    )


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
