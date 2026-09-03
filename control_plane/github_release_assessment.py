"""Pure deterministic assessment for one exact GitHub release candidate.

The caller supplies immutable, source-owned facts.  This module performs no I/O,
network access, mutation, credential selection, clock access, subprocess work,
filesystem discovery, or persistence.  It owns only the bounded classification
semantics for ``mastermind.github_release_assessment.v1``.

The contract deliberately separates observed GitHub facts from expected policy
identity.  A caller cannot make a candidate eligible by supplying naked
``compatible`` or ``production present`` conclusions: source and production
receipts are bound to the exact repository, PR, refs, SHAs, paths, owner,
revision, and observation epoch.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import re
from enum import Enum
from typing import Any, Mapping


INPUT_SCHEMA = "mastermind.github_release_assessment.input.v2"
OUTPUT_SCHEMA = "mastermind.github_release_assessment.v1"

MAX_PATHS = 256
MAX_SEMANTIC_OWNERS = 128
MAX_CARRIERS = 64
MAX_WRITERS = 128
MAX_COLLISIONS = 128
MAX_CHECK_IDENTITIES = 128
MAX_CHECK_ATTEMPTS = 512
MAX_REVIEWS = 256
MAX_SOURCE_REFS = 256
MAX_EVIDENCE_AGE_SECONDS = 86_400

_SHA_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
_OPERATION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,191}$")
_REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$")
_REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,255}$")
_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,255}$")
_CHECK_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._:/()\[\]-]{0,127}$")
_SOURCE_REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9:._/@#-]{0,255}$")
_PATH_RE = re.compile(r"^[A-Za-z0-9._/-]{1,512}$")
_SECRET_PATTERNS = (
    re.compile(r"github_pat_", re.IGNORECASE),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]", re.IGNORECASE),
    re.compile(r"\bxox[baprs]-", re.IGNORECASE),
    re.compile(r"\bsk-[A-Za-z0-9]", re.IGNORECASE),
    re.compile(r"authorization\s*=", re.IGNORECASE),
    re.compile(r"bearer\s+", re.IGNORECASE),
    re.compile(r"password\s*=", re.IGNORECASE),
    re.compile(r"-----BEGIN", re.IGNORECASE),
)


class AssessmentInputError(ValueError):
    """Raised when an immutable assessment packet is malformed or unsafe."""


class AssessmentVerdict(str, Enum):
    ELIGIBLE = "ELIGIBLE"
    HELD = "HELD"
    REFUSED = "REFUSED"
    UNKNOWN = "UNKNOWN"


class AssessmentIssue(str, Enum):
    REPOSITORY_MISMATCH = "REPOSITORY_MISMATCH"
    PULL_REQUEST_MISMATCH = "PULL_REQUEST_MISMATCH"
    PROTECTED_REF_MOVED = "PROTECTED_REF_MOVED"
    CANDIDATE_HEAD_MOVED = "CANDIDATE_HEAD_MOVED"
    BASE_REF_MISMATCH = "BASE_REF_MISMATCH"
    BASE_BRANCH_UNPROTECTED = "BASE_BRANCH_UNPROTECTED"
    PR_STATE_REFUSED = "PR_STATE_REFUSED"
    PR_STATE_UNKNOWN = "PR_STATE_UNKNOWN"
    PR_DRAFT = "PR_DRAFT"
    MERGE_CONFLICT = "MERGE_CONFLICT"
    MERGEABILITY_UNKNOWN = "MERGEABILITY_UNKNOWN"
    BASE_OR_MERGE_CONTEXT_UNKNOWN = "BASE_OR_MERGE_CONTEXT_UNKNOWN"
    CURRENT_BASE_REQUIRED = "CURRENT_BASE_REQUIRED"
    EMPTY_RELEASE_DELTA = "EMPTY_RELEASE_DELTA"
    PATH_COVERAGE_PARTIAL = "PATH_COVERAGE_PARTIAL"
    EXPECTED_PATH_MISMATCH = "EXPECTED_PATH_MISMATCH"
    PATH_COLLISION = "PATH_COLLISION"
    PATH_COLLISION_COVERAGE_PARTIAL = "PATH_COLLISION_COVERAGE_PARTIAL"
    SEMANTIC_OWNER_COVERAGE_PARTIAL = "SEMANTIC_OWNER_COVERAGE_PARTIAL"
    SEMANTIC_OWNER_AMBIGUOUS = "SEMANTIC_OWNER_AMBIGUOUS"
    SEMANTIC_OWNER_COLLISION = "SEMANTIC_OWNER_COLLISION"
    OPERATION_CARRIER_NOT_FOUND = "OPERATION_CARRIER_NOT_FOUND"
    OPERATION_CARRIER_CONFLICT = "OPERATION_CARRIER_CONFLICT"
    CARRIER_COVERAGE_PARTIAL = "CARRIER_COVERAGE_PARTIAL"
    CARRIER_WRITER_NOT_FOUND = "CARRIER_WRITER_NOT_FOUND"
    CARRIER_WRITER_CONFLICT = "CARRIER_WRITER_CONFLICT"
    WRITER_COVERAGE_PARTIAL = "WRITER_COVERAGE_PARTIAL"
    BRANCH_REQUIRED_CHECK_OMITTED = "BRANCH_REQUIRED_CHECK_OMITTED"
    CHECK_MISSING = "CHECK_MISSING"
    CHECK_PENDING = "CHECK_PENDING"
    CHECK_FAILED = "CHECK_FAILED"
    CHECK_CANCELLED = "CHECK_CANCELLED"
    CHECK_SUPERSEDED = "CHECK_SUPERSEDED"
    CHECK_SKIPPED_NOT_ALLOWED = "CHECK_SKIPPED_NOT_ALLOWED"
    CHECK_NEUTRAL_NOT_ALLOWED = "CHECK_NEUTRAL_NOT_ALLOWED"
    CHECK_COVERAGE_PARTIAL = "CHECK_COVERAGE_PARTIAL"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    CHANGES_REQUESTED = "CHANGES_REQUESTED"
    UNRESOLVED_REVIEW_THREAD = "UNRESOLVED_REVIEW_THREAD"
    REVIEW_COVERAGE_PARTIAL = "REVIEW_COVERAGE_PARTIAL"
    SOURCE_EVIDENCE_MISSING = "SOURCE_EVIDENCE_MISSING"
    SOURCE_SUBJECT_MISMATCH = "SOURCE_SUBJECT_MISMATCH"
    SOURCE_OWNER_MISMATCH = "SOURCE_OWNER_MISMATCH"
    SOURCE_REVISION_MISMATCH = "SOURCE_REVISION_MISMATCH"
    SOURCE_INCOMPLETE = "SOURCE_INCOMPLETE"
    SOURCE_STALE = "SOURCE_STALE"
    SOURCE_FUTURE = "SOURCE_FUTURE"
    SOURCE_CONFLICT = "SOURCE_CONFLICT"
    SOURCE_LAW_INCOMPATIBLE = "SOURCE_LAW_INCOMPATIBLE"
    SOURCE_LAW_UNKNOWN = "SOURCE_LAW_UNKNOWN"
    PRODUCTION_PROOF_MISSING = "PRODUCTION_PROOF_MISSING"
    PRODUCTION_PROOF_PARTIAL = "PRODUCTION_PROOF_PARTIAL"
    PRODUCTION_PROOF_UNKNOWN = "PRODUCTION_PROOF_UNKNOWN"
    PRODUCTION_PROOF_INVALID = "PRODUCTION_PROOF_INVALID"
    PRODUCTION_PROOF_STALE = "PRODUCTION_PROOF_STALE"
    PRODUCTION_PROOF_FUTURE = "PRODUCTION_PROOF_FUTURE"
    COMPLETION_CLAIM_OVERSTATED = "COMPLETION_CLAIM_OVERSTATED"
    MERGE_METHOD_REFUSED = "MERGE_METHOD_REFUSED"
    PRIOR_EFFECT_UNKNOWN = "PRIOR_EFFECT_UNKNOWN"
    PRIOR_EFFECT_APPLIED = "PRIOR_EFFECT_APPLIED"
    PRIOR_EFFECT_CONFLICT = "PRIOR_EFFECT_CONFLICT"


class CapabilityState(str, Enum):
    PROVEN_LIVE = "PROVEN_LIVE"
    BUILT_NOT_PROVEN = "BUILT_NOT_PROVEN"
    PARTIAL = "PARTIAL"
    DARK_OR_DISCONNECTED = "DARK_OR_DISCONNECTED"
    BROKEN = "BROKEN"
    SPEC_ONLY = "SPEC_ONLY"
    NOT_BUILT = "NOT_BUILT"
    REJECTED_BY_DESIGN = "REJECTED_BY_DESIGN"


class SourceCoverage(str, Enum):
    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"
    STALE = "STALE"
    CONFLICT = "CONFLICT"


class SourceLawState(str, Enum):
    COMPATIBLE = "COMPATIBLE"
    INCOMPATIBLE = "INCOMPATIBLE"
    UNKNOWN = "UNKNOWN"


class EffectState(str, Enum):
    NOT_APPLIED = "NOT_APPLIED"
    APPLIED = "APPLIED"
    EFFECT_UNKNOWN = "EFFECT_UNKNOWN"


class MergeMethod(str, Enum):
    SQUASH = "SQUASH"
    MERGE = "MERGE"
    REBASE = "REBASE"


class PullRequestState(str, Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    MERGED = "MERGED"
    UNKNOWN = "UNKNOWN"


class Mergeability(str, Enum):
    MERGEABLE = "MERGEABLE"
    CONFLICTING = "CONFLICTING"
    UNKNOWN = "UNKNOWN"


class CheckStatus(str, Enum):
    QUEUED = "QUEUED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"


class CheckConclusion(str, Enum):
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    CANCELLED = "CANCELLED"
    SKIPPED = "SKIPPED"
    NEUTRAL = "NEUTRAL"
    TIMED_OUT = "TIMED_OUT"
    ACTION_REQUIRED = "ACTION_REQUIRED"
    STALE = "STALE"
    UNKNOWN = "UNKNOWN"


class ReviewState(str, Enum):
    APPROVED = "APPROVED"
    CHANGES_REQUESTED = "CHANGES_REQUESTED"
    COMMENTED = "COMMENTED"
    DISMISSED = "DISMISSED"


class ProductionProofState(str, Enum):
    PRESENT = "PRESENT"
    MISSING = "MISSING"
    PARTIAL = "PARTIAL"
    UNKNOWN = "UNKNOWN"


class MergeContextState(str, Enum):
    CURRENT = "CURRENT"
    BEHIND_COMPATIBLE = "BEHIND_COMPATIBLE"
    HELD = "HELD"
    UNKNOWN = "UNKNOWN"


class PathState(str, Enum):
    EXACT = "EXACT"
    MISMATCH = "MISMATCH"
    UNKNOWN = "UNKNOWN"


class SemanticOwnerAssessmentState(str, Enum):
    EXACT = "EXACT"
    CONFLICT = "CONFLICT"
    UNKNOWN = "UNKNOWN"


class CarrierAssessmentState(str, Enum):
    EXACT = "EXACT"
    CONFLICT = "CONFLICT"
    UNKNOWN = "UNKNOWN"


class WriterAssessmentState(str, Enum):
    EXACT = "EXACT"
    CONFLICT = "CONFLICT"
    UNKNOWN = "UNKNOWN"


class CheckAssessmentState(str, Enum):
    GREEN = "GREEN"
    PENDING = "PENDING"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


class ReviewAssessmentState(str, Enum):
    SATISFIED = "SATISFIED"
    PENDING = "PENDING"
    BLOCKED = "BLOCKED"
    UNKNOWN = "UNKNOWN"


class SourceAssessmentState(str, Enum):
    CURRENT = "CURRENT"
    INCOMPATIBLE = "INCOMPATIBLE"
    UNKNOWN = "UNKNOWN"


class ProductionAssessmentState(str, Enum):
    NOT_REQUIRED = "NOT_REQUIRED"
    PRESENT = "PRESENT"
    MISSING = "MISSING"
    UNKNOWN = "UNKNOWN"


class CompletionClaimState(str, Enum):
    VALID = "VALID"
    OVERSTATED = "OVERSTATED"
    UNKNOWN = "UNKNOWN"


@dataclasses.dataclass(frozen=True)
class ReleaseTargetExpectation:
    repository: str
    repository_id: int
    pull_request_number: int
    protected_ref: str
    expected_protected_sha: str
    candidate_ref: str
    expected_head_sha: str


@dataclasses.dataclass(frozen=True)
class PullRequestTarget:
    repository: str
    repository_id: int
    pull_request_number: int
    state: PullRequestState
    draft: bool
    merged: bool
    merged_commit_sha: str | None
    mergeability: Mergeability
    protected_ref: str
    protected_sha: str
    protected_branch_protected: bool
    base_ref: str
    base_sha: str | None
    candidate_ref: str
    candidate_sha: str
    merge_base_sha: str | None
    ahead_by: int | None
    behind_by: int | None
    changed_paths: tuple[str, ...]
    changed_paths_complete: bool


@dataclasses.dataclass(frozen=True)
class EvidenceSubject:
    repository: str
    repository_id: int
    pull_request_number: int
    protected_ref: str
    protected_sha: str
    base_ref: str
    base_sha: str | None
    candidate_ref: str
    candidate_sha: str
    changed_paths: tuple[str, ...]


@dataclasses.dataclass(frozen=True)
class CurrentSourceEvidence:
    subject: EvidenceSubject
    owner_id: str
    revision: str
    observed_at: int
    coverage: SourceCoverage
    law_state: SourceLawState
    source_ref: str


@dataclasses.dataclass(frozen=True)
class ProductionProof:
    capability_id: str
    subject_id: str
    target_subject: EvidenceSubject
    owner_id: str
    revision: str
    observed_at: int
    coverage: SourceCoverage
    state: ProductionProofState
    source_ref: str


@dataclasses.dataclass(frozen=True)
class CheckIdentity:
    context: str
    app_id: int | None

    def key(self) -> tuple[str, int]:
        return (self.context, -1 if self.app_id is None else self.app_id)


@dataclasses.dataclass(frozen=True)
class CheckAttempt:
    identity: CheckIdentity
    head_sha: str
    attempt: int
    sequence: int
    status: CheckStatus
    conclusion: CheckConclusion | None
    applicable: bool
    superseded: bool
    source_ref: str


@dataclasses.dataclass(frozen=True)
class ReviewEvent:
    reviewer_id: str
    head_sha: str
    sequence: int
    state: ReviewState
    source_ref: str


@dataclasses.dataclass(frozen=True)
class SemanticOwnerExpectation:
    path_prefix: str
    owner_id: str | None
    no_owner_allowed: bool = False


@dataclasses.dataclass(frozen=True)
class SemanticOwnerFact:
    path_prefix: str
    owner_id: str
    operation_key: str
    active: bool
    source_ref: str


@dataclasses.dataclass(frozen=True)
class CarrierFact:
    carrier_ref: str
    operation_key: str
    repository: str
    repository_id: int
    pull_request_number: int
    base_ref: str
    base_sha: str | None
    candidate_ref: str
    candidate_sha: str
    active: bool
    source_ref: str


@dataclasses.dataclass(frozen=True)
class WriterFact:
    writer_id: str
    operation_key: str
    repository_id: int
    pull_request_number: int
    paths: tuple[str, ...]
    active: bool
    source_ref: str


@dataclasses.dataclass(frozen=True)
class PathCollisionFact:
    path: str
    other_operation_key: str
    source_ref: str


@dataclasses.dataclass(frozen=True)
class MergedEffectReceipt:
    repository: str
    repository_id: int
    pull_request_number: int
    candidate_sha: str
    merged_commit_sha: str
    changed_paths: tuple[str, ...]
    source_ref: str


@dataclasses.dataclass(frozen=True)
class AssessmentInput:
    schema: str
    operation_key: str
    observed_at: int
    expected_target: ReleaseTargetExpectation
    target: PullRequestTarget
    expected_paths: tuple[str, ...]
    expected_semantic_owners: tuple[SemanticOwnerExpectation, ...]
    semantic_owner_facts: tuple[SemanticOwnerFact, ...]
    semantic_owners_complete: bool
    carrier_facts: tuple[CarrierFact, ...]
    carriers_complete: bool
    expected_writer_id: str
    writer_facts: tuple[WriterFact, ...]
    writers_complete: bool
    path_collisions: tuple[PathCollisionFact, ...]
    path_collisions_complete: bool
    branch_required_checks: tuple[CheckIdentity, ...]
    assessment_required_checks: tuple[CheckIdentity, ...]
    allowed_non_success_checks: tuple[CheckIdentity, ...]
    check_attempts: tuple[CheckAttempt, ...]
    checks_complete: bool
    required_approvals: int
    review_events: tuple[ReviewEvent, ...]
    reviews_complete: bool
    unresolved_required_threads: int
    current_source_evidence: CurrentSourceEvidence | None
    expected_source_owner_id: str
    expected_source_revision: str
    source_max_age_seconds: int
    current_base_required: bool
    production_proof_required: bool
    claimed_capability_id: str
    claimed_capability_state: CapabilityState
    expected_production_subject_id: str
    expected_production_owner_id: str
    expected_production_revision: str
    production_max_age_seconds: int
    production_proof: ProductionProof | None
    requested_merge_method: MergeMethod
    allowed_merge_methods: tuple[MergeMethod, ...]
    prior_effect_state: EffectState
    merged_effect_receipt: MergedEffectReceipt | None
    source_refs: tuple[str, ...]


@dataclasses.dataclass(frozen=True)
class ExpectedHeadRelease:
    repository: str
    repository_id: int
    pull_request_number: int
    protected_sha: str
    candidate_sha: str
    changed_paths: tuple[str, ...]
    merge_method: MergeMethod

    def to_dict(self) -> dict[str, object]:
        return {
            "repository": self.repository,
            "repository_id": self.repository_id,
            "pull_request_number": self.pull_request_number,
            "protected_sha": self.protected_sha,
            "candidate_sha": self.candidate_sha,
            "changed_paths": list(self.changed_paths),
            "merge_method": self.merge_method.value,
        }


@dataclasses.dataclass(frozen=True)
class GithubReleaseAssessment:
    schema: str
    verdict: AssessmentVerdict
    operation_key: str
    repository: str
    repository_id: int
    pull_request_number: int
    protected_ref: str
    protected_sha: str
    candidate_ref: str
    candidate_sha: str
    merge_context_state: MergeContextState
    path_state: PathState
    semantic_owner_state: SemanticOwnerAssessmentState
    carrier_state: CarrierAssessmentState
    writer_state: WriterAssessmentState
    check_state: CheckAssessmentState
    review_state: ReviewAssessmentState
    source_state: SourceAssessmentState
    production_state: ProductionAssessmentState
    completion_claim_state: CompletionClaimState
    effective_prior_effect_state: EffectState
    expected_head_merge_eligible: bool
    expected_head_release: ExpectedHeadRelease | None
    claimed_capability_id: str
    claimed_capability_state: CapabilityState
    issues: tuple[AssessmentIssue, ...]
    source_refs: tuple[str, ...]
    input_digest: str
    canonical_digest: str

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "verdict": self.verdict.value,
            "operation_key": self.operation_key,
            "repository": self.repository,
            "repository_id": self.repository_id,
            "pull_request_number": self.pull_request_number,
            "protected_ref": self.protected_ref,
            "protected_sha": self.protected_sha,
            "candidate_ref": self.candidate_ref,
            "candidate_sha": self.candidate_sha,
            "merge_context_state": self.merge_context_state.value,
            "path_state": self.path_state.value,
            "semantic_owner_state": self.semantic_owner_state.value,
            "carrier_state": self.carrier_state.value,
            "writer_state": self.writer_state.value,
            "check_state": self.check_state.value,
            "review_state": self.review_state.value,
            "source_state": self.source_state.value,
            "production_state": self.production_state.value,
            "completion_claim_state": self.completion_claim_state.value,
            "effective_prior_effect_state": self.effective_prior_effect_state.value,
            "expected_head_merge_eligible": self.expected_head_merge_eligible,
            "expected_head_release": (
                None if self.expected_head_release is None else self.expected_head_release.to_dict()
            ),
            "claimed_capability_id": self.claimed_capability_id,
            "claimed_capability_state": self.claimed_capability_state.value,
            "issues": [item.value for item in self.issues],
            "source_refs": list(self.source_refs),
            "input_digest": self.input_digest,
            "canonical_digest": self.canonical_digest,
        }


_REFUSE_ISSUES = frozenset(
    {
        AssessmentIssue.REPOSITORY_MISMATCH,
        AssessmentIssue.PULL_REQUEST_MISMATCH,
        AssessmentIssue.PROTECTED_REF_MOVED,
        AssessmentIssue.CANDIDATE_HEAD_MOVED,
        AssessmentIssue.BASE_REF_MISMATCH,
        AssessmentIssue.BASE_BRANCH_UNPROTECTED,
        AssessmentIssue.PR_STATE_REFUSED,
        AssessmentIssue.MERGE_CONFLICT,
        AssessmentIssue.EMPTY_RELEASE_DELTA,
        AssessmentIssue.EXPECTED_PATH_MISMATCH,
        AssessmentIssue.PATH_COLLISION,
        AssessmentIssue.SEMANTIC_OWNER_AMBIGUOUS,
        AssessmentIssue.SEMANTIC_OWNER_COLLISION,
        AssessmentIssue.OPERATION_CARRIER_CONFLICT,
        AssessmentIssue.CARRIER_WRITER_CONFLICT,
        AssessmentIssue.BRANCH_REQUIRED_CHECK_OMITTED,
        AssessmentIssue.CHECK_FAILED,
        AssessmentIssue.CHECK_CANCELLED,
        AssessmentIssue.CHECK_SKIPPED_NOT_ALLOWED,
        AssessmentIssue.CHECK_NEUTRAL_NOT_ALLOWED,
        AssessmentIssue.CHANGES_REQUESTED,
        AssessmentIssue.SOURCE_SUBJECT_MISMATCH,
        AssessmentIssue.SOURCE_OWNER_MISMATCH,
        AssessmentIssue.SOURCE_REVISION_MISMATCH,
        AssessmentIssue.SOURCE_FUTURE,
        AssessmentIssue.SOURCE_CONFLICT,
        AssessmentIssue.SOURCE_LAW_INCOMPATIBLE,
        AssessmentIssue.PRODUCTION_PROOF_INVALID,
        AssessmentIssue.PRODUCTION_PROOF_FUTURE,
        AssessmentIssue.COMPLETION_CLAIM_OVERSTATED,
        AssessmentIssue.MERGE_METHOD_REFUSED,
        AssessmentIssue.PRIOR_EFFECT_UNKNOWN,
        AssessmentIssue.PRIOR_EFFECT_APPLIED,
        AssessmentIssue.PRIOR_EFFECT_CONFLICT,
    }
)
_UNKNOWN_ISSUES = frozenset(
    {
        AssessmentIssue.PR_STATE_UNKNOWN,
        AssessmentIssue.MERGEABILITY_UNKNOWN,
        AssessmentIssue.BASE_OR_MERGE_CONTEXT_UNKNOWN,
        AssessmentIssue.PATH_COVERAGE_PARTIAL,
        AssessmentIssue.PATH_COLLISION_COVERAGE_PARTIAL,
        AssessmentIssue.SEMANTIC_OWNER_COVERAGE_PARTIAL,
        AssessmentIssue.OPERATION_CARRIER_NOT_FOUND,
        AssessmentIssue.CARRIER_COVERAGE_PARTIAL,
        AssessmentIssue.CARRIER_WRITER_NOT_FOUND,
        AssessmentIssue.WRITER_COVERAGE_PARTIAL,
        AssessmentIssue.CHECK_SUPERSEDED,
        AssessmentIssue.CHECK_COVERAGE_PARTIAL,
        AssessmentIssue.REVIEW_COVERAGE_PARTIAL,
        AssessmentIssue.SOURCE_EVIDENCE_MISSING,
        AssessmentIssue.SOURCE_INCOMPLETE,
        AssessmentIssue.SOURCE_STALE,
        AssessmentIssue.SOURCE_LAW_UNKNOWN,
        AssessmentIssue.PRODUCTION_PROOF_PARTIAL,
        AssessmentIssue.PRODUCTION_PROOF_UNKNOWN,
        AssessmentIssue.PRODUCTION_PROOF_STALE,
    }
)
_HELD_ISSUES = frozenset(
    {
        AssessmentIssue.PR_DRAFT,
        AssessmentIssue.CURRENT_BASE_REQUIRED,
        AssessmentIssue.CHECK_MISSING,
        AssessmentIssue.CHECK_PENDING,
        AssessmentIssue.REVIEW_REQUIRED,
        AssessmentIssue.UNRESOLVED_REVIEW_THREAD,
        AssessmentIssue.PRODUCTION_PROOF_MISSING,
    }
)


def _reject_secret(value: str, *, field: str) -> None:
    if any(pattern.search(value) for pattern in _SECRET_PATTERNS):
        raise AssessmentInputError(f"{field} contains secret-shaped text")


def _text(value: object, *, field: str, pattern: re.Pattern[str]) -> str:
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        raise AssessmentInputError(f"{field} is malformed")
    _reject_secret(value, field=field)
    return value


def _operation(value: object, *, field: str = "operation_key") -> str:
    return _text(value, field=field, pattern=_OPERATION_RE)


def _identifier(value: object, *, field: str) -> str:
    return _text(value, field=field, pattern=_IDENTIFIER_RE)


def _sha(value: object, *, field: str, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    return _text(value, field=field, pattern=_SHA_RE)


def _repository(value: object, *, field: str = "repository") -> str:
    return _text(value, field=field, pattern=_REPOSITORY_RE)


def _ref(value: object, *, field: str) -> str:
    token = _text(value, field=field, pattern=_REF_RE)
    if (
        token.startswith("refs/")
        or token == "HEAD"
        or token.startswith("-")
        or token.endswith(".")
        or token.endswith(".lock")
        or ".." in token
        or "//" in token
        or "@{" in token
    ):
        raise AssessmentInputError(f"{field} is not a canonical short branch ref")
    return token


def _source_ref(value: object, *, field: str) -> str:
    return _text(value, field=field, pattern=_SOURCE_REF_RE)


def _path(value: object, *, field: str) -> str:
    token = _text(value, field=field, pattern=_PATH_RE)
    if (
        token.startswith("/")
        or token.endswith("/")
        or "//" in token
        or "\\" in token
        or any(part in {"", ".", "..", ".git"} for part in token.split("/"))
    ):
        raise AssessmentInputError(f"{field} is not a canonical repository path")
    return token


def _positive_int(value: object, *, field: str, allow_zero: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise AssessmentInputError(f"{field} must be an integer")
    minimum = 0 if allow_zero else 1
    if value < minimum:
        raise AssessmentInputError(f"{field} is outside the reviewed bound")
    return value


def _bool(value: object, *, field: str) -> bool:
    if type(value) is not bool:
        raise AssessmentInputError(f"{field} must be boolean")
    return value


def _enum(value: object, expected: type[Enum], *, field: str) -> None:
    if not isinstance(value, expected):
        raise AssessmentInputError(f"{field} has the wrong enum type")


def _ensure_tuple(value: object, *, field: str, maximum: int) -> tuple[object, ...]:
    if not isinstance(value, tuple) or len(value) > maximum:
        raise AssessmentInputError(f"{field} must be a bounded tuple")
    return value


def _paths(value: object, *, field: str, allow_empty: bool = False) -> tuple[str, ...]:
    rows = _ensure_tuple(value, field=field, maximum=MAX_PATHS)
    normalized = tuple(_path(item, field=f"{field}[]") for item in rows)
    if not allow_empty and not normalized:
        raise AssessmentInputError(f"{field} must not be empty")
    if len(set(normalized)) != len(normalized):
        raise AssessmentInputError(f"{field} contains duplicates")
    return tuple(sorted(normalized))


def _path_contains(prefix: str, path: str) -> bool:
    return path == prefix or path.startswith(prefix + "/")


def _paths_overlap(left: str, right: str) -> bool:
    return _path_contains(left, right) or _path_contains(right, left)


def _validate_check_identity(value: CheckIdentity, *, field: str) -> tuple[str, int]:
    if not isinstance(value, CheckIdentity):
        raise AssessmentInputError(f"{field} has wrong type")
    context = _text(value.context, field=f"{field}.context", pattern=_CHECK_RE)
    if value.app_id is not None:
        _positive_int(value.app_id, field=f"{field}.app_id")
    return (context, -1 if value.app_id is None else value.app_id)


def _subject_payload(subject: EvidenceSubject) -> dict[str, object]:
    return {
        "repository": subject.repository,
        "repository_id": subject.repository_id,
        "pull_request_number": subject.pull_request_number,
        "protected_ref": subject.protected_ref,
        "protected_sha": subject.protected_sha,
        "base_ref": subject.base_ref,
        "base_sha": subject.base_sha,
        "candidate_ref": subject.candidate_ref,
        "candidate_sha": subject.candidate_sha,
        "changed_paths": list(sorted(subject.changed_paths)),
    }


def _validate_subject(subject: EvidenceSubject, *, field: str) -> None:
    if not isinstance(subject, EvidenceSubject):
        raise AssessmentInputError(f"{field} has wrong type")
    _repository(subject.repository, field=f"{field}.repository")
    _positive_int(subject.repository_id, field=f"{field}.repository_id")
    _positive_int(subject.pull_request_number, field=f"{field}.pull_request_number")
    _ref(subject.protected_ref, field=f"{field}.protected_ref")
    _sha(subject.protected_sha, field=f"{field}.protected_sha")
    _ref(subject.base_ref, field=f"{field}.base_ref")
    _sha(subject.base_sha, field=f"{field}.base_sha", optional=True)
    _ref(subject.candidate_ref, field=f"{field}.candidate_ref")
    _sha(subject.candidate_sha, field=f"{field}.candidate_sha")
    _paths(subject.changed_paths, field=f"{field}.changed_paths", allow_empty=True)


def _target_subject(target: PullRequestTarget) -> EvidenceSubject:
    return EvidenceSubject(
        repository=target.repository,
        repository_id=target.repository_id,
        pull_request_number=target.pull_request_number,
        protected_ref=target.protected_ref,
        protected_sha=target.protected_sha,
        base_ref=target.base_ref,
        base_sha=target.base_sha,
        candidate_ref=target.candidate_ref,
        candidate_sha=target.candidate_sha,
        changed_paths=tuple(sorted(target.changed_paths)),
    )


def _subject_matches(left: EvidenceSubject, right: EvidenceSubject) -> bool:
    return _subject_payload(left) == _subject_payload(right)


def _jsonable(value: object) -> Any:
    if dataclasses.is_dataclass(value):
        return {
            field.name: _jsonable(getattr(value, field.name))
            for field in dataclasses.fields(value)
        }
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    return value


def _validate_input(packet: AssessmentInput) -> dict[str, object]:
    if not isinstance(packet, AssessmentInput) or packet.schema != INPUT_SCHEMA:
        raise AssessmentInputError("input schema/type is unsupported")
    operation_key = _operation(packet.operation_key)
    observed_at = _positive_int(packet.observed_at, field="observed_at", allow_zero=True)

    expected = packet.expected_target
    if not isinstance(expected, ReleaseTargetExpectation):
        raise AssessmentInputError("expected_target has wrong type")
    _repository(expected.repository, field="expected_target.repository")
    _positive_int(expected.repository_id, field="expected_target.repository_id")
    _positive_int(expected.pull_request_number, field="expected_target.pull_request_number")
    _ref(expected.protected_ref, field="expected_target.protected_ref")
    _sha(expected.expected_protected_sha, field="expected_target.expected_protected_sha")
    _ref(expected.candidate_ref, field="expected_target.candidate_ref")
    _sha(expected.expected_head_sha, field="expected_target.expected_head_sha")

    target = packet.target
    if not isinstance(target, PullRequestTarget):
        raise AssessmentInputError("target has wrong type")
    _repository(target.repository, field="target.repository")
    _positive_int(target.repository_id, field="target.repository_id")
    _positive_int(target.pull_request_number, field="target.pull_request_number")
    _enum(target.state, PullRequestState, field="target.state")
    _bool(target.draft, field="target.draft")
    _bool(target.merged, field="target.merged")
    _sha(target.merged_commit_sha, field="target.merged_commit_sha", optional=True)
    _enum(target.mergeability, Mergeability, field="target.mergeability")
    _ref(target.protected_ref, field="target.protected_ref")
    _sha(target.protected_sha, field="target.protected_sha")
    _bool(target.protected_branch_protected, field="target.protected_branch_protected")
    _ref(target.base_ref, field="target.base_ref")
    _sha(target.base_sha, field="target.base_sha", optional=True)
    _ref(target.candidate_ref, field="target.candidate_ref")
    _sha(target.candidate_sha, field="target.candidate_sha")
    _sha(target.merge_base_sha, field="target.merge_base_sha", optional=True)
    if target.ahead_by is not None:
        _positive_int(target.ahead_by, field="target.ahead_by", allow_zero=True)
    if target.behind_by is not None:
        _positive_int(target.behind_by, field="target.behind_by", allow_zero=True)
    target_paths = _paths(target.changed_paths, field="target.changed_paths", allow_empty=True)
    _bool(target.changed_paths_complete, field="target.changed_paths_complete")
    if target.state is PullRequestState.MERGED and not target.merged:
        raise AssessmentInputError("merged PR state must set target.merged")
    if target.state is PullRequestState.OPEN and target.merged:
        raise AssessmentInputError("open PR cannot set target.merged")
    if target.merged and target.merged_commit_sha is None:
        raise AssessmentInputError("merged target requires merged_commit_sha")
    if not target.merged and target.merged_commit_sha is not None:
        raise AssessmentInputError("unmerged target cannot carry merged_commit_sha")

    expected_paths = _paths(packet.expected_paths, field="expected_paths")

    expectations = _ensure_tuple(
        packet.expected_semantic_owners,
        field="expected_semantic_owners",
        maximum=MAX_SEMANTIC_OWNERS,
    )
    expectation_rows: list[dict[str, object]] = []
    for index, item in enumerate(expectations):
        if not isinstance(item, SemanticOwnerExpectation):
            raise AssessmentInputError("expected_semantic_owners[] has wrong type")
        prefix = _path(item.path_prefix, field=f"expected_semantic_owners[{index}].path_prefix")
        _bool(item.no_owner_allowed, field=f"expected_semantic_owners[{index}].no_owner_allowed")
        owner = None
        if item.owner_id is not None:
            owner = _identifier(item.owner_id, field=f"expected_semantic_owners[{index}].owner_id")
        if (owner is None) != item.no_owner_allowed:
            raise AssessmentInputError(
                "semantic owner expectation must name an owner or explicitly allow no owner"
            )
        expectation_rows.append(
            {"path_prefix": prefix, "owner_id": owner, "no_owner_allowed": item.no_owner_allowed}
        )
    if len({(row["path_prefix"], row["owner_id"]) for row in expectation_rows}) != len(
        expectation_rows
    ):
        raise AssessmentInputError("expected_semantic_owners contains duplicates")

    owner_facts = _ensure_tuple(
        packet.semantic_owner_facts,
        field="semantic_owner_facts",
        maximum=MAX_SEMANTIC_OWNERS,
    )
    owner_fact_rows: list[dict[str, object]] = []
    for index, item in enumerate(owner_facts):
        if not isinstance(item, SemanticOwnerFact):
            raise AssessmentInputError("semantic_owner_facts[] has wrong type")
        owner_fact_rows.append(
            {
                "path_prefix": _path(item.path_prefix, field=f"semantic_owner_facts[{index}].path_prefix"),
                "owner_id": _identifier(item.owner_id, field=f"semantic_owner_facts[{index}].owner_id"),
                "operation_key": _operation(
                    item.operation_key, field=f"semantic_owner_facts[{index}].operation_key"
                ),
                "active": _bool(item.active, field=f"semantic_owner_facts[{index}].active"),
                "source_ref": _source_ref(
                    item.source_ref, field=f"semantic_owner_facts[{index}].source_ref"
                ),
            }
        )
    _bool(packet.semantic_owners_complete, field="semantic_owners_complete")

    carriers = _ensure_tuple(packet.carrier_facts, field="carrier_facts", maximum=MAX_CARRIERS)
    carrier_rows: list[dict[str, object]] = []
    for index, item in enumerate(carriers):
        if not isinstance(item, CarrierFact):
            raise AssessmentInputError("carrier_facts[] has wrong type")
        carrier_rows.append(
            {
                "carrier_ref": _source_ref(item.carrier_ref, field=f"carrier_facts[{index}].carrier_ref"),
                "operation_key": _operation(
                    item.operation_key, field=f"carrier_facts[{index}].operation_key"
                ),
                "repository": _repository(
                    item.repository, field=f"carrier_facts[{index}].repository"
                ),
                "repository_id": _positive_int(
                    item.repository_id, field=f"carrier_facts[{index}].repository_id"
                ),
                "pull_request_number": _positive_int(
                    item.pull_request_number,
                    field=f"carrier_facts[{index}].pull_request_number",
                ),
                "base_ref": _ref(item.base_ref, field=f"carrier_facts[{index}].base_ref"),
                "base_sha": _sha(
                    item.base_sha, field=f"carrier_facts[{index}].base_sha", optional=True
                ),
                "candidate_ref": _ref(
                    item.candidate_ref, field=f"carrier_facts[{index}].candidate_ref"
                ),
                "candidate_sha": _sha(
                    item.candidate_sha, field=f"carrier_facts[{index}].candidate_sha"
                ),
                "active": _bool(item.active, field=f"carrier_facts[{index}].active"),
                "source_ref": _source_ref(
                    item.source_ref, field=f"carrier_facts[{index}].source_ref"
                ),
            }
        )
    if len({row["carrier_ref"] for row in carrier_rows}) != len(carrier_rows):
        raise AssessmentInputError("carrier_facts contains duplicate carrier_ref")
    _bool(packet.carriers_complete, field="carriers_complete")

    expected_writer_id = _identifier(packet.expected_writer_id, field="expected_writer_id")
    writers = _ensure_tuple(packet.writer_facts, field="writer_facts", maximum=MAX_WRITERS)
    writer_rows: list[dict[str, object]] = []
    for index, item in enumerate(writers):
        if not isinstance(item, WriterFact):
            raise AssessmentInputError("writer_facts[] has wrong type")
        writer_rows.append(
            {
                "writer_id": _identifier(item.writer_id, field=f"writer_facts[{index}].writer_id"),
                "operation_key": _operation(
                    item.operation_key, field=f"writer_facts[{index}].operation_key"
                ),
                "repository_id": _positive_int(
                    item.repository_id, field=f"writer_facts[{index}].repository_id"
                ),
                "pull_request_number": _positive_int(
                    item.pull_request_number,
                    field=f"writer_facts[{index}].pull_request_number",
                ),
                "paths": list(
                    _paths(item.paths, field=f"writer_facts[{index}].paths", allow_empty=True)
                ),
                "active": _bool(item.active, field=f"writer_facts[{index}].active"),
                "source_ref": _source_ref(
                    item.source_ref, field=f"writer_facts[{index}].source_ref"
                ),
            }
        )
    if len({row["writer_id"] for row in writer_rows}) != len(writer_rows):
        raise AssessmentInputError("writer_facts contains duplicate writer_id")
    _bool(packet.writers_complete, field="writers_complete")

    collisions = _ensure_tuple(
        packet.path_collisions, field="path_collisions", maximum=MAX_COLLISIONS
    )
    collision_rows: list[dict[str, object]] = []
    for index, item in enumerate(collisions):
        if not isinstance(item, PathCollisionFact):
            raise AssessmentInputError("path_collisions[] has wrong type")
        collision_rows.append(
            {
                "path": _path(item.path, field=f"path_collisions[{index}].path"),
                "other_operation_key": _operation(
                    item.other_operation_key,
                    field=f"path_collisions[{index}].other_operation_key",
                ),
                "source_ref": _source_ref(
                    item.source_ref, field=f"path_collisions[{index}].source_ref"
                ),
            }
        )
    _bool(packet.path_collisions_complete, field="path_collisions_complete")

    check_groups: dict[str, list[dict[str, object]]] = {}
    identity_groups: dict[str, tuple[CheckIdentity, ...]] = {
        "branch_required_checks": packet.branch_required_checks,
        "assessment_required_checks": packet.assessment_required_checks,
        "allowed_non_success_checks": packet.allowed_non_success_checks,
    }
    for field, group in identity_groups.items():
        rows = _ensure_tuple(group, field=field, maximum=MAX_CHECK_IDENTITIES)
        rendered: list[dict[str, object]] = []
        keys: list[tuple[str, int]] = []
        for index, identity in enumerate(rows):
            key = _validate_check_identity(identity, field=f"{field}[{index}]")
            keys.append(key)
            rendered.append({"context": key[0], "app_id": None if key[1] == -1 else key[1]})
        if len(set(keys)) != len(keys):
            raise AssessmentInputError(f"{field} contains duplicate identities")
        check_groups[field] = sorted(rendered, key=lambda row: (str(row["context"]), row["app_id"] or -1))

    attempts = _ensure_tuple(packet.check_attempts, field="check_attempts", maximum=MAX_CHECK_ATTEMPTS)
    attempt_rows: list[dict[str, object]] = []
    attempt_keys: set[tuple[tuple[str, int], str, int, int]] = set()
    for index, item in enumerate(attempts):
        if not isinstance(item, CheckAttempt):
            raise AssessmentInputError("check_attempts[] has wrong type")
        identity_key = _validate_check_identity(item.identity, field=f"check_attempts[{index}].identity")
        head = _sha(item.head_sha, field=f"check_attempts[{index}].head_sha")
        attempt = _positive_int(item.attempt, field=f"check_attempts[{index}].attempt")
        sequence = _positive_int(item.sequence, field=f"check_attempts[{index}].sequence")
        _enum(item.status, CheckStatus, field=f"check_attempts[{index}].status")
        if item.conclusion is not None:
            _enum(item.conclusion, CheckConclusion, field=f"check_attempts[{index}].conclusion")
        if item.status is CheckStatus.COMPLETED and item.conclusion is None:
            raise AssessmentInputError("completed check attempt requires conclusion")
        if item.status is not CheckStatus.COMPLETED and item.conclusion is not None:
            raise AssessmentInputError("nonterminal check attempt cannot carry conclusion")
        unique = (identity_key, str(head), attempt, sequence)
        if unique in attempt_keys:
            raise AssessmentInputError("check_attempts contains duplicate attempt identity")
        attempt_keys.add(unique)
        attempt_rows.append(
            {
                "identity": {
                    "context": identity_key[0],
                    "app_id": None if identity_key[1] == -1 else identity_key[1],
                },
                "head_sha": head,
                "attempt": attempt,
                "sequence": sequence,
                "status": item.status.value,
                "conclusion": None if item.conclusion is None else item.conclusion.value,
                "applicable": _bool(item.applicable, field=f"check_attempts[{index}].applicable"),
                "superseded": _bool(item.superseded, field=f"check_attempts[{index}].superseded"),
                "source_ref": _source_ref(
                    item.source_ref, field=f"check_attempts[{index}].source_ref"
                ),
            }
        )
    _bool(packet.checks_complete, field="checks_complete")

    required_approvals = _positive_int(
        packet.required_approvals, field="required_approvals", allow_zero=True
    )
    reviews = _ensure_tuple(packet.review_events, field="review_events", maximum=MAX_REVIEWS)
    review_rows: list[dict[str, object]] = []
    review_keys: set[tuple[str, str, int]] = set()
    for index, item in enumerate(reviews):
        if not isinstance(item, ReviewEvent):
            raise AssessmentInputError("review_events[] has wrong type")
        reviewer = _identifier(item.reviewer_id, field=f"review_events[{index}].reviewer_id")
        head = _sha(item.head_sha, field=f"review_events[{index}].head_sha")
        sequence = _positive_int(item.sequence, field=f"review_events[{index}].sequence")
        _enum(item.state, ReviewState, field=f"review_events[{index}].state")
        key = (reviewer, str(head), sequence)
        if key in review_keys:
            raise AssessmentInputError("review_events contains duplicate sequence identity")
        review_keys.add(key)
        review_rows.append(
            {
                "reviewer_id": reviewer,
                "head_sha": head,
                "sequence": sequence,
                "state": item.state.value,
                "source_ref": _source_ref(
                    item.source_ref, field=f"review_events[{index}].source_ref"
                ),
            }
        )
    _bool(packet.reviews_complete, field="reviews_complete")
    unresolved_threads = _positive_int(
        packet.unresolved_required_threads,
        field="unresolved_required_threads",
        allow_zero=True,
    )

    source_evidence_payload: dict[str, object] | None = None
    if packet.current_source_evidence is not None:
        evidence = packet.current_source_evidence
        if not isinstance(evidence, CurrentSourceEvidence):
            raise AssessmentInputError("current_source_evidence has wrong type")
        _validate_subject(evidence.subject, field="current_source_evidence.subject")
        _enum(evidence.coverage, SourceCoverage, field="current_source_evidence.coverage")
        _enum(evidence.law_state, SourceLawState, field="current_source_evidence.law_state")
        source_evidence_payload = {
            "subject": _subject_payload(evidence.subject),
            "owner_id": _identifier(evidence.owner_id, field="current_source_evidence.owner_id"),
            "revision": _identifier(evidence.revision, field="current_source_evidence.revision"),
            "observed_at": _positive_int(
                evidence.observed_at,
                field="current_source_evidence.observed_at",
                allow_zero=True,
            ),
            "coverage": evidence.coverage.value,
            "law_state": evidence.law_state.value,
            "source_ref": _source_ref(
                evidence.source_ref, field="current_source_evidence.source_ref"
            ),
        }
    expected_source_owner_id = _identifier(
        packet.expected_source_owner_id, field="expected_source_owner_id"
    )
    expected_source_revision = _identifier(
        packet.expected_source_revision, field="expected_source_revision"
    )
    source_max_age_seconds = _positive_int(
        packet.source_max_age_seconds, field="source_max_age_seconds"
    )
    if source_max_age_seconds > MAX_EVIDENCE_AGE_SECONDS:
        raise AssessmentInputError("source_max_age_seconds exceeds reviewed bound")
    _bool(packet.current_base_required, field="current_base_required")

    _bool(packet.production_proof_required, field="production_proof_required")
    claimed_capability_id = _identifier(packet.claimed_capability_id, field="claimed_capability_id")
    _enum(packet.claimed_capability_state, CapabilityState, field="claimed_capability_state")
    expected_production_subject_id = _identifier(
        packet.expected_production_subject_id, field="expected_production_subject_id"
    )
    expected_production_owner_id = _identifier(
        packet.expected_production_owner_id, field="expected_production_owner_id"
    )
    expected_production_revision = _identifier(
        packet.expected_production_revision, field="expected_production_revision"
    )
    production_max_age_seconds = _positive_int(
        packet.production_max_age_seconds, field="production_max_age_seconds"
    )
    if production_max_age_seconds > MAX_EVIDENCE_AGE_SECONDS:
        raise AssessmentInputError("production_max_age_seconds exceeds reviewed bound")
    production_payload: dict[str, object] | None = None
    if packet.production_proof is not None:
        proof = packet.production_proof
        if not isinstance(proof, ProductionProof):
            raise AssessmentInputError("production_proof has wrong type")
        _validate_subject(proof.target_subject, field="production_proof.target_subject")
        _enum(proof.coverage, SourceCoverage, field="production_proof.coverage")
        _enum(proof.state, ProductionProofState, field="production_proof.state")
        production_payload = {
            "capability_id": _identifier(proof.capability_id, field="production_proof.capability_id"),
            "subject_id": _identifier(proof.subject_id, field="production_proof.subject_id"),
            "target_subject": _subject_payload(proof.target_subject),
            "owner_id": _identifier(proof.owner_id, field="production_proof.owner_id"),
            "revision": _identifier(proof.revision, field="production_proof.revision"),
            "observed_at": _positive_int(
                proof.observed_at, field="production_proof.observed_at", allow_zero=True
            ),
            "coverage": proof.coverage.value,
            "state": proof.state.value,
            "source_ref": _source_ref(proof.source_ref, field="production_proof.source_ref"),
        }

    _enum(packet.requested_merge_method, MergeMethod, field="requested_merge_method")
    allowed_merge_methods = _ensure_tuple(
        packet.allowed_merge_methods,
        field="allowed_merge_methods",
        maximum=len(MergeMethod),
    )
    if not allowed_merge_methods:
        raise AssessmentInputError("allowed_merge_methods must not be empty")
    for index, method in enumerate(allowed_merge_methods):
        _enum(method, MergeMethod, field=f"allowed_merge_methods[{index}]")
    if len(set(allowed_merge_methods)) != len(allowed_merge_methods):
        raise AssessmentInputError("allowed_merge_methods contains duplicates")

    _enum(packet.prior_effect_state, EffectState, field="prior_effect_state")
    receipt_payload: dict[str, object] | None = None
    if packet.merged_effect_receipt is not None:
        receipt = packet.merged_effect_receipt
        if not isinstance(receipt, MergedEffectReceipt):
            raise AssessmentInputError("merged_effect_receipt has wrong type")
        receipt_payload = {
            "repository": _repository(receipt.repository, field="merged_effect_receipt.repository"),
            "repository_id": _positive_int(
                receipt.repository_id, field="merged_effect_receipt.repository_id"
            ),
            "pull_request_number": _positive_int(
                receipt.pull_request_number,
                field="merged_effect_receipt.pull_request_number",
            ),
            "candidate_sha": _sha(
                receipt.candidate_sha, field="merged_effect_receipt.candidate_sha"
            ),
            "merged_commit_sha": _sha(
                receipt.merged_commit_sha, field="merged_effect_receipt.merged_commit_sha"
            ),
            "changed_paths": list(
                _paths(receipt.changed_paths, field="merged_effect_receipt.changed_paths")
            ),
            "source_ref": _source_ref(
                receipt.source_ref, field="merged_effect_receipt.source_ref"
            ),
        }

    source_refs = _ensure_tuple(packet.source_refs, field="source_refs", maximum=MAX_SOURCE_REFS)
    normalized_source_refs = tuple(
        _source_ref(item, field="source_refs[]") for item in source_refs
    )
    if len(set(normalized_source_refs)) != len(normalized_source_refs):
        raise AssessmentInputError("source_refs contains duplicates")

    payload: dict[str, object] = {
        "schema": INPUT_SCHEMA,
        "operation_key": operation_key,
        "observed_at": observed_at,
        "expected_target": _jsonable(expected),
        "target": {
            **_jsonable(target),
            "changed_paths": list(target_paths),
        },
        "expected_paths": list(expected_paths),
        "expected_semantic_owners": sorted(
            expectation_rows,
            key=lambda row: (str(row["path_prefix"]), str(row["owner_id"])),
        ),
        "semantic_owner_facts": sorted(
            owner_fact_rows,
            key=lambda row: (
                str(row["path_prefix"]),
                str(row["owner_id"]),
                str(row["operation_key"]),
                str(row["source_ref"]),
            ),
        ),
        "semantic_owners_complete": packet.semantic_owners_complete,
        "carrier_facts": sorted(
            carrier_rows,
            key=lambda row: (
                str(row["repository"]),
                int(row["repository_id"]),
                int(row["pull_request_number"]),
                str(row["candidate_ref"]),
                str(row["carrier_ref"]),
            ),
        ),
        "carriers_complete": packet.carriers_complete,
        "expected_writer_id": expected_writer_id,
        "writer_facts": sorted(writer_rows, key=lambda row: str(row["writer_id"])),
        "writers_complete": packet.writers_complete,
        "path_collisions": sorted(
            collision_rows,
            key=lambda row: (str(row["path"]), str(row["other_operation_key"])),
        ),
        "path_collisions_complete": packet.path_collisions_complete,
        **check_groups,
        "check_attempts": sorted(
            attempt_rows,
            key=lambda row: (
                str(row["identity"]["context"]),
                int(row["identity"]["app_id"] or -1),
                str(row["head_sha"]),
                int(row["attempt"]),
                int(row["sequence"]),
            ),
        ),
        "checks_complete": packet.checks_complete,
        "required_approvals": required_approvals,
        "review_events": sorted(
            review_rows,
            key=lambda row: (
                str(row["reviewer_id"]),
                str(row["head_sha"]),
                int(row["sequence"]),
            ),
        ),
        "reviews_complete": packet.reviews_complete,
        "unresolved_required_threads": unresolved_threads,
        "current_source_evidence": source_evidence_payload,
        "expected_source_owner_id": expected_source_owner_id,
        "expected_source_revision": expected_source_revision,
        "source_max_age_seconds": source_max_age_seconds,
        "current_base_required": packet.current_base_required,
        "production_proof_required": packet.production_proof_required,
        "claimed_capability_id": claimed_capability_id,
        "claimed_capability_state": packet.claimed_capability_state.value,
        "expected_production_subject_id": expected_production_subject_id,
        "expected_production_owner_id": expected_production_owner_id,
        "expected_production_revision": expected_production_revision,
        "production_max_age_seconds": production_max_age_seconds,
        "production_proof": production_payload,
        "requested_merge_method": packet.requested_merge_method.value,
        "allowed_merge_methods": sorted(method.value for method in allowed_merge_methods),
        "prior_effect_state": packet.prior_effect_state.value,
        "merged_effect_receipt": receipt_payload,
        "source_refs": sorted(normalized_source_refs),
    }
    return payload


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _add(issues: set[AssessmentIssue], issue: AssessmentIssue) -> None:
    issues.add(issue)


def _render_identity(identity: CheckIdentity) -> tuple[str, int]:
    return identity.key()


def _source_refs(packet: AssessmentInput) -> tuple[str, ...]:
    refs = set(packet.source_refs)
    for item in packet.semantic_owner_facts:
        refs.add(item.source_ref)
    for item in packet.carrier_facts:
        refs.add(item.source_ref)
    for item in packet.writer_facts:
        refs.add(item.source_ref)
    for item in packet.path_collisions:
        refs.add(item.source_ref)
    for item in packet.check_attempts:
        refs.add(item.source_ref)
    for item in packet.review_events:
        refs.add(item.source_ref)
    if packet.current_source_evidence is not None:
        refs.add(packet.current_source_evidence.source_ref)
    if packet.production_proof is not None:
        refs.add(packet.production_proof.source_ref)
    if packet.merged_effect_receipt is not None:
        refs.add(packet.merged_effect_receipt.source_ref)
    return tuple(sorted(refs))


def _assess_source(
    packet: AssessmentInput,
    issues: set[AssessmentIssue],
) -> tuple[SourceAssessmentState, bool]:
    evidence = packet.current_source_evidence
    if evidence is None:
        _add(issues, AssessmentIssue.SOURCE_EVIDENCE_MISSING)
        return SourceAssessmentState.UNKNOWN, False

    expected_subject = _target_subject(packet.target)
    if not _subject_matches(evidence.subject, expected_subject):
        _add(issues, AssessmentIssue.SOURCE_SUBJECT_MISMATCH)
    if evidence.owner_id != packet.expected_source_owner_id:
        _add(issues, AssessmentIssue.SOURCE_OWNER_MISMATCH)
    if evidence.revision != packet.expected_source_revision:
        _add(issues, AssessmentIssue.SOURCE_REVISION_MISMATCH)
    if evidence.observed_at > packet.observed_at:
        _add(issues, AssessmentIssue.SOURCE_FUTURE)
    elif packet.observed_at - evidence.observed_at > packet.source_max_age_seconds:
        _add(issues, AssessmentIssue.SOURCE_STALE)

    if evidence.coverage is SourceCoverage.CONFLICT:
        _add(issues, AssessmentIssue.SOURCE_CONFLICT)
    elif evidence.coverage is SourceCoverage.INCOMPLETE:
        _add(issues, AssessmentIssue.SOURCE_INCOMPLETE)
    elif evidence.coverage is SourceCoverage.STALE:
        _add(issues, AssessmentIssue.SOURCE_STALE)

    if evidence.law_state is SourceLawState.INCOMPATIBLE:
        _add(issues, AssessmentIssue.SOURCE_LAW_INCOMPATIBLE)
    elif evidence.law_state is SourceLawState.UNKNOWN:
        _add(issues, AssessmentIssue.SOURCE_LAW_UNKNOWN)

    current = not any(
        issue
        in {
            AssessmentIssue.SOURCE_SUBJECT_MISMATCH,
            AssessmentIssue.SOURCE_OWNER_MISMATCH,
            AssessmentIssue.SOURCE_REVISION_MISMATCH,
            AssessmentIssue.SOURCE_FUTURE,
            AssessmentIssue.SOURCE_STALE,
            AssessmentIssue.SOURCE_CONFLICT,
            AssessmentIssue.SOURCE_INCOMPLETE,
            AssessmentIssue.SOURCE_LAW_INCOMPATIBLE,
            AssessmentIssue.SOURCE_LAW_UNKNOWN,
        }
        for issue in issues
    )
    if current:
        return SourceAssessmentState.CURRENT, True
    if any(
        item in issues
        for item in {
            AssessmentIssue.SOURCE_SUBJECT_MISMATCH,
            AssessmentIssue.SOURCE_OWNER_MISMATCH,
            AssessmentIssue.SOURCE_REVISION_MISMATCH,
            AssessmentIssue.SOURCE_FUTURE,
            AssessmentIssue.SOURCE_CONFLICT,
            AssessmentIssue.SOURCE_LAW_INCOMPATIBLE,
        }
    ):
        return SourceAssessmentState.INCOMPATIBLE, False
    return SourceAssessmentState.UNKNOWN, False


def _assess_target(
    packet: AssessmentInput,
    issues: set[AssessmentIssue],
    *,
    source_current: bool,
) -> MergeContextState:
    expected = packet.expected_target
    target = packet.target
    if target.repository != expected.repository or target.repository_id != expected.repository_id:
        _add(issues, AssessmentIssue.REPOSITORY_MISMATCH)
    if target.pull_request_number != expected.pull_request_number:
        _add(issues, AssessmentIssue.PULL_REQUEST_MISMATCH)
    if target.protected_ref != expected.protected_ref:
        _add(issues, AssessmentIssue.BASE_REF_MISMATCH)
    if target.protected_sha != expected.expected_protected_sha:
        _add(issues, AssessmentIssue.PROTECTED_REF_MOVED)
    if target.candidate_ref != expected.candidate_ref:
        _add(issues, AssessmentIssue.PULL_REQUEST_MISMATCH)
    if target.candidate_sha != expected.expected_head_sha:
        _add(issues, AssessmentIssue.CANDIDATE_HEAD_MOVED)
    if target.base_ref != expected.protected_ref:
        _add(issues, AssessmentIssue.BASE_REF_MISMATCH)
    if not target.protected_branch_protected:
        _add(issues, AssessmentIssue.BASE_BRANCH_UNPROTECTED)

    if target.state is PullRequestState.UNKNOWN:
        _add(issues, AssessmentIssue.PR_STATE_UNKNOWN)
    elif target.state is not PullRequestState.OPEN:
        _add(issues, AssessmentIssue.PR_STATE_REFUSED)
    if target.draft:
        _add(issues, AssessmentIssue.PR_DRAFT)
    if target.mergeability is Mergeability.CONFLICTING:
        _add(issues, AssessmentIssue.MERGE_CONFLICT)
    elif target.mergeability is Mergeability.UNKNOWN:
        _add(issues, AssessmentIssue.MERGEABILITY_UNKNOWN)

    if target.ahead_by is None or target.behind_by is None or target.merge_base_sha is None:
        _add(issues, AssessmentIssue.BASE_OR_MERGE_CONTEXT_UNKNOWN)
        return MergeContextState.UNKNOWN
    if target.ahead_by <= 0 or not target.changed_paths:
        _add(issues, AssessmentIssue.EMPTY_RELEASE_DELTA)
    if target.behind_by == 0:
        if target.base_sha != target.protected_sha or target.merge_base_sha != target.protected_sha:
            _add(issues, AssessmentIssue.BASE_OR_MERGE_CONTEXT_UNKNOWN)
            return MergeContextState.UNKNOWN
        return MergeContextState.CURRENT
    if packet.current_base_required:
        _add(issues, AssessmentIssue.CURRENT_BASE_REQUIRED)
        return MergeContextState.HELD
    if source_current:
        return MergeContextState.BEHIND_COMPATIBLE
    _add(issues, AssessmentIssue.BASE_OR_MERGE_CONTEXT_UNKNOWN)
    return MergeContextState.UNKNOWN


def _assess_paths(packet: AssessmentInput, issues: set[AssessmentIssue]) -> PathState:
    actual = tuple(sorted(packet.target.changed_paths))
    expected = tuple(sorted(packet.expected_paths))
    if not packet.target.changed_paths_complete:
        _add(issues, AssessmentIssue.PATH_COVERAGE_PARTIAL)
    if actual != expected:
        _add(issues, AssessmentIssue.EXPECTED_PATH_MISMATCH)
        return PathState.MISMATCH
    if not packet.target.changed_paths_complete:
        return PathState.UNKNOWN
    return PathState.EXACT


def _assess_semantic_owners(
    packet: AssessmentInput,
    issues: set[AssessmentIssue],
) -> SemanticOwnerAssessmentState:
    unknown = False
    conflict = False
    if not packet.semantic_owners_complete:
        _add(issues, AssessmentIssue.SEMANTIC_OWNER_COVERAGE_PARTIAL)
        unknown = True
    for path in sorted(packet.target.changed_paths):
        expectations = [
            item for item in packet.expected_semantic_owners if _path_contains(item.path_prefix, path)
        ]
        if len(expectations) == 0:
            _add(issues, AssessmentIssue.SEMANTIC_OWNER_COVERAGE_PARTIAL)
            unknown = True
            continue
        if len(expectations) > 1:
            _add(issues, AssessmentIssue.SEMANTIC_OWNER_AMBIGUOUS)
            conflict = True
            continue
        expectation = expectations[0]
        facts = [
            item
            for item in packet.semantic_owner_facts
            if item.active and _path_contains(item.path_prefix, path)
        ]
        if expectation.no_owner_allowed:
            if facts:
                _add(issues, AssessmentIssue.SEMANTIC_OWNER_COLLISION)
                conflict = True
            continue
        matching = [
            item
            for item in facts
            if item.owner_id == expectation.owner_id
            and item.operation_key == packet.operation_key
        ]
        foreign = [item for item in facts if item not in matching]
        if foreign or len(matching) > 1:
            _add(issues, AssessmentIssue.SEMANTIC_OWNER_COLLISION)
            conflict = True
        elif len(matching) == 0:
            _add(issues, AssessmentIssue.SEMANTIC_OWNER_COVERAGE_PARTIAL)
            unknown = True
    if conflict:
        return SemanticOwnerAssessmentState.CONFLICT
    if unknown:
        return SemanticOwnerAssessmentState.UNKNOWN
    return SemanticOwnerAssessmentState.EXACT


def _carrier_touches_target(item: CarrierFact, target: PullRequestTarget) -> bool:
    return (
        item.active
        and item.repository_id == target.repository_id
        and (
            item.pull_request_number == target.pull_request_number
            or item.candidate_ref == target.candidate_ref
        )
    )


def _carrier_exact(item: CarrierFact, packet: AssessmentInput) -> bool:
    target = packet.target
    return (
        item.operation_key == packet.operation_key
        and item.repository == target.repository
        and item.repository_id == target.repository_id
        and item.pull_request_number == target.pull_request_number
        and item.base_ref == target.base_ref
        and item.base_sha == target.base_sha
        and item.candidate_ref == target.candidate_ref
        and item.candidate_sha == target.candidate_sha
    )


def _assess_carriers(
    packet: AssessmentInput,
    issues: set[AssessmentIssue],
) -> CarrierAssessmentState:
    touching = [item for item in packet.carrier_facts if _carrier_touches_target(item, packet.target)]
    foreign = [item for item in touching if item.operation_key != packet.operation_key]
    exact = [item for item in touching if _carrier_exact(item, packet)]
    if foreign or len(exact) > 1:
        _add(issues, AssessmentIssue.OPERATION_CARRIER_CONFLICT)
        return CarrierAssessmentState.CONFLICT
    if not packet.carriers_complete:
        _add(issues, AssessmentIssue.CARRIER_COVERAGE_PARTIAL)
    if len(exact) != 1:
        _add(issues, AssessmentIssue.OPERATION_CARRIER_NOT_FOUND)
        return CarrierAssessmentState.UNKNOWN
    if not packet.carriers_complete:
        return CarrierAssessmentState.UNKNOWN
    return CarrierAssessmentState.EXACT


def _writer_touches_target(item: WriterFact, packet: AssessmentInput) -> bool:
    return (
        item.active
        and item.repository_id == packet.target.repository_id
        and item.pull_request_number == packet.target.pull_request_number
        and any(
            _paths_overlap(writer_path, candidate_path)
            for writer_path in item.paths
            for candidate_path in packet.target.changed_paths
        )
    )


def _assess_writers(
    packet: AssessmentInput,
    issues: set[AssessmentIssue],
) -> WriterAssessmentState:
    active = [item for item in packet.writer_facts if _writer_touches_target(item, packet)]
    if len(active) > 1:
        _add(issues, AssessmentIssue.CARRIER_WRITER_CONFLICT)
        return WriterAssessmentState.CONFLICT
    if not packet.writers_complete:
        _add(issues, AssessmentIssue.WRITER_COVERAGE_PARTIAL)
    if len(active) != 1:
        _add(issues, AssessmentIssue.CARRIER_WRITER_NOT_FOUND)
        return WriterAssessmentState.UNKNOWN
    writer = active[0]
    covers_all = all(
        any(_path_contains(writer_path, candidate_path) for writer_path in writer.paths)
        for candidate_path in packet.target.changed_paths
    )
    if (
        writer.writer_id != packet.expected_writer_id
        or writer.operation_key != packet.operation_key
        or not covers_all
    ):
        _add(issues, AssessmentIssue.CARRIER_WRITER_CONFLICT)
        return WriterAssessmentState.CONFLICT
    if not packet.writers_complete:
        return WriterAssessmentState.UNKNOWN
    return WriterAssessmentState.EXACT


def _assess_collisions(packet: AssessmentInput, issues: set[AssessmentIssue]) -> None:
    if not packet.path_collisions_complete:
        _add(issues, AssessmentIssue.PATH_COLLISION_COVERAGE_PARTIAL)
    for collision in packet.path_collisions:
        if collision.other_operation_key == packet.operation_key:
            continue
        if any(_paths_overlap(collision.path, path) for path in packet.target.changed_paths):
            _add(issues, AssessmentIssue.PATH_COLLISION)


def _assess_checks(
    packet: AssessmentInput,
    issues: set[AssessmentIssue],
) -> CheckAssessmentState:
    branch = {_render_identity(item) for item in packet.branch_required_checks}
    required = {_render_identity(item) for item in packet.assessment_required_checks}
    allowed_non_success = {_render_identity(item) for item in packet.allowed_non_success_checks}
    if not branch.issubset(required):
        _add(issues, AssessmentIssue.BRANCH_REQUIRED_CHECK_OMITTED)
    required |= branch
    unknown = not packet.checks_complete
    pending = False
    failed = False
    if not packet.checks_complete:
        _add(issues, AssessmentIssue.CHECK_COVERAGE_PARTIAL)

    for identity in sorted(required):
        attempts = [
            item
            for item in packet.check_attempts
            if _render_identity(item.identity) == identity
            and item.head_sha == packet.target.candidate_sha
        ]
        if not attempts:
            if packet.checks_complete:
                _add(issues, AssessmentIssue.CHECK_MISSING)
                pending = True
            else:
                unknown = True
            continue
        latest = max(attempts, key=lambda item: (item.attempt, item.sequence))
        if latest.superseded:
            _add(issues, AssessmentIssue.CHECK_SUPERSEDED)
            unknown = True
            continue
        if latest.status in {CheckStatus.QUEUED, CheckStatus.IN_PROGRESS}:
            _add(issues, AssessmentIssue.CHECK_PENDING)
            pending = True
            continue
        conclusion = latest.conclusion
        if conclusion is CheckConclusion.SUCCESS:
            continue
        if conclusion is CheckConclusion.SKIPPED:
            if identity in allowed_non_success and not latest.applicable:
                continue
            _add(issues, AssessmentIssue.CHECK_SKIPPED_NOT_ALLOWED)
            failed = True
            continue
        if conclusion is CheckConclusion.NEUTRAL:
            if identity in allowed_non_success and not latest.applicable:
                continue
            _add(issues, AssessmentIssue.CHECK_NEUTRAL_NOT_ALLOWED)
            failed = True
            continue
        if conclusion is CheckConclusion.CANCELLED:
            _add(issues, AssessmentIssue.CHECK_CANCELLED)
            failed = True
            continue
        if conclusion is CheckConclusion.UNKNOWN:
            _add(issues, AssessmentIssue.CHECK_COVERAGE_PARTIAL)
            unknown = True
            continue
        _add(issues, AssessmentIssue.CHECK_FAILED)
        failed = True

    if failed:
        return CheckAssessmentState.FAILED
    if unknown:
        return CheckAssessmentState.UNKNOWN
    if pending:
        return CheckAssessmentState.PENDING
    return CheckAssessmentState.GREEN


def _assess_reviews(
    packet: AssessmentInput,
    issues: set[AssessmentIssue],
) -> ReviewAssessmentState:
    effective: dict[str, ReviewEvent] = {}
    for event in packet.review_events:
        if event.head_sha != packet.target.candidate_sha:
            continue
        current = effective.get(event.reviewer_id)
        if current is None or event.sequence > current.sequence:
            effective[event.reviewer_id] = event
    if not packet.reviews_complete:
        _add(issues, AssessmentIssue.REVIEW_COVERAGE_PARTIAL)
    if any(item.state is ReviewState.CHANGES_REQUESTED for item in effective.values()):
        _add(issues, AssessmentIssue.CHANGES_REQUESTED)
    approvals = sum(item.state is ReviewState.APPROVED for item in effective.values())
    if approvals < packet.required_approvals:
        _add(issues, AssessmentIssue.REVIEW_REQUIRED)
    if packet.unresolved_required_threads > 0:
        _add(issues, AssessmentIssue.UNRESOLVED_REVIEW_THREAD)
    if AssessmentIssue.CHANGES_REQUESTED in issues:
        return ReviewAssessmentState.BLOCKED
    if not packet.reviews_complete:
        return ReviewAssessmentState.UNKNOWN
    if (
        AssessmentIssue.REVIEW_REQUIRED in issues
        or AssessmentIssue.UNRESOLVED_REVIEW_THREAD in issues
    ):
        return ReviewAssessmentState.PENDING
    return ReviewAssessmentState.SATISFIED


def _assess_production(
    packet: AssessmentInput,
    issues: set[AssessmentIssue],
) -> tuple[ProductionAssessmentState, CompletionClaimState]:
    required = packet.production_proof_required or (
        packet.claimed_capability_state is CapabilityState.PROVEN_LIVE
    )
    proof = packet.production_proof
    if proof is None:
        if required:
            _add(issues, AssessmentIssue.PRODUCTION_PROOF_MISSING)
            if packet.claimed_capability_state is CapabilityState.PROVEN_LIVE:
                _add(issues, AssessmentIssue.COMPLETION_CLAIM_OVERSTATED)
                return ProductionAssessmentState.MISSING, CompletionClaimState.OVERSTATED
            return ProductionAssessmentState.MISSING, CompletionClaimState.UNKNOWN
        return ProductionAssessmentState.NOT_REQUIRED, CompletionClaimState.VALID

    exact = True
    if proof.capability_id != packet.claimed_capability_id:
        exact = False
    if proof.subject_id != packet.expected_production_subject_id:
        exact = False
    if proof.owner_id != packet.expected_production_owner_id:
        exact = False
    if proof.revision != packet.expected_production_revision:
        exact = False
    if not _subject_matches(proof.target_subject, _target_subject(packet.target)):
        exact = False
    if not exact:
        _add(issues, AssessmentIssue.PRODUCTION_PROOF_INVALID)
    if proof.observed_at > packet.observed_at:
        _add(issues, AssessmentIssue.PRODUCTION_PROOF_FUTURE)
    elif packet.observed_at - proof.observed_at > packet.production_max_age_seconds:
        _add(issues, AssessmentIssue.PRODUCTION_PROOF_STALE)
    if proof.coverage is SourceCoverage.CONFLICT:
        _add(issues, AssessmentIssue.PRODUCTION_PROOF_INVALID)
    elif proof.coverage is not SourceCoverage.COMPLETE:
        _add(issues, AssessmentIssue.PRODUCTION_PROOF_PARTIAL)
    if proof.state is ProductionProofState.MISSING:
        _add(issues, AssessmentIssue.PRODUCTION_PROOF_MISSING)
    elif proof.state is ProductionProofState.PARTIAL:
        _add(issues, AssessmentIssue.PRODUCTION_PROOF_PARTIAL)
    elif proof.state is ProductionProofState.UNKNOWN:
        _add(issues, AssessmentIssue.PRODUCTION_PROOF_UNKNOWN)

    present = not any(
        item in issues
        for item in {
            AssessmentIssue.PRODUCTION_PROOF_INVALID,
            AssessmentIssue.PRODUCTION_PROOF_FUTURE,
            AssessmentIssue.PRODUCTION_PROOF_STALE,
            AssessmentIssue.PRODUCTION_PROOF_PARTIAL,
            AssessmentIssue.PRODUCTION_PROOF_UNKNOWN,
            AssessmentIssue.PRODUCTION_PROOF_MISSING,
        }
    ) and proof.state is ProductionProofState.PRESENT

    if packet.claimed_capability_state is CapabilityState.PROVEN_LIVE and not present:
        _add(issues, AssessmentIssue.COMPLETION_CLAIM_OVERSTATED)
        return (
            ProductionAssessmentState.UNKNOWN
            if proof.state is not ProductionProofState.MISSING
            else ProductionAssessmentState.MISSING,
            CompletionClaimState.OVERSTATED,
        )
    if present:
        return ProductionAssessmentState.PRESENT, CompletionClaimState.VALID
    if proof.state is ProductionProofState.MISSING:
        return ProductionAssessmentState.MISSING, CompletionClaimState.UNKNOWN
    return ProductionAssessmentState.UNKNOWN, CompletionClaimState.UNKNOWN


def _receipt_matches(packet: AssessmentInput, receipt: MergedEffectReceipt) -> bool:
    target = packet.target
    return (
        target.merged
        and target.merged_commit_sha is not None
        and receipt.repository == target.repository
        and receipt.repository_id == target.repository_id
        and receipt.pull_request_number == target.pull_request_number
        and receipt.candidate_sha == target.candidate_sha
        and receipt.merged_commit_sha == target.merged_commit_sha
        and tuple(sorted(receipt.changed_paths)) == tuple(sorted(target.changed_paths))
    )


def _assess_effect(packet: AssessmentInput, issues: set[AssessmentIssue]) -> EffectState:
    effective = packet.prior_effect_state
    receipt = packet.merged_effect_receipt
    if packet.prior_effect_state is EffectState.EFFECT_UNKNOWN:
        if receipt is not None and _receipt_matches(packet, receipt):
            effective = EffectState.APPLIED
            _add(issues, AssessmentIssue.PRIOR_EFFECT_APPLIED)
        else:
            _add(issues, AssessmentIssue.PRIOR_EFFECT_UNKNOWN)
    elif packet.prior_effect_state is EffectState.APPLIED:
        _add(issues, AssessmentIssue.PRIOR_EFFECT_APPLIED)
    elif packet.target.merged:
        if receipt is not None and _receipt_matches(packet, receipt):
            effective = EffectState.APPLIED
            _add(issues, AssessmentIssue.PRIOR_EFFECT_APPLIED)
        else:
            effective = EffectState.EFFECT_UNKNOWN
            _add(issues, AssessmentIssue.PRIOR_EFFECT_CONFLICT)
    elif receipt is not None:
        _add(issues, AssessmentIssue.PRIOR_EFFECT_CONFLICT)
    return effective


def _verdict(issues: set[AssessmentIssue]) -> AssessmentVerdict:
    if issues & _REFUSE_ISSUES:
        return AssessmentVerdict.REFUSED
    if issues & _UNKNOWN_ISSUES:
        return AssessmentVerdict.UNKNOWN
    if issues & _HELD_ISSUES:
        return AssessmentVerdict.HELD
    return AssessmentVerdict.ELIGIBLE


def assess_github_release(packet: AssessmentInput) -> GithubReleaseAssessment:
    """Classify one immutable release packet without performing an effect."""

    normalized = _validate_input(packet)
    input_digest = _digest(normalized)
    issues: set[AssessmentIssue] = set()

    source_state, source_current = _assess_source(packet, issues)
    merge_context_state = _assess_target(packet, issues, source_current=source_current)
    path_state = _assess_paths(packet, issues)
    semantic_owner_state = _assess_semantic_owners(packet, issues)
    carrier_state = _assess_carriers(packet, issues)
    writer_state = _assess_writers(packet, issues)
    _assess_collisions(packet, issues)
    check_state = _assess_checks(packet, issues)
    review_state = _assess_reviews(packet, issues)
    production_state, completion_claim_state = _assess_production(packet, issues)
    effective_prior_effect_state = _assess_effect(packet, issues)

    if packet.requested_merge_method not in set(packet.allowed_merge_methods):
        _add(issues, AssessmentIssue.MERGE_METHOD_REFUSED)

    verdict = _verdict(issues)
    release: ExpectedHeadRelease | None = None
    if verdict is AssessmentVerdict.ELIGIBLE:
        release = ExpectedHeadRelease(
            repository=packet.target.repository,
            repository_id=packet.target.repository_id,
            pull_request_number=packet.target.pull_request_number,
            protected_sha=packet.target.protected_sha,
            candidate_sha=packet.target.candidate_sha,
            changed_paths=tuple(sorted(packet.target.changed_paths)),
            merge_method=packet.requested_merge_method,
        )

    ordered_issues = tuple(sorted(issues, key=lambda item: item.value))
    refs = _source_refs(packet)
    output_without_digest = {
        "schema": OUTPUT_SCHEMA,
        "verdict": verdict.value,
        "operation_key": packet.operation_key,
        "repository": packet.target.repository,
        "repository_id": packet.target.repository_id,
        "pull_request_number": packet.target.pull_request_number,
        "protected_ref": packet.target.protected_ref,
        "protected_sha": packet.target.protected_sha,
        "candidate_ref": packet.target.candidate_ref,
        "candidate_sha": packet.target.candidate_sha,
        "merge_context_state": merge_context_state.value,
        "path_state": path_state.value,
        "semantic_owner_state": semantic_owner_state.value,
        "carrier_state": carrier_state.value,
        "writer_state": writer_state.value,
        "check_state": check_state.value,
        "review_state": review_state.value,
        "source_state": source_state.value,
        "production_state": production_state.value,
        "completion_claim_state": completion_claim_state.value,
        "effective_prior_effect_state": effective_prior_effect_state.value,
        "expected_head_merge_eligible": verdict is AssessmentVerdict.ELIGIBLE,
        "expected_head_release": None if release is None else release.to_dict(),
        "claimed_capability_id": packet.claimed_capability_id,
        "claimed_capability_state": packet.claimed_capability_state.value,
        "issues": [item.value for item in ordered_issues],
        "source_refs": list(refs),
        "input_digest": input_digest,
    }
    return GithubReleaseAssessment(
        schema=OUTPUT_SCHEMA,
        verdict=verdict,
        operation_key=packet.operation_key,
        repository=packet.target.repository,
        repository_id=packet.target.repository_id,
        pull_request_number=packet.target.pull_request_number,
        protected_ref=packet.target.protected_ref,
        protected_sha=packet.target.protected_sha,
        candidate_ref=packet.target.candidate_ref,
        candidate_sha=packet.target.candidate_sha,
        merge_context_state=merge_context_state,
        path_state=path_state,
        semantic_owner_state=semantic_owner_state,
        carrier_state=carrier_state,
        writer_state=writer_state,
        check_state=check_state,
        review_state=review_state,
        source_state=source_state,
        production_state=production_state,
        completion_claim_state=completion_claim_state,
        effective_prior_effect_state=effective_prior_effect_state,
        expected_head_merge_eligible=verdict is AssessmentVerdict.ELIGIBLE,
        expected_head_release=release,
        claimed_capability_id=packet.claimed_capability_id,
        claimed_capability_state=packet.claimed_capability_state,
        issues=ordered_issues,
        source_refs=refs,
        input_digest=input_digest,
        canonical_digest=_digest(output_without_digest),
    )


__all__ = [
    "INPUT_SCHEMA",
    "OUTPUT_SCHEMA",
    "MAX_EVIDENCE_AGE_SECONDS",
    "AssessmentInput",
    "AssessmentInputError",
    "AssessmentIssue",
    "AssessmentVerdict",
    "CapabilityState",
    "CarrierAssessmentState",
    "CarrierFact",
    "CheckAssessmentState",
    "CheckAttempt",
    "CheckConclusion",
    "CheckIdentity",
    "CheckStatus",
    "CompletionClaimState",
    "CurrentSourceEvidence",
    "EffectState",
    "EvidenceSubject",
    "ExpectedHeadRelease",
    "GithubReleaseAssessment",
    "MergeContextState",
    "MergeMethod",
    "Mergeability",
    "MergedEffectReceipt",
    "PathCollisionFact",
    "PathState",
    "ProductionAssessmentState",
    "ProductionProof",
    "ProductionProofState",
    "PullRequestState",
    "PullRequestTarget",
    "ReleaseTargetExpectation",
    "ReviewAssessmentState",
    "ReviewEvent",
    "ReviewState",
    "SemanticOwnerAssessmentState",
    "SemanticOwnerExpectation",
    "SemanticOwnerFact",
    "SourceAssessmentState",
    "SourceCoverage",
    "SourceLawState",
    "WriterAssessmentState",
    "WriterFact",
    "assess_github_release",
]
