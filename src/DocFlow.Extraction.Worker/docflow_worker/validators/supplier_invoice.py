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

    def _validate_subtotal(
        self,
        invoice: SupplierInvoiceData,
    ) -> ValidationCheckResult:
        if invoice.tax_inclusive:
            if invoice.total is None:
                return ValidationCheckResult(
                    status="skipped",
                    message="Tax-inclusive invoice total was not extracted.",
                )
            if not invoice.items or any(item.line_total is None for item in invoice.items):
                return ValidationCheckResult(
                    status="skipped",
                    message="Tax-inclusive total cannot be checked because item line totals are incomplete.",
                )

            expected = self._money(
                sum(
                    (item.line_total for item in invoice.items if item.line_total is not None),
                    Decimal("0"),
                )
            )
            actual = self._money(invoice.total)
            if abs(expected - actual) > self.tolerance:
                return ValidationCheckResult(
                    status="failed",
                    message="Tax-inclusive invoice total does not equal the sum of item line totals.",
                    details={"expected": str(expected), "actual": str(actual)},
                )

            return ValidationCheckResult(
                status="passed",
                message="Tax-inclusive invoice total equals the sum of item line totals.",
                details={"expected": str(expected), "actual": str(actual)},
            )

        if invoice.discount_amount is None:
            return super()._validate_subtotal(invoice)  # type: ignore[arg-type]

        if invoice.subtotal is None:
            return ValidationCheckResult(
                status="skipped",
                message="Subtotal was not extracted.",
            )

        if invoice.discount_amount < 0:
            return ValidationCheckResult(
                status="failed",
                message="Invoice-level discount cannot be negative.",
                details={"discount_amount": str(invoice.discount_amount)},
            )

        if not invoice.items or any(item.line_total is None for item in invoice.items):
            return ValidationCheckResult(
                status="skipped",
                message=(
                    "Discounted subtotal cannot be checked because item line totals are incomplete."
                ),
            )

        gross = self._money(
            sum(
                (item.line_total for item in invoice.items if item.line_total is not None),
                Decimal("0"),
            )
        )
        expected = self._money(gross - invoice.discount_amount)
        actual = self._money(invoice.subtotal)

        if expected < 0:
            return ValidationCheckResult(
                status="failed",
                message="Invoice-level discount exceeds the gross item total.",
                details={
                    "gross": str(gross),
                    "discount_amount": str(invoice.discount_amount),
                },
            )

        if abs(expected - actual) > self.tolerance:
            return ValidationCheckResult(
                status="failed",
                message="Subtotal does not equal gross item totals minus invoice-level discount.",
                details={
                    "gross": str(gross),
                    "discount_amount": str(invoice.discount_amount),
                    "expected": str(expected),
                    "actual": str(actual),
                },
            )

        return ValidationCheckResult(
            status="passed",
            message="Subtotal equals gross item totals minus invoice-level discount.",
            details={
                "gross": str(gross),
                "discount_amount": str(invoice.discount_amount),
                "expected": str(expected),
                "actual": str(actual),
            },
        )

    def _validate_vat(
        self,
        invoice: SupplierInvoiceData,
    ) -> ValidationCheckResult:
        if not invoice.tax_inclusive:
            return super()._validate_vat(invoice)  # type: ignore[arg-type]

        if invoice.subtotal is None or invoice.vat_amount is None or invoice.total is None:
            return ValidationCheckResult(
                status="skipped",
                message=(
                    "Tax-inclusive GST cannot be checked because net subtotal, GST amount, "
                    "or total is missing."
                ),
            )

        expected = self._money(invoice.subtotal + invoice.vat_amount)
        actual = self._money(invoice.total)
        if abs(expected - actual) > self.tolerance:
            return ValidationCheckResult(
                status="failed",
                message="Tax-inclusive total does not reconcile to net subtotal plus GST.",
                details={"expected": str(expected), "actual": str(actual)},
            )

        return ValidationCheckResult(
            status="passed",
            message="Tax-inclusive total reconciles to net subtotal plus GST.",
            details={"expected": str(expected), "actual": str(actual)},
        )
