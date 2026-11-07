"""Authority and original-lineage races in the Hermes/Fabric consumer.

These tests exercise the real handler/client/port with deterministic owner
doubles. They make no provider call and prove no installed host capability.
"""
from __future__ import annotations

import hashlib
import json
import unittest

from integrations.hermes_attended_fabric.native import (
    SessionGrant, native_handler, run_id_for,
)
from integrations.hermes_attended_fabric.facade_port import FabricFacadePort
from integrations.hermes_attended_fabric.hermes_mcp_client import (
    EXECUTION_SERVER, bind_native_mcp_client,
)
from integrations.hermes_attended_fabric.tests.test_native import FakeOwner
from integrations.hermes_attended_fabric.tests.test_facade_port import FakeFacade

SECRET = "private original-parent worker output"
TASK = {"task_class": "fix_build", "task_complexity": "C1_ROUTINE_BOUNDED",
        "work_packet": "Perform the original bounded task."}


class TestNativeReturnCurrentness(unittest.TestCase):
    def make(self, revoke_on, *, guard_error=False, existing=False):
        port = FakeOwner()
        grant = SessionGrant("main", "session-a", "root-a", "root-a", "epoch-a")
        revoked = [False]
        if existing:
            port.state = "TERMINAL"
        original = getattr(port, revoke_on)

        def operation(*args, **kwargs):
            reply = original(*args, **kwargs)
            if revoke_on == "result":
                reply["result_text"] = SECRET
                reply["result_digest"] = hashlib.sha256(SECRET.encode()).hexdigest()
            revoked[0] = True
            return reply

        setattr(port, revoke_on, operation)

        def current(original_grant):
            self.assertIs(original_grant, grant)
            if revoked[0] and guard_error:
                raise OSError("private guard diagnostic")
            return not revoked[0]

        handler = native_handler(profile_id="main", authorize_session=lambda _: grant,
                                 port=port, currentness_guard=current)
        return port, grant, handler

    def test_reads_withhold_output_when_original_grant_changes(self):
        for action in ("status", "result", "preview"):
            for guard_error in (False, True):
                with self.subTest(action=action, guard_error=guard_error):
                    port, grant, handler = self.make(action, guard_error=guard_error)
                    arguments = {"action": action, "task_key": "same-task"}
                    if action == "preview":
                        arguments.update(TASK)
                    raw = handler(arguments, session_id=grant.session_id)
                    result = json.loads(raw)
                    self.assertEqual(result["state"],
                                     "UNAVAILABLE" if guard_error else "REFUSED")
                    self.assertNotIn(SECRET, raw)
                    self.assertNotIn("private guard diagnostic", raw)
                    self.assertNotIn("result_digest", result)
                    self.assertEqual([call[0] for call in port.calls], [action])

    def test_submit_preflight_cannot_release_a_stale_existing_result(self):
        for existing in (False, True):
            with self.subTest(existing=existing):
                port, grant, handler = self.make("status", existing=existing)
                result = json.loads(handler(
                    {"action": "submit", "task_key": "same-task", **TASK},
                    session_id=grant.session_id))
                self.assertEqual(result["state"], "REFUSED")
                self.assertEqual([call[0] for call in port.calls], ["status"])

    def test_recorded_submit_stays_recorded_when_response_is_withheld(self):
        for guard_error in (False, True):
            with self.subTest(guard_error=guard_error):
                port, grant, handler = self.make("submit", guard_error=guard_error)
                result = json.loads(handler(
                    {"action": "submit", "task_key": "same-task", **TASK},
                    session_id=grant.session_id))
                self.assertEqual(result["state"], "CONTROLLER_CREATED")
                self.assertIs(result.get("response_withheld"), True)
                self.assertIs(result.get("submission_recorded"), True)
                self.assertIs(result.get("retry_authorized"), False)
                self.assertEqual(result["run_id"], run_id_for(grant, "same-task"))
                self.assertNotIn("result_text", result)
                self.assertNotIn("result_digest", result)
                self.assertEqual([call[0] for call in port.calls], ["status", "submit"])


class NativeMcpContext:
    plugin_id = "mmx-native-fabric"

    def __init__(self, facade, revoke_on=None, fail_allowlist=False):
        self.facade = facade
        self.allowed = True
        self.revoke_on = revoke_on
        self.fail_allowlist = fail_allowlist

    def _mcp_allowlist(self, _plugin_id):
        if not self.allowed and self.fail_allowlist:
            raise OSError("private allowlist diagnostic")
        return [EXECUTION_SERVER] if self.allowed else []

    def call_mcp(self, server, action, arguments, timeout=30):
        assert server == EXECUTION_SERVER
        document = self.facade.call_tool(action, arguments)
        if action == self.revoke_on:
            self.allowed = False
        document["private_diagnostic"] = SECRET
        return {"ok": True, "structuredContent": document}


class TestComposedReturnCurrentness(unittest.TestCase):
    def compose(self, facade, *, revoke_on=None, fail_allowlist=False,
                currentness_guard=lambda _: True):
        grant = SessionGrant("main", "native-session", facade.root, facade.parent, "epoch")
        ctx = NativeMcpContext(facade, revoke_on, fail_allowlist)
        port = FabricFacadePort(bind_native_mcp_client(ctx),
                                authorize_new_run=lambda *_: True)
        handle = native_handler(profile_id="main", authorize_session=lambda _: grant,
                                port=port, currentness_guard=currentness_guard)
        return grant, ctx, handle

    def test_native_mcp_rechecks_permission_after_read(self):
        for action in ("fabric_status", "fabric_result"):
            for fail_allowlist in (False, True):
                with self.subTest(action=action, fail_allowlist=fail_allowlist):
                    facade = FakeFacade()
                    facade.state = "TERMINAL"
                    ctx = NativeMcpContext(facade, action, fail_allowlist)
                    client = bind_native_mcp_client(ctx)
                    with self.assertRaisesRegex(Exception, "HERMES_"):
                        client(action, {"run_id": "original", "root_id": facade.root})
                    self.assertEqual(len(facade.calls), 1)

    def test_mcp_revocation_after_submit_retains_only_control_receipt(self):
        facade = FakeFacade()
        grant, ctx, handler = self.compose(facade, revoke_on="fabric_request")
        args = {"action": "submit", "task_key": "same-task", **TASK}
        raw = handler(args, session_id=grant.session_id)
        result = json.loads(raw)
        self.assertEqual(result["state"], "CONTROLLER_CREATED")
        self.assertIs(result.get("response_withheld"), True)
        self.assertIs(result.get("submission_recorded"), True)
        self.assertIs(result.get("retry_authorized"), False)
        self.assertNotIn(SECRET, raw)
        self.assertNotIn("private_diagnostic", result)
        self.assertNotIn("controller_pid", result)
        handler(args, session_id=grant.session_id)
        self.assertEqual(sum(name == "fabric_request" for name, _ in facade.calls), 1)

    def test_result_requires_current_original_lineage_after_fetch(self):
        for change in ("parent", "root", "effective", "unavailable"):
            with self.subTest(change=change):
                facade = FakeFacade()
                facade.state = "TERMINAL"
                facade.response = SECRET
                original = facade.call_tool
                fetched = [False]

                def changing(action, args):
                    if action == "fabric_status" and fetched[0] and change == "unavailable":
                        raise TimeoutError()
                    reply = original(action, args)
                    if action == "fabric_result":
                        fetched[0] = True
                        if change == "parent":
                            facade.parent = "other-parent"
                        elif change == "root":
                            facade.root = "other-root"
                    elif action == "fabric_status" and fetched[0] and change == "effective":
                        reply["effective_run_id"] = "different-attempt-same-bytes"
                        reply["status"]["run_id"] = reply["effective_run_id"]
                        reply["status"]["continuation"] = {
                            "requested_run_id": args["run_id"],
                            "effective_run_id": reply["effective_run_id"]}
                    return reply

                facade.call_tool = changing
                grant, ctx, handler = self.compose(facade)
                raw = handler({"action": "result", "task_key": "same-task"},
                              session_id=grant.session_id)
                result = json.loads(raw)
                self.assertEqual(result["state"], "UNAVAILABLE")
                self.assertNotIn(SECRET, raw)
                self.assertNotIn("result_digest", result)
                self.assertEqual(sum(name == "fabric_result" for name, _ in facade.calls), 1)

    def test_final_guard_runs_after_lineage_recheck(self):
        facade = FakeFacade()
        facade.state = "TERMINAL"
        facade.response = SECRET
        original = facade.call_tool
        status_reads = [0]
        current = [True]

        def changing(action, args):
            reply = original(action, args)
            if action == "fabric_status":
                status_reads[0] += 1
                if status_reads[0] == 2:
                    current[0] = False
            return reply

        facade.call_tool = changing
        grant, ctx, handler = self.compose(facade, currentness_guard=lambda _: current[0])
        raw = handler({"action": "result", "task_key": "same-task"},
                      session_id=grant.session_id)
        self.assertEqual(json.loads(raw)["state"], "REFUSED")
        self.assertNotIn(SECRET, raw)
        self.assertEqual(status_reads[0], 2)

    def test_revoked_mcp_cannot_upgrade_a_malformed_submit_to_recorded(self):
        for key, value in (("root_id", "foreign"), ("parent_id", None),
                           ("controller_pid", True), ("delivery", "QUEUED"),
                           ("worker_start_proven", True)):
            with self.subTest(field=key):
                facade = FakeFacade()
                original = facade.call_tool

                def malformed(action, args):
                    reply = original(action, args)
                    if action == "fabric_request":
                        reply[key] = value
                    return reply

                facade.call_tool = malformed
                grant, ctx, handler = self.compose(facade, revoke_on="fabric_request")
                raw = handler({"action": "submit", "task_key": "same-task", **TASK},
                              session_id=grant.session_id)
                got = json.loads(raw)
                self.assertEqual(got["state"], "EFFECT_UNKNOWN")
                self.assertNotIn("submission_recorded", got)
                self.assertNotIn(SECRET, raw)
                self.assertEqual(sum(n == "fabric_request" for n, _ in facade.calls), 1)


if __name__ == "__main__":
    unittest.main()
