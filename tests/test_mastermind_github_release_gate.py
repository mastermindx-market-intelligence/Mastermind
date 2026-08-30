from __future__ import annotations

import ast
import dataclasses
import json
from pathlib import Path

import pytest

from integrations.mastermind_github_evidence.release_gate import (
    BranchPolicyFact,
    CheckConclusion,
    CheckFact,
    CheckIdentity,
    CheckStatus,
    CompareFact,
    EvidenceFreshness,
    MergeMethod,
    Mergeability,
    PullRequestFact,
    PullRequestState,
    ReleaseAssessmentStatus,
    ReleasePolicy,
    ReleaseReason,
    ReleaseSnapshot,
    ReviewDecision,
    ReviewGateFact,
    SourceRef,
    assess_release_gate,
)


REPOSITORY = "mastermindx-market-intelligence/Mastermind"
PR_NUMBER = 301
BASE_BRANCH = "master"
BASE_SHA = "1" * 40
HEAD_SHA = "2" * 40
PATHS = (
    "integrations/mastermind_github_evidence/__init__.py",
    "integrations/mastermind_github_evidence/release_gate.py",
    "tests/test_mastermind_github_release_gate.py",
)
TEST = CheckIdentity(context="test", app_id=15368)
CODEQL = CheckIdentity(context="CodeQL", app_id=15368)
NOW = "2026-08-30T10:00:00Z"


def source(ref: str = "github:test") -> SourceRef:
    return SourceRef(
        ref=ref,
        observed_at=NOW,
        freshness=EvidenceFreshness.CURRENT,
    )


def policy(**overrides: object) -> ReleasePolicy:
    values: dict[str, object] = {
        "operation_key": "mastermind-sol-github-evidence-a1-20260830-sol-001",
        "repository": REPOSITORY,
        "pr_number": PR_NUMBER,
        "expected_base_branch": BASE_BRANCH,
        "expected_base_sha": BASE_SHA,
        "expected_head_branch": "sol/github-evidence-a1",
        "expected_head_sha": HEAD_SHA,
        "expected_changed_paths": PATHS,
        "merge_method": MergeMethod.SQUASH,
        "required_checks": (TEST, CODEQL),
        "review_required": True,
        "source": source("github:source-law"),
    }
    values.update(overrides)
    return ReleasePolicy(**values)


def pr(**overrides: object) -> PullRequestFact:
    values: dict[str, object] = {
        "repository": REPOSITORY,
        "number": PR_NUMBER,
        "state": PullRequestState.OPEN,
        "draft": False,
        "merged": False,
        "base_branch": BASE_BRANCH,
        "base_sha": BASE_SHA,
        "head_branch": "sol/github-evidence-a1",
        "head_sha": HEAD_SHA,
        "merged_commit_sha": None,
        "mergeability": Mergeability.MERGEABLE,
        "changed_paths": PATHS,
        "changed_files_complete": True,
        "source": source("github:pr"),
    }
    values.update(overrides)
    return PullRequestFact(**values)


def branch(**overrides: object) -> BranchPolicyFact:
    values: dict[str, object] = {
        "repository": REPOSITORY,
        "branch": BASE_BRANCH,
        "branch_head_sha": BASE_SHA,
        "protected": True,
        "required_checks": (TEST,),
        "allowed_merge_methods": (MergeMethod.SQUASH,),
        "source": source("github:branch"),
    }
    values.update(overrides)
    return BranchPolicyFact(**values)


def compare(**overrides: object) -> CompareFact:
    values: dict[str, object] = {
        "base_sha": BASE_SHA,
        "head_sha": HEAD_SHA,
        "merge_base_sha": BASE_SHA,
        "ahead_by": 3,
        "behind_by": 0,
        "changed_paths": PATHS,
        "comparison_complete": True,
        "source": source("github:compare"),
    }
    values.update(overrides)
    return CompareFact(**values)


def check(
    identity: CheckIdentity,
    *,
    status: CheckStatus = CheckStatus.COMPLETED,
    conclusion: CheckConclusion | None = CheckConclusion.SUCCESS,
    target_sha: str = HEAD_SHA,
    ref: str | None = None,
) -> CheckFact:
    return CheckFact(
        identity=identity,
        status=status,
        conclusion=conclusion,
        target_sha=target_sha,
        source=source(ref or f"github:check:{identity.context}"),
    )


def review(**overrides: object) -> ReviewGateFact:
    values: dict[str, object] = {
        "head_sha": HEAD_SHA,
        "decision": ReviewDecision.APPROVED,
        "unresolved_thread_count": 0,
        "review_set_complete": True,
        "source": source("github:reviews"),
    }
    values.update(overrides)
    return ReviewGateFact(**values)


def snapshot(**overrides: object) -> ReleaseSnapshot:
    values: dict[str, object] = {
        "pull_request": pr(),
        "branch_policy": branch(),
        "comparison": compare(),
        "checks": (check(TEST), check(CODEQL)),
        "checks_complete": True,
        "review_gate": review(),
        "source": source("github:snapshot"),
    }
    values.update(overrides)
    return ReleaseSnapshot(**values)


def assert_no_merge_request(result: object) -> None:
    assert getattr(result, "guarded_merge_request") is None
    assert getattr(result, "organizational_authority_granted") is False


def test_ready_snapshot_emits_only_expected_head_guarded_release_candidate() -> None:
    result = assess_release_gate(snapshot(), policy())

    assert result.status is ReleaseAssessmentStatus.READY_FOR_EXPECTED_HEAD_RELEASE
    assert result.reasons == ()
    assert result.organizational_authority_granted is False
    assert result.production_acceptance_claimed is False
    assert result.guarded_merge_request is not None
    assert dataclasses.asdict(result.guarded_merge_request) == {
        "repository": REPOSITORY,
        "pr_number": PR_NUMBER,
        "expected_head_branch": "sol/github-evidence-a1",
        "expected_head_sha": HEAD_SHA,
        "merge_method": MergeMethod.SQUASH,
    }
    wire = result.to_dict()
    assert wire["schema"] == "mastermind.github_release_evidence.v1"
    assert wire["organizational_authority_granted"] is False
    assert wire["production_acceptance_claimed"] is False
    assert len(wire["evidence_digest"]) == 64


@pytest.mark.parametrize(
    ("conclusion", "accepted"),
    [
        (CheckConclusion.SUCCESS, True),
        (CheckConclusion.NEUTRAL, True),
        (CheckConclusion.SKIPPED, True),
        (CheckConclusion.FAILURE, False),
        (CheckConclusion.CANCELLED, False),
        (CheckConclusion.TIMED_OUT, False),
        (CheckConclusion.ACTION_REQUIRED, False),
        (CheckConclusion.STALE, False),
        (CheckConclusion.STARTUP_FAILURE, False),
    ],
)
def test_required_check_conclusion_semantics(
    conclusion: CheckConclusion, accepted: bool
) -> None:
    result = assess_release_gate(
        snapshot(checks=(check(TEST, conclusion=conclusion), check(CODEQL))),
        policy(),
    )

    if accepted:
        assert result.status is ReleaseAssessmentStatus.READY_FOR_EXPECTED_HEAD_RELEASE
    else:
        assert result.status is ReleaseAssessmentStatus.BLOCKED
        assert ReleaseReason.REQUIRED_CHECK_FAILED in result.reasons
        assert_no_merge_request(result)


@pytest.mark.parametrize(
    "status",
    [
        CheckStatus.QUEUED,
        CheckStatus.IN_PROGRESS,
        CheckStatus.PENDING,
        CheckStatus.REQUESTED,
        CheckStatus.WAITING,
    ],
)
def test_nonterminal_required_check_blocks_release(status: CheckStatus) -> None:
    result = assess_release_gate(
        snapshot(
            checks=(
                check(TEST, status=status, conclusion=None),
                check(CODEQL),
            )
        ),
        policy(),
    )

    assert result.status is ReleaseAssessmentStatus.BLOCKED
    assert ReleaseReason.REQUIRED_CHECK_PENDING in result.reasons
    assert_no_merge_request(result)


def test_missing_required_check_blocks_release() -> None:
    result = assess_release_gate(snapshot(checks=(check(TEST),)), policy())

    assert result.status is ReleaseAssessmentStatus.BLOCKED
    assert ReleaseReason.REQUIRED_CHECK_MISSING in result.reasons
    assert_no_merge_request(result)


def test_duplicate_required_check_identity_requires_reconciliation() -> None:
    result = assess_release_gate(
        snapshot(
            checks=(
                check(TEST),
                check(TEST, ref="github:check:test:duplicate"),
                check(CODEQL),
            )
        ),
        policy(),
    )

    assert result.status is ReleaseAssessmentStatus.RECONCILIATION_REQUIRED
    assert ReleaseReason.CHECK_IDENTITY_CONFLICT in result.reasons
    assert_no_merge_request(result)


def test_check_from_old_head_requires_reconciliation() -> None:
    result = assess_release_gate(
        snapshot(checks=(check(TEST, target_sha="3" * 40), check(CODEQL))),
        policy(),
    )

    assert result.status is ReleaseAssessmentStatus.RECONCILIATION_REQUIRED
    assert ReleaseReason.CHECK_TARGET_MOVED in result.reasons
    assert_no_merge_request(result)


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("head_sha", "3" * 40, ReleaseReason.HEAD_MOVED),
        ("head_branch", "sol/replacement", ReleaseReason.HEAD_BRANCH_MISMATCH),
        ("base_sha", "4" * 40, ReleaseReason.BASE_MOVED),
        ("base_branch", "release", ReleaseReason.BASE_BRANCH_MISMATCH),
        ("repository", "other/repo", ReleaseReason.CARRIER_IDENTITY_MISMATCH),
        ("number", 999, ReleaseReason.CARRIER_IDENTITY_MISMATCH),
    ],
)
def test_exact_carrier_movement_never_produces_merge_request(
    field: str, value: object, reason: ReleaseReason
) -> None:
    result = assess_release_gate(snapshot(pull_request=pr(**{field: value})), policy())

    assert result.status is ReleaseAssessmentStatus.RECONCILIATION_REQUIRED
    assert reason in result.reasons
    assert_no_merge_request(result)


def test_changed_path_drift_blocks_release() -> None:
    drifted_paths = PATHS + ("control_plane/executive.py",)
    result = assess_release_gate(
        snapshot(
            pull_request=pr(changed_paths=drifted_paths),
            comparison=compare(changed_paths=drifted_paths),
        ),
        policy(),
    )

    assert result.status is ReleaseAssessmentStatus.BLOCKED
    assert ReleaseReason.CHANGED_PATHS_MISMATCH in result.reasons
    assert_no_merge_request(result)


def test_incomplete_file_or_check_or_review_pagination_requires_reconciliation(
) -> None:
    cases = (
        snapshot(pull_request=pr(changed_files_complete=False)),
        snapshot(checks_complete=False),
        snapshot(review_gate=review(review_set_complete=False)),
    )

    for case in cases:
        result = assess_release_gate(case, policy())
        assert result.status is ReleaseAssessmentStatus.RECONCILIATION_REQUIRED
        assert ReleaseReason.EVIDENCE_INCOMPLETE in result.reasons
        assert_no_merge_request(result)


def test_stale_or_unknown_source_requires_reconciliation() -> None:
    for freshness in (EvidenceFreshness.STALE, EvidenceFreshness.UNKNOWN):
        stale_source = SourceRef(
            ref=f"github:snapshot:{freshness.value}",
            observed_at=NOW if freshness is EvidenceFreshness.STALE else None,
            freshness=freshness,
        )
        result = assess_release_gate(snapshot(source=stale_source), policy())
        assert result.status is ReleaseAssessmentStatus.RECONCILIATION_REQUIRED
        assert ReleaseReason.EVIDENCE_NOT_CURRENT in result.reasons
        assert_no_merge_request(result)


def test_draft_closed_or_conflicting_pr_blocks_release() -> None:
    cases = (
        (pr(draft=True), ReleaseReason.PULL_REQUEST_DRAFT),
        (pr(state=PullRequestState.CLOSED), ReleaseReason.PULL_REQUEST_CLOSED),
        (pr(mergeability=Mergeability.CONFLICTING), ReleaseReason.MERGE_CONFLICT),
    )

    for pull_request, reason in cases:
        result = assess_release_gate(snapshot(pull_request=pull_request), policy())
        assert result.status is ReleaseAssessmentStatus.BLOCKED
        assert reason in result.reasons
        assert_no_merge_request(result)


def test_unknown_mergeability_requires_reconciliation() -> None:
    result = assess_release_gate(
        snapshot(pull_request=pr(mergeability=Mergeability.UNKNOWN)), policy()
    )

    assert result.status is ReleaseAssessmentStatus.RECONCILIATION_REQUIRED
    assert ReleaseReason.MERGEABILITY_UNKNOWN in result.reasons
    assert_no_merge_request(result)


def test_exact_already_merged_carrier_is_not_released_twice() -> None:
    result = assess_release_gate(
        snapshot(
            pull_request=pr(
                state=PullRequestState.CLOSED,
                merged=True,
                mergeability=Mergeability.UNKNOWN,
                merged_commit_sha="5" * 40,
            )
        ),
        policy(),
    )

    assert result.status is ReleaseAssessmentStatus.ALREADY_MERGED
    assert result.reasons == (ReleaseReason.ALREADY_MERGED,)
    assert_no_merge_request(result)


def test_unprotected_branch_or_disabled_merge_method_blocks_release() -> None:
    unprotected = assess_release_gate(
        snapshot(branch_policy=branch(protected=False)), policy()
    )
    unsupported = assess_release_gate(
        snapshot(branch_policy=branch(allowed_merge_methods=(MergeMethod.REBASE,))),
        policy(),
    )

    assert unprotected.status is ReleaseAssessmentStatus.BLOCKED
    assert ReleaseReason.BASE_BRANCH_UNPROTECTED in unprotected.reasons
    assert unsupported.status is ReleaseAssessmentStatus.BLOCKED
    assert ReleaseReason.MERGE_METHOD_UNAVAILABLE in unsupported.reasons
    assert_no_merge_request(unprotected)
    assert_no_merge_request(unsupported)


def test_policy_may_add_checks_but_may_not_omit_protected_branch_check() -> None:
    omitted = assess_release_gate(
        snapshot(branch_policy=branch(required_checks=(TEST, CODEQL))),
        policy(required_checks=(TEST,)),
    )

    assert omitted.status is ReleaseAssessmentStatus.RECONCILIATION_REQUIRED
    assert ReleaseReason.POLICY_OMITS_BRANCH_CHECK in omitted.reasons
    assert_no_merge_request(omitted)


def test_review_is_exact_head_complete_approved_and_thread_clean() -> None:
    cases = (
        (
            review(head_sha="3" * 40),
            ReleaseAssessmentStatus.RECONCILIATION_REQUIRED,
            ReleaseReason.REVIEW_TARGET_MOVED,
        ),
        (
            review(decision=ReviewDecision.CHANGES_REQUESTED),
            ReleaseAssessmentStatus.BLOCKED,
            ReleaseReason.REVIEW_CHANGES_REQUESTED,
        ),
        (
            review(decision=ReviewDecision.PENDING),
            ReleaseAssessmentStatus.BLOCKED,
            ReleaseReason.REVIEW_PENDING,
        ),
        (
            review(decision=ReviewDecision.UNKNOWN),
            ReleaseAssessmentStatus.RECONCILIATION_REQUIRED,
            ReleaseReason.REVIEW_UNKNOWN,
        ),
        (
            review(unresolved_thread_count=2),
            ReleaseAssessmentStatus.BLOCKED,
            ReleaseReason.REVIEW_THREADS_UNRESOLVED,
        ),
    )

    for review_gate, status, reason in cases:
        result = assess_release_gate(snapshot(review_gate=review_gate), policy())
        assert result.status is status
        assert reason in result.reasons
        assert_no_merge_request(result)


def test_review_not_required_accepts_explicit_not_required_only() -> None:
    result = assess_release_gate(
        snapshot(review_gate=review(decision=ReviewDecision.NOT_REQUIRED)),
        policy(review_required=False),
    )

    assert result.status is ReleaseAssessmentStatus.READY_FOR_EXPECTED_HEAD_RELEASE


def test_policy_requiring_review_rejects_not_required_projection() -> None:
    result = assess_release_gate(
        snapshot(review_gate=review(decision=ReviewDecision.NOT_REQUIRED)),
        policy(review_required=True),
    )

    assert result.status is ReleaseAssessmentStatus.BLOCKED
    assert ReleaseReason.REVIEW_PENDING in result.reasons


def test_permutation_stability_for_checks_and_required_check_policy() -> None:
    first = assess_release_gate(
        snapshot(checks=(check(TEST), check(CODEQL))),
        policy(required_checks=(TEST, CODEQL)),
    )
    second = assess_release_gate(
        snapshot(checks=(check(CODEQL), check(TEST))),
        policy(required_checks=(CODEQL, TEST)),
    )

    assert first.to_dict() == second.to_dict()


def test_result_wire_is_closed_and_json_serializable() -> None:
    wire = assess_release_gate(snapshot(), policy()).to_dict()

    assert set(wire) == {
        "schema",
        "status",
        "reasons",
        "operation_key",
        "repository",
        "pr_number",
        "expected_base_sha",
        "expected_head_sha",
        "merged_commit_sha",
        "evidence_refs",
        "evidence_digest",
        "guarded_merge_request",
        "organizational_authority_granted",
        "production_acceptance_claimed",
    }
    json.dumps(wire, sort_keys=True, allow_nan=False)


def test_static_read_only_fence_excludes_network_process_filesystem_and_mutations(
) -> None:
    module_path = (
        Path(__file__).parents[1]
        / "integrations"
        / "mastermind_github_evidence"
        / "release_gate.py"
    )
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    imports = {
        node.names[0].name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
    } | {
        (node.module or "").split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }
    forbidden_imports = {
        "requests",
        "httpx",
        "urllib",
        "socket",
        "subprocess",
        "sqlite3",
        "pathlib",
        "os",
        "shutil",
        "mcp",
    }
    assert imports.isdisjoint(forbidden_imports)

    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    attributes = {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    }
    forbidden_actions = {
        "merge",
        "rerun",
        "dispatch",
        "write",
        "delete",
        "update_ref",
        "create_branch",
        "submit_intent",
        "open",
    }
    assert names.isdisjoint(forbidden_actions)
    assert attributes.isdisjoint(forbidden_actions)


def test_compare_requires_exact_current_base_head_merge_base_and_zero_behind() -> None:
    cases = (
        (
            compare(base_sha="3" * 40),
            ReleaseAssessmentStatus.RECONCILIATION_REQUIRED,
            ReleaseReason.BASE_MOVED,
        ),
        (
            compare(head_sha="4" * 40),
            ReleaseAssessmentStatus.RECONCILIATION_REQUIRED,
            ReleaseReason.HEAD_MOVED,
        ),
        (
            compare(merge_base_sha="6" * 40),
            ReleaseAssessmentStatus.RECONCILIATION_REQUIRED,
            ReleaseReason.MERGE_BASE_MISMATCH,
        ),
        (
            compare(behind_by=1),
            ReleaseAssessmentStatus.BLOCKED,
            ReleaseReason.HEAD_BEHIND_BASE,
        ),
        (
            compare(ahead_by=0),
            ReleaseAssessmentStatus.BLOCKED,
            ReleaseReason.NO_RELEASE_DELTA,
        ),
    )

    for comparison, status, reason in cases:
        result = assess_release_gate(snapshot(comparison=comparison), policy())
        assert result.status is status
        assert reason in result.reasons
        assert_no_merge_request(result)


def test_pr_and_compare_changed_path_disagreement_requires_reconciliation() -> None:
    result = assess_release_gate(
        snapshot(
            comparison=compare(
                changed_paths=PATHS + ("unexpected/from-compare.py",)
            )
        ),
        policy(),
    )

    assert result.status is ReleaseAssessmentStatus.RECONCILIATION_REQUIRED
    assert ReleaseReason.CHANGED_PATH_EVIDENCE_CONFLICT in result.reasons
    assert_no_merge_request(result)


def test_already_merged_exact_carrier_wins_over_post_effect_base_movement() -> None:
    result = assess_release_gate(
        snapshot(
            pull_request=pr(
                state=PullRequestState.CLOSED,
                merged=True,
                merged_commit_sha="5" * 40,
                mergeability=Mergeability.UNKNOWN,
            ),
            branch_policy=branch(branch_head_sha="7" * 40),
            comparison=compare(
                base_sha="7" * 40,
                merge_base_sha="8" * 40,
                behind_by=2,
            ),
        ),
        policy(),
    )

    assert result.status is ReleaseAssessmentStatus.ALREADY_MERGED
    assert result.merged_commit_sha == "5" * 40
    assert result.production_acceptance_claimed is False
    assert_no_merge_request(result)


def test_merged_carrier_with_changed_path_mismatch_requires_reconciliation() -> None:
    result = assess_release_gate(
        snapshot(
            pull_request=pr(
                state=PullRequestState.CLOSED,
                merged=True,
                merged_commit_sha="5" * 40,
                mergeability=Mergeability.UNKNOWN,
                changed_paths=PATHS + ("unexpected.py",),
            )
        ),
        policy(),
    )

    assert result.status is ReleaseAssessmentStatus.RECONCILIATION_REQUIRED
    assert ReleaseReason.CHANGED_PATHS_MISMATCH in result.reasons
    assert_no_merge_request(result)


def test_release_policy_requires_nonempty_exact_changed_path_set() -> None:
    with pytest.raises(ValueError):
        policy(expected_changed_paths=())
