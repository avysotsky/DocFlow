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
    """Deterministic parser for digital supplier invoices."""

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
            description = cls._row_value(row, description_index)
            quantity = cls._parse_decimal(cls._row_value(row, quantity_index))
            if not description or quantity is None:
                continue

            items.append(
                SupplierInvoiceItem(
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
            )

        return items

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
