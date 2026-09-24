"""Pure deterministic assessment for one exact GitHub release candidate.

The caller supplies immutable, source-owned facts. This module performs no I/O,
network access, mutation, credential selection, clock access, subprocess work,
filesystem discovery, or persistence. It owns only the bounded classification
semantics for ``mastermind.github_release_assessment.v1``.

Every load-bearing observation carries a bounded, versioned ``SourceReference``.
Validation admits exact dataclass, enum, and primitive types only. Adjudication
never calls a caller-overridable identity method, so validated identity and the
identity consumed by the verdict cannot diverge.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import re
from enum import Enum
from typing import Any


INPUT_SCHEMA = "mastermind.github_release_assessment.input.v3"
OUTPUT_SCHEMA = "mastermind.github_release_assessment.v1"

MAX_PATHS = 256
MAX_SEMANTIC_OWNERS = 128
MAX_CARRIERS = 64
MAX_WRITERS = 128
MAX_COLLISIONS = 128
MAX_CHECK_IDENTITIES = 128
MAX_CHECK_ATTEMPTS = 512
MAX_REVIEWS = 256
MAX_SOURCE_REFS = 2_048
MAX_EVIDENCE_AGE_SECONDS = 86_400

_SHA_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_OPERATION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,191}$")
_REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$")
_REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,255}$")
_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,255}$")
_CHECK_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._:/()\[\]-]{0,127}$")
_SOURCE_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9:._/@#?=&,+-]{0,511}$")
_PATH_RE = re.compile(r"^[A-Za-z0-9._/-]{1,512}$")
_SOURCE_CREDENTIAL_ASSIGNMENT_RE = re.compile(
    r"(?<![A-Za-z0-9])"
    r"(?:access[._-]?token|client[._-]?secret|api[._-]?key|token|"
    r"sig(?:nature)?|secret|credential|passw(?:or)?d|authorization)"
    r"[:=]",
    re.IGNORECASE,
)
_SOURCE_PRIVATE_COORDINATE_RE = re.compile(
    r"(?:"
    r"[A-Za-z][A-Za-z0-9+.-]*://|"
    r"(?<![A-Za-z0-9])[A-Za-z]:[/\\]|"
    r"(?<![A-Za-z0-9])(?:/|~/|~\\|\\\\|//)|"
    r"(?<![A-Za-z0-9])"
    r"(?:localhost|internal(?:\.[A-Za-z0-9-]+)*|"
    r"[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.(?:internal|localhost|local)|"
    r"127(?:\.\d{1,3}){3}|10(?:\.\d{1,3}){3}|"
    r"172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2}|"
    r"192\.168(?:\.\d{1,3}){2}|169\.254(?:\.\d{1,3}){2})"
    r"(?::\d{1,5})?(?:[/?#]|$)"
    r")",
    re.IGNORECASE,
)
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


class SourceOwner(str, Enum):
    GITHUB = "github"
    EXECUTIVE_OS = "executive_os"
    AGENT_OS = "agent_os"
    RUNTIME_BINDING = "runtime_binding"
    PRODUCTION_OWNER = "production_owner"


class SourceReferenceCoverage(str, Enum):
    COMPLETE = "COMPLETE"
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
class SourceReference:
    source_kind: str
    owner: SourceOwner
    repository: str | None
    resource_kind: str
    resource_id: str
    revision: str
    observed_at: int
    valid_at: int | None
    content_sha256: str
    coverage: SourceReferenceCoverage
    truncated: bool
    continuation: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "source_kind": self.source_kind,
            "owner": self.owner.value,
            "repository": self.repository,
            "resource_kind": self.resource_kind,
            "resource_id": self.resource_id,
            "revision": self.revision,
            "observed_at": self.observed_at,
            "valid_at": self.valid_at,
            "content_sha256": self.content_sha256,
            "coverage": self.coverage.value,
            "truncated": self.truncated,
            "continuation": self.continuation,
        }


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
    source_ref: SourceReference
    changed_paths_source_ref: SourceReference


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
    source_ref: SourceReference


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
    source_ref: SourceReference


@dataclasses.dataclass(frozen=True)
class CheckIdentity:
    context: str
    app_id: int | None


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
    source_ref: SourceReference


@dataclasses.dataclass(frozen=True)
class ReviewEvent:
    reviewer_id: str
    head_sha: str
    sequence: int
    state: ReviewState
    source_ref: SourceReference


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
    source_ref: SourceReference


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
    source_ref: SourceReference


@dataclasses.dataclass(frozen=True)
class WriterFact:
    writer_id: str
    operation_key: str
    repository_id: int
    pull_request_number: int
    paths: tuple[str, ...]
    active: bool
    source_ref: SourceReference


@dataclasses.dataclass(frozen=True)
class PathCollisionFact:
    path: str
    other_operation_key: str
    source_ref: SourceReference


@dataclasses.dataclass(frozen=True)
class MergedEffectReceipt:
    repository: str
    repository_id: int
    pull_request_number: int
    candidate_sha: str
    merged_commit_sha: str
    changed_paths: tuple[str, ...]
    source_ref: SourceReference


@dataclasses.dataclass(frozen=True)
class AssessmentInput:
    schema: str
    operation_key: str
    observed_at: int
    expected_target: ReleaseTargetExpectation
    target: PullRequestTarget
    policy_source_ref: SourceReference
    expected_paths: tuple[str, ...]
    expected_semantic_owners: tuple[SemanticOwnerExpectation, ...]
    semantic_owner_facts: tuple[SemanticOwnerFact, ...]
    semantic_owners_complete: bool
    semantic_owners_source_ref: SourceReference
    carrier_facts: tuple[CarrierFact, ...]
    carriers_complete: bool
    carriers_source_ref: SourceReference
    expected_writer_id: str
    writer_facts: tuple[WriterFact, ...]
    writers_complete: bool
    writers_source_ref: SourceReference
    path_collisions: tuple[PathCollisionFact, ...]
    path_collisions_complete: bool
    path_collisions_source_ref: SourceReference
    branch_required_checks: tuple[CheckIdentity, ...]
    assessment_required_checks: tuple[CheckIdentity, ...]
    allowed_non_success_checks: tuple[CheckIdentity, ...]
    check_attempts: tuple[CheckAttempt, ...]
    checks_complete: bool
    checks_source_ref: SourceReference
    required_approvals: int
    review_events: tuple[ReviewEvent, ...]
    reviews_complete: bool
    reviews_source_ref: SourceReference
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
    source_refs: tuple[SourceReference, ...]


@dataclasses.dataclass(frozen=True)
class ExpectedHeadRelease:
    repository: str
    repository_id: int
    pull_request_number: int
    protected_sha: str
    candidate_sha: str
    changed_paths: tuple[str, ...]
    merge_method: MergeMethod
    organizational_authority_granted: bool
    production_acceptance_claimed: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "repository": self.repository,
            "repository_id": self.repository_id,
            "pull_request_number": self.pull_request_number,
            "protected_sha": self.protected_sha,
            "candidate_sha": self.candidate_sha,
            "changed_paths": list(self.changed_paths),
            "merge_method": self.merge_method.value,
            "organizational_authority_granted": self.organizational_authority_granted,
            "production_acceptance_claimed": self.production_acceptance_claimed,
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
    expected_head_sha: str
    merge_base_sha: str | None
    ahead_by: int | None
    behind_by: int | None
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
    source_refs: tuple[SourceReference, ...]
    input_digest: str
    canonical_digest: str

    @property
    def semantic_collision_state(self) -> SemanticOwnerAssessmentState:
        """Protected-contract alias for the semantic ownership assessment."""
        return self.semantic_owner_state

    @property
    def source_law_state(self) -> SourceAssessmentState:
        """Protected-contract alias for the current source-law assessment."""
        return self.source_state

    @property
    def production_proof_state(self) -> ProductionAssessmentState:
        """Protected-contract alias for the production-proof assessment."""
        return self.production_state

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
            "expected_head_sha": self.expected_head_sha,
            "merge_base_sha": self.merge_base_sha,
            "ahead_by": self.ahead_by,
            "behind_by": self.behind_by,
            "merge_context_state": self.merge_context_state.value,
            "path_state": self.path_state.value,
            "semantic_owner_state": self.semantic_owner_state.value,
            "semantic_collision_state": self.semantic_collision_state.value,
            "carrier_state": self.carrier_state.value,
            "writer_state": self.writer_state.value,
            "check_state": self.check_state.value,
            "review_state": self.review_state.value,
            "source_state": self.source_state.value,
            "source_law_state": self.source_law_state.value,
            "production_state": self.production_state.value,
            "production_proof_state": self.production_proof_state.value,
            "completion_claim_state": self.completion_claim_state.value,
            "effective_prior_effect_state": self.effective_prior_effect_state.value,
            "expected_head_merge_eligible": self.expected_head_merge_eligible,
            "expected_head_release": (
                None if self.expected_head_release is None else self.expected_head_release.to_dict()
            ),
            "claimed_capability_id": self.claimed_capability_id,
            "claimed_capability_state": self.claimed_capability_state.value,
            "issues": [item.value for item in self.issues],
            "source_refs": [item.to_dict() for item in self.source_refs],
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
    if type(value) is not str or pattern.fullmatch(value) is None:
        raise AssessmentInputError(f"{field} is malformed")
    _reject_secret(value, field=field)
    return value


def _source_reference_text(
    value: object, *, field: str, pattern: re.Pattern[str]
) -> str:
    token = _text(value, field=field, pattern=pattern)
    if (
        _SOURCE_CREDENTIAL_ASSIGNMENT_RE.search(token)
        or _SOURCE_PRIVATE_COORDINATE_RE.search(token)
    ):
        raise AssessmentInputError(f"{field} contains unsafe source-reference text")
    return token


def _operation(value: object, *, field: str = "operation_key") -> str:
    return _text(value, field=field, pattern=_OPERATION_RE)


def _identifier(value: object, *, field: str) -> str:
    return _text(value, field=field, pattern=_IDENTIFIER_RE)


def _source_token(value: object, *, field: str) -> str:
    return _text(value, field=field, pattern=_SOURCE_TOKEN_RE)


def _sha(value: object, *, field: str, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    return _text(value, field=field, pattern=_SHA_RE)


def _repository(value: object, *, field: str) -> str:
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


def _plain_int(value: object, *, field: str, allow_zero: bool = False) -> int:
    if type(value) is not int:
        raise AssessmentInputError(f"{field} must be an integer")
    minimum = 0 if allow_zero else 1
    if value < minimum:
        raise AssessmentInputError(f"{field} is outside the reviewed bound")
    return value


def _plain_bool(value: object, *, field: str) -> bool:
    if type(value) is not bool:
        raise AssessmentInputError(f"{field} must be boolean")
    return value


def _exact(value: object, expected: type[Any], *, field: str) -> Any:
    if type(value) is not expected:
        raise AssessmentInputError(f"{field} has wrong exact type")
    return value


def _exact_enum(value: object, expected: type[Enum], *, field: str) -> None:
    if type(value) is not expected:
        raise AssessmentInputError(f"{field} has the wrong enum type")


def _ensure_tuple(value: object, *, field: str, maximum: int) -> tuple[object, ...]:
    if type(value) is not tuple or len(value) > maximum:
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


def _validate_source_reference(value: object, *, field: str) -> SourceReference:
    item = _exact(value, SourceReference, field=field)
    _source_reference_text(
        item.source_kind,
        field=f"{field}.source_kind",
        pattern=_IDENTIFIER_RE,
    )
    _exact_enum(item.owner, SourceOwner, field=f"{field}.owner")
    if item.repository is not None:
        _source_reference_text(
            item.repository,
            field=f"{field}.repository",
            pattern=_REPOSITORY_RE,
        )
    _source_reference_text(
        item.resource_kind,
        field=f"{field}.resource_kind",
        pattern=_IDENTIFIER_RE,
    )
    _source_reference_text(
        item.resource_id,
        field=f"{field}.resource_id",
        pattern=_SOURCE_TOKEN_RE,
    )
    _source_reference_text(
        item.revision,
        field=f"{field}.revision",
        pattern=_SOURCE_TOKEN_RE,
    )
    _plain_int(item.observed_at, field=f"{field}.observed_at", allow_zero=True)
    if item.valid_at is not None:
        _plain_int(item.valid_at, field=f"{field}.valid_at", allow_zero=True)
        if item.valid_at > item.observed_at:
            raise AssessmentInputError(f"{field}.valid_at exceeds observed_at")
    _source_reference_text(
        item.content_sha256,
        field=f"{field}.content_sha256",
        pattern=_SHA256_RE,
    )
    _exact_enum(item.coverage, SourceReferenceCoverage, field=f"{field}.coverage")
    _plain_bool(item.truncated, field=f"{field}.truncated")
    if item.continuation is not None:
        _source_reference_text(
            item.continuation,
            field=f"{field}.continuation",
            pattern=_SOURCE_TOKEN_RE,
        )
    return item


def _validate_check_identity(value: object, *, field: str) -> tuple[str, int]:
    item = _exact(value, CheckIdentity, field=field)
    context = _text(item.context, field=f"{field}.context", pattern=_CHECK_RE)
    if item.app_id is not None:
        _plain_int(item.app_id, field=f"{field}.app_id")
    return (context, -1 if item.app_id is None else item.app_id)


def _identity_key(identity: CheckIdentity) -> tuple[str, int]:
    """Render an already exact-validated identity without virtual dispatch."""

    return (identity.context, -1 if identity.app_id is None else identity.app_id)


def _validate_subject(subject: object, *, field: str) -> EvidenceSubject:
    item = _exact(subject, EvidenceSubject, field=field)
    _repository(item.repository, field=f"{field}.repository")
    _plain_int(item.repository_id, field=f"{field}.repository_id")
    _plain_int(item.pull_request_number, field=f"{field}.pull_request_number")
    _ref(item.protected_ref, field=f"{field}.protected_ref")
    _sha(item.protected_sha, field=f"{field}.protected_sha")
    _ref(item.base_ref, field=f"{field}.base_ref")
    _sha(item.base_sha, field=f"{field}.base_sha", optional=True)
    _ref(item.candidate_ref, field=f"{field}.candidate_ref")
    _sha(item.candidate_sha, field=f"{field}.candidate_sha")
    _paths(item.changed_paths, field=f"{field}.changed_paths", allow_empty=True)
    return item


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


def _validate_input(packet: object) -> AssessmentInput:
    item = _exact(packet, AssessmentInput, field="packet")
    if type(item.schema) is not str or item.schema != INPUT_SCHEMA:
        raise AssessmentInputError("input schema/type is unsupported")
    _operation(item.operation_key)
    _plain_int(item.observed_at, field="observed_at", allow_zero=True)

    expected = _exact(item.expected_target, ReleaseTargetExpectation, field="expected_target")
    _repository(expected.repository, field="expected_target.repository")
    _plain_int(expected.repository_id, field="expected_target.repository_id")
    _plain_int(expected.pull_request_number, field="expected_target.pull_request_number")
    _ref(expected.protected_ref, field="expected_target.protected_ref")
    _sha(expected.expected_protected_sha, field="expected_target.expected_protected_sha")
    _ref(expected.candidate_ref, field="expected_target.candidate_ref")
    _sha(expected.expected_head_sha, field="expected_target.expected_head_sha")

    target = _exact(item.target, PullRequestTarget, field="target")
    _repository(target.repository, field="target.repository")
    _plain_int(target.repository_id, field="target.repository_id")
    _plain_int(target.pull_request_number, field="target.pull_request_number")
    _exact_enum(target.state, PullRequestState, field="target.state")
    _plain_bool(target.draft, field="target.draft")
    _plain_bool(target.merged, field="target.merged")
    _sha(target.merged_commit_sha, field="target.merged_commit_sha", optional=True)
    _exact_enum(target.mergeability, Mergeability, field="target.mergeability")
    _ref(target.protected_ref, field="target.protected_ref")
    _sha(target.protected_sha, field="target.protected_sha")
    _plain_bool(target.protected_branch_protected, field="target.protected_branch_protected")
    _ref(target.base_ref, field="target.base_ref")
    _sha(target.base_sha, field="target.base_sha", optional=True)
    _ref(target.candidate_ref, field="target.candidate_ref")
    _sha(target.candidate_sha, field="target.candidate_sha")
    _sha(target.merge_base_sha, field="target.merge_base_sha", optional=True)
    if target.ahead_by is not None:
        _plain_int(target.ahead_by, field="target.ahead_by", allow_zero=True)
    if target.behind_by is not None:
        _plain_int(target.behind_by, field="target.behind_by", allow_zero=True)
    _paths(target.changed_paths, field="target.changed_paths", allow_empty=True)
    _plain_bool(target.changed_paths_complete, field="target.changed_paths_complete")
    _validate_source_reference(target.source_ref, field="target.source_ref")
    _validate_source_reference(target.changed_paths_source_ref, field="target.changed_paths_source_ref")
    if target.state is PullRequestState.MERGED and not target.merged:
        raise AssessmentInputError("merged PR state must set target.merged")
    if target.state is PullRequestState.OPEN and target.merged:
        raise AssessmentInputError("open PR cannot set target.merged")
    if target.merged and target.merged_commit_sha is None:
        raise AssessmentInputError("merged target requires merged_commit_sha")
    if not target.merged and target.merged_commit_sha is not None:
        raise AssessmentInputError("unmerged target cannot carry merged_commit_sha")

    _validate_source_reference(item.policy_source_ref, field="policy_source_ref")
    _paths(item.expected_paths, field="expected_paths")

    expectations = _ensure_tuple(
        item.expected_semantic_owners,
        field="expected_semantic_owners",
        maximum=MAX_SEMANTIC_OWNERS,
    )
    expectation_keys: list[tuple[str, str | None]] = []
    for index, raw in enumerate(expectations):
        row = _exact(raw, SemanticOwnerExpectation, field=f"expected_semantic_owners[{index}]")
        prefix = _path(row.path_prefix, field=f"expected_semantic_owners[{index}].path_prefix")
        _plain_bool(row.no_owner_allowed, field=f"expected_semantic_owners[{index}].no_owner_allowed")
        owner = None
        if row.owner_id is not None:
            owner = _identifier(row.owner_id, field=f"expected_semantic_owners[{index}].owner_id")
        if (owner is None) != row.no_owner_allowed:
            raise AssessmentInputError(
                "semantic owner expectation must name an owner or explicitly allow no owner"
            )
        expectation_keys.append((prefix, owner))
    if len(set(expectation_keys)) != len(expectation_keys):
        raise AssessmentInputError("expected_semantic_owners contains duplicates")

    owner_facts = _ensure_tuple(
        item.semantic_owner_facts,
        field="semantic_owner_facts",
        maximum=MAX_SEMANTIC_OWNERS,
    )
    owner_keys: set[tuple[object, ...]] = set()
    for index, raw in enumerate(owner_facts):
        row = _exact(raw, SemanticOwnerFact, field=f"semantic_owner_facts[{index}]")
        _path(row.path_prefix, field=f"semantic_owner_facts[{index}].path_prefix")
        _identifier(row.owner_id, field=f"semantic_owner_facts[{index}].owner_id")
        _operation(row.operation_key, field=f"semantic_owner_facts[{index}].operation_key")
        _plain_bool(row.active, field=f"semantic_owner_facts[{index}].active")
        _validate_source_reference(row.source_ref, field=f"semantic_owner_facts[{index}].source_ref")
        key = (row.path_prefix, row.owner_id, row.operation_key, row.active, row.source_ref)
        if key in owner_keys:
            raise AssessmentInputError("semantic_owner_facts contains duplicates")
        owner_keys.add(key)
    _plain_bool(item.semantic_owners_complete, field="semantic_owners_complete")
    _validate_source_reference(item.semantic_owners_source_ref, field="semantic_owners_source_ref")

    carriers = _ensure_tuple(item.carrier_facts, field="carrier_facts", maximum=MAX_CARRIERS)
    carrier_refs: set[str] = set()
    for index, raw in enumerate(carriers):
        row = _exact(raw, CarrierFact, field=f"carrier_facts[{index}]")
        carrier_ref = _source_token(row.carrier_ref, field=f"carrier_facts[{index}].carrier_ref")
        _operation(row.operation_key, field=f"carrier_facts[{index}].operation_key")
        _repository(row.repository, field=f"carrier_facts[{index}].repository")
        _plain_int(row.repository_id, field=f"carrier_facts[{index}].repository_id")
        _plain_int(row.pull_request_number, field=f"carrier_facts[{index}].pull_request_number")
        _ref(row.base_ref, field=f"carrier_facts[{index}].base_ref")
        _sha(row.base_sha, field=f"carrier_facts[{index}].base_sha", optional=True)
        _ref(row.candidate_ref, field=f"carrier_facts[{index}].candidate_ref")
        _sha(row.candidate_sha, field=f"carrier_facts[{index}].candidate_sha")
        _plain_bool(row.active, field=f"carrier_facts[{index}].active")
        _validate_source_reference(row.source_ref, field=f"carrier_facts[{index}].source_ref")
        if carrier_ref in carrier_refs:
            raise AssessmentInputError("carrier_facts contains duplicate carrier_ref")
        carrier_refs.add(carrier_ref)
    _plain_bool(item.carriers_complete, field="carriers_complete")
    _validate_source_reference(item.carriers_source_ref, field="carriers_source_ref")

    _identifier(item.expected_writer_id, field="expected_writer_id")
    writers = _ensure_tuple(item.writer_facts, field="writer_facts", maximum=MAX_WRITERS)
    writer_ids: set[str] = set()
    for index, raw in enumerate(writers):
        row = _exact(raw, WriterFact, field=f"writer_facts[{index}]")
        writer_id = _identifier(row.writer_id, field=f"writer_facts[{index}].writer_id")
        _operation(row.operation_key, field=f"writer_facts[{index}].operation_key")
        _plain_int(row.repository_id, field=f"writer_facts[{index}].repository_id")
        _plain_int(row.pull_request_number, field=f"writer_facts[{index}].pull_request_number")
        _paths(row.paths, field=f"writer_facts[{index}].paths", allow_empty=True)
        _plain_bool(row.active, field=f"writer_facts[{index}].active")
        _validate_source_reference(row.source_ref, field=f"writer_facts[{index}].source_ref")
        if writer_id in writer_ids:
            raise AssessmentInputError("writer_facts contains duplicate writer_id")
        writer_ids.add(writer_id)
    _plain_bool(item.writers_complete, field="writers_complete")
    _validate_source_reference(item.writers_source_ref, field="writers_source_ref")

    collisions = _ensure_tuple(
        item.path_collisions,
        field="path_collisions",
        maximum=MAX_COLLISIONS,
    )
    collision_keys: set[tuple[str, str]] = set()
    for index, raw in enumerate(collisions):
        row = _exact(raw, PathCollisionFact, field=f"path_collisions[{index}]")
        path = _path(row.path, field=f"path_collisions[{index}].path")
        operation = _operation(
            row.other_operation_key,
            field=f"path_collisions[{index}].other_operation_key",
        )
        _validate_source_reference(row.source_ref, field=f"path_collisions[{index}].source_ref")
        if (path, operation) in collision_keys:
            raise AssessmentInputError("path_collisions contains duplicates")
        collision_keys.add((path, operation))
    _plain_bool(item.path_collisions_complete, field="path_collisions_complete")
    _validate_source_reference(item.path_collisions_source_ref, field="path_collisions_source_ref")

    identity_groups = {
        "branch_required_checks": item.branch_required_checks,
        "assessment_required_checks": item.assessment_required_checks,
        "allowed_non_success_checks": item.allowed_non_success_checks,
    }
    for field, group in identity_groups.items():
        rows = _ensure_tuple(group, field=field, maximum=MAX_CHECK_IDENTITIES)
        keys = [_validate_check_identity(raw, field=f"{field}[{index}]") for index, raw in enumerate(rows)]
        if len(set(keys)) != len(keys):
            raise AssessmentInputError(f"{field} contains duplicate identities")

    attempts = _ensure_tuple(item.check_attempts, field="check_attempts", maximum=MAX_CHECK_ATTEMPTS)
    attempt_keys: set[tuple[tuple[str, int], str, int, int]] = set()
    for index, raw in enumerate(attempts):
        row = _exact(raw, CheckAttempt, field=f"check_attempts[{index}]")
        identity = _validate_check_identity(row.identity, field=f"check_attempts[{index}].identity")
        head = _sha(row.head_sha, field=f"check_attempts[{index}].head_sha")
        attempt = _plain_int(row.attempt, field=f"check_attempts[{index}].attempt")
        sequence = _plain_int(row.sequence, field=f"check_attempts[{index}].sequence")
        _exact_enum(row.status, CheckStatus, field=f"check_attempts[{index}].status")
        if row.conclusion is not None:
            _exact_enum(row.conclusion, CheckConclusion, field=f"check_attempts[{index}].conclusion")
        if row.status is CheckStatus.COMPLETED and row.conclusion is None:
            raise AssessmentInputError("completed check attempt requires conclusion")
        if row.status is not CheckStatus.COMPLETED and row.conclusion is not None:
            raise AssessmentInputError("nonterminal check attempt cannot carry conclusion")
        _plain_bool(row.applicable, field=f"check_attempts[{index}].applicable")
        _plain_bool(row.superseded, field=f"check_attempts[{index}].superseded")
        _validate_source_reference(row.source_ref, field=f"check_attempts[{index}].source_ref")
        unique = (identity, str(head), attempt, sequence)
        if unique in attempt_keys:
            raise AssessmentInputError("check_attempts contains duplicate attempt identity")
        attempt_keys.add(unique)
    _plain_bool(item.checks_complete, field="checks_complete")
    _validate_source_reference(item.checks_source_ref, field="checks_source_ref")

    _plain_int(item.required_approvals, field="required_approvals", allow_zero=True)
    reviews = _ensure_tuple(item.review_events, field="review_events", maximum=MAX_REVIEWS)
    review_keys: set[tuple[str, str, int]] = set()
    for index, raw in enumerate(reviews):
        row = _exact(raw, ReviewEvent, field=f"review_events[{index}]")
        reviewer = _identifier(row.reviewer_id, field=f"review_events[{index}].reviewer_id")
        head = _sha(row.head_sha, field=f"review_events[{index}].head_sha")
        sequence = _plain_int(row.sequence, field=f"review_events[{index}].sequence")
        _exact_enum(row.state, ReviewState, field=f"review_events[{index}].state")
        _validate_source_reference(row.source_ref, field=f"review_events[{index}].source_ref")
        key = (reviewer, str(head), sequence)
        if key in review_keys:
            raise AssessmentInputError("review_events contains duplicate sequence identity")
        review_keys.add(key)
    _plain_bool(item.reviews_complete, field="reviews_complete")
    _validate_source_reference(item.reviews_source_ref, field="reviews_source_ref")
    _plain_int(item.unresolved_required_threads, field="unresolved_required_threads", allow_zero=True)

    if item.current_source_evidence is not None:
        evidence = _exact(
            item.current_source_evidence,
            CurrentSourceEvidence,
            field="current_source_evidence",
        )
        _validate_subject(evidence.subject, field="current_source_evidence.subject")
        _identifier(evidence.owner_id, field="current_source_evidence.owner_id")
        _source_token(evidence.revision, field="current_source_evidence.revision")
        _plain_int(evidence.observed_at, field="current_source_evidence.observed_at", allow_zero=True)
        _exact_enum(evidence.coverage, SourceCoverage, field="current_source_evidence.coverage")
        _exact_enum(evidence.law_state, SourceLawState, field="current_source_evidence.law_state")
        _validate_source_reference(evidence.source_ref, field="current_source_evidence.source_ref")
    _identifier(item.expected_source_owner_id, field="expected_source_owner_id")
    _source_token(item.expected_source_revision, field="expected_source_revision")
    _plain_int(item.source_max_age_seconds, field="source_max_age_seconds")
    if item.source_max_age_seconds > MAX_EVIDENCE_AGE_SECONDS:
        raise AssessmentInputError("source_max_age_seconds exceeds reviewed bound")
    _plain_bool(item.current_base_required, field="current_base_required")

    _plain_bool(item.production_proof_required, field="production_proof_required")
    _identifier(item.claimed_capability_id, field="claimed_capability_id")
    _exact_enum(item.claimed_capability_state, CapabilityState, field="claimed_capability_state")
    _identifier(item.expected_production_subject_id, field="expected_production_subject_id")
    _identifier(item.expected_production_owner_id, field="expected_production_owner_id")
    _source_token(item.expected_production_revision, field="expected_production_revision")
    _plain_int(item.production_max_age_seconds, field="production_max_age_seconds")
    if item.production_max_age_seconds > MAX_EVIDENCE_AGE_SECONDS:
        raise AssessmentInputError("production_max_age_seconds exceeds reviewed bound")
    if item.production_proof is not None:
        proof = _exact(item.production_proof, ProductionProof, field="production_proof")
        _identifier(proof.capability_id, field="production_proof.capability_id")
        _identifier(proof.subject_id, field="production_proof.subject_id")
        _validate_subject(proof.target_subject, field="production_proof.target_subject")
        _identifier(proof.owner_id, field="production_proof.owner_id")
        _source_token(proof.revision, field="production_proof.revision")
        _plain_int(proof.observed_at, field="production_proof.observed_at", allow_zero=True)
        _exact_enum(proof.coverage, SourceCoverage, field="production_proof.coverage")
        _exact_enum(proof.state, ProductionProofState, field="production_proof.state")
        _validate_source_reference(proof.source_ref, field="production_proof.source_ref")

    _exact_enum(item.requested_merge_method, MergeMethod, field="requested_merge_method")
    allowed_methods = _ensure_tuple(
        item.allowed_merge_methods,
        field="allowed_merge_methods",
        maximum=len(MergeMethod),
    )
    if not allowed_methods:
        raise AssessmentInputError("allowed_merge_methods must not be empty")
    for index, method in enumerate(allowed_methods):
        _exact_enum(method, MergeMethod, field=f"allowed_merge_methods[{index}]")
    if len(set(allowed_methods)) != len(allowed_methods):
        raise AssessmentInputError("allowed_merge_methods contains duplicates")

    _exact_enum(item.prior_effect_state, EffectState, field="prior_effect_state")
    if item.merged_effect_receipt is not None:
        receipt = _exact(
            item.merged_effect_receipt,
            MergedEffectReceipt,
            field="merged_effect_receipt",
        )
        _repository(receipt.repository, field="merged_effect_receipt.repository")
        _plain_int(receipt.repository_id, field="merged_effect_receipt.repository_id")
        _plain_int(receipt.pull_request_number, field="merged_effect_receipt.pull_request_number")
        _sha(receipt.candidate_sha, field="merged_effect_receipt.candidate_sha")
        _sha(receipt.merged_commit_sha, field="merged_effect_receipt.merged_commit_sha")
        _paths(receipt.changed_paths, field="merged_effect_receipt.changed_paths")
        _validate_source_reference(receipt.source_ref, field="merged_effect_receipt.source_ref")

    extras = _ensure_tuple(item.source_refs, field="source_refs", maximum=MAX_SOURCE_REFS)
    for index, source_ref in enumerate(extras):
        _validate_source_reference(source_ref, field=f"source_refs[{index}]")
    if len(set(extras)) != len(extras):
        raise AssessmentInputError("source_refs contains duplicates")
    if len(_collect_source_references(item)) > MAX_SOURCE_REFS:
        raise AssessmentInputError("total source reference count exceeds reviewed bound")
    return item


def _jsonable(value: object) -> Any:
    value_type = type(value)
    if value_type in {
        AssessmentVerdict,
        AssessmentIssue,
        CapabilityState,
        SourceCoverage,
        SourceLawState,
        EffectState,
        MergeMethod,
        PullRequestState,
        Mergeability,
        CheckStatus,
        CheckConclusion,
        ReviewState,
        ProductionProofState,
        SourceOwner,
        SourceReferenceCoverage,
        MergeContextState,
        PathState,
        SemanticOwnerAssessmentState,
        CarrierAssessmentState,
        WriterAssessmentState,
        CheckAssessmentState,
        ReviewAssessmentState,
        SourceAssessmentState,
        ProductionAssessmentState,
        CompletionClaimState,
    }:
        return value.value
    if dataclasses.is_dataclass(value):
        return {
            field.name: _jsonable(getattr(value, field.name))
            for field in dataclasses.fields(value)
        }
    if value_type is tuple:
        return [_jsonable(item) for item in value]
    if value_type is dict:
        return {str(key): _jsonable(item) for key, item in value.items()}
    return value


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


def _sorted_payloads(values: tuple[object, ...]) -> list[object]:
    rendered = [_jsonable(item) for item in values]
    return sorted(rendered, key=lambda item: _canonical_bytes(item))


def _normalized_input_payload(packet: AssessmentInput) -> dict[str, object]:
    payload = _jsonable(packet)
    payload["expected_paths"] = sorted(payload["expected_paths"])
    payload["target"]["changed_paths"] = sorted(payload["target"]["changed_paths"])
    for key in (
        "expected_semantic_owners",
        "semantic_owner_facts",
        "carrier_facts",
        "path_collisions",
        "branch_required_checks",
        "assessment_required_checks",
        "allowed_non_success_checks",
        "check_attempts",
        "review_events",
        "allowed_merge_methods",
        "source_refs",
    ):
        payload[key] = _sorted_payloads(getattr(packet, key))
    writer_rows = _sorted_payloads(packet.writer_facts)
    for row in writer_rows:
        row["paths"] = sorted(row["paths"])
    payload["writer_facts"] = sorted(writer_rows, key=lambda item: _canonical_bytes(item))
    if payload["current_source_evidence"] is not None:
        payload["current_source_evidence"]["subject"]["changed_paths"] = sorted(
            payload["current_source_evidence"]["subject"]["changed_paths"]
        )
    if payload["production_proof"] is not None:
        payload["production_proof"]["target_subject"]["changed_paths"] = sorted(
            payload["production_proof"]["target_subject"]["changed_paths"]
        )
    if payload["merged_effect_receipt"] is not None:
        payload["merged_effect_receipt"]["changed_paths"] = sorted(
            payload["merged_effect_receipt"]["changed_paths"]
        )
    return payload


def _collect_source_references(packet: AssessmentInput) -> tuple[SourceReference, ...]:
    refs = [
        packet.policy_source_ref,
        packet.target.source_ref,
        packet.target.changed_paths_source_ref,
        packet.semantic_owners_source_ref,
        packet.carriers_source_ref,
        packet.writers_source_ref,
        packet.path_collisions_source_ref,
        packet.checks_source_ref,
        packet.reviews_source_ref,
    ]
    refs.extend(item.source_ref for item in packet.semantic_owner_facts)
    refs.extend(item.source_ref for item in packet.carrier_facts)
    refs.extend(item.source_ref for item in packet.writer_facts)
    refs.extend(item.source_ref for item in packet.path_collisions)
    refs.extend(item.source_ref for item in packet.check_attempts)
    refs.extend(item.source_ref for item in packet.review_events)
    if packet.current_source_evidence is not None:
        refs.append(packet.current_source_evidence.source_ref)
    if packet.production_proof is not None:
        refs.append(packet.production_proof.source_ref)
    if packet.merged_effect_receipt is not None:
        refs.append(packet.merged_effect_receipt.source_ref)
    refs.extend(packet.source_refs)
    return tuple(refs)


def _source_native_key(ref: SourceReference) -> tuple[object, ...]:
    return (
        ref.source_kind,
        ref.owner.value,
        ref.repository,
        ref.resource_kind,
        ref.resource_id,
        ref.revision,
    )


def _source_full_key(ref: SourceReference) -> bytes:
    return _canonical_bytes(ref.to_dict())


_GITHUB_SOURCE = frozenset({SourceOwner.GITHUB})
_SEMANTIC_SOURCE = frozenset({SourceOwner.GITHUB, SourceOwner.AGENT_OS})
_WRITER_SOURCE = frozenset(
    {SourceOwner.RUNTIME_BINDING, SourceOwner.EXECUTIVE_OS, SourceOwner.AGENT_OS}
)
_CURRENT_LAW_SOURCE = frozenset({SourceOwner.GITHUB, SourceOwner.AGENT_OS})
_PRODUCTION_SOURCE = frozenset({SourceOwner.PRODUCTION_OWNER})


def _check_resource_id(attempt: CheckAttempt) -> str:
    digest = hashlib.sha256(
        _canonical_bytes(
            (
                attempt.identity.context,
                attempt.identity.app_id,
                attempt.attempt,
                attempt.sequence,
            )
        )
    ).hexdigest()
    return f"check:{digest}"


def _review_resource_id(event: ReviewEvent) -> str:
    return f"{event.reviewer_id}:{event.sequence}"


def _collision_resource_id(fact: PathCollisionFact) -> str:
    digest = hashlib.sha256(
        _canonical_bytes((fact.path, fact.other_operation_key))
    ).hexdigest()
    return f"collision:{digest}"


def _source_usage(
    packet: AssessmentInput,
) -> tuple[
    tuple[
        SourceReference,
        str | None,
        int,
        frozenset[SourceOwner] | None,
        str | None,
        str | None,
        bool,
    ],
    ...,
]:
    target_revision = packet.target.candidate_sha
    target_resource_id = str(packet.target.pull_request_number)
    general = packet.source_max_age_seconds
    rows: list[
        tuple[
            SourceReference,
            str | None,
            int,
            frozenset[SourceOwner] | None,
            str | None,
            str | None,
            bool,
        ]
    ] = [
        (
            packet.policy_source_ref,
            packet.expected_source_revision,
            general,
            _GITHUB_SOURCE,
            "protected_policy",
            None,
            True,
        ),
        (
            packet.target.source_ref,
            target_revision,
            general,
            _GITHUB_SOURCE,
            "pull_request",
            target_resource_id,
            True,
        ),
        (
            packet.target.changed_paths_source_ref,
            target_revision,
            general,
            _GITHUB_SOURCE,
            "pull_request_changed_paths",
            target_resource_id,
            True,
        ),
        # Agent OS and RuntimeBinding use owner-native immutable revisions. Their
        # fact fields and bounded target census bind the operation/PR/path.
        (
            packet.semantic_owners_source_ref,
            None,
            general,
            _SEMANTIC_SOURCE,
            "semantic_owner_census",
            target_resource_id,
            True,
        ),
        (
            packet.carriers_source_ref,
            target_revision,
            general,
            _GITHUB_SOURCE,
            "carrier_census",
            target_resource_id,
            True,
        ),
        (
            packet.writers_source_ref,
            None,
            general,
            _WRITER_SOURCE,
            "writer_census",
            target_resource_id,
            True,
        ),
        (
            packet.path_collisions_source_ref,
            None,
            general,
            _SEMANTIC_SOURCE,
            "path_collision_census",
            target_resource_id,
            True,
        ),
        (
            packet.checks_source_ref,
            target_revision,
            general,
            _GITHUB_SOURCE,
            "check_census",
            target_resource_id,
            True,
        ),
        (
            packet.reviews_source_ref,
            target_revision,
            general,
            _GITHUB_SOURCE,
            "review_census",
            target_resource_id,
            True,
        ),
    ]
    rows.extend(
        (
            fact.source_ref,
            None,
            general,
            _SEMANTIC_SOURCE,
            "semantic_owner",
            fact.path_prefix,
            True,
        )
        for fact in packet.semantic_owner_facts
    )
    rows.extend(
        (
            fact.source_ref,
            fact.candidate_sha,
            general,
            _GITHUB_SOURCE,
            "operation_carrier",
            fact.carrier_ref,
            True,
        )
        for fact in packet.carrier_facts
    )
    rows.extend(
        (
            fact.source_ref,
            None,
            general,
            _WRITER_SOURCE,
            "current_writer",
            fact.writer_id,
            True,
        )
        for fact in packet.writer_facts
    )
    rows.extend(
        (
            fact.source_ref,
            None,
            general,
            _SEMANTIC_SOURCE,
            "path_collision",
            _collision_resource_id(fact),
            True,
        )
        for fact in packet.path_collisions
    )
    rows.extend(
        (
            fact.source_ref,
            fact.head_sha,
            general,
            _GITHUB_SOURCE,
            "check_attempt",
            _check_resource_id(fact),
            True,
        )
        for fact in packet.check_attempts
    )
    rows.extend(
        (
            fact.source_ref,
            fact.head_sha,
            general,
            _GITHUB_SOURCE,
            "review_event",
            _review_resource_id(fact),
            True,
        )
        for fact in packet.review_events
    )
    if packet.current_source_evidence is not None:
        rows.append(
            (
                packet.current_source_evidence.source_ref,
                packet.current_source_evidence.revision,
                general,
                _CURRENT_LAW_SOURCE,
                "protected_source_law",
                packet.current_source_evidence.owner_id,
                True,
            )
        )
    if packet.production_proof is not None:
        rows.append(
            (
                packet.production_proof.source_ref,
                packet.production_proof.revision,
                packet.production_max_age_seconds,
                _PRODUCTION_SOURCE,
                "production_proof",
                packet.production_proof.subject_id,
                False,
            )
        )
    if packet.merged_effect_receipt is not None:
        rows.append(
            (
                packet.merged_effect_receipt.source_ref,
                packet.merged_effect_receipt.merged_commit_sha,
                general,
                _GITHUB_SOURCE,
                "merged_effect",
                packet.merged_effect_receipt.merged_commit_sha,
                True,
            )
        )
    rows.extend((ref, None, general, None, None, None, False) for ref in packet.source_refs)
    return tuple(rows)


def _assess_source_references(
    packet: AssessmentInput,
    issues: set[AssessmentIssue],
) -> tuple[
    dict[SourceReference, bool],
    dict[SourceReference, frozenset[AssessmentIssue]],
]:
    usage = _source_usage(packet)
    health: dict[SourceReference, bool] = {}
    local: dict[SourceReference, set[AssessmentIssue]] = {}
    native: dict[tuple[object, ...], SourceReference] = {}

    def mark(ref: SourceReference, issue: AssessmentIssue) -> None:
        issues.add(issue)
        local.setdefault(ref, set()).add(issue)

    for ref, _, _, _, _, _, _ in usage:
        existing = native.get(_source_native_key(ref))
        if existing is None:
            native[_source_native_key(ref)] = ref
        elif existing.content_sha256 != ref.content_sha256:
            mark(existing, AssessmentIssue.SOURCE_CONFLICT)
            mark(ref, AssessmentIssue.SOURCE_CONFLICT)

    for (
        ref,
        expected_revision,
        max_age,
        allowed_owners,
        expected_resource_kind,
        expected_resource_id,
        repository_required,
    ) in usage:
        usable = AssessmentIssue.SOURCE_CONFLICT not in local.get(ref, set())
        if allowed_owners is not None and ref.owner not in allowed_owners:
            mark(ref, AssessmentIssue.SOURCE_OWNER_MISMATCH)
            usable = False
        if expected_resource_kind is not None and ref.resource_kind != expected_resource_kind:
            mark(ref, AssessmentIssue.SOURCE_SUBJECT_MISMATCH)
            usable = False
        if expected_resource_id is not None and ref.resource_id != expected_resource_id:
            mark(ref, AssessmentIssue.SOURCE_SUBJECT_MISMATCH)
            usable = False
        if repository_required and ref.repository is None:
            mark(ref, AssessmentIssue.SOURCE_SUBJECT_MISMATCH)
            usable = False
        if ref.repository is not None and ref.repository != packet.target.repository:
            mark(ref, AssessmentIssue.SOURCE_SUBJECT_MISMATCH)
            usable = False
        if expected_revision is not None and ref.revision != expected_revision:
            mark(ref, AssessmentIssue.SOURCE_REVISION_MISMATCH)
            usable = False
        if ref.observed_at > packet.observed_at:
            mark(ref, AssessmentIssue.SOURCE_FUTURE)
            usable = False
        freshness_time = ref.observed_at if ref.valid_at is None else ref.valid_at
        if packet.observed_at - freshness_time > max_age:
            mark(ref, AssessmentIssue.SOURCE_STALE)
            usable = False
        if (
            ref.coverage is not SourceReferenceCoverage.COMPLETE
            or ref.truncated
            or ref.continuation is not None
        ):
            mark(ref, AssessmentIssue.SOURCE_INCOMPLETE)
            usable = False
        health[ref] = health.get(ref, True) and usable
    return health, {ref: frozenset(found) for ref, found in local.items()}


def _ref_current(health: dict[SourceReference, bool], ref: SourceReference) -> bool:
    return health.get(ref, False)


def _assess_current_source(
    packet: AssessmentInput,
    issues: set[AssessmentIssue],
    health: dict[SourceReference, bool],
    reference_issues: dict[SourceReference, frozenset[AssessmentIssue]],
) -> tuple[SourceAssessmentState, bool]:
    evidence = packet.current_source_evidence
    if evidence is None:
        issues.add(AssessmentIssue.SOURCE_EVIDENCE_MISSING)
        return SourceAssessmentState.UNKNOWN, False

    local_issues = set(reference_issues.get(evidence.source_ref, frozenset()))
    expected_subject = _target_subject(packet.target)
    if not _subject_matches(evidence.subject, expected_subject):
        local_issues.add(AssessmentIssue.SOURCE_SUBJECT_MISMATCH)
    if evidence.owner_id != packet.expected_source_owner_id:
        local_issues.add(AssessmentIssue.SOURCE_OWNER_MISMATCH)
    if evidence.revision != packet.expected_source_revision:
        local_issues.add(AssessmentIssue.SOURCE_REVISION_MISMATCH)
    if evidence.source_ref.observed_at != evidence.observed_at:
        local_issues.add(AssessmentIssue.SOURCE_CONFLICT)
    if evidence.observed_at > packet.observed_at:
        local_issues.add(AssessmentIssue.SOURCE_FUTURE)
    elif packet.observed_at - evidence.observed_at > packet.source_max_age_seconds:
        local_issues.add(AssessmentIssue.SOURCE_STALE)

    if evidence.coverage is SourceCoverage.CONFLICT:
        local_issues.add(AssessmentIssue.SOURCE_CONFLICT)
    elif evidence.coverage is SourceCoverage.INCOMPLETE:
        local_issues.add(AssessmentIssue.SOURCE_INCOMPLETE)
    elif evidence.coverage is SourceCoverage.STALE:
        local_issues.add(AssessmentIssue.SOURCE_STALE)

    if evidence.law_state is SourceLawState.INCOMPATIBLE:
        local_issues.add(AssessmentIssue.SOURCE_LAW_INCOMPATIBLE)
    elif evidence.law_state is SourceLawState.UNKNOWN:
        local_issues.add(AssessmentIssue.SOURCE_LAW_UNKNOWN)
    issues.update(local_issues)

    source_hard = {
        AssessmentIssue.SOURCE_SUBJECT_MISMATCH,
        AssessmentIssue.SOURCE_OWNER_MISMATCH,
        AssessmentIssue.SOURCE_REVISION_MISMATCH,
        AssessmentIssue.SOURCE_FUTURE,
        AssessmentIssue.SOURCE_CONFLICT,
        AssessmentIssue.SOURCE_LAW_INCOMPATIBLE,
    }
    source_unknown = {
        AssessmentIssue.SOURCE_EVIDENCE_MISSING,
        AssessmentIssue.SOURCE_INCOMPLETE,
        AssessmentIssue.SOURCE_STALE,
        AssessmentIssue.SOURCE_LAW_UNKNOWN,
    }
    if local_issues & source_hard:
        return SourceAssessmentState.INCOMPATIBLE, False
    if local_issues & source_unknown or not _ref_current(health, evidence.source_ref):
        return SourceAssessmentState.UNKNOWN, False
    return SourceAssessmentState.CURRENT, True


def _assess_target(
    packet: AssessmentInput,
    issues: set[AssessmentIssue],
    *,
    source_current: bool,
    health: dict[SourceReference, bool],
) -> MergeContextState:
    expected = packet.expected_target
    target = packet.target
    if target.repository != expected.repository or target.repository_id != expected.repository_id:
        issues.add(AssessmentIssue.REPOSITORY_MISMATCH)
    if target.pull_request_number != expected.pull_request_number:
        issues.add(AssessmentIssue.PULL_REQUEST_MISMATCH)
    if target.protected_ref != expected.protected_ref:
        issues.add(AssessmentIssue.BASE_REF_MISMATCH)
    if target.protected_sha != expected.expected_protected_sha:
        issues.add(AssessmentIssue.PROTECTED_REF_MOVED)
    if target.candidate_ref != expected.candidate_ref:
        issues.add(AssessmentIssue.PULL_REQUEST_MISMATCH)
    if target.candidate_sha != expected.expected_head_sha:
        issues.add(AssessmentIssue.CANDIDATE_HEAD_MOVED)
    if target.base_ref != expected.protected_ref:
        issues.add(AssessmentIssue.BASE_REF_MISMATCH)
    if not target.protected_branch_protected:
        issues.add(AssessmentIssue.BASE_BRANCH_UNPROTECTED)

    if target.state is PullRequestState.UNKNOWN:
        issues.add(AssessmentIssue.PR_STATE_UNKNOWN)
    elif target.state is not PullRequestState.OPEN:
        issues.add(AssessmentIssue.PR_STATE_REFUSED)
    if target.draft:
        issues.add(AssessmentIssue.PR_DRAFT)
    if target.mergeability is Mergeability.CONFLICTING:
        issues.add(AssessmentIssue.MERGE_CONFLICT)
    elif target.mergeability is Mergeability.UNKNOWN:
        issues.add(AssessmentIssue.MERGEABILITY_UNKNOWN)

    if not _ref_current(health, target.source_ref):
        issues.add(AssessmentIssue.BASE_OR_MERGE_CONTEXT_UNKNOWN)
        return MergeContextState.UNKNOWN
    if (
        target.base_sha is None
        or target.ahead_by is None
        or target.behind_by is None
        or target.merge_base_sha is None
    ):
        issues.add(AssessmentIssue.BASE_OR_MERGE_CONTEXT_UNKNOWN)
        return MergeContextState.UNKNOWN
    if target.ahead_by <= 0 or not target.changed_paths:
        issues.add(AssessmentIssue.EMPTY_RELEASE_DELTA)
    if target.behind_by == 0:
        if target.base_sha != target.protected_sha or target.merge_base_sha != target.protected_sha:
            issues.add(AssessmentIssue.BASE_OR_MERGE_CONTEXT_UNKNOWN)
            return MergeContextState.UNKNOWN
        return MergeContextState.CURRENT
    if packet.current_base_required:
        issues.add(AssessmentIssue.CURRENT_BASE_REQUIRED)
        return MergeContextState.HELD
    if source_current:
        return MergeContextState.BEHIND_COMPATIBLE
    issues.add(AssessmentIssue.BASE_OR_MERGE_CONTEXT_UNKNOWN)
    return MergeContextState.UNKNOWN


def _assess_paths(
    packet: AssessmentInput,
    issues: set[AssessmentIssue],
    health: dict[SourceReference, bool],
) -> PathState:
    actual = tuple(sorted(packet.target.changed_paths))
    expected = tuple(sorted(packet.expected_paths))
    if (
        not packet.target.changed_paths_complete
        or not _ref_current(health, packet.target.changed_paths_source_ref)
    ):
        issues.add(AssessmentIssue.PATH_COVERAGE_PARTIAL)
    if actual != expected:
        issues.add(AssessmentIssue.EXPECTED_PATH_MISMATCH)
        return PathState.MISMATCH
    if AssessmentIssue.PATH_COVERAGE_PARTIAL in issues:
        return PathState.UNKNOWN
    return PathState.EXACT


def _assess_semantic_owners(
    packet: AssessmentInput,
    issues: set[AssessmentIssue],
    health: dict[SourceReference, bool],
) -> SemanticOwnerAssessmentState:
    unknown = False
    conflict = False
    if (
        not packet.semantic_owners_complete
        or not _ref_current(health, packet.semantic_owners_source_ref)
    ):
        issues.add(AssessmentIssue.SEMANTIC_OWNER_COVERAGE_PARTIAL)
        unknown = True
    for path in sorted(packet.target.changed_paths):
        expectations = [
            item for item in packet.expected_semantic_owners if _path_contains(item.path_prefix, path)
        ]
        if len(expectations) == 0:
            issues.add(AssessmentIssue.SEMANTIC_OWNER_COVERAGE_PARTIAL)
            unknown = True
            continue
        if len(expectations) > 1:
            issues.add(AssessmentIssue.SEMANTIC_OWNER_AMBIGUOUS)
            conflict = True
            continue
        expectation = expectations[0]
        facts = [
            item
            for item in packet.semantic_owner_facts
            if item.active
            and _path_contains(item.path_prefix, path)
            and _ref_current(health, item.source_ref)
        ]
        unusable = [
            item
            for item in packet.semantic_owner_facts
            if item.active
            and _path_contains(item.path_prefix, path)
            and not _ref_current(health, item.source_ref)
        ]
        if unusable:
            issues.add(AssessmentIssue.SEMANTIC_OWNER_COVERAGE_PARTIAL)
            unknown = True
        if expectation.no_owner_allowed:
            if facts:
                issues.add(AssessmentIssue.SEMANTIC_OWNER_COLLISION)
                conflict = True
            continue
        matching = [
            item
            for item in facts
            if item.owner_id == expectation.owner_id and item.operation_key == packet.operation_key
        ]
        foreign = [item for item in facts if item not in matching]
        if foreign or len(matching) > 1:
            issues.add(AssessmentIssue.SEMANTIC_OWNER_COLLISION)
            conflict = True
        elif len(matching) == 0:
            issues.add(AssessmentIssue.SEMANTIC_OWNER_COVERAGE_PARTIAL)
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
    health: dict[SourceReference, bool],
) -> CarrierAssessmentState:
    if not packet.carriers_complete or not _ref_current(health, packet.carriers_source_ref):
        issues.add(AssessmentIssue.CARRIER_COVERAGE_PARTIAL)
    usable = [item for item in packet.carrier_facts if _ref_current(health, item.source_ref)]
    if len(usable) != len(packet.carrier_facts):
        issues.add(AssessmentIssue.CARRIER_COVERAGE_PARTIAL)
    touching = [item for item in usable if _carrier_touches_target(item, packet.target)]
    foreign = [item for item in touching if item.operation_key != packet.operation_key]
    operation_candidates = [
        item for item in usable if item.active and item.operation_key == packet.operation_key
    ]
    exact = [item for item in operation_candidates if _carrier_exact(item, packet)]
    if (
        foreign
        or len(operation_candidates) > 1
        or (len(operation_candidates) == 1 and len(exact) != 1)
    ):
        issues.add(AssessmentIssue.OPERATION_CARRIER_CONFLICT)
        return CarrierAssessmentState.CONFLICT
    if len(operation_candidates) == 0:
        issues.add(AssessmentIssue.OPERATION_CARRIER_NOT_FOUND)
        return CarrierAssessmentState.UNKNOWN
    if AssessmentIssue.CARRIER_COVERAGE_PARTIAL in issues:
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
    health: dict[SourceReference, bool],
) -> WriterAssessmentState:
    if not packet.writers_complete or not _ref_current(health, packet.writers_source_ref):
        issues.add(AssessmentIssue.WRITER_COVERAGE_PARTIAL)
    usable = [item for item in packet.writer_facts if _ref_current(health, item.source_ref)]
    if len(usable) != len(packet.writer_facts):
        issues.add(AssessmentIssue.WRITER_COVERAGE_PARTIAL)
    active = [item for item in usable if _writer_touches_target(item, packet)]
    if len(active) > 1:
        issues.add(AssessmentIssue.CARRIER_WRITER_CONFLICT)
        return WriterAssessmentState.CONFLICT
    if len(active) != 1:
        issues.add(AssessmentIssue.CARRIER_WRITER_NOT_FOUND)
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
        issues.add(AssessmentIssue.CARRIER_WRITER_CONFLICT)
        return WriterAssessmentState.CONFLICT
    if AssessmentIssue.WRITER_COVERAGE_PARTIAL in issues:
        return WriterAssessmentState.UNKNOWN
    return WriterAssessmentState.EXACT


def _assess_collisions(
    packet: AssessmentInput,
    issues: set[AssessmentIssue],
    health: dict[SourceReference, bool],
) -> None:
    if (
        not packet.path_collisions_complete
        or not _ref_current(health, packet.path_collisions_source_ref)
    ):
        issues.add(AssessmentIssue.PATH_COLLISION_COVERAGE_PARTIAL)
    for collision in packet.path_collisions:
        if not _ref_current(health, collision.source_ref):
            issues.add(AssessmentIssue.PATH_COLLISION_COVERAGE_PARTIAL)
            continue
        if collision.other_operation_key == packet.operation_key:
            continue
        if any(_paths_overlap(collision.path, path) for path in packet.target.changed_paths):
            issues.add(AssessmentIssue.PATH_COLLISION)


def _assess_checks(
    packet: AssessmentInput,
    issues: set[AssessmentIssue],
    health: dict[SourceReference, bool],
) -> CheckAssessmentState:
    branch = {_identity_key(item) for item in packet.branch_required_checks}
    required = {_identity_key(item) for item in packet.assessment_required_checks}
    allowed_non_success = {_identity_key(item) for item in packet.allowed_non_success_checks}
    if not branch.issubset(required):
        issues.add(AssessmentIssue.BRANCH_REQUIRED_CHECK_OMITTED)
    required |= branch
    unknown = not packet.checks_complete or not _ref_current(health, packet.checks_source_ref)
    pending = False
    failed = False
    if unknown:
        issues.add(AssessmentIssue.CHECK_COVERAGE_PARTIAL)

    for identity in sorted(required):
        all_attempts = [
            item
            for item in packet.check_attempts
            if _identity_key(item.identity) == identity and item.head_sha == packet.target.candidate_sha
        ]
        attempts = [item for item in all_attempts if _ref_current(health, item.source_ref)]
        if len(attempts) != len(all_attempts):
            issues.add(AssessmentIssue.CHECK_COVERAGE_PARTIAL)
            unknown = True
        if not attempts:
            if packet.checks_complete and _ref_current(health, packet.checks_source_ref) and not all_attempts:
                issues.add(AssessmentIssue.CHECK_MISSING)
                pending = True
            else:
                unknown = True
            continue
        latest = max(attempts, key=lambda item: (item.attempt, item.sequence))
        if latest.superseded:
            issues.add(AssessmentIssue.CHECK_SUPERSEDED)
            unknown = True
            continue
        if latest.status in {CheckStatus.QUEUED, CheckStatus.IN_PROGRESS}:
            issues.add(AssessmentIssue.CHECK_PENDING)
            pending = True
            continue
        conclusion = latest.conclusion
        if conclusion is CheckConclusion.SUCCESS:
            continue
        if conclusion is CheckConclusion.SKIPPED:
            if identity in allowed_non_success and not latest.applicable:
                continue
            issues.add(AssessmentIssue.CHECK_SKIPPED_NOT_ALLOWED)
            failed = True
            continue
        if conclusion is CheckConclusion.NEUTRAL:
            if identity in allowed_non_success and not latest.applicable:
                continue
            issues.add(AssessmentIssue.CHECK_NEUTRAL_NOT_ALLOWED)
            failed = True
            continue
        if conclusion is CheckConclusion.CANCELLED:
            issues.add(AssessmentIssue.CHECK_CANCELLED)
            failed = True
            continue
        if conclusion is CheckConclusion.UNKNOWN:
            issues.add(AssessmentIssue.CHECK_COVERAGE_PARTIAL)
            unknown = True
            continue
        issues.add(AssessmentIssue.CHECK_FAILED)
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
    health: dict[SourceReference, bool],
) -> ReviewAssessmentState:
    unknown = not packet.reviews_complete or not _ref_current(health, packet.reviews_source_ref)
    if unknown:
        issues.add(AssessmentIssue.REVIEW_COVERAGE_PARTIAL)
    effective: dict[str, ReviewEvent] = {}
    for event in packet.review_events:
        if event.head_sha != packet.target.candidate_sha:
            continue
        if not _ref_current(health, event.source_ref):
            issues.add(AssessmentIssue.REVIEW_COVERAGE_PARTIAL)
            unknown = True
            continue
        current = effective.get(event.reviewer_id)
        if current is None or event.sequence > current.sequence:
            effective[event.reviewer_id] = event
    if any(item.state is ReviewState.CHANGES_REQUESTED for item in effective.values()):
        issues.add(AssessmentIssue.CHANGES_REQUESTED)
    approvals = sum(item.state is ReviewState.APPROVED for item in effective.values())
    if approvals < packet.required_approvals:
        issues.add(AssessmentIssue.REVIEW_REQUIRED)
    if packet.unresolved_required_threads > 0:
        issues.add(AssessmentIssue.UNRESOLVED_REVIEW_THREAD)
    if AssessmentIssue.CHANGES_REQUESTED in issues:
        return ReviewAssessmentState.BLOCKED
    if unknown:
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
    health: dict[SourceReference, bool],
) -> tuple[ProductionAssessmentState, CompletionClaimState]:
    required = packet.production_proof_required or (
        packet.claimed_capability_state is CapabilityState.PROVEN_LIVE
    )
    proof = packet.production_proof
    if proof is None:
        if required:
            issues.add(AssessmentIssue.PRODUCTION_PROOF_MISSING)
            if packet.claimed_capability_state is CapabilityState.PROVEN_LIVE:
                issues.add(AssessmentIssue.COMPLETION_CLAIM_OVERSTATED)
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
    if proof.source_ref.observed_at != proof.observed_at:
        exact = False
    if not _ref_current(health, proof.source_ref):
        exact = False
    if not exact:
        issues.add(AssessmentIssue.PRODUCTION_PROOF_INVALID)
    if proof.observed_at > packet.observed_at:
        issues.add(AssessmentIssue.PRODUCTION_PROOF_FUTURE)
    elif packet.observed_at - proof.observed_at > packet.production_max_age_seconds:
        issues.add(AssessmentIssue.PRODUCTION_PROOF_STALE)
    if proof.coverage is SourceCoverage.CONFLICT:
        issues.add(AssessmentIssue.PRODUCTION_PROOF_INVALID)
    elif proof.coverage is not SourceCoverage.COMPLETE:
        issues.add(AssessmentIssue.PRODUCTION_PROOF_PARTIAL)
    if proof.state is ProductionProofState.MISSING:
        issues.add(AssessmentIssue.PRODUCTION_PROOF_MISSING)
    elif proof.state is ProductionProofState.PARTIAL:
        issues.add(AssessmentIssue.PRODUCTION_PROOF_PARTIAL)
    elif proof.state is ProductionProofState.UNKNOWN:
        issues.add(AssessmentIssue.PRODUCTION_PROOF_UNKNOWN)

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
        issues.add(AssessmentIssue.COMPLETION_CLAIM_OVERSTATED)
        return (
            ProductionAssessmentState.MISSING
            if proof.state is ProductionProofState.MISSING
            else ProductionAssessmentState.UNKNOWN,
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


def _assess_effect(
    packet: AssessmentInput,
    issues: set[AssessmentIssue],
    health: dict[SourceReference, bool],
) -> EffectState:
    effective = packet.prior_effect_state
    receipt = packet.merged_effect_receipt
    usable_receipt = receipt is not None and _ref_current(health, receipt.source_ref)
    if packet.prior_effect_state is EffectState.EFFECT_UNKNOWN:
        if usable_receipt and receipt is not None and _receipt_matches(packet, receipt):
            effective = EffectState.APPLIED
            issues.add(AssessmentIssue.PRIOR_EFFECT_APPLIED)
        else:
            issues.add(AssessmentIssue.PRIOR_EFFECT_UNKNOWN)
    elif packet.prior_effect_state is EffectState.APPLIED:
        issues.add(AssessmentIssue.PRIOR_EFFECT_APPLIED)
    elif packet.target.merged:
        if usable_receipt and receipt is not None and _receipt_matches(packet, receipt):
            effective = EffectState.APPLIED
            issues.add(AssessmentIssue.PRIOR_EFFECT_APPLIED)
        else:
            effective = EffectState.EFFECT_UNKNOWN
            issues.add(AssessmentIssue.PRIOR_EFFECT_CONFLICT)
    elif receipt is not None:
        issues.add(AssessmentIssue.PRIOR_EFFECT_CONFLICT)
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

    packet = _validate_input(packet)
    input_digest = _digest(_normalized_input_payload(packet))
    issues: set[AssessmentIssue] = set()
    health, reference_issues = _assess_source_references(packet, issues)
    source_state, source_current = _assess_current_source(
        packet, issues, health, reference_issues
    )
    merge_context_state = _assess_target(
        packet,
        issues,
        source_current=source_current,
        health=health,
    )
    path_state = _assess_paths(packet, issues, health)
    semantic_owner_state = _assess_semantic_owners(packet, issues, health)
    carrier_state = _assess_carriers(packet, issues, health)
    writer_state = _assess_writers(packet, issues, health)
    _assess_collisions(packet, issues, health)
    check_state = _assess_checks(packet, issues, health)
    review_state = _assess_reviews(packet, issues, health)
    production_state, completion_claim_state = _assess_production(packet, issues, health)
    effective_prior_effect_state = _assess_effect(packet, issues, health)

    if packet.requested_merge_method not in set(packet.allowed_merge_methods):
        issues.add(AssessmentIssue.MERGE_METHOD_REFUSED)

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
            organizational_authority_granted=False,
            production_acceptance_claimed=False,
        )

    ordered_issues = tuple(sorted(issues, key=lambda item: item.value))
    refs = tuple(sorted(set(_collect_source_references(packet)), key=_source_full_key))
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
        "expected_head_sha": packet.expected_target.expected_head_sha,
        "merge_base_sha": packet.target.merge_base_sha,
        "ahead_by": packet.target.ahead_by,
        "behind_by": packet.target.behind_by,
        "merge_context_state": merge_context_state.value,
        "path_state": path_state.value,
        "semantic_owner_state": semantic_owner_state.value,
        "semantic_collision_state": semantic_owner_state.value,
        "carrier_state": carrier_state.value,
        "writer_state": writer_state.value,
        "check_state": check_state.value,
        "review_state": review_state.value,
        "source_state": source_state.value,
        "source_law_state": source_state.value,
        "production_state": production_state.value,
        "production_proof_state": production_state.value,
        "completion_claim_state": completion_claim_state.value,
        "effective_prior_effect_state": effective_prior_effect_state.value,
        "expected_head_merge_eligible": verdict is AssessmentVerdict.ELIGIBLE,
        "expected_head_release": None if release is None else release.to_dict(),
        "claimed_capability_id": packet.claimed_capability_id,
        "claimed_capability_state": packet.claimed_capability_state.value,
        "issues": [item.value for item in ordered_issues],
        "source_refs": [item.to_dict() for item in refs],
        "input_digest": input_digest,
    }
    canonical_digest = _digest(output_without_digest)
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
        expected_head_sha=packet.expected_target.expected_head_sha,
        merge_base_sha=packet.target.merge_base_sha,
        ahead_by=packet.target.ahead_by,
        behind_by=packet.target.behind_by,
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
        canonical_digest=canonical_digest,
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
    "SourceOwner",
    "SourceReference",
    "SourceReferenceCoverage",
    "WriterAssessmentState",
    "WriterFact",
    "assess_github_release",
]
