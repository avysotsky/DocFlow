#!/usr/bin/env python3
"""Build the frozen independent purchase-order benchmark for DocFlow v1.1.1.31."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
import urllib.request
from pathlib import Path
from typing import Any

import fitz


SOURCES: list[dict[str, Any]] = [
    {
        "id": "po-holdout-kpmg-p5039687",
        "url": "https://www.contractsfinder.service.gov.uk/Notice/Attachment/c273cef9-41ed-4b4f-894d-aca092187c61",
        "sha256": "5c817c23fe8c1fff944f10443693376fc9a512d78b50f72f7dc5da3392474faa",
        "supplier": "CSL - KPMG LLP",
        "layout_class": "ukhsa-layout-preserved-sparse-priced-line",
        "expected": {
            "document_type": "purchase_order",
            "validation_status": "incomplete",
            "fields": {
                "data.supplier_name": "CSL - KPMG LLP",
                "data.purchase_order_number": "P5039687",
                "data.order_date": "2022-10-06",
                "data.currency": "GBP",
                "data.items.0.description": "Agile Project Management Foundation and Practitioner External Training for",
                "data.items.0.need_by_date": "2022-10-17",
                "data.items.0.unit_price": "48342.00",
                "data.items.0.line_total": "48342.00",
                "data.subtotal": "48342.00",
                "data.total": "48342.00",
            },
        },
    },
    {
        "id": "po-holdout-idexx-p5058264",
        "url": "https://www.contractsfinder.service.gov.uk/Notice/Attachment/24a3df4b-8ab9-46df-a513-f5b163a33470",
        "sha256": "9b409949d7110d505ac8a8d5b7b1f546ab4668fab5450f3cde6753cdf05ef2f8",
        "supplier": "IDEXX LABORATORIES LIMITED",
        "layout_class": "ukhsa-referenced-sparse-line",
        "expected": {
            "document_type": "purchase_order",
            "validation_status": "incomplete",
            "fields": {
                "data.supplier_name": "IDEXX LABORATORIES LIMITED",
                "data.purchase_order_number": "P5058264",
                "data.order_date": "2023-03-09",
                "data.currency": "GBP",
                "data.items.0.supplier_reference": "98-0002570-00",
                "data.items.0.description": "Quanti-Tray Sealer PLUS w/ 1 of each PLUS rubber insert (51 and 97 well) (12 month manufacturer warranty included) Ref: 98-0002570-00",
                "data.items.0.need_by_date": "2023-03-15",
                "data.items.0.quantity": "1",
                "data.items.0.unit": "Each",
                "data.total": "4015.03",
            },
        },
    },
    {
        "id": "po-holdout-minster-p5063409",
        "url": "https://www.contractsfinder.service.gov.uk/Notice/Attachment/1a7ee161-0f02-465b-91c9-c25914408b86",
        "sha256": "46a1e2b225a647bf16af2fda027299e8534ecbbe1519af47ba5cf3273d780677",
        "supplier": "MINSTER CLEANING SERVICES (LEEDS)",
        "layout_class": "ukhsa-layout-preserved-sparse-priced-line",
        "expected": {
            "document_type": "purchase_order",
            "validation_status": "incomplete",
            "fields": {
                "data.supplier_name": "MINSTER CLEANING SERVICES (LEEDS)",
                "data.purchase_order_number": "P5063409",
                "data.order_date": "2023-04-19",
                "data.currency": "GBP",
                "data.items.0.description": "CLEANING SERVICES - OSD, LEEDS",
                "data.items.0.need_by_date": "2023-04-20",
                "data.items.0.unit_price": "22300.00",
                "data.items.0.line_total": "22300.00",
                "data.subtotal": "22300.00",
                "data.total": "22300.00",
            },
        },
    },
    {
        "id": "po-holdout-edwards-2022",
        "url": "https://www.contractsfinder.service.gov.uk/Notice/Attachment/8893d31d-2908-42c4-9b0a-658adccf921b",
        "sha256": "8579a09fe0019ab205900d338cec982032dd5975e7afa87a8df273367d97e733",
        "supplier": "Edwards Ltd",
        "layout_class": "ukri-vertical-net-amount-multiple-lines",
        "expected": {
            "document_type": "purchase_order",
            "validation_status": "incomplete",
            "fields": {
                "data.supplier_name": "Edwards Ltd",
                "data.order_date": "2022-12-22",
                "data.currency": "GBP",
                "data.items.0.line_number": "1",
                "data.items.0.description": "Supplier Item: Vacuum Pump From Quote",
                "data.items.0.need_by_date": "2023-03-01",
                "data.items.0.unit": "Each",
                "data.items.1.line_number": "2",
                "data.items.1.description": "Supplier Item: Vacuum Pump From Quote Freight",
                "data.items.1.need_by_date": "2023-03-01",
                "data.items.1.unit": "Each",
                "data.total": "19485.60",
            },
        },
    },
    {
        "id": "po-holdout-ukri-ukr10015660",
        "url": "https://www.find-tender.service.gov.uk/Notice/Attachment/A-4650",
        "sha256": "5615dc6f7d0a7010ccc028963126e98a11e2c6519edccbced2755fa8ca8a022b",
        "supplier": "Passageways (UK) Ltd (OnBoard)",
        "layout_class": "ukri-vertical-net-amount-single-line",
        "expected": {
            "document_type": "purchase_order",
            "validation_status": "incomplete",
            "fields": {
                "data.supplier_name": "Passageways (UK) Ltd (OnBoard)",
                "data.purchase_order_number": "UKR10015660",
                "data.order_date": "2025-08-19",
                "data.currency": "GBP",
                "data.items.0.line_number": "1",
                "data.items.0.description": "DDaT25311 - Board Paper Management Tool Licences",
                "data.items.0.need_by_date": "2025-07-22",
                "data.items.0.unit_price": "40049.75",
                "data.items.0.line_total": "40049.75",
                "data.total": "48059.70",
            },
        },
    },
]


def download(url: str, target: Path) -> None:
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            request = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 DocFlowPurchaseOrderIndependentBenchmark/1.0",
                    "Accept": "application/pdf,*/*;q=0.8",
                },
            )
            with urllib.request.urlopen(request, timeout=120) as response:
                data = response.read()
            if not data.startswith(b"%PDF"):
                raise ValueError(f"Payload is not a PDF ({len(data)} bytes)")
            target.write_bytes(data)
            return
        except Exception as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(2 ** attempt)
    assert last_error is not None
    raise last_error


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def build(root: Path) -> dict[str, Any]:
    corpus = root / "corpus"
    corpus.mkdir(parents=True, exist_ok=True)

    report: list[dict[str, Any]] = []
    manifest_documents: list[dict[str, Any]] = []

    for source in SOURCES:
        target = corpus / f"{source['id']}.pdf"
        row = {
            "id": source["id"],
            "url": source["url"],
            "expected_sha256": source["sha256"],
        }
        try:
            download(source["url"], target)
            actual_sha256 = digest(target)
            if actual_sha256 != source["sha256"]:
                raise ValueError(
                    "Frozen source SHA-256 changed: "
                    f"expected {source['sha256']}, got {actual_sha256}"
                )

            with fitz.open(target) as pdf:
                native_text_chars = sum(
                    len(page.get_text("text").strip()) for page in pdf
                )
                page_count = pdf.page_count

            manifest_documents.append(
                {
                    "id": source["id"],
                    "file": f"corpus/{target.name}",
                    "sha256": actual_sha256,
                    "metadata": {
                        "supplier": source["supplier"],
                        "source_kind": "digital" if native_text_chars >= 80 else "scanned",
                        "layout_class": source["layout_class"],
                        "language": "en",
                        "tags": [
                            "purchase-order",
                            "independent-holdout",
                            "frozen-ground-truth",
                            "market-driven",
                        ],
                    },
                    "document_type": "auto",
                    "expected": source["expected"],
                }
            )
            row.update(
                {
                    "status": "ok",
                    "pages": page_count,
                    "native_text_chars": native_text_chars,
                    "sha256": actual_sha256,
                }
            )
        except Exception as exc:
            row.update({"status": "error", "error": f"{type(exc).__name__}: {exc}"})
        report.append(row)

    manifest = {"version": 1, "documents": manifest_documents}
    (root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (root / "sources-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    summary = {
        "sources_total": len(report),
        "sources_downloaded": sum(row["status"] == "ok" for row in report),
        "sources_failed": sum(row["status"] != "ok" for row in report),
        "manifest_documents": len(manifest_documents),
    }
    (root / "build-summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--min-documents", type=int, default=5)
    args = parser.parse_args()

    root = Path(args.output).resolve()
    root.mkdir(parents=True, exist_ok=True)
    summary = build(root)
    print(json.dumps(summary, indent=2))
    if summary["manifest_documents"] < args.min_documents:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
