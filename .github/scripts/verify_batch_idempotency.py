#!/usr/bin/env python3
"""Verify request-level idempotency for bounded partial-success batch intake."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import time
import urllib.error
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


def build_multipart_body(
    files: list[tuple[str, str, bytes]],
) -> tuple[str, bytes]:
    boundary = f"----docflow-batch-idempotency-{uuid.uuid4().hex}"
    body = bytearray()

    for file_name, content_type, payload in files:
        body.extend(f"--{boundary}\r\n".encode())
        body.extend(
            (
                'Content-Disposition: form-data; name="Files"; '
                f'filename="{file_name}"\r\n'
            ).encode()
        )
        body.extend(f"Content-Type: {content_type}\r\n\r\n".encode())
        body.extend(payload)
        body.extend(b"\r\n")

    body.extend(f"--{boundary}--\r\n".encode())
    return boundary, bytes(body)


def request_batch(
    base_url: str,
    api_key: str,
    idempotency_key: str,
    files: list[tuple[str, str, bytes]],
) -> tuple[int, object | None, dict[str, str]]:
    boundary, body = build_multipart_body(files)
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/documents/batch",
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


def request_json(url: str, api_key: str) -> tuple[int, object | None]:
    request = urllib.request.Request(
        url,
        headers={"X-DocFlow-Api-Key": api_key},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, parse_body(response.read())
    except urllib.error.HTTPError as error:
        return error.code, parse_body(error.read())


def get_inbox(base_url: str, api_key: str) -> dict[str, object]:
    status, payload = request_json(
        f"{base_url.rstrip('/')}/api/documents?page=1&pageSize=100",
        api_key,
    )
    assert status == 200 and isinstance(payload, dict), (status, payload)
    return payload


def count_filename(base_url: str, api_key: str, file_name: str) -> int:
    inbox = get_inbox(base_url, api_key)
    items = inbox.get("items")
    assert isinstance(items, list), inbox
    return sum(
        1
        for item in items
        if isinstance(item, dict) and item.get("originalFileName") == file_name
    )


def wait_for_terminal(base_url: str, api_key: str, document_id: str) -> str:
    status = ""
    for _ in range(30):
        code, payload = request_json(
            f"{base_url.rstrip('/')}/api/documents/{document_id}",
            api_key,
        )
        assert code == 200 and isinstance(payload, dict), (code, payload)
        status = str(payload["status"])
        if status in {"Processed", "NeedsReview", "Failed"}:
            return status
        time.sleep(1)
    return status


def verify(base_url: str, api_key: str, other_api_key: str) -> None:
    valid_pdf = Path("/tmp/supplier-quotation.pdf").read_bytes()
    invalid_payload = b"not-a-pdf"

    suffix = uuid.uuid4().hex
    valid_name = f"batch-idempotent-{suffix}.pdf"
    invalid_name = f"batch-idempotent-{suffix}.txt"
    files = [
        (valid_name, "application/pdf", valid_pdf),
        (invalid_name, "text/plain", invalid_payload),
    ]
    key = f"batch-idempotency-{suffix}"

    status, first, headers = request_batch(base_url, api_key, key, files)
    assert status == 200 and isinstance(first, dict), (status, first)
    assert headers.get("idempotency-replayed") is None, headers
    assert first["totalCount"] == 2, first
    assert first["acceptedCount"] == 1, first
    assert first["rejectedCount"] == 1, first
    assert first["failedCount"] == 0, first
    assert len(first["items"]) == 2, first
    accepted_id = first["items"][0]["documentId"]
    assert accepted_id, first

    replay_status, replay, replay_headers = request_batch(
        base_url,
        api_key,
        key,
        files,
    )
    assert replay_status == 200 and replay == first, (replay_status, replay, first)
    assert replay_headers.get("idempotency-replayed") == "true", replay_headers
    assert count_filename(base_url, api_key, valid_name) == 1

    conflict_status, conflict, _ = request_batch(
        base_url,
        api_key,
        key,
        list(reversed(files)),
    )
    assert conflict_status == 409, (conflict_status, conflict)
    assert count_filename(base_url, api_key, valid_name) == 1

    other_status, other, other_headers = request_batch(
        base_url,
        other_api_key,
        key,
        files,
    )
    assert other_status == 200 and isinstance(other, dict), (other_status, other)
    other_accepted_id = other["items"][0]["documentId"]
    assert other_accepted_id and other_accepted_id != accepted_id, (other, first)
    assert other_headers.get("idempotency-replayed") is None, other_headers

    reserved_status, reserved, _ = request_batch(
        base_url,
        api_key,
        f"docflow-internal:user-{suffix}",
        files,
    )
    assert reserved_status == 400, (reserved_status, reserved)

    concurrent_suffix = uuid.uuid4().hex
    concurrent_name = f"batch-concurrent-{concurrent_suffix}.pdf"
    concurrent_invalid_name = f"batch-concurrent-{concurrent_suffix}.txt"
    concurrent_key = f"batch-concurrent-{concurrent_suffix}"
    concurrent_files = [
        (concurrent_name, "application/pdf", valid_pdf),
        (concurrent_invalid_name, "text/plain", invalid_payload),
    ]

    def upload_concurrently() -> tuple[int, object | None, dict[str, str]]:
        return request_batch(
            base_url,
            api_key,
            concurrent_key,
            concurrent_files,
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: upload_concurrently(), range(2)))

    assert all(status == 200 for status, _, _ in results), results
    payloads = [payload for _, payload, _ in results]
    assert all(isinstance(payload, dict) for payload in payloads), payloads
    assert payloads[0] == payloads[1], payloads

    accepted_ids = {
        payload["items"][0]["documentId"]
        for payload in payloads
        if isinstance(payload, dict)
    }
    assert len(accepted_ids) == 1, results
    replay_flags = [
        response_headers.get("idempotency-replayed") == "true"
        for _, _, response_headers in results
    ]
    assert replay_flags.count(True) == 1, results
    assert count_filename(base_url, api_key, concurrent_name) == 1

    concurrent_accepted_id = next(iter(accepted_ids))
    assert wait_for_terminal(base_url, api_key, str(accepted_id)) == "Processed"
    assert wait_for_terminal(base_url, other_api_key, str(other_accepted_id)) == "Processed"
    assert wait_for_terminal(base_url, api_key, str(concurrent_accepted_id)) == "Processed"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--api-key", required=True)
    parser.add_argument("--other-api-key", required=True)
    args = parser.parse_args()

    verify(args.base_url, args.api_key, args.other_api_key)
    print("Batch intake idempotency E2E passed.")


if __name__ == "__main__":
    main()
