from docflow_worker.models import DocumentContent


SUPPORTED_DOCUMENT_TYPES = ("supplier_quotation", "supplier_invoice", "purchase_order")


def detect_document_type(content: DocumentContent) -> str:
    """Detect the supported supplier document type using deterministic text markers."""
    text = content.text.lower()

    purchase_order_markers = (
        "purchase order number",
        "order number and date must be quoted on invoices",
        "order date",
        "supplier name and address",
        "supplier:",
        "delivery address",
        "part number/description",
        "total price (excl. vat)",
        "order total",
        "grand total",
    )
    purchase_order_score = sum(marker in text for marker in purchase_order_markers)
    has_purchase_order_title = (
        "\npurchase order\n" in f"\n{text}\n"
        or text.lstrip().startswith("purchase order")
        or text.lstrip().startswith("purchase order number")
        or text.lstrip().startswith("purchase order\n")
    )
    if has_purchase_order_title and purchase_order_score >= 2:
        return "purchase_order"

    if (
        has_purchase_order_title
        and "order date" in text
        and ("supplier:" in text or "supplier name and address" in text)
        and (
            "part number/description" in text
            or ("description" in text and "quantity" in text)
            or "grand total" in text
        )
    ):
        return "purchase_order"

    if "invaice" in text and ("invoice total" in text or "total net amount" in text):
        return "supplier_invoice"

    if "proforma invoice" in text or "pro-forma invoice" in text:
        return "supplier_invoice"

    german_invoice_markers = (
        "rechnungsnummer",
        "rechnungsdatum",
        "rechnungsbetrag",
        "zahlungsziel",
    )
    german_invoice_score = sum(marker in text for marker in german_invoice_markers)
    if german_invoice_score >= 2 and "rechnung" in text:
        return "supplier_invoice"

    french_invoice_markers = (
        "total ht",
        "total tva",
        "total ttc",
        "date d'échéance",
        "net a payer",
        "net à payer",
    )
    french_invoice_score = sum(marker in text for marker in french_invoice_markers)
    if french_invoice_score >= 2 and "facture" in text:
        return "supplier_invoice"

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
        "invoice #:",
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
