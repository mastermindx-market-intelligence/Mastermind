from __future__ import annotations

import ast
import dataclasses
import hashlib
from pathlib import Path

import pytest

from control_plane.github_ci_candidate_observer import (
    CandidateObserverDisposition,
    CandidateObserverError,
    CandidateObserverKey,
    key_for_observation,
    observe_candidate_transition,
    observer_id,
)
from control_plane.github_release_assessment import (
    CI_OBSERVATION_INPUT_SCHEMA,
    CandidateCheckRun,
    CandidateCIObservationInput,
    CandidateCIState,
    CheckConclusion,
    CheckIdentity,
    CheckStatus,
    SourceOwner,
    SourceReference,
    SourceReferenceCoverage,
    assess_candidate_ci_observation,
)


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "mastermindx-market-intelligence/Mastermind"
REPOSITORY_ID = 1_317_762_013
PR = 1240
REF = "sol/web-claude-capability-hardening-20261004-c4-001"
HEAD = "a" * 40
OTHER_HEAD = "b" * 40
POLICY = "required-checks-v1"
NOW = 1_800_000_000
TEST = CheckIdentity("test", 15368)
CODEQL = CheckIdentity("CodeQL", 15368)


def source_ref(
    kind: str,
    resource_id: str,
    revision: str,
    *,
    observed_at: int = NOW,
    seed: str = "source",
) -> SourceReference:
    digest = hashlib.sha256(
        f"{seed}:{kind}:{resource_id}:{revision}:{observed_at}".encode()
    ).hexdigest()
    return SourceReference(
        source_kind="owner_native",
        owner=SourceOwner.GITHUB,
        repository=REPOSITORY,
        resource_kind=kind,
        resource_id=resource_id,
        revision=revision,
        observed_at=observed_at,
        valid_at=None,
        content_sha256=digest,
        coverage=SourceReferenceCoverage.COMPLETE,
        truncated=False,
        continuation=None,
    )


def run(
    identity: CheckIdentity,
    *,
    check_run_id: int,
    status: CheckStatus,
    conclusion: CheckConclusion | None,
    attempt: int = 1,
    sequence: int = 1,
    head: str = HEAD,
) -> CandidateCheckRun:
    return CandidateCheckRun(
        identity=identity,
        head_sha=head,
        check_run_id=check_run_id,
        workflow_run_id=check_run_id + 1000,
        attempt=attempt,
        sequence=sequence,
        status=status,
        conclusion=conclusion,
        applicable=True,
        superseded=False,
        source_ref=source_ref(
            "check_run",
            f"check-run:{check_run_id}",
            head,
            seed=f"{status.value}:{conclusion}:{attempt}:{sequence}",
        ),
    )


def observation(
    *,
    test_status: CheckStatus = CheckStatus.IN_PROGRESS,
    test_conclusion: CheckConclusion | None = None,
    codeql_status: CheckStatus = CheckStatus.QUEUED,
    codeql_conclusion: CheckConclusion | None = None,
    checks_complete: bool = True,
    expected_head: str = HEAD,
    observed_head: str = HEAD,
    include_runs: bool = True,
):
    rows = ()
    if include_runs:
        rows = (
            run(
                TEST,
                check_run_id=1001,
                status=test_status,
                conclusion=test_conclusion,
                head=observed_head,
            ),
            run(
                CODEQL,
                check_run_id=1002,
                status=codeql_status,
                conclusion=codeql_conclusion,
                head=observed_head,
            ),
        )
    packet = CandidateCIObservationInput(
        schema=CI_OBSERVATION_INPUT_SCHEMA,
        observed_at=NOW,
        repository=REPOSITORY,
        repository_id=REPOSITORY_ID,
        pull_request_number=PR,
        candidate_ref=REF,
        expected_head_sha=expected_head,
        observed_head_sha=observed_head,
        policy_revision=POLICY,
        required_checks=(TEST, CODEQL),
        allowed_non_success_checks=(),
        check_runs=rows,
        checks_complete=checks_complete,
        policy_source_ref=source_ref(
            "required_checks_policy",
            POLICY,
            POLICY,
            seed="policy",
        ),
        checks_source_ref=source_ref(
            "commit_check_runs",
            observed_head,
            observed_head,
            seed=f"checks:{test_status.value}:{codeql_status.value}:{checks_complete}",
        ),
    )
    return assess_candidate_ci_observation(packet)


def test_pending_baseline_is_quiescent_and_deterministically_identified() -> None:
    current = observation()
    assert current.state is CandidateCIState.PENDING

    decision = observe_candidate_transition(current)
    assert decision.disposition is CandidateObserverDisposition.QUIESCENT
    assert decision.reason == "BASELINE_PENDING"
    assert decision.wake_reasoning is False
    assert decision.terminal is False
    assert decision.observer_id == observer_id(key_for_observation(current))
    assert len(decision.canonical_digest) == 64


def test_pending_progress_is_suppressed_even_when_snapshot_digest_moves() -> None:
    previous = observation()
    current = observation(
        test_status=CheckStatus.COMPLETED,
        test_conclusion=CheckConclusion.SUCCESS,
        codeql_status=CheckStatus.IN_PROGRESS,
    )
    assert previous.canonical_digest != current.canonical_digest
    assert current.state is CandidateCIState.PENDING

    decision = observe_candidate_transition(current, previous=previous)
    assert decision.disposition is CandidateObserverDisposition.QUIESCENT
    assert decision.reason == "NO_MATERIAL_CHANGE"
    assert decision.wake_reasoning is False


@pytest.mark.parametrize(
    ("conclusion", "state", "reason"),
    [
        (CheckConclusion.SUCCESS, CandidateCIState.GREEN, "TERMINAL_GREEN"),
        (CheckConclusion.FAILURE, CandidateCIState.FAILED, "TERMINAL_FAILED"),
    ],
)
def test_terminal_ci_returns_reasoning_control(
    conclusion: CheckConclusion,
    state: CandidateCIState,
    reason: str,
) -> None:
    previous = observation()
    current = observation(
        test_status=CheckStatus.COMPLETED,
        test_conclusion=conclusion,
        codeql_status=CheckStatus.COMPLETED,
        codeql_conclusion=(
            CheckConclusion.SUCCESS
            if conclusion is CheckConclusion.SUCCESS
            else CheckConclusion.SUCCESS
        ),
    )
    assert current.state is state

    decision = observe_candidate_transition(current, previous=previous)
    assert decision.disposition is CandidateObserverDisposition.TERMINAL_RETURN
    assert decision.reason == reason
    assert decision.wake_reasoning is True
    assert decision.terminal is True


def test_moved_head_is_terminal_stale_return() -> None:
    previous = observation()
    current = observation(
        expected_head=HEAD,
        observed_head=OTHER_HEAD,
        test_status=CheckStatus.IN_PROGRESS,
        codeql_status=CheckStatus.QUEUED,
    )
    assert current.state is CandidateCIState.STALE

    decision = observe_candidate_transition(current, previous=previous)
    assert decision.disposition is CandidateObserverDisposition.TERMINAL_RETURN
    assert decision.reason == "TERMINAL_STALE"


def test_unknown_baseline_is_material_and_same_unknown_issue_is_suppressed() -> None:
    unknown = observation(checks_complete=False, include_runs=False)
    assert unknown.state is CandidateCIState.UNKNOWN
    first = observe_candidate_transition(unknown)
    assert first.disposition is CandidateObserverDisposition.MATERIAL_RETURN
    assert first.reason == "OBSERVER_EVIDENCE_UNKNOWN"

    moved_packet = CandidateCIObservationInput(
        schema=CI_OBSERVATION_INPUT_SCHEMA,
        observed_at=NOW + 1,
        repository=REPOSITORY,
        repository_id=REPOSITORY_ID,
        pull_request_number=PR,
        candidate_ref=REF,
        expected_head_sha=HEAD,
        observed_head_sha=HEAD,
        policy_revision=POLICY,
        required_checks=(TEST, CODEQL),
        allowed_non_success_checks=(),
        check_runs=(),
        checks_complete=False,
        policy_source_ref=source_ref(
            "required_checks_policy", POLICY, POLICY, seed="policy"
        ),
        checks_source_ref=source_ref(
            "commit_check_runs", HEAD, HEAD, seed="checks-incomplete"
        ),
    )
    moved_unknown = assess_candidate_ci_observation(moved_packet)
    assert moved_unknown.state is CandidateCIState.UNKNOWN
    assert moved_unknown.canonical_digest != unknown.canonical_digest
    assert moved_unknown.issues == unknown.issues

    second = observe_candidate_transition(moved_unknown, previous=unknown)
    assert second.disposition is CandidateObserverDisposition.QUIESCENT
    assert second.reason == "UNKNOWN_UNCHANGED"


def test_unknown_to_pending_is_material_observer_recovery() -> None:
    previous = observation(checks_complete=False, include_runs=False)
    current = observation()
    decision = observe_candidate_transition(current, previous=previous)
    assert decision.disposition is CandidateObserverDisposition.MATERIAL_RETURN
    assert decision.reason == "OBSERVER_EVIDENCE_RECOVERED"


def test_exact_observer_identity_refuses_candidate_or_policy_drift() -> None:
    previous = observation()
    changed_head_key = observation(expected_head=OTHER_HEAD, observed_head=OTHER_HEAD)
    with pytest.raises(CandidateObserverError, match="identity changed"):
        observe_candidate_transition(changed_head_key, previous=previous)

    changed_policy = dataclasses.replace(
        previous,
        policy_revision="required-checks-v2",
    )
    with pytest.raises(CandidateObserverError):
        observe_candidate_transition(changed_policy, previous=previous)


def test_terminal_observer_cannot_be_reused_or_resurrected() -> None:
    terminal = observation(
        test_status=CheckStatus.COMPLETED,
        test_conclusion=CheckConclusion.SUCCESS,
        codeql_status=CheckStatus.COMPLETED,
        codeql_conclusion=CheckConclusion.SUCCESS,
    )
    with pytest.raises(CandidateObserverError, match="terminal observer"):
        observe_candidate_transition(observation(), previous=terminal)


def test_forged_observation_digest_refuses_before_transition() -> None:
    valid = observation()
    forged = dataclasses.replace(valid, canonical_digest="f" * 64)
    with pytest.raises(CandidateObserverError, match="canonical digest"):
        observe_candidate_transition(forged)


def test_observer_id_is_order_independent_for_required_check_set() -> None:
    base = CandidateObserverKey(
        repository=REPOSITORY,
        repository_id=REPOSITORY_ID,
        pull_request_number=PR,
        candidate_ref=REF,
        expected_head_sha=HEAD,
        policy_revision=POLICY,
        required_checks=(TEST, CODEQL),
    )
    reversed_key = dataclasses.replace(
        base,
        required_checks=(CODEQL, TEST),
    )
    assert observer_id(base) == observer_id(reversed_key)


def test_filter_adds_no_polling_persistence_wake_or_release_effect() -> None:
    module = ROOT / "control_plane" / "github_ci_candidate_observer.py"
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
        "sleep(",
        "schedule(",
        "create_task(",
        "merge(",
        "deploy(",
        "rerun(",
        "append_event(",
        "create_job(",
        "wake(",
    ):
        assert forbidden not in source


def test_observer_test_is_in_existing_ci_gate() -> None:
    from scripts.ci_pytest import resolve_gate

    gate = resolve_gate(ROOT)
    assert "tests/test_github_ci_candidate_observer.py" in gate["included"]
