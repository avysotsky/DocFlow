import re
from decimal import Decimal, InvalidOperation

from docflow_worker.models import DocumentContent
from docflow_worker.supplier_invoice_models import SupplierInvoiceData, SupplierInvoiceItem


_NUMERIC_ITEM_ROW = re.compile(
    r"^\s*(?P<quantity>\d[\d,.]*)\s+"
    r"(?P<unit_price>\d[\d,.]*)\s+"
    r"(?:(?P<vat_rate>\d[\d,.]*)\s*%\s+)?"
    r"(?P<line_total>\d[\d,.]*)\s*$"
)


def apply_split_item_row_fallback(
    content: DocumentContent,
    invoice: SupplierInvoiceData,
) -> None:
    """Recover borderless items whose description and numeric row are split.

    Layout-preserved PDF text can emit a visual row as two physical lines: a
    description line followed by ``quantity unit-price VAT% amount``. The normal table
    parser deliberately expects the description and arithmetic on the same logical row.
    This conservative fallback runs only when no items were already extracted and only
    inside a section with explicit Description/Quantity/Unit Price/Amount headers.
    """
    if invoice.items:
        return

    recovered: list[SupplierInvoiceItem] = []

    for page in content.pages:
        lines = [line.strip() for line in page.text.splitlines() if line.strip()]
        header_index = _find_item_header(lines)
        if header_index is None:
            continue

        pending_description: list[str] = []
        for line in lines[header_index + 1 :]:
            normalized = _normalize(line)
            if normalized.startswith("subtotal"):
                break

            match = _NUMERIC_ITEM_ROW.match(line)
            if match is None:
                if _description_candidate(line):
                    pending_description.append(line)
                continue

            if not pending_description:
                continue

            quantity = _decimal(match.group("quantity"))
            unit_price = _decimal(match.group("unit_price"))
            line_total = _decimal(match.group("line_total"))
            if quantity is None or unit_price is None or line_total is None:
                continue

            description = " ".join(pending_description).strip()
            pending_description.clear()
            if not description:
                continue

            recovered.append(
                SupplierInvoiceItem(
                    sku=None,
                    description=description,
                    quantity=quantity,
                    unit_price=unit_price,
                    line_total=line_total,
                )
            )

        if recovered:
            invoice.items = recovered
            return


def _find_item_header(lines: list[str]) -> int | None:
    for index, line in enumerate(lines):
        normalized = _normalize(line)
        if (
            "description" in normalized
            and "quantity" in normalized
            and "unit price" in normalized
            and "amount" in normalized
        ):
            return index
    return None


def _description_candidate(line: str) -> bool:
    normalized = _normalize(line)
    if not re.search(r"[a-z]", normalized):
        return False
    if normalized.startswith(
        (
            "invoice ",
            "vat number",
            "reference",
            "subtotal",
            "total ",
            "amount due",
            "due date",
        )
    ):
        return False
    return True


def _normalize(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value.casefold()).split())


def _decimal(value: str) -> Decimal | None:
    compact = value.replace(" ", "")
    if "," in compact and "." in compact:
        compact = compact.replace(",", "")
    elif "," in compact:
        tail = compact.rsplit(",", 1)[1]
        compact = compact.replace(",", ".") if len(tail) == 2 else compact.replace(",", "")
    try:
        return Decimal(compact)
    except InvalidOperation:
        return None
