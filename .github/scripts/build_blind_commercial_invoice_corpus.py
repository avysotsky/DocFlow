#!/usr/bin/env python3
"""Build a blind commercial-style invoice corpus for DocFlow business validation.

The corpus deliberately uses public invoices that are not part of the existing
public-reference benchmark. Ground truth is transcribed independently from the
source invoices before DocFlow output is inspected.

Third-party PDFs are downloaded only at workflow runtime and are never committed.
Selected invoice pages are copied without re-layout.
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
        "id": "blind-diligent-inv307504",
        "url": "https://www.contractsfinder.service.gov.uk/Notice/Attachment/fafd2024-3391-4640-9d71-0095c9da89c6",
        "pages": [0],
        "supplier": "Diligent Boardbooks Limited",
        "layout_class": "single-page-service-table",
        "expected": {
            "document_type": "supplier_invoice",
            "fields": {
                "data.invoice_number": "INV307504",
                "data.invoice_date": "2021-07-16",
                "data.due_date": "2021-08-15",
                "data.currency": "GBP",
                "data.purchase_order_number": "275026403",
                "data.items.0.description": "Sites",
                "data.items.0.quantity": "1",
                "data.items.0.unit_price": "1295.38",
                "data.items.0.line_total": "1295.38",
                "data.items.1.description": "Administrators",
                "data.items.1.quantity": "3",
                "data.items.1.unit_price": "368.13",
                "data.items.1.line_total": "1104.39",
                "data.items.2.description": "Committees- No Charge",
                "data.items.2.quantity": "15",
                "data.items.2.unit_price": "0.00",
                "data.items.2.line_total": "0.00",
                "data.items.3.description": "User (Board Members/Executives)",
                "data.items.3.quantity": "69",
                "data.items.3.unit_price": "368.13",
                "data.items.3.line_total": "25400.97",
                "data.subtotal": "27800.74",
                "data.vat_rate": "20",
                "data.vat_amount": "5560.15",
                "data.total": "33360.89"
            }
        }
    },
    {
        "id": "blind-nuix-inuk03615",
        "url": "https://www.contractsfinder.service.gov.uk/Notice/Attachment/92a5f6b0-16dc-4874-8048-7b7dabd62bc3",
        "pages": [0],
        "supplier": "Nuix Technology UK",
        "layout_class": "single-page-tax-invoice",
        "expected": {
            "document_type": "supplier_invoice",
            "fields": {
                "data.invoice_number": "INUK03615",
                "data.invoice_date": "2020-12-31",
                "data.due_date": "2021-01-30",
                "data.currency": "GBP",
                "data.items.0.description": "eDiscovery Workstation",
                "data.items.0.quantity": "2",
                "data.items.0.line_total": "16317.00",
                "data.subtotal": "16317.00",
                "data.vat_rate": "20.0",
                "data.vat_amount": "3263.40",
                "data.total": "19580.40"
            }
        }
    },
    {
        "id": "blind-brookside-fire-98390",
        "url": "https://www.newfrankleyinbirminghamparishcouncil.gov.uk/wp-content/uploads/2024/04/Finance-report-April-2024.pdf",
        "pages": [13],
        "supplier": "Brookside Fire Service Ltd",
        "layout_class": "embedded-scanned-product-invoice",
        "expected": {
            "document_type": "supplier_invoice",
            "fields": {
                "data.invoice_number": "98390",
                "data.invoice_date": "2024-04-08",
                "data.currency": "GBP",
                "data.items.0.description": "SITE CHARGE",
                "data.items.0.quantity": "1.00",
                "data.items.0.unit_price": "30.00",
                "data.items.0.line_total": "30.00",
                "data.items.1.description": "ALL IN EXTINGUISHER SERVICE",
                "data.items.1.quantity": "4.00",
                "data.items.1.unit_price": "3.75",
                "data.items.1.line_total": "15.00",
                "data.subtotal": "45.00",
                "data.vat_amount": "9.00",
                "data.total": "54.00"
            }
        }
    },
    {
        "id": "blind-scribe-inv5481",
        "url": "https://www.newfrankleyinbirminghamparishcouncil.gov.uk/wp-content/uploads/2024/04/Finance-report-April-2024.pdf",
        "pages": [14],
        "supplier": "Starboard Systems Limited t/a Scribe Accounts",
        "layout_class": "embedded-screen-capture-invoice",
        "expected": {
            "document_type": "supplier_invoice",
            "fields": {
                "data.invoice_number": "INV-5481",
                "data.invoice_date": "2024-02-26",
                "data.due_date": "2024-04-30",
                "data.currency": "GBP",
                "data.items.0.description": "Scribe Accounts Renewal (2024)",
                "data.items.0.quantity": "1.00",
                "data.items.0.unit_price": "345.60",
                "data.items.0.line_total": "345.60",
                "data.subtotal": "345.60",
                "data.vat_rate": "20",
                "data.vat_amount": "69.12",
                "data.total": "414.72"
            }
        }
    },
    {
        "id": "blind-community-heartbeat-20794",
        "url": "https://www.newfrankleyinbirminghamparishcouncil.gov.uk/wp-content/uploads/2024/04/Finance-report-April-2024.pdf",
        "pages": [15],
        "supplier": "The Community HeartBeat Trust (Solutions) Ltd",
        "layout_class": "embedded-scanned-service-invoice",
        "expected": {
            "document_type": "supplier_invoice",
            "fields": {
                "data.invoice_number": "20794",
                "data.invoice_date": "2024-03-26",
                "data.currency": "GBP",
                "data.items.0.quantity": "1.00",
                "data.items.0.unit_price": "135.00",
                "data.items.0.line_total": "135.00",
                "data.subtotal": "135.00",
                "data.vat_rate": "20",
                "data.vat_amount": "27.00",
                "data.total": "162.00"
            }
        }
    },
    {
        "id": "blind-walc-760",
        "url": "https://www.newfrankleyinbirminghamparishcouncil.gov.uk/wp-content/uploads/2024/04/Finance-report-April-2024.pdf",
        "pages": [16],
        "supplier": "Warwickshire & West Midlands ALC Ltd",
        "layout_class": "embedded-scanned-mixed-vat-table",
        "expected": {
            "document_type": "supplier_invoice",
            "fields": {
                "data.invoice_number": "760",
                "data.invoice_date": "2024-04-01",
                "data.due_date": "2024-04-30",
                "data.currency": "GBP",
                "data.items.0.description": "WALC Subs band 18",
                "data.items.0.quantity": "1.00",
                "data.items.0.unit_price": "666.00",
                "data.items.0.line_total": "666.00",
                "data.items.1.description": "NALC subs",
                "data.items.1.quantity": "1.00",
                "data.items.1.unit_price": "430.00",
                "data.items.1.line_total": "430.00",
                "data.subtotal": "1096.00",
                "data.vat_amount": "133.20",
                "data.total": "1229.20"
            }
        }
    },
    {
        "id": "blind-baytree-25591",
        "url": "https://www.shaftesbury-tc.gov.uk/wp-content/uploads/2023-01-17-Invoices-for-approval.pdf",
        "pages": [0],
        "supplier": "The Bay Tree Cleaning Company Ltd",
        "layout_class": "embedded-single-line-vat-invoice",
        "expected": {
            "document_type": "supplier_invoice",
            "fields": {
                "data.invoice_number": "25591",
                "data.invoice_date": "2022-12-31",
                "data.due_date": "2022-12-31",
                "data.currency": "GBP",
                "data.items.0.description": "General cleaning services for December 2022",
                "data.items.0.quantity": "9",
                "data.items.0.unit_price": "16.50",
                "data.items.0.line_total": "148.50",
                "data.subtotal": "148.50",
                "data.vat_rate": "20.0",
                "data.vat_amount": "29.70",
                "data.total": "178.20"
            }
        }
    },
    {
        "id": "blind-clarity-128211",
        "url": "https://www.shaftesbury-tc.gov.uk/wp-content/uploads/2023-01-17-Invoices-for-approval.pdf",
        "pages": [3],
        "supplier": "Clarity Copiers Ltd",
        "layout_class": "embedded-meter-copy-charge",
        "expected": {
            "document_type": "supplier_invoice",
            "fields": {
                "data.invoice_number": "128211",
                "data.invoice_date": "2022-12-29",
                "data.currency": "GBP",
                "data.items.0.description": "Black Pages",
                "data.items.0.quantity": "876",
                "data.items.0.line_total": "4.12",
                "data.items.1.description": "Scans",
                "data.items.1.quantity": "90",
                "data.items.1.line_total": "0.23",
                "data.items.2.description": "Colour Pages",
                "data.items.2.quantity": "414",
                "data.items.2.line_total": "14.99",
                "data.items.3.description": "Colour Scans",
                "data.items.3.quantity": "46",
                "data.items.3.line_total": "0.12",
                "data.subtotal": "19.46",
                "data.vat_rate": "20.00",
                "data.vat_amount": "3.89",
                "data.total": "23.35"
            }
        }
    },
    {
        "id": "blind-cobblebox-inv0503",
        "url": "https://www.shaftesbury-tc.gov.uk/wp-content/uploads/2023-01-17-Invoices-for-approval.pdf",
        "pages": [4],
        "supplier": "Cobblebox LTD",
        "layout_class": "embedded-no-vat-invoice",
        "expected": {
            "document_type": "supplier_invoice",
            "fields": {
                "data.invoice_number": "INV-0503",
                "data.invoice_date": "2022-12-15",
                "data.due_date": "2022-12-15",
                "data.currency": "GBP",
                "data.items.0.description": "150 x tri-fold leaflets",
                "data.items.0.quantity": "1.00",
                "data.items.0.unit_price": "65.00",
                "data.items.0.line_total": "65.00",
                "data.subtotal": "65.00",
                "data.vat_amount": "0.00",
                "data.total": "65.00"
            }
        }
    },
    {
        "id": "blind-melbourn-1622",
        "url": "https://melbournparishcouncil.gov.uk/wp-content/uploads/2022/09/Parish-Council-Minutes-25-July-2022-PDF-Minutes.pdf",
        "pages": [43, 44],
        "supplier": "Melbourn Community Hub",
        "layout_class": "embedded-two-page-mixed-vat-invoice",
        "expected": {
            "document_type": "supplier_invoice",
            "fields": {
                "data.invoice_number": "1622",
                "data.invoice_date": "2022-06-30",
                "data.due_date": "2022-07-30",
                "data.currency": "GBP",
                "data.items.0.quantity": "1",
                "data.items.0.unit_price": "238.83",
                "data.items.0.line_total": "238.83",
                "data.items.1.quantity": "1",
                "data.items.1.unit_price": "34.00",
                "data.items.1.line_total": "34.00",
                "data.items.2.quantity": "1",
                "data.items.2.unit_price": "33.00",
                "data.items.2.line_total": "33.00",
                "data.items.3.quantity": "1",
                "data.items.3.unit_price": "5.95",
                "data.items.3.line_total": "5.95",
                "data.items.4.quantity": "18",
                "data.items.4.unit_price": "25.00",
                "data.items.4.line_total": "450.00",
                "data.items.5.quantity": "1",
                "data.items.5.unit_price": "55.00",
                "data.items.5.line_total": "55.00",
                "data.items.6.quantity": "1",
                "data.items.6.unit_price": "5.95",
                "data.items.6.line_total": "5.95",
                "data.items.7.quantity": "1",
                "data.items.7.unit_price": "150.00",
                "data.items.7.line_total": "150.00",
                "data.items.8.quantity": "1",
                "data.items.8.unit_price": "5.95",
                "data.items.8.line_total": "5.95",
                "data.items.9.quantity": "1",
                "data.items.9.unit_price": "150.00",
                "data.items.9.line_total": "150.00",
                "data.items.10.quantity": "1",
                "data.items.10.unit_price": "80.40",
                "data.items.10.line_total": "80.40",
                "data.items.11.quantity": "1",
                "data.items.11.unit_price": "5.95",
                "data.items.11.line_total": "5.95",
                "data.items.12.quantity": "1",
                "data.items.12.unit_price": "150.00",
                "data.items.12.line_total": "150.00",
                "data.subtotal": "1365.03",
                "data.vat_amount": "65.93",
                "data.total": "1430.96"
            }
        }
    },
    {
        "id": "blind-chris-berwick-2543",
        "url": "https://www.shaftesbury-tc.gov.uk/wp-content/uploads/2023-01-17-Invoices-for-approval.pdf",
        "pages": [1],
        "supplier": "Chris Berwick Ltd",
        "layout_class": "embedded-narrative-vat-invoice",
        "expected": {
            "document_type": "supplier_invoice",
            "fields": {
                "data.invoice_number": "2543",
                "data.invoice_date": "2022-10-01",
                "data.currency": "GBP",
                "data.subtotal": "747.60",
                "data.vat_rate": "20",
                "data.vat_amount": "149.52",
                "data.total": "897.12"
            }
        }
    },
    {
        "id": "blind-cumbria-clock-16624",
        "url": "https://www.shaftesbury-tc.gov.uk/wp-content/uploads/2023-01-17-Invoices-for-approval.pdf",
        "pages": [5],
        "supplier": "The Cumbria Clock Company Ltd",
        "layout_class": "embedded-two-line-service-invoice",
        "expected": {
            "document_type": "supplier_invoice",
            "fields": {
                "data.invoice_number": "16624",
                "data.invoice_date": "2022-12-30",
                "data.due_date": "2023-01-18",
                "data.currency": "GBP",
                "data.items.0.description": "Re:- Shaftesbury Town Hall Clock",
                "data.items.0.quantity": "1.00",
                "data.items.0.unit_price": "0.00",
                "data.items.0.line_total": "0.00",
                "data.items.1.description": "To servicing the above clock on 19th December 2022",
                "data.items.1.quantity": "1.00",
                "data.items.1.unit_price": "150.00",
                "data.items.1.line_total": "150.00",
                "data.subtotal": "150.00",
                "data.vat_rate": "20.00",
                "data.vat_amount": "30.00",
                "data.total": "180.00"
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
            "User-Agent": "Mozilla/5.0 DocFlowBlindCommercialBenchmark/1.0",
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
    manifest_documents: list[dict[str, Any]] = []
    source_report: list[dict[str, Any]] = []

    for source in SOURCES:
        corpus_path = corpus_dir / f"{source['id']}.pdf"
        report_entry: dict[str, Any] = {
            "id": source["id"],
            "url": source["url"],
            "supplier": source["supplier"],
            "pages": source["pages"],
        }

        try:
            raw_path = raw_by_url.get(source["url"])
            if raw_path is None:
                url_key = hashlib.sha256(source["url"].encode("utf-8")).hexdigest()[:16]
                raw_path = raw_dir / f"{url_key}.pdf"
                download_pdf(source["url"], raw_path)
                raw_by_url[source["url"]] = raw_path

            page_info = extract_pages(raw_path, source["pages"], corpus_path)
            digest = sha256(corpus_path)
            with fitz.open(corpus_path) as selected:
                native_text_chars = sum(
                    len(page.get_text("text").strip()) for page in selected
                )

            manifest_documents.append(
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
                            "blind-commercial-validation",
                            "independent-ground-truth",
                            "runtime-download",
                        ],
                    },
                    "document_type": "auto",
                    "expected": source["expected"],
                }
            )
            report_entry.update(
                {
                    "status": "ok",
                    "sha256": digest,
                    "native_text_chars": native_text_chars,
                    **page_info,
                }
            )
        except Exception as exc:
            report_entry.update(
                {
                    "status": "error",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )

        source_report.append(report_entry)

    manifest = {"version": 1, "documents": manifest_documents}
    (output_root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output_root / "sources-report.json").write_text(
        json.dumps(source_report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    ok = sum(entry["status"] == "ok" for entry in source_report)
    summary = {
        "sources_total": len(source_report),
        "sources_downloaded": ok,
        "sources_failed": len(source_report) - ok,
        "manifest_documents": len(manifest_documents),
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
