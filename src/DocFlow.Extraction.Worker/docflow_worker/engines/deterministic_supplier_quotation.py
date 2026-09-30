import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

from docflow_worker.engines.base import StructuredExtractionEngine
from docflow_worker.models import (
    BoundingBox,
    DocumentContent,
    StructuredExtractionResult,
    TableContent,
)
from docflow_worker.supplier_quotation_models import (
    SupplierQuotationData,
    SupplierQuotationItem,
)


class DeterministicSupplierQuotationEngine(StructuredExtractionEngine):
    """Deterministic parser for supplier quotations with tabular or borderless layout."""

    @property
    def name(self) -> str:
        return "deterministic_supplier_quotation_v1"

    async def extract(
        self,
        content: DocumentContent,
        *,
        document_name: str | None = None,
    ) -> StructuredExtractionResult:
        metadata = self._extract_metadata(content)
        item_table = self._find_item_table(content)

        quotation = SupplierQuotationData(
            supplier_name=self._extract_supplier_name(content),
            quotation_number=self._metadata_value(
                metadata,
                "quotation no",
                "quotation number",
                "quote no",
                "quote number",
            ),
            quotation_date=self._parse_date(
                self._metadata_value(metadata, "quotation date", "quote date")
            ),
            valid_until=self._parse_date(
                self._metadata_value(metadata, "valid until", "valid through")
            ),
            currency=self._metadata_value(metadata, "currency"),
            customer_reference=self._metadata_value(
                metadata,
                "customer ref",
                "customer reference",
            ),
            incoterms=self._metadata_value(metadata, "incoterms"),
            items=self._extract_items(item_table) if item_table else [],
        )

        self._extract_totals_and_terms(content, quotation)

        return StructuredExtractionResult(
            engine=self.name,
            document_type="supplier_quotation",
            data=quotation.model_dump(),
            confidence=None,
        )

    @classmethod
    def _extract_metadata(cls, content: DocumentContent) -> dict[str, str]:
        metadata: dict[str, str] = {}

        for page in content.pages:
            for table in page.tables:
                if not cls._looks_like_metadata_table(table):
                    continue

                cls._collect_metadata_rows(metadata, table.rows)

            # Borderless digital PDFs often preserve visual columns as runs of spaces
            # even when no vector lines exist for table detection. Use this only as a
            # fallback source and never overwrite metadata already extracted from a table.
            borderless_rows = cls._layout_rows(page.text)
            borderless_metadata: dict[str, str] = {}
            cls._collect_metadata_rows(borderless_metadata, borderless_rows)
            for key, value in borderless_metadata.items():
                metadata.setdefault(key, value)

        return metadata

    @classmethod
    def _collect_metadata_rows(
        cls,
        target: dict[str, str],
        rows: list[list[str | None]],
    ) -> None:
        for row in rows:
            for index in range(0, len(row) - 1, 2):
                key = cls._normalize_header(row[index])
                value = cls._clean_cell(row[index + 1])
                if key and value:
                    target[key] = value

    @classmethod
    def _looks_like_metadata_table(cls, table: TableContent) -> bool:
        if not table.rows:
            return False

        headers = {cls._normalize_header(cell) for cell in table.rows[0]}
        quotation_labels = {
            "quotation no",
            "quotation number",
            "quote no",
            "quote number",
        }
        return bool(headers & quotation_labels) and "currency" in headers

    @classmethod
    def _find_item_table(cls, content: DocumentContent) -> TableContent | None:
        for page in content.pages:
            for table in page.tables:
                if cls._looks_like_item_table(table.rows):
                    return table

        # No line-based table was found. Reconstruct the item table from layout-preserved
        # text columns. This keeps the semantic parser deterministic while supporting
        # digital quotations whose table has no drawn borders.
        for page in content.pages:
            rows = cls._layout_rows(page.text)
            for index, row in enumerate(rows):
                if not cls._looks_like_item_table([row]):
                    continue

                item_rows: list[list[str | None]] = [row]
                for candidate in rows[index + 1 :]:
                    if cls._is_item_table_terminator(candidate):
                        break
                    if len(candidate) < 3:
                        break
                    item_rows.append(candidate)

                if len(item_rows) > 1:
                    return TableContent(
                        bbox=BoundingBox(
                            x0=0,
                            y0=0,
                            x1=page.width,
                            y1=page.height,
                        ),
                        rows=item_rows,
                    )

        return None

    @classmethod
    def _looks_like_item_table(cls, rows: list[list[str | None]]) -> bool:
        if not rows:
            return False

        headers = [cls._normalize_header(cell) for cell in rows[0]]
        return (
            cls._find_header_index(
                headers,
                "sku",
                "item code",
                "product code",
                "part number",
                "part no",
            )
            is not None
            and cls._find_header_index(
                headers,
                "description",
                "item description",
                "product description",
                "item",
            )
            is not None
            and cls._find_header_index(headers, "qty", "quantity") is not None
        )

    @classmethod
    def _is_item_table_terminator(cls, row: list[str | None]) -> bool:
        if not row:
            return True

        first = cls._normalize_header(row[0])
        return first in {
            "subtotal",
            "vat",
            "total",
            "payment terms",
            "delivery",
            "warranty",
            "notes",
            "prepared by",
            "quote status",
        }

    @staticmethod
    def _layout_rows(text: str) -> list[list[str | None]]:
        rows: list[list[str | None]] = []

        for line in text.splitlines():
            clean_line = line.strip()
            if not clean_line:
                continue

            cells = [
                cell.strip()
                for cell in re.split(r"[ \t]{2,}", clean_line)
                if cell.strip()
            ]
            if len(cells) >= 2:
                rows.append(cells)

        return rows

    @classmethod
    def _extract_items(cls, table: TableContent) -> list[SupplierQuotationItem]:
        if not table.rows:
            return []

        headers = [cls._normalize_header(cell) for cell in table.rows[0]]

        sku_index = cls._find_header_index(
            headers,
            "sku",
            "item code",
            "product code",
            "part number",
            "part no",
        )
        description_index = cls._find_header_index(
            headers,
            "description",
            "item description",
            "product description",
            "item",
        )
        quantity_index = cls._find_header_index(headers, "qty", "quantity")
        unit_index = cls._find_header_index(headers, "unit", "uom")
        unit_price_index = cls._find_header_prefix(headers, "unit price", "price")
        lead_time_index = cls._find_header_prefix(headers, "lead time")
        line_total_index = cls._find_header_prefix(
            headers,
            "line total",
            "total price",
            "amount",
        )

        if sku_index is None or description_index is None or quantity_index is None:
            return []

        items: list[SupplierQuotationItem] = []

        for row in table.rows[1:]:
            sku = cls._row_value(row, sku_index)
            description = cls._row_value(row, description_index)
            quantity = cls._parse_decimal(cls._row_value(row, quantity_index))

            if not sku or not description or quantity is None:
                continue

            lead_time_days = None
            if lead_time_index is not None:
                lead_time = cls._parse_decimal(cls._row_value(row, lead_time_index))
                if lead_time is not None and lead_time == lead_time.to_integral_value():
                    lead_time_days = int(lead_time)

            items.append(
                SupplierQuotationItem(
                    sku=sku,
                    description=description,
                    quantity=quantity,
                    unit=(
                        cls._row_value(row, unit_index)
                        if unit_index is not None
                        else None
                    ),
                    unit_price=(
                        cls._parse_decimal(cls._row_value(row, unit_price_index))
                        if unit_price_index is not None
                        else None
                    ),
                    lead_time_days=lead_time_days,
                    line_total=(
                        cls._parse_decimal(cls._row_value(row, line_total_index))
                        if line_total_index is not None
                        else None
                    ),
                )
            )

        return items

    @classmethod
    def _extract_supplier_name(cls, content: DocumentContent) -> str | None:
        for page in content.pages:
            blocks = sorted(
                page.blocks,
                key=lambda block: (block.bbox.y0, block.bbox.x0),
            )

            for block in blocks:
                text = block.text.strip()
                lower_text = text.lower()
                lines = [line.strip() for line in text.splitlines() if line.strip()]

                if "quotation" in lower_text:
                    continue

                if len(lines) > 1 and ("@" in text or "vat" in lower_text):
                    return lines[0]

        return None

    @classmethod
    def _extract_totals_and_terms(
        cls,
        content: DocumentContent,
        quotation: SupplierQuotationData,
    ) -> None:
        number_pattern = re.compile(r"[-+]?\d[\d\s.,]*")

        for page in content.pages:
            for block in page.blocks:
                text = block.text.strip()
                lower_text = text.lower()

                numbers = [
                    value
                    for value in (
                        cls._parse_decimal(match.group())
                        for match in number_pattern.finditer(text)
                    )
                    if value is not None
                ]

                if lower_text.startswith("subtotal") and numbers:
                    quotation.subtotal = numbers[-1]
                elif lower_text.startswith("vat") and numbers:
                    if "%" in text and len(numbers) >= 2:
                        quotation.vat_rate = numbers[0]
                    quotation.vat_amount = numbers[-1]
                elif lower_text.startswith("total") and numbers:
                    quotation.total = numbers[-1]
                elif lower_text.startswith("payment terms:"):
                    quotation.payment_terms = text.split(":", 1)[1].strip()
                elif lower_text.startswith("delivery:"):
                    quotation.delivery = text.split(":", 1)[1].strip()
                elif lower_text.startswith("warranty:"):
                    quotation.warranty = text.split(":", 1)[1].strip()
                elif lower_text.startswith("notes:"):
                    quotation.notes = text.split(":", 1)[1].strip()

                for line in text.splitlines():
                    clean_line = line.strip()
                    lower_line = clean_line.lower()

                    if lower_line.startswith("prepared by:"):
                        quotation.prepared_by = clean_line.split(":", 1)[1].strip()
                    elif lower_line.startswith("quote status:"):
                        quotation.quote_status = clean_line.split(":", 1)[1].strip()

    @staticmethod
    def _metadata_value(metadata: dict[str, str], *keys: str) -> str | None:
        for key in keys:
            value = metadata.get(key)
            if value:
                return value
        return None

    @staticmethod
    def _normalize_header(value: str | None) -> str:
        if not value:
            return ""

        normalized = value.replace("\n", " ")
        normalized = re.sub(r"\([^)]*\)", "", normalized)
        normalized = re.sub(r"[^a-z0-9]+", " ", normalized.lower())
        return " ".join(normalized.split())

    @staticmethod
    def _clean_cell(value: str | None) -> str:
        return value.strip() if value else ""

    @staticmethod
    def _find_header_index(headers: list[str], *aliases: str) -> int | None:
        for alias in aliases:
            if alias in headers:
                return headers.index(alias)
        return None

    @staticmethod
    def _find_header_prefix(headers: list[str], *prefixes: str) -> int | None:
        for index, header in enumerate(headers):
            if any(header.startswith(prefix) for prefix in prefixes):
                return index
        return None

    @classmethod
    def _row_value(cls, row: list[str | None], index: int) -> str:
        if index >= len(row):
            return ""
        return cls._clean_cell(row[index])

    @staticmethod
    def _parse_decimal(value: str | None) -> Decimal | None:
        if not value:
            return None

        normalized = re.sub(r"[^\d,.\-+]", "", value)
        if not normalized:
            return None

        if "," in normalized and "." in normalized:
            normalized = normalized.replace(",", "")
        elif "," in normalized:
            normalized = normalized.replace(",", ".")

        try:
            return Decimal(normalized)
        except InvalidOperation:
            return None

    @staticmethod
    def _parse_date(value: str | None):
        if not value:
            return None

        for date_format in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y"):
            try:
                return datetime.strptime(value.strip(), date_format).date()
            except ValueError:
                continue

        return None
