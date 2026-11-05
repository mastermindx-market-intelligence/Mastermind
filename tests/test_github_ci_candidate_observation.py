from __future__ import annotations

import ast
import dataclasses
import hashlib
from pathlib import Path

import pytest

from control_plane.github_release_assessment import (
    CI_OBSERVATION_INPUT_SCHEMA,
    CI_OBSERVATION_OUTPUT_SCHEMA,
    AssessmentInputError,
    AssessmentIssue,
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


REPOSITORY = "mastermindx-market-intelligence/Mastermind"
REPOSITORY_ID = 1_317_762_013
PR_NUMBER = 1240
CANDIDATE_REF = "sol/web-claude-capability-hardening-20261004-c4-001"
HEAD = "a" * 40
OTHER_HEAD = "b" * 40
POLICY_REVISION = "ruleset-branch-protection-v1"
NOW = 1_800_000_000
TEST = CheckIdentity("test", 15368)
CODEQL = CheckIdentity("CodeQL", 15368)


def source_ref(
    resource_kind: str,
    resource_id: str,
    revision: str,
    *,
    owner: SourceOwner = SourceOwner.GITHUB,
    repository: str | None = REPOSITORY,
    observed_at: int = NOW,
    valid_at: int | None = None,
    coverage: SourceReferenceCoverage = SourceReferenceCoverage.COMPLETE,
    truncated: bool = False,
    continuation: str | None = None,
    seed: str | None = None,
) -> SourceReference:
    material = seed or f"{resource_kind}:{resource_id}:{revision}:{observed_at}"
    return SourceReference(
        source_kind="owner_native",
        owner=owner,
        repository=repository,
        resource_kind=resource_kind,
        resource_id=resource_id,
        revision=revision,
        observed_at=observed_at,
        valid_at=valid_at,
        content_sha256=hashlib.sha256(material.encode()).hexdigest(),
        coverage=coverage,
        truncated=truncated,
        continuation=continuation,
    )


def check_run(
    identity: CheckIdentity = TEST,
    *,
    check_run_id: int = 1001,
    workflow_run_id: int | None = 2001,
    attempt: int = 1,
    sequence: int = 1,
    status: CheckStatus = CheckStatus.COMPLETED,
    conclusion: CheckConclusion | None = CheckConclusion.SUCCESS,
    applicable: bool = True,
    superseded: bool = False,
    head: str = HEAD,
) -> CandidateCheckRun:
    return CandidateCheckRun(
        identity=identity,
        head_sha=head,
        check_run_id=check_run_id,
        workflow_run_id=workflow_run_id,
        attempt=attempt,
        sequence=sequence,
        status=status,
        conclusion=conclusion,
        applicable=applicable,
        superseded=superseded,
        source_ref=source_ref(
            "check_run",
            f"check-run:{check_run_id}",
            head,
            seed=f"run:{check_run_id}:{attempt}:{sequence}:{status.value}:{conclusion}",
        ),
    )


def packet(**changes) -> CandidateCIObservationInput:
    runs = (
        check_run(TEST, check_run_id=1001),
        check_run(CODEQL, check_run_id=1002, workflow_run_id=2002),
    )
    value = CandidateCIObservationInput(
        schema=CI_OBSERVATION_INPUT_SCHEMA,
        observed_at=NOW,
        repository=REPOSITORY,
        repository_id=REPOSITORY_ID,
        pull_request_number=PR_NUMBER,
        candidate_ref=CANDIDATE_REF,
        expected_head_sha=HEAD,
        observed_head_sha=HEAD,
        policy_revision=POLICY_REVISION,
        required_checks=(TEST, CODEQL),
        allowed_non_success_checks=(),
        check_runs=runs,
        checks_complete=True,
        policy_source_ref=source_ref(
            "required_checks_policy",
            POLICY_REVISION,
            POLICY_REVISION,
            seed="policy",
        ),
        checks_source_ref=source_ref(
            "commit_check_runs",
            HEAD,
            HEAD,
            seed="checks",
        ),
    )
    return dataclasses.replace(value, **changes) if changes else value


def test_green_exact_candidate_is_terminal_and_deterministic() -> None:
    result = assess_candidate_ci_observation(packet())

    assert result.schema == CI_OBSERVATION_OUTPUT_SCHEMA
    assert result.state is CandidateCIState.GREEN
    assert result.terminal is True
    assert result.issues == ()
    assert [row.identity.context for row in result.latest_checks] == ["CodeQL", "test"]
    assert len(result.input_digest) == 64
    assert len(result.canonical_digest) == 64
    assert result.to_dict()["canonical_digest"] == result.canonical_digest

    reordered = packet(
        required_checks=(CODEQL, TEST),
        check_runs=tuple(reversed(packet().check_runs)),
    )
    same = assess_candidate_ci_observation(reordered)
    assert same.input_digest == result.input_digest
    assert same.canonical_digest == result.canonical_digest


def test_latest_retry_generation_wins_without_old_failure_poisoning() -> None:
    failed = check_run(
        TEST,
        check_run_id=1000,
        attempt=1,
        sequence=1,
        conclusion=CheckConclusion.FAILURE,
    )
    passed = check_run(
        TEST,
        check_run_id=1001,
        attempt=2,
        sequence=1,
        conclusion=CheckConclusion.SUCCESS,
    )
    result = assess_candidate_ci_observation(
        packet(required_checks=(TEST,), check_runs=(failed, passed))
    )
    assert result.state is CandidateCIState.GREEN
    assert [row.check_run_id for row in result.latest_checks] == [1001]


@pytest.mark.parametrize("status", [CheckStatus.QUEUED, CheckStatus.IN_PROGRESS])
def test_current_nonterminal_check_is_pending(status: CheckStatus) -> None:
    result = assess_candidate_ci_observation(
        packet(
            required_checks=(TEST,),
            check_runs=(
                check_run(TEST, status=status, conclusion=None),
            ),
        )
    )
    assert result.state is CandidateCIState.PENDING
    assert result.terminal is False
    assert AssessmentIssue.CHECK_PENDING in result.issues


def test_complete_snapshot_missing_required_check_is_pending() -> None:
    result = assess_candidate_ci_observation(
        packet(required_checks=(TEST,), check_runs=())
    )
    assert result.state is CandidateCIState.PENDING
    assert AssessmentIssue.CHECK_MISSING in result.issues


def test_incomplete_snapshot_is_unknown_not_missing_or_green() -> None:
    result = assess_candidate_ci_observation(
        packet(
            required_checks=(TEST,),
            check_runs=(),
            checks_complete=False,
        )
    )
    assert result.state is CandidateCIState.UNKNOWN
    assert result.terminal is False
    assert AssessmentIssue.CHECK_COVERAGE_PARTIAL in result.issues
    assert AssessmentIssue.CHECK_MISSING not in result.issues


@pytest.mark.parametrize(
    ("conclusion", "issue"),
    [
        (CheckConclusion.FAILURE, AssessmentIssue.CHECK_FAILED),
        (CheckConclusion.TIMED_OUT, AssessmentIssue.CHECK_FAILED),
        (CheckConclusion.ACTION_REQUIRED, AssessmentIssue.CHECK_FAILED),
        (CheckConclusion.STALE, AssessmentIssue.CHECK_FAILED),
        (CheckConclusion.CANCELLED, AssessmentIssue.CHECK_CANCELLED),
    ],
)
def test_terminal_bad_conclusion_fails(
    conclusion: CheckConclusion,
    issue: AssessmentIssue,
) -> None:
    result = assess_candidate_ci_observation(
        packet(
            required_checks=(TEST,),
            check_runs=(check_run(TEST, conclusion=conclusion),),
        )
    )
    assert result.state is CandidateCIState.FAILED
    assert result.terminal is True
    assert issue in result.issues


@pytest.mark.parametrize("conclusion", [CheckConclusion.SKIPPED, CheckConclusion.NEUTRAL])
def test_allowed_non_success_requires_explicit_nonapplicable_check(
    conclusion: CheckConclusion,
) -> None:
    allowed = assess_candidate_ci_observation(
        packet(
            required_checks=(TEST,),
            allowed_non_success_checks=(TEST,),
            check_runs=(
                check_run(TEST, conclusion=conclusion, applicable=False),
            ),
        )
    )
    assert allowed.state is CandidateCIState.GREEN

    refused = assess_candidate_ci_observation(
        packet(
            required_checks=(TEST,),
            allowed_non_success_checks=(TEST,),
            check_runs=(
                check_run(TEST, conclusion=conclusion, applicable=True),
            ),
        )
    )
    assert refused.state is CandidateCIState.FAILED


def test_superseded_latest_generation_is_unknown() -> None:
    result = assess_candidate_ci_observation(
        packet(
            required_checks=(TEST,),
            check_runs=(check_run(TEST, superseded=True),),
        )
    )
    assert result.state is CandidateCIState.UNKNOWN
    assert AssessmentIssue.CHECK_SUPERSEDED in result.issues


def test_moved_pull_request_head_is_stale_before_check_semantics() -> None:
    checks = source_ref("commit_check_runs", OTHER_HEAD, OTHER_HEAD, seed="other-checks")
    stale_run = check_run(TEST, head=OTHER_HEAD)
    result = assess_candidate_ci_observation(
        packet(
            observed_head_sha=OTHER_HEAD,
            required_checks=(TEST,),
            check_runs=(stale_run,),
            checks_source_ref=checks,
        )
    )
    assert result.state is CandidateCIState.STALE
    assert result.terminal is True
    assert result.latest_checks == ()
    assert result.issues == (AssessmentIssue.CANDIDATE_HEAD_MOVED,)


@pytest.mark.parametrize(
    ("field", "replacement", "issue"),
    [
        (
            "checks_source_ref",
            source_ref(
                "commit_check_runs",
                HEAD,
                HEAD,
                owner=SourceOwner.EXECUTIVE_OS,
                seed="wrong-owner",
            ),
            AssessmentIssue.SOURCE_OWNER_MISMATCH,
        ),
        (
            "checks_source_ref",
            source_ref(
                "commit_check_runs",
                HEAD,
                HEAD,
                coverage=SourceReferenceCoverage.PARTIAL,
                seed="partial",
            ),
            AssessmentIssue.SOURCE_INCOMPLETE,
        ),
        (
            "policy_source_ref",
            source_ref(
                "required_checks_policy",
                POLICY_REVISION,
                "wrong-policy-revision",
                seed="wrong-revision",
            ),
            AssessmentIssue.SOURCE_REVISION_MISMATCH,
        ),
        (
            "checks_source_ref",
            source_ref(
                "commit_check_runs",
                HEAD,
                HEAD,
                observed_at=NOW - 100_000,
                seed="stale",
            ),
            AssessmentIssue.SOURCE_STALE,
        ),
    ],
)
def test_unreliable_owner_native_evidence_is_unknown(
    field: str,
    replacement: SourceReference,
    issue: AssessmentIssue,
) -> None:
    result = assess_candidate_ci_observation(packet(**{field: replacement}))
    assert result.state is CandidateCIState.UNKNOWN
    assert result.terminal is False
    assert issue in result.issues


@pytest.mark.parametrize(
    "mutator",
    [
        lambda p: dataclasses.replace(p, schema="future"),
        lambda p: dataclasses.replace(p, required_checks=()),
        lambda p: dataclasses.replace(p, required_checks=(TEST, TEST)),
        lambda p: dataclasses.replace(
            p,
            required_checks=(TEST,),
            allowed_non_success_checks=(CODEQL,),
        ),
        lambda p: dataclasses.replace(
            p,
            check_runs=(
                check_run(TEST, check_run_id=1001),
                check_run(CODEQL, check_run_id=1001),
            ),
        ),
        lambda p: dataclasses.replace(
            p,
            check_runs=(check_run(TEST, head=OTHER_HEAD),),
        ),
        lambda p: dataclasses.replace(
            p,
            check_runs=(
                check_run(
                    TEST,
                    status=CheckStatus.IN_PROGRESS,
                    conclusion=CheckConclusion.SUCCESS,
                ),
            ),
        ),
    ],
)
def test_malformed_observation_input_refuses(mutator) -> None:
    with pytest.raises(AssessmentInputError):
        assess_candidate_ci_observation(mutator(packet()))


def test_classifier_is_inert_and_source_module_has_no_github_client_or_persistence() -> None:
    result = assess_candidate_ci_observation(packet())
    assert result.state is CandidateCIState.GREEN
    assert result.to_dict()["terminal"] is True
    # This H5-A slice classifies supplied owner-native evidence only. It does not
    # claim an observer is registered, polling, or able to wake a Claude principal.
    assert "watch" not in result.to_dict()
    assert "registered" not in result.to_dict()

    root = Path(__file__).resolve().parents[1]
    module = root / "control_plane" / "github_release_assessment.py"
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
        {"requests", "httpx", "urllib", "socket", "sqlite3", "subprocess", "mcp"}
    )


def test_h5_classifier_tests_are_in_existing_ci_gate() -> None:
    from scripts.ci_pytest import resolve_gate

    root = Path(__file__).resolve().parents[1]
    gate = resolve_gate(root)
    assert "tests/test_github_ci_candidate_observation.py" in gate["included"]
