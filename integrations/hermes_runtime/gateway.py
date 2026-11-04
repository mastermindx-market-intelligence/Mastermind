"""Authenticated loopback front door. The socket is created only for 127.0.0.1."""
from __future__ import annotations

from collections.abc import Callable
import hmac
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import socket
import threading
import urllib.parse

from .constants import DASHBOARD_PATH, HEALTH_PATH, LOOPBACK_HOST
from .errors import RuntimeRefusal


def reserve_loopback_port() -> int:
    """Bind 127.0.0.1:0 and release it. Callers accept the small race."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind((LOOPBACK_HOST, 0))
        return int(sock.getsockname()[1])
    finally:
        sock.close()


def token_matches(presented: str, expected: str) -> bool:
    if not isinstance(presented, str) or not isinstance(expected, str):
        return False
    return hmac.compare_digest(presented.encode("utf-8"), expected.encode("utf-8"))


class _LoopbackServer(ThreadingHTTPServer):
    allow_reuse_address = False
    daemon_threads = True
    request_queue_size = 16


class Gateway:
    def __init__(self, host: str, port: int, token: str, snapshot: Callable[[], tuple[int, dict]]):
        if host != LOOPBACK_HOST:
            raise RuntimeRefusal("NON_LOOPBACK_BIND_REFUSED")
        if not token:
            raise RuntimeRefusal("SECRETS_TOKEN_MISSING")
        self._token = token
        self._snapshot = snapshot
        handler = _handler_factory(self)
        self._httpd = _LoopbackServer((host, port), handler)
        bound_host, bound_port = self._httpd.socket.getsockname()[:2]
        if bound_host != LOOPBACK_HOST:
            self._httpd.server_close()
            raise RuntimeRefusal("NON_LOOPBACK_BIND_REFUSED")
        self.host = bound_host
        self.port = bound_port
        self._started = threading.Event()
        self._thread = threading.Thread(target=self._serve, name="hermes-runtime-gateway", daemon=True)
        self._thread.start()
        if not self._started.wait(timeout=2):
            self.close()
            raise RuntimeRefusal("GATEWAY_START_FAILED")

    def close(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()
        self._thread.join(timeout=2)

    def _serve(self) -> None:
        self._started.set()
        self._httpd.serve_forever(poll_interval=0.05)


def _handler_factory(gateway: Gateway) -> type[BaseHTTPRequestHandler]:
    token = gateway._token
    snapshot = gateway._snapshot

    class Handler(BaseHTTPRequestHandler):
        server_version = "hermes-runtime"
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt: str, *args) -> None:
            return None

        def do_GET(self) -> None:  # noqa: N802
            parsed = urllib.parse.urlsplit(self.path)
            if parsed.query or parsed.fragment:
                self._send(400, b'{"status":"query_refused"}', "application/json")
                return
            header = self.headers.get("Authorization", "")
            presented = header[7:] if header.startswith("Bearer ") else None
            if presented is None or not token_matches(presented, token):
                self._send(401, b'{"status":"unauthorized"}', "application/json")
                return
            if parsed.path == HEALTH_PATH:
                code, payload = snapshot()
                body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
                if token.encode("utf-8") in body:
                    self._send(500, b'{"status":"health_redacted"}', "application/json")
                    return
                self._send(code, body, "application/json")
                return
            if parsed.path == DASHBOARD_PATH:
                text = snapshot()[1]
                body = (
                    "hermes-runtime\n"
                    f"role={text.get('role', '')}\n"
                    f"sha={text.get('pinned_sha', '')}\n"
                    "loopback=127.0.0.1\n"
                    "auth=required\n"
                ).encode("utf-8")
                if token.encode("utf-8") in body:
                    self._send(500, b"health_redacted\n", "text/plain; charset=utf-8")
                    return
                self._send(200, body, "text/plain; charset=utf-8")
                return
            self._send(404, b'{"status":"not_found"}', "application/json")

        def do_POST(self) -> None:  # noqa: N802
            self._send(405, b'{"status":"method_refused"}', "application/json")

        def _send(self, code: int, body: bytes, content_type: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

    return Handler
