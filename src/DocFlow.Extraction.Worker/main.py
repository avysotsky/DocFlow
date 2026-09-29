import argparse
import json
from pathlib import Path

from docflow_worker import LocalStorageReader, PdfTextExtractor


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extract embedded text from a PDF stored by DocFlow."
    )
    parser.add_argument(
        "--storage-root",
        required=True,
        help="Root directory used by DocFlow local file storage.",
    )
    parser.add_argument(
        "--storage-key",
        required=True,
        help="StorageKey value from the Documents table.",
    )
    parser.add_argument(
        "--output-text",
        help="Optional path where extracted UTF-8 text will be written.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()

    storage = LocalStorageReader(args.storage_root)
    pdf_path = storage.resolve(args.storage_key)
    result = PdfTextExtractor().extract(pdf_path)

    if args.output_text:
        output_path = Path(args.output_text)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(result.text, encoding="utf-8")

    summary = {
        "storageKey": args.storage_key,
        "pageCount": result.page_count,
        "pagesWithText": result.pages_with_text,
        "emptyPageNumbers": result.empty_page_numbers,
        "needsOcr": result.needs_ocr,
        "textLength": len(result.text),
        "outputText": args.output_text,
    }

    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
