#!/usr/bin/env python3
"""Verify authenticated tenant-scoped inbox, diagnostics, batch intake, and intake idempotency."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path


def parse_body(payload: bytes) -> object | None:
    if not payload:
        return None
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        return payload.decode("utf-8", errors="replace")


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
            return response.status, parse_body(response.read())
    except urllib.error.HTTPError as error:
        return error.code, parse_body(error.read())


def request_method(
    method: str,
    url: str,
    api_key: str,
) -> tuple[int, object | None]:
    request = urllib.request.Request(
        url,
        headers={"X-DocFlow-Api-Key": api_key},
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, parse_body(response.read())
    except urllib.error.HTTPError as error:
        return error.code, parse_body(error.read())


def build_multipart_body(
    field_name: str,
    files: list[tuple[str, str, bytes]],
) -> tuple[str, bytes]:
    boundary = f"----docflow-e2e-{uuid.uuid4().hex}"
    body = bytearray()

    for file_name, content_type, payload in files:
        body.extend(f"--{boundary}\r\n".encode())
        body.extend(
            (
                f'Content-Disposition: form-data; name="{field_name}"; '
                f'filename="{file_name}"\r\n'
            ).encode()
        )
        body.extend(f"Content-Type: {content_type}\r\n\r\n".encode())
        body.extend(payload)
        body.extend(b"\r\n")

    body.extend(f"--{boundary}--\r\n".encode())
    return boundary, bytes(body)


def request_multipart(
    url: str,
    api_key: str,
    files: list[tuple[str, str, bytes]],
) -> tuple[int, object | None]:
    boundary, body = build_multipart_body("Files", files)
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "X-DocFlow-Api-Key": api_key,
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, parse_body(response.read())
    except urllib.error.HTTPError as error:
        return error.code, parse_body(error.read())


def request_single_upload(
    base_url: str,
    api_key: str,
    idempotency_key: str,
    payload: bytes,
    *,
    file_name: str = "idempotency.pdf",
    content_type: str = "application/pdf",
) -> tuple[int, object | None, dict[str, str]]:
    boundary, body = build_multipart_body(
        "File",
        [(file_name, content_type, payload)],
    )
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/documents",
        data=body,
        headers={
            "X-DocFlow-Api-Key": api_key,
            "Idempotency-Key": idempotency_key,
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return (
                response.status,
                parse_body(response.read()),
                {key.lower(): value for key, value in response.headers.items()},
            )
    except urllib.error.HTTPError as error:
        return (
            error.code,
            parse_body(error.read()),
            {key.lower(): value for key, value in error.headers.items()},
        )


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


def wait_for_terminal_status(base_url: str, api_key: str, document_id: str) -> str:
    status = ""
    for _ in range(30):
        code, document = request_json(
            f"{base_url.rstrip('/')}/api/documents/{document_id}",
            api_key,
        )
        assert code == 200 and isinstance(document, dict), (code, document)
        status = str(document["status"])
        if status in {"Processed", "NeedsReview", "Failed"}:
            return status
        time.sleep(1)
    return status


def assert_in_descending_created_order(items: list[dict[str, object]]) -> None:
    created = [str(item["createdAt"]) for item in items]
    assert created == sorted(created, reverse=True), created


def verify_intake_idempotency(base_url: str, api_key: str, other_api_key: str) -> None:
    valid_pdf = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF\n"
    different_pdf = b"%PDF-1.4\n1 0 obj\n<</Type /Catalog>>\nendobj\n%%EOF\n"

    key = f"e2e-idempotency-{uuid.uuid4().hex}"
    first_status, first, first_headers = request_single_upload(
        base_url,
        api_key,
        key,
        valid_pdf,
    )
    assert first_status == 201 and isinstance(first, dict), (first_status, first)
    assert "idempotency-replayed" not in first_headers, first_headers

    replay_status, replay, replay_headers = request_single_upload(
        base_url,
        api_key,
        key,
        valid_pdf,
    )
    assert replay_status == 201 and replay == first, (replay_status, replay, first)
    assert replay_headers.get("idempotency-replayed") == "true", replay_headers

    conflict_status, conflict, _ = request_single_upload(
        base_url,
        api_key,
        key,
        different_pdf,
    )
    assert conflict_status == 409, (conflict_status, conflict)

    other_status, other, other_headers = request_single_upload(
        base_url,
        other_api_key,
        key,
        valid_pdf,
    )
    assert other_status == 201 and isinstance(other, dict), (other_status, other)
    assert other["id"] != first["id"], (other, first)
    assert "idempotency-replayed" not in other_headers, other_headers

    rejected_key = f"e2e-idempotency-rejected-{uuid.uuid4().hex}"
    rejected_status, rejected, rejected_headers = request_single_upload(
        base_url,
        api_key,
        rejected_key,
        b"not-a-pdf",
        file_name="invalid.pdf",
    )
    assert rejected_status == 400, (rejected_status, rejected)
    assert "idempotency-replayed" not in rejected_headers, rejected_headers

    rejected_replay_status, rejected_replay, rejected_replay_headers = request_single_upload(
        base_url,
        api_key,
        rejected_key,
        b"not-a-pdf",
        file_name="invalid.pdf",
    )
    assert rejected_replay_status == 400, (rejected_replay_status, rejected_replay)
    assert rejected_replay == rejected, (rejected_replay, rejected)
    assert rejected_replay_headers.get("idempotency-replayed") == "true", rejected_replay_headers

    concurrent_key = f"e2e-idempotency-concurrent-{uuid.uuid4().hex}"

    def concurrent_upload() -> tuple[int, object | None, dict[str, str]]:
        return request_single_upload(
            base_url,
            api_key,
            concurrent_key,
            valid_pdf,
            file_name="concurrent.pdf",
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        concurrent_results = list(executor.map(lambda _: concurrent_upload(), range(2)))

    assert all(status == 201 for status, _, _ in concurrent_results), concurrent_results
    concurrent_payloads = [payload for _, payload, _ in concurrent_results]
    assert all(isinstance(payload, dict) for payload in concurrent_payloads), concurrent_payloads
    concurrent_ids = {payload["id"] for payload in concurrent_payloads if isinstance(payload, dict)}
    assert len(concurrent_ids) == 1, concurrent_results
    replay_flags = [
        headers.get("idempotency-replayed") == "true"
        for _, _, headers in concurrent_results
    ]
    assert replay_flags.count(True) == 1, concurrent_results

    original_document_id = str(first["id"])
    terminal_status = wait_for_terminal_status(base_url, api_key, original_document_id)
    assert terminal_status in {"Processed", "NeedsReview", "Failed"}, terminal_status

    delete_status, _ = request_method(
        "DELETE",
        f"{base_url.rstrip('/')}/api/documents/{original_document_id}",
        api_key,
    )
    assert delete_status == 204, delete_status

    deleted_status, _ = request_json(
        f"{base_url.rstrip('/')}/api/documents/{original_document_id}",
        api_key,
    )
    assert deleted_status == 404, deleted_status

    post_delete_replay_status, post_delete_replay, post_delete_headers = request_single_upload(
        base_url,
        api_key,
        key,
        valid_pdf,
    )
    assert post_delete_replay_status == 201, post_delete_replay_status
    assert post_delete_replay == first, (post_delete_replay, first)
    assert post_delete_headers.get("idempotency-replayed") == "true", post_delete_headers

    still_deleted_status, _ = request_json(
        f"{base_url.rstrip('/')}/api/documents/{original_document_id}",
        api_key,
    )
    assert still_deleted_status == 404, still_deleted_status


def verify_batch_intake(base_url: str, api_key: str, other_api_key: str) -> None:
    batch_url = f"{base_url.rstrip('/')}/api/documents/batch"

    status, _ = request_multipart(batch_url, api_key, [])
    assert status == 400, status

    too_many = [
        (f"batch-{index}.pdf", "application/pdf", b"%PDF-\n")
        for index in range(11)
    ]
    status, _ = request_multipart(batch_url, api_key, too_many)
    assert status == 400, status

    valid_pdf = Path("/tmp/supplier-quotation.pdf").read_bytes()
    status, batch = request_multipart(
        batch_url,
        api_key,
        [
            ("batch-valid.pdf", "application/pdf", valid_pdf),
            ("batch-invalid.txt", "text/plain", b"not-a-pdf"),
        ],
    )
    assert status == 200 and isinstance(batch, dict), (status, batch)
    assert batch["totalCount"] == 2, batch
    assert batch["acceptedCount"] == 1, batch
    assert batch["rejectedCount"] == 1, batch
    assert batch["failedCount"] == 0, batch

    items = batch["items"]
    assert isinstance(items, list) and len(items) == 2, batch
    accepted = items[0]
    rejected = items[1]

    assert accepted["index"] == 0, accepted
    assert accepted["originalFileName"] == "batch-valid.pdf", accepted
    assert accepted["outcome"] == "Accepted", accepted
    assert accepted["documentId"], accepted
    assert accepted["documentStatus"] == "Uploaded", accepted
    assert accepted["error"] is None, accepted

    assert rejected["index"] == 1, rejected
    assert rejected["originalFileName"] == "batch-invalid.txt", rejected
    assert rejected["outcome"] == "Rejected", rejected
    assert rejected["documentId"] is None, rejected
    assert rejected["documentStatus"] is None, rejected
    assert rejected["error"] == "Only PDF files are supported.", rejected

    document_id = accepted["documentId"]
    final_status = wait_for_terminal_status(base_url, api_key, document_id)
    assert final_status == "Processed", final_status

    status, document = request_json(
        f"{base_url.rstrip('/')}/api/documents/{document_id}",
        api_key,
    )
    assert status == 200 and isinstance(document, dict), (status, document)
    assert document["originalFileName"] == "batch-valid.pdf", document

    cross_tenant_status, _ = request_json(
        f"{base_url.rstrip('/')}/api/documents/{document_id}",
        other_api_key,
    )
    assert cross_tenant_status == 404, cross_tenant_status


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

    detail_status, invoice_detail = request_json(
        f"{args.base_url.rstrip('/')}/api/documents/{args.invoice_document_id}",
        args.api_key,
    )
    assert detail_status == 200 and isinstance(invoice_detail, dict), (
        detail_status,
        invoice_detail,
    )
    assert isinstance(invoice_detail.get("storageKey"), str) and invoice_detail["storageKey"], invoice_detail
    expected_source_file_url = f"/api/documents/{args.invoice_document_id}/file"
    assert invoice_detail.get("sourceFileUrl") == expected_source_file_url, invoice_detail

    source_file_status, _ = request_json(
        f"{args.base_url.rstrip('/')}{expected_source_file_url}",
        args.api_key,
    )
    assert source_file_status == 200, source_file_status

    swagger_status, swagger = request_json(
        f"{args.base_url.rstrip('/')}/swagger/v1/swagger.json",
        None,
    )
    assert swagger_status == 200 and isinstance(swagger, dict), (
        swagger_status,
        swagger,
    )
    schemas = swagger.get("components", {}).get("schemas", {})
    document_schemas = [
        schema
        for schema in schemas.values()
        if isinstance(schema, dict)
        and isinstance(schema.get("properties"), dict)
        and "storageKey" in schema["properties"]
        and "sourceFileUrl" in schema["properties"]
        and "originalFileName" in schema["properties"]
    ]
    assert len(document_schemas) == 1, document_schemas
    document_properties = document_schemas[0]["properties"]
    assert document_properties["storageKey"].get("deprecated") is True, document_properties["storageKey"]
    assert "Deprecated internal storage locator" in document_properties["storageKey"].get("description", ""), document_properties["storageKey"]
    assert document_properties["sourceFileUrl"].get("type") == "string", document_properties["sourceFileUrl"]

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

    verify_intake_idempotency(args.base_url, args.api_key, args.other_api_key)
    verify_batch_intake(args.base_url, args.api_key, args.other_api_key)

    print(
        "Document inbox/auth/intake E2E passed: tenant isolation, processing diagnostics, "
        "single-upload persisted idempotency, concurrent replay/conflict behavior, and bounded "
        "partial-success batch intake verified."
    )


if __name__ == "__main__":
    main()
