from pathlib import Path
import argparse

import pymupdf


ITEMS = [
    ("AX-100", "Sensor bracket", "pcs", 20, 12.50),
    ("BX-240", "Junction box", "pcs", 8, 38.75),
    ("CX-310", "Cable gland set", "pcs", 15, 18.00),
    ("DX-410", "Mounting plate", "pcs", 7, 45.00),
    ("EX-510", "Terminal module", "pcs", 8, 39.00),
]


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
                str(value),
                fontsize=font_size,
                align=0,
            )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output")
    parser.add_argument(
        "--mismatch-first-price",
        action="store_true",
        help="Raise the first PO line price while keeping PO arithmetic internally valid.",
    )
    args = parser.parse_args()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    items = list(ITEMS)
    if args.mismatch_first_price:
        first = items[0]
        items[0] = (first[0], first[1], first[2], first[3], 13.50)

    rows = [
        [
            "Your Reference",
            "Description",
            "Unit Of Measure",
            "Quantity",
            "Unit Price",
            "Total Price",
        ]
    ]
    total = 0.0
    for reference, description, unit, quantity, unit_price in items:
        line_total = quantity * unit_price
        total += line_total
        rows.append(
            [
                reference,
                description,
                unit,
                str(quantity),
                f"{unit_price:.2f}",
                f"{line_total:.2f}",
            ]
        )

    document = pymupdf.open()
    page = document.new_page(width=842, height=595)

    page.insert_textbox(
        pymupdf.Rect(30, 20, 800, 55),
        "PURCHASE ORDER",
        fontsize=16,
    )
    page.insert_textbox(
        pymupdf.Rect(30, 60, 500, 82),
        "Purchase Order Number: PO-78421",
        fontsize=9,
    )
    page.insert_textbox(
        pymupdf.Rect(30, 85, 500, 107),
        "Order Date: 15-SEP-2026",
        fontsize=9,
    )
    page.insert_textbox(
        pymupdf.Rect(30, 110, 600, 132),
        "Supplier: ACME Components Ltd.",
        fontsize=9,
    )

    draw_table(
        page,
        [30, 125, 315, 415, 485, 585, 700],
        [155, 180, 205, 230, 255, 280, 305],
        rows,
        font_size=6.5,
    )

    page.insert_textbox(
        pymupdf.Rect(430, 330, 700, 355),
        f"Order Total EUR {total:.2f}",
        fontsize=10,
    )

    document.save(output_path)
    document.close()


if __name__ == "__main__":
    main()
