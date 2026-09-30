import re
from decimal import Decimal, InvalidOperation

from docflow_worker.deterministic_text_fields import (
    extract_labeled_identifier,
    extract_totals_from_text,
    infer_currency,
)
from docflow_worker.engines.deterministic_supplier_quotation import (
    DeterministicSupplierQuotationEngine,
)
from docflow_worker.invoice_identifiers import normalize_invoice_identifier
from docflow_worker.invoice_text_fallbacks import (
    extract_ocr_invoice_identifier,
    extract_preferred_invoice_total,
    infer_labeled_currency,
)
from docflow_worker.models import (
    BoundingBox,
    DocumentContent,
    StructuredExtractionResult,
    TableContent,
)
from docflow_worker.supplier_invoice_models import (
    SupplierInvoiceData,
    SupplierInvoiceItem,
)


class DeterministicSupplierInvoiceEngine(DeterministicSupplierQuotationEngine):
    """Deterministic parser for digital and OCR supplier invoices."""

    @property
    def name(self) -> str:
        return "deterministic_supplier_invoice_v1"

    async def extract(
        self,
        content: DocumentContent,
        *,
        document_name: str | None = None,
    ) -> StructuredExtractionResult:
        metadata = self._extract_invoice_metadata(content)
        item_table = self._find_invoice_item_table(content)
        invoice_items = self._extract_invoice_items(item_table) if item_table else []

        invoice_number = (
            extract_labeled_identifier(
                content,
                ("invoice number", "invoice no.", "invoice no"),
            )
            or extract_ocr_invoice_identifier(content)
            or self._metadata_value(
                metadata,
                "invoice no",
                "invoice number",
            )
        )

        invoice = SupplierInvoiceData(
            supplier_name=self._extract_supplier_name(content),
            invoice_number=normalize_invoice_identifier(invoice_number),
            invoice_date=self._parse_date(
                self._metadata_value(metadata, "invoice date")
            ),
            due_date=self._parse_date(
                self._metadata_value(metadata, "due date", "payment due")
            ),
            currency=(
                self._metadata_value(metadata, "currency")
                or infer_labeled_currency(content)
                or infer_currency(content)
            ),
            customer_reference=self._metadata_value(
                metadata,
                "customer ref",
                "customer reference",
            ),
            purchase_order_number=self._metadata_value(
                metadata,
                "po no",
                "po number",
                "purchase order",
                "purchase order number",
            ),
            payment_terms=self._metadata_value(metadata, "payment terms"),
            items=invoice_items,
        )

        self._extract_invoice_totals_and_terms(content, invoice)

        # OCR can preserve the arithmetic columns while losing the table header or
        # decimal separators. If the normal table parser found no items, recover only
        # an item set whose line totals reconcile exactly to the extracted subtotal.
        # This keeps the fallback deterministic and prevents unrelated OCR numbers from
        # being accepted as invoice lines.
        if not invoice.items and invoice.subtotal is not None:
            invoice.items = self._extract_reconciled_ocr_items(
                content,
                invoice.subtotal,
            )

        return StructuredExtractionResult(
            engine=self.name,
            document_type="supplier_invoice",
            data=invoice.model_dump(),
            confidence=None,
        )

    @classmethod
    def _find_invoice_item_table(cls, content: DocumentContent) -> TableContent | None:
        for page in content.pages:
            for table in page.tables:
                if cls._looks_like_invoice_item_table(table.rows):
                    return table

        # Supplier invoices frequently omit SKU/item-code columns. Reconstruct a
        # borderless invoice table from layout-preserved text and accept the common
        # Description + Quantity + Unit Price + Amount shape.
        for page in content.pages:
            rows = cls._layout_rows(page.text)
            for index, row in enumerate(rows):
                if not cls._looks_like_invoice_item_table([row]):
                    continue

                item_rows: list[list[str | None]] = [row]
                for candidate in rows[index + 1 :]:
                    if cls._is_item_table_terminator(candidate):
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
    def _looks_like_invoice_item_table(cls, rows: list[list[str | None]]) -> bool:
        if not rows:
            return False

        headers = [cls._normalize_header(cell) for cell in rows[0]]
        return (
            cls._find_header_index(
                headers,
                "description",
                "item description",
                "product description",
                "item",
            )
            is not None
            and cls._find_header_index(headers, "qty", "quantity") is not None
            and cls._find_header_prefix(headers, "unit price", "price") is not None
            and cls._find_header_prefix(
                headers,
                "line total",
                "total price",
                "amount",
            )
            is not None
        )

    @classmethod
    def _extract_invoice_items(cls, table: TableContent) -> list[SupplierInvoiceItem]:
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
        line_total_index = cls._find_header_prefix(
            headers,
            "line total",
            "total price",
            "amount",
        )

        if description_index is None or quantity_index is None:
            return []

        items: list[SupplierInvoiceItem] = []

        for row in table.rows[1:]:
            item = None

            # Native tables normally preserve the same column count as their header.
            # OCR/layout text can split a long description into several cells and shift
            # every numeric column to the right. In that case parse the stable numeric
            # tail from right to left instead of trusting header indexes.
            if len(row) == len(headers):
                description = cls._row_value(row, description_index)
                quantity = cls._parse_decimal(cls._row_value(row, quantity_index))
                if description and quantity is not None:
                    item = SupplierInvoiceItem(
                        sku=(
                            cls._row_value(row, sku_index)
                            if sku_index is not None
                            else None
                        ),
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
                        line_total=(
                            cls._parse_decimal(cls._row_value(row, line_total_index))
                            if line_total_index is not None
                            else None
                        ),
                    )

            if item is None:
                item = cls._extract_right_aligned_invoice_item(row)

            if item is not None:
                items.append(item)

        return items

    @classmethod
    def _extract_right_aligned_invoice_item(
        cls,
        row: list[str | None],
    ) -> SupplierInvoiceItem | None:
        cells = [cls._clean_cell(value) for value in row]
        if len(cells) < 4:
            return None

        percent_index = next(
            (index for index in range(len(cells) - 1, -1, -1) if "%" in cells[index]),
            None,
        )
        if percent_index is None:
            return None

        line_total_index = cls._previous_decimal_index(cells, len(cells) - 1, percent_index)
        unit_price_index = cls._previous_decimal_index(cells, percent_index - 1, -1)
        if line_total_index is None or unit_price_index is None:
            return None

        quantity_index = cls._previous_decimal_index(cells, unit_price_index - 1, -1)
        if quantity_index is None or quantity_index <= 0:
            return None

        quantity = cls._parse_decimal(cells[quantity_index])
        unit_price = cls._parse_decimal(cells[unit_price_index])
        line_total = cls._parse_decimal(cells[line_total_index])
        if quantity is None or unit_price is None or line_total is None:
            return None

        description = " ".join(
            value
            for value in cells[:quantity_index]
            if value and value not in {"|"}
        ).strip()
        if not description or not re.search(r"[A-Za-z]", description):
            return None

        return SupplierInvoiceItem(
            sku=None,
            description=description,
            quantity=quantity,
            unit_price=unit_price,
            line_total=line_total,
        )

    @classmethod
    def _previous_decimal_index(
        cls,
        cells: list[str],
        start: int,
        stop_exclusive: int,
    ) -> int | None:
        for index in range(start, stop_exclusive, -1):
            if cls._parse_decimal(cells[index]) is not None:
                return index
        return None

    @classmethod
    def _extract_reconciled_ocr_items(
        cls,
        content: DocumentContent,
        subtotal: Decimal,
    ) -> list[SupplierInvoiceItem]:
        subtotal_cents = cls._money_to_cents(subtotal)
        if subtotal_cents <= 0:
            return []

        for page in content.pages:
            rows = cls._layout_rows(page.text)
            subtotal_index = next(
                (
                    index
                    for index, row in enumerate(rows)
                    if row and cls._normalize_header(row[0]).startswith("subtotal")
                ),
                None,
            )
            if subtotal_index is None:
                continue

            candidate_rows = rows[max(0, subtotal_index - 12) : subtotal_index]
            alternatives: list[list[SupplierInvoiceItem]] = []
            for row in candidate_rows:
                row_alternatives = cls._ocr_item_candidates(row)
                if row_alternatives:
                    alternatives.append(row_alternatives)

            if not alternatives or len(alternatives) > 8:
                continue

            # Dynamic programming over cents chooses at most one interpretation from
            # each OCR row. Only an exact subtotal reconciliation is accepted.
            states: dict[int, list[SupplierInvoiceItem]] = {0: []}
            for row_alternatives in alternatives:
                next_states = dict(states)
                for current_sum, current_items in states.items():
                    for item in row_alternatives:
                        if item.line_total is None:
                            continue
                        line_cents = cls._money_to_cents(item.line_total)
                        new_sum = current_sum + line_cents
                        if new_sum <= subtotal_cents and new_sum not in next_states:
                            next_states[new_sum] = [*current_items, item]
                states = next_states

            reconciled = states.get(subtotal_cents)
            if reconciled:
                return reconciled

        return []

    @classmethod
    def _ocr_item_candidates(
        cls,
        row: list[str | None],
    ) -> list[SupplierInvoiceItem]:
        cells = [cls._clean_cell(value) for value in row]
        if not cells:
            return []

        joined = " ".join(cells)
        normalized = cls._normalize_header(joined)
        excluded_labels = (
            "invoice number",
            "invoice no",
            "invoice date",
            "due date",
            "vat number",
            "tax office",
            "phone",
            "email",
            "currency",
            "iban",
            "bank",
        )
        if any(label in normalized for label in excluded_labels):
            return []
        if not re.search(r"[A-Za-z]", cells[0]):
            return []

        numeric_cells: list[tuple[int, list[Decimal]]] = []
        for index, value in enumerate(cells[1:], start=1):
            if "%" in value:
                continue
            candidates = cls._ocr_decimal_candidates(value)
            if candidates:
                numeric_cells.append((index, candidates))

        if len(numeric_cells) < 2:
            return []

        results: list[SupplierInvoiceItem] = []

        if len(numeric_cells) >= 3:
            quantity_index, quantity_values = numeric_cells[-3]
            _, unit_price_values = numeric_cells[-2]
            _, line_total_values = numeric_cells[-1]
            description = " ".join(cells[:quantity_index]).strip()

            for quantity in quantity_values:
                # Quantity is not money; do not accept OCR scale alternatives here.
                if quantity <= 0 or quantity != quantity.to_integral_value():
                    continue
                for unit_price in unit_price_values:
                    for line_total in line_total_values:
                        if cls._money_close(quantity * unit_price, line_total):
                            results.append(
                                SupplierInvoiceItem(
                                    sku=None,
                                    description=description,
                                    quantity=quantity,
                                    unit_price=unit_price,
                                    line_total=line_total,
                                )
                            )
        else:
            first_index, unit_price_values = numeric_cells[-2]
            _, line_total_values = numeric_cells[-1]
            description = " ".join(cells[:first_index]).strip()

            # Some OCR layouts lose the quantity column entirely. Infer quantity only
            # when unit price and line total imply a positive integral count.
            for unit_price in unit_price_values:
                if unit_price <= 0:
                    continue
                for line_total in line_total_values:
                    ratio = line_total / unit_price
                    if (
                        ratio > 0
                        and ratio <= 1000
                        and ratio == ratio.to_integral_value()
                    ):
                        results.append(
                            SupplierInvoiceItem(
                                sku=None,
                                description=description,
                                quantity=ratio,
                                unit_price=unit_price,
                                line_total=line_total,
                            )
                        )

        # Preserve deterministic order while removing duplicate arithmetic candidates.
        unique: dict[tuple[Decimal, Decimal | None, Decimal | None], SupplierInvoiceItem] = {}
        for item in results:
            key = (item.quantity, item.unit_price, item.line_total)
            unique.setdefault(key, item)
        return list(unique.values())

    @staticmethod
    def _ocr_decimal_candidates(value: str) -> list[Decimal]:
        compact = re.sub(r"[^0-9,.-]", "", value.replace(" ", ""))
        if not compact or not any(character.isdigit() for character in compact):
            return []

        candidates: list[Decimal] = []

        def add(text: str) -> None:
            try:
                number = Decimal(text)
            except InvalidOperation:
                return
            if number >= 0 and number not in candidates:
                candidates.append(number)

        if "," in compact and "." in compact:
            # The last separator is the decimal mark; earlier separators are grouping.
            if compact.rfind(",") > compact.rfind("."):
                add(compact.replace(".", "").replace(",", "."))
            else:
                add(compact.replace(",", ""))
        elif "," in compact:
            tail = compact.rsplit(",", 1)[1]
            if len(tail) == 2:
                add(compact.replace(",", "."))
            else:
                add(compact.replace(",", ""))
        elif "." in compact:
            tail = compact.rsplit(".", 1)[1]
            if len(tail) == 2:
                add(compact)
            else:
                add(compact.replace(".", ""))
        else:
            add(compact)
            digits = compact.lstrip("+-")
            # OCR often drops the decimal point in monetary values (6000 -> 60.00).
            # Keep both interpretations; subtotal reconciliation selects one.
            if len(digits) >= 4:
                add(str(Decimal(compact) / Decimal("100")))

        return candidates

    @classmethod
    def _money_close(cls, left: Decimal, right: Decimal) -> bool:
        return abs(left - right) <= Decimal("0.01")

    @staticmethod
    def _money_to_cents(value: Decimal) -> int:
        return int((value * Decimal("100")).quantize(Decimal("1")))

    @classmethod
    def _extract_invoice_metadata(cls, content: DocumentContent) -> dict[str, str]:
        metadata: dict[str, str] = {}

        for page in content.pages:
            for table in page.tables:
                cls._collect_metadata_rows(metadata, table.rows)

            borderless_metadata: dict[str, str] = {}
            cls._collect_metadata_rows(
                borderless_metadata,
                cls._layout_rows(page.text),
            )
            for key, value in borderless_metadata.items():
                metadata.setdefault(key, value)

        return metadata

    @classmethod
    def _extract_invoice_totals_and_terms(
        cls,
        content: DocumentContent,
        invoice: SupplierInvoiceData,
    ) -> None:
        totals = extract_totals_from_text(content, cls._parse_decimal)
        invoice.subtotal = totals["subtotal"]
        invoice.vat_rate = totals["vat_rate"]
        invoice.vat_amount = totals["vat_amount"]
        invoice.total = (
            extract_preferred_invoice_total(content, cls._parse_decimal)
            or totals["total"]
        )

        for page in content.pages:
            for block in page.blocks:
                text = block.text.strip()
                lower_text = text.lower()

                if lower_text.startswith("payment terms:"):
                    invoice.payment_terms = text.split(":", 1)[1].strip()
                elif lower_text.startswith("notes:"):
                    invoice.notes = text.split(":", 1)[1].strip()
