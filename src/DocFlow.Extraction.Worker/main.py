import argparse
import json
from pathlib import Path

from docflow_worker import LocalStorageReader, PdfContentExtractor


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extract layout-aware content from a PDF stored by DocFlow."
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
        help="Optional path where extracted UTF-8 plain text will be written.",
    )
    parser.add_argument(
        "--output-json",
        help="Optional path where full layout-aware DocumentContent JSON will be written.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()

    storage = LocalStorageReader(args.storage_root)
    pdf_path = storage.resolve(args.storage_key)
    content = PdfContentExtractor().extract(pdf_path)

    if args.output_text:
        output_path = Path(args.output_text)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(content.text, encoding="utf-8")

    if args.output_json:
        output_path = Path(args.output_json)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(content.model_dump_json(indent=2), encoding="utf-8")

    summary = {
        "storageKey": args.storage_key,
        "pageCount": content.page_count,
        "pagesWithText": content.pages_with_text,
        "emptyPageNumbers": content.empty_page_numbers,
        "needsOcr": content.needs_ocr,
        "textLength": len(content.text),
        "wordCount": sum(len(page.words) for page in content.pages),
        "blockCount": sum(len(page.blocks) for page in content.pages),
        "tableCount": content.table_count,
        "outputText": args.output_text,
        "outputJson": args.output_json,
    }

    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
