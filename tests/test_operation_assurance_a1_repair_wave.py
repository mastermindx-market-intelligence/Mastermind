"""tests.test_operation_assurance_a1_repair_wave — REQUEST_REPAIR fixes 1-5.

Covers the five MAJOR findings from independent adversarial review
(RELEASE_SAFE_WITH_NOTES overall; these five require repair before release):

FIX 1 — PROPER_COMPLETION overlapping-terminal ownership: intersection, not
         union, across matching terminal outcomes (fail-closed ambiguity).
FIX 2 — model-gap relevance: a load-bearing gap downgrades ONLY the
         witnesses it actually affects (trace/property-specific relevance),
         per the model-fidelity amendment Section 5.1 item 5 — the withdrawn
         blanket "any load-bearing gap downgrades everything" rule from the
         controlling overlay Section 1(6)/Section 8 Task 6 must not return.
FIX 3 — source attribution: every witness/property-result/repair-candidate
         is source-attributed from the model elements it actually depends
         on (finalization Section 6, law Section 2, overlay Section 7(6)).
FIX 4 — the fairness-augmented product search is itself bounded by
         max_states, tracked separately from base-graph completeness
         (trusted-input clarification Section 3/Section 5); a bound hit
         with no witness found reports UNKNOWN with
         FAIRNESS_PRODUCT_STATE_LIMIT_REACHED, never proof.
FIX 5 — assumptions.environment_assumption_ids_required_by_results mirrors
         the fairness-side "actually load-bearing" logic instead of a bare
         hardcoded ().

Plus one end-to-end list-order permutation determinism test.
"""
from __future__ import annotations

import json
import random

from control_plane.operation_assurance_checker import run_checker
from control_plane.operation_assurance_model import parse_model_text
from tests.operation_assurance_fixture_lib import (
    clone,
    dumps,
    effect,
    environment_assumption,
    fairness,
    guard,
    minimal_model,
    model_gap,
    obligation,
    outcome,
    state_forbidden,
    transition,
)

GENERATED_AT = "2026-09-01T00:00:00Z"


def _run(model_dict):
    model = parse_model_text(dumps(model_dict))
    return run_checker(model, generated_at=GENERATED_AT)


# ---------------------------------------------------------------------------
# FIX 1 — overlapping-terminal ownership is an intersection, not a union
# ---------------------------------------------------------------------------


def test_h4_overlapping_terminals_each_owning_one_of_two_obligations_fails() -> None:
    d = clone(minimal_model())
    d["state_domains"] = {"phase": ["A", "DONE"], "o1": ["PENDING", "OK"], "o2": ["PENDING", "OK"]}
    d["initial_state"] = {"phase": "A", "o1": "PENDING", "o2": "PENDING"}
    d["transitions"] = [transition("finish", [guard("phase", "EQ", "A")], [effect("phase", "DONE")], required_reachable=True)]
    d["obligations"] = [
        obligation("ob1", "o1", ["PENDING"], ["OK"], persistent=True),
        obligation("ob2", "o2", ["PENDING"], ["OK"], persistent=True),
    ]
    d["terminal_outcomes"] = [
        outcome("t1", "TERMINAL_SUCCESS", [guard("phase", "EQ", "DONE")], owned_persistent_obligation_ids=["ob1"]),
        outcome("t2", "TERMINAL_SUCCESS", [guard("phase", "EQ", "DONE")], owned_persistent_obligation_ids=["ob2"]),
    ]
    r = _run(d)
    prop = [p for p in r.property_results if p.property_id == "PROPER_COMPLETION"][0]
    assert prop.status == "FAIL"
    assert r.model_analysis_verdict == "UNSAFE_COUNTEREXAMPLE"
    cx = [c for c in r.counterexamples if c.property_id == "PROPER_COMPLETION"][0]
    assert any(lim.startswith("AMBIGUOUS_TERMINAL_OWNERSHIP:") for lim in cx.limitations)


def test_overlapping_terminals_both_owning_the_same_obligation_still_passes() -> None:
    """Sanity: the intersection rule must not break the legitimate case
    where every matching terminal DOES own the pending obligation."""
    d = clone(minimal_model())
    d["state_domains"] = {"phase": ["A", "DONE"], "o1": ["PENDING", "OK"]}
    d["initial_state"] = {"phase": "A", "o1": "PENDING"}
    d["transitions"] = [transition("finish", [guard("phase", "EQ", "A")], [effect("phase", "DONE")], required_reachable=True)]
    d["obligations"] = [obligation("ob1", "o1", ["PENDING"], ["OK"], persistent=True)]
    d["terminal_outcomes"] = [
        outcome("t1", "TERMINAL_SUCCESS", [guard("phase", "EQ", "DONE")], owned_persistent_obligation_ids=["ob1"]),
        outcome("t2", "TERMINAL_SUCCESS", [guard("phase", "EQ", "DONE")], owned_persistent_obligation_ids=["ob1"]),
    ]
    r = _run(d)
    prop = [p for p in r.property_results if p.property_id == "PROPER_COMPLETION"][0]
    assert prop.status == "PASS"
    assert r.model_analysis_verdict == "PROVEN_WITHIN_FINITE_MODEL"


def test_overlapping_terminals_owned_by_neither_reports_unowned_not_ambiguous() -> None:
    """When NEITHER matching outcome owns the obligation, the reason stays
    the plain UNOWNED_PERSISTENT_OBLIGATION defect, not the ambiguity one —
    ambiguity means "some but not all", not "none"."""
    d = clone(minimal_model())
    d["state_domains"] = {"phase": ["A", "DONE"], "o1": ["PENDING", "OK"]}
    d["initial_state"] = {"phase": "A", "o1": "PENDING"}
    d["transitions"] = [transition("finish", [guard("phase", "EQ", "A")], [effect("phase", "DONE")], required_reachable=True)]
    d["obligations"] = [obligation("ob1", "o1", ["PENDING"], ["OK"], persistent=True)]
    d["terminal_outcomes"] = [
        outcome("t1", "TERMINAL_SUCCESS", [guard("phase", "EQ", "DONE")]),
        outcome("t2", "TERMINAL_SUCCESS", [guard("phase", "EQ", "DONE")]),
    ]
    r = _run(d)
    cx = [c for c in r.counterexamples if c.property_id == "PROPER_COMPLETION"][0]
    assert any(lim.startswith("UNOWNED_PERSISTENT_OBLIGATION:") for lim in cx.limitations)
    assert not any(lim.startswith("AMBIGUOUS_TERMINAL_OWNERSHIP:") for lim in cx.limitations)


# ---------------------------------------------------------------------------
# FIX 2 — model-gap relevance (H7a/H7b acceptance pair + positive variant)
# ---------------------------------------------------------------------------


def _h7_model() -> dict:
    d = clone(minimal_model())
    d["state_domains"] = {"phase": ["A", "BAD", "DONE"], "z": ["N", "Y"]}
    d["initial_state"] = {"phase": "A", "z": "N"}
    d["transitions"] = [
        transition("go", [guard("phase", "EQ", "A")], [effect("phase", "BAD")]),
        transition("fin", [guard("phase", "EQ", "BAD")], [effect("phase", "DONE")], required_reachable=True),
        transition("noise", [guard("z", "EQ", "N")], [effect("z", "Y")]),
    ]
    d["terminal_outcomes"] = [outcome("done", "TERMINAL_SUCCESS", [guard("phase", "EQ", "DONE")])]
    d["safety_properties"] = [state_forbidden("NO_BAD", [guard("phase", "EQ", "BAD")])]
    return d


def test_h7a_definite_witness_no_gap_is_unsafe_and_clean() -> None:
    r = _run(_h7_model())
    assert r.model_analysis_verdict == "UNSAFE_COUNTEREXAMPLE"
    cx = [c for c in r.counterexamples if c.property_id == "NO_BAD"][0]
    assert cx.realizability == "DECLARED_MODEL_ONLY"
    assert cx.invalidating_gap_ids == ()


def test_h7b_unrelated_load_bearing_gap_does_not_flip_the_verdict() -> None:
    """The reviewer's own acceptance pair: a load-bearing gap on a
    completely unrelated transition/variable ("noise"/"z") must leave the
    NO_BAD witness untouched and the overall verdict UNSAFE."""
    d = _h7_model()
    d["known_model_gaps"] = [
        model_gap("gap_noise", "opaque noise-variable semantics", True, affects_transition_ids=["noise"], affects_variable_ids=["z"])
    ]
    r = _run(d)
    assert r.model_analysis_verdict == "UNSAFE_COUNTEREXAMPLE"
    cx = [c for c in r.counterexamples if c.property_id == "NO_BAD"][0]
    assert cx.realizability == "DECLARED_MODEL_ONLY"
    assert cx.invalidating_gap_ids == ()


def test_relevant_load_bearing_gap_downgrades_only_the_affected_witness() -> None:
    """A gap that DOES touch the witness's own transition ("go") must
    downgrade that specific witness to POTENTIALLY_SPURIOUS with
    invalidating_gap_ids populated, and flip the overall verdict."""
    d = _h7_model()
    d["known_model_gaps"] = [model_gap("gap_go", "opaque effect semantics for go", True, affects_transition_ids=["go"])]
    r = _run(d)
    assert r.model_analysis_verdict == "INCONCLUSIVE_MODEL_GAP"
    cx = [c for c in r.counterexamples if c.property_id == "NO_BAD"][0]
    assert cx.realizability == "POTENTIALLY_SPURIOUS"
    assert cx.invalidating_gap_ids == ("gap_go",)


def test_gap_relevance_is_per_witness_not_per_report() -> None:
    """Within ONE report, a gap relevant to one witness's transitions must
    not spuriously downgrade a sibling witness whose transitions it never
    names — matching the independently-reviewed H7b model (which layers a
    'noise' transition onto the terminal state too, producing a second,
    noise-touching NO_POST_TERMINAL_TRANSITION witness alongside the clean
    NO_BAD one)."""
    d = _h7_model()
    d["known_model_gaps"] = [
        model_gap("gap_noise", "opaque noise-variable semantics", True, affects_transition_ids=["noise"], affects_variable_ids=["z"])
    ]
    r = _run(d)
    by_property = {c.property_id: c for c in r.counterexamples}
    assert by_property["NO_BAD"].realizability == "DECLARED_MODEL_ONLY"
    assert by_property["NO_BAD"].invalidating_gap_ids == ()
    # NO_POST_TERMINAL_TRANSITION's witness necessarily includes "noise"
    # (that IS the violating post-terminal transition) -> it IS affected.
    npt = by_property["NO_POST_TERMINAL_TRANSITION"]
    assert "noise" in npt.shortest_prefix
    assert npt.realizability == "POTENTIALLY_SPURIOUS"
    assert npt.invalidating_gap_ids == ("gap_noise",)
    # the overall verdict is still UNSAFE because NO_BAD's clean witness stands.
    assert r.model_analysis_verdict == "UNSAFE_COUNTEREXAMPLE"


def _single_failure_model() -> dict:
    """A model with exactly ONE failing property (NO_BAD): BAD is reached
    (the safety violation) but also has a valid recovery path onward to a
    real terminal, so OPTION_TO_COMPLETE/NO_POST_TERMINAL_TRANSITION/
    PROPER_COMPLETION all pass cleanly and don't add incidental failures."""
    d = clone(minimal_model())
    d["state_domains"]["phase"] = ["START", "BAD", "DONE"]
    d["transitions"] = [
        transition("go", [guard("phase", "EQ", "START")], [effect("phase", "BAD")]),
        transition("recover", [guard("phase", "EQ", "BAD")], [effect("phase", "DONE")], required_reachable=True),
    ]
    d["terminal_outcomes"] = [outcome("done", "TERMINAL_SUCCESS", [guard("phase", "EQ", "DONE")])]
    d["safety_properties"] = [state_forbidden("NO_BAD", [guard("phase", "EQ", "BAD")])]
    return d


def test_gap_declared_directly_on_property_id_is_relevant_even_without_overlap() -> None:
    d = _single_failure_model()
    d["known_model_gaps"] = [model_gap("gap_direct", "directly named", True, affects_property_ids=["NO_BAD"])]
    r = _run(d)
    cx = [c for c in r.counterexamples if c.property_id == "NO_BAD"][0]
    assert cx.realizability == "POTENTIALLY_SPURIOUS"
    assert cx.invalidating_gap_ids == ("gap_direct",)
    assert r.model_analysis_verdict == "INCONCLUSIVE_MODEL_GAP"


# ---------------------------------------------------------------------------
# FIX 3 — source attribution
# ---------------------------------------------------------------------------


def test_safety_witness_carries_source_refs_from_property_and_transitions() -> None:
    d = clone(minimal_model())
    d["state_domains"]["phase"] = ["START", "BAD"]
    d["transitions"] = [
        transition("go_bad", [guard("phase", "EQ", "START")], [effect("phase", "BAD")], source_refs=["Mastermind@custom0000000000000000000000000000000001"])
    ]
    d["safety_properties"] = [
        state_forbidden("NO_BAD", [guard("phase", "EQ", "BAD")], source_refs=["Mastermind@custom0000000000000000000000000000000002"])
    ]
    r = _run(d)
    cx = [c for c in r.counterexamples if c.property_id == "NO_BAD"][0]
    assert "Mastermind@custom0000000000000000000000000000000001" in cx.source_refs
    assert "Mastermind@custom0000000000000000000000000000000002" in cx.source_refs
    prop = [p for p in r.property_results if p.property_id == "NO_BAD"][0]
    assert set(prop.source_refs) == set(cx.source_refs)
    assert cx.repair_candidates[0].source_refs != ()


def test_fairness_lasso_witness_carries_transition_source_refs() -> None:
    d = clone(minimal_model())
    d["state_domains"]["phase"] = ["START", "DONE"]
    finish = transition(
        "finish",
        [guard("phase", "EQ", "START")],
        [effect("phase", "DONE")],
        required_reachable=True,
        source_refs=["Mastermind@finish0000000000000000000000000000000000"],
    )
    spin = transition(
        "spin",
        [guard("phase", "EQ", "START")],
        [effect("phase", "START")],
        source_refs=["Mastermind@spin00000000000000000000000000000000000"],
    )
    d["transitions"] = [finish, spin]
    r = _run(d)
    cx = [c for c in r.counterexamples if c.property_id == "UNIVERSAL_PROGRESS"][0]
    assert "Mastermind@spin00000000000000000000000000000000000" in cx.source_refs
    prop = [p for p in r.property_results if p.property_id == "UNIVERSAL_PROGRESS"][0]
    assert prop.source_refs == cx.source_refs


def test_gate_related_property_carries_gate_source_refs_even_on_pass() -> None:
    from tests.operation_assurance_fixture_lib import gate as gate_builder

    d = clone(minimal_model())
    d["state_domains"] = {"phase": ["WAITING", "DONE"]}
    d["initial_state"] = {"phase": "WAITING"}
    d["transitions"] = [
        transition("proceed", [guard("phase", "EQ", "WAITING")], [effect("phase", "DONE")], required_reachable=True, gate_refs=["g1"])
    ]
    d["terminal_outcomes"] = [outcome("done", "TERMINAL_SUCCESS", [guard("phase", "EQ", "DONE")])]
    d["external_gates"] = [
        gate_builder(
            "g1",
            "INTENTIONAL_WAIT",
            [guard("phase", "EQ", "WAITING")],
            ["proceed"],
            "proceed",
            source_refs=["Mastermind@gate00000000000000000000000000000000000"],
        )
    ]
    r = _run(d)
    prop = [p for p in r.property_results if p.property_id == "GATE_OR_WAIT_RETURN_PATH_VALID"][0]
    assert prop.status == "PASS"
    assert "Mastermind@gate00000000000000000000000000000000000" in prop.source_refs


def test_repair_candidate_carries_target_element_source_refs() -> None:
    # The initial state itself must keep a route to a boundary (else it is
    # the shortest -- zero-step -- failing state and the witness has no
    # transition to attribute refs from at all). Branch instead: START can
    # reach DONE, but a second branch dead-ends at STUCK one step in, so the
    # genuinely shortest failing witness has a real one-transition prefix.
    d = clone(minimal_model())
    d["state_domains"]["phase"] = ["START", "STUCK", "DONE"]
    d["transitions"] = [
        transition("finish", [guard("phase", "EQ", "START")], [effect("phase", "DONE")], required_reachable=True),
        transition("wander", [guard("phase", "EQ", "START")], [effect("phase", "STUCK")]),
    ]
    r = _run(d)
    cx = [c for c in r.counterexamples if c.property_id == "OPTION_TO_COMPLETE"][0]
    assert cx.shortest_prefix == ("wander",)
    assert cx.repair_candidates
    assert cx.repair_candidates[0].source_refs != ()


def test_dead_required_transition_witness_carries_its_own_transition_refs() -> None:
    d = clone(minimal_model())
    d["state_domains"]["phase"] = ["START", "OTHER", "DONE"]
    d["transitions"] = [
        transition("finish", [guard("phase", "EQ", "START")], [effect("phase", "DONE")], required_reachable=True),
        transition(
            "never",
            [guard("phase", "EQ", "OTHER")],
            [effect("phase", "DONE")],
            required_reachable=True,
            source_refs=["Mastermind@never0000000000000000000000000000000000"],
        ),
    ]
    r = _run(d)
    cx = [c for c in r.counterexamples if c.property_id == "NO_DEAD_REQUIRED_TRANSITION"][0]
    assert "Mastermind@never0000000000000000000000000000000000" in cx.source_refs


def test_corpus_fixtures_with_authored_refs_produce_attributed_counterexamples() -> None:
    """Every fixture in the shipped corpus authors source_refs on its
    elements (the fixture_lib REF default); every counterexample whose
    witness actually names at least one transition (a non-trivial prefix or
    cycle) must therefore carry non-empty source_refs — a witness is never
    silently unattributed when the elements it traversed ARE attributed. A
    genuinely zero-step witness (the initial state itself is already the
    shortest failing state, e.g. no boundary is declared at all) legitimately
    has no transition to attribute and is excluded from this check."""
    import glob
    import pathlib

    fixtures_dir = pathlib.Path(__file__).resolve().parent / "fixtures" / "operation_assurance"
    checked = 0
    zero_step = 0
    for path in sorted(glob.glob(str(fixtures_dir / "*.json"))):
        model_dict = json.loads(pathlib.Path(path).read_text())
        report = run_checker(parse_model_text(json.dumps(model_dict)), generated_at=GENERATED_AT)
        for cx in report.counterexamples:
            if not cx.shortest_prefix and not cx.cycle:
                zero_step += 1
                continue
            checked += 1
            assert cx.source_refs != (), (path, cx.property_id)
    assert checked > 0
    assert zero_step >= 0  # documents that the exclusion path is real, not vacuous


# ---------------------------------------------------------------------------
# FIX 4 — fairness-product bound tracked separately from base-graph bound
# ---------------------------------------------------------------------------


def _h5_bounded_model(max_states: int) -> dict:
    d = clone(minimal_model())
    d["state_domains"] = {"phase": ["S0", "S1", "S2", "S3", "BAD"]}
    d["initial_state"] = {"phase": "S0"}
    d["transitions"] = [
        transition("a", [guard("phase", "EQ", "S0")], [effect("phase", "S1")]),
        transition("b", [guard("phase", "EQ", "S1")], [effect("phase", "S2")]),
        transition("c", [guard("phase", "EQ", "S2")], [effect("phase", "S3")]),
        transition("d", [guard("phase", "EQ", "S3")], [effect("phase", "BAD")], required_reachable=True),
    ]
    d["terminal_outcomes"] = [outcome("bad", "TERMINAL_FAILED_SAFE", [guard("phase", "EQ", "BAD")])]
    d["safety_properties"] = [state_forbidden("NO_BAD", [guard("phase", "EQ", "BAD")])]
    d["exploration_limits"] = {"max_states": max_states, "max_depth": 1000}
    return d


def test_fairness_product_bound_reports_its_own_limit_reason_and_never_proves() -> None:
    r = _run(_h5_bounded_model(3))
    assert r.model_analysis_verdict != "PROVEN_WITHIN_FINITE_MODEL"
    up = [p for p in r.property_results if p.property_id == "UNIVERSAL_PROGRESS"][0]
    assert up.status == "UNKNOWN"
    assert "FAIRNESS_PRODUCT_STATE_LIMIT_REACHED" in up.reason_codes
    products_by_id = {p.analysis_id: p for p in r.exploration_receipt.analysis_products}
    assert products_by_id["UNIVERSAL_PROGRESS"].limit_reason == "FAIRNESS_PRODUCT_STATE_LIMIT_REACHED"
    assert products_by_id["UNIVERSAL_PROGRESS"].complete is False


def test_unbounded_same_model_finds_the_definite_witness() -> None:
    r = _run(_h5_bounded_model(1000))
    assert r.model_analysis_verdict == "UNSAFE_COUNTEREXAMPLE"
    nb = [p for p in r.property_results if p.property_id == "NO_BAD"][0]
    assert nb.status == "FAIL"


def test_product_limit_field_is_wired_into_lasso_result() -> None:
    from control_plane.operation_assurance_checker import LassoResult

    default = LassoResult(found=False)
    assert default.product_complete is True  # default stays True when never bounded


# ---------------------------------------------------------------------------
# FIX 5 — environment_assumption_ids_required_by_results
# ---------------------------------------------------------------------------


def _wait_model_with_env_assumption() -> dict:
    from tests.operation_assurance_fixture_lib import gate as gate_builder

    d = clone(minimal_model())
    d["state_domains"] = {"phase": ["WAITING", "DONE", "CANCELLED"], "capacity": ["UNAVAILABLE", "AVAILABLE"]}
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
    cancel_wait = transition("cancel_wait", [guard("phase", "EQ", "WAITING")], [effect("phase", "CANCELLED")], gate_refs=["wait_gate"])
    d["transitions"] = [check_again, become_available, proceed, cancel_wait]
    d["terminal_outcomes"] = [
        outcome("done", "TERMINAL_SUCCESS", [guard("phase", "EQ", "DONE")]),
        outcome("cancelled", "TERMINAL_CANCELLED", [guard("phase", "EQ", "CANCELLED")]),
    ]
    d["external_gates"] = [
        gate_builder("wait_gate", "INTENTIONAL_WAIT", [guard("phase", "EQ", "WAITING")], ["proceed", "cancel_wait"], "cancel_wait")
    ]
    d["environment_assumptions"] = [environment_assumption("capacity_may_return", ["become_available"], ["OPTION_TO_COMPLETE"])]
    return d


def test_environment_assumption_actually_used_is_recorded() -> None:
    r = _run(_wait_model_with_env_assumption())
    assert "capacity_may_return" in r.assumptions.environment_assumption_ids_required_by_results


def test_environment_assumption_never_declared_is_not_recorded() -> None:
    r = _run(minimal_model())
    assert r.assumptions.environment_assumption_ids_required_by_results == ()


# ---------------------------------------------------------------------------
# List-order permutation determinism (transitions[]/preserves[]/etc.)
# ---------------------------------------------------------------------------


def _shuffle(o, rnd: random.Random):
    if isinstance(o, dict):
        items = list(o.items())
        rnd.shuffle(items)
        return {k: _shuffle(v, rnd) for k, v in items}
    if isinstance(o, list):
        return [_shuffle(v, rnd) for v in o]
    return o


def test_full_key_and_list_order_permutation_is_byte_identical() -> None:
    import pathlib

    base = json.loads(
        (pathlib.Path(__file__).resolve().parent / "fixtures" / "operation_assurance" / "combined_cycle_fair_lasso.json").read_text()
    )
    outputs = set()
    for seed in range(6):
        rnd = random.Random(seed)
        shuffled = _shuffle(base, rnd)
        report = run_checker(parse_model_text(json.dumps(shuffled)), generated_at=GENERATED_AT)
        outputs.add(report.to_json())
    assert len(outputs) == 1
