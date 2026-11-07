"""Reproduce host-routing regressions. Fake sessions only; the original failures are retained in Git history.
Run using the dedicated mcp==1.30.0 interpreter. This is not a production test gate.
"""
import asyncio
from contextlib import asynccontextmanager
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("routing_basic", ROOT / "validation_basic.py")
fixtures = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixtures)
m = fixtures.module()
from mcp.types import CallToolResult, TextContent
from mcp.server.fastmcp import FastMCP


def result(payload):
    return CallToolResult(content=[TextContent(type="text", text=json.dumps(payload))])


class Catalog:
    tools = [SimpleNamespace(name=name) for name in sorted(m.TOOL_NAMES)]
    def model_dump(self, mode="json"):
        return {"tools": [{"name": tool.name} for tool in self.tools]}


class Backend:
    def __init__(self):
        self.calls, self.fail, self.scope, self.wrong_after = [], None, fixtures.binding(), False
    async def initialize(self):
        if self.fail == "initialize": raise ConnectionError("synthetic")
        return SimpleNamespace(serverInfo=SimpleNamespace(name="mastermind-paper"))
    async def list_tools(self): return Catalog()
    async def call_tool(self, name, arguments):
        self.calls.append(name)
        if name == "paper_inspect":
            return result({"state": "CONNECTED", "execution_binding": self.scope,
                           "document": {"write_binding_ready": True}})
        if name == "paper_edit" and self.fail == "edit": raise TimeoutError("synthetic")
        scope = fixtures.binding(fixtures.LOCAL) if self.wrong_after else self.scope
        return result({"state": "APPLIED_RESPONSE_OBSERVED" if name == "paper_edit" else "OBSERVED",
                       "execution_binding": scope, "operation_id": arguments.get("operation_id"),
                       "retry_allowed": False})


class Cases(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.backend, self.cleanup_error, self.connections, self.local_calls = Backend(), False, 0, []
        @asynccontextmanager
        async def connect(route):
            self.connections += 1
            yield self.backend
            if self.cleanup_error: raise RuntimeError("synthetic cleanup")
        async def local(name, args):
            self.local_calls.append(name)
            return result({"state": "OBSERVED", "execution_binding": fixtures.binding(fixtures.LOCAL)})
        self.policy = fixtures.policy()
        self.policy["routes"][0]["tool_schema_sha256"] = m.schema_digest(Catalog())
        self.router = m.HostRouter(self.policy, fixtures.binding(fixtures.LOCAL), local,
                                  allow_write=True, allow_prepare=True, connect=connect)

    async def call(self, name="paper_edit", host=fixtures.REMOTE):
        args = {"operation_id": "synthetic-once", "tool": "set_text_content", "arguments": {},
                "expected_snapshot": "1" * 64} if name == "paper_edit" else {}
        reply = await self.router.call(name, args, host)
        return json.loads(reply.content[0].text)

    async def test_remote_success(self):
        self.assertEqual((await self.call())["state"], "APPLIED_RESPONSE_OBSERVED")

    async def test_unknown_host_never_connects_or_falls_back(self):
        self.assertEqual((await self.call(host="host-" + "9" * 64))["state"], "HOST_NOT_CONFIGURED")
        self.assertEqual(self.connections, 0)
        self.assertEqual(self.local_calls, [])

    async def test_preconnect_failure_no_effect(self):
        self.backend.fail = "initialize"
        self.assertEqual((await self.call())["effect_state"], "EFFECT_NONE")
        self.assertEqual(self.backend.calls, [])

    async def test_lost_edit_unknown_once(self):
        self.backend.fail = "edit"
        reply = await self.call()
        self.assertEqual(reply["state"], "EFFECT_UNKNOWN")
        self.assertEqual(self.backend.calls.count("paper_edit"), 1)
        self.assertFalse(reply["automatic_failover"])

    async def test_observed_receipt_survives_cleanup(self):
        self.cleanup_error = True
        self.assertEqual((await self.call())["state"], "APPLIED_RESPONSE_OBSERVED")

    async def test_wrong_preflight_host_never_edits(self):
        self.backend.scope = fixtures.binding(fixtures.LOCAL)
        self.assertEqual((await self.call())["effect_state"], "EFFECT_NONE")
        self.assertNotIn("paper_edit", self.backend.calls)

    async def test_wrong_reply_after_dispatch_is_unknown(self):
        self.backend.wrong_after = True
        self.assertEqual((await self.call())["state"], "EFFECT_UNKNOWN")

    async def test_schema_drift_refuses_before_inspect(self):
        self.router.routes[fixtures.REMOTE]["tool_schema_sha256"] = "0" * 64
        self.assertEqual((await self.call())["state"], "BACKEND_SCHEMA_CHANGED")
        self.assertEqual(self.backend.calls, [])

    async def test_local_default_does_not_connect(self):
        self.assertEqual((await self.call(name="paper_inspect", host=None))["state"], "OBSERVED")
        self.assertEqual(self.connections, 0)

    async def test_local_lost_edit_must_not_be_no_effect(self):
        async def lost(name, args): raise TimeoutError("synthetic lost local reply")
        self.router.local_call = lost
        self.assertEqual((await self.call(host=fixtures.LOCAL))["effect_state"], "EFFECT_UNKNOWN")

    async def test_actual_sdk_routed_registration(self):
        server = FastMCP("router-fixture")
        m.register_tools(server, self.router)
        self.assertEqual(len(await server.list_tools()), 6)


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(Cases)
    outcome = unittest.TextTestRunner(verbosity=1).run(suite)
    print(json.dumps({"tests": outcome.testsRun, "failures": len(outcome.failures),
                      "errors": len(outcome.errors), "production_contacted": False}))
    raise SystemExit(0 if outcome.wasSuccessful() else 1)
