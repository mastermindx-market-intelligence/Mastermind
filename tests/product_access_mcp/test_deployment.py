"""Product deployment composition: borrow existing owners; no listener or real network."""
from __future__ import annotations

import dataclasses
import json
from datetime import datetime, timezone
import time
import unittest

from cryptography.hazmat.primitives.asymmetric import rsa
import jwt

from integrations.business_mcp_auth.contracts import (
    load_resource_policy, subject_digest,
)
from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator


ISSUER = "https://identity.product.example/"
RESOURCE = "https://product.example/mcp"


class Keys:
    def __init__(self, key):
        self.key = key

    async def key_for(self, kid):
        if kid != "fixture-key":
            raise ValueError("unknown_fixture_key")
        return self.key


class Audit:
    def __init__(self):
        self.events = []

    def emit(self, event):
        self.events.append(event)


def policy():
    return load_resource_policy({
        "schema": "mastermind.business_mcp_auth_policy.v1",
        "policy_id": "fixture.product.observe",
        "resource": RESOURCE,
        "resource_metadata_url": "https://product.example/.well-known/oauth-protected-resource/mcp",
        "issuer": ISSUER,
        "authorization_servers": [ISSUER],
        "jwks_uri": ISSUER + "jwks",
        "required_scopes": ["product.observe"],
        "allowed_subject_digests": [subject_digest(issuer=ISSUER, subject="user-a")],
        "allowed_algorithms": ["RS256"],
        "clock_skew_seconds": 0,
        "max_token_lifetime_seconds": 3600,
        "jwks_cache_ttl_seconds": 60,
        "unknown_kid_refresh_cooldown_seconds": 1,
        "fetch_failure_backoff_seconds": 1,
    })


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        from integrations.product_access_mcp.deployment import (
            ProductRuntimeServices, create_deployment,
        )
        self.Services = ProductRuntimeServices
        self.create = create_deployment
        self.selected = policy()
        private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public = jwt.algorithms.RSAAlgorithm.to_jwk(private.public_key())
        self.audit = Audit()
        self.auth = JwtAuthenticator(policy=self.selected, jwks_cache=Keys(public))
        self.now = int(time.time())
        self.services = self.Services(
            authenticator=self.auth,
            policy=self.selected,
            now=lambda: self.now,
            utc_now=lambda: datetime.fromtimestamp(self.now, timezone.utc),
            audit_sink=self.audit,
            allowed_hosts=("product.example",),
            allowed_origins=(),
        )

    def test_composition_is_inert_and_wraps_existing_mcp_sdk(self):
        from integrations.product_access_mcp.app import create_product_server
        from integrations.executive_mcp.e1_http import PreAuthMcpBodyApp
        # A production port is chosen in the factory, without opening a connection.
        app = self.create(self.services)
        self.assertIsNotNone(app)
        self.assertTrue(hasattr(app, "router"))
        self.assertTrue(any(m.cls is PreAuthMcpBodyApp for m in app.user_middleware))
        self.assertEqual(self.audit.events, [])

    def test_runtime_services_are_required_not_an_untyped_config_or_fixture(self):
        for value in (None, {}, object(), self.selected):
            with self.subTest(value=type(value).__name__):
                with self.assertRaises(ValueError):
                    self.create(value)

    def test_policy_must_be_identical_to_authenticator_policy(self):
        policy_drift = dataclasses.replace(self.selected, policy_id="fixture.other.observe")
        with self.assertRaisesRegex(ValueError, "AUTH_POLICY_BINDING_MISMATCH"):
            self.create(dataclasses.replace(self.services, policy=policy_drift))

    def test_scope_is_dedicated_to_public_product_observation(self):
        foreign = dataclasses.replace(self.selected, required_scopes=("workbench.action",))
        alternate = JwtAuthenticator(policy=foreign, jwks_cache=Keys({}))
        with self.assertRaisesRegex(ValueError, "PRODUCT_SCOPE_REQUIRED"):
            self.create(dataclasses.replace(self.services, policy=foreign, authenticator=alternate))

    def test_rejects_missing_or_mutable_or_wildcard_hosts(self):
        for bad in ((), ["product.example"], ("*",), ("product.example:*",),
                    ("product.example:invalid",), ("product.example:0",),
                    ("evil.invalid\r\nInjected: yes",), ("product.example", "other.invalid*")):
            with self.subTest(bad=bad):
                with self.assertRaisesRegex(ValueError, "TRANSPORT_POLICY_INVALID"):
                    self.create(dataclasses.replace(self.services, allowed_hosts=bad))

    def test_rejects_non_origin_or_wildcard_origin_policy(self):
        for bad in (["https://product.example"], ("*",), ("https://*.example",),
                    ("https://product.example/private",), ("http://product.example",),
                    ("http://product.example?token=x",),
                    ("https://product.example#fragment",)):
            with self.subTest(bad=bad):
                with self.assertRaisesRegex(ValueError, "TRANSPORT_POLICY_INVALID"):
                    self.create(dataclasses.replace(self.services, allowed_origins=bad))

    def test_rejects_wrong_clocks_audit_and_verifier(self):
        for value in (None, lambda: "not-epoch", lambda: True):
            with self.subTest(kind="epoch", value=str(value)):
                with self.assertRaisesRegex(ValueError, "RUNTIME_SERVICES_INVALID"):
                    self.create(dataclasses.replace(self.services, now=value))
        for value in (None, lambda: datetime.now(), lambda: 1):
            with self.subTest(kind="utc", value=str(value)):
                with self.assertRaisesRegex(ValueError, "RUNTIME_SERVICES_INVALID"):
                    self.create(dataclasses.replace(self.services, utc_now=value))
        with self.assertRaisesRegex(ValueError, "RUNTIME_SERVICES_INVALID"):
            self.create(dataclasses.replace(self.services, audit_sink=object()))
        with self.assertRaisesRegex(ValueError, "RUNTIME_SERVICES_INVALID"):
            self.create(dataclasses.replace(self.services, authenticator=object()))

    def test_valid_explicit_https_origin_is_allowed(self):
        app = self.create(dataclasses.replace(
            self.services, allowed_origins=("https://product.example",)
        ))
        self.assertTrue(hasattr(app, "router"))


class DeploymentRpcTests(unittest.IsolatedAsyncioTestCase):
    """Actual SDK/ASGI/token boundary using synthetic data and zero public traffic."""

    async def asyncSetUp(self):
        import asyncio
        from unittest.mock import patch
        import httpx
        from integrations.product_access_mcp.contracts import HttpObservation
        from integrations.product_access_mcp.deployment import (
            ProductRuntimeServices, create_deployment,
        )

        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(self.key.public_key()))
        jwk.update(kid="fixture-key", alg="RS256", use="sig")
        self.selected = policy()
        self.auth = JwtAuthenticator(policy=self.selected, jwks_cache=Keys(jwk))
        self.audit = Audit()
        self.now = int(time.time())
        self.calls = []

        async def fake_public_read(_transport, endpoint, *, symbols=()):
            self.calls.append((endpoint, symbols))
            if endpoint == "health":
                body = {"status": "ok", "commit": "a" * 40, "checkout": "a" * 40}
            elif endpoint == "status":
                body = {"status": "ok", "commit": "a" * 40,
                        "checks": {"terminal_data": {"status": "missing"}}}
            else:
                raise AssertionError("unexpected public endpoint in fixture")
            import json
            return HttpObservation(status=200, body=json.dumps(body).encode(),
                                   content_type="application/json")

        self.port_patch = patch(
            "integrations.product_access_mcp.transport.PublicTransport.read",
            new=fake_public_read,
        )
        self.port_patch.start()
        self.addCleanup(self.port_patch.stop)

        self.app = create_deployment(ProductRuntimeServices(
            authenticator=self.auth,
            policy=self.selected,
            now=lambda: self.now,
            utc_now=lambda: datetime.fromtimestamp(self.now, timezone.utc),
            audit_sink=self.audit,
            allowed_hosts=("product.example",),
        ))
        self.ready, self.stop = asyncio.Event(), asyncio.Event()

        async def lifespan():
            async with self.app.router.lifespan_context(self.app):
                self.ready.set()
                await self.stop.wait()

        self.task = asyncio.create_task(lifespan())
        await asyncio.wait_for(self.ready.wait(), timeout=5)
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app),
            base_url="http://product.example",
        )

    async def asyncTearDown(self):
        import asyncio
        if hasattr(self, "client"):
            await self.client.aclose()
            self.stop.set()
            await asyncio.wait_for(self.task, timeout=5)

    def token(self, **extra):
        claims = {
            "iss": ISSUER, "aud": RESOURCE, "sub": "user-a",
            "scope": "product.observe", "iat": self.now - 1,
            "exp": self.now + 600, "client_id": "fixture-client",
        }
        claims.update(extra)
        return jwt.encode(claims, self.key, algorithm="RS256",
                          headers={"kid": "fixture-key"})

    async def call(self, *, token=None, tool="product_diagnostics"):
        return await self.client.post(
            "/mcp",
            headers={"Accept": "application/json, text/event-stream",
                     "MCP-Protocol-Version": "2025-03-26",
                     "Authorization": "Bearer " + (token or self.token())},
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                  "params": {"name": tool, "arguments": {}}},
        )

    async def test_factory_authenticated_diagnostics_are_bounded_and_public(self):
        result = await self.call()
        self.assertEqual(result.status_code, 200, result.text[:200])
        value = result.json()["result"]
        self.assertFalse(value.get("isError", False))
        self.assertEqual(value["structuredContent"]["tool"], "product_diagnostics")
        self.assertEqual(value["structuredContent"]["observations"][0]["access_class"], "public")
        self.assertEqual(self.calls, [("health", ()), ("status", ())])
        self.assertNotIn("access_token", result.text)

    async def test_factory_wrong_identity_and_mutations_refuse_without_backend(self):
        for token in (self.token(sub="unknown-user"), self.token(exp=self.now - 3)):
            denied = await self.call(token=token)
            self.assertIn(denied.status_code, (401, 403))
        self.assertEqual(self.calls, [])
        unknown = await self.call(tool="execute_trade")
        self.assertEqual(unknown.status_code, 200)
        self.assertTrue(unknown.json()["result"]["isError"])
        self.assertEqual(self.calls, [])
