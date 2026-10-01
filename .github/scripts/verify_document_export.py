#!/usr/bin/env python3
"""Verify CSV/XLSX export against an already persisted extraction result."""

from __future__ import annotations

import argparse
import csv
import io
import urllib.error
import urllib.request
import zipfile
import xml.etree.ElementTree as ET


SPREADSHEET_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
EXPECTED = {
    "data.invoice_number": "INV-2026-091",
    "data.invoice_date": "2026-09-30",
    "data.due_date": "2026-10-30",
    "data.currency": "EUR",
    "data.purchase_order_number": "PO-78421",
    "data.subtotal": "1457.00",
    "data.vat_rate": "20",
    "data.vat_amount": "291.40",
    "data.total": "1748.40",
}


def fetch(url: str, api_key: str) -> tuple[int, dict[str, str], bytes]:
    request = urllib.request.Request(
        url,
        headers={"X-DocFlow-Api-Key": api_key},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, dict(response.headers.items()), response.read()
    except urllib.error.HTTPError as error:
        return error.code, dict(error.headers.items()), error.read()


def assert_headers(headers: dict[str, str], content_type: str, suffix: str) -> None:
    actual_content_type = next(
        (value for key, value in headers.items() if key.lower() == "content-type"),
        "",
    )
    assert actual_content_type.lower().startswith(content_type.lower()), (
        actual_content_type,
        content_type,
    )

    disposition = next(
        (value for key, value in headers.items() if key.lower() == "content-disposition"),
        "",
    )
    assert "attachment" in disposition.lower(), disposition
    assert suffix.lower() in disposition.lower(), disposition


def parse_csv(payload: bytes) -> dict[str, str]:
    text = payload.decode("utf-8-sig")
    reader = csv.reader(io.StringIO(text))
    header = next(reader)
    assert header == ["Path", "Value"], header
    rows = list(reader)
    assert rows, "CSV export contains no data rows"
    return {path: value for path, value in rows}


def parse_xlsx(payload: bytes) -> dict[str, str]:
    assert payload.startswith(b"PK"), "XLSX is not a ZIP/OOXML package"
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        expected_entries = {
            "[Content_Types].xml",
            "_rels/.rels",
            "xl/workbook.xml",
            "xl/_rels/workbook.xml.rels",
            "xl/worksheets/sheet1.xml",
        }
        assert expected_entries.issubset(set(archive.namelist())), archive.namelist()
        sheet_xml = archive.read("xl/worksheets/sheet1.xml")

    root = ET.fromstring(sheet_xml)
    namespace = {"s": SPREADSHEET_NS}
    rows: dict[str, str] = {}

    for row in root.findall(".//s:sheetData/s:row", namespace):
        cells = []
        for cell in row.findall("s:c", namespace):
            text_node = cell.find("s:is/s:t", namespace)
            cells.append("" if text_node is None or text_node.text is None else text_node.text)
        if cells == ["Path", "Value"]:
            continue
        if len(cells) == 2:
            rows[cells[0]] = cells[1]

    assert rows, "XLSX export contains no data rows"
    return rows


def assert_expected(rows: dict[str, str]) -> None:
    for path, expected in EXPECTED.items():
        actual = rows.get(path)
        assert actual == expected, f"{path}: expected {expected!r}, got {actual!r}"

    item_paths = [path for path in rows if path.startswith("data.items.0.")]
    assert item_paths, "Item array was not flattened into indexed dot paths"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--api-key", required=True)
    parser.add_argument("--document-id", required=True)
    parser.add_argument("--document-without-result-id", required=True)
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    export_base = f"{base_url}/api/documents/{args.document_id}/export"

    csv_status, csv_headers, csv_payload = fetch(
        f"{export_base}?format=csv", args.api_key
    )
    assert csv_status == 200, csv_status
    assert_headers(csv_headers, "text/csv", ".csv")
    csv_rows = parse_csv(csv_payload)
    assert_expected(csv_rows)

    xlsx_status, xlsx_headers, xlsx_payload = fetch(
        f"{export_base}?format=xlsx", args.api_key
    )
    assert xlsx_status == 200, xlsx_status
    assert_headers(
        xlsx_headers,
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".xlsx",
    )
    xlsx_rows = parse_xlsx(xlsx_payload)
    assert_expected(xlsx_rows)

    assert csv_rows == xlsx_rows, "CSV and XLSX do not expose the same flattened data"

    bad_status, _, _ = fetch(f"{export_base}?format=pdf", args.api_key)
    assert bad_status == 400, bad_status

    missing_status, _, _ = fetch(
        f"{base_url}/api/documents/{args.document_without_result_id}/export?format=csv",
        args.api_key,
    )
    assert missing_status == 404, missing_status

    print(
        "Export E2E passed: CSV/XLSX content, equivalent flattened rows, "
        "unsupported format and missing-result behavior verified."
    )


if __name__ == "__main__":
    main()
