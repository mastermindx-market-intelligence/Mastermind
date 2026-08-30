from __future__ import annotations

import pytest

from control_plane.chairman_cognition import (
    ENVELOPE_SCHEMA,
    INPUT_SCHEMA,
    ChairmanCognitionError,
    evaluate_document,
)


def _metrics(value: int = 50) -> dict[str, int]:
    return {
        "strategic_leverage": value,
        "dependency_unlock": value,
        "learning_value": value,
        "chairman_load_reduction": value,
        "user_or_machine_value": value,
    }


def _costs(value: int = 20) -> dict[str, int]:
    return {
        "time_to_evidence": value,
        "execution_cost": value,
        "coordination_risk": value,
        "irreversibility_risk": value,
        "scarce_cognition_cost": value,
    }


def _option(**changes) -> dict:
    option = {
        "option_id": "OPT-HARDEN",
        "title": "Bounded hardening option",
        "action": "SOURCE_BRANCH_WRITE",
        "reversibility": "REVERSIBLE",
        "source_refs": ["SRC-CHAIRMAN", "SRC-GITHUB"],
        "effect_state": "NONE",
        "operation_key": "ccl-hardening-001",
        "carrier_state": "EXACT_EXISTING",
        "carrier_ref": "github:Mastermind:branch:ccl",
        "expected_head_sha": None,
        "repositories": ["mastermindx-market-intelligence/Mastermind"],
        "paths": ["control_plane/chairman_cognition.py"],
        "budget_units": 1,
        "active_children_after": 1,
        "creates_duplicate_control_plane": False,
        "stop_condition": "Stop after one exact branch head.",
        "rollback_plan": "Abandon the unmerged branch.",
        "falsifier": "Any duplicate owner is a failure.",
        "benefits": _metrics(),
        "costs": _costs(),
    }
    option.update(changes)
    return option


def _envelope(**changes) -> dict:
    envelope = {
        "schema": ENVELOPE_SCHEMA,
        "envelope_id": "ENV-HARDEN-001",
        "authority_source_refs": ["SRC-CHAIRMAN"],
        "mode": "SUPERVISED_LIVE_CANARY",
        "allowed_actions": [
            "SOURCE_BRANCH_WRITE",
            "EXECUTIVE_CHILD_COMMISSION",
        ],
        "allowed_reversibility": ["REVERSIBLE"],
        "allowed_repositories": ["mastermindx-market-intelligence/Mastermind"],
        "allowed_path_prefixes": {
            "mastermindx-market-intelligence/Mastermind": ["control_plane"]
        },
        "max_budget_units": 5,
        "max_active_children": 3,
        "require_exact_carrier": True,
        "expires_at": "2026-09-30T00:00:00Z",
    }
    envelope.update(changes)
    return envelope


def _document(option: dict | None = None, envelope: dict | None = None) -> dict:
    return {
        "schema": INPUT_SCHEMA,
        "as_of": "2026-08-30T16:00:00Z",
        "source_receipts": [
            {
                "source_ref": "SRC-CHAIRMAN",
                "owner": "CHAIRMAN_DIRECTIVE",
                "revision": "conversation:2026-08-30",
                "state": "CURRENT",
                "load_bearing": True,
                "observed_at": "2026-08-30T16:00:00Z",
            },
            {
                "source_ref": "SRC-GITHUB",
                "owner": "GITHUB",
                "revision": "620263090fb9f272f763e420ba103b0ff8dc5f31",
                "state": "CURRENT",
                "load_bearing": True,
                "observed_at": "2026-08-30T16:00:00Z",
            },
        ],
        "strategic_constraints": {
            "autonomous_production_deploy": "prohibited",
            "autonomous_live_capital_execution": "prohibited",
            "duplicate_control_planes": "prohibited",
        },
        "delegation_envelope": envelope or _envelope(),
        "options": [option or _option()],
    }


def _result(document: dict) -> dict:
    return evaluate_document(document)["adjudications"][0]


def test_known_applied_effect_is_terminal_and_never_recommended() -> None:
    packet = evaluate_document(_document(_option(effect_state="KNOWN_APPLIED")))
    assert packet["strategic_frontier"] == []
    assert packet["actionable_frontier"] == []
    assert packet["recommended_option_id"] is None
    assert packet["adjudications"][0]["reason"] == "EFFECT_ALREADY_APPLIED"


def test_new_executive_child_requires_explicit_new_child_carrier() -> None:
    wrong = _option(
        action="EXECUTIVE_CHILD_COMMISSION",
        repositories=[],
        paths=[],
    )
    assert _result(_document(wrong))["reason"] == "NEW_CHILD_CARRIER_REQUIRED"

    valid = _option(
        action="EXECUTIVE_CHILD_COMMISSION",
        carrier_state="NEW_CHILD",
        carrier_ref=None,
        repositories=[],
        paths=[],
    )
    assert _result(_document(valid))["disposition"] == "ELIGIBLE_WITHIN_DELEGATION"


def test_envelope_cannot_disable_exact_carrier_law() -> None:
    with pytest.raises(ChairmanCognitionError, match="must require exact carrier"):
        evaluate_document(_document(envelope=_envelope(require_exact_carrier=False)))


def test_delegation_authority_source_must_be_chairman_owned() -> None:
    document = _document(envelope=_envelope(authority_source_refs=["SRC-GITHUB"]))
    with pytest.raises(ChairmanCognitionError, match="Chairman directive"):
        evaluate_document(document)


def test_source_actions_require_one_repository_and_explicit_paths() -> None:
    for changes in ({"repositories": [], "paths": []}, {"paths": []}):
        with pytest.raises(ChairmanCognitionError, match="explicit paths"):
            evaluate_document(_document(_option(**changes)))


def test_read_only_action_cannot_claim_an_applied_effect() -> None:
    option = _option(
        action="READ_ONLY_RESEARCH",
        reversibility="READ_ONLY",
        effect_state="KNOWN_APPLIED",
        operation_key=None,
        carrier_state="NOT_APPLICABLE",
        carrier_ref=None,
        repositories=[],
        paths=[],
        budget_units=0,
        active_children_after=0,
    )
    with pytest.raises(ChairmanCognitionError, match="NONE effect_state"):
        evaluate_document(_document(option, envelope=None))


def test_delegation_authority_source_must_be_load_bearing() -> None:
    document = _document()
    document["source_receipts"][0]["load_bearing"] = False
    with pytest.raises(ChairmanCognitionError, match="load-bearing"):
        evaluate_document(document)


def test_source_receipt_cannot_postdate_decision_snapshot() -> None:
    document = _document()
    document["source_receipts"][1]["observed_at"] = "2026-08-30T16:00:01Z"
    with pytest.raises(ChairmanCognitionError, match="postdate"):
        evaluate_document(document)
