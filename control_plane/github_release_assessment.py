"""Pure, deterministic GitHub release and collision assessment.

The caller supplies immutable, source-owned facts. This module performs no I/O,
network access, mutation, credential selection, clock access, subprocess work,
filesystem discovery, or persistence. It owns only classification semantics for
``mastermind.github_release_assessment.v1``.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import re
from enum import Enum
from typing import Any, Iterable, Mapping


INPUT_SCHEMA = "mastermind.github_release_assessment.input.v1"
OUTPUT_SCHEMA = "mastermind.github_release_assessment.v1"

MAX_PATHS = 256
MAX_SEMANTIC_OWNERS = 128
MAX_CARRIERS = 32
MAX_WRITERS = 128
MAX_COLLISIONS = 128
MAX_CHECK_NAMES = 128
MAX_CHECK_FACTS = 256
MAX_REVIEWS = 128
MAX_SOURCE_REFS = 128
MAX_FACT_PATHS = 128

_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_OPERATION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,191}$")
_REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$")
_REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,255}$")
_IDENTIFIER_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
_CHECK_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._:/()\[\]-]{0,127}$")
_SOURCE_REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9:._/@#-]{0,255}$")
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
    """The supplied immutable assessment packet is malformed or unsafe."""


class AssessmentVerdict(str, Enum):
    ELIGIBLE = "ELIGIBLE"
    HELD = "HELD"
    REFUSED = "REFUSED"
    UNKNOWN = "UNKNOWN"


class AssessmentIssue(str, Enum):
    INPUT_SCHEMA_INVALID = "INPUT_SCHEMA_INVALID"
    SOURCE_INCOMPLETE = "SOURCE_INCOMPLETE"
    SOURCE_STALE = "SOURCE_STALE"
    SOURCE_CONFLICT = "SOURCE_CONFLICT"
    PROTECTED_REF_MOVED = "PROTECTED_REF_MOVED"
    CANDIDATE_HEAD_MOVED = "CANDIDATE_HEAD_MOVED"
    BASE_OR_MERGE_CONTEXT_UNKNOWN = "BASE_OR_MERGE_CONTEXT_UNKNOWN"
    CURRENT_BASE_REQUIRED = "CURRENT_BASE_REQUIRED"
    EXPECTED_PATH_MISMATCH = "EXPECTED_PATH_MISMATCH"
    PATH_COLLISION = "PATH_COLLISION"
    SEMANTIC_OWNER_COLLISION = "SEMANTIC_OWNER_COLLISION"
    SEMANTIC_OWNER_COVERAGE_PARTIAL = "SEMANTIC_OWNER_COVERAGE_PARTIAL"
    OPERATION_CARRIER_CONFLICT = "OPERATION_CARRIER_CONFLICT"
    CARRIER_COVERAGE_PARTIAL = "CARRIER_COVERAGE_PARTIAL"
    CARRIER_WRITER_CONFLICT = "CARRIER_WRITER_CONFLICT"
    WRITER_COVERAGE_PARTIAL = "WRITER_COVERAGE_PARTIAL"
    CHECK_PENDING = "CHECK_PENDING"
    CHECK_FAILED = "CHECK_FAILED"
    CHECK_CANCELLED = "CHECK_CANCELLED"
    CHECK_SUPERSEDED = "CHECK_SUPERSEDED"
    CHECK_COVERAGE_PARTIAL = "CHECK_COVERAGE_PARTIAL"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    CHANGES_REQUESTED = "CHANGES_REQUESTED"
    UNRESOLVED_REVIEW_THREAD = "UNRESOLVED_REVIEW_THREAD"
    REVIEW_COVERAGE_PARTIAL = "REVIEW_COVERAGE_PARTIAL"
    SOURCE_LAW_INCOMPATIBLE = "SOURCE_LAW_INCOMPATIBLE"
    PRODUCTION_PROOF_MISSING = "PRODUCTION_PROOF_MISSING"
    PRODUCTION_PROOF_PARTIAL = "PRODUCTION_PROOF_PARTIAL"
    PRODUCTION_PROOF_UNKNOWN = "PRODUCTION_PROOF_UNKNOWN"
    COMPLETION_CLAIM_OVERSTATED = "COMPLETION_CLAIM_OVERSTATED"
    MERGE_METHOD_REFUSED = "MERGE_METHOD_REFUSED"
    PRIOR_EFFECT_UNKNOWN = "PRIOR_EFFECT_UNKNOWN"
    PRIOR_EFFECT_APPLIED = "PRIOR_EFFECT_APPLIED"


class CapabilityState(str, Enum):
    PROVEN_LIVE = "PROVEN_LIVE"
    BUILT_NOT_PROVEN = "BUILT_NOT_PROVEN"
    PARTIAL = "PARTIAL"
    DARK_OR_DISCONNECTED = "DARK_OR_DISCONNECTED"
    BROKEN = "BROKEN"
    SPEC_ONLY = "SPEC_ONLY"
    NOT_BUILT = "NOT_BUILT"
    REJECTED_BY_DESIGN = "REJECTED_BY_DESIGN"


class PrivilegeClass(str, Enum):
    R0_OBSERVE = "R0_OBSERVE"
    W1_ROUTINE = "W1_ROUTINE"
    W2_CONSEQUENTIAL = "W2_CONSEQUENTIAL"
    A3_ADMIN = "A3_ADMIN"


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
    NOT_REQUIRED = "NOT_REQUIRED"
    PRESENT = "PRESENT"
    MISSING = "MISSING"
    PARTIAL = "PARTIAL"
    UNKNOWN = "UNKNOWN"


class PathState(str, Enum):
    EXACT = "EXACT"
    MISMATCH = "MISMATCH"
    COLLISION = "COLLISION"


class SemanticCollisionState(str, Enum):
    CLEAR = "CLEAR"
    COLLISION = "COLLISION"
    UNKNOWN = "UNKNOWN"


class CarrierAssessmentState(str, Enum):
    EXACT = "EXACT"
    CONFLICT = "CONFLICT"
    UNKNOWN = "UNKNOWN"


class WriterAssessmentState(str, Enum):
    CLEAR = "CLEAR"
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


class MergeContextState(str, Enum):
    CURRENT = "CURRENT"
    BEHIND_COMPATIBLE = "BEHIND_COMPATIBLE"
    UNKNOWN = "UNKNOWN"


class CompletionClaimState(str, Enum):
    VALID = "VALID"
    OVERSTATED = "OVERSTATED"
    UNKNOWN = "UNKNOWN"


@dataclasses.dataclass(frozen=True)
class SemanticOwnerExpectation:
    path_prefix: str
    owner_id: str


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
    branch: str
    candidate_sha: str
    active: bool
    source_ref: str


@dataclasses.dataclass(frozen=True)
class WriterFact:
    writer_id: str
    operation_key: str
    paths: tuple[str, ...]
    active: bool
    source_ref: str


@dataclasses.dataclass(frozen=True)
class PathCollisionFact:
    path: str
    other_operation_key: str
    source_ref: str


@dataclasses.dataclass(frozen=True)
class CheckFact:
    name: str
    head_sha: str
    attempt: int
    required: bool
    status: CheckStatus
    conclusion: CheckConclusion | None
    superseded: bool
    source_ref: str


@dataclasses.dataclass(frozen=True)
class ReviewFact:
    reviewer: str
    head_sha: str
    state: ReviewState
    required: bool
    source_ref: str


@dataclasses.dataclass(frozen=True)
class AssessmentInput:
    schema: str
    operation_key: str
    repository: str
    protected_ref: str
    protected_sha: str
    expected_protected_sha: str
    candidate_branch: str
    candidate_sha: str
    base_ref: str
    base_sha: str | None
    merge_base_sha: str | None
    ahead_by: int | None
    behind_by: int | None
    expected_head_sha: str
    expected_paths: tuple[str, ...]
    actual_paths: tuple[str, ...]
    expected_semantic_owners: tuple[SemanticOwnerExpectation, ...]
    current_semantic_owners: tuple[SemanticOwnerFact, ...]
    semantic_owners_complete: bool
    carriers: tuple[CarrierFact, ...]
    carriers_complete: bool
    writers: tuple[WriterFact, ...]
    writers_complete: bool
    path_collisions: tuple[PathCollisionFact, ...]
    required_checks: tuple[str, ...]
    checks: tuple[CheckFact, ...]
    checks_complete: bool
    required_approvals: int
    reviews: tuple[ReviewFact, ...]
    unresolved_required_threads: int
    reviews_complete: bool
    source_coverage: SourceCoverage
    source_law_state: SourceLawState
    current_base_required: bool
    production_proof_required: bool
    production_proof_state: ProductionProofState
    claimed_capability_state: CapabilityState
    requested_merge_method: MergeMethod
    allowed_merge_methods: tuple[MergeMethod, ...]
    prior_effect_state: EffectState
    source_refs: tuple[str, ...]


@dataclasses.dataclass(frozen=True)
class GithubReleaseAssessment:
    schema: str
    verdict: AssessmentVerdict
    operation_key: str
    repository: str
    protected_ref: str
    protected_sha: str
    candidate_branch: str
    candidate_sha: str
    expected_head_sha: str
    base_sha: str | None
    merge_base_sha: str | None
    ahead_by: int | None
    behind_by: int | None
    merge_context_state: MergeContextState
    path_state: PathState
    semantic_collision_state: SemanticCollisionState
    carrier_state: CarrierAssessmentState
    writer_state: WriterAssessmentState
    check_state: CheckAssessmentState
    review_state: ReviewAssessmentState
    source_law_state: SourceLawState
    production_proof_state: ProductionProofState
    completion_claim_state: CompletionClaimState
    requested_merge_method: MergeMethod
    prior_effect_state: EffectState
    expected_head_merge_eligible: bool
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
            "protected_ref": self.protected_ref,
            "protected_sha": self.protected_sha,
            "candidate_branch": self.candidate_branch,
            "candidate_sha": self.candidate_sha,
            "expected_head_sha": self.expected_head_sha,
            "base_sha": self.base_sha,
            "merge_base_sha": self.merge_base_sha,
            "ahead_by": self.ahead_by,
            "behind_by": self.behind_by,
            "merge_context_state": self.merge_context_state.value,
            "path_state": self.path_state.value,
            "semantic_collision_state": self.semantic_collision_state.value,
            "carrier_state": self.carrier_state.value,
            "writer_state": self.writer_state.value,
            "check_state": self.check_state.value,
            "review_state": self.review_state.value,
            "source_law_state": self.source_law_state.value,
            "production_proof_state": self.production_proof_state.value,
            "completion_claim_state": self.completion_claim_state.value,
            "requested_merge_method": self.requested_merge_method.value,
            "prior_effect_state": self.prior_effect_state.value,
            "expected_head_merge_eligible": self.expected_head_merge_eligible,
            "claimed_capability_state": self.claimed_capability_state.value,
            "issues": [issue.value for issue in self.issues],
            "source_refs": list(self.source_refs),
            "input_digest": self.input_digest,
            "canonical_digest": self.canonical_digest,
        }


def _reject_secret(value: str, *, field: str) -> None:
    if any(pattern.search(value) for pattern in _SECRET_PATTERNS):
        raise AssessmentInputError(f"{field} contains secret-shaped text")


def _bounded_text(value: object, *, field: str, pattern: re.Pattern[str], message: str,
                  lower: bool = False) -> str:
    if not isinstance(value, str):
        raise AssessmentInputError(f"{field} must be a string")
    token = value.strip()
    _reject_secret(token, field=field)
    normalized = token.lower() if lower else token
    if pattern.fullmatch(normalized) is None:
        raise AssessmentInputError(f"{field} {message}")
    return normalized


def _operation(value: object, *, field: str) -> str:
    return _bounded_text(value, field=field, pattern=_OPERATION_RE,
                         message="must be a bounded operation identifier")


def _identifier(value: object, *, field: str) -> str:
    return _bounded_text(value, field=field, pattern=_IDENTIFIER_RE,
                         message="must be a bounded lowercase identifier", lower=True)


def _sha(value: object, *, field: str, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    return _bounded_text(value, field=field, pattern=_SHA_RE,
                         message="must be a lowercase 40-character Git SHA", lower=True)


def _repository(value: object) -> str:
    return _bounded_text(value, field="repository", pattern=_REPOSITORY_RE,
                         message="must be owner/name")


def _ref(value: object, *, field: str) -> str:
    token = _bounded_text(value, field=field, pattern=_REF_RE,
                          message="must be a bounded Git ref")
    if token.startswith("/") or ".." in token.split("/"):
        raise AssessmentInputError(f"{field} must be a bounded Git ref")
    return token


def _source_ref(value: object, *, field: str) -> str:
    return _bounded_text(value, field=field, pattern=_SOURCE_REF_RE,
                         message="must be a bounded source reference")


def _path(value: object, *, field: str) -> str:
    if not isinstance(value, str):
        raise AssessmentInputError(f"{field} must be a relative repository path")
    token = value.strip().strip("/")
    _reject_secret(token, field=field)
    original = value.strip()
    parts = token.split("/") if token else []
    if (
        not token
        or original.startswith("/")
        or "\\" in original
        or any(part in {"", ".", ".."} for part in parts)
        or len(token) > 512
    ):
        raise AssessmentInputError(f"{field} must be a relative repository path")
    return token


def _nonnegative_int(value: object, *, field: str, optional: bool = False,
                     maximum: int = 1_000_000) -> int | None:
    if value is None and optional:
        return None
    if type(value) is not int or value < 0 or value > maximum:
        raise AssessmentInputError(f"{field} must be a bounded non-negative integer")
    return value


def _boolean(value: object, *, field: str) -> bool:
    if type(value) is not bool:
        raise AssessmentInputError(f"{field} must be boolean")
    return value


def _bounded_tuple(value: object, *, field: str, maximum: int) -> tuple[Any, ...]:
    if not isinstance(value, tuple):
        raise AssessmentInputError(f"{field} must be an immutable tuple")
    if len(value) > maximum:
        raise AssessmentInputError(f"{field} must contain at most {maximum} items")
    return value


def _unique_sorted(values: Iterable[str], *, field: str) -> tuple[str, ...]:
    rows = list(values)
    if len(rows) != len(set(rows)):
        raise AssessmentInputError(f"{field} contains duplicate values")
    return tuple(sorted(rows))


def _path_overlap(left: str, right: str) -> bool:
    return left == right or left.startswith(right + "/") or right.startswith(left + "/")


def _primitive(value: object) -> object:
    if dataclasses.is_dataclass(value):
        return {
            field.name: _primitive(getattr(value, field.name))
            for field in dataclasses.fields(value)
        }
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, tuple):
        return [_primitive(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): _primitive(item) for key, item in sorted(value.items(), key=lambda row: str(row[0]))}
    return value


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _normalize_expectation(value: SemanticOwnerExpectation) -> SemanticOwnerExpectation:
    if not isinstance(value, SemanticOwnerExpectation):
        raise AssessmentInputError("expected_semantic_owners must contain SemanticOwnerExpectation")
    return SemanticOwnerExpectation(
        path_prefix=_path(value.path_prefix, field="semantic expectation path_prefix"),
        owner_id=_identifier(value.owner_id, field="semantic expectation owner_id"),
    )


def _normalize_owner(value: SemanticOwnerFact) -> SemanticOwnerFact:
    if not isinstance(value, SemanticOwnerFact):
        raise AssessmentInputError("current_semantic_owners must contain SemanticOwnerFact")
    return SemanticOwnerFact(
        path_prefix=_path(value.path_prefix, field="semantic owner path_prefix"),
        owner_id=_identifier(value.owner_id, field="semantic owner owner_id"),
        operation_key=_operation(value.operation_key, field="semantic owner operation_key"),
        active=_boolean(value.active, field="semantic owner active"),
        source_ref=_source_ref(value.source_ref, field="semantic owner source_ref"),
    )


def _normalize_carrier(value: CarrierFact) -> CarrierFact:
    if not isinstance(value, CarrierFact):
        raise AssessmentInputError("carriers must contain CarrierFact")
    return CarrierFact(
        carrier_ref=_source_ref(value.carrier_ref, field="carrier_ref"),
        operation_key=_operation(value.operation_key, field="carrier operation_key"),
        branch=_ref(value.branch, field="carrier branch"),
        candidate_sha=_sha(value.candidate_sha, field="carrier candidate_sha") or "",
        active=_boolean(value.active, field="carrier active"),
        source_ref=_source_ref(value.source_ref, field="carrier source_ref"),
    )


def _normalize_writer(value: WriterFact) -> WriterFact:
    if not isinstance(value, WriterFact):
        raise AssessmentInputError("writers must contain WriterFact")
    raw_paths = _bounded_tuple(value.paths, field="writer paths", maximum=MAX_FACT_PATHS)
    paths = _unique_sorted((_path(path, field="writer path") for path in raw_paths), field="writer paths")
    return WriterFact(
        writer_id=_identifier(value.writer_id, field="writer_id"),
        operation_key=_operation(value.operation_key, field="writer operation_key"),
        paths=paths,
        active=_boolean(value.active, field="writer active"),
        source_ref=_source_ref(value.source_ref, field="writer source_ref"),
    )


def _normalize_collision(value: PathCollisionFact) -> PathCollisionFact:
    if not isinstance(value, PathCollisionFact):
        raise AssessmentInputError("path_collisions must contain PathCollisionFact")
    return PathCollisionFact(
        path=_path(value.path, field="collision path"),
        other_operation_key=_operation(value.other_operation_key, field="collision operation_key"),
        source_ref=_source_ref(value.source_ref, field="collision source_ref"),
    )


def _normalize_check(value: CheckFact) -> CheckFact:
    if not isinstance(value, CheckFact):
        raise AssessmentInputError("checks must contain CheckFact")
    name = _bounded_text(value.name, field="check name", pattern=_CHECK_NAME_RE,
                         message="must be a bounded check name")
    if not isinstance(value.status, CheckStatus):
        raise AssessmentInputError("check status is unsupported")
    if value.conclusion is not None and not isinstance(value.conclusion, CheckConclusion):
        raise AssessmentInputError("check conclusion is unsupported")
    if value.status is not CheckStatus.COMPLETED and value.conclusion is not None:
        raise AssessmentInputError("non-terminal check cannot have a conclusion")
    return CheckFact(
        name=name,
        head_sha=_sha(value.head_sha, field="check head_sha") or "",
        attempt=_nonnegative_int(value.attempt, field="check attempt", maximum=10_000) or 0,
        required=_boolean(value.required, field="check required"),
        status=value.status,
        conclusion=value.conclusion,
        superseded=_boolean(value.superseded, field="check superseded"),
        source_ref=_source_ref(value.source_ref, field="check source_ref"),
    )


def _normalize_review(value: ReviewFact) -> ReviewFact:
    if not isinstance(value, ReviewFact):
        raise AssessmentInputError("reviews must contain ReviewFact")
    if not isinstance(value.state, ReviewState):
        raise AssessmentInputError("review state is unsupported")
    return ReviewFact(
        reviewer=_identifier(value.reviewer, field="reviewer"),
        head_sha=_sha(value.head_sha, field="review head_sha") or "",
        state=value.state,
        required=_boolean(value.required, field="review required"),
        source_ref=_source_ref(value.source_ref, field="review source_ref"),
    )


def _dedupe(rows: Iterable[Any], *, key, label: str) -> tuple[Any, ...]:
    seen: dict[object, Any] = {}
    for row in rows:
        identity = key(row)
        existing = seen.get(identity)
        if existing is not None:
            if _primitive(existing) != _primitive(row):
                raise AssessmentInputError(f"duplicate {label} identity conflicts")
            continue
        seen[identity] = row
    return tuple(seen[identity] for identity in sorted(seen, key=lambda item: str(item)))


def _normalize_input(value: AssessmentInput) -> AssessmentInput:
    if not isinstance(value, AssessmentInput):
        raise AssessmentInputError("assessment input must be AssessmentInput")
    if value.schema != INPUT_SCHEMA:
        raise AssessmentInputError("schema is unsupported")
    if not isinstance(value.source_coverage, SourceCoverage):
        raise AssessmentInputError("source_coverage is unsupported")
    if not isinstance(value.source_law_state, SourceLawState):
        raise AssessmentInputError("source_law_state is unsupported")
    if not isinstance(value.production_proof_state, ProductionProofState):
        raise AssessmentInputError("production_proof_state is unsupported")
    if not isinstance(value.claimed_capability_state, CapabilityState):
        raise AssessmentInputError("claimed_capability_state is unsupported")
    if not isinstance(value.requested_merge_method, MergeMethod):
        raise AssessmentInputError("requested_merge_method is unsupported")
    if not isinstance(value.prior_effect_state, EffectState):
        raise AssessmentInputError("prior_effect_state is unsupported")

    expected_paths_raw = _bounded_tuple(value.expected_paths, field="expected_paths", maximum=MAX_PATHS)
    actual_paths_raw = _bounded_tuple(value.actual_paths, field="actual_paths", maximum=MAX_PATHS)
    expected_paths = _unique_sorted((_path(path, field="expected path") for path in expected_paths_raw), field="expected_paths")
    actual_paths = _unique_sorted((_path(path, field="actual path") for path in actual_paths_raw), field="actual_paths")

    expectation_rows = _bounded_tuple(value.expected_semantic_owners, field="expected_semantic_owners", maximum=MAX_SEMANTIC_OWNERS)
    owner_rows = _bounded_tuple(value.current_semantic_owners, field="current_semantic_owners", maximum=MAX_SEMANTIC_OWNERS)
    expectations = _dedupe((_normalize_expectation(row) for row in expectation_rows), key=lambda row: (row.path_prefix, row.owner_id), label="semantic expectation")
    owners = _dedupe((_normalize_owner(row) for row in owner_rows), key=lambda row: (row.path_prefix, row.owner_id, row.operation_key, row.source_ref), label="semantic owner")

    carrier_rows = _bounded_tuple(value.carriers, field="carriers", maximum=MAX_CARRIERS)
    carriers = _dedupe((_normalize_carrier(row) for row in carrier_rows), key=lambda row: row.carrier_ref, label="carrier")
    writer_rows = _bounded_tuple(value.writers, field="writers", maximum=MAX_WRITERS)
    writers = _dedupe((_normalize_writer(row) for row in writer_rows), key=lambda row: (row.writer_id, row.operation_key, row.source_ref), label="writer")
    collision_rows = _bounded_tuple(value.path_collisions, field="path_collisions", maximum=MAX_COLLISIONS)
    collisions = _dedupe((_normalize_collision(row) for row in collision_rows), key=lambda row: (row.path, row.other_operation_key, row.source_ref), label="path collision")

    required_checks_raw = _bounded_tuple(value.required_checks, field="required_checks", maximum=MAX_CHECK_NAMES)
    required_checks = _unique_sorted((_bounded_text(name, field="required check", pattern=_CHECK_NAME_RE, message="must be a bounded check name") for name in required_checks_raw), field="required_checks")
    check_rows = _bounded_tuple(value.checks, field="checks", maximum=MAX_CHECK_FACTS)
    checks = _dedupe((_normalize_check(row) for row in check_rows), key=lambda row: (row.name, row.head_sha, row.attempt), label="check")
    review_rows = _bounded_tuple(value.reviews, field="reviews", maximum=MAX_REVIEWS)
    reviews = _dedupe((_normalize_review(row) for row in review_rows), key=lambda row: (row.reviewer, row.head_sha), label="review")

    methods_raw = _bounded_tuple(value.allowed_merge_methods, field="allowed_merge_methods", maximum=3)
    methods: list[MergeMethod] = []
    for method in methods_raw:
        if not isinstance(method, MergeMethod):
            raise AssessmentInputError("allowed_merge_methods contains unsupported method")
        if method in methods:
            raise AssessmentInputError("allowed_merge_methods contains duplicate values")
        methods.append(method)
    if not methods:
        raise AssessmentInputError("allowed_merge_methods must be non-empty")

    source_rows = _bounded_tuple(value.source_refs, field="source_refs", maximum=MAX_SOURCE_REFS)
    source_refs = _unique_sorted((_source_ref(row, field="source_ref") for row in source_rows), field="source_refs")
    if not source_refs:
        raise AssessmentInputError("source_refs must be non-empty")

    required_approvals = _nonnegative_int(value.required_approvals, field="required_approvals", maximum=64)
    unresolved_threads = _nonnegative_int(value.unresolved_required_threads, field="unresolved_required_threads", maximum=10_000)
    assert required_approvals is not None and unresolved_threads is not None
    production_required = _boolean(value.production_proof_required, field="production_proof_required")
    if production_required and value.production_proof_state is ProductionProofState.NOT_REQUIRED:
        raise AssessmentInputError("required production proof cannot be NOT_REQUIRED")

    return AssessmentInput(
        schema=INPUT_SCHEMA,
        operation_key=_operation(value.operation_key, field="operation_key"),
        repository=_repository(value.repository),
        protected_ref=_ref(value.protected_ref, field="protected_ref"),
        protected_sha=_sha(value.protected_sha, field="protected_sha") or "",
        expected_protected_sha=_sha(value.expected_protected_sha, field="expected_protected_sha") or "",
        candidate_branch=_ref(value.candidate_branch, field="candidate_branch"),
        candidate_sha=_sha(value.candidate_sha, field="candidate_sha") or "",
        base_ref=_ref(value.base_ref, field="base_ref"),
        base_sha=_sha(value.base_sha, field="base_sha", optional=True),
        merge_base_sha=_sha(value.merge_base_sha, field="merge_base_sha", optional=True),
        ahead_by=_nonnegative_int(value.ahead_by, field="ahead_by", optional=True),
        behind_by=_nonnegative_int(value.behind_by, field="behind_by", optional=True),
        expected_head_sha=_sha(value.expected_head_sha, field="expected_head_sha") or "",
        expected_paths=expected_paths,
        actual_paths=actual_paths,
        expected_semantic_owners=expectations,
        current_semantic_owners=owners,
        semantic_owners_complete=_boolean(value.semantic_owners_complete, field="semantic_owners_complete"),
        carriers=carriers,
        carriers_complete=_boolean(value.carriers_complete, field="carriers_complete"),
        writers=writers,
        writers_complete=_boolean(value.writers_complete, field="writers_complete"),
        path_collisions=collisions,
        required_checks=required_checks,
        checks=checks,
        checks_complete=_boolean(value.checks_complete, field="checks_complete"),
        required_approvals=required_approvals,
        reviews=reviews,
        unresolved_required_threads=unresolved_threads,
        reviews_complete=_boolean(value.reviews_complete, field="reviews_complete"),
        source_coverage=value.source_coverage,
        source_law_state=value.source_law_state,
        current_base_required=_boolean(value.current_base_required, field="current_base_required"),
        production_proof_required=production_required,
        production_proof_state=value.production_proof_state,
        claimed_capability_state=value.claimed_capability_state,
        requested_merge_method=value.requested_merge_method,
        allowed_merge_methods=tuple(sorted(methods, key=lambda item: item.value)),
        prior_effect_state=value.prior_effect_state,
        source_refs=source_refs,
    )


def _all_source_refs(value: AssessmentInput) -> tuple[str, ...]:
    refs = set(value.source_refs)
    refs.update(row.source_ref for row in value.current_semantic_owners)
    refs.update(row.source_ref for row in value.carriers)
    refs.update(row.source_ref for row in value.writers)
    refs.update(row.source_ref for row in value.path_collisions)
    refs.update(row.source_ref for row in value.checks)
    refs.update(row.source_ref for row in value.reviews)
    return tuple(sorted(refs))


def assess_github_release(input_packet: AssessmentInput) -> GithubReleaseAssessment:
    """Assess one immutable release packet without acquiring or mutating state."""

    value = _normalize_input(input_packet)
    issues: set[AssessmentIssue] = set()
    refused: set[AssessmentIssue] = set()
    unknown: set[AssessmentIssue] = set()
    held: set[AssessmentIssue] = set()

    def add(issue: AssessmentIssue, disposition: AssessmentVerdict | None) -> None:
        issues.add(issue)
        if disposition is AssessmentVerdict.REFUSED:
            refused.add(issue)
        elif disposition is AssessmentVerdict.UNKNOWN:
            unknown.add(issue)
        elif disposition is AssessmentVerdict.HELD:
            held.add(issue)

    if value.source_coverage is SourceCoverage.INCOMPLETE:
        add(AssessmentIssue.SOURCE_INCOMPLETE, AssessmentVerdict.UNKNOWN)
    elif value.source_coverage is SourceCoverage.STALE:
        add(AssessmentIssue.SOURCE_STALE, AssessmentVerdict.UNKNOWN)
    elif value.source_coverage is SourceCoverage.CONFLICT:
        add(AssessmentIssue.SOURCE_CONFLICT, AssessmentVerdict.UNKNOWN)

    if value.source_law_state is SourceLawState.INCOMPATIBLE:
        add(AssessmentIssue.SOURCE_LAW_INCOMPATIBLE, AssessmentVerdict.REFUSED)
    elif value.source_law_state is SourceLawState.UNKNOWN:
        add(AssessmentIssue.SOURCE_INCOMPLETE, AssessmentVerdict.UNKNOWN)

    protected_moved = value.protected_sha != value.expected_protected_sha
    if protected_moved:
        if value.source_law_state is SourceLawState.INCOMPATIBLE:
            add(AssessmentIssue.PROTECTED_REF_MOVED, AssessmentVerdict.REFUSED)
        elif value.source_law_state is SourceLawState.UNKNOWN:
            add(AssessmentIssue.PROTECTED_REF_MOVED, AssessmentVerdict.UNKNOWN)
        else:
            add(AssessmentIssue.PROTECTED_REF_MOVED, None)

    if value.candidate_sha != value.expected_head_sha:
        add(AssessmentIssue.CANDIDATE_HEAD_MOVED, AssessmentVerdict.REFUSED)

    merge_context_unknown = any(item is None for item in (value.base_sha, value.merge_base_sha, value.ahead_by, value.behind_by))
    if merge_context_unknown:
        merge_context_state = MergeContextState.UNKNOWN
        add(AssessmentIssue.BASE_OR_MERGE_CONTEXT_UNKNOWN, AssessmentVerdict.UNKNOWN)
    else:
        assert value.base_sha is not None
        assert value.merge_base_sha is not None
        assert value.behind_by is not None
        current_base_missing = value.base_sha != value.protected_sha or value.merge_base_sha != value.protected_sha or value.behind_by > 0
        if current_base_missing:
            merge_context_state = MergeContextState.BEHIND_COMPATIBLE
            if value.current_base_required:
                if value.source_law_state is SourceLawState.COMPATIBLE:
                    add(AssessmentIssue.CURRENT_BASE_REQUIRED, AssessmentVerdict.HELD)
                elif value.source_law_state is SourceLawState.UNKNOWN:
                    add(AssessmentIssue.CURRENT_BASE_REQUIRED, AssessmentVerdict.UNKNOWN)
                else:
                    add(AssessmentIssue.CURRENT_BASE_REQUIRED, AssessmentVerdict.REFUSED)
        else:
            merge_context_state = MergeContextState.CURRENT

    if value.expected_paths != value.actual_paths:
        path_state = PathState.MISMATCH
        add(AssessmentIssue.EXPECTED_PATH_MISMATCH, AssessmentVerdict.REFUSED)
    else:
        path_state = PathState.EXACT
    if value.path_collisions:
        path_state = PathState.COLLISION
        add(AssessmentIssue.PATH_COLLISION, AssessmentVerdict.REFUSED)

    semantic_state = SemanticCollisionState.CLEAR
    if not value.semantic_owners_complete:
        semantic_state = SemanticCollisionState.UNKNOWN
        add(AssessmentIssue.SEMANTIC_OWNER_COVERAGE_PARTIAL, AssessmentVerdict.UNKNOWN)
    for expected in value.expected_semantic_owners:
        observed = tuple(row for row in value.current_semantic_owners if row.active and _path_overlap(expected.path_prefix, row.path_prefix))
        if any(row.owner_id != expected.owner_id for row in observed):
            semantic_state = SemanticCollisionState.COLLISION
            add(AssessmentIssue.SEMANTIC_OWNER_COLLISION, AssessmentVerdict.REFUSED)
        elif not observed:
            semantic_state = SemanticCollisionState.UNKNOWN
            add(AssessmentIssue.SEMANTIC_OWNER_COVERAGE_PARTIAL, AssessmentVerdict.UNKNOWN)

    active_carriers = tuple(row for row in value.carriers if row.active and row.operation_key == value.operation_key)
    exact_carriers = tuple(row for row in active_carriers if row.branch == value.candidate_branch and row.candidate_sha == value.candidate_sha)
    if len(active_carriers) == 1 and len(exact_carriers) == 1:
        carrier_state = CarrierAssessmentState.EXACT
    elif not value.carriers_complete and not active_carriers:
        carrier_state = CarrierAssessmentState.UNKNOWN
        add(AssessmentIssue.CARRIER_COVERAGE_PARTIAL, AssessmentVerdict.UNKNOWN)
    else:
        carrier_state = CarrierAssessmentState.CONFLICT
        add(AssessmentIssue.OPERATION_CARRIER_CONFLICT, AssessmentVerdict.REFUSED)
    if not value.carriers_complete and active_carriers:
        add(AssessmentIssue.CARRIER_COVERAGE_PARTIAL, AssessmentVerdict.UNKNOWN)

    conflicting_writers = tuple(writer for writer in value.writers if writer.active and writer.operation_key != value.operation_key and any(_path_overlap(writer_path, candidate_path) for writer_path in writer.paths for candidate_path in value.actual_paths))
    if conflicting_writers:
        writer_state = WriterAssessmentState.CONFLICT
        add(AssessmentIssue.CARRIER_WRITER_CONFLICT, AssessmentVerdict.REFUSED)
    elif not value.writers_complete:
        writer_state = WriterAssessmentState.UNKNOWN
        add(AssessmentIssue.WRITER_COVERAGE_PARTIAL, AssessmentVerdict.UNKNOWN)
    else:
        writer_state = WriterAssessmentState.CLEAR

    check_failed = False
    check_pending = False
    check_unknown = False
    if value.required_checks and not value.checks_complete:
        check_unknown = True
        add(AssessmentIssue.CHECK_COVERAGE_PARTIAL, AssessmentVerdict.UNKNOWN)
    for required_name in value.required_checks:
        named = tuple(row for row in value.checks if row.name == required_name)
        applicable = tuple(row for row in named if row.head_sha == value.candidate_sha and not row.superseded)
        superseded = tuple(row for row in named if row.superseded or row.head_sha != value.candidate_sha)
        if not applicable:
            if superseded:
                add(AssessmentIssue.CHECK_SUPERSEDED, AssessmentVerdict.HELD)
            if value.checks_complete:
                check_pending = True
                add(AssessmentIssue.CHECK_PENDING, AssessmentVerdict.HELD)
            else:
                check_unknown = True
                add(AssessmentIssue.CHECK_COVERAGE_PARTIAL, AssessmentVerdict.UNKNOWN)
            continue
        latest_attempt = max(row.attempt for row in applicable)
        latest = next(row for row in applicable if row.attempt == latest_attempt)
        if latest.status is not CheckStatus.COMPLETED or latest.conclusion is None:
            check_pending = True
            add(AssessmentIssue.CHECK_PENDING, AssessmentVerdict.HELD)
        elif latest.conclusion is CheckConclusion.SUCCESS:
            pass
        elif latest.conclusion is CheckConclusion.CANCELLED:
            check_failed = True
            add(AssessmentIssue.CHECK_CANCELLED, AssessmentVerdict.REFUSED)
        elif latest.conclusion is CheckConclusion.UNKNOWN:
            check_unknown = True
            add(AssessmentIssue.CHECK_COVERAGE_PARTIAL, AssessmentVerdict.UNKNOWN)
        else:
            check_failed = True
            add(AssessmentIssue.CHECK_FAILED, AssessmentVerdict.REFUSED)
    if check_failed:
        check_state = CheckAssessmentState.FAILED
    elif check_unknown:
        check_state = CheckAssessmentState.UNKNOWN
    elif check_pending:
        check_state = CheckAssessmentState.PENDING
    else:
        check_state = CheckAssessmentState.GREEN

    current_reviews = tuple(row for row in value.reviews if row.head_sha == value.candidate_sha)
    review_blocked = any(row.state is ReviewState.CHANGES_REQUESTED for row in current_reviews)
    approvals = {row.reviewer for row in current_reviews if row.required and row.state is ReviewState.APPROVED}
    if review_blocked:
        review_state = ReviewAssessmentState.BLOCKED
        add(AssessmentIssue.CHANGES_REQUESTED, AssessmentVerdict.REFUSED)
    elif not value.reviews_complete:
        review_state = ReviewAssessmentState.UNKNOWN
        add(AssessmentIssue.REVIEW_COVERAGE_PARTIAL, AssessmentVerdict.UNKNOWN)
    elif len(approvals) < value.required_approvals or value.unresolved_required_threads > 0:
        review_state = ReviewAssessmentState.PENDING
    else:
        review_state = ReviewAssessmentState.SATISFIED
    if len(approvals) < value.required_approvals:
        add(AssessmentIssue.REVIEW_REQUIRED, AssessmentVerdict.HELD)
    if value.unresolved_required_threads > 0:
        add(AssessmentIssue.UNRESOLVED_REVIEW_THREAD, AssessmentVerdict.HELD)

    if value.production_proof_required:
        if value.production_proof_state is ProductionProofState.MISSING:
            add(AssessmentIssue.PRODUCTION_PROOF_MISSING, AssessmentVerdict.HELD)
        elif value.production_proof_state is ProductionProofState.PARTIAL:
            add(AssessmentIssue.PRODUCTION_PROOF_PARTIAL, AssessmentVerdict.HELD)
        elif value.production_proof_state is ProductionProofState.UNKNOWN:
            add(AssessmentIssue.PRODUCTION_PROOF_UNKNOWN, AssessmentVerdict.UNKNOWN)

    completion_state = CompletionClaimState.VALID
    if value.claimed_capability_state is CapabilityState.PROVEN_LIVE:
        if value.production_proof_state is ProductionProofState.UNKNOWN:
            completion_state = CompletionClaimState.UNKNOWN
            add(AssessmentIssue.PRODUCTION_PROOF_UNKNOWN, AssessmentVerdict.UNKNOWN)
        elif value.production_proof_state is not ProductionProofState.PRESENT:
            completion_state = CompletionClaimState.OVERSTATED
            add(AssessmentIssue.COMPLETION_CLAIM_OVERSTATED, AssessmentVerdict.REFUSED)

    if value.requested_merge_method not in value.allowed_merge_methods:
        add(AssessmentIssue.MERGE_METHOD_REFUSED, AssessmentVerdict.REFUSED)

    if value.prior_effect_state is EffectState.EFFECT_UNKNOWN:
        add(AssessmentIssue.PRIOR_EFFECT_UNKNOWN, AssessmentVerdict.REFUSED)
    elif value.prior_effect_state is EffectState.APPLIED:
        add(AssessmentIssue.PRIOR_EFFECT_APPLIED, AssessmentVerdict.REFUSED)

    if refused:
        verdict = AssessmentVerdict.REFUSED
    elif unknown:
        verdict = AssessmentVerdict.UNKNOWN
    elif held:
        verdict = AssessmentVerdict.HELD
    else:
        verdict = AssessmentVerdict.ELIGIBLE

    normalized_issues = tuple(sorted(issues, key=lambda item: item.value))
    source_refs = _all_source_refs(value)
    input_digest = _digest(_primitive(value))
    expected_head_merge_eligible = bool(verdict is AssessmentVerdict.ELIGIBLE and value.candidate_sha == value.expected_head_sha and value.prior_effect_state is EffectState.NOT_APPLIED and value.requested_merge_method in value.allowed_merge_methods)
    provisional = GithubReleaseAssessment(
        schema=OUTPUT_SCHEMA,
        verdict=verdict,
        operation_key=value.operation_key,
        repository=value.repository,
        protected_ref=value.protected_ref,
        protected_sha=value.protected_sha,
        candidate_branch=value.candidate_branch,
        candidate_sha=value.candidate_sha,
        expected_head_sha=value.expected_head_sha,
        base_sha=value.base_sha,
        merge_base_sha=value.merge_base_sha,
        ahead_by=value.ahead_by,
        behind_by=value.behind_by,
        merge_context_state=merge_context_state,
        path_state=path_state,
        semantic_collision_state=semantic_state,
        carrier_state=carrier_state,
        writer_state=writer_state,
        check_state=check_state,
        review_state=review_state,
        source_law_state=value.source_law_state,
        production_proof_state=value.production_proof_state,
        completion_claim_state=completion_state,
        requested_merge_method=value.requested_merge_method,
        prior_effect_state=value.prior_effect_state,
        expected_head_merge_eligible=expected_head_merge_eligible,
        claimed_capability_state=value.claimed_capability_state,
        issues=normalized_issues,
        source_refs=source_refs,
        input_digest=input_digest,
        canonical_digest="",
    )
    payload = provisional.to_dict()
    payload.pop("canonical_digest")
    return dataclasses.replace(provisional, canonical_digest=_digest(payload))


__all__ = [
    "INPUT_SCHEMA",
    "OUTPUT_SCHEMA",
    "AssessmentInput",
    "AssessmentInputError",
    "AssessmentIssue",
    "AssessmentVerdict",
    "CapabilityState",
    "CarrierFact",
    "CheckConclusion",
    "CheckFact",
    "CheckStatus",
    "CompletionClaimState",
    "EffectState",
    "GithubReleaseAssessment",
    "MergeMethod",
    "PathCollisionFact",
    "PrivilegeClass",
    "ProductionProofState",
    "ReviewFact",
    "ReviewState",
    "SemanticOwnerFact",
    "SemanticOwnerExpectation",
    "SourceCoverage",
    "SourceLawState",
    "WriterFact",
    "assess_github_release",
]
