#!/usr/bin/env python3
"""Verify customer-scoped document inbox filtering and pagination."""

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.parse
import urllib.request


def get_json(base_url: str, params: dict[str, object]) -> tuple[int, object | None]:
    query = urllib.parse.urlencode(params)
    url = f"{base_url.rstrip('/')}/api/documents?{query}"
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            payload = response.read()
            return response.status, json.loads(payload) if payload else None
    except urllib.error.HTTPError as error:
        payload = error.read()
        parsed = None
        if payload:
            try:
                parsed = json.loads(payload)
            except json.JSONDecodeError:
                parsed = payload.decode("utf-8", errors="replace")
        return error.code, parsed


def assert_in_descending_created_order(items: list[dict[str, object]]) -> None:
    created = [str(item["createdAt"]) for item in items]
    assert created == sorted(created, reverse=True), created


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--customer-id", required=True)
    parser.add_argument("--other-customer-id", required=True)
    parser.add_argument("--other-document-id", required=True)
    parser.add_argument("--invoice-document-id", required=True)
    parser.add_argument("--failed-document-id", required=True)
    parser.add_argument("--needs-review-document-id", required=True)
    args = parser.parse_args()

    status, inbox = get_json(
        args.base_url,
        {
            "customerId": args.customer_id,
            "page": 1,
            "pageSize": 50,
        },
    )
    assert status == 200, (status, inbox)
    assert isinstance(inbox, dict), inbox
    assert inbox["page"] == 1
    assert inbox["pageSize"] == 50
    assert inbox["totalCount"] >= 5, inbox
    assert inbox["totalPages"] == 1, inbox

    items = inbox["items"]
    assert isinstance(items, list) and len(items) == inbox["totalCount"], inbox
    assert_in_descending_created_order(items)

    ids = {item["id"] for item in items}
    assert args.other_document_id not in ids, "Customer isolation failed"
    assert args.invoice_document_id in ids
    assert args.failed_document_id in ids
    assert args.needs_review_document_id in ids

    invoice = next(item for item in items if item["id"] == args.invoice_document_id)
    assert invoice["documentType"] == "supplier_invoice", invoice
    assert invoice["documentStatus"] == "Processed", invoice
    assert invoice["extractionResultId"], invoice
    assert invoice["validationStatus"] == "Valid", invoice
    assert float(invoice["confidence"]) == 1.0, invoice
    assert "storageKey" not in invoice, invoice

    failed = next(item for item in items if item["id"] == args.failed_document_id)
    assert failed["documentStatus"] == "Failed", failed
    assert failed["extractionResultId"] is None, failed
    assert failed["validationStatus"] is None, failed
    assert failed["confidence"] is None, failed

    status, review = get_json(
        args.base_url,
        {
            "customerId": args.customer_id,
            "status": "needsreview",
            "page": 1,
            "pageSize": 50,
        },
    )
    assert status == 200, (status, review)
    assert isinstance(review, dict), review
    review_ids = {item["id"] for item in review["items"]}
    assert args.needs_review_document_id in review_ids, review
    assert all(item["documentStatus"] == "NeedsReview" for item in review["items"]), review

    status, invoices = get_json(
        args.base_url,
        {
            "customerId": args.customer_id,
            "documentType": "SUPPLIER_INVOICE",
            "page": 1,
            "pageSize": 50,
        },
    )
    assert status == 200, (status, invoices)
    assert isinstance(invoices, dict), invoices
    assert invoices["totalCount"] >= 1, invoices
    assert all(item["documentType"] == "supplier_invoice" for item in invoices["items"]), invoices
    assert args.invoice_document_id in {item["id"] for item in invoices["items"]}, invoices

    status, page1 = get_json(
        args.base_url,
        {"customerId": args.customer_id, "page": 1, "pageSize": 2},
    )
    assert status == 200 and isinstance(page1, dict), (status, page1)
    status, page2 = get_json(
        args.base_url,
        {"customerId": args.customer_id, "page": 2, "pageSize": 2},
    )
    assert status == 200 and isinstance(page2, dict), (status, page2)
    assert page1["totalCount"] == page2["totalCount"], (page1, page2)
    assert page1["totalPages"] == page2["totalPages"], (page1, page2)
    page1_ids = {item["id"] for item in page1["items"]}
    page2_ids = {item["id"] for item in page2["items"]}
    assert len(page1["items"]) == 2, page1
    assert page1_ids.isdisjoint(page2_ids), (page1, page2)

    status, other = get_json(
        args.base_url,
        {"customerId": args.other_customer_id, "page": 1, "pageSize": 50},
    )
    assert status == 200 and isinstance(other, dict), (status, other)
    assert other["totalCount"] == 1, other
    assert [item["id"] for item in other["items"]] == [args.other_document_id], other
    assert other["items"][0]["documentStatus"] == "Uploaded", other
    assert other["items"][0]["extractionResultId"] is None, other

    empty_customer_id = "55555555-5555-5555-5555-555555555555"
    status, empty = get_json(
        args.base_url,
        {"customerId": empty_customer_id, "page": 1, "pageSize": 50},
    )
    assert status == 200 and isinstance(empty, dict), (status, empty)
    assert empty["totalCount"] == 0, empty
    assert empty["totalPages"] == 0, empty
    assert empty["items"] == [], empty

    invalid_queries = [
        {"customerId": "00000000-0000-0000-0000-000000000000"},
        {"customerId": args.customer_id, "page": 0},
        {"customerId": args.customer_id, "pageSize": 101},
        {"customerId": args.customer_id, "status": "NotAStatus"},
        {"customerId": args.customer_id, "documentType": "x" * 101},
    ]
    for params in invalid_queries:
        invalid_status, _ = get_json(args.base_url, params)
        assert invalid_status == 400, (params, invalid_status)

    print(
        "Document inbox E2E passed: customer isolation, deterministic ordering, "
        "status/document-type filters, extraction summary, pagination and query validation verified."
    )


if __name__ == "__main__":
    main()
