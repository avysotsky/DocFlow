from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from docflow_worker.models import DocumentContent
from docflow_worker.supplier_invoice_models import SupplierInvoiceData, SupplierInvoiceItem


@dataclass(frozen=True)
class _LayoutProfile:
    name: str
    markers: tuple[str, ...]
    quantity_position: int
    unit_price_position: int | None
    line_total_position: int
    description_side: str = "before"


_LAYOUT_PROFILES = (
    _LayoutProfile(
        "meter_copy",
        ("prev meter", "curr meter", "used", "charge"),
        2,
        3,
        4,
    ),
    _LayoutProfile(
        "ocr_unit_net",
        ("unit price", "netamt", "vatquantity", "description"),
        0,
        1,
        2,
        "after",
    ),
    _LayoutProfile(
        "quantity_description_each_net",
        ("quantity description", "each", "net amount"),
        0,
        1,
        2,
        "after",
    ),
    _LayoutProfile(
        "bilingual_description_vat_net_price",
        ("description", "vat", "net price"),
        0,
        1,
        3,
        "pending",
    ),
    _LayoutProfile(
        "qty_degraded_description_rate_total",
        ("qty", "descrip on", "rate", "total"),
        0,
        1,
        2,
        "after",
    ),
    _LayoutProfile(
        "date_description_vat_qty_rate_amount",
        ("date", "description", "vat", "qty", "rate", "amount"),
        1,
        2,
        3,
        "last_before",
    ),
    _LayoutProfile(
        "description_qtyhrs_price_vat_net",
        ("description", "qty hrs", "price rate", "net"),
        0,
        1,
        -1,
    ),
    _LayoutProfile(
        "activity_qty_rate_vat_amount",
        ("activity", "qty", "rate", "vat", "amount"),
        0,
        1,
        -1,
    ),
    _LayoutProfile(
        "activity_qty_rate_amount",
        ("activity", "qty", "rate", "amount"),
        0,
        1,
        -1,
    ),
    _LayoutProfile(
        "item_description_qty_unit_total",
        ("item description", "qty", "unit price", "total price"),
        0,
        1,
        2,
    ),
    _LayoutProfile(
        "description_quantity_unit_vat",
        ("description", "quantity", "unit price", "vat"),
        0,
        1,
        -1,
    ),
    _LayoutProfile(
        "description_quantity_rate_amount",
        ("description", "quantity", "rate", "amount"),
        0,
        1,
        2,
    ),
    _LayoutProfile(
        "description_qty_unit_net_amount",
        ("description", "qty", "unit price", "net amount"),
        1,
        2,
        3,
    ),
    _LayoutProfile(
        "item_description_qty_rate_amount",
        ("item", "description", "qty", "rate", "amount"),
        -3,
        -2,
        -1,
    ),
    _LayoutProfile(
        "quantity_description_unit_net_vat",
        ("quantity", "description", "unit", "net", "vat"),
        0,
        1,
        2,
        "after",
    ),
    _LayoutProfile(
        "qty_item_amount_vat_gross",
        ("qty", "item", "amount", "vat amt", "vat rate", "gross amt"),
        0,
        None,
        1,
        "after",
    ),
    _LayoutProfile(
        "description_quantity_unit_amount",
        ("description", "quantity", "unit price", "amount"),
        0,
        1,
        2,
    ),
)

_DATE_PATTERNS = (
    re.compile(r"\b(?P<date>\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b"),
    re.compile(r"\b(?P<date>\d{1,2}-[A-Za-z]{3}-\d{2,4})\b"),
    re.compile(r"\b(?P<date>\d{1,2}\s+[A-Za-z]{3,9}\s*\d{4})\b"),
    re.compile(r"\b(?P<date>\d{1,2}\s+[A-Za-z]{3,9}\s+\d{2})\b"),
    re.compile(r"\b(?P<date>[A-Za-z]{3,9}\s+\d{1,2},\s*\d{4})\b"),
    re.compile(r"\b(?P<date>\d{1,2}(?:st|nd|rd|th)\s+[A-Za-z]{3,9}\s+'?\d{2,4})\b", re.IGNORECASE),
)
_DATE_FORMATS = (
    "%d/%m/%Y",
    "%d/%m/%y",
    "%d-%m-%Y",
    "%d-%m-%y",
    "%d-%b-%Y",
    "%d-%b-%y",
    "%d %b %Y",
    "%d %B %Y",
    "%b %d, %Y",
    "%B %d, %Y",
    "%d %b %y",
    "%d %B %y",
)

_TERMINATOR_PREFIXES = (
    "subtotal",
    "sub total",
    "total",
    "vat total",
    "vat rate",
    "amount due",
    "balance due",
    "payment due",
    "payment should",
    "please deduct",
    "vat summary",
    "notes",
    "terms",
    "bank details",
    "please use invoice",
    "alternatively payment",
    "monies to be drawn",
    "delivery to",
)

_CONTINUATION_EXCLUSIONS = (
    "please",
    "account",
    "sort code",
    "registered",
    "toner excess",
    "if you",
    "if paid by",
    "entitled to",
    "valued at",
    "payment",
)


def apply_generic_invoice_recovery(
    content: DocumentContent,
    invoice: SupplierInvoiceData,
) -> None:
    """Recover common real-world invoice layouts missed by the primary parser.

    The recovery remains deterministic. It recognizes layout families by column
    semantics rather than supplier identity and prefers arithmetic reconciliation
    over accepting free-form OCR guesses.
    """
    _recover_identifiers_and_dates(content, invoice)

    layout_items = _recover_layout_items(content)
    vertical_items = _recover_vertical_items(content)
    recovered_items = vertical_items or layout_items
    if recovered_items:
        recovered_total = _money(
            sum(
                (item.line_total for item in recovered_items if item.line_total is not None),
                Decimal("0"),
            )
        )
        existing_total = _money(
            sum(
                (item.line_total for item in invoice.items if item.line_total is not None),
                Decimal("0"),
            )
        )

        candidate_reconciles = (
            invoice.subtotal is not None
            and abs(recovered_total - _money(invoice.subtotal)) <= Decimal("0.01")
        )
        existing_reconciles = (
            invoice.subtotal is not None
            and abs(existing_total - _money(invoice.subtotal)) <= Decimal("0.01")
        )

        same_numeric_items = _same_numeric_items(invoice.items, recovered_items)
        description_upgrade = (
            same_numeric_items
            and _descriptions_are_more_complete(recovered_items, invoice.items)
            and (
                bool(vertical_items)
                or _has_wrapped_business_item_header(content)
            )
        )

        if description_upgrade:
            for existing_item, recovered_item in zip(invoice.items, recovered_items):
                if len(recovered_item.description.strip()) > len(existing_item.description.strip()):
                    existing_item.description = recovered_item.description
        elif (
            not invoice.items
            or (candidate_reconciles and not existing_reconciles)
            or len(recovered_items) > len(invoice.items)
            or (
                len(recovered_items) == len(invoice.items)
                and not existing_reconciles
            )
        ):
            invoice.items = recovered_items

    _recover_summary_totals(content, invoice)
    _recover_labeled_vat_rate(content, invoice)
    _recover_invoice_discount(content, invoice)
    _reconcile_items_and_totals(invoice)


def _recover_identifiers_and_dates(
    content: DocumentContent,
    invoice: SupplierInvoiceData,
) -> None:
    text = content.text

    _recover_vertical_header_fields(text, invoice)

    recovered_identifier = _extract_invoice_identifier(text)
    if recovered_identifier:
        invoice.invoice_number = recovered_identifier

    if invoice.invoice_date is None:
        invoice.invoice_date = _extract_labeled_date(
            text,
            labels=("invoice date", "issue date", "date"),
            exclude=("due date", "payment date", "start date", "end date"),
        )

    if invoice.due_date is None:
        invoice.due_date = _extract_labeled_date(
            text,
            labels=("due date", "payment due", "due on", "due by"),
        )

    if invoice.invoice_date is None:
        invoice.invoice_date = _extract_date_near_invoice_identifier(text)

    if invoice.invoice_date is None:
        invoice.invoice_date = _derive_invoice_date_from_explicit_due_terms(text)

    if invoice.purchase_order_number is None:
        invoice.purchase_order_number = _extract_column_value(
            text,
            labels=(
                "po",
                "p o",
                "po no",
                "p o no",
                "po number",
                "p o number",
                "purchase order",
                "purchase order no",
            ),
        ) or _extract_inline_purchase_order(text)


def _extract_invoice_identifier(text: str) -> str | None:
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    direct_patterns = (
        re.compile(
            r"\b(?:vat\s+|sales\s+|tax\s+|product\s+)?"
            r"invoice\s*(?:no\.?|number|#)?\s*[:#]?\s*"
            r"(?P<value>[A-Z][A-Z0-9._/-]*\d[A-Z0-9._/-]*|\d{3,})\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\b(?:f?invaice)\s*no\.?\s*[:#]?\s*(?P<value>\d{3,})\b",
            re.IGNORECASE,
        ),
    )

    for line in lines:
        for pattern in direct_patterns:
            match = pattern.search(line)
            if match:
                return _clean_identifier(match.group("value"))

    for index, line in enumerate(lines):
        normalized = _normalize(line)

        if "date" in normalized and "invoice" in normalized:
            for candidate in lines[index + 1 : index + 3]:
                prefixed = re.findall(
                    r"\b[A-Z]{2,}[A-Z0-9._/-]*\d[A-Z0-9._/-]*\b",
                    candidate,
                    flags=re.IGNORECASE,
                )
                invoice_prefixed = [
                    value for value in prefixed
                    if value.upper().startswith("INV")
                ]
                if invoice_prefixed:
                    return _clean_identifier(invoice_prefixed[-1])

                numeric = re.findall(r"\b\d{5,}\b", candidate)
                if numeric:
                    return numeric[-1]

        if normalized == "invoice":
            for candidate in lines[index + 1 : index + 4]:
                match = re.match(
                    r"^number\s*[:#]?\s*(?P<value>[A-Z0-9._/-]{3,})$",
                    candidate.strip(),
                    flags=re.IGNORECASE,
                )
                if match:
                    return _clean_identifier(match.group("value"))

        if normalized == "product invoice":
            for candidate in lines[index + 1 : index + 4]:
                if re.fullmatch(r"\d{3,}", candidate.strip()):
                    return candidate.strip()

    return None


def _clean_identifier(value: str) -> str:
    value = value.strip()
    upper = value.upper().replace(" ", "")
    for suffix in ("PAYMENTADVICE", "PAYMENT"):
        position = upper.find(suffix)
        if position > 0:
            return value[:position].rstrip("._/- ")
    return value


def _extract_labeled_date(
    text: str,
    *,
    labels: tuple[str, ...],
    exclude: tuple[str, ...] = (),
) -> date | None:
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    for index, line in enumerate(lines):
        normalized = _normalize(line)
        if any(label in normalized for label in exclude):
            continue

        if not any(_date_label_matches(normalized, label) for label in labels):
            continue

        value = _parse_date_from_text(line)
        if value is not None:
            return value

        for candidate in lines[index + 1 : index + 3]:
            value = _parse_date_from_text(candidate)
            if value is not None:
                return value

    return None


def _date_label_matches(normalized_line: str, label: str) -> bool:
    normalized_label = _normalize(label)
    if normalized_label in {"invoice date", "issue date", "due date", "payment due"}:
        return normalized_label in normalized_line
    if normalized_label == "date":
        return bool(re.search(r"\bdate\b", normalized_line))
    return normalized_label in normalized_line


def _parse_date_from_text(value: str) -> date | None:
    normalized = re.sub(
        r"\b(\d{1,2})(?:st|nd|rd|th)\b",
        r"\1",
        value,
        flags=re.IGNORECASE,
    )
    normalized = re.sub(r"(?<=\d)(?=[A-Za-z])", " ", normalized)
    normalized = re.sub(r"(?<=[A-Za-z])(?=\d)", " ", normalized)
    normalized = re.sub(r"\s+'(?=\d{2}\b)", " ", normalized)

    for pattern in _DATE_PATTERNS:
        match = pattern.search(normalized)
        if match is None:
            continue

        candidate = " ".join(match.group("date").split())
        for date_format in _DATE_FORMATS:
            try:
                return datetime.strptime(candidate, date_format).date()
            except ValueError:
                continue

    return None



def _extract_date_near_invoice_identifier(text: str) -> date | None:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    direct_invoice = re.compile(
        r"\b(?:vat\s+|sales\s+|tax\s+|product\s+)?"
        r"invoice\s*(?:no\.?|number|#)?\s*[:#]?\s*"
        r"(?:[A-Z][A-Z0-9._/-]*\d[A-Z0-9._/-]*|\d{3,})\b",
        re.IGNORECASE,
    )

    for index, line in enumerate(lines):
        if direct_invoice.search(line) is None:
            continue

        lower_bound = max(0, index - 2)
        for candidate in reversed(lines[lower_bound:index]):
            value = _parse_date_from_text(candidate)
            if value is not None:
                return value

    return None


def _derive_invoice_date_from_explicit_due_terms(text: str) -> date | None:
    normalized = " ".join(text.casefold().split())
    if "payment due within 30 days of invoice date" not in normalized:
        return None

    match = re.search(
        r"payment\s+due\s+(?P<date>\d{1,2}/\d{1,2}/\d{4})",
        text,
        flags=re.IGNORECASE,
    )
    if match is None:
        return None

    due_date = _parse_date_from_text(match.group("date"))
    if due_date is None:
        return None

    return due_date - timedelta(days=30)


def _extract_inline_purchase_order(text: str) -> str | None:
    match = re.search(
        r"\b(?:P\.?\s*O\.?|Purchase\s+Order)(?:\s*(?:No\.?|Number))?\s*#?\s*[:#]?\s*"
        r"(?P<value>[A-Z0-9._/-]{4,})\b",
        text,
        flags=re.IGNORECASE,
    )
    if match is None:
        return None
    return match.group("value").strip()


def _extract_column_value(
    text: str,
    *,
    labels: tuple[str, ...],
) -> str | None:
    rows = [_split_columns(line) for line in text.splitlines() if line.strip()]

    for index, row in enumerate(rows[:-1]):
        normalized = [_normalize(cell) for cell in row]
        for label in labels:
            normalized_label = _normalize(label)
            try:
                column = normalized.index(normalized_label)
            except ValueError:
                continue

            next_row = rows[index + 1]
            if column >= len(next_row):
                continue

            candidate = next_row[column].strip()
            if re.fullmatch(r"[A-Z0-9._/-]{3,}", candidate, flags=re.IGNORECASE):
                return candidate

    return None



def _recover_vertical_header_fields(
    text: str,
    invoice: SupplierInvoiceData,
) -> None:
    """Recover values from PDF tables emitted as vertical or aligned header/value streams."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    normalized = [_normalize(line) for line in lines]

    rows = [_split_columns(line) for line in lines]
    for index, row in enumerate(rows[:-1]):
        header = [_normalize(cell) for cell in row]
        if not {"invoice no", "date", "due date"}.issubset(set(header)):
            continue

        values = rows[index + 1]
        try:
            invoice_index = header.index("invoice no")
            date_index = header.index("date")
            due_index = header.index("due date")
        except ValueError:
            continue

        if invoice_index < len(values):
            identifier = _clean_identifier(values[invoice_index])
            if identifier and any(character.isdigit() for character in identifier):
                invoice.invoice_number = identifier
        if date_index < len(values):
            recovered_date = _parse_date_from_text(values[date_index])
            if recovered_date is not None:
                invoice.invoice_date = recovered_date
        if due_index < len(values):
            recovered_due = _parse_date_from_text(values[due_index])
            if recovered_due is not None:
                invoice.due_date = recovered_due
        break

    for index in range(len(lines) - 7):
        header = normalized[index : index + 6]
        if header[:4] != ["invoice no", "date", "total due", "due date"]:
            continue

        values = lines[index + 6 : index + 12]
        if len(values) < 4:
            continue

        identifier = _clean_identifier(values[0])
        invoice_date = _parse_date_from_text(values[1])
        due_date = _parse_date_from_text(values[3])

        if identifier and any(character.isdigit() for character in identifier):
            invoice.invoice_number = identifier
        if invoice_date is not None:
            invoice.invoice_date = invoice_date
        if due_date is not None:
            invoice.due_date = due_date
        return


def _recover_vertical_items(content: DocumentContent) -> list[SupplierInvoiceItem]:
    recovered: list[SupplierInvoiceItem] = []

    for page in content.pages:
        lines = [line.strip() for line in page.text.splitlines() if line.strip()]
        normalized = [_normalize(line) for line in lines]

        recovered.extend(_recover_bilingual_net_price_items(lines, normalized))
        recovered.extend(_recover_qty_description_rate_total_items(lines, normalized))
        recovered.extend(_recover_vertical_quickbooks_items(lines, normalized))
        recovered.extend(_recover_vertical_stubbington_items(lines, normalized))
        recovered.extend(_recover_vertical_wiltshire_items(lines, normalized))
        recovered.extend(_recover_vertical_halc_items(lines, normalized))
        recovered.extend(_recover_vertical_zoho_items(lines, normalized))
        recovered.extend(_recover_vertical_microsoft_items(lines, normalized))

    unique: list[SupplierInvoiceItem] = []
    seen: set[tuple[str, Decimal, Decimal | None, Decimal | None]] = set()
    for item in recovered:
        key = (
            item.description,
            item.quantity,
            item.unit_price,
            item.line_total,
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def _recover_bilingual_net_price_items(
    lines: list[str],
    normalized: list[str],
) -> list[SupplierInvoiceItem]:
    header_end: int | None = None
    for index in range(len(lines)):
        window = " ".join(normalized[index : index + 2])
        if "description" in window and "vat" in window and "net price" in window:
            header_end = min(index + 1, len(lines) - 1)
            break
    if header_end is None:
        return []

    description_buffer: list[str] = []
    for line in lines[header_end + 1 :]:
        if _is_terminator(line) or "due date" in _normalize(line):
            break

        cells = _split_columns(line)
        numeric = _numeric_cells(cells)
        if len(numeric) >= 4:
            quantity = numeric[0][1]
            unit_price = numeric[1][1]
            line_total = numeric[-1][1]
            if (
                description_buffer
                and quantity > 0
                and _money(quantity * unit_price) == _money(line_total)
            ):
                return [
                    SupplierInvoiceItem(
                        sku=None,
                        description=_clean_description(" ".join(description_buffer)),
                        quantity=quantity,
                        unit_price=unit_price,
                        line_total=line_total,
                    )
                ]

        if re.search(r"[A-Za-z]", line) and not numeric:
            description_buffer.append(line.strip())

    return []


def _recover_qty_description_rate_total_items(
    lines: list[str],
    normalized: list[str],
) -> list[SupplierInvoiceItem]:
    start = next(
        (
            index
            for index, value in enumerate(normalized)
            if "qty" in value
            and ("description" in value or "descrip on" in value)
            and "rate" in value
            and "total" in value
        ),
        None,
    )
    if start is None:
        return []

    items: list[SupplierInvoiceItem] = []
    row_pattern = re.compile(
        r"^\s*(?P<qty>\d+(?:[.,]\d+)?)\s+"
        r"(?P<description>.+?)\s+"
        r"(?P<rate>\d[\d,.]*)\s+"
        r"(?P<total>\d[\d,.]*)\s*$"
    )

    for line in lines[start + 1 :]:
        if _is_terminator(line) or _normalize(line).startswith("net"):
            break

        cells = _split_columns(line)
        numeric = _numeric_cells(cells)
        description = ""
        quantity: Decimal | None = None
        unit_price: Decimal | None = None
        line_total: Decimal | None = None

        if len(numeric) >= 3:
            quantity = numeric[0][1]
            unit_price = numeric[-2][1]
            line_total = numeric[-1][1]
            quantity_cell = numeric[0][0]
            rate_cell = numeric[-2][0]
            description = _clean_description(
                " ".join(
                    cell
                    for cell in cells[quantity_cell + 1 : rate_cell]
                    if re.search(r"[A-Za-z]", cell)
                )
            )
        else:
            match = row_pattern.match(line)
            if match:
                quantity, _ = _parse_number(match.group("qty"))
                unit_price, _ = _parse_number(match.group("rate"))
                line_total, _ = _parse_number(match.group("total"))
                description = _clean_description(match.group("description"))

        if (
            quantity is None
            or unit_price is None
            or line_total is None
            or quantity <= 0
            or not description
        ):
            continue

        if _money(quantity * unit_price) != _money(line_total):
            continue

        items.append(
            SupplierInvoiceItem(
                sku=None,
                description=description,
                quantity=quantity,
                unit_price=unit_price,
                line_total=line_total,
            )
        )

    return items


def _recover_vertical_quickbooks_items(
    lines: list[str],
    normalized: list[str],
) -> list[SupplierInvoiceItem]:
    header = _find_vertical_header_sequence(
        normalized,
        ("activity", "qty", "rate"),
        optional=("vat",),
        terminal="amount",
    )
    if header is None:
        return []

    start, end, has_vat = header
    section = _vertical_section(lines, end + 1)
    items: list[SupplierInvoiceItem] = []
    description_buffer: list[str] = []
    index = 0

    while index < len(section):
        quantity = _parse_vertical_number(section[index])
        if quantity is None:
            description_buffer.append(section[index])
            index += 1
            continue

        required = 4 if has_vat else 3
        if index + required - 1 >= len(section):
            break

        unit_price = _parse_vertical_number(section[index + 1])
        if unit_price is None:
            description_buffer.append(section[index])
            index += 1
            continue

        if has_vat:
            vat_token = section[index + 2]
            if "%" not in vat_token:
                description_buffer.append(section[index])
                index += 1
                continue
            line_total = _parse_vertical_number(section[index + 3])
            consumed = 4
        else:
            line_total = _parse_vertical_number(section[index + 2])
            consumed = 3

        if line_total is None or quantity <= 0:
            description_buffer.append(section[index])
            index += 1
            continue

        description = _clean_description(" ".join(description_buffer))
        if description and _money(quantity * unit_price) == _money(line_total):
            item = SupplierInvoiceItem(
                sku=None,
                description=description,
                quantity=quantity,
                unit_price=unit_price,
                line_total=line_total,
            )

            next_index = index + consumed
            continuation: list[str] = []
            while next_index < len(section):
                candidate = section[next_index].strip()
                if not candidate or _is_terminator(candidate):
                    break
                if _parse_vertical_number(candidate) is not None:
                    break
                normalized_candidate = _normalize(candidate)
                if any(
                    normalized_candidate.startswith(prefix)
                    for prefix in _CONTINUATION_EXCLUSIONS
                ):
                    break
                continuation.append(candidate)
                next_index += 1

            if continuation:
                item.description = _clean_description(
                    f"{item.description} {' '.join(continuation)}"
                )

            items.append(item)
            description_buffer = []
            index = next_index
            continue

        description_buffer.append(section[index])
        index += 1

    return items


def _recover_vertical_stubbington_items(
    lines: list[str],
    normalized: list[str],
) -> list[SupplierInvoiceItem]:
    sequence = ("date", "activity", "description", "vat", "qty", "rate", "amount")
    start = _find_exact_sequence(normalized, sequence)
    if start is None:
        return []

    section = _vertical_section(lines, start + len(sequence))
    if len(section) < 6:
        return []

    numeric_start = next(
        (
            index
            for index in range(len(section) - 3)
            if all(_parse_vertical_number(value) is not None for value in section[index:index + 4])
        ),
        None,
    )
    if numeric_start is None or numeric_start < 2:
        return []

    values = [
        _parse_vertical_number(value)
        for value in section[numeric_start : numeric_start + 4]
    ]
    if any(value is None for value in values):
        return []

    _, quantity, unit_price, line_total = values
    assert quantity is not None and unit_price is not None and line_total is not None
    if quantity <= 0 or _money(quantity * unit_price) != _money(line_total):
        return []

    description = _clean_description(section[numeric_start - 1])
    if not description:
        return []

    return [
        SupplierInvoiceItem(
            sku=None,
            description=description,
            quantity=quantity,
            unit_price=unit_price,
            line_total=line_total,
        )
    ]


def _recover_vertical_wiltshire_items(
    lines: list[str],
    normalized: list[str],
) -> list[SupplierInvoiceItem]:
    start = next(
        (
            index
            for index, value in enumerate(normalized)
            if value == "description"
            and "qty" in normalized[index + 1 : index + 4]
            and any("unit price" in item for item in normalized[index + 1 : index + 7])
            and any("net amount" in item for item in normalized[index + 1 : index + 9])
        ),
        None,
    )
    if start is None:
        return []

    end = min(len(lines), start + 10)
    section = _vertical_section(lines, end)
    if not section:
        return []

    first_alpha = next(
        (index for index, value in enumerate(section) if re.search(r"[A-Za-z]", value)),
        None,
    )
    if first_alpha is None:
        return []

    numeric_tail = [
        (index, number)
        for index, value in enumerate(section[first_alpha + 1 :], start=first_alpha + 1)
        if (number := _parse_vertical_number(value)) is not None
    ]
    if len(numeric_tail) < 3:
        return []

    quantity = numeric_tail[0][1]
    unit_price = numeric_tail[1][1]
    line_total = numeric_tail[2][1]
    if quantity <= 0 or _money(quantity * unit_price) != _money(line_total):
        return []

    numeric_start = numeric_tail[0][0]
    description = _clean_description(
        " ".join(
            value
            for value in section[first_alpha:numeric_start]
            if re.search(r"[A-Za-z]", value)
        )
    )
    if not description:
        return []

    return [
        SupplierInvoiceItem(
            sku=None,
            description=description,
            quantity=quantity,
            unit_price=unit_price,
            line_total=line_total,
        )
    ]


def _recover_vertical_halc_items(
    lines: list[str],
    normalized: list[str],
) -> list[SupplierInvoiceItem]:
    start = _find_exact_sequence(
        normalized,
        ("quantity", "description", "unit", "price", "net", "amount"),
    )
    if start is None:
        return []

    section = _vertical_section(lines, start + 6)
    cleaned = [
        value
        for value in section
        if value not in {".", "£", "|"}
    ]
    if not cleaned:
        return []

    quantity_index = next(
        (
            index
            for index, value in enumerate(cleaned)
            if _parse_vertical_number(value) is not None
        ),
        None,
    )
    if quantity_index is None:
        return []

    quantity = _parse_vertical_number(cleaned[quantity_index])
    first_alpha = next(
        (
            index
            for index in range(quantity_index + 1, len(cleaned))
            if re.search(r"[A-Za-z]", cleaned[index])
        ),
        None,
    )
    if quantity is None or first_alpha is None:
        return []

    numeric_after = [
        (index, number)
        for index, value in enumerate(cleaned[first_alpha + 1 :], start=first_alpha + 1)
        if (number := _parse_vertical_number(value)) is not None
    ]
    if len(numeric_after) < 2:
        return []

    unit_price = numeric_after[0][1]
    line_total = numeric_after[1][1]
    if quantity <= 0 or _money(quantity * unit_price) != _money(line_total):
        return []

    description = _clean_description(
        " ".join(
            value
            for value in cleaned[first_alpha:numeric_after[0][0]]
            if re.search(r"[A-Za-z]", value)
        )
    )
    if not description:
        return []

    return [
        SupplierInvoiceItem(
            sku=None,
            description=description,
            quantity=quantity,
            unit_price=unit_price,
            line_total=line_total,
        )
    ]


def _recover_vertical_zoho_items(
    lines: list[str],
    normalized: list[str],
) -> list[SupplierInvoiceItem]:
    start = _find_exact_sequence(
        normalized,
        ("item", "description", "qty", "rate", "amount"),
    )
    if start is None:
        return []

    section = _vertical_section(lines, start + 5)
    numeric = [
        (index, number)
        for index, value in enumerate(section)
        if (number := _parse_vertical_number(value)) is not None
    ]
    if len(numeric) < 3:
        return []

    quantity_index, quantity = numeric[-3]
    _, unit_price = numeric[-2]
    _, line_total = numeric[-1]
    if quantity <= 0 or _money(quantity * unit_price) != _money(line_total):
        return []

    description = _clean_description(
        " ".join(
            value
            for value in section[:quantity_index]
            if re.search(r"[A-Za-z]", value)
            and not re.fullmatch(r"[A-Z0-9._/-]{4,}", value)
        )
    ) or "Invoice item"

    return [
        SupplierInvoiceItem(
            sku=None,
            description=description,
            quantity=quantity,
            unit_price=unit_price,
            line_total=line_total,
        )
    ]


def _recover_vertical_microsoft_items(
    lines: list[str],
    normalized: list[str],
) -> list[SupplierInvoiceItem]:
    start = next(
        (
            index
            for index, value in enumerate(normalized)
            if "charge start date charge end date" in value
        ),
        None,
    )
    if start is None:
        return []

    end = (
        start
        if "indicator" in normalized[start]
        else next(
            (
                index
                for index in range(start + 1, min(len(lines), start + 20))
                if "tax line indicator" in normalized[index]
                or (
                    normalized[index] == "indicator"
                    and index > start
                    and normalized[index - 1] == "tax line"
                )
            ),
            None,
        )
    )
    if end is None:
        return []

    section = _vertical_section(lines, end + 1)
    numeric = [
        number
        for value in section[:12]
        if (number := _parse_vertical_number(value)) is not None
    ]

    if len(numeric) < 5:
        for value in section[:6]:
            row_numbers = [number for _, number, _, _ in _numeric_cells(_split_columns(value))]
            if len(row_numbers) >= 5:
                numeric = row_numbers
                break

    if len(numeric) < 5:
        return []

    unit_price, quantity, charge, _tax_rate, line_total = numeric[:5]
    if quantity <= 0:
        return []
    if _money(quantity * unit_price) != _money(charge):
        return []
    if _money(charge) != _money(line_total):
        return []

    return [
        SupplierInvoiceItem(
            sku=None,
            description="Microsoft service charge",
            quantity=quantity,
            unit_price=unit_price,
            line_total=line_total,
        )
    ]


def _find_vertical_header_sequence(
    normalized: list[str],
    required: tuple[str, ...],
    *,
    optional: tuple[str, ...],
    terminal: str,
) -> tuple[int, int, bool] | None:
    for start in range(len(normalized)):
        if normalized[start] != required[0]:
            continue

        cursor = start
        ok = True
        for marker in required[1:]:
            cursor += 1
            if cursor >= len(normalized) or normalized[cursor] != marker:
                ok = False
                break
        if not ok:
            continue

        cursor += 1
        has_optional = False
        if cursor < len(normalized) and normalized[cursor] in optional:
            has_optional = True
            cursor += 1

        if cursor < len(normalized) and normalized[cursor] == terminal:
            return start, cursor, has_optional

    return None


def _find_exact_sequence(
    normalized: list[str],
    sequence: tuple[str, ...],
) -> int | None:
    width = len(sequence)
    for index in range(len(normalized) - width + 1):
        if tuple(normalized[index:index + width]) == sequence:
            return index
    return None


def _vertical_section(lines: list[str], start: int) -> list[str]:
    section: list[str] = []
    for value in lines[start:]:
        if section and _is_terminator(value):
            break
        section.append(value)
    return section


def _parse_vertical_number(value: str) -> Decimal | None:
    raw = value.strip()
    if not raw:
        return None

    if re.search(r"[A-Za-z]", raw):
        if not re.fullmatch(r"[-+£€$¥₹\d\s,.:~%]+(?:\s*[Ss])?", raw):
            return None

    raw = re.sub(r"\s+[Ss]$", "", raw)
    number, _ = _parse_number(raw)
    return number


def _has_wrapped_business_item_header(content: DocumentContent) -> bool:
    for line in content.text.splitlines():
        normalized = _normalize(line)
        if (
            "activity" in normalized
            and "qty" in normalized
            and "rate" in normalized
            and "amount" in normalized
        ):
            return True
        if (
            "description" in normalized
            and "quantity" in normalized
            and "unit price" in normalized
            and "discount" in normalized
            and "amount" in normalized
        ):
            return True
    return False


def _same_numeric_items(
    left: list[SupplierInvoiceItem],
    right: list[SupplierInvoiceItem],
) -> bool:
    if len(left) != len(right) or not left:
        return False

    return all(
        a.quantity == b.quantity
        and a.unit_price == b.unit_price
        and a.line_total == b.line_total
        for a, b in zip(left, right)
    )


def _descriptions_are_more_complete(
    candidate: list[SupplierInvoiceItem],
    existing: list[SupplierInvoiceItem],
) -> bool:
    if len(candidate) != len(existing):
        return False

    return any(
        len(new.description.strip()) > len(old.description.strip())
        and new.description.strip().startswith(old.description.strip())
        for new, old in zip(candidate, existing)
    )



def _recover_layout_items(content: DocumentContent) -> list[SupplierInvoiceItem]:
    recovered: list[SupplierInvoiceItem] = []

    for page in content.pages:
        lines = [line.rstrip() for line in page.text.splitlines()]
        index = 0

        while index < len(lines):
            profile = _find_profile(lines[index])
            if profile is None:
                index += 1
                continue

            section: list[SupplierInvoiceItem] = []
            pending_description: str | None = None
            continuation_budget = 0
            cursor = index + 1

            while cursor < len(lines):
                if _find_profile(lines[cursor]) is not None:
                    break
                if _is_terminator(lines[cursor]):
                    break

                raw_line = lines[cursor]
                line = raw_line.strip()
                if not line:
                    cursor += 1
                    continue

                parsed = _parse_profile_row(
                    raw_line,
                    profile,
                    pending_description=pending_description,
                )
                if parsed is not None:
                    section.append(parsed)
                    pending_description = None
                    continuation_budget = 3
                    cursor += 1
                    continue

                cells = _split_columns(raw_line)
                numbers = _numeric_cells(cells)
                has_alpha = bool(re.search(r"[A-Za-z]", line))

                if has_alpha and not numbers:
                    next_index = cursor + 1
                    while next_index < len(lines) and not lines[next_index].strip():
                        next_index += 1

                    next_line = lines[next_index] if next_index < len(lines) else ""
                    next_has_alpha = bool(re.search(r"[A-Za-z]", next_line))
                    if (
                        next_line
                        and (
                            not next_has_alpha
                            or profile.description_side == "pending"
                        )
                        and _parse_profile_row(
                            next_line,
                            profile,
                            pending_description=line,
                        )
                        is not None
                    ):
                        pending_description = line
                    elif section and continuation_budget > 0:
                        normalized = _normalize(line)
                        if (
                            "subtotal" not in normalized
                            and "vat total" not in normalized
                            and "balance due" not in normalized
                            and not any(
                                normalized.startswith(prefix)
                                for prefix in _CONTINUATION_EXCLUSIONS
                            )
                        ):
                            section[-1].description = _clean_description(
                                f"{section[-1].description} {line}"
                            )
                elif (
                    section
                    and continuation_budget > 0
                    and re.fullmatch(r"\d{4}", line)
                ):
                    section[-1].description = _clean_description(
                        f"{section[-1].description} {line}"
                    )

                continuation_budget = max(0, continuation_budget - 1)
                cursor += 1

            recovered.extend(section)
            index = max(cursor, index + 1)

    return recovered


def _find_profile(line: str) -> _LayoutProfile | None:
    normalized = _normalize(line)
    for profile in _LAYOUT_PROFILES:
        if all(marker in normalized for marker in profile.markers):
            return profile
    return None


def _parse_profile_row(
    line: str,
    profile: _LayoutProfile,
    *,
    pending_description: str | None = None,
) -> SupplierInvoiceItem | None:
    cells = _split_columns(line)
    numbers = _numeric_cells(cells)

    quantity_token = _number_at(numbers, profile.quantity_position)
    line_total_token = _number_at(numbers, profile.line_total_position)
    if quantity_token is None or line_total_token is None:
        return None

    quantity_index, quantity, _, _ = quantity_token
    _, line_total, line_total_suspicious, _ = line_total_token
    if quantity <= 0:
        return None

    unit_price: Decimal | None = None
    unit_price_suspicious = False
    if profile.unit_price_position is not None:
        unit_token = _number_at(numbers, profile.unit_price_position)
        if unit_token is not None:
            _, unit_price, unit_price_suspicious, _ = unit_token

    if (
        profile.line_total_position == -1
        and line_total_token[0] < len(cells) - 1
        and all(
            re.fullmatch(r"[A-Za-z|]{1,3}", cell.strip())
            for cell in cells[line_total_token[0] + 1 :]
        )
    ):
        line_total_suspicious = True

    description = pending_description
    if not description:
        if profile.description_side == "pending":
            description = pending_description or ""
        elif profile.description_side == "after":
            description = next(
                (
                    cell.strip()
                    for cell in cells[quantity_index + 1 :]
                    if re.search(r"[A-Za-z]", cell)
                    and _parse_date_from_text(cell) is None
                ),
                "",
            )
        else:
            parts = []
            for cell in cells[:quantity_index]:
                normalized = _normalize(cell)
                if not re.search(r"[A-Za-z]", cell):
                    continue
                if "%" in cell or normalized in {"vat", "no vat"}:
                    continue
                parts.append(cell.strip())
            if profile.description_side == "last_before":
                description = parts[-1] if parts else ""
            else:
                description = " ".join(parts)

    description = _clean_description(description or "")
    if not description:
        return None

    if unit_price is not None:
        calculated = _money(quantity * unit_price)
        printed_total = _money(line_total)

        if abs(calculated - printed_total) > Decimal("0.01"):
            if unit_price_suspicious and not line_total_suspicious:
                unit_price = printed_total / quantity
            elif line_total_suspicious and not unit_price_suspicious:
                line_total = calculated

    return SupplierInvoiceItem(
        sku=None,
        description=description,
        quantity=quantity,
        unit_price=unit_price,
        line_total=line_total,
    )


def _number_at(
    values: list[tuple[int, Decimal, bool, str]],
    position: int,
) -> tuple[int, Decimal, bool, str] | None:
    if not values:
        return None
    try:
        return values[position]
    except IndexError:
        return None


def _numeric_cells(
    cells: list[str],
) -> list[tuple[int, Decimal, bool, str]]:
    values: list[tuple[int, Decimal, bool, str]] = []
    for index, cell in enumerate(cells):
        value, suspicious = _parse_number(cell)
        if value is not None:
            values.append((index, value, suspicious, cell))
    return values


def _parse_number(value: str) -> tuple[Decimal | None, bool]:
    raw = value.strip()
    if not raw:
        return None, False

    suspicious = False

    normalized = re.sub(r"(?<=\d):(?=\d)", ".", raw)
    if normalized != raw:
        suspicious = True
    raw = normalized

    normalized = re.sub(r"(?<=\d)[OoC](?=\d)", "0", raw, flags=re.IGNORECASE)
    if normalized != raw:
        suspicious = True
    raw = normalized

    stripped = re.sub(r"[£€$¥₹%\s~]", "", raw)
    match = re.fullmatch(
        r"(?P<number>[-+]?\d[\d,.:]*)(?:[A-Za-z|]{1,3})?",
        stripped,
    )
    if match is None:
        return None, suspicious

    compact = match.group("number").replace(":", "")
    if compact != stripped:
        suspicious = True

    if "," in compact and "." in compact:
        if compact.rfind(",") > compact.rfind("."):
            compact = compact.replace(".", "").replace(",", ".")
        else:
            compact = compact.replace(",", "")
    elif "," in compact:
        tail = compact.rsplit(",", 1)[1]
        compact = (
            compact.replace(",", ".")
            if len(tail) == 2
            else compact.replace(",", "")
        )

    try:
        return Decimal(compact), suspicious
    except InvalidOperation:
        return None, suspicious


def _recover_summary_totals(
    content: DocumentContent,
    invoice: SupplierInvoiceData,
) -> None:
    text = content.text
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    # Copier/service layouts often place labels on one row and the three values on
    # the following row.
    for index, line in enumerate(lines[:-1]):
        normalized = _normalize(line)
        if (
            "inv goods" in normalized
            and "invoice vat" in normalized
            and "inv total" in normalized
        ):
            for candidate in lines[index + 1 : index + 4]:
                numbers = [
                    value
                    for _, value, _, _ in _numeric_cells(_split_columns(candidate))
                ]
                if len(numbers) >= 3:
                    subtotal, vat_amount, total = numbers[-3:]
                    if _money(subtotal + vat_amount) == _money(total):
                        invoice.subtotal = subtotal
                        invoice.vat_amount = vat_amount
                        invoice.total = total
                        break

    net = _find_labeled_amount(
        lines,
        labels=("total net amount", "nett", "net"),
    )
    vat = _find_labeled_amount(
        lines,
        labels=("total tax", "total vat", "vat"),
    )
    gross = _find_labeled_amount(
        lines,
        labels=("invoice total", "gross", "total due"),
    )

    if net is not None and vat is not None and gross is not None:
        if _money(net + vat) == _money(gross):
            if invoice.subtotal is None or _money(invoice.subtotal) != _money(net):
                invoice.subtotal = net
            if invoice.vat_amount is None or _money(invoice.vat_amount) != _money(vat):
                invoice.vat_amount = vat
            if invoice.total is None or _money(invoice.total) != _money(gross):
                invoice.total = gross


def _find_labeled_amount(
    lines: list[str],
    *,
    labels: tuple[str, ...],
) -> Decimal | None:
    for line in lines:
        normalized = _normalize(line)
        if not any(
            normalized.startswith(_normalize(label))
            or f" {_normalize(label)} " in f" {normalized} "
            for label in labels
        ):
            continue

        values = _numeric_cells(_split_columns(line))
        if values:
            return values[-1][1]

    return None


def _recover_invoice_discount(
    content: DocumentContent,
    invoice: SupplierInvoiceData,
) -> None:
    if invoice.discount_amount is not None:
        return

    patterns = (
        re.compile(
            r"subtotal\s*\(\s*includes\s+(?:a\s+)?discount\s+of\s+"
            r"(?P<amount>\d[\d,.]*)\s*\)",
            flags=re.IGNORECASE,
        ),
        re.compile(
            r"\bdiscount\s+(?:amount\s*)?[:#]?\s*[£€$¥₹]?\s*"
            r"(?P<amount>\d[\d,.]*)\b",
            flags=re.IGNORECASE,
        ),
    )

    for pattern in patterns:
        match = pattern.search(content.text)
        if match is None:
            continue
        amount, _ = _parse_number(match.group("amount"))
        if amount is not None and amount >= 0:
            invoice.discount_amount = amount
            return


def _reconcile_items_and_totals(invoice: SupplierInvoiceData) -> None:
    if not invoice.items or any(item.line_total is None for item in invoice.items):
        return

    item_total = _money(
        sum(
            (item.line_total for item in invoice.items if item.line_total is not None),
            Decimal("0"),
        )
    )

    if (
        invoice.total is not None
        and invoice.vat_rate is not None
        and invoice.discount_amount is None
    ):
        expected_vat = _money(item_total * invoice.vat_rate / Decimal("100"))
        expected_total = _money(item_total + expected_vat)
        if expected_total == _money(invoice.total):
            invoice.subtotal = item_total
            invoice.vat_amount = expected_vat
            return

    if (
        invoice.total is not None
        and invoice.vat_amount is not None
        and _money(item_total + invoice.vat_amount) == _money(invoice.total)
    ):
        invoice.subtotal = item_total


def _recover_labeled_vat_rate(
    content: DocumentContent,
    invoice: SupplierInvoiceData,
) -> None:
    lines = [line.strip() for line in content.text.splitlines() if line.strip()]
    for index, line in enumerate(lines):
        normalized = _normalize(line)
        if "vat" not in normalized or "vat no" in normalized or "vat number" in normalized:
            continue

        candidates = (line, *lines[index + 1 : index + 3])
        for candidate in candidates:
            match = re.search(r"(?P<rate>\d+(?:[.,]\d+)?)\s*%", candidate)
            if match is None:
                continue

            rate, _ = _parse_number(match.group("rate"))
            if (
                invoice.vat_rate is None
                and rate is not None
                and Decimal("0") <= rate <= Decimal("100")
            ):
                invoice.vat_rate = rate

            if invoice.vat_amount is None:
                without_rate = re.sub(
                    r"\d+(?:[.,]\d+)?\s*%",
                    "",
                    candidate,
                    count=1,
                )
                amounts = [
                    number
                    for _, number, _, _ in _numeric_cells(_split_columns(without_rate))
                ]
                if amounts:
                    invoice.vat_amount = amounts[-1]
            return

    if (
        invoice.subtotal is not None
        and invoice.vat_amount is not None
        and invoice.subtotal > 0
    ):
        common_rates = (
            Decimal("0"),
            Decimal("5"),
            Decimal("10"),
            Decimal("15"),
            Decimal("20"),
            Decimal("21"),
            Decimal("23"),
            Decimal("25"),
        )
        for rate in common_rates:
            expected = _money(invoice.subtotal * rate / Decimal("100"))
            if expected == _money(invoice.vat_amount):
                invoice.vat_rate = rate
                return


def _is_terminator(line: str) -> bool:
    normalized = _normalize(line)
    return any(normalized.startswith(prefix) for prefix in _TERMINATOR_PREFIXES)


def _split_columns(line: str) -> list[str]:
    return [
        cell.strip()
        for cell in re.split(r"[ \t]{2,}", line.strip())
        if cell.strip()
    ]


def _clean_description(value: str) -> str:
    cleaned = " ".join(value.split())
    cleaned = re.sub(r"(?<=[a-z])-\s+(?=[a-z])", "-", cleaned)
    return cleaned.strip()


def _normalize(value: str) -> str:
    return " ".join(
        re.sub(r"[^a-z0-9]+", " ", value.casefold()).split()
    )


def _money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
