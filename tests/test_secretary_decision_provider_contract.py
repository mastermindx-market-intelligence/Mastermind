from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

import pytest

MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "integrations"
    / "mastermind_secretary_mcp"
    / "decision_provider_contract.py"
)

contract = None
if MODULE_PATH.is_file():
    spec = importlib.util.spec_from_file_location("secretary_decision_provider_contract", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    contract = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = contract
    spec.loader.exec_module(contract)


def test_secretary_decision_contract_is_available() -> None:
    assert callable(getattr(contract, "validate_secretary_recommendation", None))


def snapshot(**overrides):
    value = {
        "schema": "mastermind.secretary_decision_snapshot/v1",
        "operation_key": "mastermind-os-frontier-company-convergence-20260925-sol-001",
        "responsibility_ref": "WS:CHAIRMAN-CONTROL-ROOM",
        "trigger": "TURN_COMPLETED",
        "mission_state": "MORE_WORK",
        "turn_state": "TERMINAL",
        "effect_state": "CLEAR",
        "context_state": "HEALTHY",
        "checkpoint_state": "NONE",
        "binding_state": "EXACT_CURRENT",
        "capability_state": "SERVICEABLE",
        "human_gate": "NONE",
        "current_mode": "PRO",
        "mode_recommendation": "NONE",
        "outstanding_children": 0,
        "ready_returns": 0,
        "fanout_candidates": [],
        "source_refs": [
            "github:mastermindx-market-intelligence/Mastermind#989@c50903d5",
            "runtime:binding-current",
        ],
        "observed_at_ms": 10_000,
        "expires_at_ms": 50_000,
    }
    value.update(overrides)
    return value


def recommendation(
    action="CONTINUE_CURRENT_SESSION",
    reason_code="MORE_WORK",
    *,
    requested_mode=None,
    fanout_candidate_ids=None,
    rationale="The current exact CEO responsibility has more bounded work.",
):
    return {
        "schema": "mastermind.secretary_decision_recommendation/v1",
        "action": action,
        "reason_code": reason_code,
        "requested_mode": requested_mode,
        "fanout_candidate_ids": [] if fanout_candidate_ids is None else fanout_candidate_ids,
        "rationale": rationale,
    }


if contract is not None:
    def validate(snap=None, rec=None, now_ms=20_000):
        return contract.validate_secretary_recommendation(
            snapshot() if snap is None else snap,
            recommendation() if rec is None else rec,
            now_ms=now_ms,
        )


    def assert_safe(receipt) -> None:
        assert receipt.execution_authorized is False
        assert receipt.lifecycle_mutation_performed is False
        assert receipt.browser_mutation_performed is False
        assert receipt.requires_owner_admission is True
        assert receipt.schema_version == "mastermind.secretary_decision_validation/v1"


    def test_accepts_terminal_more_work_continue_without_granting_authority() -> None:
        receipt = validate()
        assert receipt.status == "ACCEPTED"
        assert receipt.action == "CONTINUE_CURRENT_SESSION"
        assert receipt.reason_code == "MORE_WORK"
        assert receipt.requested_mode is None
        assert receipt.fanout_candidate_ids == ()
        assert len(receipt.snapshot_digest) == 64
        assert len(receipt.recommendation_digest) == 64
        assert len(receipt.rationale_digest) == 64
        assert_safe(receipt)


    def test_effect_unknown_forces_hold_and_refuses_continue() -> None:
        snap = snapshot(effect_state="EFFECT_UNKNOWN")
        refused = validate(snap, recommendation())
        assert refused.status == "REFUSED"
        assert refused.refusal_code == "EFFECT_HOLD_REQUIRED"
        assert_safe(refused)

        accepted = validate(
            snap,
            recommendation(
                "HOLD_EFFECT_UNKNOWN",
                "EFFECT_UNCERTAIN",
                rationale="The original exact effect must be reconciled before another action.",
            ),
        )
        assert accepted.status == "ACCEPTED"
        assert accepted.action == "HOLD_EFFECT_UNKNOWN"
        assert_safe(accepted)


    def test_human_gate_forces_escalation_after_effect_is_clear() -> None:
        snap = snapshot(human_gate="REQUIRED", trigger="HUMAN_GATE")
        refused = validate(snap, recommendation())
        assert refused.refusal_code == "HUMAN_ESCALATION_REQUIRED"

        accepted = validate(
            snap,
            recommendation(
                "ESCALATE_HUMAN",
                "HUMAN_GATE",
                rationale="A current human control is the only remaining admissible edge.",
            ),
        )
        assert accepted.status == "ACCEPTED"
        assert accepted.action == "ESCALATE_HUMAN"


    def test_owner_proven_completion_forces_stop_complete() -> None:
        snap = snapshot(mission_state="COMPLETE")
        refused = validate(snap, recommendation())
        assert refused.refusal_code == "MISSION_STOP_REQUIRED"

        accepted = validate(
            snap,
            recommendation(
                "STOP_COMPLETE",
                "MISSION_COMPLETE",
                rationale="Canonical owners report the commissioned mission complete.",
            ),
        )
        assert accepted.status == "ACCEPTED"
        assert accepted.action == "STOP_COMPLETE"


    def test_switch_mode_requires_matching_session_recommendation_and_different_mode() -> None:
        snap = snapshot(
            current_mode="PRO",
            mode_recommendation="EXTRA_HIGH",
            capability_state="REPROBE_REQUIRED",
        )
        accepted = validate(
            snap,
            recommendation(
                "SWITCH_MODE_THEN_CONTINUE",
                "MODE_CHANGE_RECOMMENDED",
                requested_mode="EXTRA_HIGH",
                rationale="The CEO session requested Extra High before the next iterative tool wave.",
            ),
        )
        assert accepted.status == "ACCEPTED"
        assert accepted.requested_mode == "EXTRA_HIGH"
        assert_safe(accepted)

        mismatch = validate(
            snap,
            recommendation(
                "SWITCH_MODE_THEN_CONTINUE",
                "MODE_CHANGE_RECOMMENDED",
                requested_mode="PRO",
                rationale="Try the other mode.",
            ),
        )
        assert mismatch.refusal_code == "MODE_RECOMMENDATION_MISMATCH"

        same = validate(
            snapshot(current_mode="EXTRA_HIGH", mode_recommendation="EXTRA_HIGH"),
            recommendation(
                "SWITCH_MODE_THEN_CONTINUE",
                "MODE_CHANGE_RECOMMENDED",
                requested_mode="EXTRA_HIGH",
                rationale="No-op mode switch should not be admitted.",
            ),
        )
        assert same.refusal_code == "MODE_ALREADY_SELECTED"


    def test_continue_refuses_when_session_has_unconsumed_mode_recommendation() -> None:
        receipt = validate(snapshot(mode_recommendation="EXTRA_HIGH", current_mode="PRO"))
        assert receipt.refusal_code == "MODE_CHANGE_PENDING"


    @pytest.mark.parametrize("capability", ["DENIED", "UNKNOWN"])
    def test_continue_and_switch_cannot_evade_capability_denial_or_unknown(capability: str) -> None:
        cont = validate(snapshot(capability_state=capability))
        assert cont.refusal_code == "CAPABILITY_NOT_SERVICEABLE"

        switch = validate(
            snapshot(capability_state=capability, mode_recommendation="EXTRA_HIGH"),
            recommendation(
                "SWITCH_MODE_THEN_CONTINUE",
                "MODE_CHANGE_RECOMMENDED",
                requested_mode="EXTRA_HIGH",
                rationale="A mode change never clears a denial or unknown capability state.",
            ),
        )
        assert switch.refusal_code == "CAPABILITY_NOT_SERVICEABLE"


    @pytest.mark.parametrize("binding_state", ["STALE", "UNKNOWN"])
    def test_continue_and_switch_require_exact_current_binding(binding_state: str) -> None:
        cont = validate(snapshot(binding_state=binding_state))
        assert cont.refusal_code == "BINDING_NOT_EXACT_CURRENT"

        switch = validate(
            snapshot(binding_state=binding_state, mode_recommendation="EXTRA_HIGH"),
            recommendation(
                "SWITCH_MODE_THEN_CONTINUE",
                "MODE_CHANGE_RECOMMENDED",
                requested_mode="EXTRA_HIGH",
                rationale="Wrong or unknown exact session identity cannot support a mode transition.",
            ),
        )
        assert switch.refusal_code == "BINDING_NOT_EXACT_CURRENT"


    def test_checkpoint_then_rotation_order_is_explicit() -> None:
        due = snapshot(context_state="ROTATION_REQUIRED", checkpoint_state="NONE", trigger="CONTEXT_HEALTH")
        checkpoint = validate(
            due,
            recommendation(
                "REQUEST_CHECKPOINT",
                "CHECKPOINT_REQUIRED",
                rationale="Context rotation is required but no ready checkpoint exists yet.",
            ),
        )
        assert checkpoint.status == "ACCEPTED"

        premature = validate(
            due,
            recommendation(
                "ROTATE_TO_SUCCESSOR",
                "ROTATION_REQUIRED",
                rationale="Do not rotate before the existing checkpoint owner reports READY.",
            ),
        )
        assert premature.refusal_code == "CHECKPOINT_NOT_READY"

        ready = snapshot(context_state="ROTATION_REQUIRED", checkpoint_state="READY", trigger="CONTEXT_HEALTH")
        rotate = validate(
            ready,
            recommendation(
                "ROTATE_TO_SUCCESSOR",
                "ROTATION_REQUIRED",
                rationale="The bounded checkpoint is ready and the current context requires rotation.",
            ),
        )
        assert rotate.status == "ACCEPTED"

        stale_checkpoint = validate(
            ready,
            recommendation(
                "REQUEST_CHECKPOINT",
                "CHECKPOINT_REQUIRED",
                rationale="Do not request a second checkpoint when one is already ready.",
            ),
        )
        assert stale_checkpoint.refusal_code == "CHECKPOINT_ALREADY_READY"


    def test_fanout_can_only_select_supplied_candidates_and_requires_no_outstanding_children() -> None:
        snap = snapshot(
            trigger="FANOUT_READY",
            fanout_candidates=["lane-research", "lane-browser", "lane-review"],
        )
        accepted = validate(
            snap,
            recommendation(
                "FANOUT",
                "INDEPENDENT_WORK_READY",
                fanout_candidate_ids=["lane-research", "lane-review"],
                rationale="Two supplied workstreams are independent and bounded.",
            ),
        )
        assert accepted.status == "ACCEPTED"
        assert accepted.fanout_candidate_ids == ("lane-research", "lane-review")

        unknown = validate(
            snap,
            recommendation(
                "FANOUT",
                "INDEPENDENT_WORK_READY",
                fanout_candidate_ids=["lane-invented"],
                rationale="The provider may not invent child identities.",
            ),
        )
        assert unknown.refusal_code == "FANOUT_CANDIDATE_NOT_SUPPLIED"

        active_children = validate(
            snapshot(
                trigger="FANOUT_READY",
                fanout_candidates=["lane-research"],
                outstanding_children=1,
            ),
            recommendation(
                "FANOUT",
                "INDEPENDENT_WORK_READY",
                fanout_candidate_ids=["lane-research"],
                rationale="The v1 contract does not widen fanout while a child is outstanding.",
            ),
        )
        assert active_children.refusal_code == "CHILDREN_ALREADY_OUTSTANDING"


    def test_wait_for_return_requires_outstanding_children_and_no_ready_return() -> None:
        accepted = validate(
            snapshot(outstanding_children=2, ready_returns=0, trigger="MATERIAL_RETURN"),
            recommendation(
                "WAIT_FOR_RETURN",
                "CHILDREN_OUTSTANDING",
                rationale="Two children remain outstanding and no return is ready to consume.",
            ),
        )
        assert accepted.status == "ACCEPTED"

        none = validate(
            snapshot(outstanding_children=0),
            recommendation(
                "WAIT_FOR_RETURN",
                "CHILDREN_OUTSTANDING",
                rationale="There is nothing to wait for.",
            ),
        )
        assert none.refusal_code == "NO_OUTSTANDING_CHILDREN"

        ready = validate(
            snapshot(outstanding_children=1, ready_returns=1, trigger="MATERIAL_RETURN"),
            recommendation(
                "WAIT_FOR_RETURN",
                "CHILDREN_OUTSTANDING",
                rationale="A ready return must be consumed rather than hidden behind a wait.",
            ),
        )
        assert ready.refusal_code == "RETURN_READY"


    def test_active_or_unknown_parent_turn_cannot_take_normal_next_action() -> None:
        for state in ("ACTIVE", "UNKNOWN"):
            receipt = validate(snapshot(turn_state=state))
            assert receipt.refusal_code == "TURN_NOT_TERMINAL"


    def test_stale_future_or_overlong_snapshot_fails_closed() -> None:
        expired = validate(snapshot(observed_at_ms=1_000, expires_at_ms=10_000), now_ms=10_001)
        assert expired.refusal_code == "SNAPSHOT_STALE"

        future = validate(snapshot(observed_at_ms=20_001, expires_at_ms=50_000), now_ms=20_000)
        assert future.refusal_code == "SNAPSHOT_STALE"

        overlong = validate(snapshot(observed_at_ms=1_000, expires_at_ms=70_001), now_ms=20_000)
        assert overlong.refusal_code == "SNAPSHOT_INVALID"


    def test_reason_code_requested_mode_and_fanout_fields_are_action_closed() -> None:
        wrong_reason = validate(rec=recommendation("CONTINUE_CURRENT_SESSION", "HUMAN_GATE"))
        assert wrong_reason.refusal_code == "REASON_ACTION_MISMATCH"

        stray_mode = validate(
            rec=recommendation(requested_mode="EXTRA_HIGH"),
        )
        assert stray_mode.refusal_code == "REQUESTED_MODE_NOT_ALLOWED"

        stray_fanout = validate(
            rec=recommendation(fanout_candidate_ids=["lane-research"]),
        )
        assert stray_fanout.refusal_code == "FANOUT_IDS_NOT_ALLOWED"


    def test_rationale_and_source_refs_are_digested_but_never_echoed() -> None:
        private_rationale = "private-rationale-needle: use hidden operator prose only for audit digest"
        private_source = "runtime:private-source-needle"
        snap = snapshot(source_refs=[private_source])
        receipt = validate(snap, recommendation(rationale=private_rationale))
        rendered = json.dumps(receipt.to_dict(), sort_keys=True)
        assert receipt.status == "ACCEPTED"
        assert private_rationale not in rendered
        assert private_source not in rendered
        assert len(receipt.rationale_digest) == 64
        assert len(receipt.snapshot_digest) == 64


    @pytest.mark.parametrize(
        ("which", "field", "value"),
        [
            ("snapshot", "command", "EXECUTE"),
            ("recommendation", "prompt", "private-secret-needle"),
            ("snapshot", "outstanding_children", True),
            ("snapshot", "fanout_candidates", ["dup", "dup"]),
            ("snapshot", "source_refs", []),
            ("recommendation", "fanout_candidate_ids", ["dup", "dup"]),
        ],
    )
    def test_closed_shape_and_type_violations_refuse_without_echo(
        which: str, field: str, value
    ) -> None:
        snap = snapshot()
        rec = recommendation()
        target = snap if which == "snapshot" else rec
        target[field] = value
        receipt = validate(snap, rec)
        assert receipt.status == "REFUSED"
        assert receipt.execution_authorized is False
        rendered = json.dumps(receipt.to_dict(), sort_keys=True)
        assert "private-secret-needle" not in rendered


    def test_inputs_are_not_mutated() -> None:
        snap = snapshot()
        rec = recommendation()
        before_snap = json.dumps(snap, sort_keys=True)
        before_rec = json.dumps(rec, sort_keys=True)
        validate(snap, rec)
        assert json.dumps(snap, sort_keys=True) == before_snap
        assert json.dumps(rec, sort_keys=True) == before_rec


    def test_contract_source_has_no_model_runtime_network_browser_or_persistence_surface() -> None:
        source = MODULE_PATH.read_text(encoding="utf-8")
        forbidden = (
            "requests.",
            "httpx.",
            "subprocess.",
            "socket.",
            "sqlite",
            "open(",
            "Path(",
            "chrome.",
            "document.",
            "window.",
            "send_message",
            "create_job",
            "create_attempt",
            "Runtime(",
            "ModelRouter(",
        )
        for token in forbidden:
            assert token not in source
