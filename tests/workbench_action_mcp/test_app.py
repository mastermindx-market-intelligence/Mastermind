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

from integrations.business_mcp_auth.contracts import load_resource_policy, subject_digest
from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator
from integrations.workbench_action_mcp.app import (
    COMMIT_TOOL,
    PREPARE_TOOL,
    RECONCILE_TOOL,
    create_authenticated_action_server,
)
from integrations.workbench_action_mcp.patch_port import ProjectActionRefused

ISSUER = "https://identity.workbench-action.example"
RESOURCE = "https://workbench-action.example/mcp"
SCOPE = "workbench.action"
DIGEST_A = "a" * 64
DIGEST_B = "b" * 64


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


class WorkbenchActionAppTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.clock = int(time.time())
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.pem = self.key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
        public = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(self.key.public_key()))
        public.update(kid="fixture-key", alg="RS256", use="sig")
        self.subject = subject_digest(issuer=ISSUER, subject="operator-a")
        self.policy = load_resource_policy(
            {
                "schema": "mastermind.business_mcp_auth_policy.v1",
                "policy_id": "fixture.workbench.action",
                "resource": RESOURCE,
                "resource_metadata_url": "https://workbench-action.example/.well-known/oauth-protected-resource/mcp",
                "issuer": ISSUER,
                "authorization_servers": [ISSUER],
                "jwks_uri": ISSUER + "/jwks",
                "required_scopes": [SCOPE],
                "allowed_subject_digests": [self.subject],
                "allowed_algorithms": ["RS256"],
                "clock_skew_seconds": 0,
                "max_token_lifetime_seconds": 3600,
                "jwks_cache_ttl_seconds": 60,
                "unknown_kid_refresh_cooldown_seconds": 1,
                "fetch_failure_backoff_seconds": 1,
            }
        )
        self.auth = JwtAuthenticator(policy=self.policy, jwks_cache=Keys(public))
        self.audit = Audit()
        self.calls = []
        self.receipts = []
        self.refuse_commit = False

        async def prepare(caller, request):
            self.calls.append(("prepare", caller, dict(request)))
            return {
                "status": "PREPARED",
                "action_ref": "p" * 32,
                "project_ref": request["project_ref"],
                "responsibility_ref": "responsibility:alpha",
                "operation_ref": "operation:alpha",
                "relative_path": request["relative_path"],
                "preimage_sha256": DIGEST_A if request["mode"] == "REPLACE" else None,
                "postimage_sha256": DIGEST_B,
                "expires_at_ms": self.clock * 1000 + 60_000,
            }

        async def commit(caller, action_ref):
            self.calls.append(("commit", caller, action_ref))
            if self.refuse_commit:
                raise ProjectActionRefused("ACTION_PREIMAGE_MISMATCH")
            return {
                "status": "OK",
                "effect_state": "APPLIED",
                "cleanup_state": "UNCERTAIN",
                "project_ref": "project:alpha",
                "responsibility_ref": "responsibility:alpha",
                "operation_ref": "operation:alpha",
                "relative_path": "sample.py",
                "preimage_sha256": DIGEST_A,
                "postimage_sha256": DIGEST_B,
                "observed_sha256": DIGEST_B,
            }

        async def reconcile(caller, action_ref):
            self.calls.append(("reconcile", caller, action_ref))
            return {
                "status": "OK",
                "effect_state": "NOT_APPLIED",
                "cleanup_state": "CLEAN",
                "project_ref": "project:alpha",
                "responsibility_ref": "responsibility:alpha",
                "operation_ref": "operation:alpha",
                "relative_path": "sample.py",
                "preimage_sha256": DIGEST_A,
                "postimage_sha256": DIGEST_B,
                "observed_sha256": DIGEST_A,
            }

        self.server = create_authenticated_action_server(
            authenticator=self.auth,
            policy=self.policy,
            now=lambda: self.clock,
            audit_sink=self.audit,
            prepare_port=prepare,
            commit_port=commit,
            reconcile_port=reconcile,
            allowed_hosts=("127.0.0.1", "127.0.0.1:*"),
            call_receipt_sink=self.receipts.append,
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
            "sub": "operator-a",
            "aud": RESOURCE,
            "iat": self.clock - 1,
            "exp": self.clock + 600,
            "scope": SCOPE,
            "client_id": "fixture-client",
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
            json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}},
        )

    def result(self, response):
        self.assertEqual(response.status_code, 200, response.text[:300])
        body = response.json()
        self.assertIn("result", body, body)
        return body["result"]

    async def test_tool_discovery_is_explicit_about_write_semantics(self):
        data = self.result(await self.rpc("tools/list", token=self.token()))
        self.assertEqual(
            [tool["name"] for tool in data["tools"]],
            [PREPARE_TOOL, COMMIT_TOOL, RECONCILE_TOOL],
        )
        rows = {tool["name"]: tool for tool in data["tools"]}
        self.assertTrue(rows[PREPARE_TOOL]["annotations"]["readOnlyHint"])
        self.assertFalse(rows[PREPARE_TOOL]["annotations"]["destructiveHint"])
        self.assertFalse(rows[COMMIT_TOOL]["annotations"]["readOnlyHint"])
        self.assertTrue(rows[COMMIT_TOOL]["annotations"]["destructiveHint"])
        self.assertTrue(rows[COMMIT_TOOL]["annotations"]["idempotentHint"])
        self.assertFalse(rows[COMMIT_TOOL]["annotations"]["openWorldHint"])
        self.assertTrue(rows[RECONCILE_TOOL]["annotations"]["readOnlyHint"])

    async def test_prepare_and_commit_cross_actual_mcp_auth_boundary(self):
        prepare = self.result(
            await self.rpc(
                "tools/call",
                {
                    "name": PREPARE_TOOL,
                    "arguments": {
                        "project_ref": "project:alpha",
                        "relative_path": "sample.py",
                        "mode": "REPLACE",
                        "expected_sha256": DIGEST_A,
                        "old_text": "old",
                        "new_text": "new",
                    },
                },
                token=self.token(),
            )
        )
        self.assertFalse(prepare.get("isError", False), prepare)
        self.assertEqual(prepare["structuredContent"]["status"], "PREPARED")
        ref = prepare["structuredContent"]["action_ref"]
        committed = self.result(
            await self.rpc(
                "tools/call",
                {"name": COMMIT_TOOL, "arguments": {"action_ref": ref}},
                token=self.token(),
            )
        )
        self.assertFalse(committed.get("isError", False), committed)
        self.assertEqual(committed["structuredContent"]["effect_state"], "APPLIED")
        self.assertEqual(committed["structuredContent"]["cleanup_state"], "UNCERTAIN")
        self.assertEqual([row[0] for row in self.calls], ["prepare", "commit"])
        self.assertEqual(self.calls[0][1].subject_digest, self.subject)
        self.assertEqual([row["phase"] for row in self.receipts], ["RECEIVED", "RECEIVED"])
        self.assertEqual([row["tool"] for row in self.receipts], [PREPARE_TOOL, COMMIT_TOOL])
        self.assertTrue(all(len(row["call_ref"]) == 64 for row in self.receipts))
        serialized = json.dumps(self.receipts, sort_keys=True)
        self.assertNotIn("old_text", serialized)
        self.assertNotIn("new_text", serialized)
        self.assertNotIn(ref, serialized)

    async def test_wrong_scope_is_rejected_before_action_port(self):
        response = await self.rpc(
            "tools/call",
            {"name": RECONCILE_TOOL, "arguments": {"action_ref": "p" * 32}},
            token=self.token(scope="workbench.read"),
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(self.calls, [])

    async def test_commit_refusal_is_sanitized_and_does_not_fallback(self):
        self.refuse_commit = True
        data = self.result(
            await self.rpc(
                "tools/call",
                {"name": COMMIT_TOOL, "arguments": {"action_ref": "p" * 32}},
                token=self.token(),
            )
        )
        self.assertTrue(data["isError"])
        payload = json.loads(data["content"][0]["text"])
        self.assertEqual(payload, {"code": "ACTION_PREIMAGE_MISMATCH"})
        self.assertEqual([row[0] for row in self.calls], ["commit"])


if __name__ == "__main__":
    unittest.main()
