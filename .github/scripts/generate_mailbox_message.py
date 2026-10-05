#!/usr/bin/env python3
"""Generate deterministic RFC822 fixtures for DocFlow mailbox-ingestion E2E."""

from __future__ import annotations

import argparse
import base64
from pathlib import Path


def build(pdf: bytes, message_id: str, subject: str) -> bytes:
    encoded_pdf = base64.b64encode(pdf).decode("ascii")
    encoded_note = base64.b64encode(b"not a document").decode("ascii")
    text = f"""From: Billing Robot <billing@example.com>
To: ap@example.com
Date: Sun, 05 Oct 2026 14:00:00 +0300
Message-ID: <{message_id}>
Subject: {subject}
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary="docflow-mailbox-e2e"

--docflow-mailbox-e2e
Content-Type: text/plain; charset=utf-8

Please process the attached supplier invoice.
--docflow-mailbox-e2e
Content-Type: text/plain
Content-Disposition: attachment; filename="notes.txt"
Content-Transfer-Encoding: base64

{encoded_note}
--docflow-mailbox-e2e
Content-Type: application/octet-stream; name="mailbox-invoice.pdf"
Content-Disposition: attachment; filename="mailbox-invoice.pdf"
Content-Transfer-Encoding: base64

{encoded_pdf}
--docflow-mailbox-e2e--
"""
    return text.replace("\n", "\r\n").encode("utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--message-id", default="docflow-mailbox-e2e@example.test")
    parser.add_argument("--subject", default="Supplier invoice from mailbox")
    args = parser.parse_args()

    pdf = Path(args.pdf).read_bytes()
    if not pdf.startswith(b"%PDF-"):
        raise SystemExit("Input file is not a PDF")

    Path(args.output).write_bytes(
        build(pdf, args.message_id, args.subject)
    )


if __name__ == "__main__":
    main()
