"""Explicit qualification against the real, pinned Hermes native owner.

Run through run_native_owner_qualification.py with its marked private native
PM home. The real PluginContext, registry, middleware, AIAgent identity and
SessionDB execute.
Only the remote MCP service response is a fixture; no provider is contacted.
This file is intentionally outside automatic offline test discovery.
"""
from __future__ import annotations

import json
import os
import shutil
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
    RUNTIME_FILES, PLUGIN_SOURCE, package_fingerprint,
)
from integrations.hermes_attended_fabric.native_session import (
    NativeSessionBinding, register,
)


class NativeOwnerQualification(unittest.TestCase):
    def setUp(self):
        owner = os.environ.get("MMX_HERMES_QUALIFICATION_HOME")
        if not owner:
            raise RuntimeError("run through run_native_owner_qualification.py with a prepared fixture home")
        self.temp = tempfile.TemporaryDirectory(prefix="native-worker-", dir=Path(owner) / "profiles")
        self.home = Path(self.temp.name)
        self.token = set_hermes_home_override(str(self.home))
        self._config(True)
        # Fixture installation layout and native record, not an installer claim.
        self.plugin_dir = self.home / "plugins" / "mastermind-fabric-worker"
        self.plugin_dir.mkdir(parents=True)
        for name in RUNTIME_FILES:
            shutil.copy2(Path(__file__).parents[1] / name, self.plugin_dir / name)
        self.release_revision = "f" * 40
        self.expected_package = package_fingerprint(self.plugin_dir)
        (self.plugin_dir.parent / ".install-metadata.json").write_text(json.dumps({
            "mastermind-fabric-worker": {"source": PLUGIN_SOURCE,
                                       "revision": self.release_revision, "pinned": True}}))
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
            path=str(self.plugin_dir))
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
            result.update(root_verified=False, effective_run_id=args["run_id"], status={
                "schema": "mastermind.fabric_task_status.v1", "run_id": args["run_id"],
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

    def test_real_directory_loader_registers_from_installed_subdirectory(self):
        from hermes_cli.plugins_manifest import parse_manifest_file
        manifest = parse_manifest_file(
            self.plugin_dir / "plugin.yaml", self.plugin_dir, "user", "")
        self.assertIsNotNone(manifest)
        self.manager._load_plugin(manifest)
        loaded = self.manager._plugins["mastermind-fabric-worker"]
        self.assertIsNone(loaded.error, loaded.error)
        self.assertIsNotNone(registry.snapshot_registration(TOOL, scope=self.manager.scope_key))
        self.assertEqual(self.mcp_actions, [])

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

    def test_capacity_preview_uses_actual_native_text_envelope(self):
        from mcp.types import CallToolResult, TextContent
        from tools.mcp_tool_handlers import _render_call_tool_result
        cfg = json.loads((self.home / "config.yaml").read_text())
        cfg["plugins"]["entries"]["mastermind-fabric-worker"]["mcp_allowlist"].append(
            "mastermind-fabric-capacity")
        (self.home / "config.yaml").write_text(json.dumps(cfg))
        selected = {"pool": "minimax", "model": "qualified-model",
                    "state": "PREVIEW", "reserved": False,
                    "proof": "PREVIEW_ONLY_NO_RESERVATION_OR_DISPATCH"}
        def capacity(server, action, args, timeout=30):
            self.assertEqual(server, "mastermind-fabric-capacity")
            self.assertEqual(action, "fabric_route_preview")
            result = CallToolResult(content=[TextContent(type="text", text=json.dumps(selected))])
            return PluginContext._mcp_envelope(_render_call_tool_result(result, server))
        self.ctx.call_mcp = capacity
        args = {k: v for k, v in self.args("route-preview").items() if k != "work_packet"}
        args["action"] = "preview"
        self.persist("preview-1", args)
        result = self.invoke(self.mount(), "preview-1", args)
        self.assertEqual(result["state"], "PREVIEW_ONLY", result)
        self.assertFalse(result["worker_started"])
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
                                  "source": str(Path(run_agent.__file__).parent),
                                  "revision": getattr(self, "wire_revision", self.release_revision),
                                  "packageSha256": self.expected_package}}
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
        # Execute the installed MCP renderer and PluginContext envelope too.
        # Hermes removes duplicate structured JSON and returns its text form.
        from mcp.types import CallToolResult
        from tools.mcp_tool_handlers import _render_call_tool_result
        model = CallToolResult.model_validate(captured["reply"])
        return PluginContext._mcp_envelope(_render_call_tool_result(model, server))

    def _assert_unmeasured_code_never_runs(self, marker):
        self.assertEqual(package_fingerprint(self.plugin_dir), self.expected_package)
        self.ctx.call_mcp = self.mcp_wire
        args = self.args()
        self.persist("isolated-wire-submit", args)
        submitted = self.invoke(self.mount(), "isolated-wire-submit", args)
        self.assertFalse(marker.exists(), "unmeasured installed code executed")
        self.assertEqual(submitted["state"], "CONTROLLER_CREATED", submitted)
        self.assertEqual(len(self.requests), 1)

    def test_checker_ignores_unmeasured_standard_library_sibling(self):
        marker = self.home / "unmeasured-standard-import"
        sibling = self.plugin_dir / "json"
        sibling.mkdir()
        (sibling / "__init__.py").write_text(
            f"from pathlib import Path\nPath({str(marker)!r}).write_text('executed')\n")
        self._assert_unmeasured_code_never_runs(marker)

    def test_checker_uses_exact_private_source_before_sibling_package(self):
        marker = self.home / "unmeasured-private-import"
        sibling = self.plugin_dir / "native_evidence"
        sibling.mkdir()
        (sibling / "__init__.py").write_text(
            f"from pathlib import Path\nPath({str(marker)!r}).write_text('executed')\n")
        self._assert_unmeasured_code_never_runs(marker)

    def test_checker_does_not_execute_unmeasured_cached_bytecode(self):
        import importlib.util
        import marshal
        import struct
        marker = self.home / "unmeasured-cached-import"
        source = self.plugin_dir / "native_evidence.py"
        cache = Path(importlib.util.cache_from_source(str(source)))
        cache.parent.mkdir(exist_ok=True)
        code = compile(
            f"from pathlib import Path\nPath({str(marker)!r}).write_text('executed')\n",
            str(source), "exec")
        stat = source.stat()
        # A valid timestamp/size cache header leaves all sealed source bytes
        # unchanged; the checker must execute those source bytes, not this code.
        cache.write_bytes(importlib.util.MAGIC_NUMBER
            + struct.pack("<III", 0, int(stat.st_mtime), stat.st_size)
            + marshal.dumps(code))
        self._assert_unmeasured_code_never_runs(marker)

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

    def test_installed_pin_and_byte_drift_refuse_before_request_engine(self):
        self.ctx.call_mcp = self.mcp_wire
        args = self.args()
        self.persist("wire-submit", args)
        self.assertEqual(self.invoke(self.mount(), "wire-submit", args)["state"],
                         "CONTROLLER_CREATED")
        request = self.requests[0]
        self.wire_revision = "e" * 40
        self.assertFalse(self.mcp_wire("mastermind-fabric-exec", "fabric_request", request)["ok"])
        self.assertEqual(self.wire_last["calls"], [])
        self.wire_revision = self.release_revision
        target = self.plugin_dir / "native.py"
        target.write_bytes(target.read_bytes() + b"\n# changed installed source\n")
        self.assertFalse(self.mcp_wire("mastermind-fabric-exec", "fabric_request", request)["ok"])
        self.assertEqual(self.wire_last["calls"], [])

    def test_native_plugin_slot_link_cannot_redirect_qualifier(self):
        moved = self.home / "different-plugin-slot"
        self.plugin_dir.rename(moved)
        self.plugin_dir.symlink_to(moved, target_is_directory=True)
        with self.assertRaisesRegex(FabricNativeRefusal, "NOT_ENROLLED"):
            register(self.ctx)
        self.assertEqual(self.requests, [])

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
