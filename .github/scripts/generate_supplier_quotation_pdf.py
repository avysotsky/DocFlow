from pathlib import Path
import sys

import pymupdf


def draw_table(page, x_positions, y_positions, rows, font_size=7):
    for y in y_positions:
        page.draw_line((x_positions[0], y), (x_positions[-1], y))
    for x in x_positions:
        page.draw_line((x, y_positions[0]), (x, y_positions[-1]))

    for row_index, row in enumerate(rows):
        top = y_positions[row_index]
        bottom = y_positions[row_index + 1]
        for column_index, value in enumerate(row):
            left = x_positions[column_index]
            right = x_positions[column_index + 1]
            page.insert_textbox(
                pymupdf.Rect(left + 3, top + 3, right - 3, bottom - 2),
                value,
                fontsize=font_size,
                align=0,
            )


def main() -> None:
    output_path = Path(sys.argv[1] if len(sys.argv) > 1 else "supplier-quotation.pdf")
    grand_total = sys.argv[2] if len(sys.argv) > 2 else "1748.40"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    document = pymupdf.open()
    page = document.new_page(width=842, height=595)

    page.insert_textbox(
        pymupdf.Rect(30, 20, 360, 75),
        "ACME Components Ltd.\nVAT ID: DE314159265\nsales@acme-components.example",
        fontsize=9,
    )

    metadata_rows = [
        ["Quotation No.", "QT-2026-183", "Currency", "EUR"],
        ["Quotation Date", "2026-09-30", "Valid Until", "2026-10-15"],
        ["Customer Ref.", "RFQ-78421", "Incoterms", "DAP Odesa, Ukraine"],
    ]
    draw_table(
        page,
        [30, 155, 295, 420, 570],
        [90, 115, 140, 165],
        metadata_rows,
        font_size=7,
    )

    item_rows = [
        ["SKU", "Description", "Qty", "Unit", "Unit Price (EUR)", "Lead Time (days)", "Line Total (EUR)"],
        ["AX-100", "Sensor bracket", "20", "pcs", "12.50", "5", "250.00"],
        ["BX-240", "Junction box", "8", "pcs", "38.75", "7", "310.00"],
        ["CX-310", "Cable gland set", "15", "pcs", "18.00", "4", "270.00"],
        ["DX-410", "Mounting plate", "7", "pcs", "45.00", "6", "315.00"],
        ["EX-510", "Terminal module", "8", "pcs", "39.00", "8", "312.00"],
    ]
    draw_table(
        page,
        [30, 90, 280, 325, 370, 455, 540, 650],
        [185, 210, 235, 260, 285, 310, 335],
        item_rows,
        font_size=6.2,
    )

    # Keep totals vertically separated. PyMuPDF may merge horizontally aligned
    # text into one block, while the deterministic extractor deliberately reads
    # each totals block by its leading label.
    page.insert_textbox(
        pymupdf.Rect(30, 355, 330, 378),
        "Subtotal: 1457.00 EUR",
        fontsize=9,
    )
    page.insert_textbox(
        pymupdf.Rect(30, 385, 330, 408),
        "VAT 20%: 291.40 EUR",
        fontsize=9,
    )
    page.insert_textbox(
        pymupdf.Rect(30, 415, 330, 438),
        f"Total: {grand_total} EUR",
        fontsize=9,
    )
    page.insert_textbox(
        pymupdf.Rect(30, 460, 600, 485),
        "Payment terms: 30% advance, 70% before shipment.",
        fontsize=9,
    )
    page.insert_textbox(
        pymupdf.Rect(30, 505, 400, 540),
        "Prepared by: Martin Keller\nQuote status: Issued",
        fontsize=9,
    )

    document.save(output_path)
    document.close()


if __name__ == "__main__":
    main()
