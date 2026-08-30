"""Pure release evidence for one exact GitHub carrier.

No I/O or mutation occurs here. A positive result is evidence for a separate
expected-head guarded release action, never organizational authority.
"""
from __future__ import annotations

import dataclasses as dc
import enum
import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from typing import Any

SCHEMA = "mastermind.github_release_evidence.v1"
_REPO = re.compile(r"^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$")
_SHA = re.compile(r"^[0-9a-f]{40}$")
_OP = re.compile(r"^[a-z0-9][a-z0-9._-]{2,191}$")
_CTRL = re.compile(r"[\x00-\x1f\x7f]")
_UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$")


class ReleaseEvidenceError(ValueError):
    """Malformed policy or evidence."""


class _E(str, enum.Enum):
    pass


class EvidenceFreshness(_E):
    CURRENT = "current"
    STALE = "stale"
    UNKNOWN = "unknown"


class MergeMethod(_E):
    MERGE = "merge"
    SQUASH = "squash"
    REBASE = "rebase"


class PullRequestState(_E):
    OPEN = "open"
    CLOSED = "closed"


class Mergeability(_E):
    MERGEABLE = "mergeable"
    CONFLICTING = "conflicting"
    UNKNOWN = "unknown"


class CheckStatus(_E):
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    PENDING = "pending"
    REQUESTED = "requested"
    WAITING = "waiting"
    COMPLETED = "completed"


class CheckConclusion(_E):
    SUCCESS = "success"
    NEUTRAL = "neutral"
    SKIPPED = "skipped"
    FAILURE = "failure"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"
    ACTION_REQUIRED = "action_required"
    STALE = "stale"
    STARTUP_FAILURE = "startup_failure"


class ReviewDecision(_E):
    APPROVED = "approved"
    CHANGES_REQUESTED = "changes_requested"
    PENDING = "pending"
    UNKNOWN = "unknown"
    NOT_REQUIRED = "not_required"


class ReleaseAssessmentStatus(_E):
    READY_FOR_EXPECTED_HEAD_RELEASE = "ready_for_expected_head_release"
    BLOCKED = "blocked"
    RECONCILIATION_REQUIRED = "reconciliation_required"
    ALREADY_MERGED = "already_merged"


class ReleaseReason(_E):
    ALREADY_MERGED = "already_merged"
    CARRIER_IDENTITY_MISMATCH = "carrier_identity_mismatch"
    BASE_BRANCH_MISMATCH = "base_branch_mismatch"
    HEAD_BRANCH_MISMATCH = "head_branch_mismatch"
    BASE_MOVED = "base_moved"
    HEAD_MOVED = "head_moved"
    MERGE_BASE_MISMATCH = "merge_base_mismatch"
    HEAD_BEHIND_BASE = "head_behind_base"
    NO_RELEASE_DELTA = "no_release_delta"
    CHANGED_PATHS_MISMATCH = "changed_paths_mismatch"
    CHANGED_PATH_EVIDENCE_CONFLICT = "changed_path_evidence_conflict"
    EVIDENCE_INCOMPLETE = "evidence_incomplete"
    EVIDENCE_NOT_CURRENT = "evidence_not_current"
    PULL_REQUEST_DRAFT = "pull_request_draft"
    PULL_REQUEST_CLOSED = "pull_request_closed"
    MERGEABILITY_UNKNOWN = "mergeability_unknown"
    MERGE_CONFLICT = "merge_conflict"
    BASE_BRANCH_UNPROTECTED = "base_branch_unprotected"
    MERGE_METHOD_UNAVAILABLE = "merge_method_unavailable"
    POLICY_OMITS_BRANCH_CHECK = "policy_omits_branch_check"
    CHECK_IDENTITY_CONFLICT = "check_identity_conflict"
    CHECK_TARGET_MOVED = "check_target_moved"
    REQUIRED_CHECK_MISSING = "required_check_missing"
    REQUIRED_CHECK_PENDING = "required_check_pending"
    REQUIRED_CHECK_FAILED = "required_check_failed"
    REVIEW_TARGET_MOVED = "review_target_moved"
    REVIEW_CHANGES_REQUESTED = "review_changes_requested"
    REVIEW_PENDING = "review_pending"
    REVIEW_UNKNOWN = "review_unknown"
    REVIEW_THREADS_UNRESOLVED = "review_threads_unresolved"


_SUCCESS = {
    CheckConclusion.SUCCESS,
    CheckConclusion.NEUTRAL,
    CheckConclusion.SKIPPED,
}


def _err(message: str) -> None:
    raise ReleaseEvidenceError(message)


def _text(name: str, value: object, limit: int, spaces: bool = True) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        _err(f"{name} must be a non-empty exact string")
    if len(value) > limit or _CTRL.search(value):
        _err(f"{name} is malformed")
    if not spaces and any(char.isspace() for char in value):
        _err(f"{name} must not contain whitespace")
    return value


def _kind(name: str, value: object, kind: type) -> None:
    if not isinstance(value, kind):
        _err(f"{name} must be {kind.__name__}")


def _repo(value: object) -> str:
    value = _text("repository", value, 201, False)
    if not _REPO.fullmatch(value):
        _err("repository must be owner/name")
    return value


def _sha(name: str, value: object, optional: bool = False) -> str | None:
    if optional and value is None:
        return None
    value = _text(name, value, 40, False)
    if not _SHA.fullmatch(value):
        _err(f"{name} must be a lowercase 40-hex SHA")
    return value


def _branch(name: str, value: object) -> str:
    value = _text(name, value, 255, False)
    if value[:1] == "/" or value[-1:] == "/" or "//" in value or ".." in value:
        _err(f"{name} is malformed")
    return value


def _path(value: object) -> str:
    value = _text("changed path", value, 1024)
    parts = value.split("/")
    if value[:1] == "/" or value[-1:] == "/" or "\\" in value:
        _err("changed path must be repository-relative")
    if any(part in {"", ".", ".."} for part in parts):
        _err("changed path must be repository-relative")
    return value


def _tuple(value: object, kind: type, name: str) -> tuple:
    if not isinstance(value, tuple) or not all(isinstance(x, kind) for x in value):
        _err(f"{name} must be a tuple of {kind.__name__}")
    if len(value) != len(set(value)):
        _err(f"{name} must be unique")
    return value


def _paths(value: object, nonempty: bool = False) -> tuple[str, ...]:
    if not isinstance(value, tuple):
        _err("changed paths must be a tuple")
    result = tuple(_path(item) for item in value)
    if nonempty and not result:
        _err("expected changed paths cannot be empty")
    if len(result) != len(set(result)):
        _err("changed paths must be unique")
    return tuple(sorted(result))


def _checks(value: object, name: str) -> tuple[CheckIdentity, ...]:
    result = _tuple(value, CheckIdentity, name)
    return tuple(sorted(result, key=lambda item: item.sort_key))


def _methods(value: object) -> tuple[MergeMethod, ...]:
    result = _tuple(value, MergeMethod, "allowed_merge_methods")
    return tuple(sorted(result, key=lambda item: item.value))


@dc.dataclass(frozen=True, slots=True)
class SourceRef:
    ref: str
    observed_at: str | None
    freshness: EvidenceFreshness

    def __post_init__(self) -> None:
        _text("source ref", self.ref, 512)
        _kind("freshness", self.freshness, EvidenceFreshness)
        if self.observed_at is not None:
            if not _UTC.fullmatch(_text("observed_at", self.observed_at, 64)):
                _err("observed_at must be RFC3339 UTC")
        if self.freshness is not EvidenceFreshness.UNKNOWN and not self.observed_at:
            _err("current or stale evidence requires observed_at")


@dc.dataclass(frozen=True, order=True, slots=True)
class CheckIdentity:
    context: str
    app_id: int | None

    def __post_init__(self) -> None:
        _text("check context", self.context, 255)
        if self.app_id is not None:
            if type(self.app_id) is not int or self.app_id < 1:
                _err("check app_id must be positive or None")

    @property
    def sort_key(self) -> tuple[str, int]:
        return self.context, -1 if self.app_id is None else self.app_id


@dc.dataclass(frozen=True, slots=True)
class ReleasePolicy:
    operation_key: str
    repository: str
    pr_number: int
    expected_base_branch: str
    expected_base_sha: str
    expected_head_branch: str
    expected_head_sha: str
    expected_changed_paths: tuple[str, ...]
    merge_method: MergeMethod
    required_checks: tuple[CheckIdentity, ...]
    review_required: bool
    source: SourceRef

    def __post_init__(self) -> None:
        operation = _text("operation_key", self.operation_key, 192, False)
        if not _OP.fullmatch(operation):
            _err("operation_key is malformed")
        _repo(self.repository)
        if type(self.pr_number) is not int or self.pr_number < 1:
            _err("pr_number must be positive")
        _branch("expected_base_branch", self.expected_base_branch)
        _sha("expected_base_sha", self.expected_base_sha)
        _branch("expected_head_branch", self.expected_head_branch)
        _sha("expected_head_sha", self.expected_head_sha)
        object.__setattr__(
            self,
            "expected_changed_paths",
            _paths(self.expected_changed_paths, True),
        )
        _kind("merge_method", self.merge_method, MergeMethod)
        object.__setattr__(
            self,
            "required_checks",
            _checks(self.required_checks, "required_checks"),
        )
        if type(self.review_required) is not bool:
            _err("review_required must be bool")
        _kind("policy source", self.source, SourceRef)


@dc.dataclass(frozen=True, slots=True)
class PullRequestFact:
    repository: str
    number: int
    state: PullRequestState
    draft: bool
    merged: bool
    base_branch: str
    base_sha: str
    head_branch: str
    head_sha: str
    merged_commit_sha: str | None
    mergeability: Mergeability
    changed_paths: tuple[str, ...]
    changed_files_complete: bool
    source: SourceRef

    def __post_init__(self) -> None:
        _repo(self.repository)
        if type(self.number) is not int or self.number < 1:
            _err("pull request number must be positive")
        _kind("pull request state", self.state, PullRequestState)
        if type(self.draft) is not bool or type(self.merged) is not bool:
            _err("draft/merged must be bool")
        if self.merged and (self.state is not PullRequestState.CLOSED or self.draft):
            _err("merged pull request must be closed and non-draft")
        _branch("base_branch", self.base_branch)
        _sha("base_sha", self.base_sha)
        _branch("head_branch", self.head_branch)
        _sha("head_sha", self.head_sha)
        merged_sha = _sha("merged_commit_sha", self.merged_commit_sha, True)
        if self.merged != (merged_sha is not None):
            _err("merged state and merged_commit_sha disagree")
        _kind("mergeability", self.mergeability, Mergeability)
        object.__setattr__(self, "changed_paths", _paths(self.changed_paths))
        if type(self.changed_files_complete) is not bool:
            _err("changed_files_complete must be bool")
        _kind("pull request source", self.source, SourceRef)


@dc.dataclass(frozen=True, slots=True)
class BranchPolicyFact:
    repository: str
    branch: str
    branch_head_sha: str
    protected: bool
    required_checks: tuple[CheckIdentity, ...]
    allowed_merge_methods: tuple[MergeMethod, ...]
    source: SourceRef

    def __post_init__(self) -> None:
        _repo(self.repository)
        _branch("branch", self.branch)
        _sha("branch_head_sha", self.branch_head_sha)
        if type(self.protected) is not bool:
            _err("protected must be bool")
        object.__setattr__(
            self,
            "required_checks",
            _checks(self.required_checks, "branch required_checks"),
        )
        object.__setattr__(
            self,
            "allowed_merge_methods",
            _methods(self.allowed_merge_methods),
        )
        _kind("branch source", self.source, SourceRef)


@dc.dataclass(frozen=True, slots=True)
class CompareFact:
    base_sha: str
    head_sha: str
    merge_base_sha: str
    ahead_by: int
    behind_by: int
    changed_paths: tuple[str, ...]
    comparison_complete: bool
    source: SourceRef

    def __post_init__(self) -> None:
        _sha("compare base_sha", self.base_sha)
        _sha("compare head_sha", self.head_sha)
        _sha("compare merge_base_sha", self.merge_base_sha)
        if type(self.ahead_by) is not int or self.ahead_by < 0:
            _err("ahead_by must be an integer >= 0")
        if type(self.behind_by) is not int or self.behind_by < 0:
            _err("behind_by must be an integer >= 0")
        object.__setattr__(self, "changed_paths", _paths(self.changed_paths))
        if type(self.comparison_complete) is not bool:
            _err("comparison_complete must be bool")
        _kind("comparison source", self.source, SourceRef)


@dc.dataclass(frozen=True, slots=True)
class CheckFact:
    identity: CheckIdentity
    status: CheckStatus
    conclusion: CheckConclusion | None
    target_sha: str
    source: SourceRef

    def __post_init__(self) -> None:
        _kind("check identity", self.identity, CheckIdentity)
        _kind("check status", self.status, CheckStatus)
        if self.status is CheckStatus.COMPLETED:
            _kind("check conclusion", self.conclusion, CheckConclusion)
        elif self.conclusion is not None:
            _err("nonterminal check cannot have conclusion")
        _sha("check target_sha", self.target_sha)
        _kind("check source", self.source, SourceRef)


@dc.dataclass(frozen=True, slots=True)
class ReviewGateFact:
    head_sha: str
    decision: ReviewDecision
    unresolved_thread_count: int
    review_set_complete: bool
    source: SourceRef

    def __post_init__(self) -> None:
        _sha("review head_sha", self.head_sha)
        _kind("review decision", self.decision, ReviewDecision)
        count = self.unresolved_thread_count
        if type(count) is not int or count < 0:
            _err("unresolved_thread_count must be >= 0")
        if type(self.review_set_complete) is not bool:
            _err("review_set_complete must be bool")
        _kind("review source", self.source, SourceRef)


@dc.dataclass(frozen=True, slots=True)
class ReleaseSnapshot:
    pull_request: PullRequestFact
    branch_policy: BranchPolicyFact
    comparison: CompareFact
    checks: tuple[CheckFact, ...]
    checks_complete: bool
    review_gate: ReviewGateFact
    source: SourceRef

    def __post_init__(self) -> None:
        _kind("pull_request", self.pull_request, PullRequestFact)
        _kind("branch_policy", self.branch_policy, BranchPolicyFact)
        _kind("comparison", self.comparison, CompareFact)
        if not isinstance(self.checks, tuple):
            _err("checks must be a tuple")
        for item in self.checks:
            _kind("check", item, CheckFact)
        if type(self.checks_complete) is not bool:
            _err("checks_complete must be bool")
        _kind("review_gate", self.review_gate, ReviewGateFact)
        _kind("snapshot source", self.source, SourceRef)


@dc.dataclass(frozen=True, slots=True)
class GuardedReleaseCandidate:
    repository: str
    pr_number: int
    expected_head_branch: str
    expected_head_sha: str
    merge_method: MergeMethod


@dc.dataclass(frozen=True, slots=True)
class ReleaseAssessment:
    status: ReleaseAssessmentStatus
    reasons: tuple[ReleaseReason, ...]
    operation_key: str
    repository: str
    pr_number: int
    expected_base_sha: str
    expected_head_sha: str
    merged_commit_sha: str | None
    evidence_refs: tuple[str, ...]
    evidence_digest: str
    guarded_merge_request: GuardedReleaseCandidate | None
    organizational_authority_granted: bool = False
    production_acceptance_claimed: bool = False
    schema: str = SCHEMA

    def to_dict(self) -> dict[str, object]:
        candidate = _wire(self.guarded_merge_request)
        return {
            "schema": self.schema,
            "status": self.status.value,
            "reasons": [item.value for item in self.reasons],
            "operation_key": self.operation_key,
            "repository": self.repository,
            "pr_number": self.pr_number,
            "expected_base_sha": self.expected_base_sha,
            "expected_head_sha": self.expected_head_sha,
            "merged_commit_sha": self.merged_commit_sha,
            "evidence_refs": list(self.evidence_refs),
            "evidence_digest": self.evidence_digest,
            "guarded_merge_request": candidate,
            "organizational_authority_granted": False,
            "production_acceptance_claimed": False,
        }


def _wire(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, enum.Enum):
        return value.value
    if dc.is_dataclass(value):
        return {
            field.name: _wire(getattr(value, field.name))
            for field in dc.fields(value)
        }
    if isinstance(value, Mapping):
        return {str(key): _wire(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_wire(item) for item in value]
    raise TypeError(type(value).__name__)


def _sources(policy: ReleasePolicy, snap: ReleaseSnapshot) -> tuple[SourceRef, ...]:
    return (
        policy.source,
        snap.source,
        snap.pull_request.source,
        snap.branch_policy.source,
        snap.comparison.source,
        snap.review_gate.source,
        *(item.source for item in snap.checks),
    )


def _digest(policy: ReleasePolicy, snap: ReleaseSnapshot) -> str:
    checks = tuple(
        sorted(
            snap.checks,
            key=lambda item: (
                item.identity.sort_key,
                item.target_sha,
                item.status.value,
                "" if item.conclusion is None else item.conclusion.value,
                item.source.ref,
            ),
        )
    )
    normalized = dc.replace(snap, checks=checks)
    raw = json.dumps(
        {"schema": SCHEMA, "policy": _wire(policy), "snapshot": _wire(normalized)},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode()
    return hashlib.sha256(raw).hexdigest()


def _result(
    status: ReleaseAssessmentStatus,
    reasons: Iterable[ReleaseReason],
    policy: ReleasePolicy,
    snap: ReleaseSnapshot,
    candidate: GuardedReleaseCandidate | None = None,
) -> ReleaseAssessment:
    return ReleaseAssessment(
        status=status,
        reasons=tuple(sorted(set(reasons), key=lambda item: item.value)),
        operation_key=policy.operation_key,
        repository=policy.repository,
        pr_number=policy.pr_number,
        expected_base_sha=policy.expected_base_sha,
        expected_head_sha=policy.expected_head_sha,
        merged_commit_sha=snap.pull_request.merged_commit_sha,
        evidence_refs=tuple(sorted({item.ref for item in _sources(policy, snap)})),
        evidence_digest=_digest(policy, snap),
        guarded_merge_request=candidate,
    )


def assess_release_gate(
    snap: ReleaseSnapshot,
    policy: ReleasePolicy,
) -> ReleaseAssessment:
    """Assess one immutable GitHub snapshot without producing an effect."""
    _kind("snapshot", snap, ReleaseSnapshot)
    _kind("policy", policy, ReleasePolicy)
    pr, branch, compare = snap.pull_request, snap.branch_policy, snap.comparison

    reconcile: list[ReleaseReason] = []
    if pr.repository != policy.repository or pr.number != policy.pr_number:
        reconcile.append(ReleaseReason.CARRIER_IDENTITY_MISMATCH)
    if pr.head_branch != policy.expected_head_branch:
        reconcile.append(ReleaseReason.HEAD_BRANCH_MISMATCH)
    if pr.head_sha != policy.expected_head_sha:
        reconcile.append(ReleaseReason.HEAD_MOVED)
    if not pr.changed_files_complete:
        reconcile.append(ReleaseReason.EVIDENCE_INCOMPLETE)
    current = (policy.source, snap.source, pr.source)
    if any(item.freshness is not EvidenceFreshness.CURRENT for item in current):
        reconcile.append(ReleaseReason.EVIDENCE_NOT_CURRENT)
    if reconcile:
        return _result(
            ReleaseAssessmentStatus.RECONCILIATION_REQUIRED,
            reconcile,
            policy,
            snap,
        )
    if pr.merged:
        if pr.changed_paths != policy.expected_changed_paths:
            return _result(
                ReleaseAssessmentStatus.RECONCILIATION_REQUIRED,
                (ReleaseReason.CHANGED_PATHS_MISMATCH,),
                policy,
                snap,
            )
        return _result(
            ReleaseAssessmentStatus.ALREADY_MERGED,
            (ReleaseReason.ALREADY_MERGED,),
            policy,
            snap,
        )

    reconcile = []
    if branch.repository != policy.repository:
        reconcile.append(ReleaseReason.CARRIER_IDENTITY_MISMATCH)
    if (
        pr.base_branch != policy.expected_base_branch
        or branch.branch != policy.expected_base_branch
    ):
        reconcile.append(ReleaseReason.BASE_BRANCH_MISMATCH)
    if (
        pr.base_sha != policy.expected_base_sha
        or branch.branch_head_sha != policy.expected_base_sha
        or compare.base_sha != policy.expected_base_sha
    ):
        reconcile.append(ReleaseReason.BASE_MOVED)
    if compare.head_sha != policy.expected_head_sha:
        reconcile.append(ReleaseReason.HEAD_MOVED)
    if compare.merge_base_sha != policy.expected_base_sha:
        reconcile.append(ReleaseReason.MERGE_BASE_MISMATCH)
    if compare.changed_paths != pr.changed_paths:
        reconcile.append(ReleaseReason.CHANGED_PATH_EVIDENCE_CONFLICT)
    if not (
        compare.comparison_complete
        and snap.checks_complete
        and snap.review_gate.review_set_complete
    ):
        reconcile.append(ReleaseReason.EVIDENCE_INCOMPLETE)
    if any(
        item.freshness is not EvidenceFreshness.CURRENT
        for item in _sources(policy, snap)
    ):
        reconcile.append(ReleaseReason.EVIDENCE_NOT_CURRENT)
    if not set(branch.required_checks).issubset(policy.required_checks):
        reconcile.append(ReleaseReason.POLICY_OMITS_BRANCH_CHECK)

    by_check: dict[CheckIdentity, list[CheckFact]] = {}
    for item in snap.checks:
        by_check.setdefault(item.identity, []).append(item)
    if any(len(items) != 1 for items in by_check.values()):
        reconcile.append(ReleaseReason.CHECK_IDENTITY_CONFLICT)
    review = snap.review_gate
    if policy.review_required and review.head_sha != policy.expected_head_sha:
        reconcile.append(ReleaseReason.REVIEW_TARGET_MOVED)
    if policy.review_required and review.decision is ReviewDecision.UNKNOWN:
        reconcile.append(ReleaseReason.REVIEW_UNKNOWN)
    if reconcile:
        return _result(
            ReleaseAssessmentStatus.RECONCILIATION_REQUIRED,
            reconcile,
            policy,
            snap,
        )

    blocked: list[ReleaseReason] = []
    if pr.changed_paths != policy.expected_changed_paths:
        blocked.append(ReleaseReason.CHANGED_PATHS_MISMATCH)
    if compare.behind_by:
        blocked.append(ReleaseReason.HEAD_BEHIND_BASE)
    if not compare.ahead_by:
        blocked.append(ReleaseReason.NO_RELEASE_DELTA)
    if pr.state is PullRequestState.CLOSED:
        blocked.append(ReleaseReason.PULL_REQUEST_CLOSED)
    if pr.draft:
        blocked.append(ReleaseReason.PULL_REQUEST_DRAFT)
    if pr.mergeability is Mergeability.UNKNOWN:
        return _result(
            ReleaseAssessmentStatus.RECONCILIATION_REQUIRED,
            (ReleaseReason.MERGEABILITY_UNKNOWN,),
            policy,
            snap,
        )
    if pr.mergeability is Mergeability.CONFLICTING:
        blocked.append(ReleaseReason.MERGE_CONFLICT)
    if not branch.protected:
        blocked.append(ReleaseReason.BASE_BRANCH_UNPROTECTED)
    if policy.merge_method not in branch.allowed_merge_methods:
        blocked.append(ReleaseReason.MERGE_METHOD_UNAVAILABLE)

    for identity in policy.required_checks:
        checks = by_check.get(identity, ())
        if not checks:
            blocked.append(ReleaseReason.REQUIRED_CHECK_MISSING)
            continue
        check = checks[0]
        if check.target_sha != policy.expected_head_sha:
            return _result(
                ReleaseAssessmentStatus.RECONCILIATION_REQUIRED,
                (ReleaseReason.CHECK_TARGET_MOVED,),
                policy,
                snap,
            )
        if check.status is not CheckStatus.COMPLETED:
            blocked.append(ReleaseReason.REQUIRED_CHECK_PENDING)
        elif check.conclusion not in _SUCCESS:
            blocked.append(ReleaseReason.REQUIRED_CHECK_FAILED)

    if policy.review_required:
        if review.decision is ReviewDecision.CHANGES_REQUESTED:
            blocked.append(ReleaseReason.REVIEW_CHANGES_REQUESTED)
        elif review.decision in {ReviewDecision.PENDING, ReviewDecision.NOT_REQUIRED}:
            blocked.append(ReleaseReason.REVIEW_PENDING)
        if review.unresolved_thread_count:
            blocked.append(ReleaseReason.REVIEW_THREADS_UNRESOLVED)
    elif review.decision is not ReviewDecision.NOT_REQUIRED:
        blocked.append(ReleaseReason.REVIEW_PENDING)
    if blocked:
        return _result(
            ReleaseAssessmentStatus.BLOCKED,
            blocked,
            policy,
            snap,
        )

    candidate = GuardedReleaseCandidate(
        repository=policy.repository,
        pr_number=policy.pr_number,
        expected_head_branch=policy.expected_head_branch,
        expected_head_sha=policy.expected_head_sha,
        merge_method=policy.merge_method,
    )
    return _result(
        ReleaseAssessmentStatus.READY_FOR_EXPECTED_HEAD_RELEASE,
        (),
        policy,
        snap,
        candidate,
    )


__all__ = [
    "BranchPolicyFact",
    "CheckConclusion",
    "CheckFact",
    "CheckIdentity",
    "CheckStatus",
    "CompareFact",
    "EvidenceFreshness",
    "GuardedReleaseCandidate",
    "MergeMethod",
    "Mergeability",
    "PullRequestFact",
    "PullRequestState",
    "ReleaseAssessment",
    "ReleaseAssessmentStatus",
    "ReleaseEvidenceError",
    "ReleasePolicy",
    "ReleaseReason",
    "ReleaseSnapshot",
    "ReviewDecision",
    "ReviewGateFact",
    "SCHEMA",
    "SourceRef",
    "assess_release_gate",
]
