from __future__ import annotations

import ast
import dataclasses
from pathlib import Path

import pytest

from control_plane.github_ci_candidate_observer import CandidateObserverDisposition
from control_plane.github_ci_candidate_waiter import (
    CandidateWaitDisposition,
    CandidateWaiterConflict,
    CandidateWaiterError,
    CandidateWaiterRegistration,
    CandidateWaiterRegistry,
    wait_for_candidate_material,
)
from control_plane.github_release_assessment import (
    CandidateCIState,
    CheckConclusion,
    CheckStatus,
)
from tests.test_github_ci_candidate_observer import (
    HEAD,
    OTHER_HEAD,
    observation,
)


ROOT = Path(__file__).resolve().parents[1]


def token_factory(*values: str):
    items = iter(values)
    return lambda: next(items)


def test_registry_allows_exactly_one_active_waiter_and_compare_delete() -> None:
    baseline = observation()
    registry = CandidateWaiterRegistry(
        token_factory=token_factory("a" * 24, "b" * 24)
    )
    first = registry.register(baseline)
    assert registry.active_count() == 1
    assert registry.is_active(first.observer_id)
    with pytest.raises(CandidateWaiterConflict):
        registry.register(baseline)

    stale = CandidateWaiterRegistration(
        observer_id=first.observer_id,
        token="z" * 24,
    )
    assert registry.unregister(stale) is False
    assert registry.is_active(first.observer_id)
    assert registry.unregister(first) is True
    assert registry.active_count() == 0

    second = registry.register(baseline)
    assert second.token == "b" * 24
    assert registry.unregister(second) is True


def test_registry_rejects_process_lifetime_token_reuse() -> None:
    baseline = observation()
    registry = CandidateWaiterRegistry(token_factory=lambda: "r" * 24)
    first = registry.register(baseline)
    assert registry.unregister(first) is True
    with pytest.raises(CandidateWaiterError, match="reused"):
        registry.register(baseline)


def test_waiter_suppresses_pending_progress_until_terminal_material_return() -> None:
    baseline = observation()
    pending_progress = observation(
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
    samples = iter((pending_progress, green))
    waits = []
    registry = CandidateWaiterRegistry(token_factory=lambda: "t" * 24)

    result = wait_for_candidate_material(
        baseline,
        sample=lambda: next(samples),
        wait=lambda: waits.append("wait"),
        registry=registry,
        max_samples=3,
    )

    assert result.disposition is CandidateWaitDisposition.MATERIAL_RETURN
    assert result.sample_count == 2
    assert result.wake_reasoning is True
    assert result.decision is not None
    assert result.decision.disposition is CandidateObserverDisposition.TERMINAL_RETURN
    assert result.decision.candidate_state is CandidateCIState.GREEN
    assert waits == ["wait"]
    assert registry.active_count() == 0


def test_waiter_returns_material_unknown_without_reasoning_poll_loop() -> None:
    baseline = observation()
    unknown = observation(checks_complete=False, include_runs=False)
    registry = CandidateWaiterRegistry(token_factory=lambda: "u" * 24)
    waits = []

    result = wait_for_candidate_material(
        baseline,
        sample=lambda: unknown,
        wait=lambda: waits.append("wait"),
        registry=registry,
        max_samples=4,
    )

    assert result.disposition is CandidateWaitDisposition.MATERIAL_RETURN
    assert result.sample_count == 1
    assert result.decision is not None
    assert result.decision.reason == "OBSERVER_EVIDENCE_UNKNOWN"
    assert waits == []
    assert registry.active_count() == 0


def test_waiter_budget_exhaustion_is_quiescent_and_cleans_registration() -> None:
    baseline = observation()
    registry = CandidateWaiterRegistry(token_factory=lambda: "q" * 24)
    waits = []

    result = wait_for_candidate_material(
        baseline,
        sample=lambda: baseline,
        wait=lambda: waits.append("wait"),
        registry=registry,
        max_samples=3,
    )

    assert result.disposition is CandidateWaitDisposition.QUIESCENT_BUDGET_EXHAUSTED
    assert result.sample_count == 3
    assert result.wake_reasoning is False
    assert result.decision is None
    assert waits == ["wait", "wait"]
    assert registry.active_count() == 0


def test_terminal_or_unknown_baseline_must_be_consumed_before_waiting() -> None:
    registry = CandidateWaiterRegistry(token_factory=lambda: "n" * 24)
    terminal = observation(
        test_status=CheckStatus.COMPLETED,
        test_conclusion=CheckConclusion.SUCCESS,
        codeql_status=CheckStatus.COMPLETED,
        codeql_conclusion=CheckConclusion.SUCCESS,
    )
    unknown = observation(checks_complete=False, include_runs=False)
    for baseline in (terminal, unknown):
        with pytest.raises(CandidateWaiterError, match="already material"):
            wait_for_candidate_material(
                baseline,
                sample=lambda: baseline,
                wait=lambda: None,
                registry=registry,
                max_samples=1,
            )
        assert registry.active_count() == 0


def test_identity_drift_refuses_and_finally_unregisters() -> None:
    baseline = observation()
    drifted = observation(expected_head=OTHER_HEAD, observed_head=OTHER_HEAD)
    registry = CandidateWaiterRegistry(token_factory=lambda: "d" * 24)

    with pytest.raises(CandidateWaiterError, match="identity changed"):
        wait_for_candidate_material(
            baseline,
            sample=lambda: drifted,
            wait=lambda: None,
            registry=registry,
            max_samples=1,
        )
    assert registry.active_count() == 0


def test_cadence_failure_is_typed_and_finally_unregisters() -> None:
    baseline = observation()
    registry = CandidateWaiterRegistry(token_factory=lambda: "c" * 24)
    calls = 0

    def sample():
        nonlocal calls
        calls += 1
        return baseline

    def fail_wait():
        raise RuntimeError("scheduler unavailable")

    with pytest.raises(CandidateWaiterError, match="cadence failed"):
        wait_for_candidate_material(
            baseline,
            sample=sample,
            wait=fail_wait,
            registry=registry,
            max_samples=2,
        )
    assert calls == 1
    assert registry.active_count() == 0


def test_duplicate_wait_call_does_not_displace_incumbent_registration() -> None:
    baseline = observation()
    registry = CandidateWaiterRegistry(
        token_factory=token_factory("i" * 24, "j" * 24)
    )
    incumbent = registry.register(baseline)

    with pytest.raises(CandidateWaiterConflict):
        wait_for_candidate_material(
            baseline,
            sample=lambda: baseline,
            wait=lambda: None,
            registry=registry,
            max_samples=1,
        )
    assert registry.active_count() == 1
    assert registry.is_active(incumbent.observer_id)
    assert registry.unregister(incumbent) is True


@pytest.mark.parametrize("value", [0, -1, 121, True, 1.5])
def test_wait_budget_is_closed(value) -> None:
    baseline = observation()
    with pytest.raises(CandidateWaiterError, match="max_samples"):
        wait_for_candidate_material(
            baseline,
            sample=lambda: baseline,
            wait=lambda: None,
            registry=CandidateWaiterRegistry(token_factory=lambda: "x" * 24),
            max_samples=value,
        )


def test_waiter_adds_no_network_persistence_wake_or_release_effect() -> None:
    module = ROOT / "control_plane" / "github_ci_candidate_waiter.py"
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
            "requests", "httpx", "urllib", "socket", "sqlite3", "subprocess",
            "time", "asyncio", "mcp",
        }
    )
    source = module.read_text(encoding="utf-8")
    for forbidden in (
        "append_event(", "create_job(", "wake(", "merge(", "deploy(",
        "rerun(", "urlopen(", "gh api",
    ):
        assert forbidden not in source


def test_waiter_test_is_in_existing_ci_gate() -> None:
    from scripts.ci_pytest import resolve_gate

    gate = resolve_gate(ROOT)
    assert "tests/test_github_ci_candidate_waiter.py" in gate["included"]
