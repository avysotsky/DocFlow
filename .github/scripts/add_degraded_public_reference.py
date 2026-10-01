#!/usr/bin/env python3
"""Admit a visibly degraded public reproduction of a real supplier invoice.

The source is a JPEG reproduction of a Biffa Waste Services invoice to Wirral Council
published in 2014 in a public-accountability article. It is not hosted by Wirral Council,
so provenance is recorded explicitly and it must not be described as an official council
hosted source.

The original JPEG bytes are preserved as the source artifact. A one-page PDF wrapper is
created only because DocFlow's current ingestion contract is PDF-based; no cleanup,
thresholding, deskewing, denoising, resampling, or OCR is performed by this acquisition
script.

Ground truth was transcribed from the visible source invoice before DocFlow processing.
The expected DocFlow validation status is ``incomplete`` because the scan does not expose
reliable quantity/unit-price columns for independent line-total and subtotal validation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import urllib.request
from pathlib import Path
from typing import Any

import fitz


SOURCE: dict[str, Any] = {
    "id": "biffa-wirral-invoice-wir00286",
    "image_url": (
        "https://johnbrace.files.wordpress.com/2014/09/"
        "biffa-waste-service-limited-december-2013-invoice-wirral-council-c2a31032201-28.jpg"
    ),
    "provenance_url": (
        "https://johnbrace.com/biffa-asks-wirrals-cabinet-for-a-10-year-extension-"
        "to-bins-street-cleaning-contract-worth-at-least-120-million/"
    ),
    "supplier": "Biffa Waste Services Ltd",
    "customer": "Wirral Council",
    "layout_class": "degraded-grayscale-photocopy-scan",
    "language": "en-GB",
    "expected": {
        "document_type": "supplier_invoice",
        "validation_status": "incomplete",
        "fields": {
            "data.invoice_number": "WIR00286",
            "data.invoice_date": "2013-12-18",
            "data.currency": "GBP",
            "data.subtotal": "860167.73",
            "data.vat_rate": "20",
            "data.vat_amount": "172033.55",
            "data.total": "1032201.28",
        },
    },
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_image(url: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 DocFlowBenchmark/1.0",
            "Accept": "image/avif,image/webp,image/apng,image/jpeg,image/*,*/*;q=0.8",
            "Referer": SOURCE["provenance_url"],
        },
    )
    with urllib.request.urlopen(request, timeout=90) as response:
        data = response.read()
        content_type = response.headers.get("Content-Type", "")
    if len(data) < 10_000:
        raise ValueError(f"Degraded source image is unexpectedly small ({len(data)} bytes)")
    if not (data.startswith(b"\xff\xd8\xff") or "jpeg" in content_type.lower()):
        raise ValueError(f"Expected JPEG source, got Content-Type {content_type!r}")
    return data


def wrap_jpeg_as_pdf(image_bytes: bytes, target: Path) -> tuple[int, int]:
    """Wrap the original JPEG in PDF without visual preprocessing."""
    image_document = fitz.open(stream=image_bytes, filetype="jpeg")
    try:
        page = image_document[0]
        width = int(round(page.rect.width))
        height = int(round(page.rect.height))
        pdf_bytes = image_document.convert_to_pdf()
    finally:
        image_document.close()

    pdf_document = fitz.open("pdf", pdf_bytes)
    try:
        if pdf_document.page_count != 1:
            raise ValueError(f"Expected one wrapped page, got {pdf_document.page_count}")
        # The wrapper must remain image-only before DocFlow's OCR stage.
        if pdf_document[0].get_text("text").strip():
            raise ValueError("Wrapped degraded source unexpectedly contains native PDF text")
        pdf_document.save(target)
    finally:
        pdf_document.close()
    return width, height


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

    image_bytes = download_image(SOURCE["image_url"])
    image_sha = sha256_bytes(image_bytes)
    raw_path = raw_dir / f"{SOURCE['id']}.jpg"
    raw_path.write_bytes(image_bytes)

    corpus_path = corpus_dir / f"{SOURCE['id']}.pdf"
    width, height = wrap_jpeg_as_pdf(image_bytes, corpus_path)
    pdf_sha = sha256(corpus_path)

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
            "sha256": pdf_sha,
            "metadata": {
                "supplier": SOURCE["supplier"],
                "customer": SOURCE["customer"],
                "source_kind": "scanned",
                "source_format": "jpeg",
                "original_source_kind": "scanned-image",
                "source_image_sha256": image_sha,
                "source_url": SOURCE["image_url"],
                "provenance_url": SOURCE["provenance_url"],
                "provenance_note": "public reproduction; not official council-hosted source",
                "pdf_wrapper": "lossless ingestion wrapper around original image; no preprocessing",
                "layout_class": SOURCE["layout_class"],
                "language": SOURCE["language"],
                "tags": [
                    "public-reference",
                    "real-invoice",
                    "degraded-ocr",
                    "grayscale",
                    "photocopy-noise",
                    "low-contrast",
                    "image-only",
                    "public-reproduction",
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
            "url": SOURCE["image_url"],
            "provenance_url": SOURCE["provenance_url"],
            "supplier": SOURCE["supplier"],
            "status": "ok",
            "source_kind": "scanned",
            "original_source_kind": "scanned-image",
            "source_format": "jpeg",
            "source_image_sha256": image_sha,
            "sha256": pdf_sha,
            "source_pages": 1,
            "selected_page_numbers": [1],
            "page_selection_method": "whole_public_image_wrapped_for_pdf_ingestion",
            "image_width": width,
            "image_height": height,
            "preprocessing": "none",
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
                "source_kind": "scanned",
                "original_source_kind": "scanned-image",
                "source_image_sha256": image_sha,
                "pdf_sha256": pdf_sha,
                "image_size": [width, height],
                "preprocessing": "none",
                "expected": SOURCE["expected"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
