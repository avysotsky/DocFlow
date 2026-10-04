#!/usr/bin/env python3
"""Download a second, independent PO holdout selected after the primary PO fixes."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
import urllib.request
from pathlib import Path
from typing import Any

import fitz


SOURCES: list[dict[str, str]] = [
    {
        "id": "po-holdout-kpmg-p5039687",
        "url": "https://www.contractsfinder.service.gov.uk/Notice/Attachment/c273cef9-41ed-4b4f-894d-aca092187c61",
    },
    {
        "id": "po-holdout-idexx-p5058264",
        "url": "https://www.contractsfinder.service.gov.uk/Notice/Attachment/24a3df4b-8ab9-46df-a513-f5b163a33470",
    },
    {
        "id": "po-holdout-minster-p5063409",
        "url": "https://www.contractsfinder.service.gov.uk/Notice/Attachment/1a7ee161-0f02-465b-91c9-c25914408b86",
    },
    {
        "id": "po-holdout-ukri-ukr10015660",
        "url": "https://www.find-tender.service.gov.uk/Notice/Attachment/A-4650",
    },
    {
        "id": "po-holdout-edwards-2022",
        "url": "https://www.contractsfinder.service.gov.uk/Notice/Attachment/8893d31d-2908-42c4-9b0a-658adccf921b",
    },
]


def download(url: str, target: Path) -> None:
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            request = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 DocFlowPurchaseOrderHoldout/1.0",
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

    for source in SOURCES:
        target = corpus / f"{source['id']}.pdf"
        row: dict[str, Any] = dict(source)
        try:
            download(source["url"], target)
            with fitz.open(target) as pdf:
                row.update(
                    {
                        "status": "ok",
                        "pages": pdf.page_count,
                        "native_text_chars": sum(
                            len(page.get_text("text").strip()) for page in pdf
                        ),
                        "sha256": digest(target),
                    }
                )
        except Exception as exc:
            row.update({"status": "error", "error": f"{type(exc).__name__}: {exc}"})
        report.append(row)

    summary = {
        "sources_total": len(report),
        "sources_downloaded": sum(row["status"] == "ok" for row in report),
        "sources_failed": sum(row["status"] != "ok" for row in report),
    }
    (root / "sources-report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
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
    if summary["sources_downloaded"] < args.min_documents:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
