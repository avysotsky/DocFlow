from pathlib import Path
import sys

import pymupdf


def main() -> None:
    if len(sys.argv) < 3:
        raise SystemExit("Usage: rasterize_pdf.py <input.pdf> <output.pdf> [dpi]")

    input_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2])
    dpi = int(sys.argv[3]) if len(sys.argv) > 3 else 300

    if dpi <= 0:
        raise SystemExit("DPI must be greater than zero.")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    source = pymupdf.open(input_path)
    scanned = pymupdf.open()

    try:
        for source_page in source:
            pixmap = source_page.get_pixmap(dpi=dpi, alpha=False)
            page = scanned.new_page(
                width=float(source_page.rect.width),
                height=float(source_page.rect.height),
            )
            page.insert_image(page.rect, pixmap=pixmap)

        scanned.save(output_path)
    finally:
        scanned.close()
        source.close()


if __name__ == "__main__":
    main()
