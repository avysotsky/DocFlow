from docflow_worker.deterministic_text_fields import (
    extract_labeled_identifier,
    extract_totals_from_text,
    infer_currency,
)
from docflow_worker.engines.deterministic_supplier_quotation import (
    DeterministicSupplierQuotationEngine,
)
from docflow_worker.models import DocumentContent, StructuredExtractionResult
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
        item_table = self._find_item_table(content)
        quotation_items = self._extract_items(item_table) if item_table else []

        invoice = SupplierInvoiceData(
            supplier_name=self._extract_supplier_name(content),
            invoice_number=(
                # Text labels are the most faithful representation for Xero-style and
                # OCR invoices, but the extracted value must be reduced to a compact
                # identifier so neighboring columns are not absorbed into the number.
                extract_labeled_identifier(
                    content,
                    ("invoice number", "invoice no.", "invoice no"),
                )
                or self._metadata_value(
                    metadata,
                    "invoice no",
                    "invoice number",
                )
            ),
            invoice_date=self._parse_date(
                self._metadata_value(metadata, "invoice date")
            ),
            due_date=self._parse_date(
                self._metadata_value(metadata, "due date", "payment due")
            ),
            currency=(
                self._metadata_value(metadata, "currency")
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
            items=[
                SupplierInvoiceItem(
                    sku=item.sku,
                    description=item.description,
                    quantity=item.quantity,
                    unit=item.unit,
                    unit_price=item.unit_price,
                    line_total=item.line_total,
                )
                for item in quotation_items
            ],
        )

        self._extract_invoice_totals_and_terms(content, invoice)

        return StructuredExtractionResult(
            engine=self.name,
            document_type="supplier_invoice",
            data=invoice.model_dump(),
            confidence=None,
        )

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
        invoice.total = totals["total"]

        for page in content.pages:
            for block in page.blocks:
                text = block.text.strip()
                lower_text = text.lower()

                if lower_text.startswith("payment terms:"):
                    invoice.payment_terms = text.split(":", 1)[1].strip()
                elif lower_text.startswith("notes:"):
                    invoice.notes = text.split(":", 1)[1].strip()
