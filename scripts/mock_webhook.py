#!/usr/bin/env python3
"""Mock webhook server for testing notification delivery."""

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Lock
from urllib.parse import urlparse

# Thread-safe storage for received requests
received_requests = []
received_lock = Lock()


class WebhookHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        path = urlparse(self.path).path

        if path == "/hook":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)

            with received_lock:
                received_requests.append({
                    "method": "POST",
                    "path": path,
                    "headers": dict(self.headers),
                    "body": body.decode("utf-8", errors="replace"),
                    "timestamp": str(__import__("datetime").datetime.utcnow().isoformat()),
                })

            self.send_response(202)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "received"}).encode())

        elif path == "/_reset":
            with received_lock:
                received_requests.clear()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "reset"}).encode())

        else:
            self.send_response(404)
            self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path

        if path == "/_received":
            with received_lock:
                data = json.dumps(received_requests, indent=2)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(data.encode())

        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        # Suppress default logging
        pass


def run_server(host="0.0.0.0", port=8899):
    server = HTTPServer((host, port), WebhookHandler)
    print(f"Mock webhook server listening on {host}:{port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...", flush=True)
        server.shutdown()


if __name__ == "__main__":
    run_server()
