import argparse
import json
from pathlib import Path

from docflow_worker.corpus_audit import audit_corpus, write_audit_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Audit a private corpus inventory against a benchmark manifest before "
            "running accuracy measurements."
        )
    )
    parser.add_argument("--inventory", required=True, help="Corpus inventory JSON path.")
    parser.add_argument("--manifest", required=True, help="Benchmark manifest JSON path.")
    parser.add_argument("--output", help="Optional JSON audit report path.")
    parser.add_argument(
        "--fail-on-warnings",
        action="store_true",
        help="Return a non-zero exit code when audit warnings are present.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    report = audit_corpus(args.inventory, args.manifest)

    if args.output:
        write_audit_report(report, args.output)

    summary = {
        "inventory": str(Path(args.inventory).resolve()),
        "manifest": str(Path(args.manifest).resolve()),
        "output": str(Path(args.output).resolve()) if args.output else None,
        "errors": report.errors,
        "warnings": report.warnings,
        "inventory_documents": report.inventory_documents,
        "inventory_unique_contents": report.inventory_unique_contents,
        "manifest_documents": report.manifest_documents,
        "represented_unique_contents": report.represented_unique_contents,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    if report.errors:
        raise SystemExit(1)
    if args.fail_on_warnings and report.warnings:
        raise SystemExit(2)
    raise SystemExit(0)


if __name__ == "__main__":
    main()
