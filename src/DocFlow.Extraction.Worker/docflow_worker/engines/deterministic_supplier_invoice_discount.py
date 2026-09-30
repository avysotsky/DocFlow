import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from docflow_worker.engines.deterministic_supplier_invoice import (
    DeterministicSupplierInvoiceEngine,
)
from docflow_worker.models import DocumentContent, StructuredExtractionResult
from docflow_worker.supplier_invoice_models import (
    SupplierInvoiceData,
    SupplierInvoiceItem,
)


class DeterministicSupplierInvoiceDiscountEngine(DeterministicSupplierInvoiceEngine):
    """Invoice parser extension for explicit discounts, locale fallbacks and legacy OCR rows."""

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

        self._apply_german_invoice_fallbacks(content.text, invoice)

        discount_amount = self._extract_document_discount(content.text)
        if discount_amount is None:
            result.engine = self.name
            result.data = invoice.model_dump()
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
    def _apply_german_invoice_fallbacks(
        cls,
        text: str,
        invoice: SupplierInvoiceData,
    ) -> None:
        """Recover common German invoice labels and summary arithmetic.

        This path is activated only for text that contains German invoice vocabulary.
        It complements the existing English parser; it does not replace fields on
        unrelated documents.
        """
        if not re.search(
            r"\b(?:Rechnung|Rechnungsnummer|Rechnungsdatum|Rechnungsbetrag)\b",
            text,
            flags=re.IGNORECASE,
        ):
            return

        if invoice.invoice_number is None:
            value = cls._german_labeled_value(text, "Rechnungsnummer")
            if value:
                invoice.invoice_number = value

        if invoice.invoice_date is None:
            value = cls._german_labeled_value(text, "Rechnungsdatum")
            if value:
                invoice.invoice_date = cls._parse_date(value)

        if invoice.due_date is None:
            value = cls._german_labeled_value(text, "Zahlungsziel")
            if value:
                invoice.due_date = cls._parse_date(value)

        # Common German summary table:
        # Gesamt: Netto | MwSt. | MwSt. in % | Brutto
        #         -96,48 | -18,33 | 19,00 | -114,81
        normalized = " ".join(text.split())
        summary = re.search(
            r"\bGesamt\s*:\s*Netto\s+MwSt\.?\s+MwSt\.?\s+in\s+%\s+Brutto\s+"
            r"(?P<subtotal>[-+]?\d[\d.,]*)\s+"
            r"(?P<vat_amount>[-+]?\d[\d.,]*)\s+"
            r"(?P<vat_rate>[-+]?\d[\d.,]*)\s+"
            r"(?P<total>[-+]?\d[\d.,]*)",
            normalized,
            flags=re.IGNORECASE,
        )
        if summary is not None:
            subtotal = cls._parse_locale_decimal(summary.group("subtotal"))
            vat_amount = cls._parse_locale_decimal(summary.group("vat_amount"))
            vat_rate = cls._parse_locale_decimal(summary.group("vat_rate"))
            total = cls._parse_locale_decimal(summary.group("total"))

            if subtotal is not None:
                invoice.subtotal = subtotal
            if vat_amount is not None:
                invoice.vat_amount = vat_amount
            if vat_rate is not None:
                invoice.vat_rate = vat_rate
            if total is not None:
                invoice.total = total
        elif invoice.total is None:
            value = cls._german_labeled_value(text, "Rechnungsbetrag")
            total = cls._parse_locale_decimal(value)
            if total is not None:
                invoice.total = total

    @staticmethod
    def _german_labeled_value(text: str, label: str) -> str | None:
        match = re.search(
            rf"\b{re.escape(label)}\s*:\s*(?P<value>[^\s]+)",
            text,
            flags=re.IGNORECASE,
        )
        if match is None:
            return None
        return match.group("value").strip()

    @staticmethod
    def _parse_locale_decimal(value: str | None) -> Decimal | None:
        if not value:
            return None

        compact = re.sub(r"[^0-9,.+\-]", "", value)
        if not compact:
            return None

        if "," in compact and "." in compact:
            if compact.rfind(",") > compact.rfind("."):
                compact = compact.replace(".", "").replace(",", ".")
            else:
                compact = compact.replace(",", "")
        elif "," in compact:
            compact = compact.replace(",", ".")

        try:
            return Decimal(compact)
        except InvalidOperation:
            return None

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
