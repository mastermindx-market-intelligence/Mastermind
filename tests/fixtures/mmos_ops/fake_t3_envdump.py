#!/usr/bin/env python3
"""fake_t3_envdump — the fake t3 server that also records its own environment.

Item F: the runner must put the recorded provider CLI folder on the PATH the
server process runs with. This stub binds, answers 200, prints the pairing
banner (so install's capture sees the usual lines) and writes the environment
it was exec'd with to `env-dump.json` in its working directory — the runner
chdirs to <root>/scratch-project before exec, so that is where the test finds
it. PATH is the decisive field: the provider probe spawns `claude --version`
against this exact PATH.
"""
import json
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
    try:
        with open("env-dump.json", "w", encoding="utf-8") as stream:
            json.dump({"PATH": os.environ.get("PATH", ""),
                       "T3CODE_PORT": os.environ.get("T3CODE_PORT", "")},
                      stream)
    except OSError:
        pass
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    # Bind first, then announce: when wait_http sees 200 the banner is present.
    print("Connection string: fake://loopback", flush=True)
    print(f"Token: {SENTINEL}", flush=True)
    print(f"Pairing URL: http://127.0.0.1:{PORT}/?token={SENTINEL}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
