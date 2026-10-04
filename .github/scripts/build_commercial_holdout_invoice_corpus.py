#!/usr/bin/env python3
"""Build an independent holdout invoice corpus for DocFlow commercial validation.

These documents were selected and ground-truthed only after the first blind corpus
had been frozen. Do not tune extraction rules against this corpus before recording
the first holdout result.
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
        "id": "holdout-terry-griffiths-tgc3795",
        "url": "https://woolhope-pc.gov.uk/wp-content/uploads/2026/01/TGC3795-Drainage-Grant.pdf",
        "pages": [0],
        "supplier": "Terry Griffiths Contracts",
        "layout_class": "quickbooks-activity-single-item",
        "expected": {
            "document_type": "supplier_invoice",
            "fields": {
                "data.invoice_number": "TGC3795",
                "data.invoice_date": "2026-03-16",
                "data.currency": "GBP",
                "data.items.0.description": "Labour, Equipment and Fuel",
                "data.items.0.quantity": "1",
                "data.items.0.unit_price": "1200.00",
                "data.items.0.line_total": "1200.00",
                "data.subtotal": "1200.00",
                "data.vat_amount": "240.00",
                "data.total": "1440.00"
            }
        }
    },
    {
        "id": "holdout-somerset-web-sws110386",
        "url": "https://www.cotford-st-luke.org.uk/wp-content/uploads/2022/07/63.2.5..pdf",
        "pages": [0],
        "supplier": "Somerset Web Services Ltd",
        "layout_class": "quickbooks-activity-vat",
        "expected": {
            "document_type": "supplier_invoice",
            "fields": {
                "data.invoice_number": "SWS110386",
                "data.invoice_date": "2022-07-01",
                "data.due_date": "2022-07-31",
                "data.currency": "GBP",
                "data.items.0.description": "Google G-Suite (Annual) Google G-Suite (Annual) - cotford-st-luke.org.uk",
                "data.items.0.quantity": "10",
                "data.items.0.unit_price": "55.20",
                "data.items.0.line_total": "552.00",
                "data.subtotal": "552.00",
                "data.vat_rate": "20",
                "data.vat_amount": "110.40",
                "data.total": "662.40"
            }
        }
    },
    {
        "id": "holdout-wiltshire-92033500",
        "url": "https://www.bulkingtonparishcouncil.gov.uk/media/Meetings/Agendas/2025/February%2025/9%28i%29%28d%29%20Wiltshire%20Council%20Invoice%2092033500_1.pdf",
        "pages": [0],
        "supplier": "Wiltshire Council",
        "layout_class": "accounts-receivable-zero-vat-table",
        "expected": {
            "document_type": "supplier_invoice",
            "fields": {
                "data.invoice_number": "92033500",
                "data.invoice_date": "2025-01-27",
                "data.due_date": "2025-02-24",
                "data.currency": "GBP",
                "data.items.0.description": "Dropped kerbs at Chestnut Drive & Northfields, Bulkington",
                "data.items.0.quantity": "1.00",
                "data.items.0.unit_price": "1164.74",
                "data.items.0.line_total": "1164.74",
                "data.subtotal": "1164.74",
                "data.vat_rate": "0",
                "data.vat_amount": "0.00",
                "data.total": "1164.74"
            }
        }
    },
    {
        "id": "holdout-zoho-80030622834",
        "url": "https://www.steyningpc.gov.uk/wp-content/uploads/2025/06/Steyning-for-Trees-Newsletter-June-25.pdf",
        "pages": [0],
        "supplier": "ZOHO Corporation Limited",
        "layout_class": "zoho-item-description-table",
        "expected": {
            "document_type": "supplier_invoice",
            "fields": {
                "data.invoice_number": "80030622834",
                "data.invoice_date": "2025-06-26",
                "data.due_date": "2025-06-26",
                "data.currency": "GBP",
                "data.purchase_order_number": "2000941218324",
                "data.items.0.quantity": "1.00",
                "data.items.0.unit_price": "9.20",
                "data.items.0.line_total": "9.20",
                "data.subtotal": "9.20",
                "data.vat_rate": "20",
                "data.vat_amount": "1.84",
                "data.total": "11.04"
            }
        }
    },
    {
        "id": "holdout-signs-workshop-5225",
        "url": "https://www.colwyn-tc.gov.uk/wp-content/uploads/2025/06/General-Purpose-and-Planning-Agenda-17.6.25.pdf",
        "pages": [11],
        "supplier": "Signs Workshop Ltd",
        "layout_class": "quickbooks-activity-two-items",
        "expected": {
            "document_type": "supplier_invoice",
            "fields": {
                "data.invoice_number": "5225",
                "data.invoice_date": "2025-06-04",
                "data.due_date": "2025-07-01",
                "data.currency": "GBP",
                "data.items.0.quantity": "1",
                "data.items.0.unit_price": "720.00",
                "data.items.0.line_total": "720.00",
                "data.items.1.quantity": "1",
                "data.items.1.unit_price": "55.00",
                "data.items.1.line_total": "55.00",
                "data.subtotal": "775.00",
                "data.vat_rate": "20",
                "data.vat_amount": "155.00",
                "data.total": "930.00"
            }
        }
    },
    {
        "id": "holdout-stubbington-12271",
        "url": "https://www.shedfieldparishcouncil.org.uk/Document/Default.aspx?DocumentUid=E01788A9-867B-4296-9EEB-D84A29759CD8",
        "pages": [0],
        "supplier": "P Stubbington Land Surveys Ltd",
        "layout_class": "date-activity-description-vat-qty-rate-amount",
        "expected": {
            "document_type": "supplier_invoice",
            "fields": {
                "data.invoice_number": "12271",
                "data.invoice_date": "2025-05-19",
                "data.due_date": "2025-06-18",
                "data.currency": "GBP",
                "data.items.0.description": "Survey at Shedfield",
                "data.items.0.quantity": "1",
                "data.items.0.unit_price": "400.00",
                "data.items.0.line_total": "400.00",
                "data.subtotal": "400.00",
                "data.vat_rate": "20",
                "data.vat_amount": "80.00",
                "data.total": "480.00"
            }
        }
    },
    {
        "id": "holdout-marcus-young-4733",
        "url": "https://aynho-pc.gov.uk/wp-content/uploads/2025/05/Invoice_4733_from_Marcus_Young_Environmental_Services_Ltd.pdf",
        "pages": [0],
        "supplier": "Marcus Young Environmental Services Ltd",
        "layout_class": "activity-qty-rate-vat-amount",
        "expected": {
            "document_type": "supplier_invoice",
            "fields": {
                "data.invoice_number": "4733",
                "data.invoice_date": "2026-03-01",
                "data.due_date": "2026-03-31",
                "data.currency": "GBP",
                "data.items.0.quantity": "52",
                "data.items.0.unit_price": "21.00",
                "data.items.0.line_total": "1092.00",
                "data.subtotal": "1092.00",
                "data.vat_rate": "20",
                "data.vat_amount": "218.40",
                "data.total": "1310.40"
            }
        }
    },
    {
        "id": "holdout-halc-h1037",
        "url": "https://woolhope-pc.gov.uk/wp-content/uploads/simple-file-list/Meetings/Meetings-2020/9-August-2020/Associated-docs-25_8_2020.pdf",
        "pages": [0],
        "supplier": "Herefordshire Association of Local Councils",
        "layout_class": "classic-vat-column-table",
        "expected": {
            "document_type": "supplier_invoice",
            "fields": {
                "data.invoice_number": "H1037",
                "data.invoice_date": "2020-06-15",
                "data.currency": "GBP",
                "data.items.0.description": "Completion of the Internal Audit for 2019/20",
                "data.items.0.quantity": "1",
                "data.items.0.unit_price": "200.00",
                "data.items.0.line_total": "200.00",
                "data.subtotal": "200.00",
                "data.vat_rate": "20",
                "data.vat_amount": "40.00",
                "data.total": "240.00"
            }
        }
    },
    {
        "id": "holdout-microsoft-gb-ti2505327623",
        "url": "https://www.littlecheverell-pc.gov.uk/shared/attachments.asp?f=8a6953ad-3c33-4b6c-811e-973417eff66b.pdf&o=93%28ii%29%28c%29-G131876810.pdf",
        "pages": [0, 1, 2],
        "supplier": "Microsoft Limited",
        "layout_class": "multi-page-cloud-billing-invoice",
        "expected": {
            "document_type": "supplier_invoice",
            "fields": {
                "data.invoice_number": "GB-TI2505327623",
                "data.invoice_date": "2025-12-29",
                "data.due_date": "2025-12-29",
                "data.currency": "GBP",
                "data.items.0.quantity": "1",
                "data.items.0.unit_price": "10.08",
                "data.items.0.line_total": "10.08",
                "data.subtotal": "10.08",
                "data.vat_rate": "20.00",
                "data.vat_amount": "2.02",
                "data.total": "12.10"
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
            "User-Agent": "Mozilla/5.0 DocFlowCommercialHoldout/1.0",
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
                            "commercial-holdout",
                            "independent-ground-truth",
                            "unseen-before-first-run",
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
    parser.add_argument("--min-documents", type=int, default=8)
    args = parser.parse_args()

    output_root = Path(args.output).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    summary = build(output_root)
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    if summary["manifest_documents"] < args.min_documents:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
