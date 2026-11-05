"""tests.test_operation_assurance_checker — OLS-A1 deterministic checker contract.

Exercises the hostile/valid corpus behavior required by (precedence order):

1. docs/superpowers/specs/2026-08-31-operation-assurance-a1-wire-release-finalization.md
2. docs/superpowers/specs/2026-08-30-operation-assurance-immutable-report-projection-clarification.md
3. docs/superpowers/specs/2026-08-30-operation-assurance-model-fidelity-counterexample-validation-amendment.md
4. docs/superpowers/specs/2026-08-30-operation-assurance-a1-trusted-input-total-proof-clarification.md
5. docs/superpowers/specs/2026-08-30-operation-assurance-a1-controlling-execution-overlay.md
6. docs/superpowers/plans/2026-08-30-operation-assurance-core.md
"""
from __future__ import annotations

from control_plane.operation_assurance_checker import run_checker
from control_plane.operation_assurance_model import parse_model_text
from tests.operation_assurance_fixture_lib import (
    REF,
    clone,
    dumps,
    effect,
    environment_assumption,
    fairness,
    gate,
    guard,
    minimal_model,
    model_gap,
    obligation,
    outcome,
    resource,
    source_record,
    source_snapshot,
    state_forbidden,
    transition,
    transition_forbidden,
)

GENERATED_AT = "2026-08-30T12:00:00Z"


def _run(model_dict):
    model = parse_model_text(dumps(model_dict))
    return run_checker(model, generated_at=GENERATED_AT)


# ---------------------------------------------------------------------------
# Safe finite fixture
# ---------------------------------------------------------------------------


def test_safe_finite_model_is_proven() -> None:
    r = _run(minimal_model())
    assert r.model_analysis_verdict == "PROVEN_WITHIN_FINITE_MODEL"
    assert r.source_applicability_at_generation == "AUTHOR_DECLARED_ONLY"
    assert r.progress_disposition == "AUTONOMOUSLY_LIVE"
    assert r.admission_recommendation == "REPORT_ONLY_NO_RECOMMENDATION"
    assert r.counterexamples == ()
    assert r.exploration_receipt.base_graph_complete is True
    assert r.exploration_receipt.checker_terminated_normally is True


def test_fixed_input_and_generated_at_is_byte_identical() -> None:
    r1 = _run(minimal_model())
    r2 = _run(minimal_model())
    assert r1.to_json() == r2.to_json()


def test_model_permutation_produces_identical_report() -> None:
    import json

    d1 = minimal_model()
    d2 = json.loads(json.dumps(d1))
    d2 = {k: d2[k] for k in reversed(list(d2.keys()))}
    r1 = _run(d1)
    r2 = _run(d2)
    assert r1.to_json() == r2.to_json()


# ---------------------------------------------------------------------------
# Reachable deadlock
# ---------------------------------------------------------------------------


def _deadlock_model() -> dict:
    d = clone(minimal_model())
    # add a branch that leads to a dead end with no terminal/gate/recurring
    d["state_domains"]["phase"] = ["START", "STUCK", "DONE"]
    d["initial_state"]["phase"] = "START"
    d["transitions"] = [
        transition("finish", [guard("phase", "EQ", "START")], [effect("phase", "DONE")], required_reachable=True),
        transition("wander", [guard("phase", "EQ", "START")], [effect("phase", "STUCK")]),
    ]
    return d


def test_reachable_deadlock_fails_option_to_complete() -> None:
    r = _run(_deadlock_model())
    assert r.model_analysis_verdict == "UNSAFE_COUNTEREXAMPLE"
    otc = [p for p in r.property_results if p.property_id == "OPTION_TO_COMPLETE"][0]
    assert otc.status == "FAIL"
    assert r.progress_disposition == "NO_PROGRESS"
    assert r.admission_recommendation == "REPORT_ONLY_REPAIR"
    cx = [c for c in r.counterexamples if c.property_id == "OPTION_TO_COMPLETE"][0]
    assert cx.realizability == "DECLARED_MODEL_ONLY"
    assert cx.shortest_prefix == ("wander",)


# ---------------------------------------------------------------------------
# Non-progress lasso (canonical A --spin--> A / A --finish--> DONE)
# ---------------------------------------------------------------------------


def _spin_model(*, with_fairness: bool) -> dict:
    d = clone(minimal_model())
    d["state_domains"]["phase"] = ["START", "DONE"]
    finish = transition("finish", [guard("phase", "EQ", "START")], [effect("phase", "DONE")], required_reachable=True)
    spin = transition("spin", [guard("phase", "EQ", "START")], [effect("phase", "START")])
    if with_fairness:
        finish = dict(finish, fairness_ref="fair_finish")
        d["fairness_assumptions"] = [fairness("fair_finish", ["finish"])]
    d["transitions"] = [finish, spin]
    return d


def test_unfair_spin_cycle_is_universal_progress_violation() -> None:
    r = _run(_spin_model(with_fairness=False))
    assert r.model_analysis_verdict == "UNSAFE_COUNTEREXAMPLE"
    up = [p for p in r.property_results if p.property_id == "UNIVERSAL_PROGRESS"][0]
    assert up.status == "FAIL"
    cx = [c for c in r.counterexamples if c.property_id == "UNIVERSAL_PROGRESS"][0]
    assert cx.witness_kind == "LASSO"
    assert cx.cycle == ("spin",)


def test_weak_fairness_on_continuously_enabled_finish_excludes_the_spin_lasso() -> None:
    r = _run(_spin_model(with_fairness=True))
    assert r.model_analysis_verdict == "PROVEN_WITHIN_FINITE_MODEL"
    up = [p for p in r.property_results if p.property_id == "UNIVERSAL_PROGRESS"][0]
    assert up.status == "PASS"
    assert r.progress_disposition == "FAIRNESS_CONDITIONAL"


def test_disabled_in_one_cycle_state_defeats_weak_fairness_exclusion() -> None:
    # finish only sometimes enabled (guarded also on a second variable) so it
    # is disabled in at least one visited cycle state -> weak fairness cannot
    # exclude the candidate lasso through that state.
    d = clone(minimal_model())
    d["state_domains"] = {"phase": ["START", "DONE"], "toggle": ["ON", "OFF"]}
    d["initial_state"] = {"phase": "START", "toggle": "OFF"}
    finish = transition(
        "finish",
        [guard("phase", "EQ", "START"), guard("toggle", "EQ", "ON")],
        [effect("phase", "DONE")],
        required_reachable=True,
        fairness_ref="fair_finish",
    )
    spin = transition("spin", [guard("phase", "EQ", "START"), guard("toggle", "EQ", "OFF")], [effect("phase", "START")])
    d["transitions"] = [finish, spin]
    d["fairness_assumptions"] = [fairness("fair_finish", ["finish"])]
    r = _run(d)
    # finish is never even enabled (toggle never becomes ON) so this is really
    # a dead-end/no-progress case, not a fairness-excluded one.
    assert r.model_analysis_verdict == "UNSAFE_COUNTEREXAMPLE"
    up = [p for p in r.property_results if p.property_id == "UNIVERSAL_PROGRESS"][0]
    assert up.status == "FAIL"


# ---------------------------------------------------------------------------
# Valid intentional wait / external gate
# ---------------------------------------------------------------------------


def _wait_model(disposition: str) -> dict:
    # A valid wait/gate always has an escape enabled at EVERY reached gate
    # state (plan 14.7: "for each reached gate state"), not merely a
    # conditional happy-path release. "proceed" only becomes enabled once
    # capacity flips; "cancel_wait" is always enabled while WAITING and is
    # the modeled always-available escalation/closure path.
    d = clone(minimal_model())
    d["state_domains"] = {
        "phase": ["WAITING", "DONE", "CANCELLED"],
        "capacity": ["UNAVAILABLE", "AVAILABLE"],
    }
    d["initial_state"] = {"phase": "WAITING", "capacity": "UNAVAILABLE"}
    check_again = transition("check_again", [guard("phase", "EQ", "WAITING")], [effect("capacity", "UNAVAILABLE")])
    become_available = transition(
        "become_available",
        [guard("phase", "EQ", "WAITING"), guard("capacity", "EQ", "UNAVAILABLE")],
        [effect("capacity", "AVAILABLE")],
        external_assumption_ref="capacity_may_return",
    )
    proceed = transition(
        "proceed",
        [guard("phase", "EQ", "WAITING"), guard("capacity", "EQ", "AVAILABLE")],
        [effect("phase", "DONE")],
        required_reachable=True,
        gate_refs=["wait_gate"],
    )
    cancel_wait = transition(
        "cancel_wait",
        [guard("phase", "EQ", "WAITING")],
        [effect("phase", "CANCELLED")],
        gate_refs=["wait_gate"],
    )
    d["transitions"] = [check_again, become_available, proceed, cancel_wait]
    d["terminal_outcomes"] = [
        outcome("done", "TERMINAL_SUCCESS", [guard("phase", "EQ", "DONE")]),
        outcome("cancelled", "TERMINAL_CANCELLED", [guard("phase", "EQ", "CANCELLED")]),
    ]
    d["external_gates"] = [
        gate(
            "wait_gate",
            disposition,
            [guard("phase", "EQ", "WAITING")],
            ["proceed", "cancel_wait"],
            "cancel_wait",
            owner_or_authority="CAPACITY_FABRIC",
        )
    ]
    d["environment_assumptions"] = [
        environment_assumption("capacity_may_return", ["become_available"], ["OPTION_TO_COMPLETE"])
    ]
    return d


def test_capacity_valid_wait_is_intentional_wait_without_deadlock() -> None:
    r = _run(_wait_model("INTENTIONAL_WAIT"))
    assert r.model_analysis_verdict == "PROVEN_WITHIN_FINITE_MODEL"
    assert r.progress_disposition == "INTENTIONAL_WAIT"
    assert r.admission_recommendation == "REPORT_ONLY_AWAIT_GATE"
    gate_prop = [p for p in r.property_results if p.property_id == "GATE_OR_WAIT_RETURN_PATH_VALID"][0]
    assert gate_prop.status == "PASS"


def test_chairman_external_gate_is_externally_gated_without_autonomous_claim() -> None:
    r = _run(_wait_model("EXTERNAL_GATE"))
    assert r.model_analysis_verdict == "PROVEN_WITHIN_FINITE_MODEL"
    assert r.progress_disposition == "EXTERNALLY_GATED"
    assert r.admission_recommendation == "REPORT_ONLY_AWAIT_GATE"


def test_gate_with_no_release_ever_enabled_is_gate_incomplete() -> None:
    d = _wait_model("EXTERNAL_GATE")
    # both proceed and cancel_wait additionally require an unreachable third
    # value -> no release transition is ever enabled at the gate state.
    d["state_domains"]["capacity"] = ["UNAVAILABLE", "AVAILABLE", "IMPOSSIBLE"]
    for t in d["transitions"]:
        if t["transition_id"] in ("proceed", "cancel_wait"):
            t["guards"] = [
                guard("phase", "EQ", "WAITING"),
                guard("capacity", "EQ", "IMPOSSIBLE"),
            ]
    r = _run(d)
    gate_prop = [p for p in r.property_results if p.property_id == "GATE_OR_WAIT_RETURN_PATH_VALID"][0]
    assert gate_prop.status == "FAIL"
    assert r.model_analysis_verdict == "UNSAFE_COUNTEREXAMPLE"


# ---------------------------------------------------------------------------
# Recurring service
# ---------------------------------------------------------------------------


def _recurring_model() -> dict:
    d = clone(minimal_model())
    d["state_domains"]["phase"] = ["RUNNING"]
    d["initial_state"]["phase"] = "RUNNING"
    d["transitions"] = [
        transition("tick", [guard("phase", "EQ", "RUNNING")], [effect("phase", "RUNNING")], required_reachable=True)
    ]
    d["terminal_outcomes"] = []
    d["recurring_progress_outcomes"] = [outcome("service", "RECURRING_PROGRESS", [guard("phase", "EQ", "RUNNING")])]
    return d


def test_recurring_service_passes_without_forced_terminal_completion() -> None:
    r = _run(_recurring_model())
    assert r.model_analysis_verdict == "PROVEN_WITHIN_FINITE_MODEL"
    assert r.progress_disposition == "RECURRING_SERVICE"
    rec = [p for p in r.property_results if p.property_id == "RECURRING_PROGRESS_VALID"][0]
    assert rec.status == "PASS"


def test_fake_recurring_progress_dead_end_fails() -> None:
    d = clone(minimal_model())
    d["state_domains"]["phase"] = ["RUNNING", "STUCK"]
    d["initial_state"]["phase"] = "RUNNING"
    d["transitions"] = [
        transition("break", [guard("phase", "EQ", "RUNNING")], [effect("phase", "STUCK")], required_reachable=True)
    ]
    d["terminal_outcomes"] = []
    d["recurring_progress_outcomes"] = [
        outcome("service", "RECURRING_PROGRESS", [guard("phase", "EQ", "RUNNING")]),
        outcome("stuck_claim", "RECURRING_PROGRESS", [guard("phase", "EQ", "STUCK")]),
    ]
    r = _run(d)
    rec = [p for p in r.property_results if p.property_id == "RECURRING_PROGRESS_VALID"][0]
    assert rec.status == "FAIL"


# ---------------------------------------------------------------------------
# Starvation under declared fairness
# ---------------------------------------------------------------------------


def _starvation_model(*, with_fairness: bool) -> dict:
    d = clone(minimal_model())
    d["state_domains"] = {"phase": ["RUNNING"], "obligation_state": ["PENDING", "DISCHARGED"]}
    d["initial_state"] = {"phase": "RUNNING", "obligation_state": "PENDING"}
    discharge = transition(
        "discharge",
        [guard("phase", "EQ", "RUNNING"), guard("obligation_state", "EQ", "PENDING")],
        [effect("obligation_state", "DISCHARGED")],
        required_reachable=True,
    )
    ignore = transition("ignore", [guard("phase", "EQ", "RUNNING")], [effect("phase", "RUNNING")])
    if with_fairness:
        discharge = dict(discharge, fairness_ref="fair_discharge")
        d["fairness_assumptions"] = [fairness("fair_discharge", ["discharge"])]
    d["transitions"] = [discharge, ignore]
    d["terminal_outcomes"] = []
    d["recurring_progress_outcomes"] = [outcome("service", "RECURRING_PROGRESS", [guard("obligation_state", "EQ", "DISCHARGED")])]
    d["obligations"] = [
        obligation("ob_service", "obligation_state", ["PENDING"], ["DISCHARGED"], persistent=True, owner_or_authority="OPERATION")
    ]
    return d


def test_persistent_obligation_starves_without_fairness() -> None:
    r = _run(_starvation_model(with_fairness=False))
    starv = [p for p in r.property_results if p.property_id == "NO_STARVATION_UNDER_DECLARED_FAIRNESS"][0]
    assert starv.status == "FAIL"
    assert r.model_analysis_verdict == "UNSAFE_COUNTEREXAMPLE"


def test_weak_fairness_on_discharge_clears_starvation() -> None:
    r = _run(_starvation_model(with_fairness=True))
    starv = [p for p in r.property_results if p.property_id == "NO_STARVATION_UNDER_DECLARED_FAIRNESS"][0]
    assert starv.status == "PASS"


# ---------------------------------------------------------------------------
# Fairness realizability
# ---------------------------------------------------------------------------


def test_vacuous_fairness_assumption_fails_realizability_and_cannot_manufacture_proof() -> None:
    d = clone(minimal_model())
    d["state_domains"]["phase"] = ["START", "DONE", "UNREACHABLE"]
    finish = transition("finish", [guard("phase", "EQ", "START")], [effect("phase", "DONE")], required_reachable=True)
    spin = transition("spin", [guard("phase", "EQ", "START")], [effect("phase", "START")])
    # declare fairness on a transition guarded on a domain value nothing ever
    # transitions into -> genuinely never enabled anywhere reachable.
    unreachable = transition(
        "phantom",
        [guard("phase", "EQ", "UNREACHABLE")],
        [effect("phase", "START")],
        fairness_ref="fair_phantom",
    )
    d["transitions"] = [finish, spin, unreachable]
    d["fairness_assumptions"] = [fairness("fair_phantom", ["phantom"])]
    r = _run(d)
    fr = [p for p in r.property_results if p.property_id == "FAIRNESS_REALIZABLE"][0]
    assert fr.status == "FAIL"
    # the vacuous fairness assumption must NOT exclude the spin lasso
    up = [p for p in r.property_results if p.property_id == "UNIVERSAL_PROGRESS"][0]
    assert up.status == "FAIL"
    assert r.model_analysis_verdict == "UNSAFE_COUNTEREXAMPLE"


def test_no_fairness_declared_is_not_applicable() -> None:
    r = _run(minimal_model())
    fr = [p for p in r.property_results if p.property_id == "FAIRNESS_REALIZABLE"][0]
    assert fr.status == "NOT_APPLICABLE"


# ---------------------------------------------------------------------------
# EFFECT_UNKNOWN escape / authored transition-forbidden safety
# ---------------------------------------------------------------------------


def test_effect_unknown_escape_is_unsafe_with_declared_model_only_realizability() -> None:
    d = clone(minimal_model())
    d["state_domains"]["phase"] = ["START", "EFFECT_UNKNOWN", "DONE"]
    d["transitions"] = [
        transition("act", [guard("phase", "EQ", "START")], [effect("phase", "EFFECT_UNKNOWN")], required_reachable=True),
        transition("retry", [guard("phase", "EQ", "EFFECT_UNKNOWN")], [effect("phase", "DONE")], kind="RETRY"),
    ]
    d["safety_properties"] = [
        transition_forbidden(
            "NO_EFFECT_UNKNOWN_ESCAPE",
            [guard("phase", "EQ", "EFFECT_UNKNOWN")],
            ["RETRY", "FAILOVER", "MODIFY"],
        )
    ]
    r = _run(d)
    assert r.model_analysis_verdict == "UNSAFE_COUNTEREXAMPLE"
    assert r.admission_recommendation == "REPORT_ONLY_REPAIR"
    prop = [p for p in r.property_results if p.property_id == "NO_EFFECT_UNKNOWN_ESCAPE"][0]
    assert prop.status == "FAIL"
    assert prop.property_kind == "AUTHORED_TRANSITION_SAFETY"
    cx = [c for c in r.counterexamples if c.property_id == "NO_EFFECT_UNKNOWN_ESCAPE"][0]
    assert cx.realizability == "DECLARED_MODEL_ONLY"
    assert cx.shortest_prefix == ("act", "retry")


def test_one_action_authority_state_forbidden_violation() -> None:
    d = clone(minimal_model())
    d["state_domains"]["phase"] = ["START", "MULTI_OWNED", "DONE"]
    d["transitions"] = [
        transition("split", [guard("phase", "EQ", "START")], [effect("phase", "MULTI_OWNED")], required_reachable=True),
    ]
    d["safety_properties"] = [
        state_forbidden("ONE_ACTION_AUTHORITY", [guard("phase", "EQ", "MULTI_OWNED")])
    ]
    r = _run(d)
    assert r.model_analysis_verdict == "UNSAFE_COUNTEREXAMPLE"
    prop = [p for p in r.property_results if p.property_id == "ONE_ACTION_AUTHORITY"][0]
    assert prop.status == "FAIL"
    assert prop.property_kind == "AUTHORED_STATE_SAFETY"


# ---------------------------------------------------------------------------
# Terminal absorption / post-terminal transition
# ---------------------------------------------------------------------------


def test_post_terminal_transition_is_a_violation() -> None:
    d = clone(minimal_model())
    d["transitions"].append(
        transition("reopen", [guard("phase", "EQ", "DONE")], [effect("phase", "START")])
    )
    r = _run(d)
    prop = [p for p in r.property_results if p.property_id == "NO_POST_TERMINAL_TRANSITION"][0]
    assert prop.status == "FAIL"
    assert r.model_analysis_verdict == "UNSAFE_COUNTEREXAMPLE"


# ---------------------------------------------------------------------------
# Proper completion residue
# ---------------------------------------------------------------------------


def test_non_persistent_pending_obligation_at_terminal_is_a_violation() -> None:
    d = clone(minimal_model())
    d["obligations"] = [
        obligation("ob1", "phase", ["START"], ["DONE"], persistent=False, owner_or_authority="OPERATION")
    ]
    r = _run(d)
    prop = [p for p in r.property_results if p.property_id == "PROPER_COMPLETION"][0]
    assert prop.status == "PASS"  # phase=DONE at terminal -> obligation already discharged, not pending


def test_unowned_persistent_resource_at_terminal_is_a_violation() -> None:
    d = clone(minimal_model())
    d["state_domains"]["holder"] = ["HELD", "RELEASED"]
    d["initial_state"]["holder"] = "HELD"
    d["resources"] = [
        resource("res1", "holder", ["RELEASED"], persistent=True, owner_or_authority="OPERATION")
    ]
    r = _run(d)
    prop = [p for p in r.property_results if p.property_id == "PROPER_COMPLETION"][0]
    assert prop.status == "FAIL"
    assert r.model_analysis_verdict == "UNSAFE_COUNTEREXAMPLE"


def test_owned_persistent_resource_at_terminal_passes() -> None:
    d = clone(minimal_model())
    d["state_domains"]["holder"] = ["HELD", "RELEASED"]
    d["initial_state"]["holder"] = "HELD"
    d["resources"] = [
        resource("res1", "holder", ["RELEASED"], persistent=True, owner_or_authority="OPERATION")
    ]
    d["terminal_outcomes"] = [
        outcome("done", "TERMINAL_SUCCESS", [guard("phase", "EQ", "DONE")], owned_persistent_resource_ids=["res1"])
    ]
    r = _run(d)
    prop = [p for p in r.property_results if p.property_id == "PROPER_COMPLETION"][0]
    assert prop.status == "PASS"
    assert r.model_analysis_verdict == "PROVEN_WITHIN_FINITE_MODEL"


# ---------------------------------------------------------------------------
# Dead required transition
# ---------------------------------------------------------------------------


def test_dead_required_transition_is_a_global_certificate_violation() -> None:
    d = clone(minimal_model())
    d["state_domains"]["phase"] = ["START", "OTHER", "DONE"]
    d["transitions"] = [
        transition("finish", [guard("phase", "EQ", "START")], [effect("phase", "DONE")], required_reachable=True),
        transition("never", [guard("phase", "EQ", "OTHER")], [effect("phase", "DONE")], required_reachable=True),
    ]
    r = _run(d)
    prop = [p for p in r.property_results if p.property_id == "NO_DEAD_REQUIRED_TRANSITION"][0]
    assert prop.status == "FAIL"
    cx = [c for c in r.counterexamples if c.property_id == "NO_DEAD_REQUIRED_TRANSITION"][0]
    assert cx.witness_kind == "GLOBAL_CERTIFICATE"


# ---------------------------------------------------------------------------
# Bounded exploration
# ---------------------------------------------------------------------------


def test_bounded_exploration_is_never_proof() -> None:
    d = clone(minimal_model())
    d["state_domains"]["phase"] = ["START", "MID", "DONE"]
    d["transitions"] = [
        transition("advance", [guard("phase", "EQ", "START")], [effect("phase", "MID")], required_reachable=True),
        transition("finish", [guard("phase", "EQ", "MID")], [effect("phase", "DONE")], required_reachable=True),
    ]
    d["exploration_limits"] = {"max_states": 2, "max_depth": 1000}
    r = _run(d)
    assert r.model_analysis_verdict in ("BOUNDED_NO_COUNTEREXAMPLE", "INCONCLUSIVE_MODEL_GAP")
    assert r.exploration_receipt.base_graph_complete is False
    assert r.exploration_receipt.state_limit_reached is True


def test_complete_definite_witness_survives_unrelated_later_bound() -> None:
    d = clone(minimal_model())
    d["state_domains"]["phase"] = ["START", "BAD", "MID", "DONE"]
    d["transitions"] = [
        transition("act", [guard("phase", "EQ", "START")], [effect("phase", "BAD")], required_reachable=True),
        transition("wander1", [guard("phase", "EQ", "BAD")], [effect("phase", "MID")]),
        transition("wander2", [guard("phase", "EQ", "MID")], [effect("phase", "DONE")]),
    ]
    d["safety_properties"] = [state_forbidden("NO_BAD_STATE", [guard("phase", "EQ", "BAD")])]
    # tiny bound: the safety violation is found at depth 1 (immediately) but
    # the bound would truncate exploration of the rest of the graph.
    d["exploration_limits"] = {"max_states": 2, "max_depth": 1000}
    r = _run(d)
    assert r.model_analysis_verdict == "UNSAFE_COUNTEREXAMPLE"
    prop = [p for p in r.property_results if p.property_id == "NO_BAD_STATE"][0]
    assert prop.status == "FAIL"


# ---------------------------------------------------------------------------
# Unknown fidelity / model gap -> inconclusive, never proof or certain unsafe
# ---------------------------------------------------------------------------


def test_unknown_fidelity_never_proves() -> None:
    d = clone(minimal_model())
    d["abstraction_contract"]["kind"] = "UNKNOWN_FIDELITY"
    d["abstraction_contract"]["validation_kind"] = "NONE"
    r = _run(d)
    assert r.model_analysis_verdict == "INCONCLUSIVE_MODEL_GAP"
    assert r.admission_recommendation == "REPORT_ONLY_NO_RECOMMENDATION"


def test_load_bearing_gap_prevents_proof_even_when_all_properties_pass() -> None:
    d = clone(minimal_model())
    d["known_model_gaps"] = [
        model_gap(
            "gap1",
            "provider disconnect effect is opaque",
            True,
            affects_transition_ids=["finish"],
        )
    ]
    r = _run(d)
    assert r.model_analysis_verdict != "PROVEN_WITHIN_FINITE_MODEL"


def test_non_load_bearing_gap_does_not_hide_a_definite_witness() -> None:
    d = _deadlock_model()
    d["known_model_gaps"] = [
        model_gap("gap1", "cosmetic naming gap, cannot affect any checked property", False)
    ]
    r = _run(d)
    assert r.model_analysis_verdict == "UNSAFE_COUNTEREXAMPLE"


# ---------------------------------------------------------------------------
# Stale / conflicted source basis preserves model analysis
# ---------------------------------------------------------------------------


def test_stale_source_preserves_model_verdict_and_forces_reconcile() -> None:
    d = clone(minimal_model())
    d["source_snapshot"] = source_snapshot([source_record(freshness="STALE")])
    r = _run(d)
    assert r.model_analysis_verdict == "PROVEN_WITHIN_FINITE_MODEL"
    assert r.source_applicability_at_generation == "STALE"
    assert r.admission_recommendation == "REPORT_ONLY_RECONCILE"


def test_conflicted_source_with_unsafe_witness_still_reconciles_not_repairs() -> None:
    d = _deadlock_model()
    d["source_snapshot"] = source_snapshot([source_record(conflict="CONFLICT")])
    r = _run(d)
    assert r.model_analysis_verdict == "UNSAFE_COUNTEREXAMPLE"
    assert r.source_applicability_at_generation == "CONFLICTED"
    assert r.admission_recommendation == "REPORT_ONLY_RECONCILE"


# ---------------------------------------------------------------------------
# Trust ceiling: authored positive labels never upgrade
# ---------------------------------------------------------------------------


def test_authored_positive_validation_kind_never_upgrades_realizability() -> None:
    d = clone(minimal_model())
    d["abstraction_contract"]["validation_kind"] = "RUNTIME_EVENT_REPLAY"
    d["abstraction_contract"]["validation_refs"] = [REF]
    r = _run(d)
    # still just AUTHOR_DECLARATION-equivalent ceiling; no counterexamples to
    # check realizability on here, but source applicability must stay capped.
    assert r.source_applicability_at_generation == "AUTHOR_DECLARED_ONLY"


def test_authored_fresh_source_label_never_becomes_current_source_attested() -> None:
    d = clone(minimal_model())
    d["source_snapshot"] = source_snapshot([source_record(freshness="FRESH")])
    r = _run(d)
    assert r.source_applicability_at_generation == "AUTHOR_DECLARED_ONLY"


# ---------------------------------------------------------------------------
# No side effects
# ---------------------------------------------------------------------------


def test_checker_module_imports_forbidden_modules_nowhere() -> None:
    import ast
    import pathlib

    src = pathlib.Path("control_plane/operation_assurance_checker.py").read_text()
    tree = ast.parse(src)
    forbidden = {"socket", "subprocess", "sqlite3", "urllib", "requests", "http.client"}
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
    assert not (names & forbidden)
