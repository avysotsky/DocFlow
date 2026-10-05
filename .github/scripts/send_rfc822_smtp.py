#!/usr/bin/env python3
"""Send an RFC822 message unchanged through a local SMTP test server."""

from __future__ import annotations

import argparse
import smtplib
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--sender", required=True)
    parser.add_argument("--recipient", required=True)
    parser.add_argument("--message", required=True)
    args = parser.parse_args()

    payload = Path(args.message).read_bytes()

    with smtplib.SMTP(args.host, args.port, timeout=30) as client:
        refused = client.sendmail(
            args.sender,
            [args.recipient],
            payload,
        )

    if refused:
        raise SystemExit(f"SMTP server refused recipients: {refused}")


if __name__ == "__main__":
    main()
