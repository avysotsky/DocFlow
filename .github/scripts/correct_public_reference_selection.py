#!/usr/bin/env python3
"""Correct source-specific page selection mistakes in the public reference corpus.

The public source packs can contain several unrelated supplier documents. A broad
supplier marker may select the wrong page, and a marker on page one of a multi-page
invoice can accidentally discard later totals. This script applies independently
verified source-level selection rules before the benchmark is run:

* Trea Kids: select the page containing invoice number 1056, not an earlier OFFER
  page that merely contains the supplier name.
* Jordan commercial invoice 2019014782: retain the complete two-page original so
  totals on page two remain part of the document under test.

The third-party PDFs remain runtime-only CI artifacts and are not committed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path

import pymupdf


TREA_ID = "trea-kids-proforma-1056"
JORDAN_ID = "jordan-customs-commercial-invoice-2019014782"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text.casefold()).split())


def page_text_with_ocr(page: pymupdf.Page) -> str:
    native = page.get_text("text", sort=True).strip()
    if native:
        return native

    textpage = page.get_textpage_ocr(
        language="eng",
        dpi=200,
        full=True,
        tessdata=os.environ.get("TESSDATA_PREFIX"),
    )
    return page.get_text("text", sort=True, textpage=textpage).strip()


def select_page_containing(source_pdf: Path, target_pdf: Path, marker: str) -> int:
    normalized_marker = normalize(marker)
    with pymupdf.open(source_pdf) as source:
        for index, page in enumerate(source):
            if normalized_marker in normalize(page_text_with_ocr(page)):
                output = pymupdf.open()
                output.insert_pdf(source, from_page=index, to_page=index)
                output.save(target_pdf)
                output.close()
                return index

    raise ValueError(f"Marker {marker!r} not found in {source_pdf.name}")


def copy_complete_document(source_pdf: Path, target_pdf: Path) -> int:
    with pymupdf.open(source_pdf) as source:
        output = pymupdf.open()
        output.insert_pdf(source)
        output.save(target_pdf)
        output.close()
        return source.page_count


def update_manifest_sha(manifest: dict, document_id: str, corpus_path: Path) -> None:
    for document in manifest.get("documents", []):
        if document.get("id") == document_id:
            document["sha256"] = sha256(corpus_path)
            return
    raise ValueError(f"Document {document_id!r} is missing from manifest")


def update_source_report(report: list[dict], document_id: str, **values: object) -> None:
    for entry in report:
        if entry.get("id") == document_id:
            entry.update(values)
            entry["sha256"] = values.get("sha256", entry.get("sha256"))
            return


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    args = parser.parse_args()

    root = Path(args.root).resolve()
    raw_dir = root / "raw"
    corpus_dir = root / "corpus"
    manifest_path = root / "manifest.json"
    sources_report_path = root / "sources-report.json"

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    source_report = json.loads(sources_report_path.read_text(encoding="utf-8"))

    trea_raw = raw_dir / f"{TREA_ID}.pdf"
    trea_corpus = corpus_dir / f"{TREA_ID}.pdf"
    if trea_raw.is_file() and trea_corpus.is_file():
        page_index = select_page_containing(trea_raw, trea_corpus, "1056")
        update_manifest_sha(manifest, TREA_ID, trea_corpus)
        update_source_report(
            source_report,
            TREA_ID,
            sha256=sha256(trea_corpus),
            selected_page_index=page_index,
            selected_page_number=page_index + 1,
            matching_pages=[page_index + 1],
            page_selection_method="ocr_invoice_number_override",
        )

    jordan_raw = raw_dir / f"{JORDAN_ID}.pdf"
    jordan_corpus = corpus_dir / f"{JORDAN_ID}.pdf"
    if jordan_raw.is_file() and jordan_corpus.is_file():
        page_count = copy_complete_document(jordan_raw, jordan_corpus)
        update_manifest_sha(manifest, JORDAN_ID, jordan_corpus)
        update_source_report(
            source_report,
            JORDAN_ID,
            sha256=sha256(jordan_corpus),
            selected_page_index=0,
            selected_page_number=1,
            matching_pages=list(range(1, page_count + 1)),
            page_selection_method="complete_multi_page_invoice",
            selected_page_count=page_count,
        )

    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    sources_report_path.write_text(
        json.dumps(source_report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
