#!/usr/bin/env python3
"""A stand-in `t3 serve`: binds 127.0.0.1:$T3CODE_PORT, answers 200 on /, and
prints the pairing banner the tool captures.

It is exec'd by the real server_runner.sh (deployed into the root by install),
so it proves the installed runner path end to end: config/server-bin ->
execve -> loopback listener -> StandardOutPath banner -> capture_access.
The token value is a sentinel the tests assert is never printed by the tool.
"""
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ["T3CODE_PORT"])
SENTINEL = "FAKE-PAIRING-SECRET-SENTINEL"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 - http.server API
        body = b"ok"
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # silence the access log
        pass


def main():
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    # Bind first, then announce: when wait_http sees 200 the banner is present.
    print("Connection string: fake://loopback", flush=True)
    print(f"Token: {SENTINEL}", flush=True)
    print(f"Pairing URL: http://127.0.0.1:{PORT}/?token={SENTINEL}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
