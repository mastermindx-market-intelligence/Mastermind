"""Immutable, production-inert evidence ledger for the paired Z0 study.

The ledger is intentionally small and strict: a source generation, every
candidate query trial, and every failure becomes an append-only receipt.  It
does not invoke an indexer or a service; host-owned runners may feed it facts,
but cannot erase an inconvenient failure or turn synthetic proof into a
decision-eligible real evaluation.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from .baseline_search import AnswerKey
from .evaluation_manifest import EvaluationManifest, EvaluationQuery


LEDGER_SCHEMA_VERSION: Final = "mastermind.codeintel_z0_evaluation_ledger.v1"
QUERY_RECEIPT_SCHEMA_VERSION: Final = "mastermind.codeintel_discovery_query.v1"
INDEX_BUILD_RECEIPT_SCHEMA_VERSION: Final = "mastermind.codeintel_index_build.v1"
GENERATION_RECEIPT_SCHEMA_VERSION: Final = "mastermind.codeintel_generation.v1"
QUERY_TRIAL_RECEIPT_SCHEMA_VERSION: Final = "mastermind.codeintel_query_trial.v1"
GRADER_RECEIPT_SCHEMA_VERSION: Final = "mastermind.codeintel_grader.v1"
CLEANUP_RECEIPT_SCHEMA_VERSION: Final = "mastermind.codeintel_cleanup.v1"
CORRECTION_RECEIPT_SCHEMA_VERSION: Final = "mastermind.codeintel_correction.v1"
QUERY_RECEIPT_FAILURE_SCHEMA_VERSION: Final = (
    "mastermind.codeintel_query_receipt_failure.v1"
)
ZOEKT_FACADE_ACCEPTED_FOR_CI3: Final = "ZOEKT_FACADE_ACCEPTED_FOR_CI3"
ZOEKT_REQUIRES_ARCHITECTURE_REVISION: Final = "ZOEKT_REQUIRES_ARCHITECTURE_REVISION"
NO_SAFE_GLOBAL_INDEX: Final = "NO_SAFE_GLOBAL_INDEX"
UNKNOWN_RESOURCE: Final = "UNKNOWN"
_SHA1_RE: Final = re.compile(r"[0-9a-f]{40}\Z")
_SHA256_RE: Final = re.compile(r"[0-9a-f]{64}\Z")
_OUTCOMES: Final = frozenset({"completed", "timeout", "error", "cancelled"})
_GENERATION_STATUSES: Final = frozenset({"succeeded", "failed", "partial"})
_QUERY_STATUSES: Final = frozenset(
    {
        "SUCCESS",
        "ZERO_RESULTS",
        "DEGRADED",
        "STALE",
        "PARTIAL",
        "TRUNCATED",
        "REFUSED",
        "TIMEOUT",
        "CANCELLED",
        "INDEX_FAILED",
        "SCHEMA_INVALID",
        "EFFECT_UNKNOWN",
    }
)
_COVERAGE_VALUES: Final = frozenset(
    {
        "FULLY_COVERED",
        "PARTIALLY_COVERED",
        "EXCLUDED_BY_POLICY",
        "REPOSITORY_ABSENT",
        "REF_ABSENT",
        "SOURCE_IDENTITY_MISMATCH",
        "UNKNOWN",
    }
)
_HEALTH_VALUES: Final = frozenset(
    {
        "HEALTHY",
        "BUILDING",
        "STALE",
        "PARTIAL",
        "FAILED",
        "DEGRADED",
        "CORRUPT",
        "INDEX_ABSENT",
        "UNKNOWN",
    }
)
_FRESHNESS_VALUES: Final = frozenset(
    {
        "EXACT_SHA_CURRENT",
        "SOURCE_MOVED_WITHIN_TARGET",
        "SOURCE_MOVED_BEYOND_TARGET",
        "AGE_BUDGET_EXCEEDED",
        "SOURCE_TIME_UNKNOWN",
    }
)
_QUERY_COMPLETENESS_VALUES: Final = frozenset(
    {
        "COMPLETE",
        "TRUNCATED",
        "CANCELLED",
        "TIMED_OUT",
        "MALFORMED",
        "EXPENSIVE_QUERY_REFUSED",
        "UNKNOWN",
    }
)
_ZERO_RESULT_AUTHORITY_VALUES: Final = frozenset(
    {
        "AUTHORITATIVE_NOT_FOUND_ON_HEALTHY_COVERED_EXACT_REF",
        "NONAUTHORITATIVE_COVERAGE_GAP",
        "NONAUTHORITATIVE_STALE_OR_MOVED",
        "NONAUTHORITATIVE_UNHEALTHY",
        "NONAUTHORITATIVE_TRUNCATED_OR_INCOMPLETE",
        "NONAUTHORITATIVE_IDENTITY_UNKNOWN",
        "NOT_APPLICABLE_MATCHES_RETURNED",
    }
)
_QUERY_RECEIPT_FAILURE_STAGES: Final = frozenset({"FACTORY", "VALIDATION"})
_QUERY_RECEIPT_FAILURE_CODES: Final = frozenset({"RESULT_SCHEMA_INVALID"})
_QUERY_RECEIPT_FIELDS: Final = frozenset(
    {
        "schema_version",
        "trial_id",
        "query_index",
        "candidate",
        "query_digest",
        "normalized_arguments_digest",
        "evaluation_manifest_digest",
        "requested_sources",
        "index_identity",
        "started_at",
        "ended_at",
        "monotonic_duration_ms",
        "status",
        "coverage",
        "health",
        "freshness",
        "query_completeness",
        "matches",
        "limits",
        "zero_result_authority",
        "canonical_verification_required",
        "resource_observation",
        "security_observation",
        "cleanup_observation",
        "raw_response_digest",
        "normalized_response_digest",
        "correction_of",
    }
)
_FAILURE_CODES: Final = frozenset(
    {
        "CREDENTIAL_UNAVAILABLE",
        "CORRUPT_INDEX",
        "DISK_BUDGET_EXCEEDED",
        "EXTERNAL_PATH",
        "INCOMPLETE_SOURCE",
        "PROCESS_CRASH",
        "SOURCE_MOVED",
        "SUBMODULE_UNRESOLVED",
        "SYMLINK_REJECTED",
        "TIMEOUT",
        "TOOLCHAIN_UNAVAILABLE",
        "SOURCE_HEAD_OR_TREE_MISMATCH",
        "INCOMPLETE_SOURCE_MANIFEST",
        "FAILED_BUILD_PUBLISHED",
        "PARTIAL_BUILD_PUBLISHED",
        "CORRUPT_SHARD",
        "DISK_PRESSURE",
        "CREDENTIAL_ACCESS_ATTEMPT",
        "DUPLICATE_REPOSITORY_IDENTITY",
        "SOURCE_ROOT_SYMLINK",
        "SUBMODULE_ESCAPE",
        "EXTERNAL_PATH_TRAVERSAL",
        "QUERY_TIMEOUT",
        "QUERY_CANCELLED",
        "INCOMPLETE_DESIRED_SET",
        "GENERATION_RACE",
        "RESULT_SCHEMA_INVALID",
    }
)
REQUIRED_FAILURE_INJECTIONS: Final = (
    "SOURCE_HEAD_OR_TREE_MISMATCH",
    "INCOMPLETE_SOURCE_MANIFEST",
    "FAILED_BUILD_PUBLISHED",
    "PARTIAL_BUILD_PUBLISHED",
    "CORRUPT_SHARD",
    "DISK_PRESSURE",
    "CREDENTIAL_ACCESS_ATTEMPT",
    "DUPLICATE_REPOSITORY_IDENTITY",
    "SOURCE_ROOT_SYMLINK",
    "SUBMODULE_ESCAPE",
    "EXTERNAL_PATH_TRAVERSAL",
    "QUERY_TIMEOUT",
    "QUERY_CANCELLED",
    "INCOMPLETE_DESIRED_SET",
    "GENERATION_RACE",
)


class EvidenceError(ValueError):
    """A receipt would make the empirical evidence ambiguous or self-serving."""


class QueryReceiptError(EvidenceError):
    """A raw candidate response cannot be normalized into the closed query contract."""


@dataclass(frozen=True)
class NormalizedQueryReceipt:
    """Immutable, model-safe query facts with mechanically derived absence authority."""

    trial_id: str
    candidate: str
    query_digest: str
    evaluation_manifest_digest: str
    status: str
    query_completeness: str
    zero_result_authority: str
    payload: Mapping[str, object]
    canonical_bytes: bytes
    digest: str


def parse_normalized_query_receipt(
    document: bytes | bytearray | str | Mapping[str, object],
) -> NormalizedQueryReceipt:
    """Validate one closed query receipt and derive its absence authority.

    This is intentionally separate from any backend parser: raw HTTP/JSON
    facts must be normalized, bounded, and identity-attested before a grader or
    decision gate can consume them.
    """

    payload = _strict_receipt_json(document)
    _exact_receipt_fields(payload, _QUERY_RECEIPT_FIELDS, "query receipt")
    if payload["schema_version"] != QUERY_RECEIPT_SCHEMA_VERSION:
        raise QueryReceiptError("query receipt has an unexpected schema_version")
    trial_id = _receipt_text(payload["trial_id"], "trial_id")
    if ":" not in trial_id:
        raise QueryReceiptError("trial_id must bind case and candidate")
    case_id, candidate_from_trial = trial_id.split(":", 1)
    if not case_id or candidate_from_trial not in {"baseline", "zoekt"}:
        raise QueryReceiptError("trial_id must bind a closed candidate")
    candidate = _receipt_text(payload["candidate"], "candidate")
    if candidate != candidate_from_trial:
        raise QueryReceiptError("candidate must agree with trial_id")
    query_digest = _receipt_sha256(payload["query_digest"], "query_digest")
    evaluation_manifest_digest = _receipt_sha256(
        payload["evaluation_manifest_digest"], "evaluation_manifest_digest"
    )
    _receipt_sha256(payload["normalized_arguments_digest"], "normalized_arguments_digest")
    _validate_requested_sources(payload["requested_sources"])
    _validate_index_identity(payload["index_identity"])
    _receipt_text(payload["started_at"], "started_at")
    _receipt_text(payload["ended_at"], "ended_at")
    _receipt_nonnegative_int(payload["monotonic_duration_ms"], "monotonic_duration_ms")
    status = _receipt_closed_value(payload["status"], _QUERY_STATUSES, "status")
    coverage = _receipt_closed_list(payload["coverage"], _COVERAGE_VALUES, "coverage")
    health = _receipt_closed_list(payload["health"], _HEALTH_VALUES, "health")
    freshness = _receipt_closed_list(payload["freshness"], _FRESHNESS_VALUES, "freshness")
    completeness = _receipt_closed_value(
        payload["query_completeness"],
        _QUERY_COMPLETENESS_VALUES,
        "query_completeness",
    )
    _validate_normalized_matches(payload["matches"])
    limits = _validate_limits(payload["limits"])
    if type(payload["canonical_verification_required"]) is not bool or not payload[
        "canonical_verification_required"
    ]:
        raise QueryReceiptError("canonical_verification_required must be true")
    _validate_resource_observation(payload["resource_observation"])
    _validate_security_observation(payload["security_observation"])
    _validate_cleanup_observation(payload["cleanup_observation"])
    raw_response_digest = _receipt_digest_or_unknown(
        payload["raw_response_digest"], "raw_response_digest"
    )
    normalized_response_digest = _receipt_digest_or_unknown(
        payload["normalized_response_digest"], "normalized_response_digest"
    )
    if payload["correction_of"] is not None:
        _receipt_sha256(payload["correction_of"], "correction_of")
    expected_zero_authority = derive_zero_result_authority(
        coverage=coverage,
        health=health,
        freshness=freshness,
        query_completeness=completeness,
        truncated=limits["truncated"],
        returned_count=limits["returned_count"],
        response_identity_known=(
            raw_response_digest != UNKNOWN_RESOURCE
            and normalized_response_digest != UNKNOWN_RESOURCE
        ),
    )
    supplied_zero_authority = _receipt_closed_value(
        payload["zero_result_authority"],
        _ZERO_RESULT_AUTHORITY_VALUES,
        "zero_result_authority",
    )
    if supplied_zero_authority != expected_zero_authority:
        raise QueryReceiptError(
            "zero_result_authority must be mechanically derived from normalized state"
        )
    if status == "ZERO_RESULTS" and limits["returned_count"] != 0:
        raise QueryReceiptError("ZERO_RESULTS status requires returned_count zero")
    if status == "SUCCESS" and limits["returned_count"] == 0:
        raise QueryReceiptError("SUCCESS status requires a normalized returned match")
    canonical = _canonical_json(payload)
    frozen = _freeze_receipt_json(payload)
    assert isinstance(frozen, Mapping)
    return NormalizedQueryReceipt(
        trial_id=trial_id,
        candidate=candidate,
        query_digest=query_digest,
        evaluation_manifest_digest=evaluation_manifest_digest,
        status=status,
        query_completeness=completeness,
        zero_result_authority=expected_zero_authority,
        payload=frozen,
        canonical_bytes=canonical,
        digest=hashlib.sha256(canonical).hexdigest(),
    )


def derive_zero_result_authority(
    *,
    coverage: tuple[str, ...],
    health: tuple[str, ...],
    freshness: tuple[str, ...],
    query_completeness: str,
    truncated: bool,
    returned_count: int,
    response_identity_known: bool,
) -> str:
    """Derive the sole absence authority value from closed normalized state."""

    if returned_count > 0:
        return "NOT_APPLICABLE_MATCHES_RETURNED"
    if not response_identity_known:
        return "NONAUTHORITATIVE_IDENTITY_UNKNOWN"
    if "SOURCE_IDENTITY_MISMATCH" in coverage or "UNKNOWN" in coverage:
        return "NONAUTHORITATIVE_IDENTITY_UNKNOWN"
    if any(value != "FULLY_COVERED" for value in coverage):
        return "NONAUTHORITATIVE_COVERAGE_GAP"
    if any(value != "HEALTHY" for value in health):
        return "NONAUTHORITATIVE_UNHEALTHY"
    if any(value != "EXACT_SHA_CURRENT" for value in freshness):
        return "NONAUTHORITATIVE_STALE_OR_MOVED"
    if query_completeness != "COMPLETE" or truncated:
        return "NONAUTHORITATIVE_TRUNCATED_OR_INCOMPLETE"
    return "AUTHORITATIVE_NOT_FOUND_ON_HEALTHY_COVERED_EXACT_REF"


@dataclass(frozen=True)
class ResourceObservation:
    """Measured host resource use, with unknown explicitly distinct from zero."""

    cpu_ms: int | str
    rss_bytes: int | str
    disk_bytes: int | str

    def __post_init__(self) -> None:
        for label, value in (
            ("cpu_ms", self.cpu_ms),
            ("rss_bytes", self.rss_bytes),
            ("disk_bytes", self.disk_bytes),
        ):
            if value != UNKNOWN_RESOURCE and (type(value) is not int or value < 0):
                raise EvidenceError(f"{label} must be a non-negative integer or UNKNOWN")

    @property
    def is_known(self) -> bool:
        return all(
            value != UNKNOWN_RESOURCE
            for value in (self.cpu_ms, self.rss_bytes, self.disk_bytes)
        )

    def to_payload(self) -> dict[str, int | str]:
        return {
            "cpu_ms": self.cpu_ms,
            "rss_bytes": self.rss_bytes,
            "disk_bytes": self.disk_bytes,
        }


@dataclass(frozen=True)
class GenerationReceipt:
    """One repository/ref indexing result, whether it succeeded or failed."""

    generation_id: str
    logical_repo_id: str
    source_commit: str
    source_tree: str
    status: str
    indexed_commit_sha: str | None
    shard_digest: str | None
    failure_code: str | None


@dataclass(frozen=True)
class PublicationReceipt:
    """The explicit result of trying to publish one whole source generation."""

    generation_id: str
    state: str
    active_generation_id: str | None


@dataclass(frozen=True)
class FailureInjectionReceipt:
    """One immutable adversarial proof and any cleanup/correction lineage."""

    failure_code: str
    outcome: str
    cleanup_state: str
    correction_of: str | None
    evidence_digest: str


@dataclass(frozen=True)
class QueryReceiptFailureReceipt:
    """One receipt-normalization failure retained for its preregistered trial."""

    trial_id: str
    stage: str
    failure_code: str
    evidence_digest: str


@dataclass(frozen=True)
class TrialReceipt:
    """One trial from the preregistered alternating candidate order."""

    trial_id: str
    attempt_index: int
    outcome: str
    answer_key_digest: str
    source_census_digest: str
    generation_id: str
    query_completed: bool
    truncated: bool
    returned_identities: tuple[tuple[str, str, str, str, int, int], ...]
    recall: float
    false_positive_count: int
    resource: ResourceObservation
    failure_code: str | None


@dataclass(frozen=True)
class CandidateTrialObservation:
    """The sole candidate-provided facts consumed by the immutable trial record."""

    outcome: str
    query_completed: bool
    truncated: bool
    returned_identities: tuple[tuple[str, str, str, str, int, int], ...]
    resource: ResourceObservation
    failure_code: str | None


TrialExecutor = Callable[[EvaluationQuery], CandidateTrialObservation]
QueryReceiptFactory = Callable[
    [EvaluationQuery, str, int, CandidateTrialObservation],
    NormalizedQueryReceipt,
]


@dataclass(frozen=True)
class TrialGrade:
    """Source-derived grade for a candidate's returned source identities."""

    recall: float
    false_positive_count: int


@dataclass(frozen=True)
class EvaluationEvidence:
    """Frozen summary for the result gate; it is not itself a decision."""

    state: str
    manifest_digest: str
    source_census_digest: str
    ledger_digest: str
    run_kind: str
    active_generation_id: str | None
    required_trial_count: int
    recorded_trial_count: int
    failed_trial_count: int
    required_failure_injection_count: int
    recorded_failure_injection_count: int
    all_resources_known: bool
    all_identity_bound: bool
    reasons: tuple[str, ...]
    canonical_bytes: bytes

    def to_result_payload(self) -> dict[str, object]:
        return {
            "state": self.state,
            "manifest_digest": self.manifest_digest,
            "source_census_digest": self.source_census_digest,
            "ledger_digest": self.ledger_digest,
            "run_kind": self.run_kind,
            "active_generation_id": self.active_generation_id,
            "required_trial_count": self.required_trial_count,
            "recorded_trial_count": self.recorded_trial_count,
            "failed_trial_count": self.failed_trial_count,
            "required_failure_injection_count": self.required_failure_injection_count,
            "recorded_failure_injection_count": self.recorded_failure_injection_count,
            "all_resources_known": self.all_resources_known,
            "all_identity_bound": self.all_identity_bound,
            "reasons": list(self.reasons),
        }


def build_decision_from_evidence(
    evidence: EvaluationEvidence,
    *,
    repositories_safe: bool,
    ledger: EvaluationLedger,
    evaluation_manifest: EvaluationManifest,
    answer_keys: Mapping[str, AnswerKey],
) -> str:
    """Return a production-inert decision only from its bound ledger inputs."""

    if not isinstance(evidence, EvaluationEvidence):
        raise EvidenceError("decision builder requires EvaluationEvidence")
    if type(repositories_safe) is not bool:
        raise EvidenceError("repositories_safe must be a boolean")
    if not repositories_safe:
        return NO_SAFE_GLOBAL_INDEX
    if not isinstance(ledger, EvaluationLedger):
        raise EvidenceError("decision builder requires an EvaluationLedger")
    if not isinstance(evaluation_manifest, EvaluationManifest):
        raise EvidenceError("decision builder requires an EvaluationManifest")
    if not _manifest_binds_ledger(evaluation_manifest, ledger):
        return ZOEKT_REQUIRES_ARCHITECTURE_REVISION
    if not _answer_keys_bind_manifest(evaluation_manifest, answer_keys):
        return ZOEKT_REQUIRES_ARCHITECTURE_REVISION
    frozen = ledger.freeze()
    if evidence != frozen:
        return ZOEKT_REQUIRES_ARCHITECTURE_REVISION
    if not _trial_grades_bind_answer_keys(ledger, answer_keys):
        return ZOEKT_REQUIRES_ARCHITECTURE_REVISION
    if _bound_evidence_summary_is_acceptance_eligible(frozen):
        return ZOEKT_FACADE_ACCEPTED_FOR_CI3
    return ZOEKT_REQUIRES_ARCHITECTURE_REVISION


def _bound_evidence_summary_is_acceptance_eligible(
    evidence: EvaluationEvidence,
) -> bool:
    """Check the summary only after the builder bound it to its source ledger."""

    if (
        evidence.state != "ELIGIBLE_REAL_EMPIRICAL_EVIDENCE"
        or evidence.run_kind != "real"
        or not isinstance(evidence.active_generation_id, str)
        or not evidence.active_generation_id
        or len(evidence.active_generation_id.encode("utf-8")) > 256
        or type(evidence.required_trial_count) is not int
        or evidence.required_trial_count < 1
        or type(evidence.recorded_trial_count) is not int
        or evidence.recorded_trial_count < 1
        or evidence.recorded_trial_count != evidence.required_trial_count
        or type(evidence.failed_trial_count) is not int
        or evidence.failed_trial_count != 0
        or type(evidence.required_failure_injection_count) is not int
        or evidence.required_failure_injection_count < 1
        or type(evidence.recorded_failure_injection_count) is not int
        or evidence.recorded_failure_injection_count < 1
        or (
            evidence.recorded_failure_injection_count
            != evidence.required_failure_injection_count
        )
        or type(evidence.all_resources_known) is not bool
        or not evidence.all_resources_known
        or type(evidence.all_identity_bound) is not bool
        or not evidence.all_identity_bound
        or type(evidence.reasons) is not tuple
        or evidence.reasons
        or any(
            not isinstance(digest, str) or _SHA256_RE.fullmatch(digest) is None
            for digest in (
                evidence.manifest_digest,
                evidence.source_census_digest,
                evidence.ledger_digest,
            )
        )
    ):
        return False
    return True


def _manifest_binds_ledger(
    evaluation_manifest: EvaluationManifest,
    ledger: EvaluationLedger,
) -> bool:
    ledger_manifest = ledger.manifest
    return (
        ledger_manifest.digest == evaluation_manifest.digest
        and ledger_manifest.canonical_bytes == evaluation_manifest.canonical_bytes
        and (
            ledger_manifest.digest
            == hashlib.sha256(ledger_manifest.canonical_bytes).hexdigest()
        )
    )


def _answer_keys_bind_manifest(
    evaluation_manifest: EvaluationManifest,
    answer_keys: Mapping[str, AnswerKey],
) -> bool:
    if not isinstance(answer_keys, Mapping):
        return False
    expected_by_case = {
        query.case_id: query.answer_key_digest for query in evaluation_manifest.queries
    }
    if set(answer_keys) != set(expected_by_case):
        return False
    for case_id, expected_digest in expected_by_case.items():
        answer_key = answer_keys[case_id]
        if (
            not isinstance(answer_key, AnswerKey)
            or answer_key.case_id != case_id
            or answer_key.digest != expected_digest
        ):
            return False
    return True


def _trial_grades_bind_answer_keys(
    ledger: EvaluationLedger,
    answer_keys: Mapping[str, AnswerKey],
) -> bool:
    if tuple(item.trial_id for item in ledger.trial_receipts) != ledger.manifest.trial_order:
        return False
    for receipt in ledger.trial_receipts:
        case_id, _candidate = receipt.trial_id.split(":", 1)
        try:
            grade = grade_candidate_result(
                answer_keys[case_id], receipt.returned_identities
            )
        except (EvidenceError, KeyError):
            return False
        if (
            grade.recall != receipt.recall
            or grade.false_positive_count != receipt.false_positive_count
        ):
            return False
    return True


class EvaluationLedger:
    """Append-only in-memory ledger; its canonical bytes are the durable proof."""

    def __init__(
        self,
        manifest: EvaluationManifest,
        *,
        run_kind: str,
        source_census_digest: str,
    ) -> None:
        if not isinstance(manifest, EvaluationManifest):
            raise EvidenceError("ledger requires an EvaluationManifest")
        if run_kind not in {"real", "synthetic"}:
            raise EvidenceError("run_kind must be real or synthetic")
        _require_sha256(source_census_digest, "source_census_digest")
        self._manifest = manifest
        self._run_kind = run_kind
        self._source_census_digest = source_census_digest
        self._generation_receipts: list[GenerationReceipt] = []
        self._publication_receipts: list[PublicationReceipt] = []
        self._failure_injection_receipts: list[FailureInjectionReceipt] = []
        self._query_receipt_failure_receipts: list[QueryReceiptFailureReceipt] = []
        self._query_receipts: list[NormalizedQueryReceipt] = []
        self._trial_receipts: list[TrialReceipt] = []
        self._active_generation_id: str | None = None

    @property
    def manifest(self) -> EvaluationManifest:
        return self._manifest

    @property
    def generation_receipts(self) -> tuple[GenerationReceipt, ...]:
        return tuple(self._generation_receipts)

    @property
    def publication_receipts(self) -> tuple[PublicationReceipt, ...]:
        return tuple(self._publication_receipts)

    @property
    def query_receipts(self) -> tuple[NormalizedQueryReceipt, ...]:
        return tuple(self._query_receipts)

    @property
    def query_receipt_failure_receipts(self) -> tuple[QueryReceiptFailureReceipt, ...]:
        return tuple(self._query_receipt_failure_receipts)

    @property
    def failure_injection_receipts(self) -> tuple[FailureInjectionReceipt, ...]:
        return tuple(self._failure_injection_receipts)

    @property
    def trial_receipts(self) -> tuple[TrialReceipt, ...]:
        return tuple(self._trial_receipts)

    @property
    def active_generation_id(self) -> str | None:
        return self._active_generation_id

    def record_generation(self, receipt: GenerationReceipt) -> None:
        """Append one exact build outcome; source movement and omission are errors."""

        if not isinstance(receipt, GenerationReceipt):
            raise EvidenceError("generation receipt must be a GenerationReceipt")
        _require_identifier(receipt.generation_id, "generation_id")
        _require_identifier(receipt.logical_repo_id, "logical_repo_id")
        if receipt.status not in _GENERATION_STATUSES:
            raise EvidenceError("generation status is not in the closed vocabulary")
        expected = self._corpus_by_logical_id().get(receipt.logical_repo_id)
        if expected is None:
            raise EvidenceError("generation names an unregistered repository")
        if receipt.source_commit != expected["commit"]:
            raise EvidenceError("source_commit does not match frozen corpus")
        if receipt.source_tree != expected["tree"]:
            raise EvidenceError("source_tree does not match frozen corpus")
        _require_sha1(receipt.source_commit, "source_commit")
        _require_sha1(receipt.source_tree, "source_tree")
        key = (receipt.generation_id, receipt.logical_repo_id)
        if any(
            (item.generation_id, item.logical_repo_id) == key
            for item in self._generation_receipts
        ):
            raise EvidenceError("duplicate repository receipt in one generation")

        if receipt.status == "succeeded":
            if receipt.indexed_commit_sha is None:
                raise EvidenceError("succeeded generation requires indexed_commit_sha")
            if receipt.indexed_commit_sha != receipt.source_commit:
                raise EvidenceError("indexed_commit_sha does not bind source_commit")
            if receipt.shard_digest is None:
                raise EvidenceError("succeeded generation requires shard_digest")
            if receipt.failure_code is not None:
                raise EvidenceError("succeeded generation cannot have failure_code")
            _require_sha1(receipt.indexed_commit_sha, "indexed_commit_sha")
            _require_sha256(receipt.shard_digest, "shard_digest")
        else:
            if receipt.failure_code not in _FAILURE_CODES:
                raise EvidenceError("failed or partial generation requires known failure_code")
            if receipt.indexed_commit_sha is not None:
                _require_sha1(receipt.indexed_commit_sha, "indexed_commit_sha")
            if receipt.shard_digest is not None:
                _require_sha256(receipt.shard_digest, "shard_digest")
        self._generation_receipts.append(receipt)

    def publish_generation(self, generation_id: str) -> PublicationReceipt:
        """Publish only a complete healthy corpus; retain a prior healthy generation."""

        _require_identifier(generation_id, "generation_id")
        receipts = [
            item for item in self._generation_receipts if item.generation_id == generation_id
        ]
        expected_ids = set(self._corpus_by_logical_id())
        complete = (
            len(receipts) == len(expected_ids)
            and {item.logical_repo_id for item in receipts} == expected_ids
            and all(item.status == "succeeded" for item in receipts)
        )
        if complete:
            self._active_generation_id = generation_id
            receipt = PublicationReceipt(
                generation_id=generation_id,
                state="PUBLISHED",
                active_generation_id=generation_id,
            )
        else:
            receipt = PublicationReceipt(
                generation_id=generation_id,
                state="PUBLISH_REFUSED",
                active_generation_id=self._active_generation_id,
            )
        self._publication_receipts.append(receipt)
        return receipt

    def record_query_receipt(self, receipt: NormalizedQueryReceipt) -> None:
        """Append a closed normalized query before its corresponding trial receipt."""

        if not isinstance(receipt, NormalizedQueryReceipt):
            raise EvidenceError("query receipt must be a NormalizedQueryReceipt")
        if receipt.trial_id not in self._manifest.trial_order:
            raise EvidenceError("query receipt trial_id is not preregistered")
        if any(item.trial_id == receipt.trial_id for item in self._query_receipts):
            raise EvidenceError("query receipt duplicate trial_id")
        if any(
            item.trial_id == receipt.trial_id
            for item in self._query_receipt_failure_receipts
        ):
            raise EvidenceError("query receipt cannot replace a retained failure")
        if self._active_generation_id is None:
            raise EvidenceError("query receipt requires a published full generation")
        case_id, candidate = receipt.trial_id.split(":", 1)
        if receipt.candidate != candidate:
            raise EvidenceError("query receipt candidate does not bind trial_id")
        query = next(item for item in self._manifest.queries if item.case_id == case_id)
        if receipt.query_digest != query.query_digest:
            raise EvidenceError("query receipt query_digest does not bind frozen query")
        if receipt.evaluation_manifest_digest != self._manifest.digest:
            raise EvidenceError("query receipt evaluation manifest identity mismatch")
        index_identity = receipt.payload["index_identity"]
        assert isinstance(index_identity, Mapping)
        if index_identity["generation_id"] != self._active_generation_id:
            raise EvidenceError("query receipt generation is not current publication")
        if index_identity["generation_manifest_digest"] != self._manifest.digest:
            raise EvidenceError("query receipt generation manifest identity mismatch")
        if index_identity["source_epoch_digest"] != self._source_census_digest:
            raise EvidenceError("query receipt source epoch identity mismatch")
        requested_sources = receipt.payload["requested_sources"]
        assert isinstance(requested_sources, tuple)
        corpus_by_id = self._corpus_by_logical_id()
        requested_ids: set[str] = set()
        for source in requested_sources:
            if not isinstance(source, Mapping):
                raise EvidenceError("query receipt requested source shape is invalid")
            logical_id = source["logical_repository"]
            if not isinstance(logical_id, str) or logical_id not in corpus_by_id:
                raise EvidenceError("query receipt requested source identity is unregistered")
            expected_source = corpus_by_id[logical_id]
            canonical_digest = hashlib.sha256(
                expected_source["canonical_repository"].encode("utf-8")
            ).hexdigest()
            if (
                source["canonical_repository_digest"] != canonical_digest
                or source["requested_ref"] != expected_source["ref"]
                or source["requested_commit"] != expected_source["commit"]
                or source["requested_tree"] != expected_source["tree"]
            ):
                raise EvidenceError(
                    "query receipt requested source identity does not bind frozen corpus"
                )
            requested_ids.add(logical_id)
        if requested_ids != set(corpus_by_id):
            raise EvidenceError("query receipt requested source set is incomplete")
        self._query_receipts.append(receipt)

    def record_query_receipt_failure(self, receipt: QueryReceiptFailureReceipt) -> None:
        """Append one terminal receipt-normalization failure without a hidden retry."""

        if not isinstance(receipt, QueryReceiptFailureReceipt):
            raise EvidenceError("query receipt failure must have the closed receipt shape")
        if receipt.trial_id not in self._manifest.trial_order:
            raise EvidenceError("query receipt failure trial_id is not preregistered")
        if receipt.stage not in _QUERY_RECEIPT_FAILURE_STAGES:
            raise EvidenceError("query receipt failure stage is not in the closed vocabulary")
        if receipt.failure_code not in _QUERY_RECEIPT_FAILURE_CODES:
            raise EvidenceError("query receipt failure code is not in the closed vocabulary")
        _require_sha256(receipt.evidence_digest, "query receipt failure evidence_digest")
        if self._active_generation_id is None:
            raise EvidenceError("query receipt failure requires a published full generation")
        if any(item.trial_id == receipt.trial_id for item in self._query_receipts):
            raise EvidenceError("query receipt failure cannot replace a valid receipt")
        if any(
            item.trial_id == receipt.trial_id
            for item in self._query_receipt_failure_receipts
        ):
            raise EvidenceError("query receipt failure cannot be overwritten or duplicated")
        self._query_receipt_failure_receipts.append(receipt)

    def record_failure_injection(self, receipt: FailureInjectionReceipt) -> None:
        """Append one preregistered adversarial proof without rewriting its result."""

        if not isinstance(receipt, FailureInjectionReceipt):
            raise EvidenceError("failure injection must be a FailureInjectionReceipt")
        if receipt.failure_code not in REQUIRED_FAILURE_INJECTIONS:
            raise EvidenceError("failure injection is not preregistered")
        if any(
            item.failure_code == receipt.failure_code
            for item in self._failure_injection_receipts
        ):
            raise EvidenceError("failure injection cannot be overwritten or duplicated")
        if receipt.outcome != "REJECTED":
            raise EvidenceError("failure injection must record a rejecting outcome")
        if receipt.cleanup_state != "SUCCEEDED":
            raise EvidenceError("failure injection cleanup must be independently successful")
        if receipt.correction_of is not None:
            _require_sha256(receipt.correction_of, "correction_of")
        _require_sha256(receipt.evidence_digest, "evidence_digest")
        self._failure_injection_receipts.append(receipt)

    def record_trial(self, receipt: TrialReceipt) -> None:
        """Append exactly one result for each preregistered candidate trial."""

        if not isinstance(receipt, TrialReceipt):
            raise EvidenceError("trial receipt must be a TrialReceipt")
        if receipt.trial_id not in self._manifest.trial_order:
            raise EvidenceError("trial_id is not in the preregistered trial order")
        if any(item.trial_id == receipt.trial_id for item in self._trial_receipts):
            raise EvidenceError("retry is forbidden: every original trial remains evidence")
        if receipt.attempt_index != 1:
            raise EvidenceError("retry is forbidden: attempt_index must be one")
        if self._active_generation_id is None:
            raise EvidenceError("trial requires a published full generation")
        if receipt.generation_id != self._active_generation_id:
            raise EvidenceError("trial generation is not the active published generation")
        case_id, candidate = receipt.trial_id.split(":", 1)
        if candidate not in {"baseline", "zoekt"}:
            raise EvidenceError("trial candidate is not in the closed vocabulary")
        query = next(item for item in self._manifest.queries if item.case_id == case_id)
        if receipt.answer_key_digest != query.answer_key_digest:
            raise EvidenceError("trial answer_key_digest does not match frozen query")
        if receipt.source_census_digest != self._source_census_digest:
            raise EvidenceError("trial source_census_digest does not match ledger")
        _require_sha256(receipt.answer_key_digest, "answer_key_digest")
        _require_sha256(receipt.source_census_digest, "source_census_digest")
        _require_identifier(receipt.generation_id, "generation_id")
        if receipt.outcome not in _OUTCOMES:
            raise EvidenceError("trial outcome is not in the closed vocabulary")
        if type(receipt.query_completed) is not bool or type(receipt.truncated) is not bool:
            raise EvidenceError("query_completed and truncated must be booleans")
        if type(receipt.recall) not in {int, float} or not math.isfinite(receipt.recall):
            raise EvidenceError("recall must be finite")
        if not 0.0 <= receipt.recall <= 1.0:
            raise EvidenceError("recall must be in 0..1")
        if type(receipt.false_positive_count) is not int or receipt.false_positive_count < 0:
            raise EvidenceError("false_positive_count must be non-negative")
        if not isinstance(receipt.resource, ResourceObservation):
            raise EvidenceError("trial resource must be a ResourceObservation")
        _validate_identities(receipt.returned_identities)
        if receipt.outcome == "completed":
            if not receipt.query_completed or receipt.failure_code is not None:
                raise EvidenceError("completed trial must be complete without failure_code")
        else:
            if receipt.query_completed or receipt.failure_code not in _FAILURE_CODES:
                raise EvidenceError("failed trial requires incomplete query and known failure_code")
        self._trial_receipts.append(receipt)

    def freeze(self) -> EvaluationEvidence:
        """Return a deterministic evidence gate without mutating the ledger."""

        payload = self.to_payload()
        canonical = _canonical_json(payload)
        ledger_digest = hashlib.sha256(canonical).hexdigest()
        expected_trial_ids = set(self._manifest.trial_order)
        recorded_ids = {item.trial_id for item in self._trial_receipts}
        query_receipts_by_trial = {
            item.trial_id: item for item in self._query_receipts
        }
        queries_by_case = {item.case_id: item for item in self._manifest.queries}
        transport_failed = tuple(
            item
            for item in self._trial_receipts
            if item.outcome != "completed" or not item.query_completed or item.truncated
        )
        grade_failed = tuple(
            item
            for item in self._trial_receipts
            if _trial_grade_fails(
                item,
                queries_by_case[item.trial_id.split(":", 1)[0]],
            )
        )
        failed = tuple(
            item
            for item in self._trial_receipts
            if item in transport_failed or item in grade_failed
        )
        all_resources_known = all(item.resource.is_known for item in self._trial_receipts)
        all_query_receipts_eligible = (
            set(query_receipts_by_trial) == expected_trial_ids
            and all(
                _query_receipt_is_decision_eligible(receipt)
                for receipt in query_receipts_by_trial.values()
            )
        )
        all_failure_injections_recorded = {
            item.failure_code for item in self._failure_injection_receipts
        } == set(REQUIRED_FAILURE_INJECTIONS)
        all_identity_bound = (
            self._active_generation_id is not None
            and all(item.generation_id == self._active_generation_id for item in self._trial_receipts)
            and all(
                item.source_census_digest == self._source_census_digest
                for item in self._trial_receipts
            )
        )
        reasons: list[str] = []
        if recorded_ids != expected_trial_ids:
            reasons.append("MISSING_OR_UNEXPECTED_TRIALS")
        if not all_query_receipts_eligible:
            reasons.append("MISSING_OR_INELIGIBLE_QUERY_RECEIPT")
        if self._query_receipt_failure_receipts:
            reasons.append("QUERY_RECEIPT_NORMALIZATION_FAILURE")
        if not all_failure_injections_recorded:
            reasons.append("MISSING_FAILURE_INJECTIONS")
        if transport_failed:
            reasons.append("FAILED_OR_TRUNCATED_TRIAL")
        if grade_failed:
            reasons.append("TRIAL_GRADE_FAILURE")
        if not all_resources_known:
            reasons.append("UNKNOWN_RESOURCE_OBSERVATION")
        if not all_identity_bound:
            reasons.append("UNBOUND_GENERATION_OR_SOURCE")
        if self._run_kind == "synthetic":
            state = "NON_DECISION_SYNTHETIC_ONLY"
        elif reasons:
            state = "NON_DECISION_INCOMPLETE_EVIDENCE"
        else:
            state = "ELIGIBLE_REAL_EMPIRICAL_EVIDENCE"
        return EvaluationEvidence(
            state=state,
            manifest_digest=self._manifest.digest,
            source_census_digest=self._source_census_digest,
            ledger_digest=ledger_digest,
            run_kind=self._run_kind,
            active_generation_id=self._active_generation_id,
            required_trial_count=len(expected_trial_ids),
            recorded_trial_count=len(self._trial_receipts),
            failed_trial_count=len(failed),
            required_failure_injection_count=len(REQUIRED_FAILURE_INJECTIONS),
            recorded_failure_injection_count=len(self._failure_injection_receipts),
            all_resources_known=all_resources_known,
            all_identity_bound=all_identity_bound,
            reasons=tuple(reasons),
            canonical_bytes=canonical,
        )

    def to_payload(self) -> dict[str, object]:
        """Render the exact strict-JSON ledger document for schema validation."""

        return {
            "schema_version": LEDGER_SCHEMA_VERSION,
            "manifest_digest": self._manifest.digest,
            "source_census_digest": self._source_census_digest,
            "run_kind": self._run_kind,
            "generation_receipts": [
                _generation_payload(item) for item in self._generation_receipts
            ],
            "publication_receipts": [
                _publication_payload(item) for item in self._publication_receipts
            ],
            "failure_injection_receipts": [
                _failure_injection_payload(item)
                for item in self._failure_injection_receipts
            ],
            "query_receipt_failure_receipts": [
                _query_receipt_failure_payload(item)
                for item in self._query_receipt_failure_receipts
            ],
            "query_receipts": [
                _query_receipt_payload(item) for item in self._query_receipts
            ],
            "trial_receipts": [_trial_payload(item) for item in self._trial_receipts],
        }

    def _corpus_by_logical_id(self) -> dict[str, dict[str, str]]:
        return {str(item["logical_repo_id"]): dict(item) for item in self._manifest.corpus}


def run_paired_trials(
    ledger: EvaluationLedger,
    *,
    baseline_executor: TrialExecutor,
    zoekt_executor: TrialExecutor,
    answer_keys: Mapping[str, AnswerKey],
    query_receipt_factory: QueryReceiptFactory,
) -> tuple[TrialReceipt, ...]:
    """Run the frozen alternating order exactly once and retain every outcome.

    Executors receive the same immutable query declaration for a case. A
    timeout or callback crash becomes a typed failed trial and the remaining
    preregistered trials still run; callers cannot rerun only the bad row.
    """

    if not isinstance(ledger, EvaluationLedger):
        raise EvidenceError("paired harness requires an EvaluationLedger")
    if ledger.trial_receipts:
        raise EvidenceError("paired harness is one-shot; existing trials cannot be retried")
    if ledger.active_generation_id is None:
        raise EvidenceError("paired harness requires a published full generation")
    if not callable(baseline_executor) or not callable(zoekt_executor):
        raise EvidenceError("paired harness requires callable candidate executors")
    if not callable(query_receipt_factory):
        raise EvidenceError("paired harness requires a normalized query receipt factory")
    executors = {"baseline": baseline_executor, "zoekt": zoekt_executor}
    by_case = {query.case_id: query for query in ledger.manifest.queries}
    if not isinstance(answer_keys, Mapping) or set(answer_keys) != set(by_case):
        raise EvidenceError("paired harness requires one answer key per frozen case")
    for case_id, answer_key in answer_keys.items():
        if not isinstance(answer_key, AnswerKey) or answer_key.case_id != case_id:
            raise EvidenceError("answer key identity does not bind its frozen case")
        if answer_key.digest != by_case[case_id].answer_key_digest:
            raise EvidenceError("answer key bytes do not match the frozen query digest")
    receipts: list[TrialReceipt] = []
    for query_index, trial_id in enumerate(ledger.manifest.trial_order):
        case_id, candidate = trial_id.split(":", 1)
        query = by_case[case_id]
        try:
            observation = executors[candidate](query)
            if not isinstance(observation, CandidateTrialObservation):
                raise TypeError("candidate executor returned an invalid observation")
        except TimeoutError:
            observation = _callback_failure("timeout", "TIMEOUT")
        except Exception:
            observation = _callback_failure("error", "PROCESS_CRASH")
        try:
            query_receipt = query_receipt_factory(
                query,
                trial_id,
                query_index,
                observation,
            )
        except Exception as error:
            _retain_query_receipt_failure(ledger, trial_id, "FACTORY", error)
            observation = _callback_failure("error", "RESULT_SCHEMA_INVALID")
        else:
            try:
                if not isinstance(query_receipt, NormalizedQueryReceipt):
                    raise EvidenceError("query receipt factory returned an invalid receipt")
                ledger.record_query_receipt(query_receipt)
            except Exception as error:
                _retain_query_receipt_failure(ledger, trial_id, "VALIDATION", error)
                observation = _callback_failure("error", "RESULT_SCHEMA_INVALID")
        grade = grade_candidate_result(answer_keys[case_id], observation.returned_identities)
        receipt = TrialReceipt(
            trial_id=trial_id,
            attempt_index=1,
            outcome=observation.outcome,
            answer_key_digest=query.answer_key_digest,
            source_census_digest=ledger._source_census_digest,
            generation_id=ledger.active_generation_id,
            query_completed=observation.query_completed,
            truncated=observation.truncated,
            returned_identities=observation.returned_identities,
            recall=grade.recall,
            false_positive_count=grade.false_positive_count,
            resource=observation.resource,
            failure_code=observation.failure_code,
        )
        ledger.record_trial(receipt)
        receipts.append(receipt)
    return tuple(receipts)


def _callback_failure(outcome: str, failure_code: str) -> CandidateTrialObservation:
    return CandidateTrialObservation(
        outcome=outcome,
        query_completed=False,
        truncated=True,
        returned_identities=(),
        resource=ResourceObservation(
            cpu_ms=UNKNOWN_RESOURCE,
            rss_bytes=UNKNOWN_RESOURCE,
            disk_bytes=UNKNOWN_RESOURCE,
        ),
        failure_code=failure_code,
    )


def _retain_query_receipt_failure(
    ledger: EvaluationLedger,
    trial_id: str,
    stage: str,
    error: Exception,
) -> None:
    """Record a bounded failure identity without retaining raw callback output."""

    evidence = _canonical_json(
        {
            "trial_id": trial_id,
            "stage": stage,
            "exception_type": type(error).__name__,
        }
    )
    ledger.record_query_receipt_failure(
        QueryReceiptFailureReceipt(
            trial_id=trial_id,
            stage=stage,
            failure_code="RESULT_SCHEMA_INVALID",
            evidence_digest=hashlib.sha256(evidence).hexdigest(),
        )
    )


def grade_candidate_result(
    answer_key: AnswerKey,
    returned_identities: tuple[tuple[str, str, str, str, int, int], ...],
) -> TrialGrade:
    """Independently grade candidate output against direct-source answer bytes."""

    if not isinstance(answer_key, AnswerKey):
        raise EvidenceError("grader requires a source-derived AnswerKey")
    _validate_identities(answer_key.expected_identities)
    _validate_identities(answer_key.forbidden_identities)
    _validate_identities(returned_identities)
    expected = set(answer_key.expected_identities)
    forbidden = set(answer_key.forbidden_identities)
    if expected & forbidden:
        raise EvidenceError("answer key expected and forbidden identities overlap")
    returned = set(returned_identities)
    hits = len(expected & returned)
    recall = 1.0 if not expected else hits / len(expected)
    return TrialGrade(
        recall=recall,
        false_positive_count=len(returned - expected),
    )


def _trial_grade_fails(receipt: TrialReceipt, query: EvaluationQuery) -> bool:
    required_recall = max(query.recall_threshold, query.completeness_threshold)
    return (
        receipt.recall < required_recall
        or receipt.false_positive_count > query.false_positive_ceiling
    )


def _query_receipt_is_decision_eligible(receipt: NormalizedQueryReceipt) -> bool:
    """Require exact identity, bounded completion, and no unobserved side effect."""

    payload = receipt.payload
    coverage = payload["coverage"]
    health = payload["health"]
    freshness = payload["freshness"]
    limits = payload["limits"]
    resources = payload["resource_observation"]
    security = payload["security_observation"]
    cleanup = payload["cleanup_observation"]
    if not all(
        isinstance(value, Mapping)
        for value in (limits, resources, security, cleanup)
    ):
        return False
    if receipt.status not in {"SUCCESS", "ZERO_RESULTS"}:
        return False
    if receipt.query_completeness != "COMPLETE" or limits["truncated"] is not False:
        return False
    if coverage != ("FULLY_COVERED",) or health != ("HEALTHY",):
        return False
    if freshness != ("EXACT_SHA_CURRENT",):
        return False
    if any(value == UNKNOWN_RESOURCE for value in resources.values()):
        return False
    if any(value == UNKNOWN_RESOURCE for value in security.values()):
        return False
    if any(value != 0 for value in security.values()):
        return False
    if (
        cleanup["state"] != "SUCCEEDED"
        or cleanup["receipt_digest"] == UNKNOWN_RESOURCE
        or payload["raw_response_digest"] == UNKNOWN_RESOURCE
        or payload["normalized_response_digest"] == UNKNOWN_RESOURCE
    ):
        return False
    if receipt.status == "ZERO_RESULTS":
        return (
            receipt.zero_result_authority
            == "AUTHORITATIVE_NOT_FOUND_ON_HEALTHY_COVERED_EXACT_REF"
        )
    return receipt.zero_result_authority == "NOT_APPLICABLE_MATCHES_RETURNED"


def _query_receipt_payload(receipt: NormalizedQueryReceipt) -> dict[str, object]:
    payload = _thaw_receipt_json(receipt.payload)
    assert isinstance(payload, dict)
    return payload


def _strict_receipt_json(
    document: bytes | bytearray | str | Mapping[str, object],
) -> dict[str, object]:
    try:
        if isinstance(document, (bytes, bytearray)):
            parsed = json.loads(
                bytes(document).decode("utf-8"),
                object_pairs_hook=_receipt_no_duplicates,
                parse_constant=_receipt_reject_nonfinite,
            )
        elif isinstance(document, str):
            parsed = json.loads(
                document,
                object_pairs_hook=_receipt_no_duplicates,
                parse_constant=_receipt_reject_nonfinite,
            )
        elif isinstance(document, Mapping):
            parsed = dict(document)
        else:
            raise TypeError("receipt must be JSON bytes, text, or an object")
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as error:
        if isinstance(error, QueryReceiptError):
            raise
        raise QueryReceiptError("query receipt is not strict JSON") from error
    payload = _receipt_mapping(parsed, "query receipt")
    _assert_receipt_json_finite(payload)
    return dict(payload)


def _validate_requested_sources(value: object) -> None:
    if not isinstance(value, list) or not value:
        raise QueryReceiptError("requested_sources must be a non-empty list")
    identities: set[tuple[str, str, str]] = set()
    expected = frozenset(
        {
            "logical_repository",
            "canonical_repository_digest",
            "requested_ref",
            "requested_commit",
            "requested_tree",
        }
    )
    for index, raw in enumerate(value):
        source = _receipt_mapping(raw, f"requested_sources[{index}]")
        _exact_receipt_fields(source, expected, f"requested_sources[{index}]")
        logical_repository = _receipt_text(
            source["logical_repository"], "logical_repository"
        )
        canonical_digest = _receipt_sha256(
            source["canonical_repository_digest"], "canonical_repository_digest"
        )
        requested_ref = _receipt_text(source["requested_ref"], "requested_ref")
        _receipt_sha1(source["requested_commit"], "requested_commit")
        _receipt_sha1(source["requested_tree"], "requested_tree")
        identity = (logical_repository, canonical_digest, requested_ref)
        if identity in identities:
            raise QueryReceiptError("requested_sources contains duplicate identity")
        identities.add(identity)


def _validate_index_identity(value: object) -> None:
    identity = _receipt_mapping(value, "index_identity")
    expected = frozenset(
        {
            "generation_id",
            "generation_manifest_digest",
            "source_epoch_digest",
            "zoekt_source_commit",
            "zoekt_binary_digest",
            "go_toolchain_digest",
            "module_graph_digest",
            "ctags_disposition_digest",
            "configuration_digest",
            "sandbox_digest",
        }
    )
    _exact_receipt_fields(identity, expected, "index_identity")
    _receipt_text(identity["generation_id"], "generation_id")
    _receipt_sha256(identity["generation_manifest_digest"], "generation_manifest_digest")
    _receipt_sha256(identity["source_epoch_digest"], "source_epoch_digest")
    _receipt_sha1(identity["zoekt_source_commit"], "zoekt_source_commit")
    for field in (
        "zoekt_binary_digest",
        "go_toolchain_digest",
        "module_graph_digest",
        "ctags_disposition_digest",
        "configuration_digest",
        "sandbox_digest",
    ):
        _receipt_sha256(identity[field], field)


def _validate_limits(value: object) -> dict[str, object]:
    limits = _receipt_mapping(value, "limits")
    _exact_receipt_fields(
        limits,
        frozenset({"requested_limit", "returned_count", "total_known", "truncated"}),
        "limits",
    )
    requested_limit = _receipt_nonnegative_int(limits["requested_limit"], "requested_limit")
    if requested_limit < 1:
        raise QueryReceiptError("requested_limit must be positive")
    returned_count = _receipt_nonnegative_int(limits["returned_count"], "returned_count")
    total_known = _receipt_nonnegative_int(limits["total_known"], "total_known")
    if returned_count > total_known:
        raise QueryReceiptError("returned_count cannot exceed total_known")
    if type(limits["truncated"]) is not bool:
        raise QueryReceiptError("limits.truncated must be a boolean")
    return {
        "requested_limit": requested_limit,
        "returned_count": returned_count,
        "total_known": total_known,
        "truncated": limits["truncated"],
    }


def _validate_normalized_matches(value: object) -> None:
    if not isinstance(value, list):
        raise QueryReceiptError("matches must be a list")
    expected = frozenset(
        {
            "match_id",
            "logical_repository",
            "ref",
            "indexed_commit",
            "indexed_tree",
            "repository_relative_path",
            "range",
            "match_kind",
            "bounded_context_digest",
            "source_blob_digest",
            "index_shard_digest",
            "generation_manifest_digest",
        }
    )
    seen_ids: set[str] = set()
    for index, raw in enumerate(value):
        match = _receipt_mapping(raw, f"matches[{index}]")
        _exact_receipt_fields(match, expected, f"matches[{index}]")
        match_id = _receipt_sha256(match["match_id"], "match_id")
        if match_id in seen_ids:
            raise QueryReceiptError("matches contains duplicate match_id")
        seen_ids.add(match_id)
        for field in ("logical_repository", "ref", "repository_relative_path"):
            text = _receipt_text(match[field], field)
            if field == "repository_relative_path" and (
                text.startswith("/") or ".." in text.split("/")
            ):
                raise QueryReceiptError("match path must be repository relative")
        _receipt_sha1(match["indexed_commit"], "indexed_commit")
        _receipt_sha1(match["indexed_tree"], "indexed_tree")
        if match["match_kind"] not in {"CONTENT", "SYMBOL", "PATH", "FILE_NAME"}:
            raise QueryReceiptError("match_kind is not in the closed vocabulary")
        for field in (
            "bounded_context_digest",
            "source_blob_digest",
            "index_shard_digest",
            "generation_manifest_digest",
        ):
            _receipt_sha256(match[field], field)
        range_value = _receipt_mapping(match["range"], "match range")
        _exact_receipt_fields(
            range_value,
            frozenset({"start_line", "start_column", "end_line", "end_column"}),
            "match range",
        )
        for field in range_value:
            _receipt_nonnegative_int(range_value[field], f"match range.{field}")


def _validate_resource_observation(value: object) -> None:
    observation = _receipt_mapping(value, "resource_observation")
    _exact_receipt_fields(
        observation,
        frozenset(
            {
                "tool_calls",
                "peak_rss",
                "cpu_ms",
                "disk_io",
                "process_count",
                "open_file_peak",
            }
        ),
        "resource_observation",
    )
    for field, measurement in observation.items():
        _receipt_measurement(measurement, f"resource_observation.{field}")


def _validate_security_observation(value: object) -> None:
    observation = _receipt_mapping(value, "security_observation")
    _exact_receipt_fields(
        observation,
        frozenset(
            {
                "network_attempt_count",
                "credential_access_count",
                "source_write_count",
            }
        ),
        "security_observation",
    )
    for field, measurement in observation.items():
        _receipt_measurement(measurement, f"security_observation.{field}")


def _validate_cleanup_observation(value: object) -> None:
    observation = _receipt_mapping(value, "cleanup_observation")
    _exact_receipt_fields(
        observation,
        frozenset({"state", "receipt_digest"}),
        "cleanup_observation",
    )
    if observation["state"] not in {"SUCCEEDED", "FAILED", "NOT_REQUIRED", UNKNOWN_RESOURCE}:
        raise QueryReceiptError("cleanup_observation.state is not in the closed vocabulary")
    _receipt_digest_or_unknown(
        observation["receipt_digest"], "cleanup_observation.receipt_digest"
    )


def _receipt_mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise QueryReceiptError(f"{label} must be an object with string keys")
    return value


def _exact_receipt_fields(
    value: Mapping[str, object], expected: frozenset[str], label: str
) -> None:
    missing = expected - set(value)
    unknown = set(value) - expected
    if missing:
        raise QueryReceiptError(f"{label} missing fields: {sorted(missing)}")
    if unknown:
        raise QueryReceiptError(f"{label} has unknown fields: {sorted(unknown)}")


def _receipt_text(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value.encode("utf-8")) > 512
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise QueryReceiptError(f"{label} must be bounded printable text")
    return value


def _receipt_sha1(value: object, label: str) -> str:
    if not isinstance(value, str) or _SHA1_RE.fullmatch(value) is None:
        raise QueryReceiptError(f"{label} must be a lowercase SHA-1")
    return value


def _receipt_sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise QueryReceiptError(f"{label} must be a lowercase SHA-256")
    return value


def _receipt_digest_or_unknown(value: object, label: str) -> str:
    if value == UNKNOWN_RESOURCE:
        return UNKNOWN_RESOURCE
    return _receipt_sha256(value, label)


def _receipt_nonnegative_int(value: object, label: str) -> int:
    if type(value) is not int or value < 0:
        raise QueryReceiptError(f"{label} must be a non-negative integer")
    return value


def _receipt_measurement(value: object, label: str) -> int | str:
    if value == UNKNOWN_RESOURCE:
        return UNKNOWN_RESOURCE
    return _receipt_nonnegative_int(value, label)


def _receipt_closed_value(value: object, vocabulary: frozenset[str], label: str) -> str:
    if value not in vocabulary:
        raise QueryReceiptError(f"{label} is not in the closed vocabulary")
    assert isinstance(value, str)
    return value


def _receipt_closed_list(
    value: object, vocabulary: frozenset[str], label: str
) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise QueryReceiptError(f"{label} must be a non-empty list")
    values = tuple(_receipt_closed_value(item, vocabulary, label) for item in value)
    if len(values) != len(set(values)):
        raise QueryReceiptError(f"{label} must not contain duplicates")
    return values


def _receipt_no_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise QueryReceiptError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _receipt_reject_nonfinite(value: str) -> object:
    raise QueryReceiptError(f"non-finite JSON constant: {value}")


def _assert_receipt_json_finite(value: object) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise QueryReceiptError("query receipt has non-finite JSON value")
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise QueryReceiptError("query receipt object keys must be strings")
        for item in value.values():
            _assert_receipt_json_finite(item)
    elif isinstance(value, list):
        for item in value:
            _assert_receipt_json_finite(item)


def _freeze_receipt_json(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {str(key): _freeze_receipt_json(item) for key, item in value.items()}
        )
    if isinstance(value, list):
        return tuple(_freeze_receipt_json(item) for item in value)
    return value


def _thaw_receipt_json(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _thaw_receipt_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_receipt_json(item) for item in value]
    return value


def _generation_payload(receipt: GenerationReceipt) -> dict[str, object]:
    return {
        "schema_version": GENERATION_RECEIPT_SCHEMA_VERSION,
        "generation_id": receipt.generation_id,
        "logical_repo_id": receipt.logical_repo_id,
        "source_commit": receipt.source_commit,
        "source_tree": receipt.source_tree,
        "status": receipt.status,
        "indexed_commit_sha": receipt.indexed_commit_sha,
        "shard_digest": receipt.shard_digest,
        "failure_code": receipt.failure_code,
        "index_build_receipt": {
            "schema_version": INDEX_BUILD_RECEIPT_SCHEMA_VERSION,
            "logical_repo_id": receipt.logical_repo_id,
            "source_commit": receipt.source_commit,
            "source_tree": receipt.source_tree,
            "indexed_commit_sha": receipt.indexed_commit_sha,
            "shard_digest": receipt.shard_digest,
        },
    }


def _publication_payload(receipt: PublicationReceipt) -> dict[str, object]:
    return {
        "generation_id": receipt.generation_id,
        "state": receipt.state,
        "active_generation_id": receipt.active_generation_id,
    }


def _failure_injection_payload(receipt: FailureInjectionReceipt) -> dict[str, object]:
    return {
        "schema_version": CORRECTION_RECEIPT_SCHEMA_VERSION,
        "failure_code": receipt.failure_code,
        "outcome": receipt.outcome,
        "cleanup": {
            "schema_version": CLEANUP_RECEIPT_SCHEMA_VERSION,
            "state": receipt.cleanup_state,
        },
        "correction_of": receipt.correction_of,
        "evidence_digest": receipt.evidence_digest,
    }


def _query_receipt_failure_payload(
    receipt: QueryReceiptFailureReceipt,
) -> dict[str, object]:
    return {
        "schema_version": QUERY_RECEIPT_FAILURE_SCHEMA_VERSION,
        "trial_id": receipt.trial_id,
        "stage": receipt.stage,
        "failure_code": receipt.failure_code,
        "evidence_digest": receipt.evidence_digest,
    }


def _trial_payload(receipt: TrialReceipt) -> dict[str, object]:
    return {
        "schema_version": QUERY_TRIAL_RECEIPT_SCHEMA_VERSION,
        "trial_id": receipt.trial_id,
        "attempt_index": receipt.attempt_index,
        "outcome": receipt.outcome,
        "answer_key_digest": receipt.answer_key_digest,
        "source_census_digest": receipt.source_census_digest,
        "generation_id": receipt.generation_id,
        "query_completed": receipt.query_completed,
        "truncated": receipt.truncated,
        "returned_identities": [list(item) for item in receipt.returned_identities],
        "recall": receipt.recall,
        "false_positive_count": receipt.false_positive_count,
        "resource": receipt.resource.to_payload(),
        "failure_code": receipt.failure_code,
        "grader_receipt": {
            "schema_version": GRADER_RECEIPT_SCHEMA_VERSION,
            "answer_key_digest": receipt.answer_key_digest,
            "recall": receipt.recall,
            "false_positive_count": receipt.false_positive_count,
        },
    }


def _validate_identities(
    identities: tuple[tuple[str, str, str, str, int, int], ...]
) -> None:
    if not isinstance(identities, tuple):
        raise EvidenceError("returned_identities must be an immutable tuple")
    if len(identities) != len(set(identities)):
        raise EvidenceError("returned_identities must not contain duplicates")
    for identity in identities:
        if (
            not isinstance(identity, tuple)
            or len(identity) != 6
            or not all(isinstance(value, str) and value for value in identity[:4])
            or type(identity[4]) is not int
            or type(identity[5]) is not int
            or identity[4] < 1
            or identity[5] < identity[4]
        ):
            raise EvidenceError("returned identity has an invalid closed shape")


def _require_identifier(value: str, label: str) -> None:
    if not isinstance(value, str) or not value or len(value.encode("utf-8")) > 256:
        raise EvidenceError(f"{label} must be bounded non-empty text")


def _require_sha1(value: str, label: str) -> None:
    if not isinstance(value, str) or _SHA1_RE.fullmatch(value) is None:
        raise EvidenceError(f"{label} must be a lowercase SHA-1")


def _require_sha256(value: str, label: str) -> None:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise EvidenceError(f"{label} must be a lowercase SHA-256")


def _canonical_json(payload: object) -> bytes:
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("utf-8")
