#!/usr/bin/env python3
"""Download a fresh public purchase-order discovery corpus.

The documents are intentionally kept outside the repository. This first discovery
stage captures text/layout before ground truth is frozen, so PO extraction rules are
not tuned from search snippets alone.
"""

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
        "id": "po-kpmg-p5084955",
        "url": "https://www.contractsfinder.service.gov.uk/Notice/Attachment/1af5d30b-0bc3-42b6-9fe1-32787ffe3395",
        "supplier": "CSL - KPMG LLP",
    },
    {
        "id": "po-hologic-6659000-59",
        "url": "https://www.contractsfinder.service.gov.uk/Notice/Attachment/b22f0dff-befc-40b5-b871-132234e692a4",
        "supplier": "HOLOGIC LTD",
    },
    {
        "id": "po-dale-power-2023",
        "url": "https://www.contractsfinder.service.gov.uk/Notice/Attachment/5e1baf9c-8095-4c70-b380-4b9686381392",
        "supplier": "DALE POWER SOLUTIONS LIMITED",
    },
    {
        "id": "po-cdw-2022",
        "url": "https://www.contractsfinder.service.gov.uk/Notice/Attachment/c877eb6f-9f2d-4342-bc06-5b64fcfe9781",
        "supplier": "CDW LIMITED",
    },
    {
        "id": "po-al-haya-2022",
        "url": "https://www.contractsfinder.service.gov.uk/Notice/Attachment/4513786d-c905-4edb-931c-7cd844e12ba4",
        "supplier": "AL-HAYA MEDICAL COMPANY",
    },
    {
        "id": "po-ukri-help-scout-4070408506",
        "url": "https://www.find-tender.service.gov.uk/Notice/Attachment/A-1418",
        "supplier": "Help Scout PBC",
    },
]


def _download(url: str, target: Path) -> None:
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            request = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 DocFlowPurchaseOrderDiscovery/1.0",
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


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build(output_root: Path) -> dict[str, Any]:
    corpus = output_root / "corpus"
    corpus.mkdir(parents=True, exist_ok=True)

    report: list[dict[str, Any]] = []
    for source in SOURCES:
        target = corpus / f"{source['id']}.pdf"
        entry = dict(source)
        try:
            _download(source["url"], target)
            with fitz.open(target) as pdf:
                entry.update(
                    {
                        "status": "ok",
                        "pages": pdf.page_count,
                        "native_text_chars": sum(
                            len(page.get_text("text").strip()) for page in pdf
                        ),
                        "sha256": _sha256(target),
                    }
                )
        except Exception as exc:
            entry.update(
                {
                    "status": "error",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
        report.append(entry)

    summary = {
        "sources_total": len(report),
        "sources_downloaded": sum(row["status"] == "ok" for row in report),
        "sources_failed": sum(row["status"] != "ok" for row in report),
    }

    (output_root / "sources-report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    (output_root / "build-summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--min-documents", type=int, default=4)
    args = parser.parse_args()

    root = Path(args.output).resolve()
    root.mkdir(parents=True, exist_ok=True)
    summary = build(root)
    print(json.dumps(summary, indent=2))
    if summary["sources_downloaded"] < args.min_documents:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
