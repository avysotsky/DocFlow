#!/usr/bin/env python3
"""Add stable public supplier invoices from already-reviewed council packs.

This expansion deliberately reuses a small number of public source packs and selects
separate original invoice pages from them. It reduces network/source churn while adding
unique invoice documents to the public-reference corpus.

Ground truth below was transcribed from the public source pages, independently of
DocFlow output.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import urllib.request
from pathlib import Path
from typing import Any

import fitz


PACK_331 = (
    "https://www.bucklandandchipping-pc.gov.uk/"
    "media/Meetings/Files/331/meeting%20331%20merged%20invoices.pdf"
)
PACK_339 = (
    "https://www.bucklandandchipping-pc.gov.uk/"
    "media/Meetings/Agendas/339%20Agenda%20Parish%20Council%20September%202025%20MERGED.pdf"
)


SOURCES: list[dict[str, Any]] = [
    {
        "id": "ct-gardens-invoice-inv-0055",
        "url": PACK_331,
        "marker": "INV-0055",
        "supplier": "C T Gardens Limited",
        "layout_class": "single-item-no-vat-invoice",
        "expected": {
            "document_type": "supplier_invoice",
            "validation_status": "valid",
            "fields": {
                "data.invoice_number": "INV-0055",
                "data.currency": "GBP",
                "data.subtotal": "190.00",
                "data.vat_amount": "0.00",
                "data.total": "190.00",
            },
        },
    },
    {
        "id": "ct-gardens-invoice-inv-0065",
        "url": PACK_331,
        "marker": "INV-0065",
        "supplier": "C T Gardens Limited",
        "layout_class": "single-item-no-vat-invoice",
        "expected": {
            "document_type": "supplier_invoice",
            "validation_status": "valid",
            "fields": {
                "data.invoice_number": "INV-0065",
                "data.currency": "GBP",
                "data.subtotal": "190.00",
                "data.vat_amount": "0.00",
                "data.total": "190.00",
            },
        },
    },
    {
        "id": "ct-gardens-invoice-inv-0220",
        "url": PACK_339,
        "marker": "INV-0220",
        "supplier": "C T Gardens Limited",
        "layout_class": "single-item-no-vat-invoice",
        "expected": {
            "document_type": "supplier_invoice",
            "validation_status": "valid",
            "fields": {
                "data.invoice_number": "INV-0220",
                "data.currency": "GBP",
                "data.subtotal": "250.00",
                "data.vat_amount": "0.00",
                "data.total": "250.00",
            },
        },
    },
    {
        "id": "teec-invoice-inv-5383",
        "url": PACK_339,
        "marker": "INV-5383",
        "supplier": "TEEC Limited",
        "layout_class": "single-item-xero-style-tax-invoice",
        "expected": {
            "document_type": "supplier_invoice",
            "validation_status": "valid",
            "fields": {
                "data.invoice_number": "INV-5383",
                "data.currency": "GBP",
                "data.subtotal": "30.00",
                "data.vat_amount": "6.00",
                "data.total": "36.00",
            },
        },
    },
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
            "Accept": "application/pdf,*/*;q=0.8",
        },
    )
    with urllib.request.urlopen(request, timeout=90) as response:
        data = response.read()
    if not data.startswith(b"%PDF"):
        raise ValueError(f"Downloaded payload is not a PDF ({len(data)} bytes)")
    target.write_bytes(data)


def normalize(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text.casefold()).split())


def invoice_page_score(text: str) -> int:
    normalized = normalize(text)
    score = 0
    for marker, weight in (
        ("tax invoice", 6),
        ("invoice number", 5),
        ("invoice no", 5),
        ("invoice date", 3),
        ("subtotal", 2),
        ("amount due", 1),
        ("total gbp", 1),
    ):
        if marker in normalized:
            score += weight
    return score


def select_invoice_page(source_pdf: Path, marker: str) -> tuple[int, int]:
    normalized_marker = normalize(marker)
    with fitz.open(source_pdf) as document:
        candidates: list[tuple[int, int]] = []
        for index, page in enumerate(document):
            text = page.get_text("text")
            if normalized_marker in normalize(text):
                candidates.append((invoice_page_score(text), index))

        if not candidates:
            raise ValueError(f"Invoice marker {marker!r} not found in public source pack")

        # Payment schedules can repeat an invoice number. Prefer the candidate that
        # actually looks like an invoice page instead of blindly taking first match.
        candidates.sort(key=lambda pair: (-pair[0], pair[1]))
        best_score, best_index = candidates[0]
        if best_score <= 0:
            raise ValueError(
                f"Marker {marker!r} was found, but no candidate page had invoice signatures"
            )
        return best_index, len(candidates)


def extract_page(source_pdf: Path, page_index: int, target_pdf: Path) -> None:
    with fitz.open(source_pdf) as source:
        output = fitz.open()
        output.insert_pdf(source, from_page=page_index, to_page=page_index)
        output.save(target_pdf)
        output.close()


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

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    documents = list(manifest.get("documents", []))
    report = json.loads(report_path.read_text(encoding="utf-8"))

    cached_packs: dict[str, Path] = {}
    added: list[dict[str, Any]] = []

    for source in SOURCES:
        source_id = source["id"]
        url = source["url"]

        pack_path = cached_packs.get(url)
        if pack_path is None:
            pack_path = raw_dir / f"breadth-pack-{len(cached_packs) + 1}.pdf"
            download_pdf(url, pack_path)
            cached_packs[url] = pack_path

        page_index, candidate_count = select_invoice_page(pack_path, source["marker"])
        corpus_path = corpus_dir / f"{source_id}.pdf"
        extract_page(pack_path, page_index, corpus_path)
        digest = sha256(corpus_path)

        document_entry = {
            "id": source_id,
            "file": f"corpus/{corpus_path.name}",
            "sha256": digest,
            "metadata": {
                "supplier": source["supplier"],
                "source_kind": "digital",
                "layout_class": source["layout_class"],
                "language": "en",
                "tags": [
                    "public-reference",
                    "original-layout",
                    "runtime-download",
                    "corpus-breadth",
                    "shared-source-pack",
                ],
            },
            "document_type": "auto",
            "expected": source["expected"],
        }

        documents = [entry for entry in documents if entry.get("id") != source_id]
        documents.append(document_entry)

        report = [entry for entry in report if entry.get("id") != source_id]
        report_entry = {
            "id": source_id,
            "url": url,
            "supplier": source["supplier"],
            "marker": source["marker"],
            "status": "ok",
            "sha256": digest,
            "source_pages": fitz.open(pack_path).page_count,
            "selected_page_index": page_index,
            "selected_page_number": page_index + 1,
            "matching_pages": candidate_count,
            "page_selection_method": "native_text_invoice_signature_score",
        }
        report.append(report_entry)
        added.append(report_entry)

    manifest["documents"] = documents
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
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
                "added_documents": len(added),
                "manifest_documents": len(documents),
                "source_packs_downloaded": len(cached_packs),
                "documents": added,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
