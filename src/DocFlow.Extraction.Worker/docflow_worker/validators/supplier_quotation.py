from decimal import Decimal, ROUND_HALF_UP

from docflow_worker.models import (
    StructuredValidationResult,
    ValidationCheckResult,
)
from docflow_worker.supplier_quotation_models import SupplierQuotationData


class SupplierQuotationValidator:
    """Deterministic arithmetic validation for normalized supplier quotation data."""

    tolerance = Decimal("0.01")
    money_quantum = Decimal("0.01")

    def validate(self, quotation: SupplierQuotationData) -> StructuredValidationResult:
        checks = {
            "line_totals": self._validate_line_totals(quotation),
            "subtotal": self._validate_subtotal(quotation),
            "vat": self._validate_vat(quotation),
            "grand_total": self._validate_grand_total(quotation),
        }

        statuses = [check.status for check in checks.values()]
        if "failed" in statuses:
            status = "invalid"
        elif "skipped" in statuses:
            status = "incomplete"
        else:
            status = "valid"

        passed_count = sum(1 for check in checks.values() if check.status == "passed")
        confidence = passed_count / len(checks)

        return StructuredValidationResult(
            status=status,
            checks=checks,
            confidence=confidence,
        )

    def _validate_line_totals(
        self,
        quotation: SupplierQuotationData,
    ) -> ValidationCheckResult:
        if not quotation.items:
            return ValidationCheckResult(
                status="skipped",
                message="No quotation items were extracted.",
            )

        missing_indexes: list[int] = []
        mismatches: list[dict[str, str | int]] = []

        for index, item in enumerate(quotation.items, start=1):
            if item.unit_price is None or item.line_total is None:
                missing_indexes.append(index)
                continue

            expected = self._money(item.quantity * item.unit_price)
            actual = self._money(item.line_total)
            if abs(expected - actual) > self.tolerance:
                mismatches.append(
                    {
                        "item_index": index,
                        "sku": item.sku,
                        "expected": str(expected),
                        "actual": str(actual),
                    }
                )

        if mismatches:
            return ValidationCheckResult(
                status="failed",
                message="One or more item line totals do not equal quantity × unit price.",
                details={"mismatches": mismatches},
            )

        if missing_indexes:
            return ValidationCheckResult(
                status="skipped",
                message="Some item line totals could not be checked because values are missing.",
                details={"item_indexes": missing_indexes},
            )

        return ValidationCheckResult(
            status="passed",
            message="All item line totals equal quantity × unit price.",
            details={"checked_items": len(quotation.items)},
        )

    def _validate_subtotal(
        self,
        quotation: SupplierQuotationData,
    ) -> ValidationCheckResult:
        if quotation.subtotal is None:
            return ValidationCheckResult(
                status="skipped",
                message="Subtotal was not extracted.",
            )

        if not quotation.items or any(item.line_total is None for item in quotation.items):
            return ValidationCheckResult(
                status="skipped",
                message="Subtotal cannot be checked because item line totals are incomplete.",
            )

        expected = self._money(
            sum((item.line_total for item in quotation.items if item.line_total is not None), Decimal("0"))
        )
        actual = self._money(quotation.subtotal)

        if abs(expected - actual) > self.tolerance:
            return ValidationCheckResult(
                status="failed",
                message="Subtotal does not equal the sum of item line totals.",
                details={"expected": str(expected), "actual": str(actual)},
            )

        return ValidationCheckResult(
            status="passed",
            message="Subtotal equals the sum of item line totals.",
            details={"expected": str(expected), "actual": str(actual)},
        )

    def _validate_vat(
        self,
        quotation: SupplierQuotationData,
    ) -> ValidationCheckResult:
        if (
            quotation.subtotal is None
            or quotation.vat_rate is None
            or quotation.vat_amount is None
        ):
            return ValidationCheckResult(
                status="skipped",
                message="VAT cannot be checked because subtotal, VAT rate, or VAT amount is missing.",
            )

        expected = self._money(quotation.subtotal * quotation.vat_rate / Decimal("100"))
        actual = self._money(quotation.vat_amount)

        if abs(expected - actual) > self.tolerance:
            return ValidationCheckResult(
                status="failed",
                message="VAT amount does not equal subtotal × VAT rate.",
                details={"expected": str(expected), "actual": str(actual)},
            )

        return ValidationCheckResult(
            status="passed",
            message="VAT amount equals subtotal × VAT rate.",
            details={"expected": str(expected), "actual": str(actual)},
        )

    def _validate_grand_total(
        self,
        quotation: SupplierQuotationData,
    ) -> ValidationCheckResult:
        if quotation.subtotal is None or quotation.vat_amount is None or quotation.total is None:
            return ValidationCheckResult(
                status="skipped",
                message="Grand total cannot be checked because subtotal, VAT amount, or total is missing.",
            )

        expected = self._money(quotation.subtotal + quotation.vat_amount)
        actual = self._money(quotation.total)

        if abs(expected - actual) > self.tolerance:
            return ValidationCheckResult(
                status="failed",
                message="Grand total does not equal subtotal + VAT amount.",
                details={"expected": str(expected), "actual": str(actual)},
            )

        return ValidationCheckResult(
            status="passed",
            message="Grand total equals subtotal + VAT amount.",
            details={"expected": str(expected), "actual": str(actual)},
        )

    def _money(self, value: Decimal) -> Decimal:
        return value.quantize(self.money_quantum, rounding=ROUND_HALF_UP)
