from __future__ import annotations

import ast
from dataclasses import replace
from pathlib import Path

import pytest

from control_plane.github_release_assessment import (
    INPUT_SCHEMA,
    AssessmentInput,
    AssessmentInputError,
    AssessmentIssue,
    AssessmentVerdict,
    CapabilityState,
    CarrierFact,
    CheckConclusion,
    CheckFact,
    CheckStatus,
    EffectState,
    MergeMethod,
    PathCollisionFact,
    PrivilegeClass,
    ProductionProofState,
    ReviewFact,
    ReviewState,
    SemanticOwnerFact,
    SemanticOwnerExpectation,
    SourceCoverage,
    SourceLawState,
    WriterFact,
    assess_github_release,
)


PROTECTED = "a" * 40
CANDIDATE = "b" * 40


def _input(**overrides: object) -> AssessmentInput:
    values: dict[str, object] = {
        "schema": INPUT_SCHEMA,
        "operation_key": "mastermind-scf-gh1-test-op",
        "repository": "mastermindx-market-intelligence/Mastermind",
        "protected_ref": "refs/heads/master",
        "protected_sha": PROTECTED,
        "expected_protected_sha": PROTECTED,
        "candidate_branch": "sol/scf-gh1-test",
        "candidate_sha": CANDIDATE,
        "base_ref": "refs/heads/master",
        "base_sha": PROTECTED,
        "merge_base_sha": PROTECTED,
        "ahead_by": 1,
        "behind_by": 0,
        "expected_head_sha": CANDIDATE,
        "expected_paths": ("docs/scf-gh1.md",),
        "actual_paths": ("docs/scf-gh1.md",),
        "expected_semantic_owners": (
            SemanticOwnerExpectation(path_prefix="docs", owner_id="scf"),
        ),
        "current_semantic_owners": (
            SemanticOwnerFact(
                path_prefix="docs",
                owner_id="scf",
                operation_key="mastermind-scf-gh1-test-op",
                active=True,
                source_ref="github:semantic-owner:scf",
            ),
        ),
        "semantic_owners_complete": True,
        "carriers": (
            CarrierFact(
                carrier_ref="github:pr:1",
                operation_key="mastermind-scf-gh1-test-op",
                branch="sol/scf-gh1-test",
                candidate_sha=CANDIDATE,
                active=True,
                source_ref="github:pr:1",
            ),
        ),
        "carriers_complete": True,
        "writers": (
            WriterFact(
                writer_id="sol",
                operation_key="mastermind-scf-gh1-test-op",
                paths=("docs/scf-gh1.md",),
                active=True,
                source_ref="github:writer:sol",
            ),
        ),
        "writers_complete": True,
        "path_collisions": (),
        "required_checks": ("test",),
        "checks": (
            CheckFact(
                name="test",
                head_sha=CANDIDATE,
                attempt=1,
                required=True,
                status=CheckStatus.COMPLETED,
                conclusion=CheckConclusion.SUCCESS,
                superseded=False,
                source_ref="github:check:test:1",
            ),
        ),
        "checks_complete": True,
        "required_approvals": 0,
        "reviews": (),
        "unresolved_required_threads": 0,
        "reviews_complete": True,
        "source_coverage": SourceCoverage.COMPLETE,
        "source_law_state": SourceLawState.COMPATIBLE,
        "current_base_required": True,
        "production_proof_required": False,
        "production_proof_state": ProductionProofState.NOT_REQUIRED,
        "claimed_capability_state": CapabilityState.SPEC_ONLY,
        "requested_merge_method": MergeMethod.SQUASH,
        "allowed_merge_methods": (MergeMethod.SQUASH,),
        "prior_effect_state": EffectState.NOT_APPLIED,
        "source_refs": ("github:pr:1", "mastermind:protected:master"),
    }
    values.update(overrides)
    return AssessmentInput(**values)


def _assess(**overrides: object):
    return assess_github_release(_input(**overrides))


def test_exact_current_base_records_release_is_eligible_but_stays_spec_only() -> None:
    result = _assess()
    assert result.verdict is AssessmentVerdict.ELIGIBLE
    assert result.expected_head_merge_eligible is True
    assert result.claimed_capability_state is CapabilityState.SPEC_ONLY
    assert result.issues == ()
    assert result.schema == "mastermind.github_release_assessment.v1"


def test_moved_candidate_head_refuses_expected_head_release() -> None:
    result = _assess(candidate_sha="c" * 40)
    assert result.verdict is AssessmentVerdict.REFUSED
    assert result.expected_head_merge_eligible is False
    assert AssessmentIssue.CANDIDATE_HEAD_MOVED in result.issues


def test_compatible_protected_movement_holds_when_current_base_is_required() -> None:
    result = _assess(
        protected_sha="c" * 40,
        base_sha=PROTECTED,
        merge_base_sha=PROTECTED,
        behind_by=1,
        source_law_state=SourceLawState.COMPATIBLE,
    )
    assert result.verdict is AssessmentVerdict.HELD
    assert AssessmentIssue.PROTECTED_REF_MOVED in result.issues
    assert AssessmentIssue.CURRENT_BASE_REQUIRED in result.issues


def test_incompatible_material_source_movement_refuses() -> None:
    result = _assess(
        protected_sha="c" * 40,
        behind_by=1,
        source_law_state=SourceLawState.INCOMPATIBLE,
    )
    assert result.verdict is AssessmentVerdict.REFUSED
    assert AssessmentIssue.PROTECTED_REF_MOVED in result.issues
    assert AssessmentIssue.SOURCE_LAW_INCOMPATIBLE in result.issues


def test_unknown_merge_context_is_unknown() -> None:
    result = _assess(base_sha=None, merge_base_sha=None, ahead_by=None, behind_by=None)
    assert result.verdict is AssessmentVerdict.UNKNOWN
    assert AssessmentIssue.BASE_OR_MERGE_CONTEXT_UNKNOWN in result.issues


def test_expected_and_actual_path_mismatch_refuses() -> None:
    result = _assess(actual_paths=("docs/other.md",))
    assert result.verdict is AssessmentVerdict.REFUSED
    assert AssessmentIssue.EXPECTED_PATH_MISMATCH in result.issues


def test_path_collision_and_semantic_owner_collision_are_distinct_refusals() -> None:
    path_result = _assess(
        path_collisions=(
            PathCollisionFact(
                path="docs/scf-gh1.md",
                other_operation_key="other-op",
                source_ref="github:collision:1",
            ),
        )
    )
    assert AssessmentIssue.PATH_COLLISION in path_result.issues

    semantic_result = _assess(
        current_semantic_owners=(
            SemanticOwnerFact(
                path_prefix="docs",
                owner_id="other-owner",
                operation_key="other-op",
                active=True,
                source_ref="github:semantic-owner:other",
            ),
        )
    )
    assert semantic_result.verdict is AssessmentVerdict.REFUSED
    assert AssessmentIssue.SEMANTIC_OWNER_COLLISION in semantic_result.issues
    assert AssessmentIssue.PATH_COLLISION not in semantic_result.issues


def test_multiple_active_operation_carriers_refuse_without_electing_newest() -> None:
    other = CarrierFact(
        carrier_ref="github:pr:2",
        operation_key="mastermind-scf-gh1-test-op",
        branch="sol/duplicate",
        candidate_sha="d" * 40,
        active=True,
        source_ref="github:pr:2",
    )
    result = _assess(carriers=_input().carriers + (other,))
    assert result.verdict is AssessmentVerdict.REFUSED
    assert AssessmentIssue.OPERATION_CARRIER_CONFLICT in result.issues


def test_active_writer_on_overlapping_path_refuses() -> None:
    result = _assess(
        writers=(
            WriterFact(
                writer_id="other",
                operation_key="other-op",
                paths=("docs",),
                active=True,
                source_ref="github:writer:other",
            ),
        )
    )
    assert result.verdict is AssessmentVerdict.REFUSED
    assert AssessmentIssue.CARRIER_WRITER_CONFLICT in result.issues


def test_pending_required_check_holds() -> None:
    check = replace(
        _input().checks[0],
        status=CheckStatus.IN_PROGRESS,
        conclusion=None,
    )
    result = _assess(checks=(check,))
    assert result.verdict is AssessmentVerdict.HELD
    assert AssessmentIssue.CHECK_PENDING in result.issues


def test_failed_and_cancelled_required_checks_refuse() -> None:
    failed = replace(_input().checks[0], conclusion=CheckConclusion.FAILURE)
    cancelled = replace(_input().checks[0], conclusion=CheckConclusion.CANCELLED)
    failed_result = _assess(checks=(failed,))
    cancelled_result = _assess(checks=(cancelled,))
    assert failed_result.verdict is AssessmentVerdict.REFUSED
    assert AssessmentIssue.CHECK_FAILED in failed_result.issues
    assert cancelled_result.verdict is AssessmentVerdict.REFUSED
    assert AssessmentIssue.CHECK_CANCELLED in cancelled_result.issues


def test_superseded_or_old_head_green_check_never_counts_as_green() -> None:
    old = replace(
        _input().checks[0],
        head_sha="c" * 40,
        superseded=True,
    )
    result = _assess(checks=(old,))
    assert result.verdict is AssessmentVerdict.HELD
    assert AssessmentIssue.CHECK_SUPERSEDED in result.issues
    assert AssessmentIssue.CHECK_PENDING in result.issues


def test_partial_check_coverage_is_unknown() -> None:
    result = _assess(checks=(), checks_complete=False)
    assert result.verdict is AssessmentVerdict.UNKNOWN
    assert AssessmentIssue.CHECK_COVERAGE_PARTIAL in result.issues


def test_changes_requested_refuses_and_unresolved_thread_holds() -> None:
    review = ReviewFact(
        reviewer="auditor",
        head_sha=CANDIDATE,
        state=ReviewState.CHANGES_REQUESTED,
        required=True,
        source_ref="github:review:auditor",
    )
    blocked = _assess(required_approvals=1, reviews=(review,))
    held = _assess(unresolved_required_threads=1)
    assert blocked.verdict is AssessmentVerdict.REFUSED
    assert AssessmentIssue.CHANGES_REQUESTED in blocked.issues
    assert held.verdict is AssessmentVerdict.HELD
    assert AssessmentIssue.UNRESOLVED_REVIEW_THREAD in held.issues


def test_review_coverage_partial_is_unknown_when_review_is_required() -> None:
    result = _assess(required_approvals=1, reviews_complete=False)
    assert result.verdict is AssessmentVerdict.UNKNOWN
    assert AssessmentIssue.REVIEW_COVERAGE_PARTIAL in result.issues


@pytest.mark.parametrize(
    ("coverage", "issue"),
    (
        (SourceCoverage.INCOMPLETE, AssessmentIssue.SOURCE_INCOMPLETE),
        (SourceCoverage.STALE, AssessmentIssue.SOURCE_STALE),
        (SourceCoverage.CONFLICT, AssessmentIssue.SOURCE_CONFLICT),
    ),
)
def test_incomplete_stale_or_conflicting_source_is_unknown(
    coverage: SourceCoverage,
    issue: AssessmentIssue,
) -> None:
    result = _assess(source_coverage=coverage)
    assert result.verdict is AssessmentVerdict.UNKNOWN
    assert issue in result.issues


def test_required_production_proof_missing_holds_and_unknown_is_unknown() -> None:
    missing = _assess(
        production_proof_required=True,
        production_proof_state=ProductionProofState.MISSING,
        claimed_capability_state=CapabilityState.BUILT_NOT_PROVEN,
    )
    unknown = _assess(
        production_proof_required=True,
        production_proof_state=ProductionProofState.UNKNOWN,
        claimed_capability_state=CapabilityState.BUILT_NOT_PROVEN,
    )
    assert missing.verdict is AssessmentVerdict.HELD
    assert AssessmentIssue.PRODUCTION_PROOF_MISSING in missing.issues
    assert unknown.verdict is AssessmentVerdict.UNKNOWN
    assert AssessmentIssue.PRODUCTION_PROOF_UNKNOWN in unknown.issues


def test_green_ci_without_real_proof_refuses_proven_live_claim() -> None:
    result = _assess(
        production_proof_required=True,
        production_proof_state=ProductionProofState.MISSING,
        claimed_capability_state=CapabilityState.PROVEN_LIVE,
    )
    assert result.verdict is AssessmentVerdict.REFUSED
    assert AssessmentIssue.COMPLETION_CLAIM_OVERSTATED in result.issues
    assert result.expected_head_merge_eligible is False


def test_precise_present_proof_can_validate_exact_proven_live_claim() -> None:
    result = _assess(
        production_proof_required=True,
        production_proof_state=ProductionProofState.PRESENT,
        claimed_capability_state=CapabilityState.PROVEN_LIVE,
    )
    assert result.verdict is AssessmentVerdict.ELIGIBLE
    assert result.completion_claim_state.value == "VALID"


def test_forbidden_merge_method_and_prior_unknown_effect_refuse() -> None:
    method = _assess(requested_merge_method=MergeMethod.REBASE)
    effect = _assess(prior_effect_state=EffectState.EFFECT_UNKNOWN)
    assert method.verdict is AssessmentVerdict.REFUSED
    assert AssessmentIssue.MERGE_METHOD_REFUSED in method.issues
    assert effect.verdict is AssessmentVerdict.REFUSED
    assert AssessmentIssue.PRIOR_EFFECT_UNKNOWN in effect.issues


def test_refusal_outweighs_unknown_but_all_issues_remain_visible() -> None:
    result = _assess(
        candidate_sha="c" * 40,
        source_coverage=SourceCoverage.INCOMPLETE,
    )
    assert result.verdict is AssessmentVerdict.REFUSED
    assert AssessmentIssue.CANDIDATE_HEAD_MOVED in result.issues
    assert AssessmentIssue.SOURCE_INCOMPLETE in result.issues


def test_permutation_stability_and_load_bearing_digest_sensitivity() -> None:
    base = _input()
    permuted = replace(
        base,
        source_refs=tuple(reversed(base.source_refs)),
        actual_paths=tuple(reversed(base.actual_paths)),
        checks=tuple(reversed(base.checks)),
        writers=tuple(reversed(base.writers)),
    )
    left = assess_github_release(base)
    right = assess_github_release(permuted)
    assert left.to_dict() == right.to_dict()
    changed = assess_github_release(replace(base, required_approvals=1))
    assert changed.input_digest != left.input_digest
    assert changed.canonical_digest != left.canonical_digest


def test_duplicate_conflicting_check_or_review_identity_fails_closed() -> None:
    check = _input().checks[0]
    with pytest.raises(AssessmentInputError, match="duplicate check identity"):
        _assess(checks=(check, replace(check, conclusion=CheckConclusion.FAILURE)))

    review = ReviewFact(
        reviewer="auditor",
        head_sha=CANDIDATE,
        state=ReviewState.APPROVED,
        required=True,
        source_ref="github:review:1",
    )
    with pytest.raises(AssessmentInputError, match="duplicate review identity"):
        _assess(reviews=(review, replace(review, state=ReviewState.CHANGES_REQUESTED)))


def test_open_mapping_unknown_fields_and_secret_or_private_paths_are_rejected() -> None:
    with pytest.raises(AssessmentInputError, match="AssessmentInput"):
        assess_github_release({"schema": INPUT_SCHEMA, "admin_override": True})  # type: ignore[arg-type]
    with pytest.raises(AssessmentInputError, match="secret-shaped"):
        _assess(source_refs=("github_pat_secret",))
    with pytest.raises(AssessmentInputError, match="relative repository path"):
        _assess(actual_paths=("/Users/chris/private.txt",))


def test_input_collections_have_closed_cardinality() -> None:
    too_many = tuple(f"check-{index}" for index in range(129))
    with pytest.raises(AssessmentInputError, match="at most"):
        _assess(required_checks=too_many)


def test_module_is_pure_and_imports_no_runtime_or_io_owner() -> None:
    path = Path("control_plane/github_release_assessment.py")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    forbidden = {
        "requests",
        "httpx",
        "subprocess",
        "pathlib",
        "os",
        "socket",
        "time",
        "random",
        "github",
        "integrations",
        "control_plane.executive_runtime",
    }
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    assert not any(
        name == blocked or name.startswith(blocked + ".")
        for name in imported
        for blocked in forbidden
    )
