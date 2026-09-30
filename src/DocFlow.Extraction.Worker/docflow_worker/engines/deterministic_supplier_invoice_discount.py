import re
from decimal import Decimal, ROUND_HALF_UP

from docflow_worker.engines.deterministic_supplier_invoice import (
    DeterministicSupplierInvoiceEngine,
)
from docflow_worker.models import DocumentContent, StructuredExtractionResult
from docflow_worker.supplier_invoice_models import (
    SupplierInvoiceData,
    SupplierInvoiceItem,
)


class DeterministicSupplierInvoiceDiscountEngine(DeterministicSupplierInvoiceEngine):
    """Invoice parser extension for explicit invoice-level discounts and legacy OCR rows."""

    _money_quantum = Decimal("0.01")

    @property
    def name(self) -> str:
        return "deterministic_supplier_invoice_v2"

    async def extract(
        self,
        content: DocumentContent,
        *,
        document_name: str | None = None,
    ) -> StructuredExtractionResult:
        result = await super().extract(content, document_name=document_name)
        invoice = SupplierInvoiceData.model_validate(result.data)

        discount_amount = self._extract_document_discount(content.text)
        if discount_amount is None:
            result.engine = self.name
            return result

        invoice.discount_amount = discount_amount

        # Legacy fuel invoices can express a quantity in litres, a unit price in pence,
        # a gross GBP value, and a VAT rate on one OCR row. Recover that arithmetic only
        # when the normal invoice parser did not already find structured items.
        if not invoice.items:
            legacy_item, vat_rate = self._extract_legacy_pence_item(content.text)
            if legacy_item is not None:
                invoice.items = [legacy_item]
                if invoice.vat_rate is None and vat_rate is not None:
                    invoice.vat_rate = vat_rate

        line_totals = [item.line_total for item in invoice.items]
        if line_totals and all(value is not None for value in line_totals):
            gross = sum(
                (value for value in line_totals if value is not None),
                Decimal("0"),
            )
            net_subtotal = self._money(gross - discount_amount)
            if net_subtotal >= 0:
                invoice.subtotal = net_subtotal
                if invoice.vat_amount is not None:
                    invoice.total = self._money(net_subtotal + invoice.vat_amount)

        result.engine = self.name
        result.data = invoice.model_dump()
        return result

    @classmethod
    def _extract_document_discount(cls, text: str) -> Decimal | None:
        normalized = " ".join(text.split())
        match = re.search(
            r"\bless\b.{0,120}?\bdiscount\b(?:\s+of)?\s*(?:£|GBP)?\s*"
            r"(?P<amount>[0-9][0-9,]*(?:\.[0-9]{1,2})?)",
            normalized,
            flags=re.IGNORECASE,
        )
        if match is None:
            return None

        try:
            return Decimal(match.group("amount").replace(",", ""))
        except Exception:
            return None

    @classmethod
    def _extract_legacy_pence_item(
        cls,
        text: str,
    ) -> tuple[SupplierInvoiceItem | None, Decimal | None]:
        pattern = re.compile(
            r"^\s*(?P<description>[A-Za-z][A-Za-z0-9 /&().'-]*?)\s{2,}"
            r"(?P<quantity>[0-9]+(?:\.[0-9]+)?)\s+"
            r"(?P<unit>[lLI1])\s+"
            r"(?P<unit_price>[0-9]+(?:\.[0-9]+)?)p\s+"
            r"(?P<line_total>[0-9]+(?:\.[0-9]+)?)\s+"
            r"(?P<vat_rate>[0-9]+(?:\.[0-9]+)?)\s*$",
            flags=re.MULTILINE,
        )
        match = pattern.search(text)
        if match is None:
            return None, None

        quantity = Decimal(match.group("quantity"))
        unit_price = Decimal(match.group("unit_price")) / Decimal("100")
        line_total = Decimal(match.group("line_total"))
        vat_rate = Decimal(match.group("vat_rate"))
        unit = match.group("unit")
        if unit in {"1", "I"}:
            unit = "l"

        item = SupplierInvoiceItem(
            sku=None,
            description=match.group("description").strip(),
            quantity=quantity,
            unit=unit,
            unit_price=unit_price,
            line_total=line_total,
        )
        return item, vat_rate

    @classmethod
    def _money(cls, value: Decimal) -> Decimal:
        return value.quantize(cls._money_quantum, rounding=ROUND_HALF_UP)
