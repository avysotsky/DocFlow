#!/usr/bin/env python3
"""Admit original multi-page public invoices into the temporary benchmark corpus.

These sources are kept separate from the page-selection builder because the whole
supplier document is the benchmark unit. No page may be discarded: continuation
item rows and final-page totals are the behavior under test.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import urllib.request
from pathlib import Path
from typing import Any

import fitz


SOURCE: dict[str, Any] = {
    "id": "casterton-foodworks-invoice-02706",
    "url": "https://www.foodworks.com.au/application/files/6517/1573/6882/tax_invoice_02706.pdf",
    "supplier": "Casterton Foodworks",
    "layout_class": "two-page-continuation-item-table",
    "language": "en-AU",
    "tags": ["multi-page", "continued-item-table", "final-page-totals", "gst"],
    "expected": {
        "document_type": "supplier_invoice",
        "validation_status": "valid",
        "fields": {
            "data.invoice_number": "02706",
            "data.invoice_date": "2024-05-14",
            "data.vat_amount": "5.82",
            "data.total": "255.90",
        },
    },
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_pdf(url: str, target: Path) -> None:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 DocFlowBenchmark/1.0",
            "Accept": "application/pdf,*/*;q=0.8",
        },
    )
    with urllib.request.urlopen(request, timeout=90) as response:
        data = response.read()

    if not data.startswith(b"%PDF"):
        raise ValueError(f"Downloaded payload is not a PDF ({len(data)} bytes)")
    target.write_bytes(data)


def source_kind(document: fitz.Document) -> str:
    pages_with_text = sum(bool(page.get_text("text").strip()) for page in document)
    if pages_with_text == document.page_count:
        return "digital"
    if pages_with_text == 0:
        return "scanned"
    return "mixed"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    args = parser.parse_args()

    root = Path(args.root).resolve()
    corpus_dir = root / "corpus"
    raw_dir = root / "raw"
    manifest_path = root / "manifest.json"
    report_path = root / "sources-report.json"
    summary_path = root / "build-summary.json"

    corpus_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)

    raw_path = raw_dir / f"{SOURCE['id']}.pdf"
    corpus_path = corpus_dir / f"{SOURCE['id']}.pdf"

    download_pdf(SOURCE["url"], raw_path)

    with fitz.open(raw_path) as document:
        if document.page_count < 2:
            raise ValueError(
                f"Expected a genuine multi-page invoice, got {document.page_count} page(s)"
            )

        first_text = document[0].get_text("text")
        last_text = document[-1].get_text("text")
        if "02706" not in first_text or "02706" not in last_text:
            raise ValueError("Invoice 02706 is not identifiable on both boundary pages")
        if "Page 1 of 2" not in first_text or "Page 2 of 2" not in last_text:
            raise ValueError("Expected original two-page continuation markers were not found")
        if "255.90" not in last_text or "5.82" not in last_text:
            raise ValueError("Final-page independently reviewed total/GST markers were not found")

        kind = source_kind(document)
        native_text_chars = sum(len(page.get_text("text").strip()) for page in document)
        page_count = document.page_count

    shutil.copyfile(raw_path, corpus_path)
    digest = sha256(corpus_path)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    documents = [
        document
        for document in manifest.get("documents", [])
        if document.get("id") != SOURCE["id"]
    ]
    documents.append(
        {
            "id": SOURCE["id"],
            "file": f"corpus/{corpus_path.name}",
            "sha256": digest,
            "metadata": {
                "supplier": SOURCE["supplier"],
                "source_kind": kind,
                "layout_class": SOURCE["layout_class"],
                "language": SOURCE["language"],
                "tags": [
                    "public-reference",
                    "original-layout",
                    "runtime-download",
                    *SOURCE["tags"],
                ],
            },
            "document_type": "auto",
            "expected": SOURCE["expected"],
        }
    )
    manifest["documents"] = documents
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    report = json.loads(report_path.read_text(encoding="utf-8"))
    report = [entry for entry in report if entry.get("id") != SOURCE["id"]]
    report.append(
        {
            "id": SOURCE["id"],
            "url": SOURCE["url"],
            "supplier": SOURCE["supplier"],
            "status": "ok",
            "sha256": digest,
            "source_pages": page_count,
            "selected_page_numbers": list(range(1, page_count + 1)),
            "page_selection_method": "whole_original_document",
            "native_text_chars": native_text_chars,
        }
    )
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["sources_total"] = len(report)
    summary["sources_downloaded"] = sum(entry.get("status") == "ok" for entry in report)
    summary["sources_failed"] = summary["sources_total"] - summary["sources_downloaded"]
    summary["manifest_documents"] = len(documents)
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(
        json.dumps(
            {
                "id": SOURCE["id"],
                "pages": page_count,
                "source_kind": kind,
                "sha256": digest,
                "expected": SOURCE["expected"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
