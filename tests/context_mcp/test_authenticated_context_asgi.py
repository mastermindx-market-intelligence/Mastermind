"""Actual SDK/ASGI/JWT Context MCP auth and bounded project-binding integration.

Real ephemeral RSA signatures, SDK middleware and request-local authorization.
No HTTP listener, production token, installed plugin, root discovery or filesystem
access. The incumbent Business OAuth and Context Fabric port remain owners.
"""
from __future__ import annotations

import asyncio
import dataclasses
import json
import time
import unittest

import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

from integrations.business_mcp_auth.contracts import (
    load_resource_policy, subject_digest,
)
from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator
from integrations.context_mcp.app import create_authenticated_context_server
from integrations.context_mcp.contracts import TOOL_NAMES
from integrations.context_mcp.model import ContextPortRefused
from integrations.context_mcp.port import ContextProjectBinding, create_context_port_bundle

ISSUER = "https://identity.context.example"
RESOURCE = "https://context.example/mcp"
SCOPE = "workbench.read"


class _EphemeralKeys:
    def __init__(self, jwk):
        self.jwk = jwk

    async def key_for(self, kid):
        if kid != "ephemeral-context-key":
            raise ValueError("unrecognized key")
        return self.jwk


class _PrivateAudit:
    def __init__(self):
        self.events = []

    def emit(self, event):
        self.events.append(dataclasses.asdict(event))


class ContextSDKTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.clock = int(time.time())
        self.rsa_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(self.rsa_key.public_key()))
        public.update(kid="ephemeral-context-key", alg="RS256", use="sig")
        self.subjects = {
            subject: subject_digest(issuer=ISSUER, subject=subject)
            for subject in ("alpha-reader", "beta-reader")
        }
        policy = load_resource_policy({
            "schema": "mastermind.business_mcp_auth_policy.v1",
            "policy_id": "fixture.context.read",
            "resource": RESOURCE,
            "resource_metadata_url": "https://context.example/.well-known/oauth-protected-resource/mcp",
            "issuer": ISSUER, "authorization_servers": [ISSUER],
            "jwks_uri": ISSUER + "/jwks",
            "required_scopes": [SCOPE],
            "allowed_subject_digests": sorted(self.subjects.values()),
            "allowed_algorithms": ["RS256"],
            "clock_skew_seconds": 0, "max_token_lifetime_seconds": 3600,
            "jwks_cache_ttl_seconds": 60,
            "unknown_kid_refresh_cooldown_seconds": 1,
            "fetch_failure_backoff_seconds": 1,
        })
        self.policy = policy
        self.audit = _PrivateAudit()
        self.auth = JwtAuthenticator(policy=policy, jwks_cache=_EphemeralKeys(public))
        self.calls = []
        self.mode = "good"
        self.generations = {"project:alpha": "generation:alpha1",
                            "project:beta": "generation:beta1"}
        self.valid_projects = {self.subjects["alpha-reader"]: "project:alpha",
                               self.subjects["beta-reader"]: "project:beta"}

        def binding(caller, project_ref):
            if self.valid_projects.get(caller.subject_digest) != project_ref:
                return None
            return ContextProjectBinding(
                caller=caller, project_ref=project_ref,
                generation=self.generations[project_ref],
                repositories=("mastermindx-market-intelligence/Mastermind",),
                workspace_operations=("context-operation",),
                tools=TOOL_NAMES,
            )

        async def handle(caller, selected, request):
            self.calls.append((caller.subject_digest, selected.project_ref, dict(request)))
            await asyncio.sleep(0)
            if self.mode == "binding_drift":
                self.generations[selected.project_ref] = "generation:changed"
            if self.mode == "expire_after_await":
                self.clock += 7200  # expire after handler ran, before final auth
            if self.mode == "port_error":
                raise RuntimeError("PRIVATE_PORT_EXCEPTION")
            result = {
                "status": "OK", "schema": "mastermind.context_fixture/v1",
                "project_ref": selected.project_ref,
                "context_ref": "context:fixture:one",
                "source_digest": "e" * 64,
                "data": {"advisory": "no source or runtime permissions"},
                "degraded": [],
            }
            if self.mode == "secret_result":
                result["data"]["api_key"] = "PRIVATE_FIXTURE_VALUE"
            if self.mode == "wrong_project":
                result["project_ref"] = "project:beta"
            return result

        context_port, final_auth = create_context_port_bundle(
            resolve_binding=binding,
            handlers={name: handle for name in TOOL_NAMES},
            clock_ms=lambda: self.clock * 1000,
        )
        self.server = create_authenticated_context_server(
            authenticator=self.auth, policy=policy,
            now=lambda: self.clock, audit_sink=self.audit,
            context_port=context_port, final_authorization=final_auth,
            allowed_hosts=("127.0.0.1", "127.0.0.1:*"),
        )
        self.app = self.server.streamable_http_app()
        self.ready = asyncio.Event()
        self.stop = asyncio.Event()

        async def run_lifespan():
            async with self.app.router.lifespan_context(self.app):
                self.ready.set()
                await self.stop.wait()

        self.lifespan = asyncio.create_task(run_lifespan())
        await asyncio.wait_for(self.ready.wait(), timeout=5)
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app),
            base_url="http://127.0.0.1",
        )

    async def asyncTearDown(self):
        await self.client.aclose()
        self.stop.set()
        await asyncio.wait_for(self.lifespan, timeout=5)

    def token(self, user="alpha-reader", **overrides):
        claims = {
            "iss": ISSUER, "sub": user, "aud": RESOURCE,
            "iat": self.clock - 1, "exp": self.clock + 600,
            "scope": SCOPE, "client_id": "synthetic-context-client",
        }
        claims.update(overrides)
        return jwt.encode(
            claims, self.rsa_key, algorithm="RS256",
            headers={"kid": "ephemeral-context-key"},
        )

    async def rpc(self, method, params=None, token=None):
        headers = {
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": "2025-03-26",
        }
        if token is not None:
            headers["Authorization"] = "Bearer " + token
        return await self.client.post(
            "/mcp", headers=headers,
            json={"jsonrpc": "2.0", "id": 1,
                  "method": method, "params": params or {}},
        )

    async def call(self, project="project:alpha", token=None, name="resolve_context", extra=None):
        args = {"project_ref": project, "task": "recover evidence"}
        if name == "atlas_search":
            args = {"project_ref": project,
                    "repository": "mastermindx-market-intelligence/Mastermind",
                    "term": "context"}
        if name == "workspace_overlay":
            args = {"project_ref": project, "operation_id": "context-operation"}
        args.update(extra or {})
        return await self.rpc(
            "tools/call", {"name": name, "arguments": args},
            token=self.token() if token is None else token,
        )

    def result(self, response):
        self.assertEqual(response.status_code, 200, response.text[:250])
        body = response.json()
        self.assertIn("result", body, body)
        return body["result"]

    def error_code(self, response):
        result = self.result(response)
        self.assertTrue(result.get("isError"), result)
        return json.loads(result["content"][0]["text"])["code"]

    async def test_initialize_and_read_only_tool_inventory(self):
        result = self.result(await self.rpc(
            "initialize",
            {"protocolVersion": "2025-03-26", "capabilities": {},
             "clientInfo": {"name": "context-fixture", "version": "1"}},
            token=self.token(),
        ))
        self.assertIn("serverInfo", result)
        tools = self.result(await self.rpc("tools/list", token=self.token()))["tools"]
        self.assertEqual(tuple(x["name"] for x in tools), TOOL_NAMES)
        for row in tools:
            self.assertTrue(row["annotations"]["readOnlyHint"])
            self.assertFalse(row["annotations"]["destructiveHint"])
        self.assertEqual(self.calls, [])

    async def test_real_jwt_and_project_bound_context_result(self):
        result = self.result(await self.call())
        self.assertFalse(result.get("isError", False), result)
        data = result["structuredContent"]
        self.assertEqual(data["project_ref"], "project:alpha")
        self.assertEqual(data["data"]["advisory"], "no source or runtime permissions")
        self.assertEqual(len(self.calls), 1)

    async def test_distinct_identities_cannot_cross_project_binding(self):
        a, b = await asyncio.gather(
            self.call(token=self.token("alpha-reader"), project="project:alpha"),
            self.call(token=self.token("beta-reader"), project="project:beta"),
        )
        self.assertEqual(self.result(a)["structuredContent"]["project_ref"], "project:alpha")
        self.assertEqual(self.result(b)["structuredContent"]["project_ref"], "project:beta")
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(self.error_code(await self.call(project="project:beta")), "CONTEXT_REFUSED")
        self.assertEqual(len(self.calls), 2)

    async def test_missing_or_wrong_scope_identity_never_reaches_port(self):
        missing = await self.rpc("tools/call", {"name": "resolve_context",
                             "arguments": {"project_ref": "project:alpha", "task": "x"}})
        self.assertEqual(missing.status_code, 401)
        wrong_scope = await self.call(token=self.token(scope="not-allowed"))
        self.assertEqual(wrong_scope.status_code, 401)
        bad_subject = await self.call(token=self.token(user="not-entitled"))
        self.assertEqual(bad_subject.status_code, 401)
        self.assertEqual(len(self.calls), 0)

    async def test_await_boundary_rechecks_owner_binding(self):
        self.mode = "binding_drift"
        self.assertEqual(self.error_code(await self.call()), "CONTEXT_BINDING_CHANGED")
        self.assertEqual(len(self.calls), 1)

    async def test_secret_and_wrong_project_results_refuse(self):
        for kind in ("secret_result", "wrong_project", "port_error"):
            self.mode = kind
            expected = {
                "secret_result": "CONTEXT_RESULT_UNVERIFIED",
                "wrong_project": "CONTEXT_SOURCE_CHANGED",
                "port_error": "CONTEXT_UNAVAILABLE",
            }[kind]
            with self.subTest(kind=kind):
                self.assertEqual(self.error_code(await self.call()), expected)
                self.assertNotIn("PRIVATE_FIXTURE_VALUE", json.dumps(self.audit.events))

    async def test_request_scope_refusals_stay_inside_existing_binding(self):
        self.assertEqual(self.error_code(await self.call(
            name="atlas_search", extra={"repository": "elsewhere/private"}
        )), "CONTEXT_REFUSED")
        self.assertEqual(self.error_code(await self.call(
            name="workspace_overlay", extra={"operation_id": "not-our-workspace"}
        )), "CONTEXT_REFUSED")
        self.assertEqual(len(self.calls), 0)

    async def test_auth_expires_after_port_await_and_result_is_not_delivered(self):
        self.mode = "expire_after_await"
        outcome = self.error_code(await self.call())
        # Existing ContextPort performs the earlier post-await owner/expiry
        # fence, before the HTTP app checks the token a second time. Both are
        # fail-closed; don't weaken or reorder these established owners.
        self.assertEqual(outcome, "CONTEXT_BINDING_CHANGED")
        self.assertEqual(len(self.calls), 1)

    async def test_invalid_signature_or_audience_refuses_before_context_handler(self):
        first = self.token().split(".")
        first[2] = ("A" if first[2][0] != "A" else "B") + first[2][1:]
        invalid = await self.call(token=".".join(first))
        self.assertEqual(invalid.status_code, 401)
        wrong_audience = await self.call(token=self.token(aud="https://other.example/mcp"))
        self.assertEqual(wrong_audience.status_code, 401)
        self.assertEqual(len(self.calls), 0)

    async def test_invalid_schema_or_unknown_tool_is_refused_before_port(self):
        unexpected = await self.call(extra={"root": "/unadmitted/host/path"})
        self.assertEqual(self.error_code(unexpected), "INVALID_REQUEST")
        unknown = await self.call(name="read_absolute_host_file")
        self.assertEqual(self.error_code(unknown), "TOOL_NOT_AVAILABLE")
        self.assertEqual(len(self.calls), 0)
