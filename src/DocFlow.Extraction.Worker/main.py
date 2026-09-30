import argparse
import asyncio
import json
from pathlib import Path

from docflow_worker import LocalStorageReader, PdfContentExtractor
from docflow_worker.engines import DeterministicSupplierQuotationEngine


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
    parser.add_argument(
        "--document-type",
        choices=["supplier_quotation"],
        help="Run the currently available deterministic semantic extractor.",
    )
    parser.add_argument(
        "--output-structured-json",
        help="Optional path where StructuredExtractionResult JSON will be written.",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.output_structured_json and not args.document_type:
        parser.error("--output-structured-json requires --document-type")

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

    structured_result = None
    if args.document_type == "supplier_quotation":
        structured_result = asyncio.run(
            DeterministicSupplierQuotationEngine().extract(
                content,
                document_name=args.storage_key,
            )
        )

    if args.output_structured_json and structured_result is not None:
        output_path = Path(args.output_structured_json)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            structured_result.model_dump_json(indent=2),
            encoding="utf-8",
        )

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
        "structuredEngine": (
            structured_result.engine if structured_result is not None else None
        ),
        "structuredDocumentType": (
            structured_result.document_type if structured_result is not None else None
        ),
        "outputStructuredJson": args.output_structured_json,
    }

    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
