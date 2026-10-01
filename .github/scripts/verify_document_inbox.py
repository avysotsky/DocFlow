#!/usr/bin/env python3
"""Verify authenticated tenant-scoped document inbox filtering and pagination."""

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.parse
import urllib.request


def request_json(
    url: str,
    api_key: str | None,
) -> tuple[int, object | None]:
    headers = {}
    if api_key is not None:
        headers["X-DocFlow-Api-Key"] = api_key

    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
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


def get_inbox(
    base_url: str,
    api_key: str | None,
    params: dict[str, object],
) -> tuple[int, object | None]:
    query = urllib.parse.urlencode(params)
    suffix = f"?{query}" if query else ""
    url = f"{base_url.rstrip('/')}/api/documents{suffix}"
    return request_json(url, api_key)


def get_processing_diagnostics(
    base_url: str,
    api_key: str,
    document_id: str,
) -> tuple[int, object | None]:
    url = (
        f"{base_url.rstrip('/')}/api/documents/{document_id}/processing-diagnostics"
    )
    return request_json(url, api_key)


def assert_in_descending_created_order(items: list[dict[str, object]]) -> None:
    created = [str(item["createdAt"]) for item in items]
    assert created == sorted(created, reverse=True), created


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--api-key", required=True)
    parser.add_argument("--other-api-key", required=True)
    parser.add_argument("--customer-id", required=True)
    parser.add_argument("--other-customer-id", required=True)
    parser.add_argument("--other-document-id", required=True)
    parser.add_argument("--invoice-document-id", required=True)
    parser.add_argument("--failed-document-id", required=True)
    parser.add_argument("--needs-review-document-id", required=True)
    args = parser.parse_args()

    status, _ = get_inbox(args.base_url, None, {"page": 1})
    assert status == 401, status

    status, _ = get_inbox(args.base_url, "definitely-wrong-key", {"page": 1})
    assert status == 401, status

    status, inbox = get_inbox(
        args.base_url,
        args.api_key,
        {"page": 1, "pageSize": 50},
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
    assert all(item["customerId"] == args.customer_id for item in items), items

    ids = {item["id"] for item in items}
    assert args.other_document_id not in ids, "Tenant isolation failed"
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

    status, invoice_diagnostics = get_processing_diagnostics(
        args.base_url,
        args.api_key,
        args.invoice_document_id,
    )
    assert status == 200 and isinstance(invoice_diagnostics, dict), (
        status,
        invoice_diagnostics,
    )
    assert invoice_diagnostics["status"] == "Processed", invoice_diagnostics
    assert invoice_diagnostics["processingAttempts"] == 1, invoice_diagnostics
    assert invoice_diagnostics["lastProcessingAttemptAt"], invoice_diagnostics
    assert invoice_diagnostics["lastProcessingFailureAt"] is None, invoice_diagnostics
    assert invoice_diagnostics["lastProcessingError"] is None, invoice_diagnostics

    failed = next(item for item in items if item["id"] == args.failed_document_id)
    assert failed["documentStatus"] == "Failed", failed
    assert failed["extractionResultId"] is None, failed
    assert failed["validationStatus"] is None, failed
    assert failed["confidence"] is None, failed

    status, failed_diagnostics = get_processing_diagnostics(
        args.base_url,
        args.api_key,
        args.failed_document_id,
    )
    assert status == 200 and isinstance(failed_diagnostics, dict), (
        status,
        failed_diagnostics,
    )
    assert failed_diagnostics["status"] == "Failed", failed_diagnostics
    assert failed_diagnostics["processingAttempts"] == 3, failed_diagnostics
    assert failed_diagnostics["lastProcessingAttemptAt"], failed_diagnostics
    assert failed_diagnostics["lastProcessingFailureAt"], failed_diagnostics
    assert (
        failed_diagnostics["lastProcessingError"]
        == "InvalidOperationException: Document extraction failed."
    ), failed_diagnostics

    status, review = get_inbox(
        args.base_url,
        args.api_key,
        {"status": "needsreview", "page": 1, "pageSize": 50},
    )
    assert status == 200, (status, review)
    assert isinstance(review, dict), review
    review_ids = {item["id"] for item in review["items"]}
    assert args.needs_review_document_id in review_ids, review
    assert all(item["documentStatus"] == "NeedsReview" for item in review["items"]), review

    status, invoices = get_inbox(
        args.base_url,
        args.api_key,
        {"documentType": "SUPPLIER_INVOICE", "page": 1, "pageSize": 50},
    )
    assert status == 200, (status, invoices)
    assert isinstance(invoices, dict), invoices
    assert invoices["totalCount"] >= 1, invoices
    assert all(item["documentType"] == "supplier_invoice" for item in invoices["items"]), invoices
    assert args.invoice_document_id in {item["id"] for item in invoices["items"]}, invoices

    status, page1 = get_inbox(
        args.base_url,
        args.api_key,
        {"page": 1, "pageSize": 2},
    )
    assert status == 200 and isinstance(page1, dict), (status, page1)
    status, page2 = get_inbox(
        args.base_url,
        args.api_key,
        {"page": 2, "pageSize": 2},
    )
    assert status == 200 and isinstance(page2, dict), (status, page2)
    assert page1["totalCount"] == page2["totalCount"], (page1, page2)
    assert page1["totalPages"] == page2["totalPages"], (page1, page2)
    page1_ids = {item["id"] for item in page1["items"]}
    page2_ids = {item["id"] for item in page2["items"]}
    assert len(page1["items"]) == 2, page1
    assert page1_ids.isdisjoint(page2_ids), (page1, page2)

    status, spoofed = get_inbox(
        args.base_url,
        args.api_key,
        {
            "customerId": args.other_customer_id,
            "page": 1,
            "pageSize": 50,
        },
    )
    assert status == 200 and isinstance(spoofed, dict), (status, spoofed)
    spoofed_ids = {item["id"] for item in spoofed["items"]}
    assert args.other_document_id not in spoofed_ids, spoofed
    assert all(item["customerId"] == args.customer_id for item in spoofed["items"]), spoofed

    other_url = f"{args.base_url.rstrip('/')}/api/documents/{args.other_document_id}"
    status, _ = request_json(other_url, args.api_key)
    assert status == 404, status

    status, _ = get_processing_diagnostics(
        args.base_url,
        args.api_key,
        args.other_document_id,
    )
    assert status == 404, status

    status, other_document = request_json(other_url, args.other_api_key)
    assert status == 200 and isinstance(other_document, dict), (status, other_document)
    assert other_document["id"] == args.other_document_id, other_document
    assert other_document["customerId"] == args.other_customer_id, other_document

    status, other = get_inbox(
        args.base_url,
        args.other_api_key,
        {"page": 1, "pageSize": 50},
    )
    assert status == 200 and isinstance(other, dict), (status, other)
    assert other["totalCount"] == 1, other
    assert [item["id"] for item in other["items"]] == [args.other_document_id], other
    assert other["items"][0]["customerId"] == args.other_customer_id, other

    invalid_queries = [
        {"page": 0},
        {"pageSize": 101},
        {"status": "NotAStatus"},
        {"documentType": "x" * 101},
    ]
    for params in invalid_queries:
        invalid_status, _ = get_inbox(args.base_url, args.api_key, params)
        assert invalid_status == 400, (params, invalid_status)

    print(
        "Document inbox/auth E2E passed: 401 authentication, claim-derived tenant scope, "
        "cross-tenant 404 isolation, bounded processing retries/diagnostics, filters, "
        "extraction summary and pagination verified."
    )


if __name__ == "__main__":
    main()
