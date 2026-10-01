#!/usr/bin/env python3
"""Admit a public French EN16931 multi-VAT invoice sample into the benchmark corpus."""

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
    "id": "facturalex-french-multivat-f20260023",
    "url": "https://www.facturalex.com/files/Facture_F20260023-LE_FOURNISSEUR-POUR-LE_CLIENT_EN_16931.pdf",
    "supplier": "LE FOURNISSEUR (Facturalex EN16931 public sample)",
    "layout_class": "french-en16931-multi-vat-summary",
    "language": "fr-FR",
    "tags": ["multi-vat", "decimal-comma", "french-labels", "zero-rate", "tax-exemption", "standards-public-sample"],
    "expected": {
        "document_type": "supplier_invoice",
        "validation_status": "incomplete",
        "fields": {
            "data.invoice_number": "F20260023",
            "data.currency": "EUR",
            "data.subtotal": "100.00",
            "data.vat_amount": "4.90",
            "data.total": "104.90",
            "data.tax_breakdown.0.category_code": "S",
            "data.tax_breakdown.0.rate": "20.00",
            "data.tax_breakdown.0.taxable_amount": "11.00",
            "data.tax_breakdown.1.category_code": "E",
            "data.tax_breakdown.1.rate": "0.00",
            "data.tax_breakdown.1.taxable_amount": "60.00",
            "data.tax_breakdown.2.category_code": "S",
            "data.tax_breakdown.2.rate": "10.00",
            "data.tax_breakdown.2.taxable_amount": "27.00",
            "data.tax_breakdown.3.category_code": "K",
            "data.tax_breakdown.3.rate": "0.00",
            "data.tax_breakdown.3.taxable_amount": "2.00"
        }
    }
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_pdf(url: str, target: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 DocFlowBenchmark/1.0", "Accept": "application/pdf,*/*;q=0.8"})
    with urllib.request.urlopen(request, timeout=90) as response:
        data = response.read()
    if not data.startswith(b"%PDF"):
        raise ValueError(f"Downloaded payload is not a PDF ({len(data)} bytes)")
    target.write_bytes(data)


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
        if document.page_count != 1:
            raise ValueError(f"Expected one-page EN16931 sample, got {document.page_count} pages")
        text = document[0].get_text("text")
        required_markers = ("F20260023", "TOTAL TVA", "TOTAL TTC", "TOTAL HT", "20,00%", "10,00%", "4,90", "104,90")
        missing = [marker for marker in required_markers if marker not in text]
        if missing:
            raise ValueError(f"French multi-VAT source markers missing: {missing}")
        native_text_chars = len(text.strip())
    shutil.copyfile(raw_path, corpus_path)
    digest = sha256(corpus_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    documents = [document for document in manifest.get("documents", []) if document.get("id") != SOURCE["id"]]
    documents.append({"id": SOURCE["id"], "file": f"corpus/{corpus_path.name}", "sha256": digest, "metadata": {"supplier": SOURCE["supplier"], "source_kind": "digital", "layout_class": SOURCE["layout_class"], "language": SOURCE["language"], "tags": ["public-reference", "original-layout", "runtime-download", *SOURCE["tags"]]}, "document_type": "auto", "expected": SOURCE["expected"]})
    manifest["documents"] = documents
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report = [entry for entry in report if entry.get("id") != SOURCE["id"]]
    report.append({"id": SOURCE["id"], "url": SOURCE["url"], "supplier": SOURCE["supplier"], "status": "ok", "sha256": digest, "source_pages": 1, "selected_page_numbers": [1], "page_selection_method": "whole_original_document", "native_text_chars": native_text_chars})
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["sources_total"] = len(report)
    summary["sources_downloaded"] = sum(entry.get("status") == "ok" for entry in report)
    summary["sources_failed"] = summary["sources_total"] - summary["sources_downloaded"]
    summary["manifest_documents"] = len(documents)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"id": SOURCE["id"], "source_kind": "digital", "sha256": digest, "expected": SOURCE["expected"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
