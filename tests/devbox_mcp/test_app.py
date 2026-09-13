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
from integrations.devbox_mcp.app import create_authenticated_devbox_server
from integrations.devbox_mcp.contracts import TOOL_NAMES

ISSUER = "https://identity.devbox.example"
RESOURCE = "https://devbox.example/mcp"
SCOPE = "workbench.execute"
PROCESS_REF = "process:" + "a" * 64


class Keys:
    def __init__(self, jwk):
        self.jwk = jwk

    async def key_for(self, kid):
        if kid != "fixture-key":
            raise ValueError("unknown synthetic key")
        return self.jwk


class Audit:
    def __init__(self):
        self.events = []

    def emit(self, event):
        self.events.append(dataclasses.asdict(event))


class Port:
    def __init__(self, clock):
        self.clock = clock
        self.calls = []
        self.mode = "normal"

    async def call(self, caller, tool_name, arguments):
        self.calls.append((caller, tool_name, dict(arguments)))
        await asyncio.sleep(0)
        if self.mode == "exception":
            raise RuntimeError("PRIVATE_PROVIDER_EXCEPTION")
        if self.mode == "expire":
            self.clock[0] += 7200
        if self.mode == "bad-output":
            return {"PRIVATE_PROVIDER_OUTPUT": "must-not-escape"}
        if tool_name == "devbox_status":
            return {
                "target_ref": "target:" + "1" * 64,
                "generation": "generation:" + "2" * 64,
                "owner_ref": "owner:" + "3" * 64,
                "repository": "mastermindx-market-intelligence/Mastermind",
                "committed_head": "4" * 40,
                "observed_head": "4" * 40,
                "working_tree_dirty": False,
                "execution_profile": "ATTENDED_ONLY",
                "provider": "github_codespaces",
            }
        if tool_name == "start_devbox_command":
            return {
                "process_ref": PROCESS_REF,
                "effect_state": "APPLIED",
                "terminal": False,
                "reconciled": False,
            }
        if tool_name == "read_devbox_process":
            stream = {
                "text": "ok",
                "start_cursor": 0,
                "next_cursor": 2,
                "total_bytes": 2,
                "retained_bytes": 2,
                "dropped_bytes": 0,
                "truncated": False,
                "gap_ranges": [],
            }
            return {
                "process_ref": PROCESS_REF,
                "effect_state": "APPLIED",
                "terminal": True,
                "exit_code": 0,
                "timed_out": False,
                "cancel_requested": False,
                "stdout": stream,
                "stderr": {**stream, "text": ""},
            }
        if tool_name == "cancel_devbox_process":
            return {
                "process_ref": PROCESS_REF,
                "cancel_requested": True,
                "terminal": False,
            }
        raise AssertionError(tool_name)


class DevBoxAppTests(unittest.IsolatedAsyncioTestCase):
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
        self.keys = Keys(public)
        self.audit = Audit()
        self.subject = subject_digest(issuer=ISSUER, subject="pro-chairman-seat")
        self.policy = load_resource_policy(
            {
                "schema": "mastermind.business_mcp_auth_policy.v1",
                "policy_id": "fixture.devbox.execute",
                "resource": RESOURCE,
                "resource_metadata_url": "https://devbox.example/.well-known/oauth-protected-resource/mcp",
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
        self.auth = JwtAuthenticator(policy=self.policy, jwks_cache=self.keys)
        self.port = Port(self.clock)
        self.server = create_authenticated_devbox_server(
            authenticator=self.auth,
            policy=self.policy,
            now=lambda: self.clock[0],
            audit_sink=self.audit,
            devbox_port=self.port,
            allowed_hosts=("127.0.0.1", "127.0.0.1:*"),
        )
        self.app = self.server.streamable_http_app()
        self.ready = asyncio.Event()
        self.stop = asyncio.Event()

        async def own_lifespan():
            async with self.app.router.lifespan_context(self.app):
                self.ready.set()
                await self.stop.wait()

        self.lifespan_task = asyncio.create_task(own_lifespan())
        await asyncio.wait_for(self.ready.wait(), timeout=5)
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app), base_url="http://127.0.0.1"
        )

    async def asyncTearDown(self):
        await self.client.aclose()
        self.stop.set()
        await asyncio.wait_for(self.lifespan_task, timeout=5)

    def token(self, **changes):
        payload = {
            "iss": ISSUER,
            "sub": "pro-chairman-seat",
            "aud": RESOURCE,
            "iat": self.clock[0] - 1,
            "exp": self.clock[0] + 600,
            "scope": SCOPE,
            "client_id": "fixture-pro-client",
        }
        payload.update(changes)
        return jwt.encode(
            payload, self.pem, algorithm="RS256", headers={"kid": "fixture-key"}
        )

    async def rpc(self, method, params=None, token=None, origin=None):
        headers = {
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": "2025-03-26",
        }
        if token is not None:
            headers["Authorization"] = "Bearer " + token
        if origin:
            headers["Origin"] = origin
        return await self.client.post(
            "/mcp",
            headers=headers,
            json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}},
        )

    async def call(self, name, arguments=None, token=None):
        return await self.rpc(
            "tools/call",
            {"name": name, "arguments": arguments or {}},
            token=self.token() if token is None else token,
        )

    def result(self, response):
        self.assertEqual(response.status_code, 200, response.text[:500])
        body = response.json()
        self.assertIn("result", body, body)
        return body["result"]

    async def test_initialize_uses_real_sdk(self):
        response = await self.rpc(
            "initialize",
            {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1"},
            },
            token=self.token(),
        )
        self.assertIn("serverInfo", self.result(response))
        self.assertEqual(self.port.calls, [])

    async def test_tool_discovery_is_exact_closed_four_tool_surface(self):
        data = self.result(await self.rpc("tools/list", token=self.token()))
        self.assertEqual([row["name"] for row in data["tools"]], list(TOOL_NAMES))
        by_name = {row["name"]: row for row in data["tools"]}
        for row in data["tools"]:
            self.assertFalse(row["inputSchema"]["additionalProperties"])
            self.assertFalse(row["annotations"]["openWorldHint"])
        self.assertTrue(by_name["devbox_status"]["annotations"]["readOnlyHint"])
        self.assertTrue(by_name["read_devbox_process"]["annotations"]["readOnlyHint"])
        self.assertFalse(by_name["start_devbox_command"]["annotations"]["readOnlyHint"])
        self.assertFalse(by_name["cancel_devbox_process"]["annotations"]["readOnlyHint"])

    async def test_authenticated_calls_project_only_pseudonymous_caller_to_port(self):
        start = self.result(
            await self.call(
                "start_devbox_command",
                {"operation_key": "mcp-start", "command_text": "printf ok"},
            )
        )
        self.assertFalse(start.get("isError", False), start)
        self.assertEqual(start["structuredContent"]["process_ref"], PROCESS_REF)
        caller, name, args = self.port.calls[-1]
        self.assertEqual(name, "start_devbox_command")
        self.assertEqual(args, {"operation_key": "mcp-start", "command_text": "printf ok"})
        self.assertEqual(caller.subject_digest, self.subject)
        self.assertEqual(caller.resource, RESOURCE)
        self.assertEqual(caller.scopes, (SCOPE,))
        self.assertNotIn("pro-chairman-seat", repr(caller))

    async def test_all_four_tools_dispatch_through_same_port(self):
        self.result(await self.call("devbox_status"))
        self.result(
            await self.call(
                "start_devbox_command",
                {"operation_key": "dispatch", "command_text": "true"},
            )
        )
        self.result(
            await self.call(
                "read_devbox_process", {"process_ref": PROCESS_REF, "max_bytes": 4096}
            )
        )
        self.result(
            await self.call(
                "cancel_devbox_process", {"process_ref": PROCESS_REF, "reason": "stop"}
            )
        )
        self.assertEqual([item[1] for item in self.port.calls], list(TOOL_NAMES))

    async def test_missing_or_wrong_auth_never_reaches_port(self):
        missing = await self.call("devbox_status", token="")
        self.assertEqual(missing.status_code, 401)
        wrong = await self.call("devbox_status", token=self.token(scope="workbench.read"))
        self.assertEqual(wrong.status_code, 401)
        self.assertEqual(self.port.calls, [])

    async def test_model_cannot_supply_target_cwd_env_or_credentials(self):
        for extra in (
            {"target_ref": "target:" + "9" * 64},
            {"cwd": "/tmp"},
            {"env": {"GH_TOKEN": "x"}},
            {"token": "secret"},
        ):
            args = {"operation_key": "closed-input", "command_text": "true", **extra}
            result = self.result(await self.call("start_devbox_command", args))
            self.assertTrue(result["isError"])
        self.assertEqual(self.port.calls, [])

    async def test_unknown_tool_and_oversized_input_are_bounded_without_echo(self):
        marker = "PRIVATE_CALLER_PAYLOAD_" * 2000
        unknown = self.result(await self.call("shell", {"command_text": marker}))
        self.assertTrue(unknown["isError"])
        self.assertNotIn(marker[:100], json.dumps(unknown))
        oversized = self.result(
            await self.call(
                "start_devbox_command",
                {"operation_key": "too-large", "command_text": marker},
            )
        )
        self.assertTrue(oversized["isError"])
        self.assertLess(len(json.dumps(oversized).encode()), 1024)
        self.assertEqual(self.port.calls, [])

    async def test_maximum_valid_dual_stream_result_stays_bounded_and_visible(self):
        async def large_call(caller, tool_name, arguments):
            self.port.calls.append((caller, tool_name, dict(arguments)))
            if tool_name != "read_devbox_process":
                raise AssertionError(tool_name)
            size = 250_000
            def stream(text):
                return {
                    "text": text,
                    "start_cursor": 0,
                    "next_cursor": size,
                    "total_bytes": size,
                    "retained_bytes": size,
                    "dropped_bytes": 0,
                    "truncated": False,
                    "gap_ranges": [],
                }
            return {
                "process_ref": PROCESS_REF,
                "effect_state": "APPLIED",
                "terminal": True,
                "exit_code": 0,
                "timed_out": False,
                "cancel_requested": False,
                "stdout": stream("x" * size),
                "stderr": stream("y" * size),
            }

        self.port.call = large_call
        result = self.result(
            await self.call(
                "read_devbox_process",
                {"process_ref": PROCESS_REF, "max_bytes": 262144},
            )
        )
        self.assertFalse(result.get("isError", False), result)
        self.assertEqual(len(result["structuredContent"]["stdout"]["text"]), 250_000)
        self.assertEqual(len(result["structuredContent"]["stderr"]["text"]), 250_000)
        self.assertLess(len(json.dumps(result).encode()), 2 * 1024 * 1024)

    async def test_provider_exception_or_malformed_output_is_private(self):
        self.port.mode = "exception"
        result = self.result(await self.call("devbox_status"))
        self.assertTrue(result["isError"])
        self.assertNotIn("PRIVATE_PROVIDER_EXCEPTION", json.dumps(result))
        self.port.mode = "bad-output"
        result = self.result(await self.call("devbox_status"))
        self.assertTrue(result["isError"])
        self.assertNotIn("PRIVATE_PROVIDER_OUTPUT", json.dumps(result))

    async def test_auth_change_after_await_withholds_even_modifying_result(self):
        self.port.mode = "expire"
        result = self.result(
            await self.call(
                "start_devbox_command",
                {"operation_key": "effect-may-exist", "command_text": "true"},
            )
        )
        self.assertTrue(result["isError"])
        self.assertEqual(len(self.port.calls), 1)
        self.assertNotIn(PROCESS_REF, json.dumps(result))

    async def test_forbidden_origin_never_reaches_port(self):
        response = await self.rpc(
            "tools/list", token=self.token(), origin="https://hostile.example"
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.port.calls, [])

    async def test_audit_never_contains_raw_subject_token_or_command(self):
        token = self.token()
        command = "printf PRIVATE_COMMAND"
        self.result(
            await self.call(
                "start_devbox_command",
                {"operation_key": "audit-redaction", "command_text": command},
                token=token,
            )
        )
        rendered = json.dumps(self.audit.events)
        self.assertNotIn(token, rendered)
        self.assertNotIn("pro-chairman-seat", rendered)
        self.assertNotIn(command, rendered)
        self.assertTrue(self.audit.events)


if __name__ == "__main__":
    unittest.main(verbosity=2)
