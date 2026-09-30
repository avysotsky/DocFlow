from decimal import Decimal

from docflow_worker.models import StructuredValidationResult, ValidationCheckResult
from docflow_worker.supplier_invoice_models import SupplierInvoiceData
from docflow_worker.validators.supplier_quotation import SupplierQuotationValidator


class SupplierInvoiceValidator(SupplierQuotationValidator):
    """Applies supplier-document arithmetic checks to invoices, including discounts."""

    def validate(self, invoice: SupplierInvoiceData) -> StructuredValidationResult:
        return super().validate(invoice)  # type: ignore[arg-type]

    def _validate_line_totals(
        self,
        invoice: SupplierInvoiceData,
    ) -> ValidationCheckResult:
        if not invoice.items:
            return ValidationCheckResult(
                status="skipped",
                message="No invoice items were extracted.",
            )

        missing_indexes: list[int] = []
        mismatches: list[dict[str, str | int | None]] = []

        for index, item in enumerate(invoice.items, start=1):
            if item.unit_price is None or item.line_total is None:
                missing_indexes.append(index)
                continue

            discount_rate = item.discount_rate or Decimal("0")
            if discount_rate < 0 or discount_rate > 100:
                mismatches.append(
                    {
                        "item_index": index,
                        "sku": item.sku,
                        "discount_rate": str(discount_rate),
                        "expected": "discount rate between 0 and 100",
                        "actual": str(discount_rate),
                    }
                )
                continue

            gross = item.quantity * item.unit_price
            expected = self._money(
                gross * (Decimal("1") - discount_rate / Decimal("100"))
            )
            actual = self._money(item.line_total)

            if abs(expected - actual) > self.tolerance:
                mismatches.append(
                    {
                        "item_index": index,
                        "sku": item.sku,
                        "discount_rate": str(discount_rate),
                        "expected": str(expected),
                        "actual": str(actual),
                    }
                )

        if mismatches:
            return ValidationCheckResult(
                status="failed",
                message=(
                    "One or more invoice line totals do not equal quantity × unit price "
                    "after item discount."
                ),
                details={"mismatches": mismatches},
            )

        if missing_indexes:
            return ValidationCheckResult(
                status="skipped",
                message=(
                    "Some invoice line totals could not be checked because values are missing."
                ),
                details={"item_indexes": missing_indexes},
            )

        return ValidationCheckResult(
            status="passed",
            message="All invoice line totals match quantity × unit price after item discount.",
            details={"checked_items": len(invoice.items)},
        )
