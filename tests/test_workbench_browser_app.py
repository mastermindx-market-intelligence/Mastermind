from __future__ import annotations

import asyncio
import dataclasses
import json
import time
import unittest
from pathlib import Path

import httpx
import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from integrations.business_mcp_auth.contracts import load_resource_policy, subject_digest
from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator
from integrations.workbench_browser_mcp.app import (
    PREPARE_RESOURCE_TOOL,
    RECONCILE_ACTION_TOOL,
    RECONCILE_RESOURCE_TOOL,
    RUN_ACTION_TOOL,
    START_RESOURCE_TOOL,
    create_authenticated_browser_server,
)


ISSUER = "https://identity.workbench-browser.example"
RESOURCE = "https://workbench-browser.example/mcp"
SCOPE = "workbench.action"
# Independent expected bytes: inspected actual JWT-authenticated FastMCP tools/list
# from the reviewed MCP SDK 1.28.1 + fixed Browser source tool catalog.
# Deliberately NOT recomputed from each new observed response.
BROWSER_SNAPSHOT_SOURCE_TOOL_DIGEST = "b7edce1d0557afb4d96d62802ae3091c2301e95b1c011bee6099929e4139aa9a"


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


class WorkbenchBrowserAppTests(unittest.IsolatedAsyncioTestCase):
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
                "policy_id": "fixture.workbench.browser",
                "resource": RESOURCE,
                "resource_metadata_url": "https://workbench-browser.example/.well-known/oauth-protected-resource/mcp",
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
        self.browser_ref = "b" * 32
        self.action_ref = "a" * 32
        self.start_ref = "s" * 32

        async def prepare_resource(caller, project_ref, mode, profile_ref):
            self.calls.append(
                ("prepare_resource", caller, project_ref, mode, profile_ref)
            )
            return self.start_ref

        async def start_resource(caller, start_ref):
            self.calls.append(("start_resource", caller, start_ref))
            return {
                "status": "OK",
                "effect_state": "APPLIED",
                "browser_ref": self.browser_ref,
                "reconciled": False,
            }

        async def reconcile_resource(caller, start_ref):
            self.calls.append(("reconcile_resource", caller, start_ref))
            return {
                "status": "OK",
                "effect_state": "NOT_APPLIED",
                "browser_ref": None,
                "reconciled": True,
            }

        async def read_tool(caller, browser_ref, tool, arguments):
            self.calls.append(
                ("read_tool", caller, browser_ref, tool, dict(arguments))
            )
            return {
                "content": [{"type": "text", "text": "snapshot"}],
                "isError": False,
            }

        async def prepare_action(caller, browser_ref, tool, arguments):
            self.calls.append(
                ("prepare_action", caller, browser_ref, tool, dict(arguments))
            )
            return self.action_ref

        async def run_action(caller, browser_ref, action_ref):
            self.calls.append(("run_action", caller, browser_ref, action_ref))
            return {
                "status": "OK",
                "effect_state": "APPLIED",
                "observed_sha256": "d" * 64,
                "reconciled": False,
                "result": {
                    "content": [{"type": "text", "text": "clicked"}],
                    "isError": False,
                },
            }

        async def reconcile_action(caller, browser_ref, action_ref):
            self.calls.append(
                ("reconcile_action", caller, browser_ref, action_ref)
            )
            return {
                "status": "OK",
                "effect_state": "NOT_APPLIED",
                "observed_sha256": None,
                "reconciled": True,
            }

        catalog = json.loads(
            (
                Path(__file__).resolve().parents[1]
                / "research"
                / "evidence"
                / "claude_browser_mcp_tools_0_0_79.json"
            ).read_text(encoding="utf-8")
        )

        self.server = create_authenticated_browser_server(
            authenticator=self.auth,
            policy=self.policy,
            now=lambda: self.clock,
            audit_sink=self.audit,
            tool_catalog=catalog,
            prepare_resource=prepare_resource,
            start_resource=start_resource,
            reconcile_resource=reconcile_resource,
            read_tool=read_tool,
            prepare_action=prepare_action,
            run_action=run_action,
            reconcile_action=reconcile_action,
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
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": method,
                "params": params or {},
            },
        )

    def result(self, response):
        self.assertEqual(response.status_code, 200, response.text[:300])
        body = response.json()
        self.assertIn("result", body, body)
        return body["result"]

    async def tool_call(self, name, arguments):
        return self.result(
            await self.rpc(
                "tools/call",
                {"name": name, "arguments": arguments},
                token=self.token(),
            )
        )

    async def test_tool_catalog_separates_read_mutation_and_cleanup_authority(self):
        data = self.result(await self.rpc("tools/list", token=self.token()))
        rows = {tool["name"]: tool for tool in data["tools"]}

        self.assertIn(PREPARE_RESOURCE_TOOL, rows)
        self.assertIn(START_RESOURCE_TOOL, rows)
        self.assertIn(RECONCILE_RESOURCE_TOOL, rows)
        self.assertIn("browser_snapshot", rows)
        self.assertIn("prepare_browser_click", rows)
        self.assertNotIn("browser_click", rows)
        self.assertIn(RUN_ACTION_TOOL, rows)
        self.assertIn(RECONCILE_ACTION_TOOL, rows)

        self.assertTrue(rows["browser_snapshot"]["annotations"]["readOnlyHint"])
        self.assertTrue(rows["prepare_browser_click"]["annotations"]["readOnlyHint"])
        self.assertFalse(rows[RUN_ACTION_TOOL]["annotations"]["readOnlyHint"])
        self.assertTrue(rows[RUN_ACTION_TOOL]["annotations"]["destructiveHint"])
        self.assertTrue(rows[RUN_ACTION_TOOL]["annotations"]["idempotentHint"])
        self.assertFalse(rows[START_RESOURCE_TOOL]["annotations"]["readOnlyHint"])

        forbidden = [
            name
            for name in rows
            if "cleanup" in name or "kill" in name or "reap" in name
        ]
        self.assertEqual(forbidden, [])

    async def test_authenticated_resource_read_and_mutation_flow(self):
        prepared = await self.tool_call(
            PREPARE_RESOURCE_TOOL,
            {"project_ref": "project:browser", "mode": "isolated"},
        )
        self.assertFalse(prepared.get("isError", False), prepared)
        start_ref = prepared["structuredContent"]["start_ref"]

        started = await self.tool_call(
            START_RESOURCE_TOOL, {"start_ref": start_ref}
        )
        self.assertFalse(started.get("isError", False), started)
        browser_ref = started["structuredContent"]["browser_ref"]

        snapshot = await self.tool_call(
            "browser_snapshot", {"browser_ref": browser_ref}
        )
        self.assertFalse(snapshot.get("isError", False), snapshot)
        self.assertEqual(snapshot["content"][0]["text"], "snapshot")

        prepared_click = await self.tool_call(
            "prepare_browser_click",
            {"browser_ref": browser_ref, "target": "button"},
        )
        action_ref = prepared_click["structuredContent"]["action_ref"]

        clicked = await self.tool_call(
            RUN_ACTION_TOOL,
            {"browser_ref": browser_ref, "action_ref": action_ref},
        )
        self.assertFalse(clicked.get("isError", False), clicked)
        self.assertEqual(clicked["content"][0]["text"], "clicked")
        self.assertEqual(clicked["structuredContent"]["effect_state"], "APPLIED")

        names = [call[0] for call in self.calls]
        self.assertEqual(
            names,
            [
                "prepare_resource",
                "start_resource",
                "read_tool",
                "prepare_action",
                "run_action",
            ],
        )
        self.assertEqual(self.receipts[-1]["tool"], RUN_ACTION_TOOL)

    async def test_reconcile_tools_do_not_create_new_effect(self):
        resource = await self.tool_call(
            RECONCILE_RESOURCE_TOOL, {"start_ref": self.start_ref}
        )
        self.assertEqual(
            resource["structuredContent"]["effect_state"], "NOT_APPLIED"
        )
        action = await self.tool_call(
            RECONCILE_ACTION_TOOL,
            {"browser_ref": self.browser_ref, "action_ref": self.action_ref},
        )
        self.assertEqual(action["structuredContent"]["effect_state"], "NOT_APPLIED")
        self.assertEqual(
            [call[0] for call in self.calls],
            ["reconcile_resource", "reconcile_action"],
        )

    async def test_missing_auth_and_native_mutating_tool_name_refuse(self):
        unauth = await self.rpc("tools/list")
        self.assertEqual(unauth.status_code, 401)

        unavailable = await self.tool_call(
            "browser_click", {"browser_ref": self.browser_ref, "target": "button"}
        )
        self.assertTrue(unavailable["isError"])
        self.assertIn("TOOL_NOT_AVAILABLE", unavailable["content"][0]["text"])

    async def test_synthetic_browser_snapshot_catalog_projects_only_selected_dsh_tool(self):
        """Project one test-authored Browser tool selection, never a live grant.

        The FastMCP catalog is JWT-authenticated, but the derivative grant is
        synthetic, unsigned, non-admitted and never sent to a model/Browser host.
        Browser "readOnlyHint" does not attest effect-free behavior: the
        snapshot input includes optional "filename" artifact output. The
        original Browser/Runtime owners must qualify its filesystem effects,
        server identity and a real worker's actual tool/resource permissions.
        """
        import copy
        import hashlib

        from control_plane.dsh_mcp_client_projection import (
            DshMcpProjectionError, project_dsh_mcp_tools,
        )
        from control_plane.executive_agent_capabilities import (
            CapabilityPolicyError, ExecutionCapabilityRegistry,
            observed_mcp_tool_schema_digest,
        )

        protocol = self.result(await self.rpc(
            "initialize",
            {"protocolVersion": "2025-03-26", "capabilities": {},
             "clientInfo": {"name": "browser-read-dsh-fixture", "version": "1"}},
            token=self.token(),
        ))
        identity = protocol["serverInfo"]
        self.assertEqual(identity.get("name"), "Mastermind Workbench Browser")
        self.assertIsInstance(identity.get("version"), str)
        self.assertTrue(0 < len(identity["version"]) <= 64)
        observed = self.result(await self.rpc("tools/list", token=self.token()))
        # Do not discard actual owner pagination before the DSH completeness check.
        self.assertIn(observed.get("nextCursor"), (None, ""))
        catalog = dict(observed)
        by_name = {row["name"]: row for row in observed["tools"]}
        self.assertEqual(len(by_name), len(observed["tools"]))
        self.assertIn("browser_snapshot", by_name)
        selected_schema = by_name["browser_snapshot"]["inputSchema"]
        self.assertEqual(selected_schema["type"], "object")
        self.assertIs(selected_schema["additionalProperties"], False)
        self.assertEqual(selected_schema["required"], ["browser_ref"])
        self.assertEqual(set(selected_schema["properties"]),
                         {"browser_ref", "boxes", "depth", "filename", "target"})
        # Current SDK advertises no un-digested execution metadata.
        self.assertNotIn("execution", by_name["browser_snapshot"])
        self.assertIn(RUN_ACTION_TOOL, by_name)
        self.assertIn(START_RESOURCE_TOOL, by_name)
        self.assertTrue(by_name["browser_snapshot"]["annotations"]["readOnlyHint"])
        self.assertFalse(by_name[RUN_ACTION_TOOL]["annotations"]["readOnlyHint"])
        self.assertTrue(by_name[RUN_ACTION_TOOL]["annotations"]["destructiveHint"])
        self.assertFalse(by_name[START_RESOURCE_TOOL]["annotations"]["readOnlyHint"])

        root = Path(__file__).resolve().parents[1]
        protected = ExecutionCapabilityRegistry.load(
            root / "scripts/ohf/fixtures/"
            "executive_agent_capabilities_v4_mastermind_operator.json",
            source_root=root,
        )
        self.assertFalse(protected.production_armed)
        base = protected.resolve("operator.browser.local-review.v1")
        original = next(g for g in base.mcp_server_grants
                        if g.capability_id == "playwright-worker-browser-b1")
        self.assertEqual(original.transport, "stdio")
        self.assertEqual(original.auth_status, "unsupported")
        digest = observed_mcp_tool_schema_digest(
            {"tools": {"browser_snapshot": by_name["browser_snapshot"]}}
        )
        self.assertEqual(digest, BROWSER_SNAPSHOT_SOURCE_TOOL_DIGEST)
        synthetic_capability = "fixture.browser_mcp.snapshot.read_only"
        self.assertNotIn(synthetic_capability, protected.mcp_servers)
        # A trusted registry cannot resolve the artificial unsigned profile.
        with self.assertRaises(CapabilityPolicyError):
            protected.resolve("fixture.browser.read.only.dsh")
        grant = dataclasses.replace(
            original,
            capability_id=synthetic_capability,
            config_name="BrowserReadFixture",
            transport="streamable-http",
            url=RESOURCE,
            command=None, args=(), required=True,
            enabled_tools=("browser_snapshot",),
            default_tools_approval_mode="approve",
            server_identity=identity["name"],
            server_version=identity["version"],
            auth_status="unsupported",
            tool_schema_digest=digest,
            grant_digest=hashlib.sha256(b"SYNTHETIC_BROWSER_DSH_NOT_AUTHORITY").hexdigest(),
        )
        profile = dataclasses.replace(
            base, profile_id="fixture.browser.read.only.dsh",
            profile_digest=hashlib.sha256(b"SYNTHETIC_BROWSER_PROFILE_NOT_ADMITTED").hexdigest(),
            mcp_server_grants=(grant,),
        )
        projected = project_dsh_mcp_tools(
            profile,
            capability_id=synthetic_capability,
            observed_tool_catalog=catalog,
        ).configuration()
        self.assertIs(projected["production_armed"], False)
        self.assertIs(projected["required"], True)
        self.assertEqual(projected["approvalMode"], "approve")
        self.assertEqual(projected["target"], {
            "serverName": "BrowserReadFixture",
            "transport": "streamable-http", "url": RESOURCE,
        })
        self.assertEqual(projected["serverInfo"], {
            "name": identity["name"], "version": identity["version"],
        })
        self.assertEqual(projected["source"]["auth_status"], "unsupported")
        self.assertEqual(projected["source"]["profile_id"], "fixture.browser.read.only.dsh")
        self.assertIsNone(projected["tools"][0]["execution"])
        self.assertEqual(projected["source"]["tool_schema_digest"], digest)
        self.assertEqual([x["name"] for x in projected["tools"]], ["browser_snapshot"])
        self.assertTrue(projected["tools"][0]["annotations"]["readOnlyHint"])
        self.assertFalse(projected["tools"][0]["annotations"]["destructiveHint"])
        self.assertFalse(any(x["name"] in (RUN_ACTION_TOOL, START_RESOURCE_TOOL)
                             for x in projected["tools"]))

        # Only the selected tool is digest-bound; no network/Runtime grant.
        # The mixed live catalog cannot widen a precise grant: changing an
        # UNGRANTED mutating action does not add it to the worker-facing output.
        wider_catalog = copy.deepcopy(catalog)
        next(row for row in wider_catalog["tools"]
             if row["name"] == RUN_ACTION_TOOL)["inputSchema"] = {"type": "null"}
        rerender = project_dsh_mcp_tools(
            profile, capability_id=synthetic_capability,
            observed_tool_catalog=wider_catalog,
        ).configuration()
        self.assertEqual(rerender, projected)

        for mutation in ("inputSchema", "annotations", "outputSchema"):
            changed = copy.deepcopy(catalog)
            selected = next(row for row in changed["tools"]
                            if row["name"] == "browser_snapshot")
            if mutation == "annotations":
                selected[mutation]["readOnlyHint"] = False
            elif mutation == "outputSchema":
                selected[mutation] = {"type": "object", "additionalProperties": False}
            else:
                selected[mutation]["type"] = "null"
            with self.subTest(mutation=mutation):
                with self.assertRaises(DshMcpProjectionError):
                    project_dsh_mcp_tools(
                        profile, capability_id=synthetic_capability,
                        observed_tool_catalog=changed,
                    )
        with self.assertRaises(DshMcpProjectionError):
            project_dsh_mcp_tools(
                profile, capability_id=synthetic_capability,
                observed_tool_catalog={"tools": [r for r in catalog["tools"]
                                                 if r["name"] != "browser_snapshot"]},
            )
        with self.assertRaises(DshMcpProjectionError):
            project_dsh_mcp_tools(
                profile, capability_id=synthetic_capability,
                observed_tool_catalog={**catalog, "nextCursor": "not-complete"},
            )
        wrong_approval = dataclasses.replace(grant, default_tools_approval_mode="auto")
        with self.assertRaises(DshMcpProjectionError):
            project_dsh_mcp_tools(
                dataclasses.replace(profile, mcp_server_grants=(wrong_approval,)),
                capability_id=synthetic_capability,
                observed_tool_catalog=catalog,
            )
        unauthorized = await self.rpc("tools/list")
        self.assertEqual(unauthorized.status_code, 401)
        self.assertEqual(self.calls, [])  # no browser resource/action effects

    async def test_schema_drift_refuses_server_creation(self):
        catalog = json.loads(
            (
                Path(__file__).resolve().parents[1]
                / "research"
                / "evidence"
                / "claude_browser_mcp_tools_0_0_79.json"
            ).read_text(encoding="utf-8")
        )
        next(
            tool for tool in catalog["tools"] if tool["name"] == "browser_snapshot"
        )["inputSchema"]["properties"]["unexpected"] = {"type": "string"}

        with self.assertRaisesRegex(ValueError, "schema drift"):
            create_authenticated_browser_server(
                authenticator=self.auth,
                policy=self.policy,
                now=lambda: self.clock,
                audit_sink=self.audit,
                tool_catalog=catalog,
                prepare_resource=lambda *_: None,
                start_resource=lambda *_: None,
                reconcile_resource=lambda *_: None,
                read_tool=lambda *_: None,
                prepare_action=lambda *_: None,
                run_action=lambda *_: None,
                reconcile_action=lambda *_: None,
                allowed_hosts=("127.0.0.1",),
            )


if __name__ == "__main__":
    unittest.main()
