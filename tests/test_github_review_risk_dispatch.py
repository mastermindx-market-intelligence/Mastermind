"""Exact-head risk dispatch; automatic skips cannot borrow another PR receipt."""
from dataclasses import replace

import pytest

from control_plane.github_review_risk_dispatch import (
    ReviewDispatch, ReviewOrigin, ReviewRiskDispatchError,
    decide_risk_dispatch,
)
from control_plane.github_review_risk_policy import (
    ReviewChangeFacts, ReviewTier, assess_review_risk,
)
from control_plane.github_review_risk_source import SourcePR

REPO = "mastermindx-market-intelligence/Mastermind"
SHA = "a" * 40
BASE = "b" * 40
PR = 10


def risk(paths=("docs/user-guide.md",), *, verified=True):
    return assess_review_risk(ReviewChangeFacts(
        repository=REPO, pull_number=PR, head_sha=SHA,
        changed_paths=paths, additions=2, deletions=0,
        complete_source_verified=verified,
    ))


def current(**override):
    facts = dict(
        repository=REPO, pull_number=PR, head_sha=SHA, base_sha=BASE,
        head_repository=REPO, base_repository=REPO,
        open=True, draft=False, changed_files=1, additions=2, deletions=0,
    )
    facts.update(override)
    return SourcePR(**facts)


def auto(assessment, *, expected_repo=REPO, expected_pr=PR,
         expected_head=SHA, latest=None):
    return decide_risk_dispatch(
        origin=ReviewOrigin.AUTOMATIC_POLICY,
        assessment=assessment,
        expected_repository=expected_repo,
        expected_pull_number=expected_pr,
        expected_head_sha=expected_head,
        current_source=current() if latest is None else latest,
    )


def test_auto_fast_skips_review_job_only_for_matching_current_source():
    result = auto(risk())
    assert result.action is ReviewDispatch.SKIP_NO_REVIEW_NEEDED
    assert result.source_tier is ReviewTier.FAST
    assert (result.repository, result.pull_number, result.head_sha) == (REPO, PR, SHA)


def test_auto_ordinary_schema_source_skips_machine_review():
    result = auto(risk(("server/schema/refresh.py",)))
    assert result.action is ReviewDispatch.SKIP_NO_REVIEW_NEEDED
    assert result.source_tier is ReviewTier.STANDARD


def test_auto_sensitive_keeps_separate_machine_review():
    result = auto(risk((".github/workflows/release.yml",)))
    assert result.action is ReviewDispatch.AUTO_REVIEW_ELIGIBLE
    assert result.source_tier is ReviewTier.CRITICAL


@pytest.mark.parametrize("path", [
    "control_plane/packet_gate.py",
    "control_plane/governance.py",
    "control_plane/strategic_state.py",
    "config/strategic_state.yml",
    "config/contracts.yml",
    "research/MASTERMIND_CHARTER_V2.md",
    "DOCTRINE.md",
])
def test_auto_constitution_and_governor_paths_are_not_silent_standard_skips(path):
    # A verified one-line governance change still needs independent CRITICAL
    # technical scrutiny; an author label cannot demote source-owned authority.
    result = auto(risk((path,)))
    assert result.source_tier is ReviewTier.CRITICAL
    assert result.action is ReviewDispatch.AUTO_REVIEW_ELIGIBLE


def test_auto_partial_source_cannot_claim_exemption_or_auto_review():
    assert auto(risk(verified=False)).action is ReviewDispatch.HOLD_UNQUALIFIED_SOURCE


def test_auto_missing_risk_holds():
    assert auto(None).action is ReviewDispatch.HOLD_UNQUALIFIED_SOURCE


@pytest.mark.parametrize("identity", [
    {"expected_repo": "different/repo"},
    {"expected_pr": 11},
    {"expected_head": "c" * 40},
])
def test_auto_cross_pr_or_signed_head_reuse_holds(identity):
    assert auto(risk(), **identity).action is ReviewDispatch.HOLD_UNQUALIFIED_SOURCE


@pytest.mark.parametrize("latest", [
    current(head_sha="c" * 40),
    current(repository="different/repo"),
    current(pull_number=11),
    current(head_repository="different/fork"),
    current(open=False),
    current(draft=True),
])
def test_auto_head_move_after_census_or_changed_pr_state_holds(latest):
    assert auto(risk(), latest=latest).action is ReviewDispatch.HOLD_UNQUALIFIED_SOURCE


def test_legacy_fast_object_with_no_signed_identity_never_skips():
    assert decide_risk_dispatch(
        origin=ReviewOrigin.AUTOMATIC_POLICY,
        assessment=risk(), current_source=current(),
    ).action is ReviewDispatch.HOLD_UNQUALIFIED_SOURCE


def test_automatic_missing_fresh_read_never_skips():
    assert decide_risk_dispatch(
        origin=ReviewOrigin.AUTOMATIC_POLICY, assessment=risk(),
        expected_repository=REPO, expected_pull_number=PR,
        expected_head_sha=SHA,
    ).action is ReviewDispatch.HOLD_UNQUALIFIED_SOURCE


def test_manual_review_does_not_run_fast_lane():
    result = decide_risk_dispatch(
        origin=ReviewOrigin.MANUAL_AUTHORIZED, assessment=risk(),
    )
    assert result.action is ReviewDispatch.USE_EXISTING_MANUAL_INGRESS


def test_manual_review_without_risk_stays_on_existing_ingress():
    assert decide_risk_dispatch(
        origin=ReviewOrigin.MANUAL_AUTHORIZED, assessment=None,
    ).action is ReviewDispatch.USE_EXISTING_MANUAL_INGRESS


@pytest.mark.parametrize("bad_origin", [
    "AUTOMATIC_POLICY", None, True, 1,
])
def test_caller_text_is_not_verified_origin(bad_origin):
    with pytest.raises(ReviewRiskDispatchError):
        decide_risk_dispatch(origin=bad_origin, assessment=risk())


def test_auto_bounded_app_source_skips_machine_review():
    result = auto(risk(("app/src/component.tsx",)))
    assert result.action is ReviewDispatch.SKIP_NO_REVIEW_NEEDED
    assert result.source_tier is ReviewTier.STANDARD


def test_forged_zero_assessment_counts_cannot_skip_signed_critical_machine_risk():
    assessment = replace(
        risk((".github/workflows/ci.yml",)),
        minimum_independent_assessments=0,
        minimum_formal_non_author_approvals=0,
    )
    assert auto(assessment).action is ReviewDispatch.HOLD_UNQUALIFIED_SOURCE


@pytest.mark.parametrize("paths", [("docs/user-guide.md",), ("server/api/refresh.py",),
                                  ("control_plane/packet_gate.py",)])
@pytest.mark.parametrize("counts", [(2, 1), (True, 0), (0, True), (-1, 0)])
def test_forged_or_obsolete_count_objects_hold(paths, counts):
    assessment = replace(risk(paths), minimum_independent_assessments=counts[0],
                         minimum_formal_non_author_approvals=counts[1])
    assert auto(assessment).action is ReviewDispatch.HOLD_UNQUALIFIED_SOURCE


@pytest.mark.parametrize("paths", [("docs/user-guide.md",), ("server/api/refresh.py",)])
def test_standard_skip_retains_exact_head_and_source_gates(paths):
    assert auto(risk(paths), latest=current(head_sha="c" * 40)).action is ReviewDispatch.HOLD_UNQUALIFIED_SOURCE
    assert auto(risk(paths, verified=False)).action is ReviewDispatch.HOLD_UNQUALIFIED_SOURCE
