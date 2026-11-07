from __future__ import annotations

import ast
import dataclasses
import hashlib
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
    SourceOwner,
    SourceReference,
    SourceReferenceCoverage,
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


def _source_ref(
    resource_kind: str,
    resource_id: str,
    *,
    revision: str = CANDIDATE_SHA,
    observed_at: int = NOW,
    valid_at: int | None = None,
    owner: SourceOwner = SourceOwner.GITHUB,
    repository: str | None = REPOSITORY,
    coverage: SourceReferenceCoverage = SourceReferenceCoverage.COMPLETE,
    truncated: bool = False,
    continuation: str | None = None,
    content_seed: str | None = None,
) -> SourceReference:
    seed = content_seed or f"{resource_kind}:{resource_id}:{revision}:{observed_at}"
    return SourceReference(
        source_kind="owner_native",
        owner=owner,
        repository=repository,
        resource_kind=resource_kind,
        resource_id=resource_id,
        revision=revision,
        observed_at=observed_at,
        valid_at=valid_at,
        content_sha256=hashlib.sha256(seed.encode("utf-8")).hexdigest(),
        coverage=coverage,
        truncated=truncated,
        continuation=continuation,
    )


def _packet_with_source_reference_text(
    field_name: str, value: str
) -> AssessmentInput:
    packet = _packet()
    source_ref = dataclasses.replace(
        packet.checks_source_ref,
        **{field_name: value},
    )
    return dataclasses.replace(packet, checks_source_ref=source_ref)


def _packet_with_extra_source_reference_text(
    field_name: str, value: str
) -> AssessmentInput:
    packet = _packet()
    extra = _source_ref(
        "extra_source",
        "source-token-validation",
        revision="source-token-validation-v1",
        content_seed=f"{field_name}:{value}",
    )
    extra = dataclasses.replace(extra, **{field_name: value})
    return dataclasses.replace(packet, source_refs=packet.source_refs + (extra,))


def _assert_unsafe_source_reference_text_is_rejected(
    field_name: str, value: str
) -> None:
    with pytest.raises(AssessmentInputError) as raised:
        assess_github_release(_packet_with_source_reference_text(field_name, value))
    assert field_name in str(raised.value)
    assert value not in str(raised.value)


def _check_source_resource_id(
    context: str, app_id: int | None, attempt: int, sequence: int
) -> str:
    digest = hashlib.sha256(
        json.dumps(
            [context, app_id, attempt, sequence],
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    return f"check:{digest}"


def _collision_source_ref(path: str, operation_key: str) -> SourceReference:
    digest = hashlib.sha256(
        json.dumps(
            [path, operation_key],
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    return _source_ref("path_collision", f"collision:{digest}")


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
    candidate_sha = changes.get("candidate_sha", CANDIDATE_SHA)
    assert isinstance(candidate_sha, str)
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
        source_ref=_source_ref("pull_request", "295", revision=candidate_sha),
        changed_paths_source_ref=_source_ref(
            "pull_request_changed_paths", "295", revision=candidate_sha
        ),
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


def _source_evidence(
    target: PullRequestTarget | None = None, **changes: object
) -> CurrentSourceEvidence:
    revision = changes.get("revision", SOURCE_REVISION)
    observed_at = changes.get("observed_at", NOW)
    assert isinstance(revision, str)
    assert isinstance(observed_at, int)
    base = CurrentSourceEvidence(
        subject=_subject(target),
        owner_id=SOURCE_OWNER,
        revision=SOURCE_REVISION,
        observed_at=NOW,
        coverage=SourceCoverage.COMPLETE,
        law_state=SourceLawState.COMPATIBLE,
        source_ref=_source_ref(
            "protected_source_law",
            SOURCE_OWNER,
            revision=revision,
            observed_at=observed_at,
        ),
    )
    return dataclasses.replace(base, **changes)


def _production_proof(
    target: PullRequestTarget | None = None, **changes: object
) -> ProductionProof:
    revision = changes.get("revision", PRODUCTION_REVISION)
    observed_at = changes.get("observed_at", NOW)
    assert isinstance(revision, str)
    assert isinstance(observed_at, int)
    base = ProductionProof(
        capability_id=CAPABILITY,
        subject_id=PRODUCTION_SUBJECT,
        target_subject=_subject(target),
        owner_id=PRODUCTION_OWNER,
        revision=PRODUCTION_REVISION,
        observed_at=NOW,
        coverage=SourceCoverage.COMPLETE,
        state=ProductionProofState.PRESENT,
        source_ref=_source_ref(
            "production_proof",
            PRODUCTION_SUBJECT,
            revision=revision,
            observed_at=observed_at,
            owner=SourceOwner.PRODUCTION_OWNER,
        ),
    )
    return dataclasses.replace(base, **changes)


def _carrier(target: PullRequestTarget | None = None, **changes: object) -> CarrierFact:
    target = target or _target()
    candidate_sha = changes.get("candidate_sha", target.candidate_sha)
    carrier_ref = changes.get("carrier_ref", "github:pr:295")
    assert isinstance(candidate_sha, str)
    assert isinstance(carrier_ref, str)
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
        source_ref=_source_ref("operation_carrier", carrier_ref, revision=candidate_sha),
    )
    return dataclasses.replace(base, **changes)


def _writer(**changes: object) -> WriterFact:
    writer_id = changes.get("writer_id", WRITER)
    assert isinstance(writer_id, str)
    base = WriterFact(
        writer_id=WRITER,
        operation_key=OPERATION,
        repository_id=REPOSITORY_ID,
        pull_request_number=PR_NUMBER,
        paths=PATHS,
        active=True,
        source_ref=_source_ref(
            "current_writer",
            writer_id,
            owner=SourceOwner.RUNTIME_BINDING,
        ),
    )
    return dataclasses.replace(base, **changes)


def _check_attempt(**changes: object) -> CheckAttempt:
    head_sha = changes.get("head_sha", CANDIDATE_SHA)
    attempt = changes.get("attempt", 1)
    sequence = changes.get("sequence", 1)
    assert isinstance(head_sha, str)
    assert isinstance(attempt, int)
    assert isinstance(sequence, int)
    base = CheckAttempt(
        identity=CHECK,
        head_sha=CANDIDATE_SHA,
        attempt=1,
        sequence=1,
        status=CheckStatus.COMPLETED,
        conclusion=CheckConclusion.SUCCESS,
        applicable=True,
        superseded=False,
        source_ref=_source_ref(
            "check_attempt",
            _check_source_resource_id("test", 15368, attempt, sequence),
            revision=head_sha,
        ),
    )
    return dataclasses.replace(base, **changes)


def _review(**changes: object) -> ReviewEvent:
    head_sha = changes.get("head_sha", CANDIDATE_SHA)
    sequence = changes.get("sequence", 1)
    assert isinstance(head_sha, str)
    assert isinstance(sequence, int)
    base = ReviewEvent(
        reviewer_id="independent-reviewer",
        head_sha=CANDIDATE_SHA,
        sequence=1,
        state=ReviewState.APPROVED,
        source_ref=_source_ref(
            "review_event",
            f"independent-reviewer:{sequence}",
            revision=head_sha,
        ),
    )
    return dataclasses.replace(base, **changes)


def _packet(**changes: object) -> AssessmentInput:
    target = changes.get("target")
    assert target is None or isinstance(target, PullRequestTarget)
    target = target or _target()
    revision = target.candidate_sha
    base = AssessmentInput(
        schema=INPUT_SCHEMA,
        operation_key=OPERATION,
        observed_at=NOW,
        expected_target=_expected(),
        target=target,
        policy_source_ref=_source_ref(
            "protected_policy",
            "github-semantic-contract",
            revision=SOURCE_REVISION,
        ),
        expected_paths=PATHS,
        expected_semantic_owners=(
            SemanticOwnerExpectation("control_plane", OWNER),
            SemanticOwnerExpectation("tests", OWNER),
        ),
        semantic_owner_facts=(
            SemanticOwnerFact(
                "control_plane",
                OWNER,
                OPERATION,
                True,
                _source_ref(
                    "semantic_owner",
                    "control_plane",
                    revision=revision,
                    owner=SourceOwner.AGENT_OS,
                ),
            ),
            SemanticOwnerFact(
                "tests",
                OWNER,
                OPERATION,
                True,
                _source_ref(
                    "semantic_owner",
                    "tests",
                    revision=revision,
                    owner=SourceOwner.AGENT_OS,
                ),
            ),
        ),
        semantic_owners_complete=True,
        semantic_owners_source_ref=_source_ref(
            "semantic_owner_census",
            str(PR_NUMBER),
            revision=revision,
            owner=SourceOwner.AGENT_OS,
        ),
        carrier_facts=(_carrier(target),),
        carriers_complete=True,
        carriers_source_ref=_source_ref("carrier_census", str(PR_NUMBER), revision=revision),
        expected_writer_id=WRITER,
        writer_facts=(_writer(),),
        writers_complete=True,
        writers_source_ref=_source_ref(
            "writer_census",
            str(PR_NUMBER),
            revision=revision,
            owner=SourceOwner.RUNTIME_BINDING,
        ),
        path_collisions=(),
        path_collisions_complete=True,
        path_collisions_source_ref=_source_ref(
            "path_collision_census", str(PR_NUMBER), revision=revision
        ),
        branch_required_checks=(CHECK,),
        assessment_required_checks=(CHECK,),
        allowed_non_success_checks=(),
        check_attempts=(_check_attempt(),),
        checks_complete=True,
        checks_source_ref=_source_ref("check_census", str(PR_NUMBER), revision=revision),
        required_approvals=1,
        review_events=(_review(),),
        reviews_complete=True,
        reviews_source_ref=_source_ref("review_census", str(PR_NUMBER), revision=revision),
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
        source_refs=(
            _source_ref("packet_evidence", "pr-295", revision=revision),
            _source_ref(
                "protected_branch",
                "master",
                revision=PROTECTED_SHA,
                content_seed="extra-master",
            ),
        ),
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
        "organizational_authority_granted": False,
        "production_acceptance_claimed": False,
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
        _source_ref(
            "semantic_owner",
            "control_plane",
            owner=SourceOwner.AGENT_OS,
        ),
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
        source_ref=_source_ref("operation_carrier", "github:pr:999"),
    )
    result = _assess(carrier_facts=(_carrier(), other))
    assert result.verdict is AssessmentVerdict.ELIGIBLE
    assert result.carrier_state is CarrierAssessmentState.EXACT


def test_foreign_same_pr_or_candidate_ref_conflicts() -> None:
    foreign = _carrier(
        carrier_ref="github:foreign",
        operation_key="other-operation",
        source_ref=_source_ref("operation_carrier", "github:foreign"),
    )
    result = _assess(carrier_facts=(_carrier(), foreign))
    assert result.verdict is AssessmentVerdict.REFUSED
    assert result.carrier_state is CarrierAssessmentState.CONFLICT
    assert _issue(result, AssessmentIssue.OPERATION_CARRIER_CONFLICT)


def test_duplicate_exact_carriers_conflict_and_incomplete_or_missing_carrier_is_unknown() -> None:
    duplicate = dataclasses.replace(
        _carrier(), carrier_ref="github:pr:295:duplicate", source_ref=_source_ref("operation_carrier", "github:pr:295:duplicate")
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
    second = _writer(writer_id="second-writer", source_ref=_source_ref("current_writer", "second-writer", owner=SourceOwner.RUNTIME_BINDING))
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
    disjoint = PathCollisionFact("docs/unrelated.md", "other-operation", _collision_source_ref("docs/unrelated.md", "other-operation"))
    clean = _assess(path_collisions=(disjoint,))
    assert clean.verdict is AssessmentVerdict.ELIGIBLE
    overlap = PathCollisionFact("control_plane", "other-operation", _collision_source_ref("control_plane", "other-operation"))
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
    )
    success = _check_attempt(
        attempt=2,
        sequence=1,
        conclusion=CheckConclusion.SUCCESS,
    )
    green = _assess(check_attempts=(failed, success))
    assert green.verdict is AssessmentVerdict.ELIGIBLE
    assert green.check_state is CheckAssessmentState.GREEN
    later_failure = dataclasses.replace(
        failed,
        attempt=2,
        sequence=2,
        source_ref=_source_ref(
            "check_attempt",
            _check_source_resource_id("test", 15368, 2, 2),
            revision=CANDIDATE_SHA,
        ),
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
    approve = _review(sequence=2, state=ReviewState.APPROVED, source_ref=_source_ref("review_event", "independent-reviewer:2"))
    repaired = _assess(review_events=(change, approve))
    assert repaired.verdict is AssessmentVerdict.ELIGIBLE
    assert repaired.review_state is ReviewAssessmentState.SATISFIED
    blocked = _assess(review_events=(approve, dataclasses.replace(change, sequence=3, source_ref=_source_ref("review_event", "independent-reviewer:3"))))
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
        source_ref=_source_ref("merged_effect", MERGED_SHA, revision=MERGED_SHA),
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
        source_ref=_source_ref("merged_effect", "mismatch", revision=MERGED_SHA),
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
            PathCollisionFact("docs/unrelated.md", "other-operation", _collision_source_ref("docs/unrelated.md", "other-operation")),
        )
    )
    result = assess_github_release(packet)
    refs = {(ref.resource_kind, ref.resource_id) for ref in result.source_refs}
    assert ("path_collision", _collision_source_ref("docs/unrelated.md", "other-operation").resource_id) in refs
    assert (
        "check_attempt",
        _check_source_resource_id("test", 15368, 1, 1),
    ) in refs
    assert ("review_event", "independent-reviewer:1") in refs
    assert ("protected_source_law", SOURCE_OWNER) in refs
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


# ---------------------------------------------------------------------------
# R2 adversarial closure for the independent exact-head review
# ---------------------------------------------------------------------------


def test_output_exposes_all_contractual_head_and_merge_context_fields() -> None:
    result = _assess()
    payload = result.to_dict()
    assert payload["expected_head_sha"] == CANDIDATE_SHA
    assert payload["merge_base_sha"] == PROTECTED_SHA
    assert payload["ahead_by"] == 2
    assert payload["behind_by"] == 0
    assert payload["expected_head_release"]["organizational_authority_granted"] is False
    assert payload["expected_head_release"]["production_acceptance_claimed"] is False


def test_release_tuple_never_implies_organizational_or_production_acceptance() -> None:
    result = _assess(
        claimed_capability_state=CapabilityState.BUILT_NOT_PROVEN,
        production_proof_required=False,
    )
    assert result.verdict is AssessmentVerdict.ELIGIBLE
    assert result.expected_head_release is not None
    assert result.expected_head_release.organizational_authority_granted is False
    assert result.expected_head_release.production_acceptance_claimed is False


def test_hostile_check_identity_subclass_cannot_spoof_validated_identity() -> None:
    class HostileCheckIdentity(CheckIdentity):
        def key(self) -> tuple[str, int]:
            return CHECK.context, CHECK.app_id or -1

    hostile = HostileCheckIdentity("untrusted-different-check", 999_999)
    hostile_attempt = dataclasses.replace(
        _check_attempt(),
        identity=hostile,
        source_ref=_source_ref("check_attempt", "hostile", revision=CANDIDATE_SHA),
    )
    packet = _packet(
        assessment_required_checks=(hostile,),
        check_attempts=(hostile_attempt,),
    )
    with pytest.raises(AssessmentInputError):
        assess_github_release(packet)


def test_adjudicator_contains_no_virtual_check_identity_key_call() -> None:
    module_path = Path(__file__).parents[1] / "control_plane" / "github_release_assessment.py"
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    virtual_key_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "key"
    ]
    assert virtual_key_calls == []


def test_assessment_input_subclass_is_rejected_before_adjudication() -> None:
    class HostileAssessmentInput(AssessmentInput):
        pass

    packet = _packet()
    values = {field.name: getattr(packet, field.name) for field in dataclasses.fields(packet)}
    hostile = HostileAssessmentInput(**values)
    with pytest.raises(AssessmentInputError):
        assess_github_release(hostile)


def test_source_reference_subclass_is_rejected_before_adjudication() -> None:
    class HostileSourceReference(SourceReference):
        pass

    original = _packet().checks_source_ref
    values = {field.name: getattr(original, field.name) for field in dataclasses.fields(original)}
    hostile = HostileSourceReference(**values)
    with pytest.raises(AssessmentInputError):
        assess_github_release(dataclasses.replace(_packet(), checks_source_ref=hostile))


def test_primitive_subclasses_are_rejected_before_adjudication() -> None:
    class HostileString(str):
        pass

    with pytest.raises(AssessmentInputError):
        assess_github_release(
            dataclasses.replace(_packet(), operation_key=HostileString(OPERATION))
        )


@pytest.mark.parametrize(
    ("field_name", "component_name", "unknown_state", "coverage_issue"),
    [
        (
            "semantic_owners_source_ref",
            "semantic_owner_state",
            SemanticOwnerAssessmentState.UNKNOWN,
            AssessmentIssue.SEMANTIC_OWNER_COVERAGE_PARTIAL,
        ),
        (
            "carriers_source_ref",
            "carrier_state",
            CarrierAssessmentState.UNKNOWN,
            AssessmentIssue.CARRIER_COVERAGE_PARTIAL,
        ),
        (
            "writers_source_ref",
            "writer_state",
            WriterAssessmentState.UNKNOWN,
            AssessmentIssue.WRITER_COVERAGE_PARTIAL,
        ),
        (
            "checks_source_ref",
            "check_state",
            CheckAssessmentState.UNKNOWN,
            AssessmentIssue.CHECK_COVERAGE_PARTIAL,
        ),
        (
            "reviews_source_ref",
            "review_state",
            ReviewAssessmentState.UNKNOWN,
            AssessmentIssue.REVIEW_COVERAGE_PARTIAL,
        ),
    ],
)
def test_naked_complete_boolean_cannot_override_partial_typed_census(
    field_name, component_name, unknown_state, coverage_issue
) -> None:
    packet = _packet()
    partial = dataclasses.replace(
        getattr(packet, field_name),
        coverage=SourceReferenceCoverage.PARTIAL,
    )
    result = assess_github_release(dataclasses.replace(packet, **{field_name: partial}))
    assert result.verdict is AssessmentVerdict.UNKNOWN
    assert getattr(result, component_name) is unknown_state
    assert _issue(result, AssessmentIssue.SOURCE_INCOMPLETE)
    assert _issue(result, coverage_issue)
    assert result.expected_head_release is None


def test_complete_changed_paths_boolean_cannot_override_truncated_source() -> None:
    target = _target()
    truncated = dataclasses.replace(
        target.changed_paths_source_ref,
        truncated=True,
        continuation="page:2",
    )
    target = dataclasses.replace(target, changed_paths_source_ref=truncated)
    result = _assess(target=target, current_source_evidence=_source_evidence(target))
    assert result.verdict is AssessmentVerdict.UNKNOWN
    assert result.path_state is PathState.UNKNOWN
    assert _issue(result, AssessmentIssue.SOURCE_INCOMPLETE)
    assert _issue(result, AssessmentIssue.PATH_COVERAGE_PARTIAL)


def test_complete_target_boolean_cannot_override_partial_target_source() -> None:
    target = _target()
    partial = dataclasses.replace(
        target.source_ref,
        coverage=SourceReferenceCoverage.PARTIAL,
    )
    target = dataclasses.replace(target, source_ref=partial)
    result = _assess(target=target, current_source_evidence=_source_evidence(target))
    assert result.verdict is AssessmentVerdict.UNKNOWN
    assert result.merge_context_state is MergeContextState.UNKNOWN
    assert _issue(result, AssessmentIssue.SOURCE_INCOMPLETE)
    assert _issue(result, AssessmentIssue.BASE_OR_MERGE_CONTEXT_UNKNOWN)


def test_complete_collision_boolean_cannot_override_unknown_census_source() -> None:
    packet = _packet()
    unknown = dataclasses.replace(
        packet.path_collisions_source_ref,
        coverage=SourceReferenceCoverage.UNKNOWN,
    )
    result = assess_github_release(
        dataclasses.replace(packet, path_collisions_source_ref=unknown)
    )
    assert result.verdict is AssessmentVerdict.UNKNOWN
    assert _issue(result, AssessmentIssue.SOURCE_INCOMPLETE)
    assert _issue(result, AssessmentIssue.PATH_COLLISION_COVERAGE_PARTIAL)


@pytest.mark.parametrize(
    ("fact_field", "component_name", "unknown_state", "coverage_issue"),
    [
        (
            "carrier_facts",
            "carrier_state",
            CarrierAssessmentState.UNKNOWN,
            AssessmentIssue.CARRIER_COVERAGE_PARTIAL,
        ),
        (
            "writer_facts",
            "writer_state",
            WriterAssessmentState.UNKNOWN,
            AssessmentIssue.WRITER_COVERAGE_PARTIAL,
        ),
        (
            "check_attempts",
            "check_state",
            CheckAssessmentState.UNKNOWN,
            AssessmentIssue.CHECK_COVERAGE_PARTIAL,
        ),
        (
            "review_events",
            "review_state",
            ReviewAssessmentState.UNKNOWN,
            AssessmentIssue.REVIEW_COVERAGE_PARTIAL,
        ),
    ],
)
def test_partial_fact_reference_cannot_supply_positive_evidence(
    fact_field, component_name, unknown_state, coverage_issue
) -> None:
    packet = _packet()
    fact = getattr(packet, fact_field)[0]
    partial_ref = dataclasses.replace(
        fact.source_ref,
        coverage=SourceReferenceCoverage.PARTIAL,
    )
    partial_fact = dataclasses.replace(fact, source_ref=partial_ref)
    result = assess_github_release(
        dataclasses.replace(packet, **{fact_field: (partial_fact,)})
    )
    assert result.verdict is AssessmentVerdict.UNKNOWN
    assert getattr(result, component_name) is unknown_state
    assert _issue(result, AssessmentIssue.SOURCE_INCOMPLETE)
    assert _issue(result, coverage_issue)


def test_wrong_head_revision_on_check_source_refuses() -> None:
    attempt = _check_attempt()
    wrong_ref = dataclasses.replace(attempt.source_ref, revision="d" * 40)
    result = _assess(check_attempts=(dataclasses.replace(attempt, source_ref=wrong_ref),))
    assert result.verdict is AssessmentVerdict.REFUSED
    assert _issue(result, AssessmentIssue.SOURCE_REVISION_MISMATCH)
    assert result.expected_head_release is None


def test_wrong_protected_policy_revision_refuses() -> None:
    packet = _packet()
    wrong = dataclasses.replace(packet.policy_source_ref, revision="other-policy-revision")
    result = assess_github_release(dataclasses.replace(packet, policy_source_ref=wrong))
    assert result.verdict is AssessmentVerdict.REFUSED
    assert _issue(result, AssessmentIssue.SOURCE_REVISION_MISMATCH)


def test_stale_review_census_is_unknown_even_when_reviews_complete_true() -> None:
    packet = _packet()
    stale = dataclasses.replace(packet.reviews_source_ref, observed_at=NOW - 301)
    result = assess_github_release(dataclasses.replace(packet, reviews_source_ref=stale))
    assert result.verdict is AssessmentVerdict.UNKNOWN
    assert result.review_state is ReviewAssessmentState.UNKNOWN
    assert _issue(result, AssessmentIssue.SOURCE_STALE)
    assert _issue(result, AssessmentIssue.REVIEW_COVERAGE_PARTIAL)


def test_conflicting_same_revision_source_records_refuse() -> None:
    packet = _packet()
    conflicting = dataclasses.replace(
        packet.target.source_ref,
        content_sha256="f" * 64,
    )
    result = assess_github_release(
        dataclasses.replace(packet, source_refs=packet.source_refs + (conflicting,))
    )
    assert result.verdict is AssessmentVerdict.REFUSED
    assert _issue(result, AssessmentIssue.SOURCE_CONFLICT)
    assert result.source_state is SourceAssessmentState.CURRENT
    assert result.merge_context_state is MergeContextState.UNKNOWN


def test_source_record_repository_mismatch_refuses() -> None:
    packet = _packet()
    foreign = dataclasses.replace(packet.checks_source_ref, repository="other/repository")
    result = assess_github_release(dataclasses.replace(packet, checks_source_ref=foreign))
    assert result.verdict is AssessmentVerdict.REFUSED
    assert _issue(result, AssessmentIssue.SOURCE_SUBJECT_MISMATCH)


def test_source_observation_future_refuses() -> None:
    packet = _packet()
    future = dataclasses.replace(packet.carriers_source_ref, observed_at=NOW + 1)
    result = assess_github_release(dataclasses.replace(packet, carriers_source_ref=future))
    assert result.verdict is AssessmentVerdict.REFUSED
    assert _issue(result, AssessmentIssue.SOURCE_FUTURE)


def test_current_source_record_and_evidence_timestamp_must_agree() -> None:
    evidence = dataclasses.replace(_source_evidence(), observed_at=NOW - 1)
    result = _assess(current_source_evidence=evidence)
    assert result.verdict is AssessmentVerdict.REFUSED
    assert _issue(result, AssessmentIssue.SOURCE_CONFLICT)


def test_every_emitted_source_reference_is_closed_typed_and_secret_free() -> None:
    result = _assess()
    assert result.source_refs
    assert all(type(ref) is SourceReference for ref in result.source_refs)
    for ref in result.source_refs:
        payload = ref.to_dict()
        assert payload["owner"] in {owner.value for owner in SourceOwner}
        assert len(payload["content_sha256"]) == 64
        assert payload["revision"]
        assert payload["observed_at"] == NOW
    rendered = json.dumps(result.to_dict(), sort_keys=True)
    assert "prepared_token" not in rendered
    assert "authorization" not in rendered.lower()


def test_source_reference_order_is_canonical_and_permutation_stable() -> None:
    first = _assess()
    packet = _packet(source_refs=tuple(reversed(_packet().source_refs)))
    second = assess_github_release(packet)
    assert first.to_dict() == second.to_dict()
    encoded = [json.dumps(ref.to_dict(), sort_keys=True) for ref in first.source_refs]
    assert encoded == sorted(encoded)


def test_malformed_source_reference_secret_and_invalid_content_digest_fail_early() -> None:
    packet = _packet()
    secret = dataclasses.replace(
        packet.checks_source_ref,
        resource_id="github_pat_abcdefghijklmnopqrstuvwxyz",
    )
    with pytest.raises(AssessmentInputError):
        assess_github_release(dataclasses.replace(packet, checks_source_ref=secret))
    invalid_digest = dataclasses.replace(packet.checks_source_ref, content_sha256="abc")
    with pytest.raises(AssessmentInputError):
        assess_github_release(dataclasses.replace(packet, checks_source_ref=invalid_digest))


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("source_kind", "AcCeSs_ToKeN:SuperSecret123"),
        ("source_kind", "CLIENT-SECRET:SuperSecret123"),
        ("resource_kind", "api.key:SuperSecret123"),
        ("resource_kind", "ToKeN:SuperSecret123"),
        ("resource_id", "artifact?SIG=SuperSecret123"),
        ("resource_id", "artifact#Signature:SuperSecret123"),
        ("resource_id", "artifact&SeCrEt=SuperSecret123"),
        ("revision", "branch?Credential=SuperSecret123"),
        ("revision", "branch#PassWd:SuperSecret123"),
        ("revision", "branch&PASSWORD=SuperSecret123"),
        ("continuation", "page:2&Authorization=SuperSecret123"),
    ],
)
def test_source_reference_rejects_generic_credential_assignments_without_echoing(
    field_name: str, value: str
) -> None:
    _assert_unsafe_source_reference_text_is_rejected(field_name, value)


@pytest.mark.parametrize("separator", tuple(":._/@#?=&,+-"))
def test_prefixed_credential_assignment_is_rejected_after_every_source_token_separator(
    separator: str,
) -> None:
    _assert_unsafe_source_reference_text_is_rejected(
        "resource_id",
        f"artifact{separator}access_token=SuperSecret123",
    )


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("source_kind", "artifact/access_token:SuperSecret123"),
        ("resource_kind", "artifact-access_token:SuperSecret123"),
        ("resource_id", "artifact,token=SuperSecret123"),
        ("revision", "branch@signature:SuperSecret123"),
        ("continuation", "page+client_secret=SuperSecret123"),
    ],
)
def test_every_assignment_capable_source_reference_field_rejects_prefixed_credentials(
    field_name: str, value: str
) -> None:
    _assert_unsafe_source_reference_text_is_rejected(field_name, value)


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("source_kind", "file:///Users/chris/private/project"),
        ("resource_kind", "https://internal.example/private"),
        ("resource_id", "http://localhost:8000/private"),
        ("resource_id", "https://127.0.0.1/private"),
        ("resource_id", "https://10.1.2.3/private"),
        ("revision", "https://172.16.1.2/private"),
        ("revision", "https://192.168.1.3/private"),
        ("revision", "C:/Users/chris/private/project"),
        ("continuation", "unc://private-server/share"),
        ("continuation", "internal.example/private?page=2"),
        ("resource_id", "/Users/chris/private/project"),
        ("revision", "~/private/project"),
        ("continuation", "C:\\Users\\chris\\private\\project"),
        ("resource_id", "\\\\private-server\\share"),
    ],
)
def test_source_reference_rejects_private_coordinates_without_echoing(
    field_name: str, value: str
) -> None:
    _assert_unsafe_source_reference_text_is_rejected(field_name, value)


@pytest.mark.parametrize("separator", tuple(":._/@#?=&,+-"))
def test_prefixed_private_coordinate_is_rejected_after_every_source_token_separator(
    separator: str,
) -> None:
    _assert_unsafe_source_reference_text_is_rejected(
        "resource_id",
        f"artifact{separator}https://internal.example/private",
    )


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("source_kind", "artifact:https://internal.example/private"),
        ("repository", "artifact/internal.local"),
        ("resource_kind", "artifact/file:///Users/chris/private/project"),
        ("resource_id", "artifact:10.1.2.3/private"),
        ("revision", "branch:C:/Users/chris/private/project"),
        ("continuation", "cursor@localhost:8000/private"),
    ],
)
def test_every_coordinate_capable_source_reference_field_rejects_prefixed_coordinates(
    field_name: str, value: str
) -> None:
    _assert_unsafe_source_reference_text_is_rejected(field_name, value)


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("source_kind", "token:SuperSecret123"),
        ("repository", "access_token=SuperSecret123"),
        ("resource_kind", "file:///private"),
        ("resource_id", "artifact?client_secret=SuperSecret123"),
        ("revision", "https://internal.example/private?sig=abcdef"),
        ("content_sha256", "authorization:SuperSecret123"),
        ("continuation", "C:/Users/chris/private/project"),
    ],
)
def test_every_model_visible_source_reference_text_field_is_closed_or_fenced(
    field_name: str, value: str
) -> None:
    _assert_unsafe_source_reference_text_is_rejected(field_name, value)


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("resource_id", "github:pr:295"),
        ("continuation", "page:2"),
        ("revision", "runtime-binding-generation-7"),
        ("resource_id", "check:" + "d" * 64),
        ("resource_id", "reviewer:1"),
        ("revision", "sol/sol-capability-fabric-gh1-20260830"),
        ("revision", "agentos-commit-123"),
    ],
)
def test_lawful_owner_native_source_reference_tokens_remain_accepted(
    field_name: str, value: str
) -> None:
    result = assess_github_release(
        _packet_with_extra_source_reference_text(field_name, value)
    )
    assert any(getattr(ref, field_name) == value for ref in result.source_refs)


def test_load_bearing_source_owner_is_bound_to_evidence_role() -> None:
    packet = _packet()
    wrong_owner = dataclasses.replace(
        packet.checks_source_ref,
        owner=SourceOwner.PRODUCTION_OWNER,
    )
    result = assess_github_release(
        dataclasses.replace(packet, checks_source_ref=wrong_owner)
    )
    assert result.verdict is AssessmentVerdict.REFUSED
    assert _issue(result, AssessmentIssue.SOURCE_OWNER_MISMATCH)
    assert result.expected_head_release is None


def test_load_bearing_source_resource_kind_is_bound_to_evidence_role() -> None:
    packet = _packet()
    wrong_kind = dataclasses.replace(
        packet.reviews_source_ref,
        resource_kind="check_census",
    )
    result = assess_github_release(
        dataclasses.replace(packet, reviews_source_ref=wrong_kind)
    )
    assert result.verdict is AssessmentVerdict.REFUSED
    assert _issue(result, AssessmentIssue.SOURCE_SUBJECT_MISMATCH)
    assert result.expected_head_release is None


def test_repository_scoped_github_source_cannot_omit_repository_identity() -> None:
    packet = _packet()
    unbound = dataclasses.replace(packet.target.source_ref, repository=None)
    target = dataclasses.replace(packet.target, source_ref=unbound)
    result = assess_github_release(
        dataclasses.replace(
            packet,
            target=target,
            current_source_evidence=_source_evidence(target),
        )
    )
    assert result.verdict is AssessmentVerdict.REFUSED
    assert _issue(result, AssessmentIssue.SOURCE_SUBJECT_MISMATCH)


def test_same_operation_on_different_active_carrier_conflicts() -> None:
    duplicate_operation = _carrier(
        carrier_ref="github:pr:999",
        pull_request_number=999,
        candidate_ref="sol/other-carrier",
        candidate_sha="d" * 40,
        source_ref=_source_ref(
            "operation_carrier",
            "github:pr:999",
            revision="d" * 40,
        ),
    )
    result = _assess(carrier_facts=(_carrier(), duplicate_operation))
    assert result.verdict is AssessmentVerdict.REFUSED
    assert result.carrier_state is CarrierAssessmentState.CONFLICT
    assert _issue(result, AssessmentIssue.OPERATION_CARRIER_CONFLICT)


def test_single_same_operation_carrier_on_wrong_target_conflicts_not_unknown() -> None:
    wrong = _carrier(
        carrier_ref="github:pr:999",
        pull_request_number=999,
        candidate_ref="sol/other-carrier",
        candidate_sha="d" * 40,
        source_ref=_source_ref(
            "operation_carrier",
            "github:pr:999",
            revision="d" * 40,
        ),
    )
    result = _assess(carrier_facts=(wrong,))
    assert result.verdict is AssessmentVerdict.REFUSED
    assert result.carrier_state is CarrierAssessmentState.CONFLICT
    assert _issue(result, AssessmentIssue.OPERATION_CARRIER_CONFLICT)


def test_missing_base_sha_is_unknown_not_behind_compatible_or_held() -> None:
    target = _target(
        base_sha=None,
        behind_by=1,
        merge_base_sha="d" * 40,
    )
    result = _assess(
        target=target,
        current_source_evidence=_source_evidence(target),
        current_base_required=False,
    )
    assert result.verdict is AssessmentVerdict.UNKNOWN
    assert result.merge_context_state is MergeContextState.UNKNOWN
    assert _issue(result, AssessmentIssue.BASE_OR_MERGE_CONTEXT_UNKNOWN)


def test_owner_native_semantic_and_writer_revisions_are_not_forced_to_git_head() -> None:
    packet = _packet()
    semantic_census = dataclasses.replace(
        packet.semantic_owners_source_ref,
        revision="agentos-commit-123",
    )
    semantic_facts = tuple(
        dataclasses.replace(
            fact,
            source_ref=dataclasses.replace(
                fact.source_ref,
                revision=f"agentos-fact-{index}",
            ),
        )
        for index, fact in enumerate(packet.semantic_owner_facts)
    )
    writer_census = dataclasses.replace(
        packet.writers_source_ref,
        revision="runtime-binding-generation-7",
    )
    writer = dataclasses.replace(
        packet.writer_facts[0],
        source_ref=dataclasses.replace(
            packet.writer_facts[0].source_ref,
            revision="runtime-binding-worker-42",
        ),
    )
    result = assess_github_release(
        dataclasses.replace(
            packet,
            semantic_owners_source_ref=semantic_census,
            semantic_owner_facts=semantic_facts,
            writers_source_ref=writer_census,
            writer_facts=(writer,),
        )
    )
    assert result.verdict is AssessmentVerdict.ELIGIBLE


def test_same_immutable_source_content_may_be_observed_more_than_once() -> None:
    packet = _packet()
    repeated = dataclasses.replace(
        packet.target.source_ref,
        observed_at=NOW - 1,
    )
    result = assess_github_release(
        dataclasses.replace(packet, source_refs=packet.source_refs + (repeated,))
    )
    assert result.verdict is AssessmentVerdict.ELIGIBLE
    assert not _issue(result, AssessmentIssue.SOURCE_CONFLICT)


def test_module_uses_no_isinstance_admission_for_privileged_values() -> None:
    module_path = Path(__file__).parents[1] / "control_plane" / "github_release_assessment.py"
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "isinstance"
    ]
    assert calls == []


def test_protected_output_aliases_are_explicit_and_digest_bound() -> None:
    result = _assess()
    rendered = result.to_dict()
    assert result.semantic_collision_state is result.semantic_owner_state
    assert result.source_law_state is result.source_state
    assert result.production_proof_state is result.production_state
    assert rendered["semantic_collision_state"] == rendered["semantic_owner_state"]
    assert rendered["source_law_state"] == rendered["source_state"]
    assert rendered["production_proof_state"] == rendered["production_state"]
    without_digest = dict(rendered)
    canonical_digest = without_digest.pop("canonical_digest")
    import hashlib
    canonical = json.dumps(
        without_digest,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    assert hashlib.sha256(canonical).hexdigest() == canonical_digest



def test_source_resource_id_is_bound_to_each_load_bearing_fact() -> None:
    wrong_target = dataclasses.replace(
        _target(),
        source_ref=_source_ref("pull_request", "999"),
    )
    target_result = _assess(target=wrong_target)
    assert target_result.verdict is AssessmentVerdict.REFUSED
    assert _issue(target_result, AssessmentIssue.SOURCE_SUBJECT_MISMATCH)

    wrong_check = dataclasses.replace(
        _check_attempt(),
        source_ref=_source_ref("check_attempt", "different", revision=CANDIDATE_SHA),
    )
    check_result = _assess(check_attempts=(wrong_check,))
    assert check_result.verdict is AssessmentVerdict.REFUSED
    assert check_result.check_state is CheckAssessmentState.UNKNOWN
    assert _issue(check_result, AssessmentIssue.SOURCE_SUBJECT_MISMATCH)

    wrong_writer = dataclasses.replace(
        _writer(),
        source_ref=_source_ref(
            "current_writer",
            "different-writer",
            owner=SourceOwner.RUNTIME_BINDING,
        ),
    )
    writer_result = _assess(writer_facts=(wrong_writer,))
    assert writer_result.verdict is AssessmentVerdict.REFUSED
    assert writer_result.writer_state is WriterAssessmentState.UNKNOWN
    assert _issue(writer_result, AssessmentIssue.SOURCE_SUBJECT_MISMATCH)


def test_unrelated_fact_source_failure_does_not_corrupt_current_source_law_axis() -> None:
    wrong_writer = dataclasses.replace(
        _writer(),
        source_ref=_source_ref(
            "current_writer",
            "different-writer",
            owner=SourceOwner.RUNTIME_BINDING,
        ),
    )
    result = _assess(writer_facts=(wrong_writer,))
    assert result.verdict is AssessmentVerdict.REFUSED
    assert result.source_state is SourceAssessmentState.CURRENT
    assert result.writer_state is WriterAssessmentState.UNKNOWN
    assert _issue(result, AssessmentIssue.SOURCE_SUBJECT_MISMATCH)


def test_unrelated_incomplete_fact_source_does_not_corrupt_current_source_law_axis() -> None:
    packet = _packet()
    incomplete_writer = dataclasses.replace(
        packet.writer_facts[0],
        source_ref=dataclasses.replace(
            packet.writer_facts[0].source_ref,
            coverage=SourceReferenceCoverage.PARTIAL,
        ),
    )
    result = assess_github_release(
        dataclasses.replace(packet, writer_facts=(incomplete_writer,))
    )
    assert result.verdict is AssessmentVerdict.UNKNOWN
    assert result.source_state is SourceAssessmentState.CURRENT
    assert result.writer_state is WriterAssessmentState.UNKNOWN
    assert _issue(result, AssessmentIssue.SOURCE_INCOMPLETE)
