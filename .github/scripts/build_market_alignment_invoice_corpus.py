#!/usr/bin/env python3
"""Build a second independent market-alignment holdout corpus.

These invoices were selected after v1.1.1.29 was frozen, based on fields and
workflow requirements repeatedly present in current invoice-automation jobs.
Ground truth is transcribed from the public source documents before the first run.

Third-party PDFs are downloaded only at workflow runtime and are never committed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import urllib.request
from pathlib import Path
from typing import Any

import fitz


SOURCES: list[dict[str, Any]] = [
    {
        "id": "market-conwy-210395591",
        "url": "https://www.colwyn-tc.gov.uk/wp-content/uploads/2025/06/Council-Agenda-9.6.25-Full-copy.pdf",
        "pages": [138],
        "supplier": "Conwy County Borough Council",
        "layout_class": "bilingual-ar-invoice-single-item",
        "expected": {
            "document_type": "supplier_invoice",
            "fields": {
                "data.invoice_number": "210395591",
                "data.invoice_date": "2025-05-21",
                "data.due_date": "2025-06-04",
                "data.currency": "GBP",
                "data.items.0.description": "Event Support Grant for Prom Xtra 10/05/2025",
                "data.items.0.quantity": "1.00",
                "data.items.0.unit_price": "12733.00",
                "data.items.0.line_total": "12733.00",
                "data.subtotal": "12733.00",
                "data.vat_rate": "20.00",
                "data.vat_amount": "2546.60",
                "data.total": "15279.60"
            }
        }
    },
    {
        "id": "market-team4-37139",
        "url": "https://isfieldparishcouncil.gov.uk/wp-content/uploads/2025/05/IPC-Finance-Report-April-2025.pdf",
        "pages": [15],
        "supplier": "Team 4 Solutions LLP",
        "layout_class": "quickbooks-activity-wrapped-description",
        "expected": {
            "document_type": "supplier_invoice",
            "fields": {
                "data.invoice_number": "37139",
                "data.invoice_date": "2025-03-31",
                "data.due_date": "2025-04-14",
                "data.currency": "GBP",
                "data.items.0.description": "PAYROLLM1 Monthly Payroll & Auto Enrolment Services - 1 Employee",
                "data.items.0.quantity": "1",
                "data.items.0.unit_price": "10.00",
                "data.items.0.line_total": "10.00",
                "data.subtotal": "10.00",
                "data.vat_rate": "20.0",
                "data.vat_amount": "2.00",
                "data.total": "12.00"
            }
        }
    },
    {
        "id": "market-esalc-2031",
        "url": "https://isfieldparishcouncil.gov.uk/wp-content/uploads/2025/05/IPC-Finance-Report-April-2025.pdf",
        "pages": [16],
        "supplier": "ESALC Limited",
        "layout_class": "qty-description-rate-total-zero-vat",
        "expected": {
            "document_type": "supplier_invoice",
            "fields": {
                "data.invoice_number": "2031",
                "data.invoice_date": "2025-04-01",
                "data.due_date": "2025-06-30",
                "data.currency": "GBP",
                "data.items.0.description": "ESALC membership 1st April 2025 - 31st March 2026",
                "data.items.0.quantity": "1",
                "data.items.0.unit_price": "172.01",
                "data.items.0.line_total": "172.01",
                "data.items.1.description": "NALC membership 1st April 2025 - 31st March 2026",
                "data.items.1.quantity": "1",
                "data.items.1.unit_price": "49.62",
                "data.items.1.line_total": "49.62",
                "data.subtotal": "221.63",
                "data.vat_amount": "0.00",
                "data.total": "221.63"
            }
        }
    },
    {
        "id": "market-halc-h5103",
        "url": "https://www.ledburytowncouncil.gov.uk/uploads/Comp-Full-Agenda-20.02.2025.pdf",
        "pages": [80],
        "supplier": "Herefordshire Association of Local Councils",
        "layout_class": "vertical-four-item-vat-table",
        "expected": {
            "document_type": "supplier_invoice",
            "fields": {
                "data.invoice_number": "H5103",
                "data.invoice_date": "2025-02-11",
                "data.currency": "GBP",
                "data.items.0.description": "HALC Affiliation Fee 1st April 2025 to 31st March 2026",
                "data.items.0.quantity": "1",
                "data.items.0.unit_price": "275.00",
                "data.items.0.line_total": "275.00",
                "data.items.1.description": "HALC Subscription Fee 2025/26",
                "data.items.1.quantity": "3000",
                "data.items.1.unit_price": "0.60",
                "data.items.1.line_total": "1800.00",
                "data.items.2.description": "HALC Subscription Fee 2025/26",
                "data.items.2.quantity": "4793",
                "data.items.2.unit_price": "0.04",
                "data.items.2.line_total": "191.72",
                "data.items.3.description": "NALC Subscription Fee 2025/26",
                "data.items.3.quantity": "7793",
                "data.items.3.unit_price": "0.0834",
                "data.items.3.line_total": "649.94",
                "data.subtotal": "2916.66",
                "data.vat_rate": "20.00",
                "data.vat_amount": "583.33",
                "data.total": "3499.99"
            }
        }
    },
    {
        "id": "market-iac-inv1982",
        "url": "https://www.ledburytowncouncil.gov.uk/uploads/ToFollow22May2025.pdf",
        "pages": [33],
        "supplier": "IAC Audit and Consultancy Ltd",
        "layout_class": "line-discount-payment-advice",
        "expected": {
            "document_type": "supplier_invoice",
            "fields": {
                "data.invoice_number": "INV-1982",
                "data.invoice_date": "2025-05-18",
                "data.due_date": "2025-06-02",
                "data.currency": "GBP",
                "data.items.0.description": "Provision of Internal Audit Services - Year End Audit 2024-25",
                "data.items.0.quantity": "1.00",
                "data.items.0.unit_price": "395.00",
                "data.items.0.discount_rate": "5.00",
                "data.items.0.line_total": "375.25",
                "data.subtotal": "375.25",
                "data.vat_rate": "20",
                "data.vat_amount": "75.05",
                "data.total": "450.30"
            }
        }
    }
]


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
            "User-Agent": "Mozilla/5.0 DocFlowMarketAlignmentValidation/1.0",
            "Accept": "application/pdf,*/*;q=0.8",
        },
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        data = response.read()
    if not data.startswith(b"%PDF"):
        raise ValueError(f"Downloaded payload is not a PDF ({len(data)} bytes)")
    target.write_bytes(data)


def extract_pages(source_pdf: Path, page_indexes: list[int], target_pdf: Path) -> dict[str, Any]:
    with fitz.open(source_pdf) as source:
        for page_index in page_indexes:
            if page_index < 0 or page_index >= source.page_count:
                raise ValueError(
                    f"Page index {page_index} is outside source with {source.page_count} pages"
                )

        output = fitz.open()
        for page_index in page_indexes:
            output.insert_pdf(source, from_page=page_index, to_page=page_index)
        output.save(target_pdf)
        output.close()

        return {
            "source_pages": source.page_count,
            "selected_page_indexes": page_indexes,
            "selected_page_numbers": [index + 1 for index in page_indexes],
        }


def build(output_root: Path) -> dict[str, Any]:
    corpus_dir = output_root / "corpus"
    raw_dir = output_root / "raw"
    corpus_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)

    raw_by_url: dict[str, Path] = {}
    documents: list[dict[str, Any]] = []
    report: list[dict[str, Any]] = []

    for source in SOURCES:
        corpus_path = corpus_dir / f"{source['id']}.pdf"
        entry: dict[str, Any] = {
            "id": source["id"],
            "url": source["url"],
            "supplier": source["supplier"],
            "pages": source["pages"],
        }

        try:
            raw_path = raw_by_url.get(source["url"])
            if raw_path is None:
                key = hashlib.sha256(source["url"].encode("utf-8")).hexdigest()[:16]
                raw_path = raw_dir / f"{key}.pdf"
                download_pdf(source["url"], raw_path)
                raw_by_url[source["url"]] = raw_path

            page_info = extract_pages(raw_path, source["pages"], corpus_path)
            digest = sha256(corpus_path)
            with fitz.open(corpus_path) as selected:
                native_text_chars = sum(
                    len(page.get_text("text").strip()) for page in selected
                )

            documents.append(
                {
                    "id": source["id"],
                    "file": f"corpus/{corpus_path.name}",
                    "sha256": digest,
                    "metadata": {
                        "supplier": source["supplier"],
                        "source_kind": "digital" if native_text_chars >= 80 else "scanned",
                        "layout_class": source["layout_class"],
                        "language": "en",
                        "tags": [
                            "market-alignment-holdout",
                            "independent-ground-truth",
                            "selected-after-v1.1.1.29",
                        ],
                    },
                    "document_type": "auto",
                    "expected": source["expected"],
                }
            )
            entry.update(
                {
                    "status": "ok",
                    "sha256": digest,
                    "native_text_chars": native_text_chars,
                    **page_info,
                }
            )
        except Exception as exc:
            entry.update({"status": "error", "error": f"{type(exc).__name__}: {exc}"})

        report.append(entry)

    manifest = {"version": 1, "documents": documents}
    (output_root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output_root / "sources-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    ok = sum(entry["status"] == "ok" for entry in report)
    summary = {
        "sources_total": len(report),
        "sources_downloaded": ok,
        "sources_failed": len(report) - ok,
        "manifest_documents": len(documents),
        "output_root": str(output_root.resolve()),
    }
    (output_root / "build-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--min-documents", type=int, default=5)
    args = parser.parse_args()

    output_root = Path(args.output).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    summary = build(output_root)
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    if summary["manifest_documents"] < args.min_documents:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
