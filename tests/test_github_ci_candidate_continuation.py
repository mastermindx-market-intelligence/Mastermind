from __future__ import annotations

import ast
from pathlib import Path

import pytest

from control_plane.github_ci_candidate_continuation import (
    CandidateCIContinuationError,
    wait_for_candidate_continuation,
)
from control_plane.github_ci_candidate_waiter import (
    CandidateWaitDisposition,
    CandidateWaiterRegistry,
)
from control_plane.github_release_assessment import (
    CandidateCIState,
    CheckConclusion,
    CheckStatus,
)
from control_plane.wake_events import SourceKind, WakeKind
from tests.test_github_ci_candidate_observer import observation
from tests.test_github_ci_candidate_wake import binding


ROOT = Path(__file__).resolve().parents[1]


def test_terminal_green_composes_exact_wait_into_one_wake_obligation() -> None:
    baseline = observation()
    pending = observation(
        test_status=CheckStatus.COMPLETED,
        test_conclusion=CheckConclusion.SUCCESS,
        codeql_status=CheckStatus.IN_PROGRESS,
    )
    green = observation(
        test_status=CheckStatus.COMPLETED,
        test_conclusion=CheckConclusion.SUCCESS,
        codeql_status=CheckStatus.COMPLETED,
        codeql_conclusion=CheckConclusion.SUCCESS,
    )
    samples = iter((pending, green))
    registry = CandidateWaiterRegistry(token_factory=lambda: "a" * 24)

    result = wait_for_candidate_continuation(
        baseline,
        sample=lambda: next(samples),
        wait=lambda: None,
        registry=registry,
        max_samples=3,
        wake_binding=binding(),
    )

    assert result.material_return is True
    assert result.wait_result.disposition is CandidateWaitDisposition.MATERIAL_RETURN
    assert result.wait_result.decision is not None
    assert result.wait_result.decision.candidate_state is CandidateCIState.GREEN
    assert result.wake_obligation is not None
    assert result.wake_obligation.wake_kind is WakeKind.CI_CANDIDATE_MATERIAL
    assert (
        result.wake_obligation.source_kind
        is SourceKind.GITHUB_CI_CANDIDATE_OBSERVATION
    )
    assert result.wake_obligation.source_ref.endswith(
        result.wait_result.decision.canonical_digest
    )
    assert registry.active_count() == 0


def test_terminal_failure_composes_same_wake_kind_with_failure_decision() -> None:
    baseline = observation()
    failed = observation(
        test_status=CheckStatus.COMPLETED,
        test_conclusion=CheckConclusion.FAILURE,
        codeql_status=CheckStatus.COMPLETED,
        codeql_conclusion=CheckConclusion.SUCCESS,
    )
    registry = CandidateWaiterRegistry(token_factory=lambda: "b" * 24)

    result = wait_for_candidate_continuation(
        baseline,
        sample=lambda: failed,
        wait=lambda: None,
        registry=registry,
        max_samples=1,
        wake_binding=binding(),
    )

    assert result.material_return is True
    assert result.wait_result.decision is not None
    assert result.wait_result.decision.candidate_state is CandidateCIState.FAILED
    assert result.wake_obligation is not None
    assert result.wake_obligation.wake_kind is WakeKind.CI_CANDIDATE_MATERIAL
    assert registry.active_count() == 0


def test_unknown_observer_health_becomes_material_wake() -> None:
    baseline = observation()
    unknown = observation(checks_complete=False, include_runs=False)
    registry = CandidateWaiterRegistry(token_factory=lambda: "c" * 24)

    result = wait_for_candidate_continuation(
        baseline,
        sample=lambda: unknown,
        wait=lambda: None,
        registry=registry,
        max_samples=2,
        wake_binding=binding(),
    )

    assert result.material_return is True
    assert result.wait_result.decision is not None
    assert result.wait_result.decision.candidate_state is CandidateCIState.UNKNOWN
    assert result.wait_result.decision.reason == "OBSERVER_EVIDENCE_UNKNOWN"
    assert result.wake_obligation is not None
    assert registry.active_count() == 0


def test_quiescent_budget_exhaustion_creates_no_wake_obligation() -> None:
    baseline = observation()
    registry = CandidateWaiterRegistry(token_factory=lambda: "d" * 24)

    result = wait_for_candidate_continuation(
        baseline,
        sample=lambda: baseline,
        wait=lambda: None,
        registry=registry,
        max_samples=2,
        wake_binding=binding(),
    )

    assert result.material_return is False
    assert (
        result.wait_result.disposition
        is CandidateWaitDisposition.QUIESCENT_BUDGET_EXHAUSTED
    )
    assert result.wake_obligation is None
    assert registry.active_count() == 0


def test_invalid_wake_binding_refuses_after_wait_and_registration_is_clean() -> None:
    baseline = observation()
    green = observation(
        test_status=CheckStatus.COMPLETED,
        test_conclusion=CheckConclusion.SUCCESS,
        codeql_status=CheckStatus.COMPLETED,
        codeql_conclusion=CheckConclusion.SUCCESS,
    )
    registry = CandidateWaiterRegistry(token_factory=lambda: "e" * 24)

    with pytest.raises(CandidateCIContinuationError, match="COO-bound"):
        wait_for_candidate_continuation(
            baseline,
            sample=lambda: green,
            wait=lambda: None,
            registry=registry,
            max_samples=1,
            wake_binding=binding(target_seat="ceo"),
        )

    assert registry.active_count() == 0


def test_sample_identity_drift_refuses_without_wake_or_registration_leak() -> None:
    baseline = observation()
    drifted = observation(
        expected_head="b" * 40,
        observed_head="b" * 40,
    )
    registry = CandidateWaiterRegistry(token_factory=lambda: "f" * 24)

    with pytest.raises(CandidateCIContinuationError, match="identity changed"):
        wait_for_candidate_continuation(
            baseline,
            sample=lambda: drifted,
            wait=lambda: None,
            registry=registry,
            max_samples=1,
            wake_binding=binding(),
        )

    assert registry.active_count() == 0


def test_composition_has_no_transport_persistence_or_delivery_owner() -> None:
    module = ROOT / "control_plane" / "github_ci_candidate_continuation.py"
    tree = ast.parse(module.read_text(encoding="utf-8"))
    imported_roots = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported_roots |= {
        (node.module or "").split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }
    assert imported_roots.isdisjoint(
        {
            "requests",
            "httpx",
            "urllib",
            "socket",
            "sqlite3",
            "subprocess",
            "time",
            "asyncio",
            "mcp",
        }
    )
    source = module.read_text(encoding="utf-8")
    for forbidden in (
        "append_event(",
        "create_job(",
        "deliver(",
        "wake(",
        "merge(",
        "deploy(",
        "rerun(",
        "urlopen(",
        "gh api",
    ):
        assert forbidden not in source


def test_continuation_test_is_in_existing_ci_gate() -> None:
    from scripts.ci_pytest import resolve_gate

    gate = resolve_gate(ROOT)
    assert "tests/test_github_ci_candidate_continuation.py" in gate["included"]
