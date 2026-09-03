from __future__ import annotations

import ast
import dataclasses
import json
from pathlib import Path

import pytest

from control_plane.github_release_assessment import (
    INPUT_SCHEMA,
    AssessmentInput,
    AssessmentInputError,
    AssessmentIssue,
    AssessmentVerdict,
    CapabilityState,
    CarrierAssessmentState,
    CarrierFact,
    CheckAssessmentState,
    CheckAttempt,
    CheckConclusion,
    CheckIdentity,
    CheckStatus,
    CompletionClaimState,
    CurrentSourceEvidence,
    EffectState,
    EvidenceSubject,
    MergeContextState,
    MergeMethod,
    Mergeability,
    MergedEffectReceipt,
    PathCollisionFact,
    PathState,
    ProductionAssessmentState,
    ProductionProof,
    ProductionProofState,
    PullRequestState,
    PullRequestTarget,
    ReleaseTargetExpectation,
    ReviewAssessmentState,
    ReviewEvent,
    ReviewState,
    SemanticOwnerAssessmentState,
    SemanticOwnerExpectation,
    SemanticOwnerFact,
    SourceAssessmentState,
    SourceCoverage,
    SourceLawState,
    WriterAssessmentState,
    WriterFact,
    assess_github_release,
)


REPOSITORY = "mastermindx-market-intelligence/Mastermind"
REPOSITORY_ID = 1_317_762_013
PR_NUMBER = 295
PROTECTED_REF = "master"
PROTECTED_SHA = "a" * 40
CANDIDATE_REF = "sol/sol-capability-fabric-gh1-20260830"
CANDIDATE_SHA = "b" * 40
MERGED_SHA = "c" * 40
OPERATION = "mastermind-sol-capability-fabric-gh1-r1-test"
OWNER = "github-release-assessment"
WRITER = "sol-current-writer"
SOURCE_OWNER = "mastermind-protected-source"
SOURCE_REVISION = "skillpack-1.0.1"
CAPABILITY = "mastermind.github-release-assessment"
PRODUCTION_SUBJECT = "mastermind-production-release-proof"
PRODUCTION_OWNER = "mastermind-production-owner"
PRODUCTION_REVISION = "proof-v1"
NOW = 1_800_000_000
PATHS = (
    "control_plane/github_release_assessment.py",
    "tests/test_github_release_assessment.py",
)
CHECK = CheckIdentity("test", 15368)


def _expected(**changes: object) -> ReleaseTargetExpectation:
    base = ReleaseTargetExpectation(
        repository=REPOSITORY,
        repository_id=REPOSITORY_ID,
        pull_request_number=PR_NUMBER,
        protected_ref=PROTECTED_REF,
        expected_protected_sha=PROTECTED_SHA,
        candidate_ref=CANDIDATE_REF,
        expected_head_sha=CANDIDATE_SHA,
    )
    return dataclasses.replace(base, **changes)


def _target(**changes: object) -> PullRequestTarget:
    base = PullRequestTarget(
        repository=REPOSITORY,
        repository_id=REPOSITORY_ID,
        pull_request_number=PR_NUMBER,
        state=PullRequestState.OPEN,
        draft=False,
        merged=False,
        merged_commit_sha=None,
        mergeability=Mergeability.MERGEABLE,
        protected_ref=PROTECTED_REF,
        protected_sha=PROTECTED_SHA,
        protected_branch_protected=True,
        base_ref=PROTECTED_REF,
        base_sha=PROTECTED_SHA,
        candidate_ref=CANDIDATE_REF,
        candidate_sha=CANDIDATE_SHA,
        merge_base_sha=PROTECTED_SHA,
        ahead_by=2,
        behind_by=0,
        changed_paths=PATHS,
        changed_paths_complete=True,
    )
    return dataclasses.replace(base, **changes)


def _subject(target: PullRequestTarget | None = None, **changes: object) -> EvidenceSubject:
    target = target or _target()
    base = EvidenceSubject(
        repository=target.repository,
        repository_id=target.repository_id,
        pull_request_number=target.pull_request_number,
        protected_ref=target.protected_ref,
        protected_sha=target.protected_sha,
        base_ref=target.base_ref,
        base_sha=target.base_sha,
        candidate_ref=target.candidate_ref,
        candidate_sha=target.candidate_sha,
        changed_paths=target.changed_paths,
    )
    return dataclasses.replace(base, **changes)


def _source_evidence(target: PullRequestTarget | None = None, **changes: object) -> CurrentSourceEvidence:
    base = CurrentSourceEvidence(
        subject=_subject(target),
        owner_id=SOURCE_OWNER,
        revision=SOURCE_REVISION,
        observed_at=NOW,
        coverage=SourceCoverage.COMPLETE,
        law_state=SourceLawState.COMPATIBLE,
        source_ref="github:protected-source:current",
    )
    return dataclasses.replace(base, **changes)


def _production_proof(target: PullRequestTarget | None = None, **changes: object) -> ProductionProof:
    base = ProductionProof(
        capability_id=CAPABILITY,
        subject_id=PRODUCTION_SUBJECT,
        target_subject=_subject(target),
        owner_id=PRODUCTION_OWNER,
        revision=PRODUCTION_REVISION,
        observed_at=NOW,
        coverage=SourceCoverage.COMPLETE,
        state=ProductionProofState.PRESENT,
        source_ref="github:production-proof:current",
    )
    return dataclasses.replace(base, **changes)


def _carrier(target: PullRequestTarget | None = None, **changes: object) -> CarrierFact:
    target = target or _target()
    base = CarrierFact(
        carrier_ref="github:pr:295",
        operation_key=OPERATION,
        repository=target.repository,
        repository_id=target.repository_id,
        pull_request_number=target.pull_request_number,
        base_ref=target.base_ref,
        base_sha=target.base_sha,
        candidate_ref=target.candidate_ref,
        candidate_sha=target.candidate_sha,
        active=True,
        source_ref="github:carrier:295",
    )
    return dataclasses.replace(base, **changes)


def _writer(**changes: object) -> WriterFact:
    base = WriterFact(
        writer_id=WRITER,
        operation_key=OPERATION,
        repository_id=REPOSITORY_ID,
        pull_request_number=PR_NUMBER,
        paths=PATHS,
        active=True,
        source_ref="github:writer:sol",
    )
    return dataclasses.replace(base, **changes)


def _check_attempt(**changes: object) -> CheckAttempt:
    base = CheckAttempt(
        identity=CHECK,
        head_sha=CANDIDATE_SHA,
        attempt=1,
        sequence=1,
        status=CheckStatus.COMPLETED,
        conclusion=CheckConclusion.SUCCESS,
        applicable=True,
        superseded=False,
        source_ref="github:check:test:1",
    )
    return dataclasses.replace(base, **changes)


def _review(**changes: object) -> ReviewEvent:
    base = ReviewEvent(
        reviewer_id="independent-reviewer",
        head_sha=CANDIDATE_SHA,
        sequence=1,
        state=ReviewState.APPROVED,
        source_ref="github:review:1",
    )
    return dataclasses.replace(base, **changes)


def _packet(**changes: object) -> AssessmentInput:
    target = changes.get("target")
    assert target is None or isinstance(target, PullRequestTarget)
    target = target or _target()
    base = AssessmentInput(
        schema=INPUT_SCHEMA,
        operation_key=OPERATION,
        observed_at=NOW,
        expected_target=_expected(),
        target=target,
        expected_paths=PATHS,
        expected_semantic_owners=(
            SemanticOwnerExpectation("control_plane", OWNER),
            SemanticOwnerExpectation("tests", OWNER),
        ),
        semantic_owner_facts=(
            SemanticOwnerFact("control_plane", OWNER, OPERATION, True, "github:owner:control-plane"),
            SemanticOwnerFact("tests", OWNER, OPERATION, True, "github:owner:tests"),
        ),
        semantic_owners_complete=True,
        carrier_facts=(_carrier(target),),
        carriers_complete=True,
        expected_writer_id=WRITER,
        writer_facts=(_writer(),),
        writers_complete=True,
        path_collisions=(),
        path_collisions_complete=True,
        branch_required_checks=(CHECK,),
        assessment_required_checks=(CHECK,),
        allowed_non_success_checks=(),
        check_attempts=(_check_attempt(),),
        checks_complete=True,
        required_approvals=1,
        review_events=(_review(),),
        reviews_complete=True,
        unresolved_required_threads=0,
        current_source_evidence=_source_evidence(target),
        expected_source_owner_id=SOURCE_OWNER,
        expected_source_revision=SOURCE_REVISION,
        source_max_age_seconds=300,
        current_base_required=True,
        production_proof_required=False,
        claimed_capability_id=CAPABILITY,
        claimed_capability_state=CapabilityState.BUILT_NOT_PROVEN,
        expected_production_subject_id=PRODUCTION_SUBJECT,
        expected_production_owner_id=PRODUCTION_OWNER,
        expected_production_revision=PRODUCTION_REVISION,
        production_max_age_seconds=300,
        production_proof=None,
        requested_merge_method=MergeMethod.SQUASH,
        allowed_merge_methods=(MergeMethod.SQUASH,),
        prior_effect_state=EffectState.NOT_APPLIED,
        merged_effect_receipt=None,
        source_refs=("github:pr:295", "github:protected:master"),
    )
    return dataclasses.replace(base, **changes)


def _assess(**changes: object):
    return assess_github_release(_packet(**changes))


def _issue(result, issue: AssessmentIssue) -> bool:
    return issue in result.issues


def test_fully_bound_packet_is_eligible_and_emits_guarded_release_tuple() -> None:
    result = _assess()
    assert result.verdict is AssessmentVerdict.ELIGIBLE
    assert result.expected_head_merge_eligible is True
    assert result.expected_head_release is not None
    assert result.expected_head_release.to_dict() == {
        "repository": REPOSITORY,
        "repository_id": REPOSITORY_ID,
        "pull_request_number": PR_NUMBER,
        "protected_sha": PROTECTED_SHA,
        "candidate_sha": CANDIDATE_SHA,
        "changed_paths": sorted(PATHS),
        "merge_method": "SQUASH",
    }
    assert result.issues == ()
    assert result.to_dict()["canonical_digest"] == result.canonical_digest


def test_permutation_stability_canonicalizes_collections_and_source_refs() -> None:
    first = _assess()
    packet = _packet(
        expected_paths=tuple(reversed(PATHS)),
        expected_semantic_owners=tuple(reversed(_packet().expected_semantic_owners)),
        semantic_owner_facts=tuple(reversed(_packet().semantic_owner_facts)),
        source_refs=tuple(reversed(_packet().source_refs)),
    )
    second = assess_github_release(packet)
    assert first.input_digest == second.input_digest
    assert first.canonical_digest == second.canonical_digest
    assert first.to_dict() == second.to_dict()


@pytest.mark.parametrize(
    ("expected", "target", "issue"),
    [
        (_expected(repository="other/repo"), _target(), AssessmentIssue.REPOSITORY_MISMATCH),
        (_expected(repository_id=42), _target(), AssessmentIssue.REPOSITORY_MISMATCH),
        (_expected(pull_request_number=1), _target(), AssessmentIssue.PULL_REQUEST_MISMATCH),
        (_expected(candidate_ref="sol/other"), _target(), AssessmentIssue.PULL_REQUEST_MISMATCH),
        (_expected(expected_protected_sha="d" * 40), _target(), AssessmentIssue.PROTECTED_REF_MOVED),
        (_expected(expected_head_sha="d" * 40), _target(), AssessmentIssue.CANDIDATE_HEAD_MOVED),
        (_expected(protected_ref="main"), _target(), AssessmentIssue.BASE_REF_MISMATCH),
    ],
)
def test_exact_target_identity_contradictions_refuse(expected, target, issue) -> None:
    result = _assess(expected_target=expected, target=target)
    assert result.verdict is AssessmentVerdict.REFUSED
    assert _issue(result, issue)
    assert result.expected_head_release is None


def test_unprotected_base_branch_refuses() -> None:
    result = _assess(target=_target(protected_branch_protected=False))
    assert result.verdict is AssessmentVerdict.REFUSED
    assert _issue(result, AssessmentIssue.BASE_BRANCH_UNPROTECTED)


def test_draft_is_held_but_not_misclassified_as_refused() -> None:
    result = _assess(target=_target(draft=True))
    assert result.verdict is AssessmentVerdict.HELD
    assert _issue(result, AssessmentIssue.PR_DRAFT)
    assert result.expected_head_release is None


def test_merge_conflict_refuses_and_unknown_mergeability_is_unknown() -> None:
    conflict = _assess(target=_target(mergeability=Mergeability.CONFLICTING))
    assert conflict.verdict is AssessmentVerdict.REFUSED
    assert _issue(conflict, AssessmentIssue.MERGE_CONFLICT)
    unknown = _assess(target=_target(mergeability=Mergeability.UNKNOWN))
    assert unknown.verdict is AssessmentVerdict.UNKNOWN
    assert _issue(unknown, AssessmentIssue.MERGEABILITY_UNKNOWN)


def test_zero_or_empty_release_delta_refuses() -> None:
    zero = _assess(target=_target(ahead_by=0))
    assert zero.verdict is AssessmentVerdict.REFUSED
    assert _issue(zero, AssessmentIssue.EMPTY_RELEASE_DELTA)
    empty_target = _target(changed_paths=(), ahead_by=1)
    empty = _assess(
        target=empty_target,
        current_source_evidence=_source_evidence(empty_target),
    )
    assert empty.verdict is AssessmentVerdict.REFUSED
    assert _issue(empty, AssessmentIssue.EMPTY_RELEASE_DELTA)


def test_incomplete_or_mismatched_changed_path_coverage_cannot_green() -> None:
    partial = _assess(target=_target(changed_paths_complete=False))
    assert partial.verdict is AssessmentVerdict.UNKNOWN
    assert partial.path_state is PathState.UNKNOWN
    assert _issue(partial, AssessmentIssue.PATH_COVERAGE_PARTIAL)
    mismatch = _assess(expected_paths=(PATHS[0],))
    assert mismatch.verdict is AssessmentVerdict.REFUSED
    assert mismatch.path_state is PathState.MISMATCH
    assert _issue(mismatch, AssessmentIssue.EXPECTED_PATH_MISMATCH)


def test_every_changed_path_requires_exactly_one_semantic_owner_expectation() -> None:
    missing = _assess(expected_semantic_owners=())
    assert missing.verdict is AssessmentVerdict.UNKNOWN
    assert missing.semantic_owner_state is SemanticOwnerAssessmentState.UNKNOWN
    assert _issue(missing, AssessmentIssue.SEMANTIC_OWNER_COVERAGE_PARTIAL)
    ambiguous = _assess(
        expected_semantic_owners=(
            SemanticOwnerExpectation("control_plane", OWNER),
            SemanticOwnerExpectation(PATHS[0], OWNER),
            SemanticOwnerExpectation("tests", OWNER),
        )
    )
    assert ambiguous.verdict is AssessmentVerdict.REFUSED
    assert ambiguous.semantic_owner_state is SemanticOwnerAssessmentState.CONFLICT
    assert _issue(ambiguous, AssessmentIssue.SEMANTIC_OWNER_AMBIGUOUS)


def test_foreign_or_duplicate_semantic_owner_facts_refuse() -> None:
    foreign = SemanticOwnerFact(
        "control_plane",
        "other-owner",
        "other-operation",
        True,
        "github:owner:foreign",
    )
    result = _assess(semantic_owner_facts=(_packet().semantic_owner_facts[0], foreign, _packet().semantic_owner_facts[1]))
    assert result.verdict is AssessmentVerdict.REFUSED
    assert result.semantic_owner_state is SemanticOwnerAssessmentState.CONFLICT
    assert _issue(result, AssessmentIssue.SEMANTIC_OWNER_COLLISION)


def test_explicit_closed_no_owner_class_is_allowed_but_any_fact_then_collides() -> None:
    expectations = (
        SemanticOwnerExpectation("control_plane", OWNER),
        SemanticOwnerExpectation("tests", None, no_owner_allowed=True),
    )
    clean = _assess(
        expected_semantic_owners=expectations,
        semantic_owner_facts=(_packet().semantic_owner_facts[0],),
    )
    assert clean.verdict is AssessmentVerdict.ELIGIBLE
    collision = _assess(expected_semantic_owners=expectations)
    assert collision.verdict is AssessmentVerdict.REFUSED
    assert _issue(collision, AssessmentIssue.SEMANTIC_OWNER_COLLISION)


def test_same_sha_on_different_branch_alone_is_not_carrier_conflict() -> None:
    other = _carrier(
        carrier_ref="github:pr:999",
        operation_key="other-operation",
        pull_request_number=999,
        candidate_ref="sol/unrelated",
        candidate_sha=CANDIDATE_SHA,
        source_ref="github:carrier:999",
    )
    result = _assess(carrier_facts=(_carrier(), other))
    assert result.verdict is AssessmentVerdict.ELIGIBLE
    assert result.carrier_state is CarrierAssessmentState.EXACT


def test_foreign_same_pr_or_candidate_ref_conflicts() -> None:
    foreign = _carrier(
        carrier_ref="github:foreign",
        operation_key="other-operation",
        source_ref="github:carrier:foreign",
    )
    result = _assess(carrier_facts=(_carrier(), foreign))
    assert result.verdict is AssessmentVerdict.REFUSED
    assert result.carrier_state is CarrierAssessmentState.CONFLICT
    assert _issue(result, AssessmentIssue.OPERATION_CARRIER_CONFLICT)


def test_duplicate_exact_carriers_conflict_and_incomplete_or_missing_carrier_is_unknown() -> None:
    duplicate = dataclasses.replace(
        _carrier(), carrier_ref="github:pr:295:duplicate", source_ref="github:carrier:duplicate"
    )
    conflict = _assess(carrier_facts=(_carrier(), duplicate))
    assert conflict.verdict is AssessmentVerdict.REFUSED
    assert _issue(conflict, AssessmentIssue.OPERATION_CARRIER_CONFLICT)
    partial = _assess(carriers_complete=False)
    assert partial.verdict is AssessmentVerdict.UNKNOWN
    assert _issue(partial, AssessmentIssue.CARRIER_COVERAGE_PARTIAL)
    missing = _assess(carrier_facts=())
    assert missing.verdict is AssessmentVerdict.UNKNOWN
    assert _issue(missing, AssessmentIssue.OPERATION_CARRIER_NOT_FOUND)


def test_more_than_one_active_writer_conflicts_even_under_same_operation() -> None:
    second = _writer(writer_id="second-writer", source_ref="github:writer:second")
    result = _assess(writer_facts=(_writer(), second))
    assert result.verdict is AssessmentVerdict.REFUSED
    assert result.writer_state is WriterAssessmentState.CONFLICT
    assert _issue(result, AssessmentIssue.CARRIER_WRITER_CONFLICT)


def test_wrong_partial_or_missing_writer_cannot_green() -> None:
    wrong = _assess(writer_facts=(_writer(writer_id="wrong-writer"),))
    assert wrong.verdict is AssessmentVerdict.REFUSED
    assert _issue(wrong, AssessmentIssue.CARRIER_WRITER_CONFLICT)
    partial = _assess(writers_complete=False)
    assert partial.verdict is AssessmentVerdict.UNKNOWN
    assert _issue(partial, AssessmentIssue.WRITER_COVERAGE_PARTIAL)
    missing = _assess(writer_facts=())
    assert missing.verdict is AssessmentVerdict.UNKNOWN
    assert _issue(missing, AssessmentIssue.CARRIER_WRITER_NOT_FOUND)


def test_disjoint_path_collision_is_evidence_only_but_overlap_refuses() -> None:
    disjoint = PathCollisionFact("docs/unrelated.md", "other-operation", "github:collision:other")
    clean = _assess(path_collisions=(disjoint,))
    assert clean.verdict is AssessmentVerdict.ELIGIBLE
    overlap = PathCollisionFact("control_plane", "other-operation", "github:collision:overlap")
    blocked = _assess(path_collisions=(overlap,))
    assert blocked.verdict is AssessmentVerdict.REFUSED
    assert _issue(blocked, AssessmentIssue.PATH_COLLISION)


def test_incomplete_path_collision_census_is_unknown() -> None:
    result = _assess(path_collisions_complete=False)
    assert result.verdict is AssessmentVerdict.UNKNOWN
    assert _issue(result, AssessmentIssue.PATH_COLLISION_COVERAGE_PARTIAL)


def test_branch_required_check_cannot_be_omitted_or_collapsed_by_context_only() -> None:
    omitted = _assess(assessment_required_checks=())
    assert omitted.verdict is AssessmentVerdict.REFUSED
    assert _issue(omitted, AssessmentIssue.BRANCH_REQUIRED_CHECK_OMITTED)
    other_app = CheckIdentity("test", 999)
    collapsed = _assess(
        assessment_required_checks=(other_app,),
        check_attempts=(dataclasses.replace(_check_attempt(), identity=other_app),),
    )
    assert collapsed.verdict is AssessmentVerdict.REFUSED
    assert _issue(collapsed, AssessmentIssue.BRANCH_REQUIRED_CHECK_OMITTED)


def test_latest_exact_head_check_attempt_wins_by_attempt_then_sequence() -> None:
    failed = _check_attempt(
        attempt=1,
        sequence=1,
        conclusion=CheckConclusion.FAILURE,
        source_ref="github:check:test:failed",
    )
    success = _check_attempt(
        attempt=2,
        sequence=1,
        conclusion=CheckConclusion.SUCCESS,
        source_ref="github:check:test:success",
    )
    green = _assess(check_attempts=(failed, success))
    assert green.verdict is AssessmentVerdict.ELIGIBLE
    assert green.check_state is CheckAssessmentState.GREEN
    later_failure = dataclasses.replace(
        failed,
        attempt=2,
        sequence=2,
        source_ref="github:check:test:later-failure",
    )
    red = _assess(check_attempts=(success, later_failure))
    assert red.verdict is AssessmentVerdict.REFUSED
    assert red.check_state is CheckAssessmentState.FAILED
    assert _issue(red, AssessmentIssue.CHECK_FAILED)


@pytest.mark.parametrize(
    ("conclusion", "issue"),
    [
        (CheckConclusion.SKIPPED, AssessmentIssue.CHECK_SKIPPED_NOT_ALLOWED),
        (CheckConclusion.NEUTRAL, AssessmentIssue.CHECK_NEUTRAL_NOT_ALLOWED),
    ],
)
def test_skipped_or_neutral_only_passes_under_exact_policy_and_nonapplicability(conclusion, issue) -> None:
    attempt = _check_attempt(conclusion=conclusion, applicable=False)
    denied = _assess(check_attempts=(attempt,))
    assert denied.verdict is AssessmentVerdict.REFUSED
    assert _issue(denied, issue)
    allowed = _assess(
        allowed_non_success_checks=(CHECK,),
        check_attempts=(attempt,),
    )
    assert allowed.verdict is AssessmentVerdict.ELIGIBLE
    applicable = _assess(
        allowed_non_success_checks=(CHECK,),
        check_attempts=(dataclasses.replace(attempt, applicable=True),),
    )
    assert applicable.verdict is AssessmentVerdict.REFUSED
    assert _issue(applicable, issue)


def test_cancelled_failed_pending_superseded_and_incomplete_check_states_are_distinct() -> None:
    cancelled = _assess(check_attempts=(_check_attempt(conclusion=CheckConclusion.CANCELLED),))
    assert cancelled.verdict is AssessmentVerdict.REFUSED
    assert _issue(cancelled, AssessmentIssue.CHECK_CANCELLED)
    pending_attempt = _check_attempt(status=CheckStatus.IN_PROGRESS, conclusion=None)
    pending = _assess(check_attempts=(pending_attempt,))
    assert pending.verdict is AssessmentVerdict.HELD
    assert pending.check_state is CheckAssessmentState.PENDING
    superseded = _assess(check_attempts=(_check_attempt(superseded=True),))
    assert superseded.verdict is AssessmentVerdict.UNKNOWN
    assert _issue(superseded, AssessmentIssue.CHECK_SUPERSEDED)
    incomplete = _assess(checks_complete=False)
    assert incomplete.verdict is AssessmentVerdict.UNKNOWN
    assert _issue(incomplete, AssessmentIssue.CHECK_COVERAGE_PARTIAL)


def test_effective_latest_review_per_reviewer_controls_release() -> None:
    change = _review(sequence=1, state=ReviewState.CHANGES_REQUESTED)
    approve = _review(sequence=2, state=ReviewState.APPROVED, source_ref="github:review:2")
    repaired = _assess(review_events=(change, approve))
    assert repaired.verdict is AssessmentVerdict.ELIGIBLE
    assert repaired.review_state is ReviewAssessmentState.SATISFIED
    blocked = _assess(review_events=(approve, dataclasses.replace(change, sequence=3, source_ref="github:review:3")))
    assert blocked.verdict is AssessmentVerdict.REFUSED
    assert blocked.review_state is ReviewAssessmentState.BLOCKED
    assert _issue(blocked, AssessmentIssue.CHANGES_REQUESTED)


def test_incomplete_review_history_is_unknown_and_missing_approval_or_thread_is_held() -> None:
    incomplete = _assess(reviews_complete=False)
    assert incomplete.verdict is AssessmentVerdict.UNKNOWN
    assert _issue(incomplete, AssessmentIssue.REVIEW_COVERAGE_PARTIAL)
    missing = _assess(review_events=())
    assert missing.verdict is AssessmentVerdict.HELD
    assert _issue(missing, AssessmentIssue.REVIEW_REQUIRED)
    thread = _assess(unresolved_required_threads=1)
    assert thread.verdict is AssessmentVerdict.HELD
    assert _issue(thread, AssessmentIssue.UNRESOLVED_REVIEW_THREAD)


def test_typed_current_source_evidence_is_required_and_exactly_bound() -> None:
    missing = _assess(current_source_evidence=None)
    assert missing.verdict is AssessmentVerdict.UNKNOWN
    assert missing.source_state is SourceAssessmentState.UNKNOWN
    assert _issue(missing, AssessmentIssue.SOURCE_EVIDENCE_MISSING)
    mismatch = _assess(current_source_evidence=_source_evidence(subject=_subject(repository="other/repo")))
    assert mismatch.verdict is AssessmentVerdict.REFUSED
    assert mismatch.source_state is SourceAssessmentState.INCOMPATIBLE
    assert _issue(mismatch, AssessmentIssue.SOURCE_SUBJECT_MISMATCH)


def test_source_owner_revision_future_conflict_and_incompatible_law_refuse() -> None:
    cases = (
        (_source_evidence(owner_id="other-owner"), AssessmentIssue.SOURCE_OWNER_MISMATCH),
        (_source_evidence(revision="other-revision"), AssessmentIssue.SOURCE_REVISION_MISMATCH),
        (_source_evidence(observed_at=NOW + 1), AssessmentIssue.SOURCE_FUTURE),
        (_source_evidence(coverage=SourceCoverage.CONFLICT), AssessmentIssue.SOURCE_CONFLICT),
        (_source_evidence(law_state=SourceLawState.INCOMPATIBLE), AssessmentIssue.SOURCE_LAW_INCOMPATIBLE),
    )
    for evidence, issue in cases:
        result = _assess(current_source_evidence=evidence)
        assert result.verdict is AssessmentVerdict.REFUSED
        assert _issue(result, issue)
        assert result.expected_head_release is None


def test_stale_incomplete_or_unknown_source_evidence_is_unknown() -> None:
    cases = (
        (_source_evidence(observed_at=NOW - 301), AssessmentIssue.SOURCE_STALE),
        (_source_evidence(coverage=SourceCoverage.STALE), AssessmentIssue.SOURCE_STALE),
        (_source_evidence(coverage=SourceCoverage.INCOMPLETE), AssessmentIssue.SOURCE_INCOMPLETE),
        (_source_evidence(law_state=SourceLawState.UNKNOWN), AssessmentIssue.SOURCE_LAW_UNKNOWN),
    )
    for evidence, issue in cases:
        result = _assess(current_source_evidence=evidence)
        assert result.verdict is AssessmentVerdict.UNKNOWN
        assert _issue(result, issue)
        assert result.expected_head_release is None


def test_current_base_requirement_and_typed_behind_compatibility_are_separate() -> None:
    behind_target = _target(base_sha="d" * 40, merge_base_sha="d" * 40, behind_by=1)
    held = _assess(target=behind_target, current_source_evidence=_source_evidence(behind_target))
    assert held.verdict is AssessmentVerdict.HELD
    assert held.merge_context_state is MergeContextState.HELD
    assert _issue(held, AssessmentIssue.CURRENT_BASE_REQUIRED)
    compatible = _assess(
        target=behind_target,
        current_source_evidence=_source_evidence(behind_target),
        current_base_required=False,
    )
    assert compatible.verdict is AssessmentVerdict.ELIGIBLE
    assert compatible.merge_context_state is MergeContextState.BEHIND_COMPATIBLE


def test_proven_live_requires_exact_typed_production_proof() -> None:
    missing = _assess(
        claimed_capability_state=CapabilityState.PROVEN_LIVE,
        production_proof_required=True,
    )
    assert missing.verdict is AssessmentVerdict.REFUSED
    assert missing.production_state is ProductionAssessmentState.MISSING
    assert missing.completion_claim_state is CompletionClaimState.OVERSTATED
    assert _issue(missing, AssessmentIssue.PRODUCTION_PROOF_MISSING)
    assert _issue(missing, AssessmentIssue.COMPLETION_CLAIM_OVERSTATED)
    assert missing.expected_head_release is None

    valid = _assess(
        claimed_capability_state=CapabilityState.PROVEN_LIVE,
        production_proof_required=True,
        production_proof=_production_proof(),
    )
    assert valid.verdict is AssessmentVerdict.ELIGIBLE
    assert valid.production_state is ProductionAssessmentState.PRESENT
    assert valid.completion_claim_state is CompletionClaimState.VALID

    mismatched = _assess(
        claimed_capability_state=CapabilityState.PROVEN_LIVE,
        production_proof_required=True,
        production_proof=_production_proof(subject_id="wrong-subject"),
    )
    assert mismatched.verdict is AssessmentVerdict.REFUSED
    assert _issue(mismatched, AssessmentIssue.PRODUCTION_PROOF_INVALID)
    assert _issue(mismatched, AssessmentIssue.COMPLETION_CLAIM_OVERSTATED)
    assert mismatched.expected_head_release is None


def test_partial_stale_future_or_wrong_target_production_proof_never_greens() -> None:
    cases = (
        (_production_proof(coverage=SourceCoverage.INCOMPLETE), AssessmentIssue.PRODUCTION_PROOF_PARTIAL),
        (_production_proof(observed_at=NOW - 301), AssessmentIssue.PRODUCTION_PROOF_STALE),
        (_production_proof(observed_at=NOW + 1), AssessmentIssue.PRODUCTION_PROOF_FUTURE),
        (_production_proof(target_subject=_subject(candidate_sha="d" * 40)), AssessmentIssue.PRODUCTION_PROOF_INVALID),
    )
    for proof, issue in cases:
        result = _assess(
            claimed_capability_state=CapabilityState.PROVEN_LIVE,
            production_proof_required=True,
            production_proof=proof,
        )
        assert result.verdict is AssessmentVerdict.REFUSED
        assert _issue(result, issue)
        assert result.expected_head_release is None


def test_prior_effect_unknown_refuses_without_exact_receipt() -> None:
    result = _assess(prior_effect_state=EffectState.EFFECT_UNKNOWN)
    assert result.verdict is AssessmentVerdict.REFUSED
    assert result.effective_prior_effect_state is EffectState.EFFECT_UNKNOWN
    assert _issue(result, AssessmentIssue.PRIOR_EFFECT_UNKNOWN)
    assert result.expected_head_release is None


def test_exact_merged_receipt_reconciles_lost_response_as_applied_without_retry() -> None:
    merged_target = _target(
        state=PullRequestState.MERGED,
        draft=False,
        merged=True,
        merged_commit_sha=MERGED_SHA,
    )
    receipt = MergedEffectReceipt(
        repository=REPOSITORY,
        repository_id=REPOSITORY_ID,
        pull_request_number=PR_NUMBER,
        candidate_sha=CANDIDATE_SHA,
        merged_commit_sha=MERGED_SHA,
        changed_paths=PATHS,
        source_ref="github:merged-effect:295",
    )
    result = _assess(
        target=merged_target,
        current_source_evidence=_source_evidence(merged_target),
        prior_effect_state=EffectState.EFFECT_UNKNOWN,
        merged_effect_receipt=receipt,
    )
    assert result.verdict is AssessmentVerdict.REFUSED
    assert result.effective_prior_effect_state is EffectState.APPLIED
    assert _issue(result, AssessmentIssue.PRIOR_EFFECT_APPLIED)
    assert not _issue(result, AssessmentIssue.PRIOR_EFFECT_UNKNOWN)
    assert result.expected_head_release is None


def test_mismatched_or_spurious_merged_effect_receipt_refuses() -> None:
    mismatched = MergedEffectReceipt(
        repository=REPOSITORY,
        repository_id=REPOSITORY_ID,
        pull_request_number=PR_NUMBER,
        candidate_sha="d" * 40,
        merged_commit_sha=MERGED_SHA,
        changed_paths=PATHS,
        source_ref="github:merged-effect:mismatch",
    )
    merged_target = _target(
        state=PullRequestState.MERGED,
        draft=False,
        merged=True,
        merged_commit_sha=MERGED_SHA,
    )
    unknown = _assess(
        target=merged_target,
        current_source_evidence=_source_evidence(merged_target),
        prior_effect_state=EffectState.EFFECT_UNKNOWN,
        merged_effect_receipt=mismatched,
    )
    assert unknown.verdict is AssessmentVerdict.REFUSED
    assert unknown.effective_prior_effect_state is EffectState.EFFECT_UNKNOWN
    assert _issue(unknown, AssessmentIssue.PRIOR_EFFECT_UNKNOWN)
    spurious = _assess(merged_effect_receipt=mismatched)
    assert spurious.verdict is AssessmentVerdict.REFUSED
    assert _issue(spurious, AssessmentIssue.PRIOR_EFFECT_CONFLICT)


def test_disallowed_merge_method_refuses_and_never_emits_release_tuple() -> None:
    result = _assess(requested_merge_method=MergeMethod.MERGE)
    assert result.verdict is AssessmentVerdict.REFUSED
    assert _issue(result, AssessmentIssue.MERGE_METHOD_REFUSED)
    assert result.expected_head_release is None


def test_hard_contradiction_does_not_hide_partial_coverage_issues() -> None:
    result = _assess(
        expected_target=_expected(repository="other/repo"),
        target=_target(changed_paths_complete=False),
        checks_complete=False,
        reviews_complete=False,
        semantic_owners_complete=False,
        carriers_complete=False,
        writers_complete=False,
        path_collisions_complete=False,
        current_source_evidence=None,
    )
    assert result.verdict is AssessmentVerdict.REFUSED
    for issue in (
        AssessmentIssue.REPOSITORY_MISMATCH,
        AssessmentIssue.PATH_COVERAGE_PARTIAL,
        AssessmentIssue.CHECK_COVERAGE_PARTIAL,
        AssessmentIssue.REVIEW_COVERAGE_PARTIAL,
        AssessmentIssue.SEMANTIC_OWNER_COVERAGE_PARTIAL,
        AssessmentIssue.CARRIER_COVERAGE_PARTIAL,
        AssessmentIssue.WRITER_COVERAGE_PARTIAL,
        AssessmentIssue.PATH_COLLISION_COVERAGE_PARTIAL,
        AssessmentIssue.SOURCE_EVIDENCE_MISSING,
    ):
        assert _issue(result, issue)


def test_output_collects_all_source_refs_without_echoing_secret_payloads() -> None:
    packet = _packet(
        path_collisions=(
            PathCollisionFact("docs/unrelated.md", "other-operation", "github:collision:one"),
        )
    )
    result = assess_github_release(packet)
    refs = set(result.source_refs)
    assert "github:collision:one" in refs
    assert "github:check:test:1" in refs
    assert "github:review:1" in refs
    assert "github:protected-source:current" in refs
    serialized = json.dumps(result.to_dict(), sort_keys=True)
    assert "post_image" not in serialized
    assert "prepared_token" not in serialized


def test_malformed_packets_and_secret_shaped_identifiers_fail_before_assessment() -> None:
    with pytest.raises(AssessmentInputError):
        assess_github_release(dataclasses.replace(_packet(), schema="wrong"))
    with pytest.raises(AssessmentInputError):
        assess_github_release(dataclasses.replace(_packet(), operation_key="ghp_" + "A" * 40))
    with pytest.raises(AssessmentInputError):
        assess_github_release(dataclasses.replace(_packet(), source_refs=("Bearer secret",)))
    with pytest.raises(AssessmentInputError):
        assess_github_release(
            dataclasses.replace(
                _packet(),
                target=dataclasses.replace(_target(), state=PullRequestState.MERGED, merged=False),
            )
        )


def test_module_is_pure_and_imports_no_effectful_surfaces() -> None:
    module_path = Path(__file__).parents[1] / "control_plane" / "github_release_assessment.py"
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".", 1)[0])
    assert imports.isdisjoint(
        {
            "asyncio",
            "github",
            "httpx",
            "os",
            "pathlib",
            "random",
            "requests",
            "socket",
            "subprocess",
            "time",
            "urllib",
        }
    )
    called: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            called.add(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            called.add(node.func.attr)
    assert called.isdisjoint({"open", "connect", "request", "urlopen", "update_ref", "merge"})
