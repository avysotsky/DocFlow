from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from docflow_worker.engines.base import StructuredExtractionEngine
from docflow_worker.models import DocumentContent, StructuredExtractionResult, TableContent
from docflow_worker.purchase_order_models import PurchaseOrderData, PurchaseOrderItem


class DeterministicPurchaseOrderEngine(StructuredExtractionEngine):
    """Deterministic purchase-order parser for common procurement PDF layouts."""

    @property
    def name(self) -> str:
        return "deterministic_purchase_order_v1"

    async def extract(
        self,
        content: DocumentContent,
        *,
        document_name: str | None = None,
    ) -> StructuredExtractionResult:
        po = PurchaseOrderData(
            supplier_name=self._extract_supplier_name(content),
            purchase_order_number=self._extract_po_number(content.text),
            order_date=self._extract_order_date(content.text),
            currency=self._extract_currency(content.text),
        )

        po.items = self._extract_vertical_net_amount_items(content)
        if not po.items:
            po.items = self._extract_table_items(content)
        if not po.items:
            po.items = self._extract_referenced_ukhsa_sparse_items(content)
        if not po.items:
            po.items = self._extract_text_items(content)
        if not po.items:
            po.items = self._extract_sparse_net_amount_items(content)
        if not po.items:
            po.items = self._extract_partial_text_items(content)

        self._extract_totals(content.text, po)
        self._reconcile_totals(po)

        return StructuredExtractionResult(
            engine=self.name,
            document_type="purchase_order",
            data=po.model_dump(),
            confidence=None,
        )

    @classmethod
    def _extract_vertical_net_amount_items(
        cls,
        content: DocumentContent,
    ) -> list[PurchaseOrderItem]:
        """Parse sparse UKRI-style Net Amount tables without inventing values.

        Real PDFs may preserve the whole header/row on one text line or emit every
        cell vertically. Quantity/UOM can legitimately be blank. Tax percentages
        are never interpreted as monetary values.
        """
        recovered: list[PurchaseOrderItem] = []

        for page in content.pages:
            lines = [line.strip() for line in page.text.splitlines() if line.strip()]
            normalized = [cls._normalize(line) for line in lines]

            header_start = next(
                (
                    index
                    for index, value in enumerate(normalized)
                    if "part number description" in value
                    and (
                        "net amount" in value
                        or "net amount" in " ".join(normalized[index:index + 10])
                    )
                ),
                None,
            )
            if header_start is None:
                continue

            # Skip header continuation lines until the first numbered item row.
            index = header_start + 1
            while index < len(lines):
                if re.match(r"^\d+(?:\s+|$)", lines[index]):
                    break
                if cls._normalize(lines[index]).startswith(("total", "grand total")):
                    break
                index += 1

            items: list[PurchaseOrderItem] = []
            while index < len(lines):
                if cls._normalize(lines[index]).startswith(("total", "grand total")):
                    break

                row_match = re.match(r"^(?P<line>\d+)(?:\s+(?P<rest>.*))?$", lines[index])
                if row_match is None:
                    index += 1
                    continue

                line_number = row_match.group("line")
                row_parts: list[str] = []
                if row_match.group("rest"):
                    row_parts.append(row_match.group("rest").strip())

                cursor = index + 1
                while cursor < len(lines):
                    candidate = lines[cursor]
                    if re.match(r"^\d+(?:\s+|$)", candidate):
                        break
                    if cls._normalize(candidate).startswith(("total", "grand total")):
                        break
                    row_parts.append(candidate)
                    cursor += 1

                cells: list[str] = []
                for part in row_parts:
                    cells.extend(
                        cell.strip()
                        for cell in re.split(r"[ \t]{2,}", part)
                        if cell.strip()
                    )

                description_parts: list[str] = []
                delivery_date: date | None = None
                unit: str | None = None
                numeric_values: list[Decimal] = []

                for cell in cells:
                    parsed_date = cls._parse_date(cell)
                    if parsed_date is not None:
                        delivery_date = parsed_date
                        continue

                    if "%" in cell:
                        continue

                    if cls._looks_like_unit(cell):
                        unit = cell
                        continue

                    if re.fullmatch(r"[-+]?\d[\d,]*(?:\.\d+)?", cell):
                        numeric = cls._parse_decimal(cell)
                        if numeric is not None:
                            numeric_values.append(numeric)
                        continue

                    if re.search(r"[A-Za-z]", cell):
                        description_parts.append(cell)

                description = " ".join(description_parts).strip()
                if description:
                    quantity: Decimal | None = None
                    unit_price: Decimal | None = None
                    line_total: Decimal | None = None

                    if len(numeric_values) >= 3:
                        quantity = numeric_values[0]
                        unit_price = numeric_values[-2]
                        line_total = numeric_values[-1]
                    elif len(numeric_values) == 2:
                        unit_price = numeric_values[0]
                        line_total = numeric_values[1]
                    elif len(numeric_values) == 1:
                        # One monetary-looking value is ambiguous in a sparse row.
                        # Preserve it only as line total when no unit price can be proven.
                        line_total = numeric_values[0]

                    items.append(
                        PurchaseOrderItem(
                            line_number=line_number,
                            description=" ".join(description.split()),
                            need_by_date=delivery_date,
                            quantity=quantity,
                            unit=unit,
                            unit_price=unit_price,
                            line_total=line_total,
                        )
                    )

                index = max(cursor, index + 1)

            recovered.extend(items)

        return cls._deduplicate_items(recovered)

    @classmethod
    def _extract_table_items(cls, content: DocumentContent) -> list[PurchaseOrderItem]:
        items: list[PurchaseOrderItem] = []

        for page in content.pages:
            for table in page.tables:
                parsed = cls._parse_table(table)
                if parsed:
                    items.extend(parsed)

        return cls._deduplicate_items(items)

    @classmethod
    def _parse_table(cls, table: TableContent) -> list[PurchaseOrderItem]:
        if not table.rows:
            return []

        header_index = None
        header: list[str] = []
        for index, row in enumerate(table.rows[:4]):
            normalized = [cls._normalize(cell) for cell in row]
            if (
                cls._find_index(normalized, "description", "order detail", "item", "part number description")
                is not None
                and cls._find_prefix(normalized, "total price", "net amount", "total") is not None
            ):
                header_index = index
                header = normalized
                break

        if header_index is None:
            return []

        description_index = cls._find_index(
            header,
            "description",
            "order detail",
            "item",
            "part number description",
        )
        quantity_index = cls._find_index(header, "quantity", "qty")
        unit_index = cls._find_index(header, "unit of measure", "uom", "unit", "units")
        unit_price_index = cls._find_prefix(header, "unit price", "price")
        line_total_index = cls._find_prefix(
            header,
            "total price",
            "net amount",
            "line total",
            "amount",
            "total",
        )
        reference_index = cls._find_index(
            header,
            "your reference",
            "supplier reference",
            "part number",
            "item code",
        )
        line_number_index = cls._find_index(header, "line", "line number")

        if description_index is None or line_total_index is None:
            return []

        items: list[PurchaseOrderItem] = []
        for row in table.rows[header_index + 1 :]:
            description = cls._cell(row, description_index)
            if not description:
                continue

            normalized_description = cls._normalize(description)
            if normalized_description in {"order total", "subtotal", "total", "grand total"}:
                continue

            quantity = (
                cls._parse_decimal(cls._cell(row, quantity_index))
                if quantity_index is not None
                else None
            )
            unit_price = (
                cls._parse_decimal(cls._cell(row, unit_price_index))
                if unit_price_index is not None
                else None
            )
            line_total = cls._parse_decimal(cls._cell(row, line_total_index))
            if line_total is None:
                continue

            clean_description, need_by_date = cls._strip_need_by_date(description)
            items.append(
                PurchaseOrderItem(
                    line_number=(
                        cls._cell(row, line_number_index)
                        if line_number_index is not None
                        else None
                    ),
                    supplier_reference=(
                        cls._cell(row, reference_index)
                        if reference_index is not None
                        else None
                    ),
                    description=clean_description,
                    need_by_date=need_by_date,
                    quantity=quantity,
                    unit=cls._cell(row, unit_index) if unit_index is not None else None,
                    unit_price=unit_price,
                    line_total=line_total,
                )
            )

        return items

    @classmethod
    def _extract_referenced_ukhsa_sparse_items(
        cls,
        content: DocumentContent,
    ) -> list[PurchaseOrderItem]:
        """Recover UKHSA rows anchored by a supplier reference.

        Some layout-preserved PDFs collapse the header into one line and place
        UOM/quantity at the far right, while price cells are blank. Only rows
        beginning with an explicit reference are treated as new items.
        """
        items: list[PurchaseOrderItem] = []

        for page in content.pages:
            lines = [line.rstrip() for line in page.text.splitlines() if line.strip()]
            header_index = next(
                (
                    index
                    for index, line in enumerate(lines)
                    if "description" in cls._normalize(line)
                    and "quantity" in cls._normalize(line)
                    and "unit price" in cls._normalize(line)
                    and "total price" in cls._normalize(line)
                ),
                None,
            )
            if header_index is None:
                continue

            index = header_index + 1
            while index < len(lines):
                line = lines[index].strip()
                normalized = cls._normalize(line)
                if cls._is_item_section_terminator(normalized):
                    break

                match = re.match(
                    r"^(?P<reference>[A-Z0-9][A-Z0-9._/-]{4,})\s{2,}(?P<rest>.+)$",
                    line,
                    flags=re.IGNORECASE,
                )
                if match is None:
                    index += 1
                    continue

                reference = match.group("reference")
                cells = [
                    cell.strip()
                    for cell in re.split(r"[ \t]{2,}", match.group("rest"))
                    if cell.strip()
                ]
                if not cells:
                    index += 1
                    continue

                quantity: Decimal | None = None
                unit: str | None = None
                if cls._parse_decimal(cells[-1]) is not None:
                    quantity = cls._parse_decimal(cells[-1])
                    cells = cells[:-1]
                if cells and cls._looks_like_unit(cells[-1]):
                    unit = cells[-1]
                    cells = cells[:-1]

                body = " ".join(cells).strip()
                if not body:
                    index += 1
                    continue

                description_parts = [body]
                need_by_date: date | None = None
                cursor = index + 1
                while cursor < len(lines):
                    candidate = lines[cursor].strip()
                    candidate_normalized = cls._normalize(candidate)
                    if cls._is_item_section_terminator(candidate_normalized):
                        break
                    if re.match(
                        r"^[A-Z0-9][A-Z0-9._/-]{4,}\s{2,}",
                        candidate,
                        flags=re.IGNORECASE,
                    ):
                        break

                    need_by = re.search(
                        r"\bneed\s+by\s+date\s+"
                        r"(?P<date>\d{1,2}-[A-Za-z]{3}-\d{2,4})\b",
                        candidate,
                        flags=re.IGNORECASE,
                    )
                    if need_by:
                        need_by_date = cls._parse_date(need_by.group("date"))
                        break

                    if re.search(r"[A-Za-z]", candidate):
                        description_parts.append(candidate)
                    cursor += 1

                description = " ".join(description_parts)
                description = " ".join(description.split())
                if description:
                    items.append(
                        PurchaseOrderItem(
                            supplier_reference=reference,
                            description=description,
                            need_by_date=need_by_date,
                            quantity=quantity,
                            unit=unit.strip() if unit else None,
                        )
                    )

                index = max(cursor + 1, index + 1)

        return cls._deduplicate_items(items)


    @classmethod
    def _extract_text_items(cls, content: DocumentContent) -> list[PurchaseOrderItem]:
        items: list[PurchaseOrderItem] = []

        for page in content.pages:
            lines = [line.strip() for line in page.text.splitlines() if line.strip()]
            in_item_section = False
            description_buffer: list[str] = []

            for line in lines:
                normalized = cls._normalize(line)

                if cls._looks_like_item_header(normalized):
                    in_item_section = True
                    description_buffer = []
                    continue

                if not in_item_section:
                    continue

                if cls._is_item_section_terminator(normalized):
                    in_item_section = False
                    description_buffer = []
                    continue

                parsed = cls._parse_text_item_line(line, description_buffer)
                if parsed is not None:
                    items.append(parsed)
                    description_buffer = []
                    continue

                if cls._is_description_line(line):
                    description_buffer.append(line)

        return cls._deduplicate_items(items)

    @classmethod
    def _extract_sparse_net_amount_items(
        cls,
        content: DocumentContent,
    ) -> list[PurchaseOrderItem]:
        items: list[PurchaseOrderItem] = []

        for page in content.pages:
            lines = [line.strip() for line in page.text.splitlines() if line.strip()]
            header_index = next(
                (
                    index
                    for index, line in enumerate(lines)
                    if "part number/description" in line.casefold()
                    and "net amount" in line.casefold()
                ),
                None,
            )
            if header_index is None:
                continue

            index = header_index + 1
            while index < len(lines):
                line = lines[index]
                normalized = cls._normalize(line)
                if cls._is_item_section_terminator(normalized):
                    break

                cells = [
                    cell.strip()
                    for cell in re.split(r"[ \t]{2,}", line)
                    if cell.strip()
                ]
                if not cells or not re.fullmatch(r"\d+", cells[0]):
                    index += 1
                    continue

                line_number = cells[0]
                date_index = next(
                    (i for i, cell in enumerate(cells) if cls._parse_date(cell) is not None),
                    None,
                )
                total = cls._parse_decimal(cells[-1])
                if date_index is None or total is None:
                    index += 1
                    continue

                unit = next(
                    (cell for cell in cells[date_index + 1 : -1] if cls._looks_like_unit(cell)),
                    None,
                )
                description_parts = cells[1:date_index]

                cursor = index + 1
                while cursor < len(lines):
                    candidate = lines[cursor]
                    candidate_normalized = cls._normalize(candidate)
                    if cls._is_item_section_terminator(candidate_normalized):
                        break
                    if re.match(r"^\d+\s{2,}", candidate):
                        break
                    if cls._parse_date(candidate) is not None:
                        break
                    if re.search(r"[A-Za-z]", candidate):
                        description_parts.append(candidate)
                        cursor += 1
                        continue
                    break

                description = " ".join(description_parts).strip()
                if description:
                    items.append(
                        PurchaseOrderItem(
                            line_number=line_number,
                            description=" ".join(description.split()),
                            quantity=None,
                            unit=unit,
                            unit_price=None,
                            line_total=total,
                        )
                    )
                index = max(cursor, index + 1)

        return cls._deduplicate_items(items)

    @classmethod
    def _extract_partial_text_items(
        cls,
        content: DocumentContent,
    ) -> list[PurchaseOrderItem]:
        items: list[PurchaseOrderItem] = []

        for page in content.pages:
            lines = [line.strip() for line in page.text.splitlines() if line.strip()]
            in_item_section = False
            pending_description: list[str] = []
            pending_unit: str | None = None

            for line in lines:
                normalized = cls._normalize(line)

                if cls._looks_like_item_header(normalized):
                    in_item_section = True
                    pending_description = []
                    pending_unit = None
                    continue

                if not in_item_section:
                    continue

                if cls._is_item_section_terminator(normalized):
                    in_item_section = False
                    pending_description = []
                    pending_unit = None
                    continue

                need_by = re.search(
                    r"\bneed\s+by\s+date\s+(?P<date>\d{1,2}-[A-Za-z]{3}-\d{2,4})\b",
                    line,
                    flags=re.IGNORECASE,
                )
                if need_by and pending_description:
                    description = " ".join(pending_description).strip()
                    if description:
                        items.append(
                            PurchaseOrderItem(
                                description=description,
                                need_by_date=cls._parse_date(need_by.group("date")),
                                unit=pending_unit,
                            )
                        )
                    pending_description = []
                    pending_unit = None
                    continue

                if not cls._is_description_line(line):
                    continue

                cells = [
                    cell.strip()
                    for cell in re.split(r"[ \t]{2,}", line)
                    if cell.strip()
                ]
                if not cells:
                    continue

                if cls._looks_like_unit(cells[-1]):
                    pending_unit = cells[-1]
                    cells = cells[:-1]

                if len(cells) >= 2 and re.fullmatch(
                    r"[A-Z0-9._/-]{2,}",
                    cells[0],
                    flags=re.IGNORECASE,
                ) and any(character.isdigit() for character in cells[0]):
                    cells = cells[1:]

                description = " ".join(cells).strip()
                if description:
                    pending_description.append(description)

        return cls._deduplicate_items(items)

    @classmethod
    def _parse_text_item_line(
        cls,
        line: str,
        description_buffer: list[str],
    ) -> PurchaseOrderItem | None:
        cells = [
            cell.strip()
            for cell in re.split(r"[ \t]{2,}", line)
            if cell.strip()
        ]

        # Layout-preserved PO rows commonly end in:
        # UOM | Quantity | Unit Price | Total Price
        if len(cells) >= 4:
            line_total = cls._parse_decimal(cells[-1])
            unit_price = cls._parse_decimal(cells[-2])
            quantity = cls._parse_decimal(cells[-3])
            unit = cells[-4] if cls._looks_like_unit(cells[-4]) else None

            if line_total is not None and unit_price is not None and quantity is not None:
                prefix_cells = cells[:-4] if unit else cells[:-3]
                description_parts = [*description_buffer, *prefix_cells]
                description = " ".join(part for part in description_parts if part)
                description, need_by_date = cls._strip_need_by_date(description)
                if description:
                    return PurchaseOrderItem(
                        description=description,
                        need_by_date=need_by_date,
                        quantity=quantity,
                        unit=unit,
                        unit_price=unit_price,
                        line_total=line_total,
                    )

        # Vertically emitted UKHSA/UKRI rows often have a single UOM/qty/price/total
        # line following a wrapped description.
        match = re.fullmatch(
            r"(?P<unit>[A-Za-z][A-Za-z0-9 /.-]{0,24})\s+"
            r"(?P<quantity>\d+(?:[.,]\d+)?)\s+"
            r"(?P<unit_price>[-+]?\d[\d,]*(?:\.\d+)?)\s+"
            r"(?P<line_total>[-+]?\d[\d,]*(?:\.\d+)?)",
            line,
        )
        if match and description_buffer:
            quantity = cls._parse_decimal(match.group("quantity"))
            unit_price = cls._parse_decimal(match.group("unit_price"))
            line_total = cls._parse_decimal(match.group("line_total"))
            if quantity is not None and unit_price is not None and line_total is not None:
                description, need_by_date = cls._strip_need_by_date(
                    " ".join(description_buffer)
                )
                if description:
                    return PurchaseOrderItem(
                        description=description,
                        need_by_date=need_by_date,
                        quantity=quantity,
                        unit=match.group("unit").strip(),
                        unit_price=unit_price,
                        line_total=line_total,
                    )

        return None

    @staticmethod
    def _looks_like_item_header(normalized: str) -> bool:
        return (
            "description" in normalized
            and ("quantity" in normalized or "qty" in normalized)
            and ("unit price" in normalized or "price" in normalized)
            and ("total price" in normalized or "net amount" in normalized or "total" in normalized)
        ) or (
            "part number description" in normalized
            and "quantity" in normalized
            and "unit price" in normalized
        )

    @staticmethod
    def _is_item_section_terminator(normalized: str) -> bool:
        return normalized.startswith(
            (
                "order total",
                "subtotal",
                "total excluding vat",
                "total vat",
                "order totalgbp",
                "order totalusd",
                "grand total",
                "notes",
                "conditions of contract",
            )
        )

    @staticmethod
    def _is_description_line(line: str) -> bool:
        normalized = DeterministicPurchaseOrderEngine._normalize(line)
        if not re.search(r"[A-Za-z]", line):
            return False
        exclusions = (
            "purchase order",
            "order number",
            "page number",
            "supplier name and address",
            "delivery address",
            "all invoices",
            "special instructions",
            "vat registration",
            "invoice to",
            "deliver to",
            "contact",
            "email",
            "tel",
            "fax",
        )
        return not any(normalized.startswith(prefix) for prefix in exclusions)

    @staticmethod
    def _looks_like_unit(value: str) -> bool:
        normalized = DeterministicPurchaseOrderEngine._normalize(value)
        if normalized in {
            "each",
            "ea",
            "unit",
            "units",
            "pack",
            "box",
            "lot",
            "day",
            "days",
            "hour",
            "hours",
            "service",
        }:
            return True
        return bool(re.fullmatch(r"pack \d+", normalized))

    @classmethod
    def _extract_po_number(cls, text: str) -> str | None:
        reserved = {"purchase", "order", "number", "date", "page", "supplier"}

        direct_patterns = (
            re.compile(
                r"\bpurchase[ \t]+order[ \t]+"
                r"(?P<value>[A-Z]{2,}[A-Z0-9/-]*\d[A-Z0-9/-]*)(?:\.\d+)?\b",
                re.IGNORECASE,
            ),
            re.compile(
                r"\bpurchase[ \t]+order[ \t]+(?:number|no\.?|#)"
                r"[ \t]*[:#]?[ \t]*(?P<value>[A-Z0-9][A-Z0-9._/-]{3,})\b",
                re.IGNORECASE,
            ),
            re.compile(
                r"\border[ \t]+(?:number|no\.?|#)"
                r"[ \t]*[:#]?[ \t]*(?P<value>[A-Z0-9][A-Z0-9._/-]{3,})\b",
                re.IGNORECASE,
            ),
            re.compile(
                r"^\s*order[ \t]+(?P<value>\d{6,}(?:[-/][A-Z0-9]+)?)\b",
                re.IGNORECASE | re.MULTILINE,
            ),
        )
        for pattern in direct_patterns:
            match = pattern.search(text)
            if match:
                candidate = match.group("value").strip()
                if cls._normalize(candidate) not in reserved:
                    return candidate

        lines = [line.rstrip() for line in text.splitlines() if line.strip()]
        for index, line in enumerate(lines):
            normalized = cls._normalize(line)
            cells = [
                cell.strip()
                for cell in re.split(r"[ \t]{2,}", line.strip())
                if cell.strip()
            ]

            if "purchase order number" in normalized:
                for cell in reversed(cells):
                    if "purchase order" in cls._normalize(cell):
                        continue
                    candidate = cls._po_number_candidate(cell, reserved)
                    if candidate:
                        return candidate

                for candidate_line in lines[index + 1 : index + 5]:
                    candidate = cls._po_number_candidate(candidate_line.strip(), reserved)
                    if candidate:
                        return candidate

            if normalized == "purchase order":
                for candidate_line in lines[index + 1 : index + 4]:
                    candidate = cls._po_number_candidate(candidate_line.strip(), reserved)
                    if candidate:
                        return candidate

        return None

    @classmethod
    def _po_number_candidate(
        cls,
        value: str,
        reserved: set[str],
    ) -> str | None:
        cells = [
            cell.strip()
            for cell in re.split(r"[ \t]{2,}", value)
            if cell.strip()
        ]
        candidates = cells if cells else [value.strip()]

        for cell in reversed(candidates):
            match = re.fullmatch(
                r"(?P<value>[A-Z0-9][A-Z0-9._/-]{3,})",
                cell,
                flags=re.IGNORECASE,
            )
            if match is None:
                match = re.search(
                    r"(?P<value>[A-Z0-9][A-Z0-9._/-]{2,}\d[A-Z0-9._/-]*)\s*$",
                    cell,
                    flags=re.IGNORECASE,
                )
            if match is None:
                continue
            candidate = match.group("value")
            normalized = cls._normalize(candidate)
            if normalized in reserved:
                continue
            if not any(character.isdigit() for character in candidate):
                continue
            if cls._parse_date(candidate) is not None:
                continue
            return candidate
        return None

    @classmethod
    def _extract_order_date(cls, text: str) -> date | None:
        patterns = (
            re.compile(
                r"\border\s+date\s*[:#]?\s*"
                r"(?P<value>\d{1,2}(?:-|/)[A-Za-z]{3}(?:-|/)\d{2,4})",
                re.IGNORECASE,
            ),
            re.compile(
                r"\bdate\s*:\s*"
                r"(?P<value>\d{1,2}(?:-|/)[A-Za-z]{3}(?:-|/)\d{2,4})",
                re.IGNORECASE,
            ),
        )
        for pattern in patterns:
            match = pattern.search(text)
            if match:
                parsed = cls._parse_date(match.group("value"))
                if parsed is not None:
                    return parsed

        lines = [line.strip() for line in text.splitlines() if line.strip()]
        for index, line in enumerate(lines):
            normalized = cls._normalize(line)
            if normalized in {"order date", "date"}:
                for candidate in lines[index + 1 : index + 3]:
                    parsed = cls._parse_date(candidate)
                    if parsed is not None:
                        return parsed

        return None

    @classmethod
    def _extract_supplier_name(cls, content: DocumentContent) -> str | None:
        lines = [line.rstrip() for line in content.text.splitlines() if line.strip()]
        header_lines = lines[:100]

        # Same-line forms such as Supplier: Help Scout PBC. Check these first
        # because PDF column spacing may otherwise split the value into a second cell.
        for line in header_lines:
            match = re.match(
                r"^\s*(?:supplier|to)[ \t]*:[ \t]*(?P<value>.+?)\s*$",
                line,
                flags=re.IGNORECASE,
            )
            if match:
                value = cls._clean_supplier_name(match.group("value"))
                if value:
                    return value

        # Multi-column supplier headers used by UKHSA/PHE templates.
        for index, line in enumerate(header_lines):
            cells = [
                cell.strip()
                for cell in re.split(r"[ \t]{2,}", line.strip())
                if cell.strip()
            ]
            normalized_cells = [cls._normalize(cell) for cell in cells]
            supplier_column = next(
                (
                    column
                    for column, value in enumerate(normalized_cells)
                    if value in {"supplier", "supplier name and address"}
                    or value.startswith("supplier name and address")
                ),
                None,
            )
            if supplier_column is None:
                continue

            for candidate_line in header_lines[index + 1 : index + 6]:
                candidate_cells = [
                    cell.strip()
                    for cell in re.split(r"[ \t]{2,}", candidate_line.strip())
                    if cell.strip()
                ]
                if not candidate_cells:
                    continue
                candidate = (
                    candidate_cells[supplier_column]
                    if supplier_column < len(candidate_cells)
                    else candidate_cells[0]
                )
                normalized = cls._normalize(candidate)
                if not re.search(r"[A-Za-z]", candidate):
                    continue
                if normalized.startswith(
                    ("delivery address", "all invoices", "invoice to", "deliver to")
                ):
                    break
                return cls._clean_supplier_name(candidate)

        # Standalone To: label followed by supplier on the next line.
        for index, line in enumerate(header_lines):
            if cls._normalize(line) != "to":
                continue
            for candidate_line in header_lines[index + 1 : index + 4]:
                candidate = cls._clean_supplier_name(candidate_line)
                if re.search(r"[A-Za-z]", candidate):
                    return candidate

        return None

    @staticmethod
    def _clean_supplier_name(value: str) -> str:
        value = re.split(r"[ \t]{2,}", value.strip(), maxsplit=1)[0]
        value = re.sub(r"#.*$", "", value).strip()
        return " ".join(value.split())

    @staticmethod
    def _extract_currency(text: str) -> str | None:
        matches = re.findall(r"\b(?:GBP|USD|EUR)\b", text, flags=re.IGNORECASE)
        if matches:
            return matches[-1].upper()
        if "£" in text:
            return "GBP"
        if "€" in text:
            return "EUR"
        return None

    @classmethod
    def _extract_totals(cls, text: str, po: PurchaseOrderData) -> None:
        lines = [line.strip() for line in text.splitlines() if line.strip()]

        for line in lines:
            normalized = cls._normalize(line)
            numbers = [
                value
                for value in (
                    cls._parse_decimal(token)
                    for token in re.findall(r"[-+]?\d[\d,]*(?:\.\d+)?", line)
                )
                if value is not None
            ]
            if not numbers:
                continue

            if "total excluding vat" in normalized:
                po.subtotal = numbers[-1]
            elif normalized.startswith("total vat"):
                po.tax_amount = numbers[-1]
            elif "order total" in normalized:
                po.total = numbers[-1]
            elif normalized.startswith("grand total"):
                po.total = numbers[-1]

        # Vertically emitted summaries may put the Grand Total value on the next line.
        if po.total is None:
            for index, line in enumerate(lines[:-1]):
                if cls._normalize(line) != "grand total":
                    continue
                next_value = cls._parse_decimal(lines[index + 1])
                if next_value is not None:
                    po.total = next_value
                    break

        # Some PDF layouts emit the three summary labels in one visual block.
        # Only use this fallback for values that were not already extracted line-by-line.
        if po.subtotal is None or po.tax_amount is None or po.total is None:
            combined = re.search(
                r"total\s*\(\s*excluding\s+vat\s*\).*?"
                r"(?P<subtotal>\d[\d,]*(?:\.\d+)?)"
                r".*?total\s+vat.*?(?P<tax>\d[\d,]*(?:\.\d+)?)"
                r".*?order\s+total\s*(?:gbp|usd|eur)?\s*"
                r"(?P<total>\d[\d,]*(?:\.\d+)?)",
                text,
                flags=re.IGNORECASE | re.DOTALL,
            )
            if combined:
                po.subtotal = po.subtotal or cls._parse_decimal(combined.group("subtotal"))
                po.tax_amount = po.tax_amount or cls._parse_decimal(combined.group("tax"))
                po.total = po.total or cls._parse_decimal(combined.group("total"))

    @classmethod
    def _reconcile_totals(cls, po: PurchaseOrderData) -> None:
        complete_line_totals = [
            item.line_total for item in po.items if item.line_total is not None
        ]
        if po.items and len(complete_line_totals) == len(po.items):
            item_sum = sum(complete_line_totals, Decimal("0"))
            if po.subtotal is None and po.total is not None and po.tax_amount is None:
                if cls._money(item_sum) == cls._money(po.total):
                    po.subtotal = item_sum
            if po.total is None and po.subtotal is not None and po.tax_amount is None:
                po.total = po.subtotal

    @classmethod
    def _strip_need_by_date(cls, description: str) -> tuple[str, date | None]:
        match = re.search(
            r"\bneed\s+by\s+date\s+(?P<date>\d{1,2}-[A-Za-z]{3}-\d{2,4})\b",
            description,
            flags=re.IGNORECASE,
        )
        need_by = cls._parse_date(match.group("date")) if match else None
        if match:
            description = (description[: match.start()] + description[match.end() :]).strip()

        description = re.sub(r"^your\s+reference\s+", "", description, flags=re.IGNORECASE)
        return " ".join(description.split()), need_by

    @staticmethod
    def _parse_date(value: str | None) -> date | None:
        if not value:
            return None

        candidate = " ".join(value.strip().split())
        for fmt in (
            "%d-%b-%Y",
            "%d-%b-%y",
            "%Y-%m-%d",
            "%d/%m/%Y",
            "%d/%m/%y",
            "%d/%b/%Y",
            "%d/%b/%y",
            "%d.%m.%Y",
        ):
            try:
                return datetime.strptime(candidate, fmt).date()
            except ValueError:
                continue
        return None

    @staticmethod
    def _parse_decimal(value: str | None) -> Decimal | None:
        if not value:
            return None

        normalized = re.sub(r"[^\d,.-]", "", value)
        if not normalized:
            return None

        if "," in normalized and "." in normalized:
            normalized = normalized.replace(",", "")
        elif "," in normalized:
            tail = normalized.rsplit(",", 1)[-1]
            normalized = (
                normalized.replace(",", ".")
                if len(tail) == 2
                else normalized.replace(",", "")
            )

        try:
            return Decimal(normalized)
        except InvalidOperation:
            return None

    @staticmethod
    def _money(value: Decimal) -> Decimal:
        return value.quantize(Decimal("0.01"))

    @staticmethod
    def _normalize(value: str | None) -> str:
        if not value:
            return ""
        return " ".join(re.sub(r"[^a-z0-9]+", " ", value.casefold()).split())

    @classmethod
    def _find_index(cls, headers: list[str], *aliases: str) -> int | None:
        for alias in aliases:
            normalized_alias = cls._normalize(alias)
            if normalized_alias in headers:
                return headers.index(normalized_alias)
        return None

    @classmethod
    def _find_prefix(cls, headers: list[str], *prefixes: str) -> int | None:
        for index, header in enumerate(headers):
            if any(header.startswith(cls._normalize(prefix)) for prefix in prefixes):
                return index
        return None

    @staticmethod
    def _cell(row: list[str | None], index: int | None) -> str:
        if index is None or index >= len(row):
            return ""
        return row[index].strip() if row[index] else ""

    @staticmethod
    def _deduplicate_items(items: list[PurchaseOrderItem]) -> list[PurchaseOrderItem]:
        unique: list[PurchaseOrderItem] = []
        seen: set[tuple[str, Decimal | None, Decimal | None, Decimal | None]] = set()
        for item in items:
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
