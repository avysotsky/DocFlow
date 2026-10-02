#!/usr/bin/env python3
"""Verify request-level idempotency for bounded partial-success batch intake."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import subprocess
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


def run_psql(sql: str, *, tuples_only: bool = False) -> str:
    command = [
        "docker",
        "run",
        "--rm",
        "--network",
        "host",
        "-e",
        "PGPASSWORD=postgres",
        "postgres:16",
        "psql",
        "-h",
        "127.0.0.1",
        "-U",
        "postgres",
        "-d",
        "docflow",
        "-v",
        "ON_ERROR_STOP=1",
    ]
    if tuples_only:
        command.append("-At")
    command.extend(["-c", sql])
    result = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


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

    resume_suffix = uuid.uuid4().hex
    resume_names = [
        f"batch-resume-{resume_suffix}-0.pdf",
        f"batch-resume-{resume_suffix}-1.txt",
        f"batch-resume-{resume_suffix}-2-fault.pdf",
        f"batch-resume-{resume_suffix}-3.pdf",
    ]
    resume_files = [
        (resume_names[0], "application/pdf", valid_pdf),
        (resume_names[1], "text/plain", invalid_payload),
        (resume_names[2], "application/pdf", valid_pdf),
        (resume_names[3], "application/pdf", valid_pdf),
    ]
    resume_key = f"batch-resume-{resume_suffix}"
    trigger_function = "docflow_e2e_batch_resume_fail"
    trigger_name = "docflow_e2e_batch_resume_fail_trigger"
    fault_name_literal = sql_literal(resume_names[2])

    run_psql(
        f'''\
DROP TRIGGER IF EXISTS {trigger_name} ON "Documents";
DROP FUNCTION IF EXISTS {trigger_function}();
CREATE FUNCTION {trigger_function}() RETURNS trigger
LANGUAGE plpgsql
AS $
BEGIN
    IF NEW."OriginalFileName" = {fault_name_literal} THEN
        RAISE EXCEPTION 'docflow e2e injected document persistence failure';
    END IF;
    RETURN NEW;
END;
$;
CREATE TRIGGER {trigger_name}
BEFORE INSERT ON "Documents"
FOR EACH ROW EXECUTE FUNCTION {trigger_function}();
'''
    )

    try:
        first_resume_status, first_resume, first_resume_headers = request_batch(
            base_url,
            api_key,
            resume_key,
            resume_files,
        )
        assert first_resume_status == 200 and isinstance(first_resume, dict), (
            first_resume_status,
            first_resume,
        )
        assert first_resume_headers.get("idempotency-replayed") is None, first_resume_headers
        assert first_resume["totalCount"] == 4, first_resume
        assert first_resume["acceptedCount"] == 2, first_resume
        assert first_resume["rejectedCount"] == 1, first_resume
        assert first_resume["failedCount"] == 1, first_resume
        assert [item["outcome"] for item in first_resume["items"]] == [
            "Accepted",
            "Rejected",
            "Failed",
            "Accepted",
        ], first_resume
        assert first_resume["items"][0]["documentId"], first_resume
        assert first_resume["items"][1]["documentId"] is None, first_resume
        assert first_resume["items"][2]["documentId"] is None, first_resume
        assert first_resume["items"][3]["documentId"], first_resume
        assert first_resume["items"][2]["error"] == "The document could not be persisted.", first_resume
    finally:
        run_psql(
            f'''\
DROP TRIGGER IF EXISTS {trigger_name} ON "Documents";
DROP FUNCTION IF EXISTS {trigger_function}();
'''
        )

    resume_key_literal = sql_literal(resume_key)
    generation_id = run_psql(
        f'''SELECT "GenerationId"::text
FROM "BatchIntakeIdempotencyRecords"
WHERE "Key" = {resume_key_literal};''',
        tuples_only=True,
    )
    assert generation_id, generation_id

    manifest_incomplete = run_psql(
        f'''SELECT CASE WHEN "ResponseJson" IS NULL THEN 1 ELSE 0 END
FROM "BatchIntakeIdempotencyRecords"
WHERE "Key" = {resume_key_literal};''',
        tuples_only=True,
    )
    assert manifest_incomplete == "1", manifest_incomplete

    internal_prefix = f"docflow-internal:batch:{generation_id}:"
    checkpoint_count = run_psql(
        f'''SELECT COUNT(*)
FROM "IntakeIdempotencyRecords"
WHERE "Key" LIKE {sql_literal(internal_prefix + "%")};''',
        tuples_only=True,
    )
    assert checkpoint_count == "3", checkpoint_count

    failed_checkpoint_count = run_psql(
        f'''SELECT COUNT(*)
FROM "IntakeIdempotencyRecords"
WHERE "Key" = {sql_literal(internal_prefix + "2")};''',
        tuples_only=True,
    )
    assert failed_checkpoint_count == "0", failed_checkpoint_count

    second_resume_status, second_resume, second_resume_headers = request_batch(
        base_url,
        api_key,
        resume_key,
        resume_files,
    )
    assert second_resume_status == 200 and isinstance(second_resume, dict), (
        second_resume_status,
        second_resume,
    )
    assert second_resume_headers.get("idempotency-replayed") is None, second_resume_headers
    assert second_resume["acceptedCount"] == 3, second_resume
    assert second_resume["rejectedCount"] == 1, second_resume
    assert second_resume["failedCount"] == 0, second_resume
    assert second_resume["items"][0] == first_resume["items"][0], (
        second_resume,
        first_resume,
    )
    assert second_resume["items"][1] == first_resume["items"][1], (
        second_resume,
        first_resume,
    )
    assert second_resume["items"][3] == first_resume["items"][3], (
        second_resume,
        first_resume,
    )
    assert second_resume["items"][2]["outcome"] == "Accepted", second_resume
    assert second_resume["items"][2]["documentId"], second_resume

    checkpoint_count_after_resume = run_psql(
        f'''SELECT COUNT(*)
FROM "IntakeIdempotencyRecords"
WHERE "Key" LIKE {sql_literal(internal_prefix + "%")};''',
        tuples_only=True,
    )
    assert checkpoint_count_after_resume == "4", checkpoint_count_after_resume

    manifest_complete = run_psql(
        f'''SELECT CASE WHEN "ResponseJson" IS NOT NULL THEN 1 ELSE 0 END
FROM "BatchIntakeIdempotencyRecords"
WHERE "Key" = {resume_key_literal};''',
        tuples_only=True,
    )
    assert manifest_complete == "1", manifest_complete

    third_resume_status, third_resume, third_resume_headers = request_batch(
        base_url,
        api_key,
        resume_key,
        resume_files,
    )
    assert third_resume_status == 200 and third_resume == second_resume, (
        third_resume_status,
        third_resume,
        second_resume,
    )
    assert third_resume_headers.get("idempotency-replayed") == "true", third_resume_headers

    document_count = run_psql(
        f'''SELECT COUNT(*)
FROM "Documents"
WHERE "OriginalFileName" IN (
    {sql_literal(resume_names[0])},
    {sql_literal(resume_names[2])},
    {sql_literal(resume_names[3])}
);''',
        tuples_only=True,
    )
    assert document_count == "3", document_count

    resume_document_ids = [
        second_resume["items"][0]["documentId"],
        second_resume["items"][2]["documentId"],
        second_resume["items"][3]["documentId"],
    ]
    assert all(resume_document_ids), second_resume

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
