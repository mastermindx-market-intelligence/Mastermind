from __future__ import annotations

import dataclasses
import hashlib
from pathlib import Path

import pytest

from control_plane.github_ci_candidate_observer import (
    CandidateObserverDisposition,
    CandidateObserverError,
    observe_candidate_transition,
    validate_candidate_observer_decision,
)
from control_plane.github_ci_candidate_wake import (
    CandidateCIWakeBinding,
    CandidateCIWakeError,
    github_ci_source_ref,
    obligation_from_candidate_ci,
)
from control_plane.github_release_assessment import (
    CI_OBSERVATION_INPUT_SCHEMA,
    CandidateCheckRun,
    CandidateCIObservationInput,
    CheckConclusion,
    CheckIdentity,
    CheckStatus,
    SourceOwner,
    SourceReference,
    SourceReferenceCoverage,
    assess_candidate_ci_observation,
)
from control_plane.session_targets import load_session_targets, route_obligation
from control_plane.wake_events import (
    SourceKind,
    WakeKind,
    WakeObligationError,
    mint_obligation,
    parse_obligation,
)


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "mastermindx-market-intelligence/Mastermind"
REPOSITORY_ID = 1_317_762_013
HEAD = "a" * 40
POLICY = "required-checks-v1"
NOW = 1_800_000_000
TEST = CheckIdentity("test", 15368)


def source_ref(kind: str, resource_id: str, revision: str, *, seed: str) -> SourceReference:
    return SourceReference(
        source_kind="owner_native",
        owner=SourceOwner.GITHUB,
        repository=REPOSITORY,
        resource_kind=kind,
        resource_id=resource_id,
        revision=revision,
        observed_at=NOW,
        valid_at=None,
        content_sha256=hashlib.sha256(seed.encode()).hexdigest(),
        coverage=SourceReferenceCoverage.COMPLETE,
        truncated=False,
        continuation=None,
    )


def observation(
    *,
    status: CheckStatus,
    conclusion: CheckConclusion | None,
):
    run = CandidateCheckRun(
        identity=TEST,
        head_sha=HEAD,
        check_run_id=1001,
        workflow_run_id=2001,
        attempt=1,
        sequence=1,
        status=status,
        conclusion=conclusion,
        applicable=True,
        superseded=False,
        source_ref=source_ref("check_run", "check-run:1001", HEAD, seed=f"run:{status}:{conclusion}"),
    )
    return assess_candidate_ci_observation(
        CandidateCIObservationInput(
            schema=CI_OBSERVATION_INPUT_SCHEMA,
            observed_at=NOW,
            repository=REPOSITORY,
            repository_id=REPOSITORY_ID,
            pull_request_number=1240,
            candidate_ref="sol/web-claude-capability-hardening-20261004-c4-001",
            expected_head_sha=HEAD,
            observed_head_sha=HEAD,
            policy_revision=POLICY,
            required_checks=(TEST,),
            allowed_non_success_checks=(),
            check_runs=(run,),
            checks_complete=True,
            policy_source_ref=source_ref(
                "required_checks_policy", POLICY, POLICY, seed="policy"
            ),
            checks_source_ref=source_ref(
                "commit_check_runs", HEAD, HEAD, seed=f"checks:{status}:{conclusion}"
            ),
        )
    )


def decision(
    *,
    terminal: bool = True,
    failure: bool = False,
):
    pending = observation(status=CheckStatus.IN_PROGRESS, conclusion=None)
    if terminal:
        current = observation(
            status=CheckStatus.COMPLETED,
            conclusion=(
                CheckConclusion.FAILURE if failure else CheckConclusion.SUCCESS
            ),
        )
    else:
        unknown = dataclasses.replace(pending, canonical_digest="f" * 64)
        # This helper only produces valid decisions; nonterminal material return
        # is covered separately through decision tamper tests.
        with pytest.raises(CandidateObserverError):
            validate_candidate_observer_decision(
                observe_candidate_transition(unknown, previous=pending)
            )
        raise AssertionError("unreachable")
    return observe_candidate_transition(current, previous=pending)


def binding(**changes) -> CandidateCIWakeBinding:
    value = CandidateCIWakeBinding(
        target_seat="coo",
        routing_workstream=None,
        source_workstream="WS:EXECUTIVE-CAPACITY-FABRIC",
        root_job_id=None,
        source_created_at=None,
        emitted_at="2026-10-05T09:00:00Z",
    )
    return dataclasses.replace(value, **changes) if changes else value


def test_terminal_candidate_decision_mints_existing_wake_obligation() -> None:
    current = decision()
    assert current.disposition is CandidateObserverDisposition.TERMINAL_RETURN

    obligation = obligation_from_candidate_ci(current, binding=binding())

    assert obligation.wake_kind is WakeKind.CI_CANDIDATE_MATERIAL
    assert obligation.source_kind is SourceKind.GITHUB_CI_CANDIDATE_OBSERVATION
    assert obligation.source_ref == "github_ci_candidate:" + current.canonical_digest
    assert obligation.declared_target_seat == "coo"
    assert obligation.job_id is None
    assert obligation.attempt_id is None
    assert obligation.root_job_id is None
    assert obligation.source_workstream == "WS:EXECUTIVE-CAPACITY-FABRIC"
    assert parse_obligation(obligation.to_dict()) == obligation


def test_failed_candidate_is_same_wake_kind_but_distinct_source_identity() -> None:
    green = decision()
    failed = decision(failure=True)
    first = obligation_from_candidate_ci(green, binding=binding())
    second = obligation_from_candidate_ci(failed, binding=binding())

    assert first.wake_kind is second.wake_kind is WakeKind.CI_CANDIDATE_MATERIAL
    assert first.source_ref != second.source_ref
    assert first.obligation_id != second.obligation_id


def test_route_metadata_never_changes_source_obligation_identity() -> None:
    current = decision()
    first = obligation_from_candidate_ci(current, binding=binding())
    second = obligation_from_candidate_ci(
        current,
        binding=binding(routing_workstream="prophet"),
    )
    assert first.obligation_id == second.obligation_id
    assert first.source_ref == second.source_ref
    assert first.workstream is None
    assert second.workstream == "prophet"


def test_checked_in_session_target_registry_can_route_without_mutating_obligation() -> None:
    current = decision()
    obligation = obligation_from_candidate_ci(current, binding=binding())
    registry = load_session_targets()
    before = obligation.to_dict()

    route = route_obligation(obligation, registry)

    assert route.obligation_id == obligation.obligation_id
    assert route.target_seat == "coo"
    assert obligation.to_dict() == before


def test_quiescent_candidate_cannot_mint_wake() -> None:
    pending = observation(status=CheckStatus.IN_PROGRESS, conclusion=None)
    quiet = observe_candidate_transition(pending)
    assert quiet.disposition is CandidateObserverDisposition.QUIESCENT
    with pytest.raises(CandidateCIWakeError, match="quiescent"):
        obligation_from_candidate_ci(quiet, binding=binding())


def test_forged_observer_decision_is_refused_before_wake() -> None:
    current = decision()
    forged = dataclasses.replace(current, canonical_digest="f" * 64)
    with pytest.raises(CandidateCIWakeError, match="canonical digest"):
        obligation_from_candidate_ci(forged, binding=binding())


@pytest.mark.parametrize("target", ["ceo", "chairman", "worker", ""])
def test_h5_candidate_return_is_coo_bound(target: str) -> None:
    with pytest.raises(CandidateCIWakeError, match="COO-bound"):
        obligation_from_candidate_ci(decision(), binding=binding(target_seat=target))


def test_wake_vocabulary_does_not_allow_ci_source_to_impersonate_other_kinds() -> None:
    current = decision()
    source = github_ci_source_ref(current)
    with pytest.raises(WakeObligationError, match="github CI source cannot mint"):
        mint_obligation(
            wake_kind=WakeKind.DIALOGUE_TURN_PENDING,
            source_kind=SourceKind.GITHUB_CI_CANDIDATE_OBSERVATION,
            source_ref=source,
            declared_target_seat="coo",
            emitted_at="2026-10-05T09:00:00Z",
        )
    with pytest.raises(WakeObligationError, match="cannot claim a Job or Attempt"):
        mint_obligation(
            wake_kind=WakeKind.CI_CANDIDATE_MATERIAL,
            source_kind=SourceKind.GITHUB_CI_CANDIDATE_OBSERVATION,
            source_ref=source,
            declared_target_seat="coo",
            job_id="JOB-100",
            emitted_at="2026-10-05T09:00:00Z",
        )


def test_h5_wake_adapter_adds_no_sampler_persistence_transport_or_reasoning_owner() -> None:
    source = (ROOT / "control_plane" / "github_ci_candidate_wake.py").read_text()
    for forbidden in (
        "requests",
        "httpx",
        "urllib",
        "socket",
        "sqlite3",
        "subprocess",
        "sleep(",
        "create_task(",
        "poll",
        "rerun",
        "merge(",
        "deploy(",
    ):
        assert forbidden not in source


def test_h5_wake_test_is_in_existing_ci_gate() -> None:
    from scripts.ci_pytest import resolve_gate

    gate = resolve_gate(ROOT)
    assert "tests/test_github_ci_candidate_wake.py" in gate["included"]
