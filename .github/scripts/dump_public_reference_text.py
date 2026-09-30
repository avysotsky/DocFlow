#!/usr/bin/env python3
"""Write native-text diagnostics for the temporary public-reference corpus."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import fitz


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    corpus = Path(args.corpus).resolve()
    documents = []

    for pdf_path in sorted(corpus.glob("*.pdf")):
        with fitz.open(pdf_path) as document:
            pages = [page.get_text("text") for page in document]
        text = "\n--- PAGE ---\n".join(pages)
        documents.append(
            {
                "file": pdf_path.name,
                "page_count": len(pages),
                "native_text_chars": len(text.strip()),
                "text": text[:20000],
            }
        )

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps({"documents": documents}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
