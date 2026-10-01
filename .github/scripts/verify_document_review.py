#!/usr/bin/env python3
"""Verify the human-review workflow over a persisted NeedsReview document."""

from __future__ import annotations

import argparse
import csv
import io
import json
import urllib.error
import urllib.request
import uuid


def request_json(
    method: str,
    url: str,
    payload: object | None = None,
) -> tuple[int, object | None]:
    data = None
    headers: dict[str, str] = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read()
            return response.status, json.loads(body) if body else None
    except urllib.error.HTTPError as error:
        body = error.read()
        parsed: object | None = None
        if body:
            try:
                parsed = json.loads(body)
            except json.JSONDecodeError:
                parsed = body.decode("utf-8", errors="replace")
        return error.code, parsed


def get_bytes(url: str) -> tuple[int, bytes]:
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--review-document-id", required=True)
    parser.add_argument("--processed-document-id", required=True)
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    review_result_url = (
        f"{base}/api/documents/{args.review_document_id}/extraction-result"
    )
    review_url = f"{base}/api/documents/{args.review_document_id}/review"

    status, before = request_json("GET", review_result_url)
    assert status == 200 and isinstance(before, dict), (status, before)
    extraction_result_id = before["id"]
    assert before["validationStatus"] == "Invalid", before
    assert before["reviewId"] is None, before
    assert before["reviewedAt"] is None, before
    assert before["structuredData"]["data"]["total"] == "1748.42", before

    corrected_data = dict(before["structuredData"]["data"])
    corrected_data["total"] = "1748.40"

    stale_id = str(uuid.uuid4())
    status, _ = request_json(
        "PUT",
        review_url,
        {
            "expectedExtractionResultId": stale_id,
            "data": corrected_data,
            "note": "Correct arithmetic total after human review.",
        },
    )
    assert status == 409, status

    status, malformed = request_json(
        "PUT",
        review_url,
        {
            "expectedExtractionResultId": extraction_result_id,
            "data": ["not", "an", "object"],
        },
    )
    assert status == 400, (status, malformed)

    status, reviewed = request_json(
        "PUT",
        review_url,
        {
            "expectedExtractionResultId": extraction_result_id,
            "data": corrected_data,
            "note": "Correct arithmetic total after human review.",
        },
    )
    assert status == 200 and isinstance(reviewed, dict), (status, reviewed)
    assert reviewed["documentId"] == args.review_document_id, reviewed
    assert reviewed["extractionResultId"] == extraction_result_id, reviewed
    assert reviewed["documentStatus"] == "Processed", reviewed
    review_id = reviewed["reviewId"]
    assert review_id, reviewed
    assert reviewed["reviewedAt"], reviewed

    status, document = request_json(
        "GET", f"{base}/api/documents/{args.review_document_id}"
    )
    assert status == 200 and isinstance(document, dict), (status, document)
    assert document["status"] == "Processed", document

    status, after = request_json("GET", review_result_url)
    assert status == 200 and isinstance(after, dict), (status, after)
    assert after["id"] == extraction_result_id, after
    assert after["validationStatus"] == "Invalid", after
    assert after["reviewId"] == review_id, after
    assert after["reviewedAt"], after
    assert after["reviewNote"] == "Correct arithmetic total after human review.", after
    assert after["structuredData"]["data"]["total"] == "1748.40", after
    assert after["structuredData"]["human_review"]["review_id"] == review_id, after

    status, csv_bytes = get_bytes(
        f"{base}/api/documents/{args.review_document_id}/export?format=csv"
    )
    assert status == 200, status
    rows = {
        row["Path"]: row["Value"]
        for row in csv.DictReader(io.StringIO(csv_bytes.decode("utf-8-sig")))
    }
    assert rows["data.total"] == "1748.40", rows.get("data.total")
    assert rows["human_review.review_id"] == review_id, rows

    status, _ = request_json(
        "PUT",
        review_url,
        {
            "expectedExtractionResultId": extraction_result_id,
            "data": corrected_data,
            "note": "duplicate",
        },
    )
    assert status == 409, status

    status, processed_result = request_json(
        "GET",
        f"{base}/api/documents/{args.processed_document_id}/extraction-result",
    )
    assert status == 200 and isinstance(processed_result, dict), (status, processed_result)
    status, _ = request_json(
        "PUT",
        f"{base}/api/documents/{args.processed_document_id}/review",
        {
            "expectedExtractionResultId": processed_result["id"],
            "data": processed_result["structuredData"]["data"],
        },
    )
    assert status == 409, status

    missing_document_id = str(uuid.uuid4())
    status, _ = request_json(
        "PUT",
        f"{base}/api/documents/{missing_document_id}/review",
        {
            "expectedExtractionResultId": extraction_result_id,
            "data": corrected_data,
        },
    )
    assert status == 404, status

    print(
        "Document review E2E passed: stale/malformed writes rejected, NeedsReview corrected to "
        "Processed, original extraction id preserved, reviewed data returned and exported, "
        "duplicate/non-reviewable/missing reviews handled predictably."
    )


if __name__ == "__main__":
    main()
