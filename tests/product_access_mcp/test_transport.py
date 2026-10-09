"""Real loopback HTTP boundary. A fixture bridge never resolves production DNS."""
from __future__ import annotations

import importlib
import importlib.util
import json
import os
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

import httpx


class Bridge(httpx.AsyncBaseTransport):
    def __init__(self, port, seen):
        self.port, self.seen = port, seen
        self.inner = httpx.AsyncHTTPTransport(retries=0)

    async def handle_async_request(self, request):
        self.seen.append({"url": str(request.url), "headers": dict(request.headers)})
        target = httpx.URL(f"http://127.0.0.1:{self.port}").copy_with(raw_path=request.url.raw_path)
        local = httpx.Request(request.method, target, headers=request.headers,
                             stream=request.stream, extensions=request.extensions)
        return await self.inner.handle_async_request(local)

    async def aclose(self):
        await self.inner.aclose()


class TransportTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec("integrations.product_access_mcp.transport"),
                             "PublicTransport implementation is absent")
        self.module = importlib.import_module("integrations.product_access_mcp.transport")
        self.seen = []
        self.hits = []
        self.mode = "ok"
        test = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass
            def do_GET(self):
                test.hits.append(self.path)
                if test.mode == "disconnect":
                    self.connection.close()
                    return
                code = {"redirect": 302, "denied": 403, "missing": 404, "limited": 429}.get(test.mode, 200)
                body = b'{"status":"ok","commit":"abcdef0","checkout":"abcdef0"}'
                if test.mode == "large":
                    body = b"x" * (256 * 1024 + 1)
                self.send_response(code)
                self.send_header("Content-Type", "text/html" if test.mode == "html" else "application/json")
                self.send_header("Set-Cookie", "private_fixture=PRIVATE_COOKIE")
                if code == 302:
                    self.send_header("Location", "https://unapproved.invalid/secret")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                try:
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    pass
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.transport = self.module.PublicTransport(transport_factory=lambda: Bridge(self.server.server_port, self.seen))

    def tearDown(self):
        if hasattr(self, "server"):
            self.server.shutdown()
            self.server.server_close()
            self.thread.join(timeout=2)

    async def test_fixed_gets_never_send_auth_or_cookie(self):
        with patch.dict(os.environ, {"HTTPS_PROXY": "http://127.0.0.1:9", "HTTP_PROXY": "http://127.0.0.1:9"}):
            first = await self.transport.read("health")
            second = await self.transport.read("status")
        self.assertEqual(first.status, 200)
        self.assertEqual(second.status, 200)
        self.assertEqual(self.hits, ["/api/health", "/api/status"])
        for row in self.seen:
            self.assertTrue(row["url"].startswith("https://www.mastermind-x.com/api/"))
            self.assertNotIn("authorization", row["headers"])
            self.assertNotIn("cookie", row["headers"])
            self.assertNotIn("proxy-authorization", row["headers"])

    async def test_query_is_fixed_and_symbols_encoded(self):
        result = await self.transport.read("market_pulse", symbols=("SPY", "BRK.B"))
        self.assertEqual(result.status, 200)
        self.assertEqual(self.hits, ["/api/intelligence-hub/market-pulse?symbols=SPY%2CBRK.B"])

    async def test_unknown_endpoint_or_extra_query_never_opens_socket(self):
        for endpoint, symbols in [("https://evil.invalid", ()), ("health", ("SPY",)), ("market_pulse", ("SPY&x=y",))]:
            with self.subTest(endpoint=endpoint):
                with self.assertRaises(ValueError):
                    await self.transport.read(endpoint, symbols=symbols)
        self.assertEqual(self.hits, [])
        self.assertEqual(self.seen, [])

    async def test_redirect_is_not_followed_or_retried(self):
        self.mode = "redirect"
        result = await self.transport.read("health")
        self.assertEqual(result.status, 302)
        self.assertEqual(result.error, "redirect_refused")
        self.assertEqual(self.hits, ["/api/health"])

    async def test_denial_missing_and_rate_limit_preserve_status_without_retry(self):
        for mode, status in [("denied", 403), ("missing", 404), ("limited", 429)]:
            with self.subTest(mode=mode):
                self.mode = mode
                result = await self.transport.read("health")
                self.assertEqual(result.status, status)
        self.assertEqual(len(self.hits), 3)

    async def test_oversized_and_html_bodies_are_not_returned(self):
        for mode, error in [("large", "response_too_large"), ("html", "invalid_content_type")]:
            with self.subTest(mode=mode):
                self.mode = mode
                result = await self.transport.read("health")
                self.assertEqual(result.error, error)
                self.assertEqual(result.body, b"")

    async def test_connection_loss_is_one_attempt_without_raw_exception(self):
        self.mode = "disconnect"
        result = await self.transport.read("health")
        self.assertEqual(result.error, "backend_unavailable")
        self.assertEqual(self.hits, ["/api/health"])
        self.assertEqual(result.body, b"")

    async def test_timeout_has_closed_error(self):
        async def timeout(request):
            raise httpx.ReadTimeout("PRIVATE_EXCEPTION")
        transport = self.module.PublicTransport(transport_factory=lambda: httpx.MockTransport(timeout))
        result = await transport.read("health")
        self.assertEqual(result.error, "timeout")
        self.assertNotIn("PRIVATE_EXCEPTION", repr(result))
