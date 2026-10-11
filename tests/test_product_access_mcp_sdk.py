"""Real MCP SDK / ASGI / signed-token transport tests with disposable JWTs.

Fixture product grants and static public responses are NOT production identity
linking, installed tunnel acceptance, or real-account login.
"""
from __future__ import annotations

import asyncio
import dataclasses
import json
import time
import unittest
from datetime import datetime, timedelta, timezone

import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

from integrations.business_mcp_auth.contracts import load_resource_policy, subject_digest
from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator
from integrations.product_access_mcp.app import create_authenticated_product_server
from integrations.product_access_mcp.contracts import ProductRefused, READ_SCOPE, SOURCES
from integrations.product_access_mcp.observer import HttpPayload, product_observe

ISSUER = "https://identity.product-fixture.example"
RESOURCE = "https://product-fixture.example/mcp"


class Keys:
    def __init__(self, jwk):
        self.jwk = jwk
    async def key_for(self, kid):
        if kid != "product-test":
            raise ValueError("unknown key")
        return self.jwk


class Audit:
    def __init__(self):
        self.events = []
    def emit(self, event):
        self.events.append(dataclasses.asdict(event))


class ProductAppTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.clock = int(time.time())
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.private = key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption())
        jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
        jwk.update(kid="product-test", alg="RS256", use="sig")
        self.subject_a = subject_digest(issuer=ISSUER, subject="product-a")
        self.subject_b = subject_digest(issuer=ISSUER, subject="product-b")
        self.policy = load_resource_policy({
            "schema": "mastermind.business_mcp_auth_policy.v1",
            "policy_id": "fixture.product.read",
            "resource": RESOURCE,
            "resource_metadata_url": "https://product-fixture.example/.well-known/oauth-protected-resource/mcp",
            "issuer": ISSUER,
            "authorization_servers": [ISSUER],
            "jwks_uri": ISSUER + "/jwks",
            "required_scopes": [READ_SCOPE],
            "allowed_subject_digests": [self.subject_a, self.subject_b],
            "allowed_algorithms": ["RS256"],
            "clock_skew_seconds": 0,
            "max_token_lifetime_seconds": 3600,
            "jwks_cache_ttl_seconds": 60,
            "unknown_kid_refresh_cooldown_seconds": 1,
            "fetch_failure_backoff_seconds": 1,
        })
        self.keys = Keys(jwk)
        self.auth = JwtAuthenticator(policy=self.policy, jwks_cache=self.keys)
        self.audit = Audit()
        self.reads = 0
        self.grant_checks = 0
        self.mode = "normal"
        self.granted = {self.subject_a}
        self.outcome = []
        def final_authorization(caller, request):
            self.grant_checks += 1
            if caller.subject_digest not in self.granted:
                raise ProductRefused("PRODUCT_GRANT_CHANGED")
            captured = (caller, tuple(sorted(request.items())))
            def revalidate():
                self.grant_checks += 1
                if caller.subject_digest not in self.granted or (
                    caller, tuple(sorted(request.items()))) != captured:
                    raise ProductRefused("PRODUCT_GRANT_CHANGED")
            return revalidate

        async def read_port(caller, request):
            self.reads += 1
            if self.mode == "error":
                raise RuntimeError("PRIVATE_NETWORK_EXCEPTION_AND_API_KEY")
            if self.mode == "revoke":
                self.granted.clear()
            if self.mode == "expire":
                self.clock += 7200
            if self.mode == "cross-source":
                return product_observe(caller,
                    {"product": "macro", "view": "status"},
                    datetime.now(timezone.utc), getter)
            if self.mode == "malformed":
                return {"data": {"private": "PRIVATE_SECRET"}}
            await asyncio.sleep(0)
            response = product_observe(caller, request, datetime.now(timezone.utc), getter)
            if self.mode == "fake-healthy":
                response["data"] = {}
            return response

        def getter(url, cap):
            now = datetime.now(timezone.utc)
            day = now.astimezone(__import__("zoneinfo").ZoneInfo("America/New_York")).date().isoformat()
            if url == SOURCES[("terminal", "market_risk")][1]:
                data = {
                    "schema": "market_risk/v1", "verdict": "MIXED", "score": 48,
                    "asof": day, "stale": False,
                    "stale_after": (now + timedelta(hours=1)).isoformat(),
                    "is_display_only": True,
                    "freshness": {"qualified": True, "reasons": []},
                }
            else:
                data = {"status": "ok", "commit": "server123", "checks": {"site": {"commit": "site123"}}}
            raw = json.dumps(data).encode("utf-8")
            return HttpPayload(200, raw, {"content-type": "application/json",
                                          "content-length": str(len(raw))})

        self.server = create_authenticated_product_server(
            authenticator=self.auth, policy=self.policy,
            now=lambda: self.clock, audit_sink=self.audit,
            read_port=read_port, final_authorization=final_authorization,
            allowed_hosts=("127.0.0.1", "127.0.0.1:*"),
        )
        self.app = self.server.streamable_http_app()
        self.started = asyncio.Event()
        self.stop = asyncio.Event()
        async def lifetime():
            async with self.app.router.lifespan_context(self.app):
                self.started.set()
                await self.stop.wait()
        self.owner = asyncio.create_task(lifetime())
        await asyncio.wait_for(self.started.wait(), timeout=5)
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app),
                                        base_url="http://127.0.0.1")

    async def asyncTearDown(self):
        await self.client.aclose()
        self.stop.set()
        await asyncio.wait_for(self.owner, timeout=5)

    def token(self, user="product-a", **claims):
        data = {
            "iss": ISSUER, "sub": user, "aud": RESOURCE,
            "iat": self.clock - 1, "exp": self.clock + 600,
            "scope": READ_SCOPE, "client_id": "product-test-client",
        }
        data.update(claims)
        return jwt.encode(data, self.private, algorithm="RS256",
                          headers={"kid": "product-test"})

    async def rpc(self, method, params=None, token=None, origin=None):
        headers = {"Accept": "application/json, text/event-stream",
                   "MCP-Protocol-Version": "2025-03-26"}
        if token is not None:
            headers["Authorization"] = "Bearer " + token
        if origin:
            headers["Origin"] = origin
        return await self.client.post("/mcp", headers=headers, json={
            "jsonrpc": "2.0", "id": 1, "method": method, "params": params or {},
        })

    async def call(self, args=None, name="product_observe", token=None):
        if args is None:
            args = {"product": "terminal", "view": "market_risk"}
        return await self.rpc("tools/call", {"name": name, "arguments": args},
                              token=self.token() if token is None else token)

    def parsed(self, res):
        self.assertEqual(res.status_code, 200, res.text[:250])
        data = res.json()
        self.assertIn("result", data, data)
        return data["result"]

    async def test_protocol_initialize_native_sdk(self):
        response = await self.rpc("initialize", {
            "protocolVersion": "2025-03-26", "capabilities": {},
            "clientInfo": {"name": "canary", "version": "1"},
        }, token=self.token())
        self.assertIn("serverInfo", self.parsed(response))

    async def test_two_static_discovered_read_only_tools(self):
        result = self.parsed(await self.rpc("tools/list", token=self.token()))
        self.assertEqual([x["name"] for x in result["tools"]],
                         ["product_manifest", "product_observe"])
        for tool in result["tools"]:
            self.assertTrue(tool["annotations"]["readOnlyHint"])
            self.assertFalse(tool["annotations"]["destructiveHint"])
            self.assertFalse(tool["inputSchema"]["additionalProperties"])
        self.assertEqual(self.reads, 0)

    async def test_authenticated_product_observation(self):
        result = self.parsed(await self.call())
        self.assertFalse(result.get("isError"))
        data = result["structuredContent"]
        self.assertEqual(data["status"], "OK")
        self.assertEqual(data["data"]["verdict"], "MIXED")
        self.assertEqual(data["source"]["source_id"], "terminal.public_risk_projection")
        self.assertEqual(self.reads, 1)
        self.assertGreaterEqual(self.grant_checks, 2)

    async def test_manifest_never_reads_upstream(self):
        result = self.parsed(await self.call({}, name="product_manifest"))
        self.assertFalse(result.get("isError"))
        self.assertEqual(len(result["structuredContent"]["data"]["views"]), 3)
        self.assertEqual(self.reads, 0)

    async def test_valid_token_without_product_grant_refuses(self):
        result = self.parsed(await self.call(token=self.token("product-b")))
        self.assertTrue(result["isError"])
        self.assertEqual(self.reads, 0)

    async def test_no_token_refuses_before_port(self):
        res = await self.rpc("tools/call", {"name": "product_observe", "arguments": {
            "product": "terminal", "view": "market_risk",
        }})
        self.assertEqual(res.status_code, 401)
        self.assertEqual(self.reads, 0)

    async def test_wrong_issuer_audience_and_scope_refuse(self):
        for changes in (
            {"iss": "https://different.example"},
            {"aud": "https://executive.example/mcp"},
            {"scope": "mastermind.executive.read"},
            {"scope": READ_SCOPE + " mastermind.executive.read"},
        ):
            res = await self.call(token=self.token(**changes))
            self.assertEqual(res.status_code, 401, res.text[:120])
        self.assertEqual(self.reads, 0)

    async def test_argument_cannot_supply_other_url_or_cookie(self):
        res = self.parsed(await self.call({
            "product": "terminal", "view": "market_risk",
            "url": "http://169.254.169.254", "cookie": "private",
        }))
        self.assertTrue(res["isError"])
        self.assertEqual(self.reads, 0)

    async def test_revocation_mid_await_withholds_result(self):
        self.mode = "revoke"
        res = self.parsed(await self.call())
        self.assertTrue(res["isError"])
        self.assertNotIn('"verdict"', json.dumps(res))
        self.assertEqual(self.reads, 1)

    async def test_expired_token_after_await_withholds_result(self):
        self.mode = "expire"
        res = self.parsed(await self.call())
        self.assertTrue(res["isError"])
        self.assertNotIn('"verdict"', json.dumps(res))
        self.assertEqual(self.reads, 1)

    async def test_wrong_source_reply_refused(self):
        self.mode = "cross-source"
        res = self.parsed(await self.call())
        self.assertTrue(res["isError"])
        self.assertNotIn('"checks"', json.dumps(res))

    async def test_bad_port_return_does_not_leak(self):
        self.mode = "malformed"
        res = self.parsed(await self.call())
        self.assertTrue(res["isError"])
        self.assertNotIn("PRIVATE_SECRET", json.dumps(res))

    async def test_exception_not_returned(self):
        self.mode = "error"
        res = self.parsed(await self.call())
        self.assertTrue(res["isError"])
        self.assertNotIn("PRIVATE_NETWORK_EXCEPTION", json.dumps(res))

    async def test_origin_guard_refuses(self):
        res = await self.rpc("tools/list", token=self.token(), origin="https://evil.example")
        self.assertEqual(res.status_code, 403)
        self.assertEqual(self.reads, 0)

    async def test_audit_redacts_identity_and_token(self):
        raw = self.token()
        self.parsed(await self.call(token=raw))
        self.assertNotIn(raw, json.dumps(self.audit.events))
        self.assertNotIn("product-a", json.dumps(self.audit.events))

    async def test_standard_oidc_oauth_still_requires_owner_product_grant(self):
        # Supabase OAuth 2.1 currently supports standard 'openid', NOT a custom
        # mastermind.product.read OAuth scope. The product-user gate is separate.
        from integrations.product_access_mcp.contracts import OIDC_READ_SCOPE
        policy = dataclasses.replace(self.policy, required_scopes=(OIDC_READ_SCOPE,))
        auth = JwtAuthenticator(policy=policy, jwks_cache=self.keys)
        calls = []
        async def forbidden_port(caller, request):
            calls.append("read")
            raise AssertionError("private product read must not run")
        def deny_grant(caller, request):
            raise ProductRefused("PRODUCT_GRANT_CHANGED")
        server = create_authenticated_product_server(
            authenticator=auth, policy=policy, now=lambda: self.clock,
            audit_sink=self.audit, read_port=forbidden_port,
            final_authorization=deny_grant,
            allowed_hosts=("127.0.0.1", "127.0.0.1:*"))
        app = server.streamable_http_app()
        ready = asyncio.Event()
        stop = asyncio.Event()
        async def owner():
            async with app.router.lifespan_context(app):
                ready.set()
                await stop.wait()
        task = asyncio.create_task(owner())
        await asyncio.wait_for(ready.wait(), timeout=5)
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                         base_url="http://127.0.0.1") as client:
                res = await client.post("/mcp", headers={
                    "Authorization": "Bearer " + self.token(scope=OIDC_READ_SCOPE),
                    "Accept": "application/json, text/event-stream",
                    "MCP-Protocol-Version": "2025-03-26",
                }, json={
                    "jsonrpc": "2.0", "id": 1, "method": "tools/call",
                    "params": {"name": "product_observe", "arguments": {
                        "product": "terminal", "view": "market_risk",
                    }},
                })
                self.assertEqual(res.status_code, 200)
                self.assertTrue(res.json()["result"]["isError"])
                self.assertFalse(calls)
        finally:
            stop.set()
            await asyncio.wait_for(task, timeout=5)


    async def test_supabase_default_authenticated_audience_is_not_resource_access(self):
        # Real Supabase OAuth access tokens use aud='authenticated' by default.
        # A valid token from that issuer must NOT be silently treated as a
        # Product MCP resource token by the Business MCP verifier.
        result = await self.call(token=self.token(
            aud="authenticated", scope="openid"))
        self.assertEqual(result.status_code, 401)
        self.assertEqual(self.reads, 0)

    async def test_owner_bound_deployment_positive_then_revoke_after_await(self):
        """Owner-supplied binding → native MCP/ASGI → signed caller → late fence."""
        from zoneinfo import ZoneInfo
        from integrations.product_access_mcp.deployment import (
            ProductDeploymentServices, ProductReadBinding,
            create_product_deployment,
        )
        from integrations.product_access_mcp.contracts import SOURCES
        from integrations.product_access_mcp.observer import HttpPayload, product_observe

        granted_generation = ["v1"]
        seen = []

        def owner(caller, product, view):
            if caller.subject_digest != self.subject_a or granted_generation[0] == "revoked":
                raise ProductRefused("PRODUCT_GRANT_CHANGED")
            source = ("catalog.static" if product == "catalog"
                      else SOURCES[(product, view)][0])
            return ProductReadBinding(
                caller=caller, product=product, view=view, source_id=source,
                owner_ref="incumbent-product-auth",
                grant_generation=granted_generation[0],
                expires_at=caller.expires_at,
            )

        def fake_public_get(url, cap):
            self.assertEqual(url, SOURCES[("terminal", "market_risk")][1])
            now = datetime.now(timezone.utc)
            session = now.astimezone(ZoneInfo("America/New_York")).date().isoformat()
            data = {
                "schema": "market_risk/v1", "verdict": "MIXED", "score": 44,
                "asof": session, "stale": False,
                "stale_after": (now + timedelta(hours=1)).isoformat(),
                "is_display_only": True,
                "freshness": {"qualified": True, "reasons": []},
            }
            raw = json.dumps(data).encode()
            return HttpPayload(200, raw, {
                "content-type": "application/json",
                "content-length": str(len(raw)),
            })

        async def read_port(caller, request):
            seen.append((caller, dict(request)))
            await asyncio.sleep(0)
            if self.mode == "change-generation":
                granted_generation[0] = "v2"
            return product_observe(
                caller, request, datetime.now(timezone.utc), fake_public_get,
            )

        deployment = create_product_deployment(ProductDeploymentServices(
            authenticator=self.auth, policy=self.policy,
            now=lambda: self.clock, audit_sink=self.audit,
            read_port=read_port, resolve_binding=owner,
            allowed_hosts=("127.0.0.1",),
        ))
        from integrations.product_access_mcp.mount import create_product_asgi_app
        ready = [False]
        app = create_product_asgi_app(server=deployment, owner_ready=lambda: ready[0])
        started = asyncio.Event()
        stop = asyncio.Event()

        async def run_owner():
            async with app.router.lifespan_context(app):
                started.set()
                await stop.wait()

        worker = asyncio.create_task(run_owner())
        await asyncio.wait_for(started.wait(), timeout=5)
        try:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://127.0.0.1",
            ) as client:
                async def call(token, name="product_observe", arguments=None):
                    return await client.post("/mcp", headers={
                        "Authorization": "Bearer " + token,
                        "Accept": "application/json, text/event-stream",
                        "MCP-Protocol-Version": "2025-03-26",
                    }, json={
                        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
                        "params": {"name": name, "arguments":
                                   arguments if arguments is not None else {
                                       "product": "terminal", "view": "market_risk",
                                   }},
                    })

                not_ready = await call(self.token())
                self.assertEqual(not_ready.status_code, 503)
                self.assertEqual(len(seen), 0)
                ready[0] = True
                self.assertEqual((await client.get("/readyz")).status_code, 200)
                metadata = await client.get("/.well-known/oauth-protected-resource/mcp")
                self.assertEqual(metadata.status_code, 200, metadata.text[:160])
                self.assertEqual(metadata.json()["resource"], RESOURCE)
                self.assertEqual(metadata.json()["authorization_servers"], [ISSUER + "/"])
                self.assertEqual(metadata.json()["scopes_supported"], [READ_SCOPE])
                self.assertNotIn("client_secret", metadata.text)

                valid = await call(self.token())
                self.assertEqual(valid.status_code, 200, valid.text[:150])
                positive = valid.json()["result"]
                self.assertFalse(positive.get("isError", False), positive)
                self.assertEqual(positive["structuredContent"]["data"]["verdict"], "MIXED")
                self.assertEqual(len(seen), 1)

                denied_user = await call(self.token("product-b"))
                self.assertEqual(denied_user.status_code, 200)
                self.assertTrue(denied_user.json()["result"]["isError"])
                self.assertEqual(len(seen), 1)

                self.mode = "change-generation"
                changed = await call(self.token())
                self.assertEqual(changed.status_code, 200)
                self.assertTrue(changed.json()["result"]["isError"])
                self.assertNotIn("MIXED", json.dumps(changed.json()))
                self.assertEqual(len(seen), 2)

                granted_generation[0] = "revoked"
                self.mode = "normal"
                rejected = await call(self.token())
                self.assertTrue(rejected.json()["result"]["isError"])
                self.assertEqual(len(seen), 2)
        finally:
            stop.set()
            await asyncio.wait_for(worker, timeout=5)


    async def test_oauth_resource_metadata_and_missing_token_challenge(self):
        """SDK should advertise exactly this verifier resource, not a user identity."""
        r = await self.client.get("/.well-known/oauth-protected-resource/mcp")
        self.assertEqual(r.status_code, 200, r.text[:220])
        meta = r.json()
        self.assertEqual(meta["resource"], RESOURCE)
        self.assertEqual(meta["authorization_servers"], [ISSUER + "/"])
        self.assertEqual(meta["scopes_supported"], [READ_SCOPE])
        self.assertNotIn("client_secret", json.dumps(meta))
        self.assertEqual(self.reads, 0)

        no_token = await self.rpc("tools/list")
        self.assertEqual(no_token.status_code, 401)
        challenge = no_token.headers.get("www-authenticate", "")
        self.assertIn("resource_metadata", challenge)
        self.assertIn("oauth-protected-resource/mcp", challenge)
        self.assertEqual(self.reads, 0)


    async def test_incomplete_healthy_port_result_withheld_from_authenticated_mcp(self):
        self.mode = "fake-healthy"
        result = self.parsed(await self.call())
        self.assertTrue(result["isError"])
        self.assertNotIn("MIXED", json.dumps(result))
        self.assertEqual(self.reads, 1)
