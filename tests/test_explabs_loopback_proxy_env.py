"""Offline credential-custody regression for shared-gateway loopback traffic.

The fake ambient HTTP proxy is a localhost fixture. No provider/network requests
or actual credentials are used. Both GET metadata and POST completion must bypass
HTTP_PROXY and lowercase http_proxy in production's default (uninjected) client.
"""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import socket
import threading

import httpx
import pytest

from brain import explabs_client, explabs_pool


SCOPED = "scoped-fixture-token-never-to-an-ambient-proxy"


def _closed_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_brain_local_gateway_get_and_post_ignore_ambient_proxy(monkeypatch):
    observed = []

    class FakeAmbientProxy(BaseHTTPRequestHandler):
        def _capture(self):
            observed.append({
                "method": self.command,
                "path": self.path,
                "had_bearer": self.headers.get("Authorization") == "Bearer " + SCOPED,
            })
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.end_headers()
            self.wfile.write(b"{}")

        def do_GET(self):
            self._capture()

        def do_POST(self):
            self._capture()

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeAmbientProxy)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        proxy_url = f"http://127.0.0.1:{server.server_address[1]}"
        # Different process environments select upper-/lowercase variants.
        for name in ("HTTP_PROXY", "http_proxy"):
            monkeypatch.setenv(name, proxy_url)
        for name in ("ALL_PROXY", "all_proxy", "NO_PROXY", "no_proxy"):
            monkeypatch.setenv(name, "")
        local_origin = f"http://127.0.0.1:{_closed_loopback_port()}"

        # No server is bound to local_origin. If a default HTTPX client follows
        # HTTP_PROXY, our fixture proxy captures the bearer instead of refusing.
        with pytest.raises(explabs_client.ExperientialError) as post_error:
            explabs_client.chat_completion(
                [{"role": "user", "content": "local-only fixture"}],
                api_key=SCOPED, shared_gateway_origin=local_origin, max_tokens=8,
            )
        assert str(post_error.value) == "explabs_transport_error"

        with pytest.raises(explabs_client.ExperientialError) as get_error:
            explabs_pool.AccountPool()._get(local_origin + "/api/whoami", SCOPED)
        assert str(get_error.value) == "explabs_probe_transport_error"

        assert observed == [], "local gateway bearer was sent to an ambient proxy"
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)


def test_shared_gateway_rejects_redirect_before_decoding(monkeypatch):
    monkeypatch.delenv("EXPLABS_API_KEY", raising=False)

    def fixture(req: httpx.Request):
        assert req.headers["authorization"] == "Bearer " + SCOPED
        return httpx.Response(302, headers={"location": "https://untrusted.invalid/"})

    with httpx.Client(transport=httpx.MockTransport(fixture), follow_redirects=False) as client:
        with pytest.raises(
            explabs_client.ExperientialError, match="explabs_upstream_redirect_refused"
        ) as exc:
            explabs_client.chat_completion(
                [{"role": "user", "content": "fixture"}],
                client=client, api_key=SCOPED,
                shared_gateway_origin="http://127.0.0.1:18311",
                max_tokens=8,
            )
    assert exc.value.status == 302
