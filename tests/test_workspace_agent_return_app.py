"""Authenticated end-to-end MCP boundary tests for Workspace candidate return."""
from __future__ import annotations

import asyncio
import dataclasses
import json
import time
import unittest

import httpx
import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from integrations.business_mcp_auth.contracts import (
    load_resource_policy,
    subject_digest,
)
from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator
from integrations.business_mcp_auth.mcp_adapter import MastermindTokenVerifier
from integrations.workspace_agent_return import (
    RETURN_RESULT_SCHEMA,
    TOOL_NAME,
    WorkspaceCandidateReturnGateway,
)
from integrations.workspace_agent_return_app import (
    REQUIRED_SCOPE,
    create_authenticated_return_server,
)

ISSUER = "https://identity.workspace-return.example"
RESOURCE = "https://workspace-return.example/mcp"
METADATA = "https://workspace-return.example/.well-known/oauth-protected-resource/mcp"
MESSAGE_KEY = "asd-wsa-" + "0" * 32


class Keys:
    def __init__(self, jwk):
        self.jwk = jwk

    async def key_for(self, kid):
        if kid != "fixture-key":
            raise ValueError("unknown key")
        return self.jwk


class Audit:
    def __init__(self):
        self.events = []

    def emit(self, event):
        self.events.append(dataclasses.asdict(event))


class StubGateway(WorkspaceCandidateReturnGateway):
    def __init__(self, *, clock_ref, state="success", expire_after_call=False):
        self.clock_ref = clock_ref
        self.state = state
        self.expire_after_call = expire_after_call
        self.calls = []

    async def call_tool(self, name, arguments):
        self.calls.append((name, dict(arguments)))
        if self.expire_after_call:
            self.clock_ref[0] += 700
        if self.state == "raise":
            raise RuntimeError("SECRET_BACKEND_DETAIL")
        if self.state == "malformed":
            return {"ok": True, "secret": "SECRET_BACKEND_DETAIL"}
        if self.state == "changed":
            return {
                "schema": RETURN_RESULT_SCHEMA,
                "ok": False,
                "state": "CURRENT_TARGET_CHANGED",
                "message_key": MESSAGE_KEY,
            }
        if self.state == "unknown":
            return {
                "schema": RETURN_RESULT_SCHEMA,
                "ok": False,
                "state": "EFFECT_UNKNOWN",
                "message_key": MESSAGE_KEY,
            }
        return {
            "schema": RETURN_RESULT_SCHEMA,
            "ok": True,
            "state": "CANDIDATE_RECORDED",
            "message_key": MESSAGE_KEY,
            "transport_action": "POSTED",
            "accepted": False,
            "wake_acknowledged": False,
        }


class WorkspaceReturnAuthenticatedAppTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.clock = [int(time.time())]
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.pem = self.key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
        public = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(self.key.public_key()))
        public.update(kid="fixture-key", alg="RS256", use="sig")
        self.subject = subject_digest(issuer=ISSUER, subject="workspace-agent-a")
        self.policy = load_resource_policy(
            {
                "schema": "mastermind.business_mcp_auth_policy.v1",
                "policy_id": "fixture.workspace.return",
                "resource": RESOURCE,
                "resource_metadata_url": METADATA,
                "issuer": ISSUER,
                "authorization_servers": [ISSUER],
                "jwks_uri": ISSUER + "/jwks",
                "required_scopes": [REQUIRED_SCOPE],
                "allowed_subject_digests": [self.subject],
                "allowed_algorithms": ["RS256"],
                "clock_skew_seconds": 0,
                "max_token_lifetime_seconds": 3600,
                "jwks_cache_ttl_seconds": 60,
                "unknown_kid_refresh_cooldown_seconds": 1,
                "fetch_failure_backoff_seconds": 1,
            }
        )
        self.authenticator = JwtAuthenticator(
            policy=self.policy,
            jwks_cache=Keys(public),
        )
        self.audit = Audit()
        self.verifier = MastermindTokenVerifier(
            authenticator=self.authenticator,
            policy=self.policy,
            now=lambda: self.clock[0],
            audit_sink=self.audit,
        )
        self.gateway = StubGateway(clock_ref=self.clock)
        self.server = create_authenticated_return_server(
            gateway=self.gateway,
            policy=self.policy,
            token_verifier=self.verifier,
            allowed_hosts=("127.0.0.1", "127.0.0.1:*"),
        )
        self.app = self.server.streamable_http_app()
        self.ready = asyncio.Event()
        self.stop = asyncio.Event()

        async def lifespan():
            async with self.app.router.lifespan_context(self.app):
                self.ready.set()
                await self.stop.wait()

        self.lifespan_task = asyncio.create_task(lifespan())
        await asyncio.wait_for(self.ready.wait(), timeout=5)
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app),
            base_url="http://127.0.0.1",
        )

    async def asyncTearDown(self):
        await self.client.aclose()
        self.stop.set()
        await asyncio.wait_for(self.lifespan_task, timeout=5)

    def token(self, **changes):
        payload = {
            "iss": ISSUER,
            "sub": "workspace-agent-a",
            "aud": RESOURCE,
            "iat": self.clock[0] - 1,
            "exp": self.clock[0] + 600,
            "scope": REQUIRED_SCOPE,
            "client_id": "fixture-workspace-agent",
        }
        payload.update(changes)
        return jwt.encode(
            payload,
            self.pem,
            algorithm="RS256",
            headers={"kid": "fixture-key"},
        )

    async def rpc(self, method, params=None, token=None):
        headers = {
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": "2025-03-26",
        }
        if token is not None:
            headers["Authorization"] = "Bearer " + token
        return await self.client.post(
            "/mcp",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": method,
                "params": params or {},
            },
        )

    def result(self, response):
        self.assertEqual(response.status_code, 200, response.text[:400])
        body = response.json()
        self.assertIn("result", body, body)
        return body["result"]

    def call_params(self):
        return {
            "name": TOOL_NAME,
            "arguments": {
                "return_ref": "synthetic-return-ref",
                "status": "PASS",
                "result": "Candidate only.",
            },
        }

    async def replace_gateway(self, gateway):
        await self.client.aclose()
        self.stop.set()
        await asyncio.wait_for(self.lifespan_task, timeout=5)

        self.gateway = gateway
        self.server = create_authenticated_return_server(
            gateway=self.gateway,
            policy=self.policy,
            token_verifier=self.verifier,
            allowed_hosts=("127.0.0.1", "127.0.0.1:*"),
        )
        self.app = self.server.streamable_http_app()
        self.ready = asyncio.Event()
        self.stop = asyncio.Event()

        async def lifespan():
            async with self.app.router.lifespan_context(self.app):
                self.ready.set()
                await self.stop.wait()

        self.lifespan_task = asyncio.create_task(lifespan())
        await asyncio.wait_for(self.ready.wait(), timeout=5)
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app),
            base_url="http://127.0.0.1",
        )

    async def test_tool_discovery_is_exact_one_tool_and_declares_oauth_scope(self):
        data = self.result(await self.rpc("tools/list", token=self.token()))
        self.assertEqual([row["name"] for row in data["tools"]], [TOOL_NAME])
        row = data["tools"][0]
        self.assertFalse(row["annotations"]["readOnlyHint"])
        self.assertFalse(row["annotations"]["destructiveHint"])
        self.assertTrue(row["annotations"]["idempotentHint"])
        self.assertFalse(row["annotations"]["openWorldHint"])
        self.assertEqual(
            row["securitySchemes"],
            [{"type": "oauth2", "scopes": [REQUIRED_SCOPE]}],
        )
        properties = row["inputSchema"]["properties"]
        self.assertEqual(
            set(properties),
            {"return_ref", "status", "result", "evidence_refs"},
        )

    async def test_authenticated_call_crosses_real_mcp_auth_boundary_once(self):
        token = self.token()
        data = self.result(
            await self.rpc("tools/call", self.call_params(), token=token)
        )
        self.assertFalse(data.get("isError", False), data)
        result = data["structuredContent"]
        self.assertEqual(result["state"], "CANDIDATE_RECORDED")
        self.assertFalse(result["accepted"])
        self.assertFalse(result["wake_acknowledged"])
        self.assertEqual(len(self.gateway.calls), 1)
        self.assertEqual(self.gateway.calls[0][0], TOOL_NAME)
        self.assertEqual(
            self.gateway.calls[0][1],
            self.call_params()["arguments"],
        )
        self.assertGreaterEqual(
            len([row for row in self.audit.events if row["accepted"]]),
            2,
        )

    async def test_missing_and_wrong_scope_tokens_never_reach_gateway(self):
        missing = await self.rpc("tools/call", self.call_params())
        self.assertEqual(missing.status_code, 401)
        wrong = await self.rpc(
            "tools/call",
            self.call_params(),
            token=self.token(scope="mastermind.dialogue.read"),
        )
        self.assertEqual(wrong.status_code, 401)
        self.assertEqual(self.gateway.calls, [])

    async def test_post_effect_auth_expiry_becomes_effect_unknown_not_retry_signal(self):
        token = self.token()
        await self.replace_gateway(
            StubGateway(
                clock_ref=self.clock,
                state="success",
                expire_after_call=True,
            )
        )
        data = self.result(
            await self.rpc("tools/call", self.call_params(), token=token)
        )
        self.assertTrue(data.get("isError", False), data)
        result = data["structuredContent"]
        self.assertEqual(result["state"], "EFFECT_UNKNOWN")
        self.assertEqual(result["message_key"], MESSAGE_KEY)
        self.assertEqual(len(self.gateway.calls), 1)
        self.assertNotIn("accepted", result)

    async def test_no_effect_error_plus_auth_change_stays_non_effect_unknown(self):
        token = self.token()
        await self.replace_gateway(
            StubGateway(
                clock_ref=self.clock,
                state="changed",
                expire_after_call=True,
            )
        )
        data = self.result(
            await self.rpc("tools/call", self.call_params(), token=token)
        )
        result = data["structuredContent"]
        self.assertEqual(result["state"], "AUTHENTICATION_CHANGED")
        self.assertEqual(result["message_key"], MESSAGE_KEY)
        self.assertEqual(len(self.gateway.calls), 1)

    async def test_gateway_exception_or_malformed_result_is_sanitized_unknown(self):
        for state in ("raise", "malformed"):
            await self.replace_gateway(StubGateway(clock_ref=self.clock, state=state))
            data = self.result(
                await self.rpc(
                    "tools/call",
                    self.call_params(),
                    token=self.token(),
                )
            )
            self.assertTrue(data.get("isError", False), data)
            result = data["structuredContent"]
            self.assertEqual(result["state"], "EFFECT_UNKNOWN")
            self.assertNotIn("SECRET", json.dumps(result, sort_keys=True))
            self.assertEqual(len(self.gateway.calls), 1)

    async def test_unknown_tool_does_not_reach_gateway(self):
        data = self.result(
            await self.rpc(
                "tools/call",
                {"name": "accept_candidate", "arguments": {}},
                token=self.token(),
            )
        )
        self.assertTrue(data.get("isError", False), data)
        self.assertEqual(data["structuredContent"]["state"], "INVALID_REQUEST")
        self.assertEqual(self.gateway.calls, [])


class WorkspaceReturnConstructionTests(unittest.TestCase):
    def test_scope_and_verifier_composition_are_exact(self):
        clock = [int(time.time())]
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
        public.update(kid="fixture-key", alg="RS256", use="sig")
        subject = subject_digest(issuer=ISSUER, subject="workspace-agent-a")

        def policy(scope, subjects=None):
            allowed_subjects = [subject] if subjects is None else list(subjects)
            return load_resource_policy(
                {
                    "schema": "mastermind.business_mcp_auth_policy.v1",
                    "policy_id": "fixture.workspace.return",
                    "resource": RESOURCE,
                    "resource_metadata_url": METADATA,
                    "issuer": ISSUER,
                    "authorization_servers": [ISSUER],
                    "jwks_uri": ISSUER + "/jwks",
                    "required_scopes": [scope],
                    "allowed_subject_digests": allowed_subjects,
                    "allowed_algorithms": ["RS256"],
                    "clock_skew_seconds": 0,
                    "max_token_lifetime_seconds": 3600,
                    "jwks_cache_ttl_seconds": 60,
                    "unknown_kid_refresh_cooldown_seconds": 1,
                    "fetch_failure_backoff_seconds": 1,
                }
            )

        good = policy(REQUIRED_SCOPE)
        wrong = policy("mastermind.dialogue.read")
        verifier = MastermindTokenVerifier(
            authenticator=JwtAuthenticator(policy=good, jwks_cache=Keys(public)),
            policy=good,
            now=lambda: clock[0],
            audit_sink=Audit(),
        )
        gateway = StubGateway(clock_ref=clock)
        with self.assertRaisesRegex(ValueError, "must require exactly"):
            create_authenticated_return_server(
                gateway=gateway,
                policy=wrong,
                token_verifier=verifier,
                allowed_hosts=("127.0.0.1",),
            )
        with self.assertRaisesRegex(ValueError, "policy must match"):
            mismatch_verifier = MastermindTokenVerifier(
                authenticator=JwtAuthenticator(
                    policy=wrong,
                    jwks_cache=Keys(public),
                ),
                policy=wrong,
                now=lambda: clock[0],
                audit_sink=Audit(),
            )
            create_authenticated_return_server(
                gateway=gateway,
                policy=good,
                token_verifier=mismatch_verifier,
                allowed_hosts=("127.0.0.1",),
            )
        second_subject = subject_digest(
            issuer=ISSUER,
            subject="workspace-agent-b",
        )
        shared_subject_policy = policy(
            REQUIRED_SCOPE,
            subjects=[subject, second_subject],
        )
        shared_subject_verifier = MastermindTokenVerifier(
            authenticator=JwtAuthenticator(
                policy=shared_subject_policy,
                jwks_cache=Keys(public),
            ),
            policy=shared_subject_policy,
            now=lambda: clock[0],
            audit_sink=Audit(),
        )
        with self.assertRaisesRegex(ValueError, "exactly one caller subject"):
            create_authenticated_return_server(
                gateway=gateway,
                policy=shared_subject_policy,
                token_verifier=shared_subject_verifier,
                allowed_hosts=("127.0.0.1",),
            )
        with self.assertRaisesRegex(ValueError, "allowed_hosts"):
            create_authenticated_return_server(
                gateway=gateway,
                policy=good,
                token_verifier=verifier,
                allowed_hosts=(),
            )


if __name__ == "__main__":
    unittest.main()
