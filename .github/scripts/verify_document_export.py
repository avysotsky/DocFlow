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


def parse_business_csv(payload: bytes) -> list[dict[str, str]]:
    text = payload.decode("utf-8-sig")
    rows = list(csv.DictReader(io.StringIO(text)))
    assert rows, "Business CSV export contains no line-item rows"
    expected_headers = [
        "Supplier",
        "InvoiceNumber",
        "InvoiceDate",
        "DueDate",
        "Currency",
        "CustomerReference",
        "PurchaseOrderNumber",
        "SKU",
        "Description",
        "Quantity",
        "Unit",
        "UnitPrice",
        "DiscountRate",
        "LineTotal",
        "Subtotal",
        "VATRate",
        "VATAmount",
        "Total",
        "DuplicateStatus",
        "DuplicateOfDocumentId",
        "ValidationStatus",
        "ReviewStatus",
    ]
    assert list(rows[0].keys()) == expected_headers, list(rows[0].keys())
    return rows


def _xlsx_rows(archive: zipfile.ZipFile, path: str) -> list[list[str]]:
    root = ET.fromstring(archive.read(path))
    namespace = {"s": SPREADSHEET_NS}
    rows: list[list[str]] = []
    for row in root.findall(".//s:sheetData/s:row", namespace):
        values: list[str] = []
        for cell in row.findall("s:c", namespace):
            text_node = cell.find("s:is/s:t", namespace)
            values.append("" if text_node is None or text_node.text is None else text_node.text)
        rows.append(values)
    return rows


def parse_business_xlsx(payload: bytes) -> tuple[dict[str, str], list[dict[str, str]]]:
    assert payload.startswith(b"PK"), "Business XLSX is not a ZIP/OOXML package"
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        expected_entries = {
            "[Content_Types].xml",
            "_rels/.rels",
            "xl/workbook.xml",
            "xl/_rels/workbook.xml.rels",
            "xl/worksheets/sheet1.xml",
            "xl/worksheets/sheet2.xml",
        }
        assert expected_entries.issubset(set(archive.namelist())), archive.namelist()

        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        namespace = {"s": SPREADSHEET_NS}
        sheet_names = [
            sheet.attrib["name"]
            for sheet in workbook.findall(".//s:sheets/s:sheet", namespace)
        ]
        assert sheet_names == ["Invoice", "Line Items"], sheet_names

        summary_rows = _xlsx_rows(archive, "xl/worksheets/sheet1.xml")
        item_rows = _xlsx_rows(archive, "xl/worksheets/sheet2.xml")

    assert summary_rows and summary_rows[0] == ["Field", "Value"], summary_rows[:1]
    summary = {
        row[0]: row[1]
        for row in summary_rows[1:]
        if len(row) >= 2
    }

    assert item_rows, "Line Items worksheet is empty"
    headers = item_rows[0]
    expected_item_headers = [
        "SKU",
        "Description",
        "Quantity",
        "Unit",
        "UnitPrice",
        "DiscountRate",
        "LineTotal",
    ]
    assert headers == expected_item_headers, headers
    items = [
        {header: value for header, value in zip(headers, row)}
        for row in item_rows[1:]
    ]
    return summary, items


def assert_business_export(
    rows: list[dict[str, str]],
    summary: dict[str, str] | None = None,
) -> None:
    assert len(rows) == 5, len(rows)
    first = rows[0]
    assert first["InvoiceNumber"] == "INV-2026-091", first
    assert first["InvoiceDate"] == "2026-09-30", first
    assert first["DueDate"] == "2026-10-30", first
    assert first["Currency"] == "EUR", first
    assert first["PurchaseOrderNumber"] == "PO-78421", first
    assert first["SKU"] == "AX-100", first
    assert first["Description"] == "Sensor bracket", first
    assert first["Quantity"] == "20", first
    assert first["Unit"] == "pcs", first
    assert first["UnitPrice"] == "12.50", first
    assert first["LineTotal"] == "250.00", first
    assert first["Subtotal"] == "1457.00", first
    assert first["VATRate"] == "20", first
    assert first["VATAmount"] == "291.40", first
    assert first["Total"] == "1748.40", first
    assert first["DuplicateStatus"] == "clear", first
    assert first["DuplicateOfDocumentId"] == "", first
    assert first["ValidationStatus"] == "Valid", first
    assert first["ReviewStatus"] == "NotReviewed", first

    if summary is not None:
        assert summary["Invoice Number"] == "INV-2026-091", summary
        assert summary["Invoice Date"] == "2026-09-30", summary
        assert summary["Due Date"] == "2026-10-30", summary
        assert summary["Currency"] == "EUR", summary
        assert summary["Purchase Order Number"] == "PO-78421", summary
        assert summary["Subtotal"] == "1457.00", summary
        assert summary["VAT Amount"] == "291.40", summary
        assert summary["Total"] == "1748.40", summary
        assert summary["Duplicate Status"] == "clear", summary
        assert summary["Duplicate Of Document Id"] == "", summary
        assert summary["Validation Status"] == "Valid", summary
        assert summary["Review Status"] == "NotReviewed", summary


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

    business_csv_status, business_csv_headers, business_csv_payload = fetch(
        f"{export_base}?format=invoice-csv", args.api_key
    )
    assert business_csv_status == 200, business_csv_status
    assert_headers(business_csv_headers, "text/csv", "-invoice.csv")
    business_csv_rows = parse_business_csv(business_csv_payload)
    assert_business_export(business_csv_rows)

    business_xlsx_status, business_xlsx_headers, business_xlsx_payload = fetch(
        f"{export_base}?format=invoice-xlsx", args.api_key
    )
    assert business_xlsx_status == 200, business_xlsx_status
    assert_headers(
        business_xlsx_headers,
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "-invoice.xlsx",
    )
    business_summary, business_items = parse_business_xlsx(business_xlsx_payload)
    assert_business_export(
        [
            {
                "InvoiceNumber": business_summary["Invoice Number"],
                "InvoiceDate": business_summary["Invoice Date"],
                "DueDate": business_summary["Due Date"],
                "Currency": business_summary["Currency"],
                "PurchaseOrderNumber": business_summary["Purchase Order Number"],
                "SKU": item["SKU"],
                "Description": item["Description"],
                "Quantity": item["Quantity"],
                "Unit": item["Unit"],
                "UnitPrice": item["UnitPrice"],
                "DiscountRate": item["DiscountRate"],
                "LineTotal": item["LineTotal"],
                "Subtotal": business_summary["Subtotal"],
                "VATRate": business_summary["VAT Rate"],
                "VATAmount": business_summary["VAT Amount"],
                "Total": business_summary["Total"],
                "DuplicateStatus": business_summary["Duplicate Status"],
                "DuplicateOfDocumentId": business_summary["Duplicate Of Document Id"],
                "ValidationStatus": business_summary["Validation Status"],
                "ReviewStatus": business_summary["Review Status"],
                "Supplier": business_summary["Supplier"],
                "CustomerReference": business_summary["Customer Reference"],
            }
            for item in business_items
        ],
        business_summary,
    )

    bad_status, _, _ = fetch(f"{export_base}?format=pdf", args.api_key)
    assert bad_status == 400, bad_status

    missing_status, _, _ = fetch(
        f"{base_url}/api/documents/{args.document_without_result_id}/export?format=csv",
        args.api_key,
    )
    assert missing_status == 404, missing_status

    print(
        "Export E2E passed: diagnostic CSV/XLSX plus business invoice CSV/XLSX, "
        "two-sheet workbook structure, unsupported format and missing-result behavior verified."
    )


if __name__ == "__main__":
    main()
