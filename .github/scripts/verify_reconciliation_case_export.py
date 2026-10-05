#!/usr/bin/env python3
"""Verify customer-facing reconciliation CSV/XLSX exports end to end."""

from __future__ import annotations

import argparse
import csv
import io
import urllib.error
import urllib.request
import zipfile
import xml.etree.ElementTree as ET


def fetch(url: str, api_key: str) -> tuple[int, bytes, dict[str, str]]:
    request = urllib.request.Request(
        url,
        headers={"X-DocFlow-Api-Key": api_key},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, response.read(), dict(response.headers.items())
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), dict(exc.headers.items())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--api-key", required=True)
    parser.add_argument("--other-api-key", required=True)
    parser.add_argument("--case-id", required=True)
    args = parser.parse_args()

    export_url = f"{args.base_url}/api/reconciliation/cases/{args.case_id}/export"

    status, csv_bytes, csv_headers = fetch(
        f"{export_url}?format=reconciliation-csv",
        args.api_key,
    )
    assert status == 200, status
    assert csv_headers.get("Content-Type", "").startswith("text/csv")
    assert "reconciliation-" in csv_headers.get("Content-Disposition", "")
    assert ".csv" in csv_headers.get("Content-Disposition", "")

    rows = list(csv.DictReader(io.StringIO(csv_bytes.decode("utf-8-sig"))))
    assert rows
    assert all(row["CaseId"] == args.case_id for row in rows)
    assert all(row["ReconciliationStatus"] == "NeedsReview" for row in rows)
    assert all(row["ReviewStatus"] == "Resolved" for row in rows)
    assert all(row["LatestAction"] == "Resolve" for row in rows)
    assert all(row["LatestReviewer"] == "e2e-primary" for row in rows)
    assert all(
        row["LatestDecisionNote"]
        == "Price difference accepted after supplier confirmation."
        for row in rows
    )

    unit_price = next(
        row
        for row in rows
        if row["Field"] == "unit_price"
        and row["CheckStatus"] == "NeedsReview"
    )
    assert unit_price["CheckScope"] == "InvoiceItem"
    assert unit_price["InvoiceItemIndex"] == "1"
    assert unit_price["MatchMethod"] == "sku_reference"
    assert unit_price["InvoiceValue"] == "12.5"
    assert unit_price["PurchaseOrderValue"] == "13.5"
    assert unit_price["Delta"] == "-1"

    line_total = next(
        row
        for row in rows
        if row["Field"] == "line_total"
        and row["CheckStatus"] == "NeedsReview"
    )
    assert line_total["InvoiceValue"] == "250"
    assert line_total["PurchaseOrderValue"] == "270"
    assert line_total["Delta"] == "-20"

    status, xlsx_bytes, xlsx_headers = fetch(
        f"{export_url}?format=reconciliation-xlsx",
        args.api_key,
    )
    assert status == 200, status
    assert (
        xlsx_headers.get("Content-Type", "")
        == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert xlsx_bytes.startswith(b"PK")

    with zipfile.ZipFile(io.BytesIO(xlsx_bytes)) as archive:
        required = {
            "xl/workbook.xml",
            "xl/worksheets/sheet1.xml",
            "xl/worksheets/sheet2.xml",
            "xl/worksheets/sheet3.xml",
        }
        assert required.issubset(set(archive.namelist()))

        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        ns = {
            "s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
        }
        sheet_names = [
            sheet.attrib["name"]
            for sheet in workbook.findall(".//s:sheet", ns)
        ]
        assert sheet_names == ["Case", "Checks", "Audit History"]

        case_xml = archive.read("xl/worksheets/sheet1.xml").decode("utf-8")
        checks_xml = archive.read("xl/worksheets/sheet2.xml").decode("utf-8")
        audit_xml = archive.read("xl/worksheets/sheet3.xml").decode("utf-8")

        assert "Review Status" in case_xml
        assert "Resolved" in case_xml
        assert "Needs Review Checks" in case_xml
        assert "unit_price" in checks_xml
        assert "line_total" in checks_xml
        assert "NeedsReview" in checks_xml
        assert "Resolve" in audit_xml
        assert "Price difference accepted after supplier confirmation." in audit_xml
        assert "e2e-primary" in audit_xml

    bad_status, _, _ = fetch(
        f"{export_url}?format=technical-json",
        args.api_key,
    )
    assert bad_status == 400, bad_status

    other_status, _, _ = fetch(
        f"{export_url}?format=reconciliation-csv",
        args.other_api_key,
    )
    assert other_status == 404, other_status

    print(
        "Reconciliation business exports verified: "
        f"{len(rows)} CSV check rows, XLSX Case/Checks/Audit History sheets, "
        "tenant isolation and format validation."
    )


if __name__ == "__main__":
    main()
