"""Real Hermes PluginContext MCP call-shape regression (no live backend)."""
from __future__ import annotations

import unittest
import json

from integrations.hermes_attended_fabric.hermes_mcp_client import (
    bind_native_mcp_client, EXECUTION_SERVER,
)


class OwnerContext:
    plugin_id = "mmx-native-fabric"
    def __init__(self, allowed=True):
        self.allowed = allowed
        self.calls = []
        self.reply = {
            "ok": True,
            "structuredContent": {
                "schema": "mastermind.fabric_mcp.v1",
                "action": "fabric_status",
                "run_id": "hermes-native-1",
                "status": {"schema": "mastermind.fabric_task_status.v1", "state": "NOT_FOUND",
                           "result_available": False},
                "root_verified": False,
            },
        }

    def _mcp_allowlist(self, plugin_id):
        assert plugin_id == self.plugin_id
        return [EXECUTION_SERVER] if self.allowed else ["mastermind-fabric-capacity"]

    def call_mcp(self, server, tool, arguments=None, timeout=30):
        self.calls.append((server, tool, arguments, timeout))
        return self.reply


class TestNativeHermesMcpClient(unittest.TestCase):
    def test_bound_uses_existing_hermes_client_and_exact_server(self):
        ctx = OwnerContext()
        port = bind_native_mcp_client(ctx)
        raw = port("fabric_status", {"run_id": "hermes-native-1", "root_id": "root-1"})
        self.assertEqual(raw["run_id"], "hermes-native-1")
        self.assertEqual(ctx.calls, [
            (EXECUTION_SERVER, "fabric_status",
             {"run_id": "hermes-native-1", "root_id": "root-1"}, 30),
        ])

    def test_native_dual_emit_normalization_keeps_canonical_json_text(self):
        ctx = OwnerContext()
        original = ctx.reply["structuredContent"]
        ctx.reply = {"ok": True, "result": json.dumps(original)}
        self.assertEqual(bind_native_mcp_client(ctx)("fabric_status", {}), original)
        for text in (json.dumps(json.dumps(original)), json.dumps({"schema": "other"}),
                     "log prefix " + json.dumps(original)):
            ctx.reply = {"ok": True, "result": text}
            with self.assertRaisesRegex(Exception, "SCHEMA_INVALID"):
                bind_native_mcp_client(ctx)("fabric_status", {})

    def test_read_only_capacity_enrollment_never_escalates_to_execution(self):
        ctx = OwnerContext(allowed=False)
        with self.assertRaisesRegex(Exception, "HERMES_FABRIC_EXECUTION_NOT_ENROLLED"):
            bind_native_mcp_client(ctx)
        self.assertEqual(ctx.calls, [])

    def test_allowlist_revocation_after_binding_fails_before_any_call(self):
        ctx = OwnerContext()
        port = bind_native_mcp_client(ctx)
        ctx.allowed = False
        with self.assertRaisesRegex(Exception, "HERMES_FABRIC_EXECUTION_NOT_ENROLLED"):
            port("fabric_status", {"run_id": "hermes-native-1"})
        self.assertEqual(ctx.calls, [])

    def test_non_fabric_action_never_calls_native_mcp(self):
        ctx = OwnerContext()
        port = bind_native_mcp_client(ctx)
        for name in ("fabric_accept", "fabric_cancel", "fabric_controller_output",
                     "fabric_wait", "fabric_result_page", "write_file", "run_shell"):
            with self.subTest(name=name):
                with self.assertRaisesRegex(Exception, "HERMES_FABRIC_ACTION_NOT_ALLOWED"):
                    port(name, {})
        self.assertEqual(ctx.calls, [])

    def test_wrong_server_schema_and_action_fail_closed(self):
        ctx = OwnerContext()
        port = bind_native_mcp_client(ctx)
        for change in (
            {"schema": "other"},
            {"action": "fabric_request"},
            {"run_id": "hermes-native-1", "schema": None},
        ):
            with self.subTest(change=change):
                ctx.reply = {"ok": True, "structuredContent": {
                    **ctx.reply.get("structuredContent", {}),
                    **change,
                }}
                with self.assertRaisesRegex(Exception, "HERMES_FABRIC_MCP_SCHEMA_INVALID"):
                    port("fabric_status", {})

    def test_incomplete_or_error_is_not_success(self):
        ctx = OwnerContext()
        port = bind_native_mcp_client(ctx)
        for raw in (
            {"ok": False, "error": "unknown"},
            {"ok": True, "result": "controller output"},
            {"ok": True, "structuredContent": "not-json"},
            {"ok": True, "truncated": True, "result": {"schema": "mastermind.fabric_mcp.v1",
                                                      "action": "fabric_status"}},
            None,
        ):
            ctx.reply = raw
            with self.subTest(raw=raw):
                with self.assertRaises(Exception):
                    port("fabric_status", {})

    def test_native_client_exception_never_replayed(self):
        ctx = OwnerContext()
        def break_client(server, action, arguments=None, timeout=30):
            ctx.calls.append((server, action, arguments, timeout))
            raise TimeoutError("unknown post-send effect")
        ctx.call_mcp = break_client
        port = bind_native_mcp_client(ctx)
        with self.assertRaisesRegex(Exception, "HERMES_FABRIC_MCP_UNAVAILABLE"):
            port("fabric_request", {"run_id": "hermes-native-1"})
        self.assertEqual(len(ctx.calls), 1)

    def test_no_retroactive_promotion_from_readonly_server(self):
        ctx = OwnerContext()
        bind_native_mcp_client(ctx)
        self.assertNotEqual(EXECUTION_SERVER, "mastermind-fabric-capacity")


if __name__ == "__main__":
    unittest.main()
