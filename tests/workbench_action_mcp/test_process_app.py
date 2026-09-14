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
from integrations.workbench_action_mcp.app import create_authenticated_action_server
from integrations.workbench_action_mcp.process_mcp import (
    LIST_RECIPES_TOOL,
    PREPARE_COMMAND_TOOL,
    READ_PROCESS_TOOL,
    RECONCILE_COMMAND_TOOL,
    START_COMMAND_TOOL,
)
from integrations.workbench_action_mcp.process_port import AttendedProcessPorts

ISSUER = "https://identity.workbench-action.example"
RESOURCE = "https://workbench-action.example/mcp"
DIGEST = "d" * 64
GENERATION = "generation:alpha"


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


class ProcessAppTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.clock = int(time.time())
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.pem = key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
        public = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
        public.update(kid="fixture-key", alg="RS256", use="sig")
        self.subject = subject_digest(issuer=ISSUER, subject="operator-a")
        self.policy = load_resource_policy(
            {
                "schema": "mastermind.business_mcp_auth_policy.v1",
                "policy_id": "fixture.workbench.action.process",
                "resource": RESOURCE,
                "resource_metadata_url": "https://workbench-action.example/.well-known/oauth-protected-resource/mcp",
                "issuer": ISSUER,
                "authorization_servers": [ISSUER],
                "jwks_uri": ISSUER + "/jwks",
                "required_scopes": ["workbench.action"],
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
        self.receipts = []
        self.calls = []
        self.expire_after_start = False
        self.command_ref = "c" * 32

        async def patch_prepare(caller, request):
            raise AssertionError("patch port not expected")

        async def patch_commit(caller, ref):
            raise AssertionError("patch port not expected")

        async def patch_reconcile(caller, ref):
            raise AssertionError("patch port not expected")

        async def list_recipes(caller, project_ref):
            self.calls.append(("list", project_ref))
            return {
                "status": "OK",
                "project_ref": project_ref,
                "generation": GENERATION,
                "observed_at_ms": self.clock * 1000,
                "recipes": [
                    {
                        "recipe_id": "git.diff-check",
                        "description": "Validate whitespace errors.",
                        "timeout_seconds": 20,
                        "max_output_bytes": 65536,
                        "recipe_digest": DIGEST,
                    }
                ],
            }

        async def prepare(caller, request):
            self.calls.append(("prepare-command", dict(request)))
            return {
                "status": "PREPARED",
                "command_ref": self.command_ref,
                "process_ref": "command:alpha",
                "project_ref": request["project_ref"],
                "responsibility_ref": "responsibility:alpha",
                "operation_ref": "operation:alpha",
                "generation": GENERATION,
                "recipe_id": request["recipe_id"],
                "recipe_digest": DIGEST,
                "runner_digest": DIGEST,
                "timeout_seconds": request.get("timeout_seconds", 20),
                "max_output_bytes": request.get("max_output_bytes", 65536),
                "expires_at_ms": self.clock * 1000 + 60_000,
            }

        def state(process_state="RUNNING"):
            return {
                "status": "OK",
                "effect_state": "APPLIED",
                "process_state": process_state,
                "process_ref": "command:alpha",
                "project_ref": "project:alpha",
                "responsibility_ref": "responsibility:alpha",
                "operation_ref": "operation:alpha",
                "generation": GENERATION,
                "recipe_id": "git.diff-check",
                "recipe_digest": DIGEST,
                "runner_digest": DIGEST,
                "observed_at_ms": self.clock * 1000,
                "exit_code": 0 if process_state == "EXITED" else None,
                "stdout_bytes": 3,
                "stderr_bytes": 0,
            }

        async def start(caller, ref):
            self.calls.append(("start", ref))
            result = state("RUNNING")
            if self.expire_after_start:
                self.clock += 7200
            return result

        async def reconcile(caller, ref):
            self.calls.append(("reconcile-start", ref))
            return state("EXITED")

        async def read(caller, request):
            self.calls.append(("read", dict(request)))
            result = state("EXITED")
            page = {
                "offset_start": 0,
                "offset_end": 3,
                "retained_start": 0,
                "retained_end": 3,
                "gap_ranges": [],
                "content": "ok\n",
                "truncated": False,
                "next_offset": None,
            }
            result.update(stdout=page, stderr={**page, "offset_end": 0, "retained_end": 0, "content": ""})
            return result

        process_ports = AttendedProcessPorts(
            list_recipes=list_recipes,
            prepare=prepare,
            start=start,
            reconcile_start=reconcile,
            read=read,
        )
        self.server = create_authenticated_action_server(
            authenticator=self.auth,
            policy=self.policy,
            now=lambda: self.clock,
            audit_sink=self.audit,
            prepare_port=patch_prepare,
            commit_port=patch_commit,
            reconcile_port=patch_reconcile,
            process_ports=process_ports,
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
            "scope": "workbench.action",
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

    async def call(self, name, arguments):
        return self.result(
            await self.rpc(
                "tools/call",
                {"name": name, "arguments": arguments},
                token=self.token(),
            )
        )

    async def test_process_tools_are_explicit_and_start_is_effectful(self):
        data = self.result(await self.rpc("tools/list", token=self.token()))
        rows = {tool["name"]: tool for tool in data["tools"]}
        for name in (
            LIST_RECIPES_TOOL,
            PREPARE_COMMAND_TOOL,
            START_COMMAND_TOOL,
            RECONCILE_COMMAND_TOOL,
            READ_PROCESS_TOOL,
        ):
            self.assertIn(name, rows)
        self.assertTrue(rows[LIST_RECIPES_TOOL]["annotations"]["readOnlyHint"])
        self.assertTrue(rows[PREPARE_COMMAND_TOOL]["annotations"]["readOnlyHint"])
        self.assertFalse(rows[START_COMMAND_TOOL]["annotations"]["readOnlyHint"])
        self.assertTrue(rows[START_COMMAND_TOOL]["annotations"]["destructiveHint"])
        self.assertTrue(rows[RECONCILE_COMMAND_TOOL]["annotations"]["readOnlyHint"])
        self.assertTrue(rows[READ_PROCESS_TOOL]["annotations"]["readOnlyHint"])

    async def test_process_journey_crosses_real_auth_boundary(self):
        listed = await self.call(LIST_RECIPES_TOOL, {"project_ref": "project:alpha"})
        self.assertEqual(listed["structuredContent"]["recipes"][0]["recipe_id"], "git.diff-check")
        prepared = await self.call(
            PREPARE_COMMAND_TOOL,
            {"project_ref": "project:alpha", "recipe_id": "git.diff-check"},
        )
        ref = prepared["structuredContent"]["command_ref"]
        started = await self.call(START_COMMAND_TOOL, {"command_ref": ref})
        self.assertEqual(started["structuredContent"]["effect_state"], "APPLIED")
        reconciled = await self.call(RECONCILE_COMMAND_TOOL, {"command_ref": ref})
        self.assertEqual(reconciled["structuredContent"]["process_state"], "EXITED")
        observed = await self.call(READ_PROCESS_TOOL, {"command_ref": ref})
        self.assertEqual(observed["structuredContent"]["stdout"]["content"], "ok\n")
        self.assertEqual(
            [row[0] for row in self.calls],
            ["list", "prepare-command", "start", "reconcile-start", "read"],
        )
        serialized = json.dumps(self.receipts, sort_keys=True)
        self.assertNotIn(ref, serialized)
        self.assertEqual(len(self.receipts), 5)

    async def test_post_start_auth_loss_is_effect_unknown_not_retry_signal(self):
        self.expire_after_start = True
        data = await self.call(START_COMMAND_TOOL, {"command_ref": self.command_ref})
        self.assertTrue(data["isError"])
        payload = json.loads(data["content"][0]["text"])
        self.assertEqual(payload, {"code": "PROCESS_EFFECT_UNKNOWN"})
        self.assertEqual([row[0] for row in self.calls], ["start"])


if __name__ == "__main__":
    unittest.main()
