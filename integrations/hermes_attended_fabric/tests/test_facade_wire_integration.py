"""Native handler -> Hermes client -> real Node Fabric facade -> fixture engine.

Only the final command engine and incumbent durable admission are doubles.
The fixture subprocess never runs the generated adapter commands or contacts
any host/provider. Restart cases prove composition against retained owner state,
not an installed M2 restart or a production worker START.
"""
from __future__ import annotations

import hashlib
import copy
import json
from pathlib import Path
import subprocess
import unittest

from integrations.hermes_attended_fabric.facade_port import FabricFacadePort
from integrations.hermes_attended_fabric.hermes_mcp_client import (
    EXECUTION_SERVER, bind_native_mcp_client,
)
from integrations.hermes_attended_fabric.native import (
    SessionGrant, native_handler, run_id_for,
)

FIXTURE = Path(__file__).with_name("facade_wire_fixture.mjs")
TASK = {"action": "submit", "task_key": "original-task",
        "task_class": "audit", "task_complexity": "C2_COMPLEX_BOUNDED",
        "work_packet": "Return one bounded source finding."}


class WireOwner:
    plugin_id = "fixture-hermes-fabric"
    root = "fixture-root"
    parent = "fixture-parent"

    def __init__(self):
        self.state = "NOT_FOUND"
        self.text = "original retained worker result"
        self.mode = "normal"
        self.follow = False
        self.calls = []
        self.attempts = set()
        self.bind("generation-one")

    def bind(self, generation):
        self.grant = SessionGrant("fixture", "fixture-session", self.root,
                                  self.parent, generation)
        grant = self.grant
        self.run_id = run_id_for(grant, TASK["task_key"])
        self.port = FabricFacadePort(bind_native_mcp_client(self),
                                    authorize_new_run=self.admit)
        self.handler = native_handler(profile_id="fixture",
            authorize_session=lambda _: grant, port=self.port,
            currentness_guard=lambda original: original == self.grant)

    def admit(self, grant, run_id):
        if run_id in self.attempts:
            return False
        self.attempts.add(run_id)
        return True

    def _mcp_allowlist(self, plugin):
        assert plugin == self.plugin_id
        return [EXECUTION_SERVER]

    def observation(self):
        effective = self.run_id + ".q1.fixture" if self.follow else self.run_id
        status = {"schema": "mastermind.fabric_task_status.v1",
            "run_id": effective, "root_id": self.root,
            "parent_run_id": self.parent, "state": self.state,
            "result_available": self.state == "TERMINAL", "accepted": None,
            "result_bytes": len(self.text.encode()), "rc": 0, "signal": "ok"}
        if self.state in {"NOT_FOUND", "REQUEST_REFUSED_BEFORE_LAUNCH"}:
            status.update(root_id=None, parent_run_id=None, result_bytes=None,
                          rc=None, signal=None)
        if self.state == "REQUEST_REFUSED_BEFORE_LAUNCH":
            status.update(request_root_id=self.root, request_parent_run_id=self.parent,
                request_retained=True, execution_absence_proven=True,
                same_run_replay_allowed=False,
                continuation={"requested_run_id": self.run_id,
                    "effective_run_id": self.run_id, "prior_attempts": [],
                    "controller_return": "RECORDED",
                    "controller_reason": "request_refused_before_launch"})
        if self.follow:
            return {"schema": "mastermind.fabric_continuation.v1",
                "requested_run_id": self.run_id, "effective_run_id": effective,
                "effective_status": status, "prior_attempts": [],
                "controller_return": "RECORDED"}
        return status

    def call_mcp(self, server, action, arguments, *, timeout):
        assert server == EXECUTION_SERVER and timeout == 30
        outputs = [{"kind": "json", "value": self.observation()}]
        if action == "fabric_request":
            outputs.append({"kind": "lost" if self.mode == "lost" else "pending"})
        elif action == "fabric_result":
            outputs.append({"kind": "text", "value": self.text})
        completed = subprocess.run(["node", str(FIXTURE)], input=json.dumps({
            "action": action, "arguments": arguments,
            "adapter_outputs": outputs, "follow": self.follow}),
            text=True, capture_output=True, timeout=10, check=True)
        captured = json.loads(completed.stdout)
        self.calls.append((action, captured))
        if action == "fabric_request" and self.mode != "lost":
            self.state = ("REQUEST_REFUSED_BEFORE_LAUNCH"
                          if self.mode == "refused" else "ACTIVE_OR_WAITING")
        return {"ok": True, "structuredContent": captured["reply"]["structuredContent"]}

    def ask(self, action):
        arguments = TASK if action == "submit" else {
            "action": action, "task_key": TASK["task_key"]}
        return json.loads(self.handler(arguments, session_id="fixture-session"))


class TestFacadeWireIntegration(unittest.TestCase):
    def test_original_submit_restart_and_result_share_one_run(self):
        owner = WireOwner()
        submitted = owner.ask("submit")
        self.assertEqual(submitted["state"], "CONTROLLER_CREATED")
        self.assertFalse(submitted["worker_started"])
        original_run = owner.run_id
        owner.state = "TERMINAL"
        owner.bind("generation-two")
        existing = owner.ask("submit")
        result = owner.ask("result")
        self.assertEqual(owner.run_id, original_run)
        self.assertEqual(existing["state"], "TERMINAL")
        self.assertEqual(result["result_text"], owner.text)
        self.assertEqual(result["result_digest"], hashlib.sha256(owner.text.encode()).hexdigest())
        self.assertEqual([n for n, _ in owner.calls].count("fabric_request"), 1)
        self.assertEqual([n for n, _ in owner.calls][-3:],
                         ["fabric_status", "fabric_result", "fabric_status"])

    def test_incumbent_successor_result_preserves_origin_and_parent(self):
        owner = WireOwner()
        owner.state = "TERMINAL"
        owner.follow = True
        got = owner.ask("result")
        self.assertEqual(got["state"], "TERMINAL")
        self.assertEqual(got["run_id"], owner.run_id)
        self.assertEqual(got["parent_id"], owner.parent)
        self.assertEqual(got["result_text"], owner.text)
        result_wire = owner.calls[1][1]["reply"]["structuredContent"]
        self.assertEqual(result_wire["effective_run_id"], owner.run_id + ".q1.fixture")
        self.assertEqual(result_wire["accept_run_id"], result_wire["effective_run_id"])
        self.assertFalse(result_wire["accepted"])

    def test_lost_submit_restart_and_absent_status_cannot_repeat_effect(self):
        owner = WireOwner()
        owner.mode = "lost"
        lost = owner.ask("submit")
        self.assertEqual(lost["state"], "EFFECT_UNKNOWN")
        owner.bind("generation-two")
        again = owner.ask("submit")
        self.assertEqual(again["state"], "REFUSED")
        self.assertEqual(again["reason"], "FABRIC_ORIGINAL_ADMISSION_REFUSED")
        self.assertEqual([n for n, _ in owner.calls].count("fabric_request"), 1)
        self.assertEqual(again["run_id"], lost["run_id"])

    def test_prelaunch_refusal_is_visible_without_replay_or_result_authority(self):
        owner = WireOwner()
        owner.mode = "refused"
        owner.ask("submit")
        owner.bind("generation-two")
        observed = owner.ask("status")
        self.assertEqual(observed["state"], "REQUEST_REFUSED_BEFORE_LAUNCH")
        self.assertTrue(observed["request_correlation_only"])
        for field in ("root_verified", "worker_started", "retry_authorized",
                      "result_consumption_authorized"):
            self.assertFalse(observed[field])
        self.assertEqual(owner.ask("submit")["state"], observed["state"])
        self.assertEqual(owner.ask("result")["state"], "UNAVAILABLE")
        self.assertEqual([n for n, _ in owner.calls].count("fabric_request"), 1)
        self.assertNotIn("fabric_result", [n for n, _ in owner.calls])

    def test_oversized_result_is_not_released_as_a_successful_partial_return(self):
        owner = WireOwner()
        owner.state = "TERMINAL"
        owner.text = "x" * 8193
        got = owner.ask("result")
        self.assertEqual(got["state"], "UNAVAILABLE")
        self.assertNotIn("result_text", got)
        self.assertNotIn("result_digest", got)
        wire = owner.calls[-1][1]
        self.assertEqual(wire["reply"]["structuredContent"]["error"], "RESULT_TOO_LARGE")
        self.assertEqual(len(wire["calls"]), 1)

    def test_incomplete_or_foreign_request_correlation_never_becomes_proof(self):
        owner = WireOwner()
        owner.state = "REQUEST_REFUSED_BEFORE_LAUNCH"
        original = owner.call_mcp(EXECUTION_SERVER, "fabric_status", {
            "run_id": owner.run_id, "root_id": owner.root}, timeout=30)["structuredContent"]
        changes = (
            (("status", "request_root_id"), "foreign"),
            (("status", "request_parent_run_id"), "foreign"),
            (("status", "run_id"), "foreign"),
            (("status", "request_retained"), False),
            (("status", "execution_absence_proven"), False),
            (("status", "result_available"), True),
            (("status", "same_run_replay_allowed"), True),
            (("status", "continuation", "controller_return"), "UNCONFIRMED"),
            (("parent_recovery", "requested_run_id"), "foreign"),
            (("parent_recovery", "request_correlation_only"), False),
            (("parent_recovery", "disposition"), "WAIT_ORIGINAL_CONTROLLER"),
            (("effective_run_id",), "foreign"),
        )
        for path, value in changes:
            with self.subTest(path=path):
                raw = copy.deepcopy(original)
                target = raw
                for key in path[:-1]:
                    target = target[key]
                target[path[-1]] = value
                port = FabricFacadePort(lambda *_: raw)
                handler = native_handler(profile_id="fixture",
                    authorize_session=lambda _: owner.grant, port=port,
                    currentness_guard=lambda _: True)
                got = json.loads(handler(TASK, session_id="fixture-session"))
                self.assertEqual(got["state"], "UNVERIFIED")
                self.assertNotIn("request_correlation_only", got)
                self.assertNotIn("result_text", got)
