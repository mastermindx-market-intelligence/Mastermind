"""tests.test_operation_assurance_fixtures — frozen OLS-A1 fixture corpus.

Pins the exact verdict/applicability/disposition/recommendation for every
required fixture named in
docs/superpowers/plans/2026-08-30-operation-assurance-core.md Section 17
Task 7 (the file-map/task-order scaffold that wins on exact fixture *names*
per the 2026-08-31 finalization's precedence carve-out), corrected per the
controlling execution overlay's Section 9 expectation table for the fixtures
it names in common.

Also proves the CLI end-to-end over real on-disk fixture files (not just
inline models), for both the file-path and stdin invocation forms.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from control_plane.operation_assurance_checker import run_checker
from control_plane.operation_assurance_model import parse_model_text

ROOT = Path(__file__).resolve().parents[1]
FIXTURES_DIR = ROOT / "tests" / "fixtures" / "operation_assurance"
CLI = ROOT / "scripts" / "operation_assurance.py"
GENERATED_AT = "2026-08-30T12:00:00Z"

# name -> (model_analysis_verdict, source_applicability_at_generation, progress_disposition, admission_recommendation)
EXPECTED = {
    "safe_finite": ("PROVEN_WITHIN_FINITE_MODEL", "AUTHOR_DECLARED_ONLY", "AUTONOMOUSLY_LIVE", "REPORT_ONLY_NO_RECOMMENDATION"),
    "effect_unknown_failover": ("UNSAFE_COUNTEREXAMPLE", "AUTHOR_DECLARED_ONLY", "AUTONOMOUSLY_LIVE", "REPORT_ONLY_REPAIR"),
    "ownerless_modifying_transition": ("UNSAFE_COUNTEREXAMPLE", "AUTHOR_DECLARED_ONLY", "NO_PROGRESS", "REPORT_ONLY_REPAIR"),
    "carrier_split": ("UNSAFE_COUNTEREXAMPLE", "AUTHOR_DECLARED_ONLY", "AUTONOMOUSLY_LIVE", "REPORT_ONLY_REPAIR"),
    "stranded_parent": ("UNSAFE_COUNTEREXAMPLE", "AUTHOR_DECLARED_ONLY", "AUTONOMOUSLY_LIVE", "REPORT_ONLY_REPAIR"),
    "stale_binding": ("PROVEN_WITHIN_FINITE_MODEL", "STALE", "AUTONOMOUSLY_LIVE", "REPORT_ONLY_RECONCILE"),
    "stale_projection": ("PROVEN_WITHIN_FINITE_MODEL", "CONFLICTED", "AUTONOMOUSLY_LIVE", "REPORT_ONLY_RECONCILE"),
    "chairman_external_gate": ("PROVEN_WITHIN_FINITE_MODEL", "AUTHOR_DECLARED_ONLY", "EXTERNALLY_GATED", "REPORT_ONLY_AWAIT_GATE"),
    "capacity_valid_wait": ("PROVEN_WITHIN_FINITE_MODEL", "AUTHOR_DECLARED_ONLY", "INTENTIONAL_WAIT", "REPORT_ONLY_AWAIT_GATE"),
    "natural_time_wait": ("PROVEN_WITHIN_FINITE_MODEL", "AUTHOR_DECLARED_ONLY", "INTENTIONAL_WAIT", "REPORT_ONLY_AWAIT_GATE"),
    "recurring_service": ("PROVEN_WITHIN_FINITE_MODEL", "AUTHOR_DECLARED_ONLY", "RECURRING_SERVICE", "REPORT_ONLY_NO_RECOMMENDATION"),
    "safe_cancellation": ("PROVEN_WITHIN_FINITE_MODEL", "AUTHOR_DECLARED_ONLY", "AUTONOMOUSLY_LIVE", "REPORT_ONLY_NO_RECOMMENDATION"),
    "weak_fair_progress": ("PROVEN_WITHIN_FINITE_MODEL", "AUTHOR_DECLARED_ONLY", "FAIRNESS_CONDITIONAL", "REPORT_ONLY_NO_RECOMMENDATION"),
    "weak_fair_disabled_cycle": ("UNSAFE_COUNTEREXAMPLE", "AUTHOR_DECLARED_ONLY", "NO_PROGRESS", "REPORT_ONLY_REPAIR"),
    "combined_cycle_fair_lasso": ("UNSAFE_COUNTEREXAMPLE", "AUTHOR_DECLARED_ONLY", "NO_PROGRESS", "REPORT_ONLY_REPAIR"),
    "fairness_unrealizable": ("UNSAFE_COUNTEREXAMPLE", "AUTHOR_DECLARED_ONLY", "NO_PROGRESS", "REPORT_ONLY_REPAIR"),
    "terminal_transition_violation": ("UNSAFE_COUNTEREXAMPLE", "AUTHOR_DECLARED_ONLY", "AUTONOMOUSLY_LIVE", "REPORT_ONLY_REPAIR"),
    "bounded_exploration": ("BOUNDED_NO_COUNTEREXAMPLE", "AUTHOR_DECLARED_ONLY", "UNKNOWN", "REPORT_ONLY_NO_RECOMMENDATION"),
    "unknown_fidelity": ("INCONCLUSIVE_MODEL_GAP", "AUTHOR_DECLARED_ONLY", "AUTONOMOUSLY_LIVE", "REPORT_ONLY_NO_RECOMMENDATION"),
}

REQUIRED_FIXTURE_NAMES = tuple(EXPECTED.keys())


def _load(name: str) -> dict:
    return json.loads((FIXTURES_DIR / f"{name}.json").read_text())


def test_every_required_fixture_file_exists() -> None:
    for name in REQUIRED_FIXTURE_NAMES:
        assert (FIXTURES_DIR / f"{name}.json").is_file(), f"missing fixture {name}.json"


@pytest.mark.parametrize("name", REQUIRED_FIXTURE_NAMES)
def test_fixture_matches_frozen_expectation(name: str) -> None:
    model = parse_model_text(json.dumps(_load(name)))
    report = run_checker(model, generated_at=GENERATED_AT)
    verdict, applicability, disposition, recommendation = EXPECTED[name]
    assert report.model_analysis_verdict == verdict, name
    assert report.source_applicability_at_generation == applicability, name
    assert report.progress_disposition == disposition, name
    assert report.admission_recommendation == recommendation, name


def test_bounded_exploration_never_claims_proof() -> None:
    report = run_checker(parse_model_text(json.dumps(_load("bounded_exploration"))), generated_at=GENERATED_AT)
    assert report.model_analysis_verdict != "PROVEN_WITHIN_FINITE_MODEL"
    assert report.exploration_receipt.base_graph_complete is False


def test_unsafe_fixtures_carry_a_declared_model_only_counterexample() -> None:
    for name in ("effect_unknown_failover", "carrier_split", "stranded_parent"):
        report = run_checker(parse_model_text(json.dumps(_load(name))), generated_at=GENERATED_AT)
        assert report.counterexamples, name
        for cx in report.counterexamples:
            assert cx.realizability == "DECLARED_MODEL_ONLY", name


def test_combined_cycle_lasso_witness_uses_both_fair_transitions() -> None:
    report = run_checker(parse_model_text(json.dumps(_load("combined_cycle_fair_lasso"))), generated_at=GENERATED_AT)
    cx = [c for c in report.counterexamples if c.property_id == "UNIVERSAL_PROGRESS"][0]
    assert "mark_x" in cx.cycle
    assert "mark_y" in cx.cycle


def test_repair_scope_field_never_appears_on_any_fixture_report() -> None:
    for name in REQUIRED_FIXTURE_NAMES:
        report = run_checker(parse_model_text(json.dumps(_load(name))), generated_at=GENERATED_AT)
        payload = report.to_json()
        assert '"repair_scope"' not in payload, name


# ---------------------------------------------------------------------------
# Real CLI invocations over on-disk fixture files
# ---------------------------------------------------------------------------


def _run_cli(args: list[str], stdin_text: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CLI), *args],
        input=stdin_text,
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        timeout=30,
    )


@pytest.mark.parametrize("name", REQUIRED_FIXTURE_NAMES)
def test_cli_over_real_fixture_file_matches_expectation(name: str) -> None:
    proc = _run_cli([str(FIXTURES_DIR / f"{name}.json")])
    assert proc.returncode == 0, proc.stderr
    report = json.loads(proc.stdout)
    verdict, applicability, disposition, recommendation = EXPECTED[name]
    assert report["model_analysis_verdict"] == verdict, name
    assert report["source_applicability_at_generation"] == applicability, name
    assert report["progress_disposition"] == disposition, name
    assert report["admission_recommendation"] == recommendation, name


def test_cli_over_stdin_matches_file_invocation_for_every_fixture() -> None:
    for name in REQUIRED_FIXTURE_NAMES:
        text = (FIXTURES_DIR / f"{name}.json").read_text()
        proc_file = _run_cli([str(FIXTURES_DIR / f"{name}.json")])
        proc_stdin = _run_cli(["-"], stdin_text=text)
        assert proc_file.returncode == proc_stdin.returncode == 0
        rf = json.loads(proc_file.stdout)
        rs = json.loads(proc_stdin.stdout)
        # report_hash/report_id/generated_at are legitimately time-dependent
        # across two separate real-time subprocess invocations (each stamps
        # its own generated_at); byte-identical output for a FIXED
        # generated_at is proven separately in
        # test_cli_output_is_byte_stable_across_runs.
        for key in ("model_analysis_verdict", "source_applicability_at_generation", "progress_disposition", "admission_recommendation", "model_hash"):
            assert rf[key] == rs[key], (name, key)
