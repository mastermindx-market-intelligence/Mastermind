"""Fail-closed, deterministic tests for the native Hermes→Fabric ingress.

No paid worker or machine service is accessed by these tests.
"""
from __future__ import annotations

import json
import unittest
import sys
import types
from contextlib import nullcontext
from unittest.mock import patch

from integrations.hermes_attended_fabric.native import (
    SCHEMA, TOOL, TOOLSET, SessionGrant, native_handler,
    register_native_tool, run_id_for,
)


class FakeOwner:
    def __init__(self):
        self.calls = []
        self.state = "NOT_FOUND"
        self.fail = ""
        self.override_parent = None
        self.override_root = None

    def _return(self, grant, run_id, state):
        return {
            "run_id": run_id,
            "root_id": self.override_root or grant.root_id,
            "parent_id": self.override_parent or grant.parent_id,
            "state": state,
            "worker_started": state == "RUNNING",
            "result_digest": "a" * 64 if state == "TERMINAL" else None,
        }

    def preview(self, grant, run_id, task_class, complexity, reason):
        self.calls.append(("preview", run_id, task_class, complexity, reason))
        if self.fail == "preview":
            raise TimeoutError()
        return self._return(grant, run_id, "PREVIEW_ONLY")

    def status(self, grant, run_id):
        self.calls.append(("status", run_id))
        if self.fail == "status":
            raise TimeoutError()
        return self._return(grant, run_id, self.state)

    def submit(self, grant, run_id, task_class, complexity, packet, reason, *,
               pool=None, model=None):
        self.calls.append(("submit", run_id, task_class, complexity, packet, reason, pool, model))
        if self.fail == "submit":
            raise TimeoutError()
        if self.fail == "bad_submit":
            return {"state": "CONTROLLER_CREATED", "run_id": "other"}
        self.state = "ACTIVE_OR_WAITING"
        return self._return(grant, run_id, "CONTROLLER_CREATED")

    def result(self, grant, run_id):
        self.calls.append(("result", run_id))
        if self.fail == "result":
            raise TimeoutError()
        return self._return(grant, run_id, "TERMINAL")


class TestNativeFabric(unittest.TestCase):
    def setUp(self):
        self.port = FakeOwner()
        self.grant = SessionGrant(
            profile_id="main", session_id="native-session-A",
            root_id="hermes-owned-root-A", parent_id="hermes-owned-root-A",
            generation="generation-A")
        self.guards = [True]
        self.handle = native_handler(
            profile_id="main",
            authorize_session=lambda session: self.grant,
            port=self.port,
            currentness_guard=lambda grant: self.guards.pop(0) if len(self.guards) > 1 else self.guards[0])

    def call(self, action, session="native-session-A", **kw):
        args = {"action": action, "task_key": "one-thing", **kw}
        return json.loads(self.handle(args, session_id=session))

    def fields(self):
        return {"task_class": "fix_build", "task_complexity": "C1_ROUTINE_BOUNDED",
                "work_packet": "Make one verified change and report evidence."}

    def test_stable_native_origin_and_generation(self):
        same = run_id_for(self.grant, "one-thing")
        self.assertEqual(same, run_id_for(self.grant, "one-thing"))
        other = SessionGrant(self.grant.profile_id, self.grant.session_id,
                             self.grant.root_id, self.grant.parent_id, "generation-B")
        self.assertEqual(same, run_id_for(other, "one-thing"))
        self.assertTrue(same.startswith("hermes-native-"))

    def test_reconnect_does_not_create_new_original_run(self):
        changed = SessionGrant("main", "native-session-A", "hermes-owned-root-A",
                               "hermes-owned-root-A", "generation-after-restart")
        self.assertEqual(run_id_for(self.grant, "one-thing"),
                         run_id_for(changed, "one-thing"))

    def test_preview_cannot_dispatch(self):
        result = self.call("preview", **{k: v for k, v in self.fields().items()
                                         if k != "work_packet"})
        self.assertEqual(result["state"], "PREVIEW_ONLY")
        self.assertEqual([c[0] for c in self.port.calls], ["preview"])

    def test_submit_once_with_authoritative_absence(self):
        result = self.call("submit", **self.fields())
        self.assertEqual(result["schema"], SCHEMA)
        self.assertEqual(result["state"], "CONTROLLER_CREATED")
        self.assertFalse(result["worker_started"])
        self.assertEqual([c[0] for c in self.port.calls], ["status", "submit"])
        again = self.call("submit", **self.fields())
        self.assertEqual(again["state"], "ACTIVE_OR_WAITING")
        self.assertEqual([c[0] for c in self.port.calls],
                         ["status", "submit", "status"])

    def test_model_cannot_forge_identity(self):
        result = self.call("submit", root_id="JOB-99", **self.fields())
        self.assertEqual(result["reason"], "UNKNOWN_FIELD")
        self.assertEqual(self.port.calls, [])

    def test_model_cannot_change_account_or_host(self):
        for field in ("account", "host", "session_id",
                      "parent_id", "run_id", "idempotency_key", "accepted_by"):
            with self.subTest(field=field):
                result = self.call("submit", **self.fields(), **{field: "other"})
                self.assertEqual(result["reason"], "UNKNOWN_FIELD")
        self.assertEqual(self.port.calls, [])

    def test_model_without_manual_grant_cannot_pin_pool_or_model(self):
        for selection in ({"pool": "minimax"}, {"pool": "minimax", "model": "MiniMax-M3"},
                          {"model": "MiniMax-M3"}):
            with self.subTest(selection=selection):
                got = self.call("submit", **self.fields(), **selection)
                self.assertEqual(got["reason"], "MANUAL_ROUTE_NOT_AUTHORIZED")
        self.assertEqual(self.port.calls, [])

    def test_exact_manual_grant_reuses_native_strict_pin_owner(self):
        grant = SessionGrant(
            "main", "native-session-A", self.grant.root_id, self.grant.parent_id,
            "generation-A", manual_pools=("minimax",),
            manual_models=(("minimax", "MiniMax-M3"),))
        handle = native_handler(
            profile_id="main", authorize_session=lambda session: grant,
            port=self.port, currentness_guard=lambda grant: True)
        def call(**selection):
            return json.loads(handle(
                {"action": "submit", "task_key": "one-thing",
                 **self.fields(), **selection}, session_id=grant.session_id))
        got = call(pool="minimax", model="MiniMax-M3")
        self.assertEqual(got["state"], "CONTROLLER_CREATED")
        self.assertEqual(self.port.calls[-1][-2:], ("minimax", "MiniMax-M3"))

    def test_unauthorized_manual_model_or_pool_refuses_before_owner(self):
        grant = SessionGrant(
            "main", "native-session-A", self.grant.root_id, self.grant.parent_id,
            "generation-A", manual_pools=("minimax",),
            manual_models=(("minimax", "MiniMax-M3"),))
        handle = native_handler(
            profile_id="main", authorize_session=lambda session: grant,
            port=self.port, currentness_guard=lambda grant: True)
        for selection in ({"pool": "minimax", "model": "Other-M3"},
                          {"pool": "glm", "model": "auto"},
                          {"model": "MiniMax-M3"}):
            got = json.loads(handle(
                {"action": "submit", "task_key": "one-thing",
                 **self.fields(), **selection}, session_id=grant.session_id))
            self.assertEqual(got["reason"], "MANUAL_ROUTE_NOT_AUTHORIZED")
        self.assertEqual(self.port.calls, [])

    def test_wrong_actual_native_caller_fails(self):
        result = self.call("submit", session="foreign-session", **self.fields())
        self.assertEqual(result["reason"], "NATIVE_SESSION_NOT_AUTHORIZED")
        self.assertEqual(self.port.calls, [])

    def test_missing_native_identity_fails(self):
        result = json.loads(self.handle({"action": "status", "task_key": "a"}))
        self.assertEqual(result["reason"], "NATIVE_SESSION_MISSING")

    def test_unavailable_preflight_fails_closed(self):
        self.port.fail = "status"
        result = self.call("submit", **self.fields())
        self.assertEqual(result["state"], "UNAVAILABLE")
        self.assertEqual([c[0] for c in self.port.calls], ["status"])

    def test_post_send_exception_is_unknown_not_refused(self):
        self.port.fail = "submit"
        result = self.call("submit", **self.fields())
        self.assertEqual(result["state"], "EFFECT_UNKNOWN")
        self.assertEqual([c[0] for c in self.port.calls], ["status", "submit"])

    def test_post_send_wrong_identity_is_unknown(self):
        self.port.fail = "bad_submit"
        result = self.call("submit", **self.fields())
        self.assertEqual(result["state"], "EFFECT_UNKNOWN")

    def test_revoked_just_before_send_refuses(self):
        self.guards = [True, False]
        result = self.call("submit", **self.fields())
        self.assertEqual(result["state"], "REFUSED")
        self.assertEqual(result["reason"], "NATIVE_SESSION_REVOKED")
        self.assertEqual([c[0] for c in self.port.calls], ["status"])

    def test_preflight_live_stays_on_original_carrier(self):
        self.port.state = "EFFECT_UNKNOWN"
        result = self.call("submit", **self.fields())
        self.assertEqual(result["state"], "EFFECT_UNKNOWN")
        self.assertEqual([c[0] for c in self.port.calls], ["status"])

    def test_observation_parent_mismatch_is_unavailable(self):
        self.port.override_parent = "someone-elses-parent"
        result = self.call("status")
        self.assertEqual(result["state"], "UNAVAILABLE")
        self.assertEqual(len(self.port.calls), 1)

    def test_result_is_scoped_to_same_session(self):
        result = self.call("result")
        self.assertEqual(result["state"], "TERMINAL")
        self.assertEqual(result["result_digest"], "a" * 64)
        self.assertNotIn("result_text", result)
        self.assertEqual(self.call("result", session="another")["state"], "REFUSED")
        self.assertEqual([c[0] for c in self.port.calls], ["result"])

    def test_required_escalation_for_c3(self):
        fields = self.fields()
        fields["task_complexity"] = "C3_FRONTIER_JUDGMENT"
        self.assertEqual(self.call("submit", **fields)["reason"],
                         "ESCALATION_REASON_REQUIRED")
        self.assertEqual(self.port.calls, [])

    def test_packet_limits_and_null(self):
        for packet in ("", "abc\x00def", "🙂" * 9000):
            with self.subTest(len=len(packet)):
                fields = self.fields()
                fields["work_packet"] = packet
                self.assertEqual(self.call("submit", **fields)["reason"], "PACKET_INVALID")
        self.assertEqual(self.port.calls, [])

    def test_invalid_unhashable_action(self):
        result = json.loads(self.handle({"action": [], "task_key": "abc"},
                                        session_id=self.grant.session_id))
        self.assertEqual(result["reason"], "ACTION_INVALID")

    def test_default_unbound_port_refuses(self):
        with self.assertRaises(Exception):
            native_handler(profile_id="main",
                           authorize_session=lambda s: self.grant,
                           port=None, currentness_guard=lambda g: True)

    @staticmethod
    def make_native_owner():
        """Stub only Hermes' incumbent registry and replacement coordinator."""
        import types

        registry = types.SimpleNamespace(installed=None)
        registry.snapshot_registration = lambda name, scope: registry.installed
        registry.get_entry = lambda name, scope: registry.installed
        plugin = types.ModuleType("hermes_cli.plugin_isolation")
        plugin.HOST_PROCESS_ENV = "_MMX_HERMES_PLUGIN_HOST_TEST_ONLY"
        plugin.ISOLATION_HOST = "host"
        plugin.isolation_mode = lambda: "in_process"
        coordinator = types.ModuleType("registration_lifecycle")
        coordinator.replacement_coordinator = types.SimpleNamespace(transaction=nullcontext)
        reg = types.ModuleType("tools.registry")
        reg.registry = registry
        tools = types.ModuleType("tools")
        tools.__path__ = []
        hermes_cli = types.ModuleType("hermes_cli")
        hermes_cli.__path__ = []
        modules = {
            "tools": tools,
            "tools.registry": reg,
            "registration_lifecycle": coordinator,
            "hermes_cli": hermes_cli,
            "hermes_cli.plugin_isolation": plugin,
        }
        return registry, modules

    def make_native_context(self, registry, *, mismatch=False, raise_after=False):
        class Context:
            profile_name = "main"
            _manager = types.SimpleNamespace(scope_key="main-scope")
            manifest = types.SimpleNamespace(source="local")

            def register_tool(self, **kwargs):
                self.registered = kwargs
                registry.installed = types.SimpleNamespace(
                    handler=kwargs["handler"],
                    schema=kwargs["schema"] if not mismatch else {"bad": True},
                    toolset=kwargs["toolset"],
                    check_fn=kwargs["check_fn"])
                self.disposed = False

                class Handle:
                    def dispose(instance):
                        self.disposed = True
                        registry.installed = None

                if raise_after:
                    raise OSError("synthetic lost reply after registration")
                return Handle()
        return Context()

    def test_actual_native_registration_receipt(self):
        registry, modules = self.make_native_owner()
        context = self.make_native_context(registry)
        with patch.dict(sys.modules, modules):
            receipt = register_native_tool(
                context, authorize_session=lambda session: self.grant,
                port=self.port, currentness_guard=lambda grant: True)
        self.assertIsNotNone(receipt)
        self.assertEqual(context.registered["name"], TOOL)
        self.assertEqual(context.registered["toolset"], TOOLSET)
        self.assertFalse(context.registered["is_async"])
        self.assertEqual(registry.installed.handler.__name__, "handle")
        self.assertNotIn("root_id", context.registered["schema"]["parameters"]["properties"])

    def test_native_registration_collision_is_no_write(self):
        registry, modules = self.make_native_owner()
        registry.installed = object()
        context = self.make_native_context(registry)
        with patch.dict(sys.modules, modules):
            with self.assertRaisesRegex(Exception, "HERMES_NATIVE_TOOL_COLLISION"):
                register_native_tool(context,
                    authorize_session=lambda session: self.grant,
                    port=self.port, currentness_guard=lambda grant: True)
        self.assertFalse(hasattr(context, "registered"))

    def test_native_registration_wrong_readback_disposes_original_handle(self):
        registry, modules = self.make_native_owner()
        context = self.make_native_context(registry, mismatch=True)
        with patch.dict(sys.modules, modules):
            with self.assertRaisesRegex(Exception, "HERMES_REGISTRATION_READBACK_MISMATCH"):
                register_native_tool(context,
                    authorize_session=lambda session: self.grant,
                    port=self.port, currentness_guard=lambda grant: True)
        self.assertTrue(context.disposed)
        self.assertIsNone(registry.installed)

    def test_native_registration_lost_return_is_unknown_not_refused(self):
        registry, modules = self.make_native_owner()
        context = self.make_native_context(registry, raise_after=True)
        with patch.dict(sys.modules, modules):
            with self.assertRaisesRegex(Exception, "HERMES_REGISTRATION_EFFECT_UNKNOWN"):
                register_native_tool(context,
                    authorize_session=lambda session: self.grant,
                    port=self.port, currentness_guard=lambda grant: True)
        self.assertIsNotNone(registry.installed)


if __name__ == "__main__":
    unittest.main()
