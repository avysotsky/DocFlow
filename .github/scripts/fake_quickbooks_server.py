#!/usr/bin/env python3

import argparse
import base64
import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


class Handler(BaseHTTPRequestHandler):
    output_path: Path
    expected_basic: str
    bill_lock = threading.Lock()
    bills_by_request_id: dict[str, str] = {}
    lost_response_request_ids: set[str] = set()

    def log_message(self, format, *args):
        return

    def _write_json(self, status: int, payload: dict):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _record(self, kind: str, body: str):
        item = {
            "kind": kind,
            "path": self.path,
            "authorization": self.headers.get("Authorization"),
            "body": body,
        }
        with self.output_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(item, separators=(",", ":")) + "\n")

    def do_GET(self):
        if self.path == "/health":
            self._write_json(200, {"status": "ok"})
            return

        parsed = urlparse(self.path)
        if parsed.path == "/v3/company/realm-e2e/query":
            self._record("query", "")
            if self.headers.get("Authorization") != "Bearer refreshed-access-token":
                self._write_json(401, {"error": "unexpected_bearer_token"})
                return

            query = parse_qs(parsed.query).get("query", [""])[0]

            if query.lower().startswith("select * from vendor"):
                self._write_json(
                    200,
                    {
                        "QueryResponse": {
                            "Vendor": [
                                {
                                    "Id": "vendor-41",
                                    "DisplayName": "ACME Components Ltd.",
                                    "Active": True,
                                },
                                {
                                    "Id": "vendor-99",
                                    "DisplayName": "Backup Supplier",
                                    "Active": False,
                                },
                            ]
                        }
                    },
                )
                return

            if query.lower().startswith("select * from account"):
                self._write_json(
                    200,
                    {
                        "QueryResponse": {
                            "Account": [
                                {
                                    "Id": "ap-33",
                                    "Name": "Accounts Payable",
                                    "FullyQualifiedName": "Accounts Payable",
                                    "AccountType": "Accounts Payable",
                                    "AccountSubType": "AccountsPayable",
                                    "Active": True,
                                },
                                {
                                    "Id": "expense-default",
                                    "Name": "Office Expenses",
                                    "FullyQualifiedName": "Expenses:Office Expenses",
                                    "AccountType": "Expense",
                                    "AccountSubType": "OfficeGeneralAdministrativeExpenses",
                                    "Active": True,
                                },
                            ]
                        }
                    },
                )
                return

            if query.lower().startswith("select * from taxcode"):
                self._write_json(
                    200,
                    {
                        "QueryResponse": {
                            "TaxCode": [
                                {
                                    "Id": "vat-20",
                                    "Name": "VAT 20%",
                                    "Active": True,
                                }
                            ]
                        }
                    },
                )
                return

            self._write_json(400, {"error": "unsupported_query"})
            return

        self._write_json(404, {"error": "not_found"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        body = raw.decode("utf-8")

        if self.path == "/oauth2/v1/tokens/bearer":
            self._record("token", body)

            if self.headers.get("Authorization") != self.expected_basic:
                self._write_json(401, {"error": "invalid_client"})
                return

            form = parse_qs(body)
            grant_type = form.get("grant_type", [""])[0]

            if grant_type == "authorization_code":
                if form.get("code", [""])[0] != "e2e-authorization-code":
                    self._write_json(400, {"error": "invalid_grant"})
                    return

                self._write_json(
                    200,
                    {
                        "access_token": "initial-access-token",
                        "expires_in": 1,
                        "refresh_token": "initial-refresh-token",
                        "x_refresh_token_expires_in": 8726400,
                    },
                )
                return

            if grant_type == "refresh_token":
                if form.get("refresh_token", [""])[0] != "initial-refresh-token":
                    self._write_json(400, {"error": "invalid_grant"})
                    return

                self._write_json(
                    200,
                    {
                        "access_token": "refreshed-access-token",
                        "expires_in": 3600,
                        "refresh_token": "rotated-refresh-token",
                        "x_refresh_token_expires_in": 8726400,
                    },
                )
                return

            self._write_json(400, {"error": "unsupported_grant_type"})
            return

        parsed = urlparse(self.path)
        if parsed.path == "/v3/company/realm-e2e/bill":
            query = parse_qs(parsed.query)
            request_id = query.get("requestid", [""])[0]
            self._record("bill", body)

            if not request_id:
                self._write_json(
                    400,
                    {
                        "Fault": {
                            "Error": [
                                {
                                    "Message": "ValidationFault",
                                    "Detail": "requestid is required for E2E Bill posting",
                                    "code": "E2E-REQUEST-ID",
                                }
                            ],
                            "type": "ValidationFault",
                        }
                    },
                )
                return

            if self.headers.get("Authorization") != "Bearer refreshed-access-token":
                self._write_json(
                    401,
                    {
                        "Fault": {
                            "Error": [
                                {
                                    "Message": "AuthenticationFailed",
                                    "Detail": "Unexpected bearer token",
                                    "code": "3200",
                                }
                            ],
                            "type": "AUTHENTICATION",
                        }
                    },
                )
                return

            try:
                payload = json.loads(body)
            except json.JSONDecodeError:
                self._write_json(400, {"error": "invalid_json"})
                return

            if (
                payload.get("VendorRef", {}).get("value") != "vendor-41"
                or payload.get("APAccountRef", {}).get("value") != "ap-33"
                or payload.get("DocNumber") != "INV-2026-091"
            ):
                self._write_json(
                    400,
                    {
                        "Fault": {
                            "Error": [
                                {
                                    "Message": "ValidationFault",
                                    "Detail": "Unexpected Bill mapping",
                                    "code": "E2E",
                                }
                            ],
                            "type": "ValidationFault",
                        }
                    },
                )
                return

            simulate_lost_response = (
                payload.get("PrivateNote") == "E2E_SIMULATE_LOST_RESPONSE"
            )

            with self.bill_lock:
                existing_bill_id = self.bills_by_request_id.get(request_id)
                if existing_bill_id is None:
                    bill_id = (
                        "QBO-E2E-LOST-1"
                        if simulate_lost_response
                        else "QBO-E2E-1"
                    )
                    self.bills_by_request_id[request_id] = bill_id
                    first_commit = True
                else:
                    bill_id = existing_bill_id
                    first_commit = False

            if simulate_lost_response and first_commit:
                self._record("bill_commit_lost_response", body)
                with self.bill_lock:
                    self.lost_response_request_ids.add(request_id)

                self.close_connection = True
                try:
                    self.connection.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                self.connection.close()
                return

            if simulate_lost_response and not first_commit:
                self._record("bill_replay", body)

            self._write_json(
                200,
                {
                    "Bill": {
                        "Id": bill_id,
                        "SyncToken": "0",
                    }
                },
            )
            return

        self._write_json(404, {"error": "not_found"})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=5100)
    parser.add_argument("--output", required=True)
    parser.add_argument("--client-id", default="e2e-client-id")
    parser.add_argument("--client-secret", default="e2e-client-secret")
    args = parser.parse_args()

    Handler.output_path = Path(args.output)
    Handler.output_path.write_text("", encoding="utf-8")
    credentials = f"{args.client_id}:{args.client_secret}".encode("utf-8")
    Handler.expected_basic = "Basic " + base64.b64encode(credentials).decode("ascii")

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    server.serve_forever()


if __name__ == "__main__":
    main()
