import argparse
import asyncio
import json
from pathlib import Path

from docflow_worker import LocalStorageReader, PdfContentExtractor
from docflow_worker.engines import DeterministicSupplierQuotationEngine
from docflow_worker.supplier_quotation_models import SupplierQuotationData
from docflow_worker.validators import SupplierQuotationValidator


OUTPUT_DIR = Path(__file__).resolve().parent / "output"


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
        help=(
            "Optional path where extracted UTF-8 plain text will be written. "
            "A simple file name is written under the worker output directory."
        ),
    )
    parser.add_argument(
        "--output-json",
        help=(
            "Optional path where full layout-aware DocumentContent JSON will be written. "
            "A simple file name is written under the worker output directory."
        ),
    )
    parser.add_argument(
        "--document-type",
        choices=["supplier_quotation"],
        help="Run the currently available deterministic semantic extractor.",
    )
    parser.add_argument(
        "--output-structured-json",
        help=(
            "Optional path where StructuredExtractionResult JSON will be written. "
            "A simple file name is written under the worker output directory."
        ),
    )
    return parser


def resolve_output_path(value: str) -> Path:
    path = Path(value)

    if path.is_absolute() or path.parent != Path("."):
        return path

    return OUTPUT_DIR / path.name


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.output_structured_json and not args.document_type:
        parser.error("--output-structured-json requires --document-type")

    storage = LocalStorageReader(args.storage_root)
    pdf_path = storage.resolve(args.storage_key)
    content = PdfContentExtractor().extract(pdf_path)

    output_text_path = None
    if args.output_text:
        output_text_path = resolve_output_path(args.output_text)
        output_text_path.parent.mkdir(parents=True, exist_ok=True)
        output_text_path.write_text(content.text, encoding="utf-8")

    output_json_path = None
    if args.output_json:
        output_json_path = resolve_output_path(args.output_json)
        output_json_path.parent.mkdir(parents=True, exist_ok=True)
        output_json_path.write_text(content.model_dump_json(indent=2), encoding="utf-8")

    structured_result = None
    if args.document_type == "supplier_quotation":
        structured_result = asyncio.run(
            DeterministicSupplierQuotationEngine().extract(
                content,
                document_name=args.storage_key,
            )
        )

        quotation = SupplierQuotationData.model_validate(structured_result.data)
        validation = SupplierQuotationValidator().validate(quotation)
        structured_result.validation_status = validation.status
        structured_result.validation = validation
        structured_result.confidence = validation.confidence

    output_structured_json_path = None
    if args.output_structured_json and structured_result is not None:
        output_structured_json_path = resolve_output_path(args.output_structured_json)
        output_structured_json_path.parent.mkdir(parents=True, exist_ok=True)
        output_structured_json_path.write_text(
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
        "outputText": str(output_text_path) if output_text_path else None,
        "outputJson": str(output_json_path) if output_json_path else None,
        "structuredEngine": (
            structured_result.engine if structured_result is not None else None
        ),
        "structuredDocumentType": (
            structured_result.document_type if structured_result is not None else None
        ),
        "validationStatus": (
            structured_result.validation_status if structured_result is not None else None
        ),
        "confidence": (
            structured_result.confidence if structured_result is not None else None
        ),
        "outputStructuredJson": (
            str(output_structured_json_path) if output_structured_json_path else None
        ),
    }

    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
