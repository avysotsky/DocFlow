from docflow_worker.document_type_detector import detect_document_type
from docflow_worker.engines import DeterministicSupplierQuotationEngine
from docflow_worker.engines.deterministic_supplier_invoice_discount import (
    DeterministicSupplierInvoiceDiscountEngine,
)
from docflow_worker.models import DocumentContent, StructuredExtractionResult
from docflow_worker.supplier_invoice_models import SupplierInvoiceData
from docflow_worker.supplier_quotation_models import SupplierQuotationData
from docflow_worker.validators import SupplierInvoiceValidator, SupplierQuotationValidator


SUPPORTED_DOCUMENT_TYPES = ("supplier_quotation", "supplier_invoice")


async def extract_structured_document(
    content: DocumentContent,
    *,
    document_type: str = "auto",
    document_name: str | None = None,
) -> StructuredExtractionResult:
    """Run the production deterministic semantic pipeline for one parsed document."""
    resolved_document_type = (
        detect_document_type(content) if document_type == "auto" else document_type
    )

    if resolved_document_type == "supplier_quotation":
        result = await DeterministicSupplierQuotationEngine().extract(
            content,
            document_name=document_name,
        )
        quotation = SupplierQuotationData.model_validate(result.data)
        validation = SupplierQuotationValidator().validate(quotation)
    elif resolved_document_type == "supplier_invoice":
        result = await DeterministicSupplierInvoiceDiscountEngine().extract(
            content,
            document_name=document_name,
        )
        invoice = SupplierInvoiceData.model_validate(result.data)
        validation = SupplierInvoiceValidator().validate(invoice)
    else:
        supported = ", ".join(SUPPORTED_DOCUMENT_TYPES)
        raise ValueError(
            f"Unsupported document type '{resolved_document_type}'. "
            f"Supported types: {supported}."
        )

    result.validation_status = validation.status
    result.validation = validation
    result.confidence = validation.confidence
    return result
