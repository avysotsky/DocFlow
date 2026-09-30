from decimal import Decimal

from docflow_worker.deterministic_text_fields import extract_totals_from_text
from docflow_worker.models import BoundingBox, DocumentContent, PageContent, TextBlockContent


def _parse_decimal(value: str | None) -> Decimal | None:
    if value is None:
        return None
    return Decimal(value.replace(",", "").strip())


def test_parenthetical_discount_does_not_overwrite_subtotal() -> None:
    content = DocumentContent(
        pages=[
            PageContent(
                page_number=1,
                width=100,
                height=100,
                text=(
                    "Subtotal (includes a discount of 34.50) 103.50\n"
                    "TOTAL VAT 20% 20.70\n"
                    "TOTAL GBP 124.20"
                ),
                blocks=[
                    TextBlockContent(
                        block_number=1,
                        text="Subtotal (includes a discount of 34.50)",
                        bbox=BoundingBox(x0=0, y0=0, x1=100, y1=10),
                    )
                ],
                words=[],
                tables=[],
            )
        ]
    )

    totals = extract_totals_from_text(content, _parse_decimal)

    assert totals["subtotal"] == Decimal("103.50")
    assert totals["vat_rate"] == Decimal("20")
    assert totals["vat_amount"] == Decimal("20.70")
    assert totals["total"] == Decimal("124.20")
