"""Offline WP4 acceptance tests. No Fabric, Cursor, or Executive process is started."""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import unittest
from pathlib import Path

from integrations.hermes_delegate.admission import NOT_BOUND_REASON
from integrations.hermes_delegate.bridge import Bridge
from integrations.hermes_delegate.handoff import HandoffError, render_child_handoff, validate_handoff
from integrations.hermes_delegate.policy import REQUIRED_DISABLED_TOOLSETS, load_policy
from integrations.hermes_delegate.tool import TOOL_REGISTRATION, dispatch, registered_tools


REPO = Path(__file__).resolve().parents[3]
PACKAGE = Path(__file__).resolve().parents[1]
PARENT = "hermes-parent-01"
ROOT = "hermes-root-0001"
REVIEWER = "independent-reviewer-01"
REFUSAL = "quota window closed; do not reroute"


class FakeAdmission:
    def __init__(self, outcome="ADMITTED", reason="admitted"):
        self.outcome = outcome
        self.reason = reason
        self.calls = []
        self.extra = {}
        self.error = None
        self.decision = None

    def admit(self, submission):
        self.calls.append(dict(submission))
        if self.error is not None:
            raise self.error
        if self.decision is not None:
            return self.decision
        return {
            **self.extra,
            "schema": "mastermind.hermes_delegate.admission/v1",
            "outcome": self.outcome,
            "reason": self.reason,
            "carrier": submission["carrier"],
            "idempotency_key": submission["idempotency_key"],
        }


class FakeCarrier:
    def __init__(self, body=b"bounded child result\n"):
        self.body = body
        self.submits = []
        self.cancels = []
        self.statuses = []
        self.results = []
        self.submit_result = None
        self.submit_error = None

    def submit(self, spec):
        self.submits.append(spec)
        if self.submit_error is not None:
            raise self.submit_error
        if self.submit_result is not None:
            return dict(self.submit_result)
        return {"state": "SUBMITTED", "run_id": spec["run_id"]}

    def status(self, run_id):
        self.statuses.append(run_id)
        return {
            "state": "TERMINAL",
            "result_available": True,
            "result_sha256": hashlib.sha256(self.body).hexdigest(),
        }

    def cancel(self, run_id):
        self.cancels.append(run_id)
        return {"state": "CANCELLED"}

    def result(self, run_id):
        self.results.append(run_id)
        return {"body": self.body}


class FakeReviewVerifier:
    """Synthetic stand-in for an EXISTING independent review owner.

    Its fixture identity is deliberately separate from both child and parent.
    This is not an authentication implementation or an authorized deployment.
    """
    def __init__(self):
        self.calls = []
        self.error = None

    def verify(self, **proof):
        self.calls.append(dict(proof))
        if self.error is not None:
            raise self.error
        return (
            proof["reviewer_id"] == REVIEWER
            and proof["parent_id"] == PARENT
            and proof["root_id"] == ROOT
            and proof["carrier"] == "fabric"
            and proof["idempotency_key"].startswith("child-impl-")
            and proof["verdict"] in {"accept", "reject"}
        )


class FakeParentVerifier:
    """Fixture-only original-parent attestation, not Executive OS admission."""
    def __init__(self):
        self.calls = []
        self.error = None
        self.deny = False

    def verify(self, **binding):
        self.calls.append(dict(binding))
        if self.error is not None:
            raise self.error
        if self.deny:
            return False
        return (
            binding["parent_id"] == PARENT
            and binding["root_id"] == ROOT
            and binding["carrier"] == "fabric"
            and binding["run_id"] == binding["idempotency_key"]
            and binding["idempotency_key"].startswith("child-impl-")
            and isinstance(binding["result_sha256"], str)
            and len(binding["result_sha256"]) == 64
        )


def bridge_for(admission=None, fabric=None, cursor=None, policy=None):
    admission = admission or FakeAdmission()
    fabric = fabric or FakeCarrier()
    cursor = cursor or FakeCarrier()
    bridge = Bridge(
        admission,
        {"fabric": fabric, "cursor_cloud": cursor},
        policy if policy is not None else load_policy(),
        review_verifier=FakeReviewVerifier(),
        parent_verifier=FakeParentVerifier(),
    )
    return bridge, admission, fabric, cursor


def request(**overrides):
    body = {
        "action": "submit",
        "idempotency_key": "child-impl-0001",
        "parent_id": PARENT,
        "root_id": ROOT,
        "child_kind": "implementation",
        "carrier": "fabric",
        "task_class": "fix_build",
        "task_complexity": "C1_ROUTINE_BOUNDED",
        "objective": "Repair the bounded parser test in the named file.",
        "acceptance": "The named unit test passes offline.",
        "constraints": ["Touch only the named test and parser."],
    }
    body.update(overrides)
    return body


def loads(raw):
    return json.loads(raw)


def fixture_dispatch(arguments, bridge):
    """Exercise trusted owner-side fixture methods separately from model tools.

    Only submit/status/cancel travel through the actual model-facing dispatch.
    Offline source tests may simulate a review/parent-consume by invoking
    Bridge directly, but that does NOT prove authenticated reviewer authority
    or make terminal operations available to a model or live runtime.
    """
    if isinstance(arguments, dict) and arguments.get("action") == "review":
        return json.dumps(bridge.review(
            arguments["idempotency_key"],
            reviewer_id=arguments.get("reviewer_id", ""),
            verdict=arguments.get("verdict", ""),
            result_sha256=arguments.get("result_sha256", ""),
        ))
    if isinstance(arguments, dict) and arguments.get("action") == "consume":
        return json.dumps(bridge.consume(
            arguments["idempotency_key"],
            parent_id=arguments.get("parent_id", ""),
            handoff_model=arguments.get("handoff_model"),
            workstream=arguments.get("workstream"),
            session=arguments.get("session"),
        ))
    return dispatch(arguments, bridge)


class DelegateBridge(unittest.TestCase):
    def test_parent_consumption_requires_existing_owner_verification(self):
        fabric = FakeCarrier()
        bridge = Bridge(
            FakeAdmission(), {"fabric": fabric},
            review_verifier=FakeReviewVerifier(),
        )
        self.assertEqual(loads(dispatch(request(), bridge))["state"], "SUBMITTED")
        sha = hashlib.sha256(fabric.body).hexdigest()
        self.assertEqual(bridge.review(
            "child-impl-0001", reviewer_id=REVIEWER,
            verdict="accept", result_sha256=sha,
        )["state"], "REVIEWED")
        unbound = bridge.consume("child-impl-0001", parent_id=PARENT)
        self.assertEqual(unbound["state"], "REFUSED")
        self.assertEqual(unbound["reason"], "PARENT_CONSUMPTION_NOT_BOUND")
        self.assertEqual(fabric.results, [])

        owned, _admission, other_fabric, _cursor = bridge_for()
        self.assertEqual(loads(dispatch(request(), owned))["state"], "SUBMITTED")
        digest = hashlib.sha256(other_fabric.body).hexdigest()
        self.assertEqual(owned.review(
            "child-impl-0001", reviewer_id=REVIEWER,
            verdict="accept", result_sha256=digest,
        )["state"], "REVIEWED")

        owned.parent_verifier.deny = True
        refused = owned.consume("child-impl-0001", parent_id=PARENT)
        self.assertEqual(refused["reason"], "PARENT_OWNER_UNVERIFIED")
        self.assertEqual(other_fabric.results, [])

        owned.parent_verifier.deny = False
        owned.parent_verifier.error = RuntimeError("parent-private-path")
        unavailable = owned.consume("child-impl-0001", parent_id=PARENT)
        self.assertEqual(unavailable["reason"], "PARENT_OWNER_UNAVAILABLE")
        self.assertNotIn("parent-private-path", str(unavailable))
        self.assertEqual(other_fabric.results, [])

        owned.parent_verifier.error = None
        consumed = owned.consume("child-impl-0001", parent_id=PARENT)
        self.assertEqual(consumed["state"], "CONSUMED")
        self.assertEqual(len(other_fabric.results), 1)
        self.assertEqual(len(owned.parent_verifier.calls), 3)

    def test_bridge_refuses_unbound_or_unverified_review_owner(self):
        fabric = FakeCarrier()
        bridge = Bridge(FakeAdmission(), {"fabric": fabric})
        self.assertEqual(loads(dispatch(request(), bridge))["state"], "SUBMITTED")
        sha = hashlib.sha256(fabric.body).hexdigest()
        not_bound = bridge.review(
            "child-impl-0001", reviewer_id=REVIEWER,
            verdict="accept", result_sha256=sha,
        )
        self.assertEqual(not_bound["state"], "REVIEW_REQUIRED")
        self.assertEqual(not_bound["reason"], "INDEPENDENT_REVIEW_NOT_BOUND")
        self.assertEqual(fabric.results, [])

        backed, _admission, backing_fabric, _cursor = bridge_for()
        self.assertEqual(loads(dispatch(request(), backed))["state"], "SUBMITTED")
        backing_sha = hashlib.sha256(backing_fabric.body).hexdigest()
        forged = backed.review(
            "child-impl-0001", reviewer_id="fabricated-reviewer-02",
            verdict="accept", result_sha256=backing_sha,
        )
        self.assertEqual(forged["state"], "REFUSED")
        self.assertEqual(forged["reason"], "INDEPENDENT_REVIEW_UNVERIFIED")
        self.assertEqual(backing_fabric.results, [])

        backed.review_verifier.error = RuntimeError("private-path-credential-canary")
        unavailable = backed.review(
            "child-impl-0001", reviewer_id=REVIEWER,
            verdict="accept", result_sha256=backing_sha,
        )
        self.assertEqual(unavailable["state"], "REFUSED")
        self.assertEqual(unavailable["reason"], "REVIEW_OWNER_UNAVAILABLE")
        self.assertNotIn("private-path-credential-canary", str(unavailable))
        self.assertEqual(backing_fabric.results, [])

    def test_model_tool_cannot_issue_or_reach_review_or_parent_consume(self):
        public = TOOL_REGISTRATION["schema"]["parameters"]
        branches = public["oneOf"]
        self.assertEqual(len(branches), 2)
        bridge, selected = branches
        self.assertEqual(bridge["properties"]["action"]["enum"], [
            "cancel", "status", "submit",
        ])
        self.assertEqual(bridge["required"], ["action", "idempotency_key"])
        # The selected-child branch is closed: the action and the exact
        # canonical command reference, and nothing else.
        self.assertEqual(selected["properties"]["action"]["enum"], [
            "selected_child_status", "selected_child_submit",
        ])
        self.assertEqual(selected["required"], ["action", "command"])
        self.assertEqual(set(selected["properties"]), {"action", "command"})
        for forbidden in (
            "reviewer_id", "verdict", "result_sha256",
            "handoff_model", "workstream", "session",
        ):
            self.assertNotIn(forbidden, bridge["properties"])
            self.assertNotIn(forbidden, selected["properties"])
        for closed in ("idempotency_key", "job_id", "root_id", "carrier",
                       "objective", "acceptance", "child_kind", "task_class"):
            self.assertNotIn(closed, selected["properties"])

        bridge, _admission, fabric, _cursor = bridge_for()
        submitted = loads(dispatch(request(), bridge))
        self.assertEqual(submitted["state"], "SUBMITTED")
        digest = hashlib.sha256(fabric.body).hexdigest()

        # The model knows the exact child key and digest, and can invent an
        # unrelated reviewer name. Neither grants independent review authority.
        for action_args in (
            {"action": "review", "idempotency_key": "child-impl-0001",
             "reviewer_id": REVIEWER, "verdict": "accept",
             "result_sha256": digest},
            {"action": "review", "idempotency_key": "child-impl-0001"},
            {"action": "consume", "idempotency_key": "child-impl-0001",
             "parent_id": PARENT, "handoff_model": "sol"},
            {"action": "consume", "idempotency_key": "child-impl-0001"},
        ):
            with self.subTest(action=action_args["action"], extras=len(action_args)):
                refusal = loads(dispatch(action_args, bridge))
                self.assertEqual(refusal["state"], "REFUSED")
                self.assertEqual(refusal["reason"], "REVIEW_AND_CONSUME_OWNER_ONLY")
                self.assertFalse(refusal["live_submit"])
                self.assertNotIn("result_text", refusal)
        self.assertEqual(fabric.statuses, [])
        self.assertEqual(fabric.results, [])

        # Even a fixture-only owner-side approval doesn't let the model
        # consume the result or spoof the original parent.
        trusted_fixture = bridge.review(
            "child-impl-0001", reviewer_id=REVIEWER,
            verdict="accept", result_sha256=digest,
        )
        self.assertEqual(trusted_fixture["state"], "REVIEWED")
        denied = loads(dispatch({
            "action": "consume", "idempotency_key": "child-impl-0001",
            "parent_id": PARENT,
        }, bridge))
        self.assertEqual(denied["reason"], "REVIEW_AND_CONSUME_OWNER_ONLY")
        self.assertEqual(fabric.results, [])

    def test_admitted_child_is_reviewed_and_consumed_once(self):
        bridge, _admission, fabric, cursor = bridge_for()
        submitted = loads(fixture_dispatch(request(), bridge))
        self.assertEqual(submitted["state"], "SUBMITTED")
        self.assertEqual(submitted["live_submit"], False)
        self.assertEqual(len(fabric.submits), 1)
        argv = fabric.submits[0]["argv"]
        self.assertEqual(argv[1:3], ["fabric_task.py", "request"])
        self.assertIn("--stdin", argv)
        self.assertNotIn("--pool", argv)
        self.assertNotIn("--model", argv)
        self.assertEqual(cursor.submits, [])

        sha = hashlib.sha256(fabric.body).hexdigest()
        denied = loads(fixture_dispatch({
            "action": "review",
            "idempotency_key": "child-impl-0001",
            "reviewer_id": PARENT,
            "verdict": "accept",
            "result_sha256": sha,
        }, bridge))
        self.assertEqual(denied["state"], "SELF_APPROVAL_FORBIDDEN")
        self.assertEqual(fabric.results, [])

        early = loads(fixture_dispatch({
            "action": "consume",
            "idempotency_key": "child-impl-0001",
            "parent_id": PARENT,
        }, bridge))
        self.assertEqual(early["state"], "REVIEW_REQUIRED")
        self.assertEqual(fabric.results, [])

        reviewed = loads(fixture_dispatch({
            "action": "review",
            "idempotency_key": "child-impl-0001",
            "reviewer_id": REVIEWER,
            "verdict": "accept",
            "result_sha256": sha,
        }, bridge))
        self.assertEqual(reviewed["state"], "REVIEWED")
        self.assertEqual(len(fabric.statuses), 1)

        consumed = loads(fixture_dispatch({
            "action": "consume",
            "idempotency_key": "child-impl-0001",
            "parent_id": PARENT,
            "handoff_model": "sol",
            "workstream": "WS:HERMES-DELEGATE-WP4",
            "session": "sol/hermes-delegate-wp4-20261025",
        }, bridge))
        self.assertEqual(consumed["state"], "CONSUMED")
        self.assertFalse(consumed["already_consumed"])
        self.assertEqual(consumed["result_sha256"], sha)
        self.assertEqual(len(fabric.results), 1)
        validate_handoff(consumed["handoff"])
        self.assertEqual(consumed["handoff"]["schema"], "agentos.handoff.v1")
        self.assertEqual(consumed["handoff"]["model"], "sol")
        self.assertEqual(consumed["handoff"]["ended_because"], "complete")
        self.assertTrue(consumed["handoff"]["unverified"])
        self.assertTrue(consumed["handoff"]["verified"][0]["command"])
        self.assertIn("result_text", consumed)

        # A model can observe that a child was consumed but cannot read its
        # private result or handoff through public status after the fact.
        public = loads(dispatch({
            "action": "status", "idempotency_key": "child-impl-0001",
        }, bridge))
        self.assertEqual(public["state"], "CONSUMED")
        for private in ("result_text", "handoff", "handoff_reason"):
            self.assertNotIn(private, public)
        for hidden in (bridge.status("child-impl-0001"),
                       bridge.submit(request())):
            self.assertNotIn("result_text", hidden)

        # Idempotent replay MUST recheck the exact original-parent binding:
        # otherwise a guessed child key leaks the already-consumed result.
        forged = bridge.consume("child-impl-0001", parent_id="other-parent-02")
        self.assertEqual(forged["reason"], "PARENT_MISMATCH")
        self.assertNotIn("result_text", forged)
        bridge.parent_verifier.deny = True
        revoked = bridge.consume("child-impl-0001", parent_id=PARENT)
        self.assertEqual(revoked["reason"], "PARENT_OWNER_UNVERIFIED")
        self.assertNotIn("result_text", revoked)
        bridge.parent_verifier.deny = False

        again = loads(fixture_dispatch({
            "action": "consume",
            "idempotency_key": "child-impl-0001",
            "parent_id": PARENT,
            "handoff_model": "sol",
            "workstream": "WS:HERMES-DELEGATE-WP4",
            "session": "sol/hermes-delegate-wp4-20261025",
        }, bridge))
        self.assertEqual(again["state"], "CONSUMED")
        self.assertTrue(again["already_consumed"])
        self.assertEqual(len(fabric.results), 1)
        self.assertEqual(cursor.submits, [])

    def test_duplicate_submit_dedupes_and_does_not_switch_carrier(self):
        bridge, admission, fabric, cursor = bridge_for()
        first = loads(fixture_dispatch(request(), bridge))
        second = loads(fixture_dispatch(request(carrier="cursor_cloud"), bridge))
        self.assertEqual(first["idempotency_key"], second["idempotency_key"])
        self.assertEqual(second["carrier"], "fabric")
        self.assertTrue(second["deduped"])
        self.assertEqual(len(admission.calls), 1)
        self.assertEqual(len(fabric.submits), 1)
        self.assertEqual(cursor.submits, [])

        other = loads(fixture_dispatch(request(
            idempotency_key="child-impl-0002",
            objective="Add a separate bounded regression test.",
        ), bridge))
        self.assertEqual(other["state"], "SUBMITTED")
        self.assertFalse(other["deduped"])
        self.assertEqual(len(fabric.submits), 2)
        self.assertEqual(len(admission.calls), 2)

    def test_cancel_is_once_and_blocks_consume(self):
        bridge, _admission, fabric, cursor = bridge_for()
        loads(fixture_dispatch(request(), bridge))
        cancelled = loads(fixture_dispatch({
            "action": "cancel",
            "idempotency_key": "child-impl-0001",
        }, bridge))
        self.assertEqual(cancelled["state"], "CANCELLED")
        self.assertEqual(len(fabric.cancels), 1)
        again = loads(fixture_dispatch({
            "action": "cancel",
            "idempotency_key": "child-impl-0001",
        }, bridge))
        self.assertEqual(again["state"], "CANCELLED")
        self.assertTrue(again["deduped"])
        self.assertEqual(len(fabric.cancels), 1)
        consumed = loads(fixture_dispatch({
            "action": "consume",
            "idempotency_key": "child-impl-0001",
            "parent_id": PARENT,
        }, bridge))
        self.assertEqual(consumed["state"], "CANCELLED")
        self.assertEqual(fabric.results, [])
        self.assertEqual(cursor.submits, [])

    def test_unknown_effect_is_sticky_and_not_replayed(self):
        detail = "reply lost after launch rc=unknown"
        fabric = FakeCarrier()
        fabric.submit_result = {"state": "EFFECT_UNKNOWN", "detail": detail}
        bridge, admission, fabric, cursor = bridge_for(fabric=fabric)
        first = loads(fixture_dispatch(request(), bridge))
        self.assertEqual(first["state"], "UNKNOWN")
        self.assertEqual(first["detail"], detail)
        second = loads(fixture_dispatch(request(carrier="cursor_cloud"), bridge))
        self.assertEqual(second["state"], "UNKNOWN")
        self.assertEqual(second["detail"], detail)
        self.assertTrue(second["deduped"])
        replay = loads(fixture_dispatch(request(
            idempotency_key="child-impl-0099",
            carrier="cursor_cloud",
            replay_of="child-impl-0001",
        ), bridge))
        self.assertEqual(replay["state"], "UNKNOWN")
        self.assertEqual(replay["detail"], detail)
        renamed = loads(fixture_dispatch(request(
            idempotency_key="child-impl-0007",
            carrier="cursor_cloud",
        ), bridge))
        self.assertEqual(renamed["state"], "UNKNOWN")
        self.assertEqual(renamed["idempotency_key"], "child-impl-0001")
        self.assertEqual(renamed["detail"], detail)
        self.assertEqual(len(fabric.submits), 1)
        self.assertEqual(cursor.submits, [])
        self.assertEqual(len(admission.calls), 1)
        status = loads(fixture_dispatch({
            "action": "status",
            "idempotency_key": "child-impl-0001",
        }, bridge))
        self.assertEqual(status["state"], "UNKNOWN")
        self.assertEqual(fabric.statuses, [])

        broken = FakeCarrier()
        broken.submit_error = RuntimeError("connection reset mid-write")
        other, _admission, broken, other_cursor = bridge_for(fabric=broken)
        failed = loads(fixture_dispatch(request(idempotency_key="child-impl-0003"), other))
        self.assertEqual(failed["state"], "UNKNOWN")
        self.assertIn("connection reset mid-write", failed["detail"])
        loads(fixture_dispatch(request(idempotency_key="child-impl-0003", carrier="cursor_cloud"), other))
        self.assertEqual(len(broken.submits), 1)
        self.assertEqual(other_cursor.submits, [])

    def test_refused_submission_is_verbatim_and_not_rehomed(self):
        admission = FakeAdmission(outcome="REFUSED", reason=REFUSAL)
        admission.extra = {"fallback_carrier": "cursor_cloud"}
        bridge, admission, fabric, cursor = bridge_for(admission=admission)
        refused = loads(fixture_dispatch(request(), bridge))
        self.assertEqual(refused["state"], "REFUSED")
        self.assertEqual(refused["reason"], REFUSAL)
        retry = loads(fixture_dispatch(request(
            idempotency_key="child-impl-0099",
            carrier="cursor_cloud",
            replay_of="child-impl-0001",
        ), bridge))
        self.assertEqual(retry["reason"], REFUSAL)
        same_task = loads(fixture_dispatch(request(
            idempotency_key="child-impl-0008",
            carrier="cursor_cloud",
        ), bridge))
        self.assertEqual(same_task["reason"], REFUSAL)
        self.assertEqual(same_task["carrier"], "fabric")
        self.assertEqual(fabric.submits, [])
        self.assertEqual(cursor.submits, [])
        self.assertEqual(len(admission.calls), 1)

        carrier_admission = FakeAdmission()
        carrier = FakeCarrier()
        carrier.submit_result = {
            "state": "REFUSED",
            "reason": "ECONOMIC_POLICY_REFUSED: pool closed",
        }
        second, _admission, carrier, other_cursor = bridge_for(
            admission=carrier_admission,
            fabric=carrier,
        )
        viewed = loads(fixture_dispatch(request(idempotency_key="child-impl-0004"), second))
        self.assertEqual(viewed["reason"], "ECONOMIC_POLICY_REFUSED: pool closed")
        loads(fixture_dispatch(request(
            idempotency_key="child-impl-0005",
            carrier="cursor_cloud",
            objective="Repair the bounded parser test in the named file.",
        ), second))
        self.assertEqual(len(carrier.submits), 1)
        self.assertEqual(other_cursor.submits, [])

    def test_selected_child_branch_is_closed_and_unbound_by_default(self):
        from integrations.hermes_delegate.executive import (
            clear_selected_child_composition,
            selected_child_composition,
        )

        clear_selected_child_composition()
        self.assertIsNone(selected_child_composition())
        command = "coo-cycle:JOB-001:dispatch:JOB-003:attempt:1"

        # The default process has no trusted-host composition, so the branch
        # refuses instead of constructing a live bridge.
        for action in ("selected_child_submit", "selected_child_status"):
            refused = loads(dispatch({"action": action, "command": command}))
            self.assertEqual(refused["state"], "REFUSED")
            self.assertEqual(refused["reason"], "EXECUTIVE_SELECTED_CHILD_NOT_BOUND")
            self.assertFalse(refused["live_submit"])

        # A request key never selects or replaces a canonical Attempt.
        keyed = loads(dispatch({
            "action": "selected_child_submit", "command": command,
            "idempotency_key": "child-impl-0001",
        }))
        self.assertEqual(keyed["state"], "REFUSED")
        self.assertEqual(keyed["reason"], "UNKNOWN_FIELD")

        # The model cannot name a Job, root, carrier, objective or acceptance.
        for extra in (
            {"job_id": "JOB-003"}, {"root_id": "JOB-001"},
            {"carrier": "fabric"}, {"objective": "choose another child"},
            {"acceptance": "choose another child"},
        ):
            refused = loads(dispatch({
                "action": "selected_child_submit", "command": command, **extra,
            }))
            self.assertEqual(refused["state"], "REFUSED")
            self.assertEqual(refused["reason"], "UNKNOWN_FIELD")

        # A malformed command reference is not a canonical command.
        for bad in ("", "JOB-003", "coo-cycle:JOB-001:dispatch:JOB-003",
                    "coo-cycle:JOB-001:dispatch:JOB-003:attempt:0",
                    "coo-cycle:JOB-001:dispatch:JOB-003:attempt:x"):
            refused = loads(dispatch({
                "action": "selected_child_status", "command": bad,
            }))
            self.assertEqual(refused["state"], "REFUSED")
            self.assertEqual(refused["reason"], "COMMAND_INVALID")

        # Owner operations and generic cancel stay outside this branch.
        for action in ("review", "consume"):
            refused = loads(dispatch({
                "action": action, "command": command,
            }))
            self.assertEqual(refused["state"], "REFUSED")
            self.assertEqual(refused["reason"], "REVIEW_AND_CONSUME_OWNER_ONLY")
        cancelled = loads(dispatch({
            "action": "cancel", "command": command,
        }))
        self.assertEqual(cancelled["state"], "REFUSED")
        self.assertEqual(cancelled["reason"], "UNKNOWN_FIELD")

        # The inert bridge path is unchanged by the selected-child branch.
        bridge, _admission, fabric, _cursor = bridge_for()
        self.assertEqual(loads(dispatch(request(), bridge))["state"], "SUBMITTED")
        self.assertEqual(len(fabric.submits), 1)

        # The handler answers one JSON object and never raises, whatever the
        # model puts in the action field.
        for bad_action in ([], {}, 3, None, True):
            answered = loads(dispatch({"action": bad_action}))
            self.assertEqual(answered["state"], "REFUSED")
            self.assertFalse(answered["live_submit"])

    def test_builtin_delegation_stays_disabled_and_only_one_tool_exists(self):
        policy = load_policy()
        self.assertIn("delegation", policy["disabled_toolsets"])
        self.assertEqual(policy["enabled_tools"], ["mmx_delegate"])
        self.assertEqual(policy["enabled_toolsets"], ["mmx_delegate"])
        self.assertNotIn("delegate_task", policy["enabled_tools"])
        self.assertFalse(policy["live_submit"])
        self.assertEqual(policy["hermes_pin"], "1c0cd667746d3395fe9e1b6c74f8f85952486f18")
        tools = registered_tools(policy)
        self.assertEqual(len(tools), 1)
        self.assertEqual(tools[0]["name"], "mmx_delegate")
        self.assertEqual(tools[0]["toolset"], "mmx_delegate")
        self.assertNotEqual(tools[0]["toolset"], "delegation")
        self.assertEqual(tools[0]["schema"]["name"], "mmx_delegate")
        self.assertNotEqual(TOOL_REGISTRATION["name"], "delegate_task")

        preflight_path = REPO / "integrations" / "hermes_qualification" / "preflight.py"
        spec = importlib.util.spec_from_file_location("hermes_qualification_preflight", preflight_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(REQUIRED_DISABLED_TOOLSETS, module.REQUIRED_DISABLED)

        for name in ("mmsecretary", "mmmeta"):
            text = (REPO / "integrations" / "hermes_qualification" / "profiles" / name / "config.yaml").read_text(encoding="utf-8")
            self.assertIn("\n    - delegation\n", text)
            self.assertIn("\ntoolsets:\n  - clarify\n", text)
            self.assertNotIn("mmx_delegate", text)
            self.assertNotIn("delegate_task", text)

        opened = load_policy()
        opened["disabled_toolsets"] = [item for item in opened["disabled_toolsets"] if item != "delegation"]
        bridge, admission, fabric, _cursor = bridge_for(policy=opened)
        blocked = loads(fixture_dispatch(request(), bridge))
        self.assertEqual(blocked["reason"], "BUILTIN_DELEGATION_ENABLED")
        self.assertEqual(admission.calls, [])
        self.assertEqual(fabric.submits, [])

        many = load_policy()
        many["enabled_tools"] = ["mmx_delegate", "delegate_task"]
        bridge, admission, fabric, _cursor = bridge_for(policy=many)
        blocked = loads(fixture_dispatch(request(), bridge))
        self.assertEqual(blocked["reason"], "MULTIPLE_DELEGATION_TOOLS")
        self.assertEqual(admission.calls, [])
        self.assertEqual(fabric.submits, [])

    def test_caller_cannot_self_admit(self):
        inert = loads(fixture_dispatch(request(), Bridge()))
        self.assertEqual(inert["state"], "REFUSED")
        self.assertEqual(inert["reason"], NOT_BOUND_REASON)
        self.assertFalse(inert["live_submit"])

        admission = FakeAdmission(outcome="REFUSED", reason=REFUSAL)
        bridge, admission, fabric, cursor = bridge_for(admission=admission)
        forged = request(outcome="ADMITTED", state="CONSUMED")
        blocked = loads(fixture_dispatch(forged, bridge))
        self.assertEqual(blocked["reason"], "UNKNOWN_FIELD")
        self.assertEqual(admission.calls, [])
        self.assertEqual(fabric.submits, [])
        self.assertEqual(cursor.submits, [])

        ignored = bridge.submit(request(outcome="ADMITTED", state="CONSUMED"))
        self.assertEqual(ignored["state"], "REFUSED")
        self.assertEqual(ignored["reason"], REFUSAL)
        self.assertEqual(len(admission.calls), 1)

    def test_three_child_kinds_use_the_one_tool(self):
        bridge, _admission, fabric, cursor = bridge_for()
        cases = (
            ("implementation", "fabric", "child-impl-0010", "fix_build", "C1_ROUTINE_BOUNDED", "Implement the named fence."),
            ("watcher", "fabric", "child-watch-0011", "census", "C0_MECHANICAL", "Watch the named receipt and report once."),
            ("computer_use", "cursor_cloud", "child-cua-000012", "mechanical", "C1_ROUTINE_BOUNDED", "Open the named screen and stop."),
        )
        for kind, carrier, key, task_class, complexity, objective in cases:
            with self.subTest(kind=kind):
                viewed = loads(fixture_dispatch(request(
                    idempotency_key=key,
                    child_kind=kind,
                    carrier=carrier,
                    task_class=task_class,
                    task_complexity=complexity,
                    objective=objective,
                ), bridge))
                self.assertEqual(viewed["state"], "SUBMITTED")
                self.assertEqual(viewed["child_kind"], kind)
                self.assertEqual(viewed["carrier"], carrier)
        self.assertEqual(len(fabric.submits), 2)
        self.assertEqual(len(cursor.submits), 1)
        cloud = cursor.submits[0]["request"]
        self.assertFalse(cloud["live_submit"])
        self.assertEqual(cloud["child_kind"], "computer_use")
        self.assertNotIn("api_key", cloud)
        self.assertNotIn("token", cloud)
        self.assertEqual(len(registered_tools()), 1)

    def test_handoff_rejects_unadmitted_model_and_forbidden_phrases(self):
        submission = {
            "idempotency_key": "child-impl-0001",
            "carrier": "fabric",
            "child_kind": "implementation",
            "objective": "Repair the bounded parser test in the named file.",
        }
        with self.assertRaises(HandoffError) as caught:
            render_child_handoff(
                workstream="WS:HERMES-DELEGATE-WP4",
                session="sol/hermes-delegate-wp4-20261025",
                model="grok",
                submission=submission,
                result_sha256="a" * 64,
            )
        self.assertEqual(caught.exception.reason, "HANDOFF_MODEL_NOT_ADMITTED")
        submission["objective"] = "Please see above and continue."
        with self.assertRaises(HandoffError) as caught:
            render_child_handoff(
                workstream="WS:HERMES-DELEGATE-WP4",
                session="sol/hermes-delegate-wp4-20261025",
                model="sol",
                submission=submission,
                result_sha256="a" * 64,
            )
        self.assertEqual(caught.exception.reason, "HANDOFF_PHRASE_FORBIDDEN")

    def test_package_has_no_live_transport(self):
        banned = {"subprocess", "urllib", "socket", "requests", "http", "fabric_task"}
        # Only the explicit host composition may import these existing Runtime,
        # Service and current-principal owners. Bridge/tool/package stays unbound;
        # the transport ban and exact per-module import set remain enforced.
        # The terminal-return owner contributes only the pure, closed result
        # capsule validator; it creates no transport or result lifecycle.
        owner_reads = {
            "control_plane.executive_runtime",
            "control_plane.executive_delegation_identity",
            "control_plane.executive_service",
            "control_plane.executive_terminal_return",
            "control_plane.coo_principal_host",
            "control_plane.coo_principal_envelope",
        }
        for path in PACKAGE.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            imported: set[str] = set()
            owner_imports: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(alias.name.split(".")[0] for alias in node.names)
                    owner_imports.update(alias.name for alias in node.names
                                         if alias.name.split(".")[0] == "control_plane")
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    imported.add(module.split(".")[0])
                    if module == "control_plane":
                        owner_imports.update(f"{module}.{alias.name}" for alias in node.names)
                    elif module.startswith("control_plane."):
                        owner_imports.add(module)
            self.assertFalse(banned & imported, f"{path.name} imports {banned & imported}")
            self.assertEqual(owner_imports, owner_reads if path.name == "executive.py" else set(),
                             f"{path.name} imports an unbound Executive owner")


def _review(key, reviewer, sha, verdict="accept"):
        return {
            "action": "review",
            "idempotency_key": key,
            "reviewer_id": reviewer,
            "verdict": verdict,
            "result_sha256": sha,
        }


class DelegateEdgePaths(unittest.TestCase):
    def test_admission_exception_latches_unknown_without_carrier(self):
        admission = FakeAdmission()
        admission.error = RuntimeError("admission store unavailable")
        bridge, admission, fabric, cursor = bridge_for(admission=admission)
        failed = loads(fixture_dispatch(request(), bridge))
        self.assertEqual(failed["state"], "UNKNOWN")
        self.assertEqual(failed["detail"], "RuntimeError: admission store unavailable")
        self.assertIsNone(failed["reason"])
        again = loads(fixture_dispatch(request(carrier="cursor_cloud"), bridge))
        self.assertEqual(again["state"], "UNKNOWN")
        self.assertTrue(again["deduped"])
        self.assertEqual(len(admission.calls), 1)
        self.assertEqual(fabric.submits, [])
        self.assertEqual(cursor.submits, [])

    def test_carrier_mismatch_is_refused_without_either_submit(self):
        admission = FakeAdmission()
        admission.decision = {
            "outcome": "ADMITTED",
            "reason": "admitted for cursor_cloud only",
            "carrier": "cursor_cloud",
            "idempotency_key": "child-impl-0001",
        }
        bridge, admission, fabric, cursor = bridge_for(admission=admission)
        refused = loads(fixture_dispatch(request(), bridge))
        self.assertEqual(refused["state"], "REFUSED")
        self.assertEqual(refused["reason"], "admitted for cursor_cloud only")
        self.assertEqual(refused["carrier"], "fabric")
        retry = loads(fixture_dispatch(request(carrier="cursor_cloud"), bridge))
        self.assertEqual(retry["state"], "REFUSED")
        self.assertEqual(retry["reason"], "admitted for cursor_cloud only")
        self.assertTrue(retry["deduped"])
        self.assertEqual(len(admission.calls), 1)
        self.assertEqual(fabric.submits, [])
        self.assertEqual(cursor.submits, [])

        empty = FakeAdmission()
        empty.decision = {
            "outcome": "ADMITTED",
            "reason": "",
            "carrier": "cursor_cloud",
            "idempotency_key": "child-impl-0002",
        }
        other, _empty, other_fabric, other_cursor = bridge_for(admission=empty)
        viewed = loads(fixture_dispatch(request(idempotency_key="child-impl-0002"), other))
        self.assertEqual(viewed["state"], "REFUSED")
        self.assertEqual(viewed["reason"], "ADMISSION_CARRIER_MISMATCH")
        self.assertEqual(other_fabric.submits, [])
        self.assertEqual(other_cursor.submits, [])

    def test_non_string_refusal_is_not_coerced(self):
        admission = FakeAdmission()
        admission.decision = {
            "outcome": "REFUSED",
            "reason": None,
            "carrier": "fabric",
            "idempotency_key": "child-impl-0001",
        }
        bridge, admission, fabric, cursor = bridge_for(admission=admission)
        refused = loads(fixture_dispatch(request(), bridge))
        self.assertEqual(refused["state"], "UNKNOWN")
        self.assertEqual(refused["detail"], "ADMISSION_REFUSAL_UNREADABLE")
        self.assertIsNone(refused["reason"])
        self.assertEqual(fabric.submits, [])
        self.assertEqual(cursor.submits, [])
        self.assertEqual(len(admission.calls), 1)

        carrier = FakeCarrier()
        carrier.submit_result = {"state": "REFUSED", "reason": ["ECONOMIC_POLICY_REFUSED: pool closed"]}
        second, _admission, carrier, other_cursor = bridge_for(fabric=carrier)
        viewed = loads(fixture_dispatch(request(idempotency_key="child-impl-0004"), second))
        self.assertEqual(viewed["state"], "UNKNOWN")
        self.assertEqual(viewed["detail"], "CARRIER_REFUSAL_UNREADABLE")
        self.assertIsNone(viewed["reason"])
        loads(fixture_dispatch(request(
            idempotency_key="child-impl-0004",
            carrier="cursor_cloud",
        ), second))
        self.assertEqual(len(carrier.submits), 1)
        self.assertEqual(other_cursor.submits, [])

    def test_run_id_mismatch_latches_unknown(self):
        fabric = FakeCarrier()
        fabric.submit_result = {"state": "SUBMITTED", "run_id": "other-run-0002"}
        bridge, _admission, fabric, cursor = bridge_for(fabric=fabric)
        mismatched = loads(fixture_dispatch(request(), bridge))
        self.assertEqual(mismatched["state"], "UNKNOWN")
        self.assertEqual(mismatched["detail"], "CARRIER_RUN_ID_MISMATCH")
        self.assertEqual(mismatched["run_id"], "child-impl-0001")
        again = loads(fixture_dispatch(request(carrier="cursor_cloud"), bridge))
        self.assertEqual(again["state"], "UNKNOWN")
        self.assertTrue(again["deduped"])
        self.assertEqual(len(fabric.submits), 1)
        self.assertEqual(cursor.submits, [])

    def test_cancel_and_status_after_unknown_do_not_call_carrier(self):
        fabric = FakeCarrier()
        fabric.submit_result = {"state": "EFFECT_UNKNOWN", "detail": "reply lost after launch"}
        bridge, _admission, fabric, cursor = bridge_for(fabric=fabric)
        loads(fixture_dispatch(request(), bridge))
        cancelled = loads(fixture_dispatch({"action": "cancel", "idempotency_key": "child-impl-0001"}, bridge))
        status = loads(fixture_dispatch({"action": "status", "idempotency_key": "child-impl-0001"}, bridge))
        self.assertEqual(cancelled["state"], "UNKNOWN")
        self.assertEqual(cancelled["detail"], "reply lost after launch")
        self.assertFalse(cancelled["deduped"])
        self.assertEqual(status["state"], "UNKNOWN")
        self.assertEqual(fabric.cancels, [])
        self.assertEqual(fabric.statuses, [])
        self.assertEqual(cursor.cancels, [])
        self.assertEqual(cursor.submits, [])

    def test_review_by_root_or_child_id_is_rejected(self):
        bridge, _admission, fabric, _cursor = bridge_for()
        loads(fixture_dispatch(request(), bridge))
        sha = hashlib.sha256(fabric.body).hexdigest()
        for reviewer in (ROOT, "child-impl-0001"):
            with self.subTest(reviewer=reviewer):
                denied = loads(fixture_dispatch(_review("child-impl-0001", reviewer, sha), bridge))
                self.assertEqual(denied["state"], "SELF_APPROVAL_FORBIDDEN")
                self.assertEqual(denied["reason"], "SELF_APPROVAL_FORBIDDEN")
        self.assertEqual(fabric.results, [])
        self.assertEqual(fabric.statuses, [])
        accepted = loads(fixture_dispatch(_review("child-impl-0001", REVIEWER, sha), bridge))
        self.assertEqual(accepted["state"], "REVIEWED")
        self.assertEqual(len(fabric.statuses), 1)

    def test_reject_verdict_blocks_consume(self):
        bridge, _admission, fabric, _cursor = bridge_for()
        loads(fixture_dispatch(request(), bridge))
        sha = hashlib.sha256(fabric.body).hexdigest()
        rejected = loads(fixture_dispatch(_review("child-impl-0001", REVIEWER, sha, verdict="reject"), bridge))
        self.assertEqual(rejected["state"], "REVIEW_REJECTED")
        consumed = loads(fixture_dispatch({
            "action": "consume",
            "idempotency_key": "child-impl-0001",
            "parent_id": PARENT,
        }, bridge))
        self.assertEqual(consumed["state"], "REVIEW_REJECTED")
        self.assertEqual(consumed["reason"], "REVIEW_REJECTED")
        self.assertFalse(consumed["consumed"])
        replacement = loads(fixture_dispatch(_review("child-impl-0001", "another-reviewer-02", sha), bridge))
        self.assertEqual(replacement["state"], "REVIEW_REJECTED")
        self.assertTrue(replacement["deduped"])
        self.assertEqual(fabric.results, [])

    def test_parent_mismatch_does_not_consume(self):
        bridge, _admission, fabric, _cursor = bridge_for()
        loads(fixture_dispatch(request(), bridge))
        sha = hashlib.sha256(fabric.body).hexdigest()
        loads(fixture_dispatch(_review("child-impl-0001", REVIEWER, sha), bridge))
        mismatched = loads(fixture_dispatch({
            "action": "consume",
            "idempotency_key": "child-impl-0001",
            "parent_id": "other-parent-02",
        }, bridge))
        self.assertEqual(mismatched["state"], "REFUSED")
        self.assertEqual(mismatched["reason"], "PARENT_MISMATCH")
        self.assertEqual(fabric.results, [])
        status = loads(fixture_dispatch({"action": "status", "idempotency_key": "child-impl-0001"}, bridge))
        self.assertEqual(status["state"], "REVIEWED")
        consumed = loads(fixture_dispatch({
            "action": "consume",
            "idempotency_key": "child-impl-0001",
            "parent_id": PARENT,
        }, bridge))
        self.assertEqual(consumed["state"], "CONSUMED")
        self.assertEqual(len(fabric.results), 1)

    def test_digest_mismatch_blocks_acceptance(self):
        bridge, _admission, fabric, _cursor = bridge_for()
        loads(fixture_dispatch(request(), bridge))
        wrong = "ab" * 32
        denied = loads(fixture_dispatch(_review("child-impl-0001", REVIEWER, wrong), bridge))
        self.assertEqual(denied["state"], "REFUSED")
        self.assertEqual(denied["reason"], "REVIEW_DIGEST_MISMATCH")
        self.assertEqual(fabric.results, [])
        status = loads(fixture_dispatch({"action": "status", "idempotency_key": "child-impl-0001"}, bridge))
        self.assertEqual(status["state"], "TERMINAL")

        other, _admission, other_fabric, _cursor = bridge_for()
        loads(fixture_dispatch(request(idempotency_key="child-impl-0006"), other))
        sha = hashlib.sha256(other_fabric.body).hexdigest()
        reviewed = loads(fixture_dispatch(_review("child-impl-0006", REVIEWER, sha), other))
        self.assertEqual(reviewed["state"], "REVIEWED")
        other_fabric.body = b"tampered result\n"
        consumed = loads(fixture_dispatch({
            "action": "consume",
            "idempotency_key": "child-impl-0006",
            "parent_id": PARENT,
        }, other))
        self.assertEqual(consumed["state"], "RESULT_DIGEST_MISMATCH")
        self.assertEqual(consumed["detail"], "RESULT_DIGEST_MISMATCH")
        self.assertFalse(consumed["consumed"])
        again = loads(fixture_dispatch({
            "action": "consume",
            "idempotency_key": "child-impl-0006",
            "parent_id": PARENT,
        }, other))
        self.assertEqual(again["state"], "RESULT_DIGEST_MISMATCH")
        self.assertEqual(len(other_fabric.results), 1)

    def test_frontier_complexity_is_refused_before_admission(self):
        bridge, admission, fabric, cursor = bridge_for()
        refused = loads(fixture_dispatch(request(task_complexity="C3_FRONTIER_JUDGMENT"), bridge))
        self.assertEqual(refused["state"], "REFUSED")
        self.assertEqual(refused["reason"], "TASK_COMPLEXITY_INVALID")
        self.assertEqual(admission.calls, [])
        self.assertEqual(fabric.submits, [])
        self.assertEqual(cursor.submits, [])

    def test_uppercase_sha_is_refused(self):
        bridge, _admission, fabric, _cursor = bridge_for()
        loads(fixture_dispatch(request(idempotency_key="child-impl-0091"), bridge))
        sha = hashlib.sha256(fabric.body).hexdigest().upper()
        denied = loads(fixture_dispatch(_review("child-impl-0091", REVIEWER, sha), bridge))
        self.assertEqual(denied["state"], "REFUSED")
        self.assertEqual(denied["reason"], "REVIEW_INVALID")

    def test_live_submit_policy_is_refused_before_admission(self):
        policy = load_policy()
        policy["live_submit"] = True
        bridge, admission, fabric, cursor = bridge_for(policy=policy)
        refused = loads(fixture_dispatch(request(idempotency_key="child-impl-0092"), bridge))
        self.assertEqual(refused["state"], "REFUSED")
        self.assertEqual(refused["reason"], "DELEGATION_POLICY_INVALID")
        self.assertEqual(admission.calls, [])
        self.assertEqual(fabric.submits, [])
        self.assertEqual(cursor.submits, [])

    def test_absent_replay_of_submits_a_new_child(self):
        body = request(idempotency_key="child-impl-0093")
        self.assertNotIn("replay_of", body)
        bridge, admission, fabric, _cursor = bridge_for()
        submitted = loads(fixture_dispatch(body, bridge))
        self.assertEqual(submitted["state"], "SUBMITTED")
        self.assertEqual(len(fabric.submits), 1)
        self.assertIsNone(admission.calls[0].get("replay_of"))

    def test_secret_shaped_objective_is_not_stored(self):
        bridge, admission, _fabric, _cursor = bridge_for()
        refused = loads(fixture_dispatch(
            request(idempotency_key="child-impl-0094", objective="api_key=sk-should-not-store"),
            bridge,
        ))
        self.assertEqual(refused["state"], "REFUSED")
        self.assertEqual(refused["reason"], "SECRET_MATERIAL_REFUSED")
        self.assertEqual(admission.calls, [])
        missing = loads(fixture_dispatch({"action": "status", "idempotency_key": "child-impl-0094"}, bridge))
        self.assertEqual(missing["state"], "NOT_FOUND")

    def test_admitted_unbound_carrier_latches_unknown(self):
        bridge = Bridge(FakeAdmission())
        refused = loads(fixture_dispatch(request(idempotency_key="child-impl-0095"), bridge))
        self.assertEqual(refused["state"], "UNKNOWN")
        self.assertIn("CarrierNotBound", refused["detail"])
        again = loads(fixture_dispatch(
            request(idempotency_key="child-impl-0095", carrier="cursor_cloud"),
            bridge,
        ))
        self.assertEqual(again["state"], "UNKNOWN")
        self.assertTrue(again["deduped"])


if __name__ == "__main__":
    unittest.main()
