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
        "scope_refs": ["WS:CHAIRMAN-CONTROL-ROOM"],
        "effect_state": "NONE",
        "operation_key": "ccl-hardening-001",
        "carrier_state": "EXACT_EXISTING",
        "carrier_ref": "github:Mastermind:branch:ccl",
        "expected_head_sha": "a" * 40,
        "repositories": ["mastermindx-market-intelligence/Mastermind"],
        "paths": ["control_plane/chairman_cognition.py"],
        "budget_units": 1,
        "active_children_after": 1,
        "creates_duplicate_control_plane": False,
        "stop_condition": "Stop after one exact branch head.",
        "rollback_plan": "Abandon the unmerged branch.",
        "falsifier": "Any duplicate owner is a failure.",
        "change_classes": ["EXISTING_CAPABILITY_COMPLETION"],
        "affected_departments": ["executive"],
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
        "allowed_scope_prefixes": ["WS:CHAIRMAN-CONTROL-ROOM"],
        "allowed_carrier_prefixes": ["github:Mastermind:", "agentos:", "executive:"],
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
                "source_ref": "SRC-STRATEGY",
                "owner": "STRATEGIC_STATE",
                "revision": "sha256:current-strategic-state",
                "state": "CURRENT",
                "load_bearing": True,
                "observed_at": "2026-08-30T16:00:00Z",
            },
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
        "strategic_constraints_source_ref": "SRC-STRATEGY",
        "strategic_constraints": {
            "autonomous_production_deploy": "prohibited",
            "autonomous_live_capital_execution": "prohibited",
            "duplicate_control_planes": "prohibited",
            "marketing_org_expansion_before_distribution_proof": "prohibited",
            "new_feature_expansion": "constrained",
            "unbounded_autonomous_strategic_modification": "prohibited",
        },
        "delegation_envelope": envelope or _envelope(),
        "options": [option or _option()],
    }


def _result(document: dict) -> dict:
    return evaluate_document(document)["adjudications"][0]


def _organizational_option(**changes) -> dict:
    return _option(
        action="ORGANIZATIONAL_RESTRUCTURE",
        carrier_ref="agentos:WS:CHAIRMAN-CONTROL-ROOM",
        expected_head_sha=None,
        repositories=[],
        paths=[],
        **changes,
    )


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
        expected_head_sha=None,
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
        scope_refs=[],
        effect_state="KNOWN_APPLIED",
        operation_key=None,
        carrier_state="NOT_APPLICABLE",
        carrier_ref=None,
        expected_head_sha=None,
        repositories=[],
        paths=[],
        budget_units=0,
        active_children_after=0,
        change_classes=["RESEARCH"],
    )
    with pytest.raises(ChairmanCognitionError, match="NONE effect_state"):
        evaluate_document(_document(option, envelope=None))


def test_delegation_authority_source_must_be_load_bearing() -> None:
    document = _document()
    document["source_receipts"][1]["load_bearing"] = False
    with pytest.raises(ChairmanCognitionError, match="load-bearing"):
        evaluate_document(document)


def test_source_receipt_cannot_postdate_decision_snapshot() -> None:
    document = _document()
    document["source_receipts"][2]["observed_at"] = "2026-08-30T16:00:01Z"
    with pytest.raises(ChairmanCognitionError, match="postdate"):
        evaluate_document(document)


def test_portfolio_hold_is_a_first_class_no_effect_option() -> None:
    option = _option(
        action="PORTFOLIO_HOLD",
        reversibility="READ_ONLY",
        scope_refs=[],
        operation_key=None,
        carrier_state="NOT_APPLICABLE",
        carrier_ref=None,
        expected_head_sha=None,
        repositories=[],
        paths=[],
        budget_units=0,
        active_children_after=0,
        change_classes=["RESEARCH"],
    )
    packet = evaluate_document(_document(option, envelope=None))
    assert packet["recommended_option_id"] == "OPT-HARDEN"
    assert packet["adjudications"][0]["disposition"] == "READ_ONLY_ELIGIBLE"


def test_modifying_organizational_action_requires_canonical_scope_ref() -> None:
    with pytest.raises(ChairmanCognitionError, match="scope_ref"):
        evaluate_document(_document(_option(scope_refs=[])))


def test_scope_ref_must_be_inside_delegation_envelope() -> None:
    option = _option(scope_refs=["WS:PROPHET-US-V4-RECOVERY"])
    assert _result(_document(option))["reason"] == "SCOPE_OUTSIDE_ENVELOPE"


def test_exact_carrier_must_be_inside_delegation_envelope() -> None:
    option = _option(carrier_ref="slack:C0OTHER/123.456")
    assert _result(_document(option))["reason"] == "SCOPE_OUTSIDE_ENVELOPE"


def test_program_start_uses_new_child_semantics() -> None:
    allowed = _envelope(
        allowed_actions=_envelope()["allowed_actions"] + ["PROGRAM_START"]
    )
    wrong = _option(
        action="PROGRAM_START",
        carrier_state="EXACT_EXISTING",
        carrier_ref="agentos:WS:CHAIRMAN-CONTROL-ROOM",
        expected_head_sha=None,
        repositories=[],
        paths=[],
    )
    assert _result(_document(wrong, allowed))["reason"] == "NEW_CHILD_CARRIER_REQUIRED"

    valid = _option(
        action="PROGRAM_START",
        carrier_state="NEW_CHILD",
        carrier_ref=None,
        expected_head_sha=None,
        repositories=[],
        paths=[],
    )
    assert _result(_document(valid, allowed))["disposition"] == "ELIGIBLE_WITHIN_DELEGATION"


@pytest.mark.parametrize(
    "action",
    [
        "PROGRAM_PAUSE",
        "PROGRAM_RESUME",
        "PROGRAM_RETIRE",
        "PROGRAM_COMBINE",
        "PROGRAM_SPLIT",
        "RESOURCE_REALLOCATION",
        "ORGANIZATIONAL_RESTRUCTURE",
    ],
)
def test_chairman_organizational_actions_are_modeled_without_generic_task_aliases(action: str) -> None:
    allowed = _envelope(
        allowed_actions=_envelope()["allowed_actions"] + [action]
    )
    option = _option(
        action=action,
        carrier_ref="agentos:WS:CHAIRMAN-CONTROL-ROOM",
        expected_head_sha=None,
        repositories=[],
        paths=[],
    )
    assert _result(_document(option, allowed))["disposition"] == "ELIGIBLE_WITHIN_DELEGATION"


def test_missing_unbounded_autonomous_constraint_rejects_closed_input() -> None:
    document = _document()
    del document["strategic_constraints"][
        "unbounded_autonomous_strategic_modification"
    ]
    with pytest.raises(
        ChairmanCognitionError, match="missing load-bearing strategic constraint"
    ):
        evaluate_document(document)


@pytest.mark.parametrize(
    "level,disposition,reason",
    [
        ("prohibited", "REFUSED", "STRATEGIC_CONSTRAINT_PROHIBITS"),
        (
            "constrained",
            "CHAIRMAN_REQUIRED",
            "STRATEGIC_CONSTRAINT_REQUIRES_CHAIRMAN",
        ),
        ("permitted", "ELIGIBLE_WITHIN_DELEGATION", "EXPLICIT_DELEGATION_ENVELOPE"),
    ],
)
def test_bounded_autonomous_modification_consumes_strategic_constraint(
    level: str, disposition: str, reason: str
) -> None:
    envelope = _envelope(
        mode="BOUNDED_AUTONOMOUS",
        allowed_actions=_envelope()["allowed_actions"]
        + ["ORGANIZATIONAL_RESTRUCTURE"],
    )
    document = _document(_organizational_option(), envelope)
    document["strategic_constraints"][
        "unbounded_autonomous_strategic_modification"
    ] = level
    item = _result(document)
    assert item["disposition"] == disposition
    assert item["reason"] == reason


def test_read_only_option_remains_eligible_in_bounded_autonomous_mode() -> None:
    option = _option(
        action="PORTFOLIO_HOLD",
        reversibility="READ_ONLY",
        scope_refs=[],
        operation_key=None,
        carrier_state="NOT_APPLICABLE",
        carrier_ref=None,
        expected_head_sha=None,
        repositories=[],
        paths=[],
        budget_units=0,
        active_children_after=0,
        change_classes=["RESEARCH"],
    )
    item = _result(_document(option, _envelope(mode="BOUNDED_AUTONOMOUS")))
    assert item["disposition"] == "READ_ONLY_ELIGIBLE"
    assert item["reason"] == "READ_ONLY_INHERENT"


@pytest.mark.parametrize("missing", ["stop_condition", "rollback_plan", "falsifier"])
def test_every_supervised_modifying_option_requires_canary_controls(
    missing: str,
) -> None:
    item = _result(_document(_option(**{missing: None}), _envelope()))
    assert item["disposition"] == "REFUSED"
    assert item["reason"] == "CANARY_CONTROLS_REQUIRED"


def test_runtime_canary_requires_controls_in_bounded_autonomous_mode() -> None:
    envelope = _envelope(
        mode="BOUNDED_AUTONOMOUS",
        allowed_actions=_envelope()["allowed_actions"]
        + ["REVERSIBLE_RUNTIME_CANARY"],
    )
    document = _document(
        _option(
            action="REVERSIBLE_RUNTIME_CANARY",
            stop_condition=None,
            expected_head_sha=None,
            repositories=[],
            paths=[],
            change_classes=["RUNTIME_CANARY"],
        ),
        envelope,
    )
    document["strategic_constraints"][
        "unbounded_autonomous_strategic_modification"
    ] = "permitted"
    item = _result(document)
    assert item["disposition"] == "REFUSED"
    assert item["reason"] == "CANARY_CONTROLS_REQUIRED"


@pytest.mark.parametrize(
    "level,disposition,reason",
    [
        ("prohibited", "REFUSED", "DUPLICATE_CONTROL_PLANE_REFUSED"),
        (
            "constrained",
            "CHAIRMAN_REQUIRED",
            "CONSTITUTIONAL_CHAIRMAN_BOUNDARY",
        ),
        (
            "permitted",
            "CHAIRMAN_REQUIRED",
            "CONSTITUTIONAL_CHAIRMAN_BOUNDARY",
        ),
    ],
)
def test_duplicate_plane_constraint_is_consumed_and_never_delegates(
    level: str, disposition: str, reason: str
) -> None:
    document = _document(_option(creates_duplicate_control_plane=True))
    document["strategic_constraints"]["duplicate_control_planes"] = level
    item = _result(document)
    assert item["disposition"] == disposition
    assert item["reason"] == reason
    assert item["execution_authority_granted"] is False


def test_scope_prefix_requires_exact_or_delimited_boundary() -> None:
    sibling = _option(scope_refs=["WS:CHAIRMAN-CONTROL-ROOM-EVIL"])
    sibling_item = _result(_document(sibling))
    assert sibling_item["disposition"] == "CHAIRMAN_REQUIRED"
    assert sibling_item["reason"] == "SCOPE_OUTSIDE_ENVELOPE"

    exact_item = _result(
        _document(_option(scope_refs=["WS:CHAIRMAN-CONTROL-ROOM"]))
    )
    assert exact_item["disposition"] == "ELIGIBLE_WITHIN_DELEGATION"

    child_item = _result(
        _document(_option(scope_refs=["WS:CHAIRMAN-CONTROL-ROOM:REPAIR"]))
    )
    assert child_item["disposition"] == "ELIGIBLE_WITHIN_DELEGATION"


def test_carrier_prefix_requires_exact_or_delimited_boundary() -> None:
    exact_prefix = "github:Mastermind:branch:ccl"
    envelope = _envelope(allowed_carrier_prefixes=[exact_prefix])

    sibling_item = _result(
        _document(
            _option(carrier_ref=exact_prefix + "-EVIL"),
            envelope,
        )
    )
    assert sibling_item["disposition"] == "CHAIRMAN_REQUIRED"
    assert sibling_item["reason"] == "SCOPE_OUTSIDE_ENVELOPE"

    exact_item = _result(_document(_option(carrier_ref=exact_prefix), envelope))
    assert exact_item["disposition"] == "ELIGIBLE_WITHIN_DELEGATION"

    child_item = _result(
        _document(_option(carrier_ref=exact_prefix + "/repair"), envelope)
    )
    assert child_item["disposition"] == "ELIGIBLE_WITHIN_DELEGATION"
