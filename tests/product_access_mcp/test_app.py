"""Actual MCP HTTP/ASGI and cryptographic auth; synthetic keys and owner payloads only."""
from __future__ import annotations

import asyncio
import dataclasses
import importlib
import importlib.util
import json
import time
import unittest
from datetime import datetime, timezone

import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

from integrations.business_mcp_auth.contracts import load_resource_policy, subject_digest
from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator
from integrations.product_access_mcp.contracts import HttpObservation
from integrations.product_access_mcp.reader import ProductReader

ISSUER = "https://identity.product.example/"
RESOURCE = "https://product.example/mcp"


class Keys:
    def __init__(self, key):
        self.key = key
    async def key_for(self, kid):
        if kid != "fixture-key":
            raise ValueError("synthetic unknown key")
        return self.key


class Audit:
    def __init__(self):
        self.events = []
        self.fail = False
    def emit(self, event):
        if self.fail:
            raise RuntimeError("PRIVATE_AUDIT_FAILURE")
        self.events.append(dataclasses.asdict(event))


class ProductAppTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.assertIsNotNone(importlib.util.find_spec("integrations.product_access_mcp.app"),
                             "Product MCP factory is absent")
        self.module = importlib.import_module("integrations.product_access_mcp.app")
        self.clock = int(time.time())
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(self.key.public_key()))
        public.update(kid="fixture-key", alg="RS256", use="sig")
        self.audit = Audit()
        self.policy = load_resource_policy({
            "schema": "mastermind.business_mcp_auth_policy.v1", "policy_id": "fixture.product.observe",
            "resource": RESOURCE, "resource_metadata_url": "https://product.example/.well-known/oauth-protected-resource/mcp",
            "issuer": ISSUER, "authorization_servers": [ISSUER], "jwks_uri": ISSUER + "jwks",
            "required_scopes": ["product.observe"],
            "allowed_subject_digests": sorted(subject_digest(issuer=ISSUER, subject=u) for u in ("user-a", "user-b")),
            "allowed_algorithms": ["RS256"], "clock_skew_seconds": 0, "max_token_lifetime_seconds": 3600,
            "jwks_cache_ttl_seconds": 60, "unknown_kid_refresh_cooldown_seconds": 1, "fetch_failure_backoff_seconds": 1,
        })
        self.auth = JwtAuthenticator(policy=self.policy, jwks_cache=Keys(public))
        self.calls = []
        self.mode = "normal"
        test = self
        class Port:
            async def read(self, endpoint, *, symbols=()):
                test.calls.append((endpoint, symbols))
                await asyncio.sleep(0)
                if test.mode == "expire":
                    test.clock += 7200
                elif test.mode == "revoke":
                    test.auth._policy = dataclasses.replace(test.policy, allowed_subject_digests=("0" * 64,))
                elif test.mode == "audit-fail":
                    test.audit.fail = True
                if endpoint == "health":
                    payload = {"status": "ok", "commit": "a" * 7, "checkout": "a" * 7}
                else:
                    payload = {"status": "ok", "commit": "a" * 7, "checks": {"quotes": {"status": "missing"}}}
                return HttpObservation(status=200, body=json.dumps(payload).encode(), content_type="application/json")
        self.reader = ProductReader(transport=Port(), now=lambda: datetime.fromtimestamp(self.clock, timezone.utc))
        self.server = self.module.create_product_server(authenticator=self.auth, policy=self.policy,
            now=lambda: self.clock, audit_sink=self.audit, reader=self.reader,
            allowed_hosts=("127.0.0.1", "127.0.0.1:*"))
        self.assertTrue(callable(getattr(self.module, "product_http_app", None)), "bounded HTTP composition is absent")
        self.app = self.module.product_http_app(self.server)
        self.ready, self.stop = asyncio.Event(), asyncio.Event()
        async def lifespan():
            async with self.app.router.lifespan_context(self.app):
                self.ready.set()
                await self.stop.wait()
        self.task = asyncio.create_task(lifespan())
        await asyncio.wait_for(self.ready.wait(), 5)
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://127.0.0.1")

    async def asyncTearDown(self):
        if hasattr(self, "client"):
            await self.client.aclose()
            self.stop.set()
            await asyncio.wait_for(self.task, 5)

    def token(self, **changes):
        claims = {"iss": ISSUER, "aud": RESOURCE, "sub": "user-a", "scope": "product.observe",
                  "iat": self.clock - 1, "exp": self.clock + 600, "client_id": "fixture-client"}
        claims.update(changes)
        return jwt.encode(claims, self.key, algorithm="RS256", headers={"kid": "fixture-key"})

    async def rpc(self, method, params=None, token=None, extra_headers=None):
        headers = {"Accept": "application/json, text/event-stream", "MCP-Protocol-Version": "2025-03-26"}
        if token is not None:
            headers["Authorization"] = "Bearer " + token
        headers.update(extra_headers or {})
        return await self.client.post("/mcp", headers=headers,
            json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}})

    async def read(self, args=None, name="product_diagnostics", token=None):
        return await self.rpc("tools/call", {"name": name, "arguments": args or {}}, token=token or self.token())

    def result(self, response):
        self.assertEqual(response.status_code, 200, response.text[:300])
        return response.json()["result"]

    async def test_actual_initialize_and_exact_read_catalog(self):
        initial = self.result(await self.rpc("initialize", {"protocolVersion": "2025-03-26", "capabilities": {},
            "clientInfo": {"name": "fixture", "version": "1"}}, token=self.token()))
        self.assertEqual(initial["serverInfo"]["name"], "Mastermind Product Observations")
        tools = self.result(await self.rpc("tools/list", token=self.token()))["tools"]
        self.assertEqual([x["name"] for x in tools], ["product_diagnostics", "product_market_pulse"])
        for tool in tools:
            self.assertFalse(tool["inputSchema"]["additionalProperties"])
            self.assertTrue(tool["annotations"]["readOnlyHint"])
            self.assertEqual(tool["_meta"]["securitySchemes"], [{"type": "oauth2", "scopes": ["product.observe"]}])
        self.assertEqual(self.calls, [])

    async def test_catalog_is_compact_without_weakening_output_validation(self):
        tools = self.result(await self.rpc("tools/list", token=self.token()))["tools"]
        self.assertLess(len(json.dumps(tools).encode()), 16000)

    async def test_real_signed_token_invokes_real_projection(self):
        result = self.result(await self.read())
        self.assertFalse(result.get("isError", False))
        self.assertEqual(result["structuredContent"]["schema"], "mastermind.product_observation.v1")
        self.assertEqual(result["structuredContent"]["observations"][0]["data"]["process_revision"], "a" * 7)
        self.assertEqual(self.calls, [("health", ()), ("status", ())])
        self.assertNotIn(self.token(), json.dumps(result))

    async def test_missing_auth_never_reaches_reader(self):
        result = await self.rpc("tools/call", {"name": "product_diagnostics", "arguments": {}})
        self.assertEqual(result.status_code, 401)
        self.assertIn("WWW-Authenticate", result.headers)
        self.assertEqual(self.calls, [])

    async def test_wrong_audience_issuer_scope_subject_expiry_and_signature_refuse(self):
        changes = [{"aud": "https://executive.example/mcp"}, {"iss": "https://other.example"},
                   {"scope": "executive.read"}, {"sub": "unapproved"}, {"exp": self.clock - 1}]
        for change in changes:
            with self.subTest(change=change):
                response = await self.read(token=self.token(**change))
                self.assertIn(response.status_code, (401, 403))
        response = await self.read(token="not-a-token")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(self.calls, [])

    async def test_revoked_policy_before_request_never_enters_backend(self):
        self.auth._policy = dataclasses.replace(self.policy, allowed_subject_digests=("0" * 64,))
        response = await self.read()
        self.assertIn(response.status_code, (401, 403))
        self.assertEqual(self.calls, [])

    async def test_auth_change_during_read_discards_buffered_output(self):
        for mode in ("expire", "revoke", "audit-fail"):
            with self.subTest(mode=mode):
                self.clock = int(time.time())
                self.auth._policy = self.policy
                self.audit.fail = False
                self.mode = mode
                result = self.result(await self.read())
                self.assertTrue(result["isError"])
                self.assertNotIn("structuredContent", result)
                self.assertNotIn("process_revision", json.dumps(result))
                self.assertNotIn("PRIVATE_AUDIT_FAILURE", json.dumps(result))

    async def test_unknown_arguments_identity_and_mutation_tools_are_refused(self):
        for args in ({"url": "https://private.invalid"}, {"user_id": "user-b"}, {"headers": {"Cookie": "PRIVATE"}},
                     {"refresh": True}, {"_meta": {"subject": "user-b"}}):
            with self.subTest(args=args):
                result = self.result(await self.read(args=args))
                self.assertTrue(result["isError"])
                self.assertNotIn("PRIVATE", json.dumps(result))
        result = self.result(await self.read(name="execute_trade"))
        self.assertTrue(result["isError"])
        self.assertEqual(self.calls, [])

    async def test_invalid_symbol_requests_are_closed_before_reader(self):
        for args in ({"symbols": []}, {"symbols": ["SPY", "SPY"]}, {"symbols": [True]},
                     {"symbols": ["SPY"], "url": "https://private.invalid"}):
            with self.subTest(args=args):
                result = self.result(await self.read(name="product_market_pulse", args=args))
                self.assertTrue(result["isError"])
        self.assertEqual(self.calls, [])

    async def test_host_and_origin_refusal(self):
        for headers in ({"Host": "attacker.invalid"}, {"Origin": "https://attacker.invalid"}):
            response = await self.rpc("tools/list", token=self.token(), extra_headers=headers)
            self.assertIn(response.status_code, (400, 403, 421))
        self.assertEqual(self.calls, [])

    async def test_allowed_users_share_only_public_observations_without_private_selector(self):
        responses = await asyncio.gather(self.read(token=self.token(sub="user-a")), self.read(token=self.token(sub="user-b")))
        for response in responses:
            result = self.result(response)
            self.assertFalse(result.get("isError", False))
            for item in result["structuredContent"]["observations"]:
                self.assertEqual(item["access_class"], "public")
        self.assertEqual(len(self.calls), 4)

    async def test_unexpected_output_cannot_expose_private_fields(self):
        async def invalid():
            return {"schema": "mastermind.product_observation.v1", "tool": "product_diagnostics",
                    "observations": [], "limitations": [], "cookie": "PRIVATE_COOKIE"}
        self.reader.diagnostics = invalid
        result = self.result(await self.read())
        self.assertTrue(result["isError"])
        self.assertNotIn("PRIVATE_COOKIE", json.dumps(result))

    async def test_private_values_inside_data_are_refused_by_output_schema(self):
        original = self.reader.diagnostics
        async def invalid():
            result = await original()
            result["observations"][0]["data"]["cookie"] = "PRIVATE_COOKIE"
            return result
        self.reader.diagnostics = invalid
        result = self.result(await self.read())
        self.assertTrue(result["isError"])
        self.assertNotIn("PRIVATE_COOKIE", json.dumps(result))

    async def test_raw_body_bound_runs_before_auth_and_sdk_json_parsing(self):
        for raw in (b"x" * 65537, b"{\"PRIVATE_BODY\":\"" + b"x" * 65536):
            response = await self.client.post("/mcp", content=raw, headers={"Content-Type": "application/json"})
            self.assertEqual(response.status_code, 413)
            self.assertNotIn("PRIVATE_BODY", response.text)
        self.assertEqual(self.calls, [])
        self.assertEqual(self.audit.events, [])

    async def test_streamed_body_limit_does_not_trust_declared_length(self):
        async def body():
            yield b"x" * 32768
            yield b"x" * 32769
        response = await self.client.post("/mcp", content=body(), headers={"Content-Length": "1"})
        self.assertEqual(response.status_code, 413)
        self.assertEqual(self.calls, [])

    async def test_disconnected_request_and_receive_deadline_are_bounded(self):
        from unittest.mock import patch
        from integrations.executive_mcp import e1_http
        scope = {"type": "http", "method": "POST", "path": "/mcp", "headers": []}
        for mode in ("disconnect", "stall"):
            with self.subTest(mode=mode):
                sent = []
                async def receive():
                    if mode == "stall":
                        await asyncio.sleep(5)
                    return {"type": "http.disconnect"}
                async def send(value):
                    sent.append(value)
                with patch.object(e1_http, "PREAUTH_RECEIVE_DEADLINE_SECONDS", 0.01):
                    await asyncio.wait_for(self.app(scope, receive, send), timeout=1)
                self.assertEqual(sent[0]["status"], 400)
        self.assertEqual(self.calls, [])

    async def test_factory_refuses_sdk_normalization_of_verified_issuer(self):
        issuer = ISSUER.rstrip("/")
        policy = dataclasses.replace(self.policy, issuer=issuer, authorization_servers=(issuer,))
        auth = JwtAuthenticator(policy=policy, jwks_cache=Keys({}))
        with self.assertRaisesRegex(ValueError, "SDK URL"):
            self.module.create_product_server(authenticator=auth, policy=policy, now=lambda: self.clock,
                audit_sink=self.audit, reader=self.reader, allowed_hosts=("127.0.0.1",))

    async def test_factory_refuses_policy_metadata_the_sdk_would_not_advertise(self):
        policy = dataclasses.replace(self.policy,
            resource_metadata_url="https://product.example/.well-known/oauth-protected-resource/wrong")
        auth = JwtAuthenticator(policy=policy, jwks_cache=Keys({}))
        with self.assertRaisesRegex(ValueError, "SDK metadata"):
            self.module.create_product_server(authenticator=auth, policy=policy, now=lambda: self.clock,
                audit_sink=self.audit, reader=self.reader, allowed_hosts=("127.0.0.1",))

    async def test_existing_sdk_resource_metadata_matches_exact_resource(self):
        response = await self.client.get("/.well-known/oauth-protected-resource/mcp")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["resource"], RESOURCE)
        self.assertEqual(response.json()["authorization_servers"], [ISSUER])
        self.assertEqual(self.calls, [])

    async def test_catalog_schema_snapshot_is_pinned(self):
        from integrations.product_access_mcp.schemas import SCHEMA_SNAPSHOT_SHA256, TOOL_SPECS
        self.assertEqual(SCHEMA_SNAPSHOT_SHA256, "fbf9ae8b688264d0772a3c64ca4327ad4afe4adf2f4be948e5a72f6efc6b8123")
        tools = self.result(await self.rpc("tools/list", token=self.token()))["tools"]
        self.assertEqual(tools, list(TOOL_SPECS))

    async def test_entire_stack_uses_real_http_without_any_production_network(self):
        import threading
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        from .test_transport import Bridge
        from .test_observations import pulse
        from integrations.product_access_mcp.transport import PublicTransport
        hits, seen = [], []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass
            def do_GET(self):
                hits.append(self.path)
                if self.path.startswith("/api/intelligence-hub/market-pulse"):
                    value = pulse()
                elif self.path == "/api/health":
                    value = {"status": "ok", "commit": "a" * 7, "checkout": "b" * 7}
                else:
                    value = {"status": "ok", "commit": "a" * 7, "checks": {"terminal_data": {"status": "missing"}}}
                body = json.dumps(value).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
        host = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=host.serve_forever, daemon=True)
        thread.start()
        self.reader._transport = PublicTransport(transport_factory=lambda: Bridge(host.server_port, seen))
        try:
            rejected = await self.read(token=self.token(sub="unapproved"))
            self.assertEqual(rejected.status_code, 401)
            self.assertEqual(hits, [])
            diagnostics = self.result(await self.read())
            self.assertFalse(diagnostics.get("isError", False), diagnostics)
            self.assertTrue(diagnostics["structuredContent"]["observations"][0]["data"]["checkout_drift"])
            quotes = self.result(await self.read(name="product_market_pulse", args={"symbols": ["SPY"]}))
            self.assertFalse(quotes.get("isError", False), quotes)
            self.assertEqual(quotes["structuredContent"]["observations"][0]["data"]["items"][0]["symbol"], "SPY")
            self.assertEqual(len(hits), 3)
            for request in seen:
                self.assertNotIn("authorization", request["headers"])
                self.assertNotIn("cookie", request["headers"])
        finally:
            host.shutdown()
            host.server_close()
            thread.join(timeout=2)

    async def test_factory_rejects_wrong_scope_and_absent_host_policy(self):
        for policy, hosts in [(dataclasses.replace(self.policy, required_scopes=("executive.read",)), ("127.0.0.1",)),
                              (self.policy, ())]:
            with self.subTest(hosts=hosts):
                with self.assertRaises(ValueError):
                    self.module.create_product_server(authenticator=self.auth, policy=policy, now=lambda: self.clock,
                        audit_sink=self.audit, reader=self.reader, allowed_hosts=hosts)
