"""Explicit qualification against the real, pinned Hermes native owner.

Run with the existing Hermes Python and its source on sys.path. The real
PluginContext, registry, middleware, AIAgent identity and SessionDB execute.
Only the remote MCP service response is a fixture; no provider is contacted.
This file is intentionally outside automatic offline test discovery.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from agent.subagent_lifecycle import bind_subagent_parent
from hermes_cli.middleware import run_tool_execution_middleware
from hermes_cli.plugins import (
    LoadedPlugin, PluginContext, PluginManifest, get_plugin_manager,
)
from hermes_constants import set_hermes_home_override, reset_hermes_home_override
from hermes_state import SessionDB
from run_agent import AIAgent
from tools.registry import registry

from integrations.hermes_attended_fabric.native import (
    FabricNativeRefusal, TOOL, run_id_for,
)
from integrations.hermes_attended_fabric.native_evidence import (
    read_enrollment, verify_origin, native_root, ENROLLMENT_SCHEMA,
)
from integrations.hermes_attended_fabric.native_session import (
    NativeSessionBinding, register,
)


class NativeOwnerQualification(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name)
        self.token = set_hermes_home_override(str(self.home))
        self._config(True)
        self.db = SessionDB(self.home / "state.db")
        self.sid = "native-attended-parent"
        self.db.create_session(self.sid, source="cli")
        self.holder = "qualification-turn"
        self.assertTrue(self.db.try_acquire_session_turn_lease(
            self.sid, self.holder, ttl_seconds=120))
        self.agent = AIAgent.__new__(AIAgent)
        self.agent.session_id = self.sid
        self.agent._session_db = self.db
        self.agent._current_turn_id = "native-turn-1"
        self.agent._active_session_turn_lease_holder = self.holder
        self.agent._delegate_depth = 0
        self.agent._turn_origin = None
        self.agent._persist_disabled = False
        self.agent._interrupt_requested = False
        self.manager = get_plugin_manager()
        self.manager._discovered = True
        self.manager._cli_ref = object()
        self.manifest = PluginManifest(
            name="mastermind-fabric-worker", version="1.0.0", source="user",
            path=str(Path(__file__).parents[1]))
        self.manager._plugins[self.manifest.name] = LoadedPlugin(
            self.manifest, enabled=True)
        self.ctx = PluginContext(self.manifest, self.manager)
        self.ctx.call_mcp = self.mcp
        self.requests = []
        self.mcp_actions = []
        self.on_status = None
        self.on_request = None
        self.response_loss = False

    def tearDown(self):
        for handle in list(getattr(self.manager, "_registration_handles", {}).values()):
            if hasattr(handle, "dispose"):
                handle.dispose()
        self.db.close()
        reset_hermes_home_override(self.token)
        self.temp.cleanup()

    def _config(self, enrolled):
        (self.home / "config.yaml").write_text(json.dumps({
            "plugins": {"enabled": ["mastermind-fabric-worker"],
                        "entries": {"mastermind-fabric-worker": {
                "mcp_allowlist": ["mastermind-fabric-exec"] if enrolled else [],
                "native_origin": {"schema": ENROLLMENT_SCHEMA, "enabled": True,
                                  "namespace": "native-owner-qualification"},
            }}}
        }))

    def args(self, key="read-source"):
        return {"action": "submit", "task_key": key, "task_class": "census",
                "task_complexity": "C1_ROUTINE_BOUNDED",
                "work_packet": "Read the assigned source and return a bounded finding."}

    def persist(self, call_id, args):
        return self.db.append_message(self.agent.session_id, "assistant", content="",
            tool_calls=[{"id": call_id, "type": "function",
                         "function": {"name": TOOL, "arguments": json.dumps(args)}}])

    def mcp(self, server, action, args, timeout=30):
        self.assertEqual(server, "mastermind-fabric-exec")
        self.mcp_actions.append(action)
        contract = read_enrollment(self.home)
        if action == "fabric_capabilities":
            return {"ok": True, "structuredContent": {
                "schema": "mastermind.fabric_mcp.v1", "action": "capabilities",
                "hermes_native_origin": contract}}
        verify_origin(self.home, action, args, contract)
        result = {"schema": "mastermind.fabric_mcp.v1", "action": action,
                  "run_id": args["run_id"]}
        if action == "fabric_status":
            if self.on_status:
                self.on_status()
            result.update(root_verified=False, status={
                "schema": "mastermind.fabric_task_status.v1",
                "state": "NOT_FOUND", "result_available": False,
            })
        elif action == "fabric_request":
            self.requests.append(dict(args))
            if self.on_request:
                self.on_request()
            if self.response_loss:
                raise TimeoutError("fixture response loss after submission")
            result.update(root_id=args["root_id"], parent_id=args["parent_id"],
                          delivery="CONTROLLER_CREATED", controller_pid=123,
                          worker_start_proven=False)
        else:
            self.fail("unexpected remote action")
        return {"ok": True, "structuredContent": result}

    def mount(self):
        register(self.ctx)
        entry = registry.snapshot_registration(TOOL, scope=self.manager.scope_key)
        self.assertIsNotNone(entry)
        return entry.handler

    def invoke(self, handler, call_id, args):
        with bind_subagent_parent(self.agent):
            result = run_tool_execution_middleware(
                TOOL, args, lambda value: handler(value, session_id=self.agent.session_id),
                session_id=self.agent.session_id, turn_id=self.agent._current_turn_id,
                tool_call_id=call_id)
        return json.loads(result)

    def test_real_native_mount_submits_with_host_produced_identity(self):
        args = self.args()
        self.persist("call-1", args)
        result = self.invoke(self.mount(), "call-1", args)
        self.assertEqual(result["state"], "CONTROLLER_CREATED", result)
        self.assertFalse(result["worker_started"])
        self.assertEqual(len(self.requests), 1)
        root = native_root(read_enrollment(self.home), self.sid)
        self.assertEqual(self.requests[0]["root_id"], root)
        self.assertEqual(self.requests[0]["parent_id"], root)
        self.assertTrue(self.requests[0]["run_id"].startswith("hermes-native-"))

    def test_plugin_discovery_precedes_mcp_startup_without_losing_registration(self):
        original = self.ctx.call_mcp
        ready = False
        def existing_client(*args, **kwargs):
            if not ready:
                raise AssertionError("MCP is not initialized during native discovery")
            return original(*args, **kwargs)
        self.ctx.call_mcp = existing_client
        handler = self.mount()
        self.assertEqual(self.mcp_actions, [])
        ready = True
        args = self.args()
        self.persist("call-1", args)
        result = self.invoke(handler, "call-1", args)
        self.assertEqual(result["state"], "CONTROLLER_CREATED", result)

    def test_first_current_invocation_attests_before_request(self):
        args = self.args()
        self.persist("call-1", args)
        handler = self.mount()
        self.assertEqual(self.mcp_actions, [])
        result = self.invoke(handler, "call-1", args)
        self.assertEqual(result["state"], "CONTROLLER_CREATED", result)
        self.assertEqual(self.mcp_actions,
                         ["fabric_capabilities", "fabric_status", "fabric_request"])

    def test_unenrolled_profile_does_not_publish_worker_tool(self):
        self._config(False)
        with self.assertRaisesRegex(FabricNativeRefusal, "NOT_ENROLLED"):
            register(self.ctx)
        self.assertIsNone(registry.snapshot_registration(TOOL, scope=self.manager.scope_key))
        self.assertEqual(self.requests, [])

    def test_direct_handler_without_native_execution_context_refuses(self):
        result = json.loads(self.mount()(self.args(), session_id=self.sid))
        self.assertEqual(result["state"], "REFUSED", result)
        self.assertEqual(self.requests, [])

    def test_unpersisted_tool_call_cannot_submit(self):
        result = self.invoke(self.mount(), "call-1", self.args())
        self.assertEqual(result["state"], "REFUSED", result)
        self.assertEqual(self.requests, [])

    def test_same_task_key_in_concurrent_native_batch_cannot_double_submit(self):
        args = self.args()
        self.persist("call-1", args)
        self.persist("call-2", args)
        handler = self.mount()
        for call in ("call-1", "call-2"):
            self.assertEqual(self.invoke(handler, call, args)["state"], "REFUSED")
        self.assertEqual(self.requests, [])

    def test_lost_response_and_new_turn_cannot_replay_missing_remote_status(self):
        args = self.args()
        self.persist("call-1", args)
        handler = self.mount()
        self.response_loss = True
        first = self.invoke(handler, "call-1", args)
        self.assertEqual(first["state"], "EFFECT_UNKNOWN", first)
        self.agent._current_turn_id = "native-turn-2"
        self.persist("call-2", args)
        second = self.invoke(handler, "call-2", args)
        self.assertEqual(second["state"], "REFUSED", second)
        self.assertEqual(first["run_id"], second["run_id"])
        self.assertEqual(len(self.requests), 1)

    def test_revocation_during_observation_prevents_submission(self):
        args = self.args()
        self.persist("call-1", args)
        self.on_status = lambda: setattr(self.agent, "_interrupt_requested", True)
        result = self.invoke(self.mount(), "call-1", args)
        self.assertEqual(result["state"], "REFUSED", result)
        self.assertEqual(self.requests, [])

    def test_revocation_after_submission_retains_only_control_receipt(self):
        args = self.args()
        self.persist("call-1", args)
        self.on_request = lambda: setattr(self.agent, "_interrupt_requested", True)
        result = self.invoke(self.mount(), "call-1", args)
        self.assertEqual(result["state"], "CONTROLLER_CREATED", result)
        self.assertTrue(result["response_withheld"])
        self.assertFalse(result["retry_authorized"])
        self.assertNotIn("result_text", result)
        self.assertEqual(len(self.requests), 1)

    def test_rewritten_packet_must_match_original_native_intent(self):
        args = self.args()
        self.persist("call-1", args)
        changed = {**args, "work_packet": "A different request."}
        result = self.invoke(self.mount(), "call-1", changed)
        self.assertEqual(result["state"], "REFUSED", result)
        self.assertEqual(self.requests, [])

    def test_delegated_parent_is_not_promoted_to_attended_root(self):
        args = self.args()
        self.persist("call-1", args)
        self.agent._delegate_depth = 1
        result = self.invoke(self.mount(), "call-1", args)
        self.assertEqual(result["state"], "REFUSED", result)
        self.assertEqual(self.requests, [])

    def test_native_lease_loss_refuses_before_mcp(self):
        args = self.args()
        self.persist("call-1", args)
        self.db.release_session_turn_lease(self.sid, self.holder)
        result = self.invoke(self.mount(), "call-1", args)
        self.assertEqual(result["state"], "REFUSED", result)
        self.assertEqual(self.requests, [])

    def test_compression_preserves_original_run_and_prior_attempt(self):
        args = self.args()
        self.persist("call-1", args)
        handler = self.mount()
        first = self.invoke(handler, "call-1", args)
        self.assertEqual(first["state"], "CONTROLLER_CREATED", first)
        self.db.end_session(self.sid, "compression")
        self.db.create_session("native-compression-segment", source="cli",
                               parent_session_id=self.sid)
        self.agent.session_id = "native-compression-segment"
        self.agent._current_turn_id = "native-turn-2"
        self.persist("call-2", args)
        second = self.invoke(handler, "call-2", args)
        self.assertEqual(second["state"], "REFUSED", second)
        self.assertEqual(first["run_id"], second["run_id"])
        self.assertEqual(second["root_id"], native_root(read_enrollment(self.home), self.sid))
        self.assertEqual(len(self.requests), 1)

    def test_fabric_grant_is_not_model_or_fake_native_context(self):
        with self.assertRaisesRegex(FabricNativeRefusal, "CONTEXT_UNAVAILABLE"):
            NativeSessionBinding(object())

    def mcp_wire(self, server, action, args, timeout=30):
        """Real facade + its real read-only native verifier; final engine is a fixture."""
        import subprocess
        import sys
        import run_agent
        self.assertEqual(server, "mastermind-fabric-exec")
        text = "fixture retained result through both installed owner APIs"
        state = getattr(self, "wire_state", "NOT_FOUND")
        if action == "fabric_capabilities":
            outputs = [{"kind": "text", "value":
                "request status result accept preview --strict-manual-pin --quota-fallback --follow"}
                       for _ in range(8)]
        else:
            status = {"schema": "mastermind.fabric_task_status.v1",
                "run_id": args["run_id"], "state": state,
                "root_id": args["root_id"] if state == "TERMINAL" else None,
                "parent_run_id": args["root_id"] if state == "TERMINAL" else None,
                "result_available": state == "TERMINAL", "accepted": None,
                "result_bytes": len(text.encode()) if state == "TERMINAL" else None,
                "rc": 0 if state == "TERMINAL" else None,
                "signal": "ok" if state == "TERMINAL" else None}
            outputs = [{"kind": "json", "value": status}]
            if action == "fabric_request":
                self.requests.append(dict(args))
                outputs.append({"kind": "pending"})
            elif action == "fabric_result":
                outputs.append({"kind": "text", "value": text})
        spec = {"action": action, "arguments": args, "adapter_outputs": outputs,
                "hermes_native": {"home": str(self.home), "python": sys.executable,
                                  "source": str(Path(run_agent.__file__).parent)}}
        if action == "fabric_request" and getattr(self, "revoke_in_preflight", False):
            spec["revoke_native_after_call"] = 1
        completed = subprocess.run(
            ["node", str(Path(__file__).with_name("facade_wire_fixture.mjs"))],
            input=json.dumps(spec), text=True, capture_output=True, timeout=35, check=True)
        captured = json.loads(completed.stdout)
        self.wire_last = captured
        if not hasattr(self, "wire_calls"):
            self.wire_calls = []
        self.wire_calls.append((action, captured))
        return {"ok": not captured["reply"].get("isError", False),
                "structuredContent": captured["reply"]["structuredContent"]}

    def test_real_facade_native_verifier_request_and_result_path(self):
        self.ctx.call_mcp = self.mcp_wire
        args = self.args()
        self.persist("wire-submit", args)
        handler = self.mount()
        submitted = self.invoke(handler, "wire-submit", args)
        self.assertEqual(submitted["state"], "CONTROLLER_CREATED", submitted)
        original = self.requests[0]
        self.assertEqual(original["native_origin"]["kind"], "hermes_attended_session")
        self.assertEqual(len(self.wire_last["calls"]), 2)
        self.assertNotIn("native_origin", self.wire_last["calls"][-1]["arguments"]["command"])
        self.wire_state = "TERMINAL"
        read = {"action": "result", "task_key": args["task_key"]}
        self.persist("wire-result", read)
        returned = self.invoke(handler, "wire-result", read)
        self.assertEqual(returned["state"], "TERMINAL", returned)
        self.assertEqual(returned["run_id"], submitted["run_id"])
        self.assertEqual(returned["result_text"],
                         "fixture retained result through both installed owner APIs")
        self.assertEqual(len(self.requests), 1)

    def test_native_channel_cannot_omit_origin_or_claim_another_profile(self):
        self.ctx.call_mcp = self.mcp_wire
        args = self.args()
        self.persist("wire-submit", args)
        self.assertEqual(self.invoke(self.mount(), "wire-submit", args)["state"],
                         "CONTROLLER_CREATED")
        request = self.requests[0]
        missing = {k: v for k, v in request.items() if k != "native_origin"}
        self.assertFalse(self.mcp_wire("mastermind-fabric-exec", "fabric_request", missing)["ok"])
        self.assertEqual(self.wire_last["calls"], [])
        foreign = {**request, "native_origin": {
            **request["native_origin"], "profile_id": "foreign-profile"}}
        self.assertFalse(self.mcp_wire("mastermind-fabric-exec", "fabric_request", foreign)["ok"])
        self.assertEqual(self.wire_last["calls"], [])

    def test_server_rechecks_enrollment_after_async_preflight(self):
        self.ctx.call_mcp = self.mcp_wire
        args = self.args()
        self.persist("wire-submit", args)
        handler = self.mount()
        self.revoke_in_preflight = True
        result = self.invoke(handler, "wire-submit", args)
        self.assertNotEqual(result["state"], "CONTROLLER_CREATED")
        request = [captured for action, captured in self.wire_calls
                   if action == "fabric_request"][-1]
        self.assertEqual(len(request["calls"]), 1)  # status only, no request launch
        self.assertEqual(request["reply"]["structuredContent"]["error"],
                         "HERMES_NATIVE_ORIGIN_REFUSED")


if __name__ == "__main__":
    unittest.main(verbosity=2)
