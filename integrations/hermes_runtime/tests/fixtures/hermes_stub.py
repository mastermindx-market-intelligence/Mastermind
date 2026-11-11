#!/usr/bin/env python3
"""Stand-in for the pinned Hermes CLI. It never opens a public socket."""
from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import sys
import threading
import time


def main() -> int:
    args = sys.argv[1:]
    if args and args[0] == "-p":
        if len(args) < 3:
            return 2
        args = args[2:]
    if args[:4] == ["tools", "list", "--platform", "cli"]:
        stderr = os.environ.get("HERMES_STUB_STDERR", "")
        if stderr:
            sys.stderr.write(stderr)
        fixture = os.environ.get("HERMES_STUB_TOOLS")
        if not fixture:
            sys.stderr.write("FIXTURE_TOOLS_NOT_SET")
            return 2
        sys.stdout.write(Path(fixture).read_text(encoding="utf-8"))
        return 0
    if args and args[0] == "serve":
        host = _flag(args, "--host")
        if host not in {"127.0.0.1", "127.0.0.2", "127.0.0.3"}:
            sys.stderr.write("NON_LOOPBACK\n")
            return 2
        mode = os.environ.get("HERMES_STUB_MODE")
        if mode == "exit":
            _count()
            return 1
        if mode != "silent":
            port = int(_flag(args, "--port"))
            if not 1024 <= port <= 65535:
                return 2

            class Health(BaseHTTPRequestHandler):
                def do_GET(self) -> None:  # noqa: N802
                    code = 503 if mode == "unhealthy" else 200
                    if self.path != "/api/health":
                        code = 404
                    if code != 200:
                        body = b'{"status":"unavailable"}'
                    elif mode == "bad-json":
                        body = b'{"ok":'
                    elif mode == "missing-commit":
                        body = b'{"ok":true}'
                    else:
                        commit = ("f" * 40 if mode == "wrong-commit"
                                  else os.environ.get("HERMES_STUB_COMMIT", ""))
                        payload = {"ok": True, "commit": commit, "auth_required": False}
                        if mode == "oversized":
                            payload["padding"] = "a" * 5000
                        body = json.dumps(payload).encode("utf-8")
                    self.send_response(code)
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)

                def log_message(self, *args) -> None:
                    pass

            httpd = HTTPServer((host, port), Health)
            threading.Thread(target=httpd.serve_forever, daemon=True).start()
        ready = os.environ.get("HERMES_STUB_READY")
        if ready:
            payload = {"pid": os.getpid(), "argv": args, "env_keys": sorted(os.environ)}
            tmp = ready + ".tmp"
            Path(tmp).write_text(json.dumps(payload), encoding="utf-8")
            os.replace(tmp, ready)
        _count()
        while True:
            time.sleep(0.2)
    sys.stderr.write("STUB_USAGE\n")
    return 2


def _flag(args: list[str], name: str) -> str:
    if name not in args:
        return ""
    index = args.index(name)
    if index + 1 >= len(args):
        return ""
    return args[index + 1]


def _count() -> None:
    path = os.environ.get("HERMES_STUB_COUNT")
    if not path:
        return
    file = Path(path)
    current = int(file.read_text(encoding="utf-8") or "0") if file.exists() else 0
    file.write_text(str(current + 1), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
