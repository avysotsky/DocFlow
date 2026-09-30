import argparse
import asyncio
import json
from pathlib import Path

from docflow_worker.benchmarking import run_benchmark


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Benchmark the current DocFlow deterministic+OCR extraction pipeline "
            "against a local manifest of supplier documents."
        )
    )
    parser.add_argument(
        "--manifest",
        required=True,
        help="Path to the benchmark manifest JSON file.",
    )
    parser.add_argument(
        "--output",
        help="Optional JSON report path.",
    )
    parser.add_argument(
        "--disable-ocr",
        action="store_true",
        help="Do not OCR pages without native text.",
    )
    parser.add_argument(
        "--ocr-language",
        default="eng",
        help="Tesseract language code(s). Default: eng.",
    )
    parser.add_argument(
        "--ocr-dpi",
        type=int,
        default=300,
        help="OCR resolution. Default: 300 DPI.",
    )
    parser.add_argument(
        "--tessdata",
        help="Optional explicit path to the Tesseract tessdata directory.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()

    report = asyncio.run(
        run_benchmark(
            args.manifest,
            output_path=args.output,
            enable_ocr=not args.disable_ocr,
            ocr_language=args.ocr_language,
            ocr_dpi=args.ocr_dpi,
            tessdata=args.tessdata,
        )
    )

    summary = {
        "manifest": str(Path(args.manifest).resolve()),
        "output": str(Path(args.output).resolve()) if args.output else None,
        **report.metrics.model_dump(mode="json"),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    raise SystemExit(0 if report.metrics.documents_failed == 0 else 1)


if __name__ == "__main__":
    main()
