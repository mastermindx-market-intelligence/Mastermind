#!/usr/bin/env python3
"""A stand-in `t3 serve` that binds slowly (3 s) — long enough for a foreign
listener to win the recorded port AFTER install's port_busy pre-check (the
panel R4 race). If the port is gone by then it dies on EADDRINUSE exactly as
the real server would (launchd then crash-loops it); if it wins the race it
serves 200 and prints the banner like the normal fake server.
"""
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

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
    port = int(os.environ["T3CODE_PORT"])
    time.sleep(6.0)
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print("Connection string: fake://loopback", flush=True)
    print(f"Token: {SENTINEL}", flush=True)
    print(f"Pairing URL: http://127.0.0.1:{port}/?token={SENTINEL}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
