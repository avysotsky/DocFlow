from docflow_worker.models import DocumentContent


SUPPORTED_DOCUMENT_TYPES = ("supplier_quotation", "supplier_invoice")


def detect_document_type(content: DocumentContent) -> str:
    """Detect the supported supplier document type using deterministic text markers."""
    text = content.text.lower()

    quotation_markers = (
        "quotation no",
        "quotation number",
        "quotation date",
        "quote no",
        "quote number",
        "quote date",
        "valid until",
    )
    invoice_markers = (
        "invoice no",
        "invoice number",
        "invoice date",
        "due date",
        "payment due",
    )

    quotation_score = sum(marker in text for marker in quotation_markers)
    invoice_score = sum(marker in text for marker in invoice_markers)

    if invoice_score >= 2 and invoice_score > quotation_score:
        return "supplier_invoice"
    if quotation_score >= 2 and quotation_score > invoice_score:
        return "supplier_quotation"

    if invoice_score > 0 and quotation_score == 0 and "invoice" in text:
        return "supplier_invoice"
    if quotation_score > 0 and invoice_score == 0 and (
        "quotation" in text or "quote" in text
    ):
        return "supplier_quotation"

    raise ValueError("The document type could not be detected deterministically.")
