#!/usr/bin/env python3
"""Build the frozen public purchase-order benchmark corpus for DocFlow v1.1.1.31."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
import urllib.request
from pathlib import Path
from typing import Any

import fitz


def kpmg_fields() -> dict[str, str]:
    delegates = [
        ("Elaine Nock", "2024-03-29"),
        ("Chris Sunny", "2024-03-29"),
        ("Beth MacKenzie", "2024-03-29"),
        ("Ashley McAlister", "2024-03-29"),
        ("Jason Deakin", "2024-03-29"),
        ("Georgina Milne", "2024-03-29"),
        ("Christie Hay", "2023-11-08"),
        ("Samuel Toffa", "2024-03-29"),
        ("Rahul Gupta", "2024-03-29"),
        ("Victoria Adebisi", "2023-11-08"),
        ("Bogumila (Bogusia) Torbus", "2024-03-29"),
        ("Jana Terenova", "2024-03-29"),
        ("Kelly Cawley", "2024-03-29"),
        ("Rachel MacLehose", "2024-03-29"),
    ]
    fields: dict[str, str] = {
        "data.supplier_name": "CSL - KPMG LLP",
        "data.purchase_order_number": "P5084955",
        "data.order_date": "2023-11-03",
        "data.currency": "GBP",
        "data.subtotal": "24108.00",
        "data.total": "24108.00",
    }
    base = (
        "DAS Group - Data Operations - Agile Project Management Foundation & "
        "Practitioner, Duration: 5 days, Method of delivery: Virtual, Delegate: "
    )
    for index, (delegate, need_by) in enumerate(delegates):
        prefix = f"data.items.{index}"
        fields[f"{prefix}.description"] = base + delegate
        fields[f"{prefix}.need_by_date"] = need_by
        fields[f"{prefix}.quantity"] = "1"
        fields[f"{prefix}.unit"] = "Each"
        fields[f"{prefix}.unit_price"] = "1722.00"
        fields[f"{prefix}.line_total"] = "1722.00"
    return fields


SOURCES: list[dict[str, Any]] = [
    {
        "id": "po-kpmg-p5084955",
        "url": "https://www.contractsfinder.service.gov.uk/Notice/Attachment/1af5d30b-0bc3-42b6-9fe1-32787ffe3395",
        "pages": [0, 1, 2, 3, 4],
        "supplier": "CSL - KPMG LLP",
        "layout_class": "ukhsa-multipage-priced-lines",
        "expected": {
            "document_type": "purchase_order",
            "validation_status": "valid",
            "fields": kpmg_fields(),
        },
    },
    {
        "id": "po-hologic-6659000-59",
        "url": "https://www.contractsfinder.service.gov.uk/Notice/Attachment/b22f0dff-befc-40b5-b871-132234e692a4",
        "pages": [71],
        "supplier": "HOLOGIC LTD",
        "layout_class": "ukhsa-single-page-zero-price-lines",
        "expected": {
            "document_type": "purchase_order",
            "validation_status": "valid",
            "fields": {
                "data.supplier_name": "HOLOGIC LTD",
                "data.purchase_order_number": "6659000-59",
                "data.order_date": "2019-10-10",
                "data.currency": "GBP",
                "data.items.0.supplier_reference": "900907",
                "data.items.0.description": "TIGRIS WASTE BAG KIT (PK 10) - FOC",
                "data.items.0.need_by_date": "2019-10-15",
                "data.items.0.quantity": "2",
                "data.items.0.unit": "Pack 10",
                "data.items.0.unit_price": "0.00",
                "data.items.0.line_total": "0.00",
                "data.items.1.supplier_reference": "CL0040",
                "data.items.1.description": "REPLACEMENT CAPS FOR TCR AND SELECT 250 TK (PK 100) - FOC",
                "data.items.1.need_by_date": "2019-10-15",
                "data.items.1.quantity": "2",
                "data.items.1.unit": "Pack 100",
                "data.items.1.unit_price": "0.00",
                "data.items.1.line_total": "0.00",
                "data.subtotal": "0.00",
                "data.total": "0.00",
            },
        },
    },
    {
        "id": "po-cdw-2022",
        "url": "https://www.contractsfinder.service.gov.uk/Notice/Attachment/c877eb6f-9f2d-4342-bc06-5b64fcfe9781",
        "pages": [0],
        "supplier": "CDW LIMITED",
        "layout_class": "ukhsa-sparse-line",
        "expected": {
            "document_type": "purchase_order",
            "validation_status": "incomplete",
            "fields": {
                "data.supplier_name": "CDW LIMITED",
                "data.order_date": "2022-08-23",
                "data.currency": "GBP",
                "data.items.0.description": "100 x GraphPad Prism licences for PHE staff to be recharged back to relevant cost centres.",
                "data.items.0.need_by_date": "2022-08-25",
                "data.items.0.unit": "Each",
                "data.total": "12864.00",
            },
        },
    },
    {
        "id": "po-dale-power-2023",
        "url": "https://www.contractsfinder.service.gov.uk/Notice/Attachment/5e1baf9c-8095-4c70-b380-4b9686381392",
        "pages": [0],
        "supplier": "DALE POWER SOLUTIONS LIMITED",
        "layout_class": "ukhsa-sparse-service-line",
        "expected": {
            "document_type": "purchase_order",
            "validation_status": "incomplete",
            "fields": {
                "data.supplier_name": "DALE POWER SOLUTIONS LIMITED",
                "data.order_date": "2023-02-08",
                "data.currency": "GBP",
                "data.items.0.description": "Dale Power-New UPS and Bypass switch as per OPP105365 (BC, MF) 07/02/2023",
                "data.items.0.need_by_date": "2023-06-15",
                "data.total": "16895.00",
            },
        },
    },
    {
        "id": "po-al-haya-2022",
        "url": "https://www.contractsfinder.service.gov.uk/Notice/Attachment/4513786d-c905-4edb-931c-7cd844e12ba4",
        "pages": [0, 1],
        "supplier": "AL-HAYA MEDICAL COMPANY",
        "layout_class": "ukhsa-multipage-sparse-lines",
        "expected": {
            "document_type": "purchase_order",
            "validation_status": "incomplete",
            "fields": {
                "data.supplier_name": "AL-HAYA MEDICAL COMPANY",
                "data.order_date": "2022-03-31",
                "data.currency": "USD",
                "data.items.0.description": "Polyvalent Scorpion Antivenom (Equine) 1ml/amp",
                "data.items.0.need_by_date": "2022-05-31",
                "data.items.1.description": "Polyvalent Snake Antivenom (Equine) 10ml/amp",
                "data.items.1.need_by_date": "2022-05-31",
                "data.items.2.description": "Shipment charges for antivenoms from Saudi Arabia",
                "data.items.2.need_by_date": "2022-05-31",
                "data.total": "27700.00",
            },
        },
    },
    {
        "id": "po-ukri-help-scout-4070408506",
        "url": "https://www.find-tender.service.gov.uk/Notice/Attachment/A-1418",
        "pages": [0],
        "supplier": "Help Scout PBC",
        "layout_class": "ukri-sparse-net-amount-line",
        "expected": {
            "document_type": "purchase_order",
            "validation_status": "incomplete",
            "fields": {
                "data.supplier_name": "Help Scout PBC",
                "data.purchase_order_number": "4070408506",
                "data.order_date": "2025-05-02",
                "data.currency": "USD",
                "data.items.0.description": "Supplier Item: Help Scout Renewal for Centre for Environmental Data Analysis",
                "data.items.0.unit": "Each",
                "data.items.0.line_total": "15955.20",
                "data.total": "15955.20",
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
                    "User-Agent": "Mozilla/5.0 DocFlowPurchaseOrderBenchmark/1.0",
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


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def select_pages(raw: Path, pages: list[int], output: Path) -> int:
    with fitz.open(raw) as source:
        result = fitz.open()
        for page in pages:
            if page < 0 or page >= source.page_count:
                raise ValueError(f"Page {page} outside source with {source.page_count} pages")
            result.insert_pdf(source, from_page=page, to_page=page)
        result.save(output)
        result.close()
        return source.page_count


def build(root: Path) -> dict[str, Any]:
    corpus = root / "corpus"
    raw_dir = root / "raw"
    corpus.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)

    manifest_documents: list[dict[str, Any]] = []
    report: list[dict[str, Any]] = []

    for source in SOURCES:
        entry = {
            "id": source["id"],
            "url": source["url"],
            "pages": source["pages"],
            "supplier": source["supplier"],
        }
        try:
            raw = raw_dir / f"{source['id']}-raw.pdf"
            selected = corpus / f"{source['id']}.pdf"
            download(source["url"], raw)
            page_count = select_pages(raw, source["pages"], selected)
            digest = sha256(selected)
            with fitz.open(selected) as pdf:
                native_text_chars = sum(
                    len(page.get_text("text").strip()) for page in pdf
                )

            manifest_documents.append(
                {
                    "id": source["id"],
                    "file": f"corpus/{selected.name}",
                    "sha256": digest,
                    "metadata": {
                        "supplier": source["supplier"],
                        "source_kind": "digital" if native_text_chars >= 80 else "scanned",
                        "layout_class": source["layout_class"],
                        "language": "en",
                        "tags": [
                            "purchase-order",
                            "public-benchmark",
                            "market-driven",
                            "independent-ground-truth",
                        ],
                    },
                    "document_type": "auto",
                    "expected": source["expected"],
                }
            )
            entry.update(
                {
                    "status": "ok",
                    "source_page_count": page_count,
                    "sha256": digest,
                    "native_text_chars": native_text_chars,
                }
            )
        except Exception as exc:
            entry.update(
                {"status": "error", "error": f"{type(exc).__name__}: {exc}"}
            )
        report.append(entry)

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
    parser.add_argument("--min-documents", type=int, default=6)
    args = parser.parse_args()

    root = Path(args.output).resolve()
    root.mkdir(parents=True, exist_ok=True)
    summary = build(root)
    print(json.dumps(summary, indent=2))
    if summary["manifest_documents"] < args.min_documents:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
