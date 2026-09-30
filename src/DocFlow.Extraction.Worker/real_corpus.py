import argparse
import asyncio
import json
from pathlib import Path

from docflow_worker.benchmarking import run_benchmark
from docflow_worker.corpus_audit import audit_corpus, write_audit_report
from docflow_worker.corpus_inventory import build_corpus_inventory


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the complete local DocFlow real-corpus workflow: inventory, audit, "
            "then benchmark when the corpus/manifest are consistent."
        )
    )
    parser.add_argument(
        "--corpus",
        required=True,
        help="Directory containing private supplier PDFs.",
    )
    parser.add_argument(
        "--manifest",
        required=True,
        help="Local benchmark manifest containing independent ground truth.",
    )
    parser.add_argument(
        "--results",
        required=True,
        help="Directory where inventory, audit and benchmark reports are written.",
    )
    parser.add_argument(
        "--fail-on-warnings",
        action="store_true",
        help="Do not benchmark when the corpus audit contains warnings.",
    )
    parser.add_argument(
        "--disable-ocr",
        action="store_true",
        help="Disable OCR for pages without native PDF text.",
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

    corpus_path = Path(args.corpus).resolve()
    manifest_path = Path(args.manifest).resolve()
    results_path = Path(args.results).resolve()
    results_path.mkdir(parents=True, exist_ok=True)

    inventory_path = results_path / "corpus-inventory.json"
    audit_path = results_path / "corpus-audit.json"
    benchmark_path = results_path / "benchmark-report.json"

    inventory = build_corpus_inventory(corpus_path)
    inventory_path.write_text(
        inventory.model_dump_json(indent=2),
        encoding="utf-8",
    )

    if inventory.errors:
        print(
            json.dumps(
                {
                    "stage": "inventory",
                    "status": "failed",
                    "errors": inventory.errors,
                    "duplicates": inventory.duplicates,
                    "inventory": str(inventory_path),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        raise SystemExit(2)

    audit = audit_corpus(inventory_path, manifest_path)
    write_audit_report(audit, audit_path)

    if audit.errors or (args.fail_on_warnings and audit.warnings):
        print(
            json.dumps(
                {
                    "stage": "audit",
                    "status": "failed",
                    "errors": audit.errors,
                    "warnings": audit.warnings,
                    "inventory": str(inventory_path),
                    "audit": str(audit_path),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        raise SystemExit(3)

    benchmark = asyncio.run(
        run_benchmark(
            manifest_path,
            output_path=benchmark_path,
            enable_ocr=not args.disable_ocr,
            ocr_language=args.ocr_language,
            ocr_dpi=args.ocr_dpi,
            tessdata=args.tessdata,
        )
    )

    print(
        json.dumps(
            {
                "stage": "benchmark",
                "status": (
                    "passed" if benchmark.metrics.documents_failed == 0 else "failed"
                ),
                "inventory": str(inventory_path),
                "audit": str(audit_path),
                "benchmark": str(benchmark_path),
                **benchmark.metrics.model_dump(mode="json"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )

    raise SystemExit(0 if benchmark.metrics.documents_failed == 0 else 1)


if __name__ == "__main__":
    main()
