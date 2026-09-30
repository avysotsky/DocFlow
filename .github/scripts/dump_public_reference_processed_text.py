#!/usr/bin/env python3
"""Dump the exact text seen by DocFlow after native extraction/OCR.

This diagnostic intentionally runs the production PdfContentExtractor rather than a
separate OCR command so public-reference failures can be reproduced from the same
DocumentContent that reaches document-type detection and deterministic extraction.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from docflow_worker.pdf_content_extractor import PdfContentExtractor


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    corpus = Path(args.corpus)
    output = Path(args.output)
    extractor = PdfContentExtractor(
        enable_ocr=True,
        ocr_language="eng",
        tessdata=os.environ.get("TESSDATA_PREFIX"),
    )

    documents: list[dict[str, object]] = []
    for pdf_path in sorted(corpus.glob("*.pdf")):
        try:
            content = extractor.extract(pdf_path)
            documents.append(
                {
                    "file": pdf_path.name,
                    "pages": [
                        {
                            "page_number": page.page_number,
                            "ocr_applied": page.ocr_applied,
                            "text": page.text,
                        }
                        for page in content.pages
                    ],
                }
            )
        except Exception as exc:
            documents.append(
                {
                    "file": pdf_path.name,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )

    output.write_text(
        json.dumps({"documents": documents}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
