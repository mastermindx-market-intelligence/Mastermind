from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from control_plane.chairman_cognition import (
    ENVELOPE_SCHEMA,
    INPUT_SCHEMA,
    PACKET_SCHEMA,
    ChairmanCognitionError,
    evaluate_document,
)

_ROOT = Path(__file__).resolve().parents[1]


def _benefits(**changes):
    value = {
        "strategic_leverage": 70,
        "dependency_unlock": 70,
        "learning_value": 70,
        "chairman_load_reduction": 70,
        "user_or_machine_value": 70,
    }
    value.update(changes)
    return value


def _costs(**changes):
    value = {
        "time_to_evidence": 30,
        "execution_cost": 30,
        "coordination_risk": 30,
        "irreversibility_risk": 20,
        "scarce_cognition_cost": 30,
    }
    value.update(changes)
    return value


def _option(option_id="OPT-A", **changes):
    value = {
        "option_id": option_id,
        "title": "Bounded strategic option",
        "action": "SOURCE_BRANCH_WRITE",
        "reversibility": "REVERSIBLE",
        "source_refs": ["SRC-CHAIRMAN", "SRC-GITHUB"],
        "scope_refs": ["WS:CHAIRMAN-CONTROL-ROOM"],
        "effect_state": "NONE",
        "operation_key": "chairman-cognition-test-001",
        "carrier_state": "EXACT_EXISTING",
        "carrier_ref": "github:Mastermind:branch:test",
        "expected_head_sha": None,
        "repositories": ["mastermindx-market-intelligence/Mastermind"],
        "paths": ["control_plane/chairman_cognition.py"],
        "budget_units": 5,
        "active_children_after": 1,
        "creates_duplicate_control_plane": False,
        "stop_condition": "Stop at one immutable review-ready branch head.",
        "rollback_plan": "Delete no canonical state; abandon the branch if rejected.",
        "falsifier": "Any duplicate lifecycle or authority owner is a failure.",
        "benefits": _benefits(),
        "costs": _costs(),
    }
    value.update(changes)
    return value


def _envelope(**changes):
    value = {
        "schema": ENVELOPE_SCHEMA,
        "envelope_id": "ENV-CCL-001",
        "authority_source_refs": ["SRC-CHAIRMAN"],
        "mode": "SUPERVISED_LIVE_CANARY",
        "allowed_actions": [
            "DURABLE_RECORD_WRITE",
            "SOURCE_BRANCH_WRITE",
            "SOURCE_MERGE",
            "EXECUTIVE_CHILD_COMMISSION",
            "REVERSIBLE_RUNTIME_CANARY",
        ],
        "allowed_reversibility": ["REVERSIBLE", "COSTLY_REVERSIBLE"],
        "allowed_repositories": ["mastermindx-market-intelligence/Mastermind"],
        "allowed_path_prefixes": {
            "mastermindx-market-intelligence/Mastermind": [
                "control_plane",
                "docs",
                "scripts",
                "tests",
            ]
        },
        "allowed_scope_prefixes": ["WS:CHAIRMAN-CONTROL-ROOM"],
        "allowed_carrier_prefixes": ["github:Mastermind:", "agentos:", "executive:"],
        "max_budget_units": 20,
        "max_active_children": 3,
        "require_exact_carrier": True,
        "expires_at": "2026-09-30T00:00:00Z",
    }
    value.update(changes)
    return value


def _document(*options, envelope=None):
    return {
        "schema": INPUT_SCHEMA,
        "as_of": "2026-08-30T15:00:00Z",
        "source_receipts": [
            {
                "source_ref": "SRC-CHAIRMAN",
                "owner": "CHAIRMAN_DIRECTIVE",
                "revision": "conversation:2026-08-30",
                "state": "CURRENT",
                "load_bearing": True,
                "observed_at": "2026-08-30T15:00:00Z",
            },
            {
                "source_ref": "SRC-GITHUB",
                "owner": "GITHUB",
                "revision": "620263090fb9f272f763e420ba103b0ff8dc5f31",
                "state": "CURRENT",
                "load_bearing": True,
                "observed_at": "2026-08-30T15:00:00Z",
            },
        ],
        "strategic_constraints": {
            "autonomous_production_deploy": "prohibited",
            "autonomous_live_capital_execution": "prohibited",
            "duplicate_control_planes": "prohibited",
            "unbounded_autonomous_strategic_modification": "prohibited",
        },
        "delegation_envelope": envelope,
        "options": list(options or [_option()]),
    }


def _adjudication(packet, option_id="OPT-A"):
    return next(item for item in packet["adjudications"] if item["option_id"] == option_id)


def test_packet_is_deterministic_and_never_grants_execution_authority():
    document = _document(_option(), envelope=_envelope())
    first = evaluate_document(document)
    second = evaluate_document(copy.deepcopy(document))
    assert first == second
    assert first["schema"] == PACKET_SCHEMA
    assert first["packet_digest"] == second["packet_digest"]
    assert first["execution_authority_granted"] is False
    assert first["next_effect_requires_owner_revalidation"] is True
    assert all(
        item["execution_authority_granted"] is False
        for item in first["adjudications"]
    )


def test_modifying_action_without_envelope_requires_chairman():
    packet = evaluate_document(_document(_option(), envelope=None))
    item = _adjudication(packet)
    assert item["disposition"] == "CHAIRMAN_REQUIRED"
    assert item["reason"] == "MISSING_DELEGATION_ENVELOPE"
    assert packet["recommended_option_id"] is None


def test_read_only_action_is_eligible_without_envelope():
    option = _option(
        action="READ_ONLY_RESEARCH",
        reversibility="READ_ONLY",
        scope_refs=[],
        operation_key=None,
        carrier_state="NOT_APPLICABLE",
        carrier_ref=None,
        repositories=[],
        paths=[],
        budget_units=0,
        active_children_after=0,
    )
    packet = evaluate_document(_document(option, envelope=None))
    item = _adjudication(packet)
    assert item["disposition"] == "READ_ONLY_ELIGIBLE"
    assert packet["recommended_option_id"] == "OPT-A"


def test_current_envelope_allows_bounded_reversible_source_write():
    packet = evaluate_document(_document(_option(), envelope=_envelope()))
    item = _adjudication(packet)
    assert item["disposition"] == "ELIGIBLE_WITHIN_DELEGATION"
    assert item["reason"] == "EXPLICIT_DELEGATION_ENVELOPE"
    assert item["serviceable"] is True


def test_envelope_is_not_accepted_when_authority_source_is_stale():
    document = _document(_option(), envelope=_envelope())
    document["source_receipts"][0]["state"] = "STALE"
    packet = evaluate_document(document)
    assert packet["delegation_envelope"]["state"] == "SOURCE_NOT_CURRENT"
    assert _adjudication(packet)["reason"] == "SOURCE_NOT_CURRENT"


def test_expired_envelope_requires_chairman():
    packet = evaluate_document(
        _document(
            _option(),
            envelope=_envelope(expires_at="2026-08-30T14:59:59Z"),
        )
    )
    item = _adjudication(packet)
    assert item["disposition"] == "CHAIRMAN_REQUIRED"
    assert item["reason"] == "ENVELOPE_EXPIRED"


def test_effect_unknown_refuses_before_any_route_or_failover():
    packet = evaluate_document(
        _document(_option(effect_state="EFFECT_UNKNOWN"), envelope=_envelope())
    )
    item = _adjudication(packet)
    assert item["disposition"] == "REFUSED"
    assert item["reason"] == "EFFECT_UNKNOWN_RECONCILE_FIRST"


def test_duplicate_control_plane_is_always_refused():
    packet = evaluate_document(
        _document(
            _option(creates_duplicate_control_plane=True), envelope=_envelope()
        )
    )
    item = _adjudication(packet)
    assert item["disposition"] == "REFUSED"
    assert item["reason"] == "DUPLICATE_CONTROL_PLANE_REFUSED"


@pytest.mark.parametrize(
    "action,constraint",
    [
        ("PRODUCTION_DEPLOY", "autonomous_production_deploy"),
        ("LIVE_CAPITAL_EXECUTION", "autonomous_live_capital_execution"),
    ],
)
def test_standing_prohibitions_override_envelope(action, constraint):
    envelope = _envelope(allowed_actions=_envelope()["allowed_actions"] + [action])
    packet = evaluate_document(
        _document(_option(action=action), envelope=envelope)
    )
    item = _adjudication(packet)
    assert item["disposition"] == "REFUSED"
    assert item["reason"] == "STRATEGIC_CONSTRAINT_PROHIBITS"


@pytest.mark.parametrize(
    "action",
    [
        "CONSTITUTION_CHANGE",
        "TERMINAL_OBJECTIVE_CHANGE",
        "BUDGET_EXPANSION",
        "ADMIN_INFRASTRUCTURE",
    ],
)
def test_constitutional_boundaries_stay_with_chairman(action):
    envelope = _envelope(allowed_actions=_envelope()["allowed_actions"] + [action])
    packet = evaluate_document(
        _document(_option(action=action), envelope=envelope)
    )
    item = _adjudication(packet)
    assert item["disposition"] == "CHAIRMAN_REQUIRED"
    assert item["reason"] == "CONSTITUTIONAL_CHAIRMAN_BOUNDARY"


def test_irreversible_or_unknown_reversibility_requires_chairman():
    for reversibility in ("IRREVERSIBLE", "UNKNOWN"):
        packet = evaluate_document(
            _document(
                _option(reversibility=reversibility), envelope=_envelope()
            )
        )
        assert _adjudication(packet)["reason"] == "IRREVERSIBLE_REQUIRES_CHAIRMAN"


def test_scope_budget_and_child_limits_fail_closed():
    outside = evaluate_document(
        _document(
            _option(paths=["secrets/keys.json"]), envelope=_envelope()
        )
    )
    assert _adjudication(outside)["reason"] == "SCOPE_OUTSIDE_ENVELOPE"

    over_budget = evaluate_document(
        _document(_option(budget_units=21), envelope=_envelope())
    )
    assert _adjudication(over_budget)["reason"] == "BUDGET_EXCEEDS_ENVELOPE"

    too_many = evaluate_document(
        _document(_option(active_children_after=4), envelope=_envelope())
    )
    assert _adjudication(too_many)["reason"] == "ACTIVE_CHILDREN_EXCEED_ENVELOPE"


def test_stable_operation_and_exact_carrier_are_required():
    no_op = evaluate_document(
        _document(_option(operation_key=None), envelope=_envelope())
    )
    assert _adjudication(no_op)["reason"] == "STABLE_OPERATION_REQUIRED"

    ambiguous = evaluate_document(
        _document(_option(carrier_state="AMBIGUOUS"), envelope=_envelope())
    )
    assert _adjudication(ambiguous)["reason"] == "EXACT_CARRIER_REQUIRED"


def test_source_merge_requires_expected_head_sha():
    packet = evaluate_document(
        _document(_option(action="SOURCE_MERGE"), envelope=_envelope())
    )
    assert _adjudication(packet)["reason"] == "EXPECTED_HEAD_REQUIRED"

    green = evaluate_document(
        _document(
            _option(action="SOURCE_MERGE", expected_head_sha="a" * 40),
            envelope=_envelope(),
        )
    )
    assert _adjudication(green)["disposition"] == "ELIGIBLE_WITHIN_DELEGATION"


def test_live_canary_requires_stop_rollback_and_falsifier():
    for missing in ("stop_condition", "rollback_plan", "falsifier"):
        changes = {missing: None, "action": "REVERSIBLE_RUNTIME_CANARY"}
        packet = evaluate_document(
            _document(_option(**changes), envelope=_envelope())
        )
        assert _adjudication(packet)["reason"] == "CANARY_CONTROLS_REQUIRED"


def test_pareto_frontier_has_no_hidden_scalar_totalization():
    leverage = _option(
        "OPT-LEVERAGE",
        benefits=_benefits(strategic_leverage=95, learning_value=50),
        costs=_costs(execution_cost=45, time_to_evidence=20),
    )
    learning = _option(
        "OPT-LEARNING",
        operation_key="chairman-cognition-test-002",
        benefits=_benefits(strategic_leverage=70, learning_value=95),
        costs=_costs(execution_cost=20, time_to_evidence=45),
    )
    packet = evaluate_document(_document(leverage, learning, envelope=_envelope()))
    assert packet["strategic_frontier"] == ["OPT-LEARNING", "OPT-LEVERAGE"]
    assert packet["actionable_frontier"] == ["OPT-LEARNING", "OPT-LEVERAGE"]
    assert packet["selection_state"] == "MULTIPLE_INCOMPARABLE_ACTIONABLE_OPTIONS"
    assert packet["recommended_option_id"] is None


def test_dominated_option_is_removed_and_unique_option_is_recommended():
    strong = _option("OPT-STRONG", benefits=_benefits(strategic_leverage=90))
    weak = _option(
        "OPT-WEAK",
        operation_key="chairman-cognition-test-003",
        benefits=_benefits(strategic_leverage=60),
        costs=_costs(execution_cost=40),
    )
    packet = evaluate_document(_document(strong, weak, envelope=_envelope()))
    assert packet["strategic_frontier"] == ["OPT-STRONG"]
    assert packet["recommended_option_id"] == "OPT-STRONG"


def test_unknown_dimension_prevents_false_dominance():
    known = _option("OPT-KNOWN", benefits=_benefits(strategic_leverage=90))
    unknown = _option(
        "OPT-UNKNOWN",
        operation_key="chairman-cognition-test-004",
        benefits=_benefits(strategic_leverage=None),
    )
    packet = evaluate_document(_document(known, unknown, envelope=_envelope()))
    assert packet["strategic_frontier"] == ["OPT-KNOWN", "OPT-UNKNOWN"]


def test_closed_grammar_rejects_unknown_fields_and_unknown_sources():
    document = _document(_option(), envelope=_envelope())
    document["surprise"] = True
    with pytest.raises(ChairmanCognitionError, match="unknown fields"):
        evaluate_document(document)

    document = _document(_option(source_refs=["SRC-MISSING"]), envelope=_envelope())
    with pytest.raises(ChairmanCognitionError, match="unknown source receipt"):
        evaluate_document(document)


def test_cli_emits_fixed_opaque_error_without_input_leakage(tmp_path):
    secret = "secret-marker-should-not-leak"
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"bad": secret}), encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(_ROOT / "scripts" / "chairman_cognition.py"), str(path)],
        cwd=_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 2
    assert "INVALID_INPUT" in proc.stderr
    assert secret not in proc.stderr
    assert proc.stdout == ""


def test_prohibited_high_value_option_does_not_hide_best_eligible_fallback():
    prohibited = _option(
        "OPT-PROD",
        action="PRODUCTION_DEPLOY",
        benefits=_benefits(
            strategic_leverage=100,
            dependency_unlock=100,
            learning_value=100,
            chairman_load_reduction=100,
            user_or_machine_value=100,
        ),
        costs=_costs(
            time_to_evidence=1,
            execution_cost=1,
            coordination_risk=1,
            irreversibility_risk=1,
            scarce_cognition_cost=1,
        ),
    )
    safe = _option(
        "OPT-SAFE",
        operation_key="chairman-cognition-test-005",
        benefits=_benefits(strategic_leverage=60),
        costs=_costs(execution_cost=40),
    )
    envelope = _envelope(
        allowed_actions=_envelope()["allowed_actions"] + ["PRODUCTION_DEPLOY"]
    )
    packet = evaluate_document(_document(prohibited, safe, envelope=envelope))
    assert packet["strategic_frontier"] == ["OPT-PROD"]
    assert packet["actionable_frontier"] == ["OPT-SAFE"]
    assert packet["recommended_option_id"] == "OPT-SAFE"


def test_option_action_reversibility_and_carrier_grammar_is_consistent():
    with pytest.raises(ChairmanCognitionError, match="read-only action"):
        evaluate_document(
            _document(
                _option(
                    action="READ_ONLY_RESEARCH",
                    reversibility="REVERSIBLE",
                ),
                envelope=None,
            )
        )
    with pytest.raises(ChairmanCognitionError, match="modifying action"):
        evaluate_document(
            _document(_option(reversibility="READ_ONLY"), envelope=_envelope())
        )
    with pytest.raises(ChairmanCognitionError, match="requires carrier_ref"):
        evaluate_document(
            _document(_option(carrier_ref=None), envelope=_envelope())
        )


def test_noncurrent_envelope_source_is_distinct_from_current_option_sources():
    document = _document(_option(), envelope=_envelope(authority_source_refs=["SRC-ENVELOPE"]))
    document["source_receipts"].append(
        {
            "source_ref": "SRC-ENVELOPE",
            "owner": "CHAIRMAN_DIRECTIVE",
            "revision": "expired-or-conflicted-envelope-source",
            "state": "CONFLICT",
            "load_bearing": True,
            "observed_at": "2026-08-30T15:00:00Z",
        }
    )
    packet = evaluate_document(document)
    item = _adjudication(packet)
    assert packet["delegation_envelope"]["state"] == "SOURCE_NOT_CURRENT"
    assert item["disposition"] == "REFUSED"
    assert item["reason"] == "ENVELOPE_SOURCE_NOT_CURRENT"


def test_cli_emits_valid_packet_for_valid_input(tmp_path):
    path = tmp_path / "input.json"
    path.write_text(
        json.dumps(_document(_option(), envelope=_envelope())),
        encoding="utf-8",
    )
    proc = subprocess.run(
        [
            sys.executable,
            str(_ROOT / "scripts" / "chairman_cognition.py"),
            str(path),
        ],
        cwd=_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    packet = json.loads(proc.stdout)
    assert packet["schema"] == PACKET_SCHEMA
    assert packet["recommended_option_id"] == "OPT-A"
    assert proc.stderr == ""


def test_known_applied_effect_is_terminal_and_never_recommended():
    packet = evaluate_document(
        _document(_option(effect_state="KNOWN_APPLIED"), envelope=_envelope())
    )
    item = _adjudication(packet)
    assert item["disposition"] == "REFUSED"
    assert item["reason"] == "EFFECT_ALREADY_APPLIED"
    assert packet["strategic_frontier"] == []
    assert packet["actionable_frontier"] == []
    assert packet["recommended_option_id"] is None


def test_executive_child_commission_requires_explicit_new_child_carrier():
    invalid = evaluate_document(
        _document(
            _option(action="EXECUTIVE_CHILD_COMMISSION"),
            envelope=_envelope(),
        )
    )
    assert _adjudication(invalid)["reason"] == "NEW_CHILD_CARRIER_REQUIRED"

    valid = evaluate_document(
        _document(
            _option(
                action="EXECUTIVE_CHILD_COMMISSION",
                carrier_state="NEW_CHILD",
                carrier_ref=None,
            ),
            envelope=_envelope(),
        )
    )
    assert _adjudication(valid)["disposition"] == "ELIGIBLE_WITHIN_DELEGATION"


def test_delegation_envelope_cannot_disable_exact_carrier_law():
    with pytest.raises(ChairmanCognitionError, match="must require exact carrier"):
        evaluate_document(
            _document(
                _option(),
                envelope=_envelope(require_exact_carrier=False),
            )
        )


def test_delegation_authority_must_be_chairman_owned_source():
    with pytest.raises(ChairmanCognitionError, match="Chairman directive"):
        evaluate_document(
            _document(
                _option(),
                envelope=_envelope(authority_source_refs=["SRC-GITHUB"]),
            )
        )


def test_source_actions_require_one_repository_and_explicit_paths():
    with pytest.raises(ChairmanCognitionError, match="explicit paths"):
        evaluate_document(
            _document(
                _option(paths=[]),
                envelope=_envelope(),
            )
        )
    with pytest.raises(ChairmanCognitionError, match="explicit paths"):
        evaluate_document(
            _document(
                _option(
                    repositories=[
                        "mastermindx-market-intelligence/Mastermind",
                        "mastermindx-market-intelligence/macro",
                    ]
                ),
                envelope=_envelope(),
            )
        )


def test_read_only_options_cannot_carry_effect_state():
    with pytest.raises(ChairmanCognitionError, match="NONE effect_state"):
        evaluate_document(
            _document(
                _option(
                    action="READ_ONLY_RESEARCH",
                    reversibility="READ_ONLY",
                    scope_refs=[],
                    effect_state="KNOWN_APPLIED",
                    operation_key=None,
                    carrier_state="NOT_APPLICABLE",
                    carrier_ref=None,
                    repositories=[],
                    paths=[],
                    budget_units=0,
                    active_children_after=0,
                ),
                envelope=None,
            )
        )
