"""tests.test_operation_assurance_a2_end_to_end — OLS-A2 through the
PROTECTED, UNCHANGED OLS-A1 engine.

Proves the three end-to-end behaviors the OLS-A2 packet commissions (design
Section 6 + implementation-wave FROZEN SPEC end-to-end item):
    1. hostile fixture (real byte-exact capture at Agent OS revision
       a3f6ef40d41e6d308c8d8cdc35f76802cd0525e4) -> compiled model parses
       under the protected A1 parser -> checker runs -> report shows
       non-current applicability, SOUND_OVERAPPROXIMATION, and never PROVEN.
    2. black-hole fixture -> the compiled model detects a real,
       source-attributed no-progress witness. See DEVIATIONS in the return
       packet for why the top-level verdict is INCONCLUSIVE_MODEL_GAP, not
       UNSAFE_COUNTEREXAMPLE — that value is MECHANICALLY unreachable once
       abstraction_contract.kind is SOUND_OVERAPPROXIMATION
       (control_plane.operation_assurance_checker._fidelity_proof_eligible),
       which this vertical is required to always emit and never override.
    3. corrected fixture -> a valid, degraded-but-coherent compilation with
       zero FAIL property results.

This module NEVER imports operation_assurance_sources/compiler production
internals to fake a result — every model here is produced by the real
gather -> Steward -> compile pipeline and then handed unmodified to the
PROTECTED control_plane.operation_assurance_checker/model/report modules.
"""
from __future__ import annotations

from pathlib import Path

from control_plane.operation_assurance_checker import run_checker
from control_plane.operation_assurance_compiler import compile_operation_assurance_model
from control_plane.operation_assurance_model import parse_model_bytes
from control_plane.operation_assurance_sources import gather_agent_os_source_facts

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "operation_assurance_a2"
REV = "a3f6ef40d41e6d308c8d8cdc35f76802cd0525e4"
OBSERVED_AT = "2026-09-02T00:00:00Z"
REPO = "mastermindx-market-intelligence/macro"


def test_hostile_fixture_is_the_exact_pinned_revision() -> None:
    facts = gather_agent_os_source_facts(FIXTURES / "hostile", repo=REPO, revision=REV, observed_at=OBSERVED_AT)
    ws = next(f for f in facts.facts if f.path.endswith("WS-OPERATION-ASSURANCE.md"))
    assert ws.revision == REV


def test_1_hostile_end_to_end_through_the_protected_a1_engine() -> None:
    import json

    facts = gather_agent_os_source_facts(FIXTURES / "hostile", repo=REPO, revision=REV, observed_at=OBSERVED_AT)
    model = compile_operation_assurance_model(facts)

    # the model really does round-trip through the protected parser's own
    # bytes-in entry point (not just constructed and trusted in-process).
    raw = json.dumps(model.to_dict()).encode("utf-8")
    reparsed = parse_model_bytes(raw)
    assert reparsed.model_hash == model.model_hash

    report = run_checker(reparsed, generated_at=OBSERVED_AT)

    assert report.abstraction_contract.kind == "SOUND_OVERAPPROXIMATION"
    assert report.model_analysis_verdict != "PROVEN_WITHIN_FINITE_MODEL"
    assert report.source_applicability_at_generation != "AUTHOR_DECLARED_ONLY"  # non-current, never "healthy"
    assert report.source_applicability_at_generation == "UNKNOWN"


def test_2_black_hole_fixture_yields_a_real_source_attributed_witness() -> None:
    import json

    facts = gather_agent_os_source_facts(FIXTURES / "black_hole", repo=REPO, revision=REV, observed_at=OBSERVED_AT)
    model = compile_operation_assurance_model(facts)
    raw = json.dumps(model.to_dict()).encode("utf-8")
    reparsed = parse_model_bytes(raw)
    report = run_checker(reparsed, generated_at=OBSERVED_AT)

    assert report.progress_disposition == "NO_PROGRESS"
    dead_transition = next(r for r in report.property_results if r.property_id == "NO_DEAD_REQUIRED_TRANSITION")
    assert dead_transition.status == "FAIL"
    cx = next(c for c in report.counterexamples if c.counterexample_id == dead_transition.counterexample_id)
    assert cx.source_refs, "the witness must name the offending wave's record"
    ws_fact = next(f for f in facts.facts if f.path.endswith("WS-OPERATION-ASSURANCE.md"))
    assert any(ws_fact.path in ref for ref in cx.source_refs)

    # MECHANIZED, not a design-doc opinion: UNSAFE_COUNTEREXAMPLE is
    # unreachable whenever abstraction_contract.kind != DECLARED_EXACT (see
    # control_plane.operation_assurance_checker._fidelity_proof_eligible and
    # _run_checker_inner's "elif any_fail and not fidelity_ok:" branch,
    # which unconditionally routes to INCONCLUSIVE_MODEL_GAP and downgrades
    # every counterexample's realizability to POTENTIALLY_SPURIOUS). Since
    # this vertical's abstraction_contract.kind is ALWAYS
    # SOUND_OVERAPPROXIMATION by mandate, UNSAFE_COUNTEREXAMPLE can never be
    # this vertical's verdict for ANY fixture — pinned here so a future
    # change to either module is caught rather than silently drifting.
    assert report.model_analysis_verdict == "INCONCLUSIVE_MODEL_GAP"
    assert cx.realizability == "POTENTIALLY_SPURIOUS"


def test_3_corrected_fixture_is_a_valid_degraded_but_coherent_compilation() -> None:
    import json

    facts = gather_agent_os_source_facts(FIXTURES / "corrected", repo=REPO, revision=REV, observed_at=OBSERVED_AT)
    model = compile_operation_assurance_model(facts)
    raw = json.dumps(model.to_dict()).encode("utf-8")
    reparsed = parse_model_bytes(raw)
    report = run_checker(reparsed, generated_at=OBSERVED_AT)

    fails = [r for r in report.property_results if r.status == "FAIL"]
    assert fails == []
    assert report.model_analysis_verdict == "INCONCLUSIVE_MODEL_GAP"  # capped: load-bearing gaps + SOUND_OVERAPPROXIMATION
    assert report.model_analysis_verdict != "PROVEN_WITHIN_FINITE_MODEL"
    assert report.progress_disposition in ("AUTONOMOUSLY_LIVE", "EXTERNALLY_GATED", "INTENTIONAL_WAIT", "RECURRING_SERVICE")


def test_determinism_byte_identical_output_across_runs() -> None:
    facts_a = gather_agent_os_source_facts(FIXTURES / "hostile", repo=REPO, revision=REV, observed_at=OBSERVED_AT)
    facts_b = gather_agent_os_source_facts(FIXTURES / "hostile", repo=REPO, revision=REV, observed_at=OBSERVED_AT)
    model_a = compile_operation_assurance_model(facts_a)
    model_b = compile_operation_assurance_model(facts_b)
    assert model_a.to_dict() == model_b.to_dict()
    assert model_a.model_hash == model_b.model_hash

    report_a = run_checker(model_a, generated_at=OBSERVED_AT)
    report_b = run_checker(model_b, generated_at=OBSERVED_AT)
    assert report_a.to_dict() == report_b.to_dict()
