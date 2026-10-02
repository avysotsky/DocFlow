#!/usr/bin/env python3
import argparse
import hashlib
import hmac
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock

def parse_args():
    parser=argparse.ArgumentParser()
    parser.add_argument("--host",default="127.0.0.1")
    parser.add_argument("--port",type=int,default=5099)
    parser.add_argument("--output",required=True)
    return parser.parse_args()

class ReceiverState:
    def __init__(self,output,secret):
        self.output=output
        self.secret=secret
        self.lock=Lock()
        self.attempts={}

    def record(self,entry):
        with self.lock:
            with self.output.open("a",encoding="utf-8") as handle:
                handle.write(json.dumps(entry,separators=(",",":"))+"\n")

class Handler(BaseHTTPRequestHandler):
    server_version="DocFlowWebhookE2E/1.0"

    def do_GET(self):
        self.send_response(204 if self.path=="/health" else 404)
        self.end_headers()

    def do_POST(self):
        if self.path!="/webhook":
            self.send_response(404); self.end_headers(); return
        state=self.server.receiver_state
        length=int(self.headers.get("Content-Length","0"))
        if length<=0 or length>65536:
            self.send_response(413); self.end_headers(); return
        body=self.rfile.read(length)
        expected="sha256="+hmac.new(state.secret,body,hashlib.sha256).hexdigest()
        presented=self.headers.get("X-DocFlow-Signature","")
        signature_valid=hmac.compare_digest(expected,presented)
        try:
            payload=json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError,json.JSONDecodeError):
            payload=None
        event_id=payload.get("eventId") if isinstance(payload,dict) else None
        header_event_id=self.headers.get("X-DocFlow-Event-Id")
        header_matches=bool(event_id) and header_event_id==event_id
        if not signature_valid or not header_matches:
            response_code=401; attempt=0
        else:
            with state.lock:
                attempt=state.attempts.get(event_id,0)+1
                state.attempts[event_id]=attempt
            if payload.get("documentType")=="force_webhook_failure":
                response_code=500
            elif payload.get("status")=="NeedsReview" and attempt==1:
                response_code=500
            else:
                response_code=204
        state.record({"eventId":event_id,"headerEventId":header_event_id,"signatureValid":signature_valid,"headerMatches":header_matches,"attempt":attempt,"responseCode":response_code,"payload":payload})
        self.send_response(response_code)
        self.end_headers()

    def log_message(self,format,*args):
        return

def main():
    args=parse_args()
    output=Path(args.output)
    output.write_text("",encoding="utf-8")
    secret=os.environ["DOCFLOW_WEBHOOK_SECRET"].encode("utf-8")
    server=ThreadingHTTPServer((args.host,args.port),Handler)
    server.receiver_state=ReceiverState(output,secret)
    server.serve_forever()

if __name__=="__main__":
    main()
