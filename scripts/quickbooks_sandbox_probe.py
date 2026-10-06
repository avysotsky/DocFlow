#!/usr/bin/env python3

import argparse
import json
import sys
import urllib.error
import urllib.request


def get_json(url: str, api_key: str):
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "X-DocFlow-Api-Key": api_key,
        },
        method="GET",
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"GET {url} returned HTTP {exc.code}: {body}"
        ) from exc


def main():
    parser = argparse.ArgumentParser(
        description="Read-only DocFlow QuickBooks Online sandbox readiness probe."
    )
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8080",
        help="DocFlow API base URL.",
    )
    parser.add_argument("--api-key", required=True)
    parser.add_argument("--target-key", default="qbo-sandbox")
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    target = args.target_key.strip()

    connection = get_json(
        f"{base}/api/accounting-connections/quickbooks-online/targets/{target}",
        args.api_key,
    )

    references = get_json(
        f"{base}/api/accounting-connections/quickbooks-online/targets/{target}/references",
        args.api_key,
    )

    mapping_validation = get_json(
        f"{base}/api/accounting-connections/quickbooks-online/targets/{target}/mapping-validation",
        args.api_key,
    )

    result = {
        "connection": {
            "targetKey": connection.get("targetKey"),
            "isConnected": connection.get("isConnected"),
            "accessTokenExpiresAt": connection.get("accessTokenExpiresAt"),
            "refreshTokenExpiresAt": connection.get("refreshTokenExpiresAt"),
        },
        "vendors": [
            item
            for item in references.get("vendors", [])
            if item.get("active", True)
        ],
        "accounts": [
            item
            for item in references.get("accounts", [])
            if item.get("active", True)
        ],
        "taxCodes": [
            item
            for item in references.get("taxCodes", [])
            if item.get("active", True)
        ],
        "mappingValidation": mapping_validation,
    }

    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")

    if not result["connection"]["isConnected"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
