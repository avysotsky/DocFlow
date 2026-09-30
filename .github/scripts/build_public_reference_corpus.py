#!/usr/bin/env python3
"""Build a temporary DocFlow benchmark corpus from publicly accessible supplier PDFs.

The script does not commit third-party PDFs. It downloads them at runtime, extracts the
supplier-invoice page when a source is a larger public meeting/payment pack, computes
SHA-256, and writes a benchmark manifest with independently transcribed ground truth.

Page selection first uses native PDF text. If a public source pack has a broken or
image-only text layer, Tesseract OCR is used only to locate the matching original page.
OCR search is bounded per source so large archive/report PDFs cannot dominate CI time.
The selected page itself is copied unchanged into the benchmark corpus.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import urllib.request
from pathlib import Path
from typing import Any

import fitz


SOURCES: list[dict[str, Any]] = [
    {
        "id": "asar-proforma-pr-46039",
        "url": "https://erp.asar.co.tz/workshop/pdf/PR-46039.pdf",
        "marker": "PROFORMA INVOICE",
        "supplier": "Asar Ltd",
        "layout_class": "single-page-table",
        "expected": {
            "document_type": "supplier_invoice",
            "fields": {
                "data.currency": "TZS",
                "data.subtotal": "60762.71",
                "data.vat_amount": "10937.29",
                "data.total": "71700.00"
            }
        }
    },
    {
        "id": "gastech-tax-invoice-77057631",
        "url": "https://bourtons-cherwell-pc.gov.uk/wp-content/uploads/2025/07/Feb25-meeting-FIN-REP-and-Invoices.pdf",
        "marker": "GAS-TECH HEATING SERVICES",
        "supplier": "Gas-Tech Heating Services (Banbury) Ltd",
        "layout_class": "embedded-in-public-payment-pack",
        "expected": {
            "document_type": "supplier_invoice",
            "fields": {
                "data.invoice_number": "77057631",
                "data.currency": "GBP",
                "data.subtotal": "225.00",
                "data.vat_amount": "45.00",
                "data.total": "270.00"
            }
        }
    },
    {
        "id": "hw-pickrell-proforma-hwi-2403005",
        "url": "https://www.bishopsstortfordtc.gov.uk/sites/default/files/committees/agendas/BZT240325%20Agenda%20and%20Attachments%2025%20Mar%2024.pdf",
        "marker": "H.W. PICKRELL LTD",
        "supplier": "H.W. Pickrell Ltd",
        "layout_class": "embedded-borderless-proforma",
        "expected": {
            "document_type": "supplier_invoice",
            "fields": {
                "data.currency": "GBP",
                "data.subtotal": "37000.00",
                "data.vat_amount": "7400.00",
                "data.total": "44400.00"
            }
        }
    },
    {
        "id": "trea-kids-proforma-1056",
        "url": "https://www.obs.kostinbrod.bg/wp-content/uploads/2025/02/%D0%A2%D0%BE%D1%87%D0%BA%D0%B0-19_%D0%BF%D1%80%D0%B8%D0%BB%D0%BE%D0%B6%D0%B5%D0%BD%D0%B8%D1%8F.pdf",
        "marker": "Trea Kids",
        "supplier": "Trea Kids Danismanlik Anonim Sirketi",
        "layout_class": "embedded-single-page-table",
        "expected": {
            "document_type": "supplier_invoice",
            "fields": {
                "data.invoice_number": "1056",
                "data.currency": "EUR",
                "data.subtotal": "1680.00",
                "data.vat_amount": "336.00",
                "data.total": "2016.00"
            }
        }
    },
    {
        "id": "hcc-solutions-invoice-inv-2180",
        "url": "https://www.kingsthorpe-pc.gov.uk/_webedit/uploaded-files/All%20Files/August%20Payments.pdf",
        "marker": "HCC Solutions Co Ltd",
        "supplier": "HCC Solutions Co Ltd",
        "layout_class": "embedded-xero-style-table",
        "expected": {
            "document_type": "supplier_invoice",
            "fields": {
                "data.invoice_number": "INV-2180",
                "data.currency": "GBP",
                "data.subtotal": "782.88",
                "data.vat_amount": "156.57",
                "data.total": "939.45"
            }
        }
    },
    {
        "id": "soft-tech-proforma-prof005",
        "url": "https://openjicareport.jica.go.jp/pdf/11766748_02.pdf",
        "marker": "Soft-Tech Consultants",
        "supplier": "Soft-Tech Consultants Ltd",
        "layout_class": "embedded-legacy-proforma",
        "ocr_page_limit": 0,
        "expected": {
            "document_type": "supplier_invoice",
            "fields": {
                "data.currency": "USD",
                "data.subtotal": "5814.00",
                "data.vat_amount": "1162.86",
                "data.total": "6976.86"
            }
        }
    },
    {
        "id": "hugofox-invoice-inv-23226",
        "url": "https://www.castlesowerby-pc.gov.uk/shared/attachments.asp?f=f3beb9df-737a-4975-99e8-caf87453dab2.pdf&o=CSPC-meeting-agenda-260326.pdf",
        "marker": "Hugofox Limited",
        "supplier": "Hugofox Limited",
        "layout_class": "embedded-xero-style-table",
        "expected": {
            "document_type": "supplier_invoice",
            "fields": {
                "data.invoice_number": "INV-23226",
                "data.currency": "GBP",
                "data.subtotal": "2.49",
                "data.vat_amount": "0.50",
                "data.total": "2.99"
            }
        }
    },
    {
        "id": "rainfords-farm-invoice-inv-0011",
        "url": "https://www.holmevalleyparishcouncil.gov.uk/wp-content/uploads/2025/02/2024-25-4.-Honley-Business-Association-1.-Christmas-Lights-and-2.-Christmas-Tree-Grant-Evaluation-Form.pdf",
        "marker": "Rainford's Farm Limited",
        "supplier": "Rainford's Farm Limited",
        "layout_class": "embedded-xero-style-table",
        "expected": {
            "document_type": "supplier_invoice",
            "fields": {
                "data.invoice_number": "INV-0011",
                "data.currency": "GBP",
                "data.subtotal": "2080.00",
                "data.vat_amount": "416.00",
                "data.total": "2496.00"
            }
        }
    },
    {
        "id": "mulberry-las-invoice-inv-1021",
        "url": "https://isfieldparishcouncil.gov.uk/wp-content/uploads/2025/05/IPC-Finance-Report-April-2025.pdf",
        "marker": "Mulberry Local Authority",
        "supplier": "Mulberry Local Authority Services Limited",
        "layout_class": "embedded-xero-style-table",
        "expected": {
            "document_type": "supplier_invoice",
            "fields": {
                "data.invoice_number": "INV-1021",
                "data.currency": "GBP",
                "data.subtotal": "210.00",
                "data.vat_amount": "42.00",
                "data.total": "252.00"
            }
        }
    },
    {
        "id": "aa-salt-invoice-inv-7077",
        "url": "https://tibbertonparishcouncil.gov.uk/wp-content/uploads/2025/03/Agenda-2025-03-13-Tibberton-Parish-Council-v.1.pdf",
        "marker": "AA Salt Services",
        "supplier": "AA Salt Services Limited",
        "layout_class": "embedded-xero-style-table",
        "expected": {
            "document_type": "supplier_invoice",
            "fields": {
                "data.invoice_number": "INV-7077",
                "data.currency": "GBP",
                "data.subtotal": "180.00",
                "data.vat_amount": "36.00",
                "data.total": "216.00"
            }
        }
    },
    {
        "id": "jordan-customs-commercial-invoice-2019014782",
        "url": "https://tradeportal.customs.gov.jo/media/%D9%81%D8%A7%D8%AA%D9%88%D8%B1%D8%A9%20%D8%AA%D8%B5%D8%AF%D9%8A%D8%B1%D9%8A%D8%A9%20%D8%BA%D8%B0%D8%A7%D8%A6%D9%8A%D8%A9.pdf",
        "marker": "2019014782",
        "supplier": "Jordan export commercial invoice",
        "layout_class": "bilingual-commercial-invoice",
        "expected": {
            "document_type": "supplier_invoice",
            "fields": {
                "data.invoice_number": "2019014782",
                "data.currency": "USD",
                "data.subtotal": "27372.74",
                "data.total": "28672.74"
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
            "User-Agent": "Mozilla/5.0 DocFlowBenchmark/1.0",
            "Accept": "application/pdf,*/*;q=0.8"
        },
    )
    with urllib.request.urlopen(request, timeout=90) as response:
        data = response.read()
    if not data.startswith(b"%PDF"):
        raise ValueError(f"Downloaded payload is not a PDF ({len(data)} bytes)")
    target.write_bytes(data)


def _normalize_marker_text(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text.casefold()).split())


def _page_ocr_text(page: fitz.Page) -> str:
    if shutil.which("tesseract") is None:
        return ""

    pixmap = page.get_pixmap(
        matrix=fitz.Matrix(1.5, 1.5),
        colorspace=fitz.csGRAY,
        alpha=False,
    )
    completed = subprocess.run(
        ["tesseract", "stdin", "stdout", "-l", "eng", "--psm", "6"],
        input=pixmap.tobytes("png"),
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        timeout=45,
        check=False,
    )
    if completed.returncode != 0:
        return ""
    return completed.stdout.decode("utf-8", errors="replace")


def extract_matching_page(
    source_pdf: Path,
    marker: str,
    target_pdf: Path,
    *,
    ocr_page_limit: int = 30,
) -> dict[str, Any]:
    with fitz.open(source_pdf) as source:
        normalized_marker = _normalize_marker_text(marker)
        matching_pages = [
            index
            for index, page in enumerate(source)
            if normalized_marker in _normalize_marker_text(page.get_text("text"))
        ]
        selection_method = "native_text"
        ocr_pages_checked = 0

        if (
            not matching_pages
            and source.page_count > 1
            and ocr_page_limit > 0
            and shutil.which("tesseract")
        ):
            selection_method = "ocr"
            pages_to_check = min(source.page_count, ocr_page_limit)
            for index in range(pages_to_check):
                page = source[index]
                ocr_pages_checked += 1
                ocr_text = _page_ocr_text(page)
                if normalized_marker in _normalize_marker_text(ocr_text):
                    matching_pages.append(index)
                    break

        if not matching_pages:
            if source.page_count == 1:
                matching_pages = [0]
                selection_method = "single_page_fallback"
            else:
                raise ValueError(
                    f"Marker {marker!r} not found in {source.page_count}-page source PDF "
                    f"after native-text/OCR search ({ocr_pages_checked} OCR pages checked; "
                    f"limit={ocr_page_limit})"
                )

        page_index = matching_pages[0]
        output = fitz.open()
        output.insert_pdf(source, from_page=page_index, to_page=page_index)
        output.save(target_pdf)
        output.close()

        return {
            "source_pages": source.page_count,
            "selected_page_index": page_index,
            "selected_page_number": page_index + 1,
            "matching_pages": [index + 1 for index in matching_pages],
            "page_selection_method": selection_method,
            "ocr_pages_checked": ocr_pages_checked,
            "ocr_page_limit": ocr_page_limit,
        }


def build(output_root: Path) -> dict[str, Any]:
    corpus_dir = output_root / "corpus"
    raw_dir = output_root / "raw"
    corpus_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)

    manifest_documents: list[dict[str, Any]] = []
    source_report: list[dict[str, Any]] = []

    for source in SOURCES:
        raw_path = raw_dir / f"{source['id']}.pdf"
        corpus_path = corpus_dir / f"{source['id']}.pdf"
        report_entry: dict[str, Any] = {
            "id": source["id"],
            "url": source["url"],
            "supplier": source["supplier"],
            "marker": source["marker"]
        }

        try:
            download_pdf(source["url"], raw_path)
            page_info = extract_matching_page(
                raw_path,
                source["marker"],
                corpus_path,
                ocr_page_limit=int(source.get("ocr_page_limit", 30)),
            )
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
                        "source_kind": "digital" if native_text_chars else "scanned",
                        "layout_class": source["layout_class"],
                        "language": "en",
                        "tags": ["public-reference", "original-layout", "runtime-download"]
                    },
                    "document_type": "auto",
                    "expected": source["expected"]
                }
            )
            report_entry.update(
                {
                    "status": "ok",
                    "sha256": digest,
                    "native_text_chars": native_text_chars,
                    **page_info
                }
            )
        except Exception as exc:
            report_entry.update(
                {
                    "status": "error",
                    "error": f"{type(exc).__name__}: {exc}"
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
    failed = len(source_report) - ok
    summary = {
        "sources_total": len(source_report),
        "sources_downloaded": ok,
        "sources_failed": failed,
        "manifest_documents": len(manifest_documents),
        "output_root": str(output_root.resolve())
    }
    (output_root / "build-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--min-documents",
        type=int,
        default=3,
        help="Fail when fewer than this many original public supplier documents were built."
    )
    args = parser.parse_args()

    output_root = Path(args.output).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    summary = build(output_root)
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    if summary["manifest_documents"] < args.min_documents:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
