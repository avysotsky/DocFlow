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

        po.items = self._extract_table_items(content)
        if not po.items:
            po.items = self._extract_text_items(content)

        self._extract_totals(content.text, po)
        self._reconcile_totals(po)

        return StructuredExtractionResult(
            engine=self.name,
            document_type="purchase_order",
            data=po.model_dump(),
            confidence=None,
        )

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
        return normalized in {
            "each",
            "ea",
            "unit",
            "units",
            "pack",
            "pack 10",
            "box",
            "lot",
            "day",
            "days",
            "hour",
            "hours",
            "service",
        }

    @classmethod
    def _extract_po_number(cls, text: str) -> str | None:
        direct_patterns = (
            re.compile(
                r"\bpurchase\s+order\s+(?:number|no\.?|#)\s*[:#]?\s*"
                r"(?P<value>[A-Z0-9][A-Z0-9._/-]{3,})\b",
                re.IGNORECASE,
            ),
            re.compile(
                r"\border\s+(?:number|no\.?|#)\s*[:#]?\s*"
                r"(?P<value>[A-Z0-9][A-Z0-9._/-]{3,})\b",
                re.IGNORECASE,
            ),
            re.compile(
                r"\bpurchase\s+order\s+(?P<value>\d{6,})(?:[,/]\d+)?\b",
                re.IGNORECASE,
            ),
        )
        for pattern in direct_patterns:
            match = pattern.search(text)
            if match:
                return match.group("value").strip()

        lines = [line.strip() for line in text.splitlines() if line.strip()]
        for index, line in enumerate(lines):
            normalized = cls._normalize(line)
            if normalized not in {"purchase order number", "order number"}:
                continue

            for candidate in lines[index + 1 : index + 4]:
                candidate_normalized = cls._normalize(candidate)
                if "purchase order" in candidate_normalized or "order date" in candidate_normalized:
                    continue
                match = re.fullmatch(r"[A-Z0-9][A-Z0-9._/-]{3,}", candidate, flags=re.IGNORECASE)
                if match:
                    return candidate

        return None

    @classmethod
    def _extract_order_date(cls, text: str) -> date | None:
        patterns = (
            re.compile(r"\border\s+date\s*[:#]?\s*(?P<value>\d{1,2}-[A-Za-z]{3}-\d{2,4})", re.IGNORECASE),
            re.compile(r"\bdate\s*:\s*(?P<value>\d{1,2}-[A-Za-z]{3}-\d{2,4})", re.IGNORECASE),
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
        lines = [line.strip() for line in content.text.splitlines() if line.strip()]

        labels = (
            "supplier name and address",
            "supplier",
            "to",
        )
        for index, line in enumerate(lines):
            normalized = cls._normalize(line)

            same_line = re.match(
                r"^(?:supplier|to)\s*:\s*(?P<value>.+)$",
                line,
                flags=re.IGNORECASE,
            )
            if same_line:
                value = same_line.group("value").strip()
                if value:
                    return cls._clean_supplier_name(value)

            if normalized not in labels:
                continue

            for candidate in lines[index + 1 : index + 5]:
                candidate_normalized = cls._normalize(candidate)
                if not candidate_normalized:
                    continue
                if any(
                    candidate_normalized.startswith(prefix)
                    for prefix in (
                        "delivery address",
                        "all invoices",
                        "invoice to",
                        "deliver to",
                    )
                ):
                    break
                if re.search(r"[A-Za-z]", candidate):
                    return cls._clean_supplier_name(candidate)

        return None

    @staticmethod
    def _clean_supplier_name(value: str) -> str:
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

        # Some PDF layouts place the three labels in one text block and values in order.
        normalized_text = cls._normalize(text)
        combined = re.search(
            r"total excluding vat.*?total vat.*?order total\s*(?:gbp|usd|eur)?\s*"
            r"(?P<subtotal>\d[\d,.]*)\s+"
            r"(?P<tax>\d[\d,.]*)\s+"
            r"(?P<total>\d[\d,.]*)",
            normalized_text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if combined:
            po.subtotal = cls._parse_decimal(combined.group("subtotal"))
            po.tax_amount = cls._parse_decimal(combined.group("tax"))
            po.total = cls._parse_decimal(combined.group("total"))

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
