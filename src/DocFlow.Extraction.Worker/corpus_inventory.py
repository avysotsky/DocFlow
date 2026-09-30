import argparse
import json
from pathlib import Path

from docflow_worker.corpus_inventory import build_corpus_inventory


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Inventory a local/private PDF corpus without extracting business fields. "
            "Reports hashes, sizes, page counts, native-text coverage and duplicates."
        )
    )
    parser.add_argument(
        "--corpus",
        required=True,
        help="Directory containing the private supplier PDF corpus.",
    )
    parser.add_argument(
        "--output",
        help="Optional JSON inventory output path.",
    )
    parser.add_argument(
        "--fail-on-duplicates",
        action="store_true",
        help="Return a non-zero exit code when duplicate PDF contents are detected.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()

    inventory = build_corpus_inventory(args.corpus)

    if args.output:
        output_path = Path(args.output).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            inventory.model_dump_json(indent=2),
            encoding="utf-8",
        )

    summary = {
        "corpus": str(Path(args.corpus).resolve()),
        "output": str(Path(args.output).resolve()) if args.output else None,
        "documents_total": inventory.documents_total,
        "unique_contents": inventory.unique_contents,
        "duplicates": inventory.duplicates,
        "errors": inventory.errors,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    if inventory.errors > 0:
        raise SystemExit(1)

    if args.fail_on_duplicates and inventory.duplicates > 0:
        raise SystemExit(2)

    raise SystemExit(0)


if __name__ == "__main__":
    main()
