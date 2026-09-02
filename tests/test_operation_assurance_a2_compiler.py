"""tests.test_operation_assurance_a2_compiler — OLS-A2 pure source compiler.

Covers control_plane.operation_assurance_compiler: Steward composition is
mandatory and real, freshness is always UNKNOWN, wave/dependency mapping,
per-element source_refs, and the mechanized SOUND_OVERAPPROXIMATION fidelity
ceiling (design Sections 2 and 5).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from control_plane.operation_assurance_compiler import CompilerError, compile_operation_assurance_model
from control_plane.operation_assurance_sources import gather_agent_os_source_facts

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "operation_assurance_a2"
REV = "a3f6ef40d41e6d308c8d8cdc35f76802cd0525e4"


def _facts(name: str, **overrides):
    kwargs = dict(repo="mastermindx-market-intelligence/macro", revision=REV, observed_at="2026-09-02T00:00:00Z")
    kwargs.update(overrides)
    return gather_agent_os_source_facts(FIXTURES / name, **kwargs)


def _compile(name: str, **overrides):
    return compile_operation_assurance_model(_facts(name, **overrides))


# ---------------------------------------------------------------------------
# Refusals mirror the adapter's SOURCE_* states 1:1 (design Section 9: fail
# closed, never an apparently healthy compilation)
# ---------------------------------------------------------------------------


def test_missing_target_refuses_with_source_missing() -> None:
    with pytest.raises(CompilerError) as exc:
        _compile("missing")
    assert exc.value.reason_code == "SOURCE_MISSING"


def test_conflicted_target_refuses_with_source_conflicted() -> None:
    with pytest.raises(CompilerError) as exc:
        _compile("conflict")
    assert exc.value.reason_code == "SOURCE_CONFLICTED"


def test_malformed_target_refuses_with_source_partial() -> None:
    with pytest.raises(CompilerError) as exc:
        _compile("malformed")
    assert exc.value.reason_code == "SOURCE_PARTIAL"


def test_truncated_target_refuses_with_source_truncated() -> None:
    with pytest.raises(CompilerError) as exc:
        _compile("truncated")
    assert exc.value.reason_code == "SOURCE_TRUNCATED"


# ---------------------------------------------------------------------------
# Mandatory proof ceiling (design Section 5)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["hostile", "corrected", "black_hole", "wait_gate"])
def test_abstraction_contract_is_always_sound_overapproximation_never_declared_exact(name: str) -> None:
    model = _compile(name)
    assert model.abstraction_contract.kind == "SOUND_OVERAPPROXIMATION"
    assert model.abstraction_contract.kind != "DECLARED_EXACT"


@pytest.mark.parametrize("name", ["hostile", "corrected", "black_hole", "wait_gate"])
def test_source_snapshot_freshness_is_always_unknown_never_current_or_fresh(name: str) -> None:
    model = _compile(name)
    assert model.source_snapshot.sources, "expected at least one disclosed source"
    for record in model.source_snapshot.sources:
        assert record.freshness == "UNKNOWN"


@pytest.mark.parametrize("name", ["hostile", "corrected", "black_hole", "wait_gate"])
def test_known_model_gaps_disclose_the_unsupported_property_subset(name: str) -> None:
    model = _compile(name)
    gap_ids = {g.gap_id for g in model.known_model_gaps}
    assert "unsupported_starvation_and_fairness_realizability" in gap_ids
    assert "unsupported_recurring_progress_validity" in gap_ids
    for gap in model.known_model_gaps:
        assert gap.load_bearing is True


def test_compiler_invocation_mode_is_authored_input() -> None:
    # forced by the protected A1 parser regardless of gather-vs-facts mode
    model = _compile("hostile")
    assert model.compiler.invocation_mode == "AUTHORED_INPUT"
    assert model.compiler.name


# ---------------------------------------------------------------------------
# Wave -> state mapping (design Section 5)
# ---------------------------------------------------------------------------


def test_hostile_compiles_nine_wave_variables_with_closed_marking_domain() -> None:
    model = _compile("hostile")
    domains = model.domains_dict()
    assert len(domains) == 9  # R0, A1..A8
    for values in domains.values():
        assert set(values) == {"PENDING", "ACTIVE", "DONE", "DROPPED"}
    initial = model.initial_state_dict()
    assert initial["wave_r0"] == "DONE"
    assert initial["wave_a1"] == "DONE"
    assert initial["wave_a2"] == "ACTIVE"  # in_progress
    assert initial["wave_a3"] == "PENDING"  # todo


def test_depends_on_becomes_a_gating_transition_guard() -> None:
    model = _compile("hostile")
    start_a3 = next(t for t in model.transitions if t.transition_id == "start_a3")
    variables_guarded = {g.variable for g in start_a3.guards}
    assert "wave_a3" in variables_guarded
    assert "wave_a2" in variables_guarded
    dep_guard = next(g for g in start_a3.guards if g.variable == "wave_a2")
    assert dep_guard.op == "IN"
    assert set(dep_guard.value) == {"DONE", "DROPPED"}


def test_next_action_becomes_an_obligation_owned_by_the_derived_seat() -> None:
    model = _compile("hostile")
    obligation = next(o for o in model.obligations if o.obligation_id == "next_action_a2")
    assert obligation.state_variable == "wave_a2"
    assert obligation.owner_or_authority == "COO"
    assert "DONE" in obligation.discharged_values
    assert obligation.source_refs


def test_black_hole_wave_has_zero_outgoing_transitions() -> None:
    model = _compile("black_hole")
    # STUCK never appears as an EFFECT (nothing ever writes its variable);
    # it may still appear as a GUARD on a downstream dependent's transition
    # (that dependent's own required transition is exactly the
    # NO_DEAD_REQUIRED_TRANSITION witness this fixture exists to produce).
    stuck_effect_transitions = [t for t in model.transitions if any(e.variable == "wave_stuck" for e in t.effects)]
    assert stuck_effect_transitions == []
    assert "next_action_stuck" not in {o.obligation_id for o in model.obligations}


def test_wait_mapping_produces_a_typed_external_gate() -> None:
    model = _compile("wait_gate")
    assert len(model.external_gates) == 1
    gate = model.external_gates[0]
    assert gate.disposition == "EXTERNAL_GATE"
    assert gate.owner_or_authority == "COO"
    finish = next(t for t in model.transitions if gate.gate_id in t.gate_refs)
    assert finish.required_reachable is False


def test_terminal_outcome_requires_every_wave_resolved() -> None:
    model = _compile("hostile")
    outcome = model.terminal_outcomes[0]
    guarded_vars = {g.variable for g in outcome.guards}
    assert guarded_vars == set(model.domains_dict().keys())


# ---------------------------------------------------------------------------
# source_refs: every compiler-authored element must carry at least one, and
# the full un-abbreviated repo@revision:path#sha256:digest string is
# recorded verbatim somewhere in the model for full-fidelity disclosure
# (design Section 3 "content-bound source receipts"; DEVIATIONS explains why
# the per-element token itself is a compact, schema-legal encoding instead).
# ---------------------------------------------------------------------------


def test_every_compiled_element_carries_nonempty_source_refs() -> None:
    model = _compile("hostile")
    for t in model.transitions:
        assert t.source_refs, t.transition_id
    for o in model.obligations:
        assert o.source_refs, o.obligation_id
    for outcome in model.terminal_outcomes:
        assert outcome.source_refs


def test_full_fidelity_source_string_is_recorded_verbatim_in_notes() -> None:
    facts = _facts("hostile")
    model = compile_operation_assurance_model(facts)
    ws_fact = next(f for f in facts.facts if f.path.endswith("WS-OPERATION-ASSURANCE.md"))
    expected = f"source: {ws_fact.repo}@{ws_fact.revision}:{ws_fact.path}#sha256:{ws_fact.content_digest}"
    assert expected in model.abstraction_contract.notes


# ---------------------------------------------------------------------------
# Determinism (design "byte-identical output across runs and under input
# key permutation")
# ---------------------------------------------------------------------------


def test_compile_is_deterministic_across_repeated_calls() -> None:
    facts = _facts("hostile")
    m1 = compile_operation_assurance_model(facts)
    m2 = compile_operation_assurance_model(facts)
    assert m1.model_hash == m2.model_hash
    assert m1.to_dict() == m2.to_dict()


def test_compile_is_deterministic_under_fact_list_permutation() -> None:
    import dataclasses

    facts = _facts("hostile")
    reversed_facts = dataclasses.replace(facts, facts=tuple(reversed(facts.facts)))
    m1 = compile_operation_assurance_model(facts)
    m2 = compile_operation_assurance_model(reversed_facts)
    assert m1.model_hash == m2.model_hash
