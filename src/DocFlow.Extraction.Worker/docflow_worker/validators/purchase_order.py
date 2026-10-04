from decimal import Decimal, ROUND_HALF_UP

from docflow_worker.models import StructuredValidationResult, ValidationCheckResult
from docflow_worker.purchase_order_models import PurchaseOrderData


class PurchaseOrderValidator:
    tolerance = Decimal("0.01")
    money_quantum = Decimal("0.01")

    def validate(self, purchase_order: PurchaseOrderData) -> StructuredValidationResult:
        checks = {
            "line_totals": self._validate_line_totals(purchase_order),
            "subtotal": self._validate_subtotal(purchase_order),
            "grand_total": self._validate_grand_total(purchase_order),
        }

        statuses = [check.status for check in checks.values()]
        if "failed" in statuses:
            status = "invalid"
        elif "skipped" in statuses:
            status = "incomplete"
        else:
            status = "valid"

        passed = sum(1 for check in checks.values() if check.status == "passed")
        return StructuredValidationResult(
            status=status,
            checks=checks,
            confidence=passed / len(checks),
        )

    def _validate_line_totals(self, po: PurchaseOrderData) -> ValidationCheckResult:
        if not po.items:
            return ValidationCheckResult(
                status="skipped",
                message="No purchase-order line items were extracted.",
            )

        missing: list[int] = []
        mismatches: list[dict[str, str | int | None]] = []

        for index, item in enumerate(po.items, start=1):
            if (
                item.quantity is None
                or item.unit_price is None
                or item.line_total is None
            ):
                missing.append(index)
                continue

            expected = self._money(item.quantity * item.unit_price)
            actual = self._money(item.line_total)
            if abs(expected - actual) > self.tolerance:
                mismatches.append(
                    {
                        "item_index": index,
                        "line_number": item.line_number,
                        "expected": str(expected),
                        "actual": str(actual),
                    }
                )

        if mismatches:
            return ValidationCheckResult(
                status="failed",
                message="One or more PO line totals do not equal quantity × unit price.",
                details={"mismatches": mismatches},
            )

        if missing:
            return ValidationCheckResult(
                status="skipped",
                message="Some PO line totals cannot be checked because values are missing.",
                details={"item_indexes": missing},
            )

        return ValidationCheckResult(
            status="passed",
            message="All PO line totals equal quantity × unit price.",
            details={"checked_items": len(po.items)},
        )

    def _validate_subtotal(self, po: PurchaseOrderData) -> ValidationCheckResult:
        if po.subtotal is None:
            return ValidationCheckResult(
                status="skipped",
                message="PO subtotal was not extracted.",
            )

        if not po.items or any(item.line_total is None for item in po.items):
            return ValidationCheckResult(
                status="skipped",
                message="PO subtotal cannot be checked because line totals are incomplete.",
            )

        expected = self._money(
            sum(
                (item.line_total for item in po.items if item.line_total is not None),
                Decimal("0"),
            )
        )
        actual = self._money(po.subtotal)

        if abs(expected - actual) > self.tolerance:
            return ValidationCheckResult(
                status="failed",
                message="PO subtotal does not equal the sum of line totals.",
                details={"expected": str(expected), "actual": str(actual)},
            )

        return ValidationCheckResult(
            status="passed",
            message="PO subtotal equals the sum of line totals.",
            details={"expected": str(expected), "actual": str(actual)},
        )

    def _validate_grand_total(self, po: PurchaseOrderData) -> ValidationCheckResult:
        if po.total is None or po.subtotal is None:
            return ValidationCheckResult(
                status="skipped",
                message="PO total cannot be checked because subtotal or total is missing.",
            )

        expected = self._money(po.subtotal + (po.tax_amount or Decimal("0")))
        actual = self._money(po.total)

        if abs(expected - actual) > self.tolerance:
            return ValidationCheckResult(
                status="failed",
                message="PO total does not equal subtotal + tax.",
                details={"expected": str(expected), "actual": str(actual)},
            )

        return ValidationCheckResult(
            status="passed",
            message="PO total equals subtotal + tax.",
            details={"expected": str(expected), "actual": str(actual)},
        )

    def _money(self, value: Decimal) -> Decimal:
        return value.quantize(self.money_quantum, rounding=ROUND_HALF_UP)
