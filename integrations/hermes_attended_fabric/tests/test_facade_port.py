"""Facade-wire contract tests with a hermetic authenticated-owner double.

All calls remain in-process; no M2, provider, tunnel, credential or paid worker.
"""
from __future__ import annotations

import hashlib
import json
import unittest

from integrations.hermes_attended_fabric.native import (
    SessionGrant, native_handler, run_id_for,
)
from integrations.hermes_attended_fabric.facade_port import FabricFacadePort

FABRIC_SCHEMA = "mastermind.fabric_mcp.v1"
STATUS_SCHEMA = "mastermind.fabric_task_status.v1"


class FakeFacade:
    def __init__(self):
        self.calls = []
        self.state = "NOT_FOUND"
        self.root = "root-from-authenticated-host"
        self.parent = "root-from-authenticated-host"
        self.response = "verified result"
        self.worker_started = False
        self.break_contract = None

    def call_tool(self, name, args):
        self.calls.append((name, dict(args)))
        run = args["run_id"]
        if self.break_contract == "timeout":
            raise TimeoutError()
        if name == "fabric_status":
            status = {
                "schema": STATUS_SCHEMA, "run_id": run,
                "state": self.state,
                "result_available": self.state == "TERMINAL",
            }
            if self.state != "NOT_FOUND":
                status.update(root_id=self.root, parent_run_id=self.parent,
                              controller_lineage={"worker_started": self.worker_started})
            raw = {
                "schema": FABRIC_SCHEMA, "action": name, "run_id": run,
                "effective_run_id": run, "status": status,
                "root_verified": self.state != "NOT_FOUND",
                "execution_absence_proven": False,
            }
        elif name == "fabric_request":
            self.state = "ACTIVE_OR_WAITING"
            raw = {
                "schema": FABRIC_SCHEMA, "action": name, "run_id": run,
                "root_id": args["root_id"], "parent_id": args["parent_id"],
                "delivery": "CONTROLLER_CREATED",
                "controller_pid": 1234,
                "worker_start_proven": False,
            }
        elif name == "fabric_result":
            data = self.response.encode("utf-8")
            raw = {
                "schema": FABRIC_SCHEMA, "action": name, "run_id": run,
                "root_id": args["root_id"], "effective_run_id": run,
                "accept_run_id": run, "adapter_response": self.response,
                "response_bytes": len(data),
                "response_sha256": hashlib.sha256(data).hexdigest(),
            }
        else:
            raise AssertionError("unexpected " + name)
        if self.break_contract == "wrong_schema":
            raw["schema"] = "foreign"
        if self.break_contract == "wrong_result_digest" and name == "fabric_result":
            raw["response_sha256"] = "a" * 64
        if self.break_contract == "missing_parent" and name == "fabric_status":
            raw["status"].pop("parent_run_id", None)
        if self.break_contract == "missing_live_lineage" and name == "fabric_status":
            raw["status"].pop("parent_run_id", None)
            raw["status"].pop("root_id", None)
            raw["root_verified"] = False
        if self.break_contract == "wrong_run":
            raw["run_id"] = "foreign"
        if self.break_contract == "backend_refusal":
            raw["error"] = "OBSERVATION_INCOMPLETE"
        return raw


class TestFabricFacadePort(unittest.TestCase):
    def setUp(self):
        self.facade = FakeFacade()
        self.grant = SessionGrant("main", "session-owned", self.facade.root,
                                  self.facade.parent, "generation-current")
        self.port = FabricFacadePort(self.facade.call_tool, authorize_new_run=lambda g, r: True)
        self.handle = native_handler(
            profile_id="main", authorize_session=lambda session: self.grant,
            port=self.port, currentness_guard=lambda grant: True)
        self.run_id = run_id_for(self.grant, "build-once")

    def ask(self, action, **options):
        return json.loads(self.handle({"action": action, "task_key": "build-once",
            **options}, session_id="session-owned"))

    def task(self):
        return {"task_class": "fix_build", "task_complexity": "C1_ROUTINE_BOUNDED",
                "work_packet": "Build one bounded fixture and prove result."}

    def test_submit_actual_fabric_tool_arguments_are_bound_to_host(self):
        got = self.ask("submit", **self.task())
        self.assertEqual(got["state"], "CONTROLLER_CREATED")
        self.assertFalse(got["worker_started"])
        names = [name for name, _ in self.facade.calls]
        self.assertEqual(names, ["fabric_status", "fabric_request"])
        request = self.facade.calls[-1][1]
        self.assertEqual(request["run_id"], self.run_id)
        self.assertEqual(request["root_id"], self.grant.root_id)
        self.assertEqual(request["parent_id"], self.grant.parent_id)
        self.assertEqual(request["task_complexity"], "C1_ROUTINE_BOUNDED")
        self.assertNotIn("model", request)
        self.assertNotIn("pool", request)
        self.assertNotIn("host", request)

    def test_existing_worker_is_not_repeated(self):
        self.facade.state = "ACTIVE_OR_WAITING"
        got = self.ask("submit", **self.task())
        self.assertEqual(got["state"], "ACTIVE_OR_WAITING")
        self.assertEqual([name for name, _ in self.facade.calls], ["fabric_status"])

    def test_status_never_claims_start_from_controller_only(self):
        submitted = self.ask("submit", **self.task())
        self.assertEqual(submitted["state"], "CONTROLLER_CREATED")
        self.assertFalse(submitted["worker_started"])
        observed = self.ask("status")
        self.assertEqual(observed["state"], "ACTIVE_OR_WAITING")
        self.assertFalse(observed["worker_started"])
        self.assertEqual(len([x for x, _ in self.facade.calls
                              if x == "fabric_request"]), 1)

    def test_status_projects_only_explicit_owner_start_evidence(self):
        self.facade.state = "ACTIVE_OR_WAITING"
        self.facade.worker_started = True
        observed = self.ask("status")
        self.assertTrue(observed["worker_started"])
        self.assertEqual([name for name, _ in self.facade.calls],
                         ["fabric_status"])

    def test_original_parent_result_bytes_and_digest(self):
        self.facade.state = "TERMINAL"
        got = self.ask("result")
        self.assertEqual(got["state"], "TERMINAL")
        self.assertEqual(got["result_text"], "verified result")
        self.assertEqual(got["result_digest"],
                         hashlib.sha256(b"verified result").hexdigest())
        self.assertEqual([n for n, _ in self.facade.calls],
                         ["fabric_status", "fabric_result", "fabric_status"])

    def test_wrong_native_session_cannot_read_result(self):
        got = json.loads(self.handle(
            {"action": "result", "task_key": "build-once"},
            session_id="foreign-session"))
        self.assertEqual(got["state"], "REFUSED")
        self.assertEqual(self.facade.calls, [])

    def test_absent_original_parent_refuses_result(self):
        self.facade.state = "TERMINAL"
        self.facade.break_contract = "missing_parent"
        got = self.ask("result")
        self.assertEqual(got["state"], "UNAVAILABLE")
        self.assertEqual([name for name, _ in self.facade.calls],
                         ["fabric_status"])

    def test_foreign_root_refuses_and_no_result(self):
        self.facade.state = "TERMINAL"
        self.facade.root = "another-root"
        got = self.ask("result")
        self.assertEqual(got["state"], "UNAVAILABLE")
        self.assertEqual(len(self.facade.calls), 1)

    def test_active_run_without_canonical_lineage_blocks_duplicate_submit(self):
        self.facade.state = "ACTIVE_OR_WAITING"
        self.facade.break_contract = "missing_live_lineage"
        observed = self.ask("status")
        self.assertEqual(observed["state"], "UNVERIFIED")
        self.assertEqual(observed["reason"], "FABRIC_STATUS_LINEAGE_NOT_PROVEN")
        attempted = self.ask("submit", **self.task())
        self.assertEqual(attempted["state"], "UNVERIFIED")
        self.assertEqual([name for name, _ in self.facade.calls],
                         ["fabric_status", "fabric_status"])

    def test_wrong_digest_does_not_reveal_result_bytes(self):
        self.facade.state = "TERMINAL"
        self.facade.break_contract = "wrong_result_digest"
        got = self.ask("result")
        self.assertEqual(got["state"], "UNAVAILABLE")
        self.assertNotIn("result_text", got)

    def test_incomplete_original_observation_refuses_submit(self):
        self.facade.break_contract = "backend_refusal"
        got = self.ask("submit", **self.task())
        self.assertEqual(got["state"], "UNAVAILABLE")
        self.assertEqual([name for name, _ in self.facade.calls],
                         ["fabric_status"])

    def test_old_wire_schema_is_refused(self):
        self.facade.break_contract = "wrong_schema"
        got = self.ask("status")
        self.assertEqual(got["state"], "UNAVAILABLE")

    def test_post_send_timeout_never_retries(self):
        original = self.facade.call_tool
        def interrupted(name, args):
            if name == "fabric_request":
                self.facade.calls.append((name, dict(args)))
                raise TimeoutError("controller return lost")
            return original(name, args)
        self.port = FabricFacadePort(interrupted, authorize_new_run=lambda g, r: True)
        self.handle = native_handler(
            profile_id="main", authorize_session=lambda session: self.grant,
            port=self.port, currentness_guard=lambda grant: True)
        got = self.ask("submit", **self.task())
        self.assertEqual(got["state"], "EFFECT_UNKNOWN")
        self.assertEqual([name for name, _ in self.facade.calls],
                         ["fabric_status", "fabric_request"])

    def test_fabric_admission_unbound_is_proven_no_send(self):
        port = FabricFacadePort(self.facade.call_tool)
        handle = native_handler(
            profile_id="main", authorize_session=lambda s: self.grant,
            port=port, currentness_guard=lambda g: True)
        got = json.loads(handle(
            {"action": "submit", "task_key": "build-once", **self.task()},
            session_id=self.grant.session_id))
        self.assertEqual(got["state"], "REFUSED")
        self.assertEqual(got["reason"], "FABRIC_ORIGINAL_ADMISSION_UNBOUND")
        self.assertEqual([n for n, _ in self.facade.calls], ["fabric_status"])

    def test_host_admission_revocation_before_send_is_no_effect(self):
        port = FabricFacadePort(self.facade.call_tool,
                                authorize_new_run=lambda g, r: False)
        handle = native_handler(
            profile_id="main", authorize_session=lambda s: self.grant,
            port=port, currentness_guard=lambda g: True)
        got = json.loads(handle(
            {"action": "submit", "task_key": "build-once", **self.task()},
            session_id=self.grant.session_id))
        self.assertEqual(got["state"], "REFUSED")
        self.assertEqual(got["reason"], "FABRIC_ORIGINAL_ADMISSION_REFUSED")
        self.assertEqual([n for n, _ in self.facade.calls], ["fabric_status"])

    def test_strict_manual_grant_reaches_native_facade(self):
        grant = SessionGrant("main", "session-owned", self.grant.root_id,
                             self.grant.parent_id, "generation-current",
                             manual_pools=("minimax",),
                             manual_models=(("minimax", "MiniMax-M3"),))
        handle = native_handler(
            profile_id="main", authorize_session=lambda s: grant,
            port=self.port, currentness_guard=lambda g: True)
        got = json.loads(handle({
            "action": "submit", "task_key": "build-once",
            "pool": "minimax", "model": "MiniMax-M3", **self.task()},
            session_id=grant.session_id))
        self.assertEqual(got["state"], "CONTROLLER_CREATED")
        request = self.facade.calls[-1][1]
        self.assertEqual(request["pool"], "minimax")
        self.assertEqual(request["model"], "MiniMax-M3")

    def test_preview_without_host_preview_owner_is_unavailable(self):
        got = self.ask("preview", task_class="mechanical",
                       task_complexity="C0_MECHANICAL")
        self.assertEqual(got["state"], "UNAVAILABLE")
        self.assertEqual(self.facade.calls, [])

    def test_preview_with_host_preview_owner_is_read_only(self):
        port = FabricFacadePort(
            self.facade.call_tool, authorize_new_run=lambda g, r: True,
            preview_route=lambda g, r, tc, co, reason: {
                "state": "PREVIEW_ONLY", "reserved": False,
                "pool": "minimax", "model": "MiniMax-M3"})
        handle = native_handler(
            profile_id="main", authorize_session=lambda s: self.grant,
            port=port, currentness_guard=lambda g: True)
        result = json.loads(handle(
            {"action": "preview", "task_key": "build-once",
             "task_class": "mechanical", "task_complexity": "C0_MECHANICAL"},
            session_id=self.grant.session_id))
        self.assertEqual(result["state"], "PREVIEW_ONLY")
        self.assertEqual(self.facade.calls, [])

    def test_no_command_or_credential_are_exposed(self):
        self.assertFalse(any(hasattr(self.port, name) for name in (
            "api_key", "backend", "run_shell", "spawn", "credential_store",
            "create_job", "approve", "accept")))


if __name__ == "__main__":
    unittest.main()
