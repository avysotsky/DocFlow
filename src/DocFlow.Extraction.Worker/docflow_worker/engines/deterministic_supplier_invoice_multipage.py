import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

from docflow_worker.engines.deterministic_supplier_invoice_discount import (
    DeterministicSupplierInvoiceDiscountEngine,
)
from docflow_worker.models import DocumentContent, StructuredExtractionResult
from docflow_worker.supplier_invoice_models import SupplierInvoiceData, SupplierInvoiceItem


class DeterministicSupplierInvoiceMultipageEngine(
    DeterministicSupplierInvoiceDiscountEngine
):
    """Invoice v2 extension for tax-inclusive retail tables spanning multiple pages."""

    @property
    def name(self) -> str:
        # Keep the public engine contract stable while extending deterministic coverage.
        return "deterministic_supplier_invoice_v2"

    async def extract(
        self,
        content: DocumentContent,
        *,
        document_name: str | None = None,
    ) -> StructuredExtractionResult:
        result = await super().extract(content, document_name=document_name)
        invoice = SupplierInvoiceData.model_validate(result.data)

        self._apply_tax_inclusive_retail_fallbacks(content, invoice)

        result.engine = self.name
        result.data = invoice.model_dump()
        return result

    @classmethod
    def _apply_tax_inclusive_retail_fallbacks(
        cls,
        content: DocumentContent,
        invoice: SupplierInvoiceData,
    ) -> None:
        text = content.text
        lower = text.lower()
        if not (
            "tax invoice" in lower
            and re.search(r"\binvoice\s*#\s*:", text, flags=re.IGNORECASE)
            and re.search(r"total\s*\(\s*inc\s+gst\s*\)", text, flags=re.IGNORECASE)
            and re.search(r"total\s+includes\s+gst\s+of", text, flags=re.IGNORECASE)
        ):
            return

        invoice_number = re.search(
            r"\binvoice\s*#\s*:\s*(?P<value>[A-Za-z0-9._/-]+)",
            text,
            flags=re.IGNORECASE,
        )
        if invoice_number is not None:
            invoice.invoice_number = invoice_number.group("value").strip()

        date_match = re.search(
            r"\bDATE\s+(?P<value>\d{1,2}/\d{1,2}/\d{4})\b",
            text,
            flags=re.IGNORECASE,
        )
        if date_match is not None:
            try:
                invoice.invoice_date = datetime.strptime(
                    date_match.group("value"), "%d/%m/%Y"
                ).date()
            except ValueError:
                pass

        total_match = re.search(
            r"total\s*\(\s*inc\s+gst\s*\)\s*(?P<value>[0-9][0-9,.]*)",
            text,
            flags=re.IGNORECASE,
        )
        gst_match = re.search(
            r"total\s+includes\s+gst\s+of\s*(?P<value>[0-9][0-9,.]*)",
            text,
            flags=re.IGNORECASE,
        )
        total = cls._simple_decimal(total_match.group("value") if total_match else None)
        gst = cls._simple_decimal(gst_match.group("value") if gst_match else None)

        if total is not None:
            invoice.total = cls._money(total)
        if gst is not None:
            invoice.vat_amount = cls._money(gst)
        if total is not None and gst is not None and total >= gst:
            invoice.subtotal = cls._money(total - gst)

        items: list[SupplierInvoiceItem] = []
        for page in content.pages:
            for line in page.text.splitlines():
                item = cls._parse_packed_retail_line(line)
                if item is not None:
                    items.append(item)

        if items:
            invoice.items = items
        invoice.tax_inclusive = True

    @classmethod
    def _parse_packed_retail_line(cls, line: str) -> SupplierInvoiceItem | None:
        match = re.match(
            r"^\s*\d+\s+"
            r"(?P<quantity>\d+(?:\.\d+)?)\s+"
            r"(?P<description>.+?)\s{2,}"
            r"(?P<unit_price>\d+(?:\.\d{1,2})?)\s+"
            r"(?P<ordered_total>\d+(?:\.\d{1,2})?)\s+"
            r"(?P<packed_total>\d+(?:\.\d{1,2})?)\s*$",
            line,
        )
        if match is None:
            return None

        quantity = cls._simple_decimal(match.group("quantity"))
        unit_price = cls._simple_decimal(match.group("unit_price"))
        packed_total = cls._simple_decimal(match.group("packed_total"))
        description = match.group("description").strip()
        if quantity is None or unit_price is None or packed_total is None or not description:
            return None

        return SupplierInvoiceItem(
            sku=None,
            description=description,
            quantity=quantity,
            unit_price=unit_price,
            line_total=packed_total,
        )

    @staticmethod
    def _simple_decimal(value: str | None) -> Decimal | None:
        if not value:
            return None
        try:
            return Decimal(value.replace(",", ""))
        except InvalidOperation:
            return None
