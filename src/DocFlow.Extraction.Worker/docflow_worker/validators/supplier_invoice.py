from docflow_worker.models import StructuredValidationResult
from docflow_worker.supplier_invoice_models import SupplierInvoiceData
from docflow_worker.validators.supplier_quotation import SupplierQuotationValidator


class SupplierInvoiceValidator(SupplierQuotationValidator):
    """Applies the shared supplier-document arithmetic checks to invoices."""

    def validate(self, invoice: SupplierInvoiceData) -> StructuredValidationResult:
        # Supplier quotations and invoices share the same arithmetic invariants:
        # line total = quantity × unit price, subtotal = sum(lines), VAT and grand total.
        return super().validate(invoice)  # type: ignore[arg-type]
