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

from .baseline_search import AnswerKey, SourceCensus, SourceCensusError, census_sealed_sources
from .evaluation_manifest import EvaluationManifest, EvaluationQuery
from .index_manifest import IndexManifest


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
        "NONAUTHORITATIVE_SOURCE_SET_MISMATCH",
        "NOT_APPLICABLE_MATCHES_RETURNED",
    }
)
_QUERY_RECEIPT_FAILURE_STAGES: Final = frozenset({"FACTORY", "VALIDATION"})
_QUERY_RECEIPT_FAILURE_CODES: Final = frozenset({"RESULT_SCHEMA_INVALID"})
_ANSWER_KEY_PAYLOAD_FIELDS: Final = frozenset(
    {"case_id", "census_digest", "query", "path_policy_digest", "expected", "forbidden"}
)
_ANSWER_KEY_QUERY_FIELDS: Final = frozenset(
    {
        "query",
        "regex",
        "case_sensitive",
        "repository_ids",
        "refs",
        "path_prefixes",
        "languages",
        "limit",
        "context_lines",
        "timeout_ms",
    }
)
_ANSWER_KEY_MATCH_FIELDS: Final = frozenset(
    {"identity", "preview", "source_content_digest"}
)
_QUERY_RECEIPT_FIELDS: Final = frozenset(
    {
        "schema_version",
        "trial_id",
        "query_identity",
        "query_index",
        "candidate",
        "query_plan_digest",
        "query_digest",
        "normalized_arguments_digest",
        "evaluation_manifest_digest",
        "source_statuses",
        "index_identity",
        "started_at",
        "ended_at",
        "monotonic_duration_ms",
        "status",
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
_SOURCE_STATUS_FIELDS: Final = frozenset(
    {
        "logical_repository",
        "canonical_repository_digest",
        "requested_ref",
        "requested_commit",
        "requested_tree",
        "indexed_commit",
        "indexed_tree",
        "generation_id",
        "coverage",
        "health",
        "freshness",
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
class EvidenceError(ValueError):
    """A receipt would make the empirical evidence ambiguous or self-serving."""


class QueryReceiptError(EvidenceError):
    """A raw candidate response cannot be normalized into the closed query contract."""


@dataclass(frozen=True)
class QueryPlan:
    """One answer-key-derived execution object shared by both candidate adapters.

    It is deliberately richer than ``EvaluationQuery``: the latter is the
    public manifest projection, while the plan carries the only executable
    normalized query/filter bytes.  A candidate never receives a caller-made
    lookalike object or a case label detached from its repetition identity.
    """

    query_identity: str
    evaluation_manifest_digest: str
    case_id: str
    family: str
    repetition_index: int
    warm_or_cold: str
    query_index: int
    candidate_order: tuple[str, str]
    query: str
    regex: bool
    case_sensitive: bool
    logical_repo_ids: tuple[str, ...]
    refs: tuple[str, ...]
    path_prefixes: tuple[str, ...]
    languages: tuple[str, ...]
    max_results: int
    max_context_lines: int
    timeout_ms: int
    query_digest: str
    filters_digest: str
    answer_key_digest: str
    forbidden_answer_digest: str
    normalized_arguments_digest: str
    digest: str

    def trial_id(self, candidate: str) -> str:
        if candidate not in {"baseline", "zoekt"}:
            raise EvidenceError("query plan candidate is not in the closed vocabulary")
        return f"{self.query_identity}:{candidate}"


@dataclass(frozen=True)
class TrialIdentity:
    """The one immutable query/repetition/candidate address in the ledger."""

    query_identity: str
    candidate: str
    trial_id: str


@dataclass(frozen=True)
class NormalizedQueryReceipt:
    """Immutable, model-safe query facts with mechanically derived absence authority."""

    trial_id: str
    query_identity: str
    query_index: int
    candidate: str
    query_plan_digest: str
    query_digest: str
    normalized_arguments_digest: str
    evaluation_manifest_digest: str
    status: str
    query_completeness: str
    zero_result_authority: str
    payload: Mapping[str, object]
    canonical_bytes: bytes
    digest: str


def build_query_plan(
    evaluation_manifest: EvaluationManifest,
    query: EvaluationQuery,
    answer_key: AnswerKey,
) -> QueryPlan:
    """Derive the sole executable query object from the bound AnswerKey bytes.

    The manifest commits to digests and the source-derived answer key commits
    to the raw query.  Joining both documents here prevents a candidate from
    receiving query text, filters, or budgets that differ from the grader's
    truth.  Every returned field is frozen and hash-bound before either
    baseline or Zoekt is called.
    """

    if not isinstance(evaluation_manifest, EvaluationManifest):
        raise EvidenceError("query plan requires an EvaluationManifest")
    if not isinstance(query, EvaluationQuery):
        raise EvidenceError("query plan requires an EvaluationQuery")
    if not isinstance(answer_key, AnswerKey):
        raise EvidenceError("query plan requires a source-derived AnswerKey")
    if query not in evaluation_manifest.queries:
        raise EvidenceError("query plan query is not in the frozen manifest")
    if answer_key.case_id != query.case_id:
        raise EvidenceError("answer key case does not bind the frozen query")
    if hashlib.sha256(answer_key.canonical_bytes).hexdigest() != answer_key.digest:
        raise EvidenceError("answer key digest does not bind canonical bytes")
    if answer_key.digest != query.answer_key_digest:
        raise EvidenceError("answer key digest does not bind frozen query")
    try:
        answer_payload = _strict_receipt_json(answer_key.canonical_bytes)
        _exact_receipt_fields(answer_payload, _ANSWER_KEY_PAYLOAD_FIELDS, "answer key")
        if _canonical_json(answer_payload) != answer_key.canonical_bytes:
            raise EvidenceError("answer key must use canonical JSON")
        if answer_payload["case_id"] != query.case_id:
            raise EvidenceError("answer key canonical case does not bind frozen query")
        expected_policy_digest = evaluation_manifest.path_policy_rules.get(
            "policy_document_digest"
        )
        if (
            not isinstance(expected_policy_digest, str)
            or answer_payload["path_policy_digest"] != expected_policy_digest
            or answer_key.path_policy_digest != expected_policy_digest
        ):
            raise EvidenceError("answer key does not bind the frozen path-policy digest")
        raw_query = _receipt_mapping(answer_payload["query"], "answer key query")
        _validate_answer_key_query(raw_query)
        forbidden = _answer_key_forbidden_identities(answer_payload["forbidden"])
        expected = _answer_key_expected_identities(answer_payload["expected"])
        _validate_identities(answer_key.expected_identities)
        _validate_identities(answer_key.forbidden_identities)
    except (EvidenceError, QueryReceiptError) as error:
        raise EvidenceError("answer key cannot derive a query plan") from error
    if (
        expected != answer_key.expected_identities
        or forbidden != answer_key.forbidden_identities
        or set(expected) & set(forbidden)
    ):
        raise EvidenceError("answer key public identities disagree with canonical bytes")

    query_text = raw_query["query"]
    regex = raw_query["regex"]
    case_sensitive = raw_query["case_sensitive"]
    repository_ids = tuple(raw_query["repository_ids"])
    refs = tuple(raw_query["refs"])
    path_prefixes = tuple(raw_query["path_prefixes"])
    languages = tuple(raw_query["languages"])
    max_results = raw_query["limit"]
    max_context_lines = raw_query["context_lines"]
    timeout_ms = raw_query["timeout_ms"]
    assert isinstance(query_text, str)
    assert type(regex) is bool and type(case_sensitive) is bool
    assert isinstance(max_results, int)
    assert isinstance(max_context_lines, int)
    assert isinstance(timeout_ms, int)
    query_material = {
        "query": query_text,
        "regex": regex,
        "case_sensitive": case_sensitive,
    }
    filters_material = {
        "logical_repo_ids": list(repository_ids),
        "refs": list(refs),
        "path_prefixes": list(path_prefixes),
        "languages": list(languages),
        "max_results": max_results,
        "max_context_lines": max_context_lines,
        "timeout_ms": timeout_ms,
    }
    if hashlib.sha256(_canonical_json(query_material)).hexdigest() != query.query_digest:
        raise EvidenceError("query digest does not bind the answer-key query bytes")
    if hashlib.sha256(_canonical_json(filters_material)).hexdigest() != query.filters_digest:
        raise EvidenceError("filters digest does not bind the answer-key query filters")
    if (
        repository_ids != query.logical_repo_ids
        or refs != query.refs
        or path_prefixes != query.path_prefixes
        or languages != query.languages
        or max_results != query.max_results
        or max_context_lines != query.max_context_lines
        or timeout_ms != query.timeout_ms
    ):
        raise EvidenceError("answer-key query fields do not bind manifest query fields")
    if (
        hashlib.sha256(_canonical_json([list(item) for item in forbidden])).hexdigest()
        != query.forbidden_answer_digest
    ):
        raise EvidenceError("forbidden answer digest does not bind source-derived identities")
    normalized_material = {
        "query_identity": query.identity,
        "evaluation_manifest_digest": evaluation_manifest.digest,
        "case_id": query.case_id,
        "family": query.family,
        "repetition_index": query.repetition_index,
        "warm_or_cold": query.warm_or_cold,
        "query_index": query.query_index,
        "candidate_order": list(query.candidate_order),
        "query": query_material,
        "filters": filters_material,
        "query_digest": query.query_digest,
        "filters_digest": query.filters_digest,
        "answer_key_digest": query.answer_key_digest,
        "forbidden_answer_digest": query.forbidden_answer_digest,
    }
    normalized_arguments_digest = hashlib.sha256(
        _canonical_json(normalized_material)
    ).hexdigest()
    plan_digest = hashlib.sha256(
        _canonical_json(
            {
                "schema": "mastermind.codeintel_query_plan.v1",
                "normalized_arguments_digest": normalized_arguments_digest,
                "answer_key_digest": answer_key.digest,
            }
        )
    ).hexdigest()
    return QueryPlan(
        query_identity=query.identity,
        evaluation_manifest_digest=evaluation_manifest.digest,
        case_id=query.case_id,
        family=query.family,
        repetition_index=query.repetition_index,
        warm_or_cold=query.warm_or_cold,
        query_index=query.query_index,
        candidate_order=query.candidate_order,
        query=query_text,
        regex=regex,
        case_sensitive=case_sensitive,
        logical_repo_ids=repository_ids,
        refs=refs,
        path_prefixes=path_prefixes,
        languages=languages,
        max_results=max_results,
        max_context_lines=max_context_lines,
        timeout_ms=timeout_ms,
        query_digest=query.query_digest,
        filters_digest=query.filters_digest,
        answer_key_digest=query.answer_key_digest,
        forbidden_answer_digest=query.forbidden_answer_digest,
        normalized_arguments_digest=normalized_arguments_digest,
        digest=plan_digest,
    )


def parse_normalized_query_receipt(
    document: bytes | bytearray | str | Mapping[str, object],
    *,
    query_plan: QueryPlan,
) -> NormalizedQueryReceipt:
    """Validate one closed query receipt and derive its absence authority.

    This is intentionally separate from any backend parser: raw HTTP/JSON
    facts must be normalized, bounded, and identity-attested before a grader or
    decision gate can consume them.
    """

    if not isinstance(query_plan, QueryPlan):
        raise QueryReceiptError("query receipt requires its immutable QueryPlan")
    payload = _strict_receipt_json(document)
    _exact_receipt_fields(payload, _QUERY_RECEIPT_FIELDS, "query receipt")
    if payload["schema_version"] != QUERY_RECEIPT_SCHEMA_VERSION:
        raise QueryReceiptError("query receipt has an unexpected schema_version")
    trial_id = _receipt_text(payload["trial_id"], "trial_id")
    query_identity = _receipt_text(payload["query_identity"], "query_identity")
    candidate_from_trial = trial_id.rsplit(":", 1)[-1]
    if (
        candidate_from_trial not in {"baseline", "zoekt"}
        or trial_id != f"{query_identity}:{candidate_from_trial}"
    ):
        raise QueryReceiptError("trial_id must bind the full query identity and candidate")
    candidate = _receipt_text(payload["candidate"], "candidate")
    if candidate != candidate_from_trial:
        raise QueryReceiptError("candidate must agree with trial_id")
    query_index = _receipt_nonnegative_int(payload["query_index"], "query_index")
    if query_index < 1:
        raise QueryReceiptError("query_index must be positive")
    query_plan_digest = _receipt_sha256(payload["query_plan_digest"], "query_plan_digest")
    query_digest = _receipt_sha256(payload["query_digest"], "query_digest")
    evaluation_manifest_digest = _receipt_sha256(
        payload["evaluation_manifest_digest"], "evaluation_manifest_digest"
    )
    normalized_arguments_digest = _receipt_sha256(
        payload["normalized_arguments_digest"], "normalized_arguments_digest"
    )
    index_identity = _receipt_mapping(payload["index_identity"], "index_identity")
    _validate_index_identity(index_identity)
    generation_id = _receipt_text(index_identity["generation_id"], "generation_id")
    source_statuses = _validate_source_statuses(
        payload["source_statuses"], index_generation_id=generation_id
    )
    _validate_receipt_binds_query_plan(
        query_plan=query_plan,
        trial_id=trial_id,
        query_identity=query_identity,
        query_index=query_index,
        candidate=candidate,
        query_plan_digest=query_plan_digest,
        query_digest=query_digest,
        normalized_arguments_digest=normalized_arguments_digest,
        evaluation_manifest_digest=evaluation_manifest_digest,
        source_statuses=source_statuses,
    )
    _receipt_text(payload["started_at"], "started_at")
    _receipt_text(payload["ended_at"], "ended_at")
    _receipt_nonnegative_int(payload["monotonic_duration_ms"], "monotonic_duration_ms")
    status = _receipt_closed_value(payload["status"], _QUERY_STATUSES, "status")
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
        source_statuses=source_statuses,
        expected_logical_repo_ids=query_plan.logical_repo_ids,
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
        query_identity=query_identity,
        query_index=query_index,
        candidate=candidate,
        query_plan_digest=query_plan_digest,
        query_digest=query_digest,
        normalized_arguments_digest=normalized_arguments_digest,
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
    source_statuses: tuple[Mapping[str, object], ...],
    expected_logical_repo_ids: tuple[str, ...],
    query_completeness: str,
    truncated: bool,
    returned_count: int,
    response_identity_known: bool,
) -> str:
    """Derive the sole absence authority value from closed normalized state."""

    actual_logical_repo_ids = tuple(
        item.get("logical_repository") for item in source_statuses
    )
    if actual_logical_repo_ids != expected_logical_repo_ids:
        return "NONAUTHORITATIVE_SOURCE_SET_MISMATCH"
    if returned_count > 0:
        return "NOT_APPLICABLE_MATCHES_RETURNED"
    if not response_identity_known:
        return "NONAUTHORITATIVE_IDENTITY_UNKNOWN"
    if any(
        item.get("requested_commit") != item.get("indexed_commit")
        or item.get("requested_tree") != item.get("indexed_tree")
        for item in source_statuses
    ):
        return "NONAUTHORITATIVE_IDENTITY_UNKNOWN"
    coverage = tuple(item.get("coverage") for item in source_statuses)
    health = tuple(item.get("health") for item in source_statuses)
    freshness = tuple(item.get("freshness") for item in source_statuses)
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
class GenerationExecutionReceipt:
    """Measured build/publish environment for one immutable source generation."""

    evaluation_manifest_digest: str
    source_blob_census_digest: str
    source_path_policy_digest: str
    zoekt_source_commit: str
    zoekt_binary_digest: str
    go_toolchain_digest: str
    module_graph_digest: str
    ctags_disposition_digest: str
    configuration_digest: str
    sandbox_digest: str
    selected_file_count: int | str
    selected_byte_count: int | str
    shard_count: int | str
    build_ms: int | str
    refresh_ms: int | str
    query_ms: int | str
    cpu_ms: int | str
    rss_bytes: int | str
    disk_bytes: int | str
    disk_io_bytes: int | str
    process_count: int | str
    open_file_peak: int | str
    network_attempt_count: int | str
    credential_access_count: int | str
    source_write_count: int | str
    output_digest: str
    published_generation_id: str | None
    prior_generation_id: str | None
    effect: str
    cleanup_state: str
    cleanup_receipt_digest: str
    correction_of: str | None


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
    execution: GenerationExecutionReceipt | None = None


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
    execution: "FailureExecutionReceipt | None" = None


@dataclass(frozen=True)
class FailureExecutionReceipt:
    """Typed execution proof for one actual injected fault, not a caller label."""

    injection_id: str
    expected_failure_code: str
    observed_failure_code: str
    expected_effect: str
    observed_effect: str
    cleanup_state: str
    execution_receipt_digest: str


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
    query_identity: str
    query_index: int
    query_plan_digest: str
    normalized_arguments_digest: str
    query_receipt_digest: str
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


@dataclass(frozen=True)
class CandidateTransport:
    """Opaque candidate transport material; it contains no grader semantics."""

    receipt_document: bytes | bytearray | str | Mapping[str, object]


@dataclass(frozen=True)
class EvaluationBundleIdentity:
    """Exact host-captured bundle identities required by one real evidence run.

    This type intentionally carries only identities, not binary paths, endpoints,
    credentials, or an execution command.  The orchestration layer can therefore
    bind observed receipts to the reviewed bundle without gaining a mechanism to
    start a service, install a dependency, or access an account.
    """

    zoekt_source_commit: str
    zoekt_git_index_digest: str
    zoekt_webserver_digest: str
    go_toolchain_digest: str
    module_graph_digest: str
    ctags_disposition_digest: str
    configuration_digest: str
    sandbox_digest: str
    tool_schema_digest: str


@dataclass(frozen=True)
class CapturedCandidateAdapter:
    """Read-only transport capture for exactly one candidate implementation.

    Host runners may populate this object after they have performed an
    independently authorized disposable experiment.  It does not execute a
    command: it only returns the already-captured opaque receipt document for a
    frozen ``QueryPlan``.
    """

    candidate: str
    transports: Mapping[str, CandidateTransport]

    def __post_init__(self) -> None:
        if self.candidate not in {"baseline", "zoekt"}:
            raise EvidenceError("captured adapter candidate is not in the closed vocabulary")
        if not isinstance(self.transports, Mapping):
            raise EvidenceError("captured adapter transports must be a mapping")
        copied: dict[str, CandidateTransport] = {}
        for query_identity, transport in self.transports.items():
            if not isinstance(query_identity, str) or not query_identity:
                raise EvidenceError("captured adapter query identity is invalid")
            if not isinstance(transport, CandidateTransport):
                raise EvidenceError("captured adapter transport is invalid")
            copied[query_identity] = transport
        object.__setattr__(self, "transports", MappingProxyType(copied))

    def transport_for(self, plan: QueryPlan) -> CandidateTransport:
        """Return existing transport material; a missing row is retained as failure."""

        if not isinstance(plan, QueryPlan):
            raise EvidenceError("captured adapter requires a QueryPlan")
        transport = self.transports.get(plan.query_identity)
        if transport is None:
            raise EvidenceError("captured adapter is missing the frozen query transport")
        return transport


@dataclass(frozen=True)
class CapturedEvaluation:
    """A complete host capture consumed without any live runtime operation.

    The capture deliberately separates generation facts, paired candidate
    transport, adversarial fault receipts, and the final path/topology evidence.
    Every field is fed through the same append-only ledger validation used for
    direct test fixtures; this class merely removes production callbacks from
    the public orchestration entry point.
    """

    generation_id: str
    generation_receipts: tuple[GenerationReceipt, ...]
    baseline: CapturedCandidateAdapter
    zoekt: CapturedCandidateAdapter
    failure_injection_receipts: tuple[FailureInjectionReceipt, ...]
    decision_evidence: DecisionEvidence | None


@dataclass(frozen=True)
class EmpiricalEvaluationArtifacts:
    """Canonical in-memory evidence artifacts emitted by the inert orchestrator."""

    ledger_bytes: bytes
    ledger_digest: str
    evidence: EvaluationEvidence
    decision: str | None
    result_bytes: bytes
    result_digest: str


TrialExecutor = Callable[[QueryPlan], CandidateTransport]
QueryReceiptFactory = Callable[
    [QueryPlan, TrialIdentity, CandidateTransport],
    NormalizedQueryReceipt,
]


@dataclass(frozen=True)
class TrialGrade:
    """Source-derived grade for a candidate's returned source identities."""

    recall: float
    false_positive_count: int


@dataclass(frozen=True)
class ComparativeEvidence:
    """Closed measured comparison used by the decision law, never a caller vote."""

    metrics: Mapping[str, Mapping[str, float]]
    measurement_digest: str


@dataclass(frozen=True)
class DecisionEvidence:
    """Bound path/topology/freshness/reproducibility evidence for one final gate."""

    manifest_digest: str
    path_policy_id: str
    path_policy_measurements_digest: str
    p0_non_recall_justification: str | None
    topology_id: str
    topology_measurements_digest: str
    freshness_receipt_digest: str
    reproducibility_receipt_digest: str
    comparative: ComparativeEvidence
    safety_complete: bool
    correctness_complete: bool
    freshness_complete: bool
    reproducibility_complete: bool
    path_policy_complete: bool
    topology_complete: bool
    constitutional_failure: bool


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
    decision: str | None
    decision_evidence: DecisionEvidence | None
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
            "decision": self.decision,
            "decision_evidence": _decision_evidence_payload(self.decision_evidence),
            "reasons": list(self.reasons),
        }


def build_decision_from_evidence(
    evidence: EvaluationEvidence,
    *,
    ledger: EvaluationLedger,
    evaluation_manifest: EvaluationManifest,
    answer_keys: Mapping[str, AnswerKey],
) -> str | None:
    """Return a final only from complete real measured evidence, otherwise null."""

    if not isinstance(evidence, EvaluationEvidence):
        raise EvidenceError("decision builder requires EvaluationEvidence")
    if not isinstance(ledger, EvaluationLedger):
        raise EvidenceError("decision builder requires an EvaluationLedger")
    if not isinstance(evaluation_manifest, EvaluationManifest):
        raise EvidenceError("decision builder requires an EvaluationManifest")
    if not _manifest_binds_ledger(evaluation_manifest, ledger):
        return None
    if not _answer_keys_bind_manifest(evaluation_manifest, ledger, answer_keys):
        return None
    frozen = ledger.freeze()
    if evidence != frozen:
        return None
    if not _trial_grades_bind_answer_keys(ledger, answer_keys):
        return None
    if not _bound_evidence_summary_is_final_eligible(frozen):
        return None
    decision_evidence = frozen.decision_evidence
    assert decision_evidence is not None
    if decision_evidence.topology_id == "NO_SAFE_TOPOLOGY" or decision_evidence.constitutional_failure:
        return NO_SAFE_GLOBAL_INDEX
    if not _zoekt_has_preregistered_material_advantage(
        evaluation_manifest,
        decision_evidence.comparative,
    ):
        return ZOEKT_REQUIRES_ARCHITECTURE_REVISION
    return ZOEKT_FACADE_ACCEPTED_FOR_CI3


def _bound_evidence_summary_is_final_eligible(
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
        or evidence.decision is not None
        or not isinstance(evidence.decision_evidence, DecisionEvidence)
        or not _decision_evidence_is_complete(evidence.decision_evidence)
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


def _decision_evidence_is_complete(evidence: DecisionEvidence) -> bool:
    """Completion is a conjunction of observed safety, truth, and reproducibility."""

    return (
        evidence.safety_complete
        and evidence.correctness_complete
        and evidence.freshness_complete
        and evidence.reproducibility_complete
        and evidence.path_policy_complete
        and evidence.topology_complete
        and all(
            isinstance(value, str) and _SHA256_RE.fullmatch(value) is not None
            for value in (
                evidence.manifest_digest,
                evidence.path_policy_measurements_digest,
                evidence.topology_measurements_digest,
                evidence.freshness_receipt_digest,
                evidence.reproducibility_receipt_digest,
                evidence.comparative.measurement_digest,
            )
        )
    )


def _validate_comparative_metrics(metrics: Mapping[str, Mapping[str, float]]) -> None:
    if not isinstance(metrics, Mapping) or not metrics:
        raise EvidenceError("comparative metrics must be a non-empty mapping")
    for metric, values in metrics.items():
        _require_identifier(metric, "comparative metric")
        if not isinstance(values, Mapping) or set(values) != {"baseline", "zoekt"}:
            raise EvidenceError("comparative metric must contain baseline and zoekt values")
        for candidate, value in values.items():
            if type(value) not in {int, float} or not math.isfinite(float(value)) or value < 0:
                raise EvidenceError(f"comparative metric {metric}/{candidate} is invalid")


def _zoekt_has_preregistered_material_advantage(
    manifest: EvaluationManifest,
    comparative: ComparativeEvidence,
) -> bool:
    """Apply only manifest-supplied materiality rules; ties always stay baseline."""

    _validate_comparative_metrics(comparative.metrics)
    rules = manifest.materiality_bands
    positive_rules = rules.get("required_positive_advantage_any")
    if isinstance(positive_rules, tuple):
        for rule in positive_rules:
            if not isinstance(rule, Mapping):
                return False
            metric = rule.get("metric")
            if not isinstance(metric, str) or metric not in comparative.metrics:
                continue
            baseline = comparative.metrics[metric]["baseline"]
            zoekt = comparative.metrics[metric]["zoekt"]
            fraction = rule.get("zoekt_at_most_fraction_of_baseline")
            delta = rule.get("zoekt_minus_baseline_minimum")
            if (
                type(fraction) in {int, float}
                and baseline > 0
                and zoekt <= baseline * float(fraction)
            ):
                return True
            if type(delta) in {int, float} and zoekt - baseline >= float(delta):
                return True
        return False

    recall_delta = rules.get("minimum_recall_delta")
    latency_delta = rules.get("minimum_useful_latency_delta_ms")
    if type(recall_delta) not in {int, float} or type(latency_delta) not in {int, float}:
        return False
    recall = comparative.metrics.get("critical_path_recall")
    latency = comparative.metrics.get("time_to_first_useful_ms")
    return bool(
        recall is not None
        and recall["zoekt"] - recall["baseline"] > float(recall_delta)
        or latency is not None
        and latency["baseline"] - latency["zoekt"] > float(latency_delta)
    )


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
    ledger: EvaluationLedger,
    answer_keys: Mapping[str, AnswerKey],
) -> bool:
    if not isinstance(ledger, EvaluationLedger) or not isinstance(answer_keys, Mapping):
        return False
    expected_by_query = {
        query.identity: query.answer_key_digest
        for query in evaluation_manifest.queries
    }
    if set(answer_keys) != set(expected_by_query):
        return False
    for query in evaluation_manifest.queries:
        expected_digest = expected_by_query[query.identity]
        answer_key = answer_keys[query.identity]
        if (
            not isinstance(answer_key, AnswerKey)
            or answer_key.case_id != query.case_id
            or answer_key.digest != expected_digest
            or not _answer_key_binds_canonical_source(
                answer_key, ledger._source_census_digest
            )
        ):
            return False
        try:
            build_query_plan(evaluation_manifest, query, answer_key)
        except EvidenceError:
            return False
    return True


def _answer_key_binds_canonical_source(
    answer_key: AnswerKey,
    source_census_digest: str,
) -> bool:
    """Bind public grader fields to the immutable direct-source key bytes.

    ``AnswerKey`` is a dataclass for transport ergonomics, so its public
    digest or identity fields alone cannot be trusted at the decision edge.
    The frozen manifest commits to the canonical bytes; this verifier proves
    the digest, source epoch, and every grade-affecting identity agree with
    those bytes before the result can influence a decision.
    """

    if (
        not isinstance(answer_key, AnswerKey)
        or type(answer_key.canonical_bytes) is not bytes
        or not isinstance(answer_key.case_id, str)
        or not isinstance(answer_key.digest, str)
        or hashlib.sha256(answer_key.canonical_bytes).hexdigest()
        != answer_key.digest
    ):
        return False
    try:
        _require_sha256(answer_key.digest, "answer_key.digest")
        _require_sha256(source_census_digest, "source_census_digest")
        payload = _strict_receipt_json(answer_key.canonical_bytes)
        _exact_receipt_fields(payload, _ANSWER_KEY_PAYLOAD_FIELDS, "answer key")
        if _canonical_json(payload) != answer_key.canonical_bytes:
            return False
        if (
            _answer_key_text(payload["case_id"], "answer key case_id")
            != answer_key.case_id
        ):
            return False
        if payload["census_digest"] != source_census_digest:
            return False
        _require_sha256(payload["census_digest"], "answer key census_digest")
        if payload["path_policy_digest"] is not None:
            _require_sha256(payload["path_policy_digest"], "answer key path_policy_digest")
        _validate_answer_key_query(payload["query"])
        expected = _answer_key_expected_identities(payload["expected"])
        forbidden = _answer_key_forbidden_identities(payload["forbidden"])
        _validate_identities(answer_key.expected_identities)
        _validate_identities(answer_key.forbidden_identities)
    except (EvidenceError, QueryReceiptError, TypeError, ValueError):
        return False
    return (
        expected == answer_key.expected_identities
        and forbidden == answer_key.forbidden_identities
        and answer_key.path_policy_digest == payload["path_policy_digest"]
        and not (set(expected) & set(forbidden))
    )


def _validate_answer_key_query(value: object) -> None:
    """Accept only the canonical ``BaselineQuery`` payload shape."""

    query = _receipt_mapping(value, "answer key query")
    _exact_receipt_fields(query, _ANSWER_KEY_QUERY_FIELDS, "answer key query")
    query_text = _answer_key_text(query["query"], "answer key query.query")
    if type(query["regex"]) is not bool or type(query["case_sensitive"]) is not bool:
        raise EvidenceError("answer key query booleans are invalid")
    for field in ("repository_ids", "refs", "path_prefixes", "languages"):
        values = query[field]
        if (
            not isinstance(values, list)
            or any(not isinstance(item, str) or not item for item in values)
            or len(values) != len(set(values))
        ):
            raise EvidenceError(f"answer key query {field} is invalid")
    if type(query["limit"]) is not int or not 1 <= query["limit"] <= 100:
        raise EvidenceError("answer key query limit is invalid")
    if type(query["context_lines"]) is not int or not 0 <= query["context_lines"] <= 8:
        raise EvidenceError("answer key query context_lines is invalid")
    if type(query["timeout_ms"]) is not int or not 1 <= query["timeout_ms"] <= 60_000:
        raise EvidenceError("answer key query timeout_ms is invalid")
    flags = 0 if query["case_sensitive"] else re.IGNORECASE
    try:
        re.compile(query_text if query["regex"] else re.escape(query_text), flags)
    except re.error as error:
        raise EvidenceError("answer key query regex is invalid") from error


def _answer_key_expected_identities(
    value: object,
) -> tuple[tuple[str, str, str, str, int, int], ...]:
    if not isinstance(value, list):
        raise EvidenceError("answer key expected must be a list")
    identities: list[tuple[str, str, str, str, int, int]] = []
    for index, raw in enumerate(value):
        match = _receipt_mapping(raw, f"answer key expected[{index}]")
        _exact_receipt_fields(
            match, _ANSWER_KEY_MATCH_FIELDS, f"answer key expected[{index}]"
        )
        if not isinstance(match["preview"], str):
            raise EvidenceError("answer key expected preview is invalid")
        _require_sha256(
            match["source_content_digest"],
            "answer key expected source_content_digest",
        )
        identities.append(_answer_key_identity(match["identity"]))
    result = tuple(identities)
    _validate_identities(result)
    return result


def _answer_key_forbidden_identities(
    value: object,
) -> tuple[tuple[str, str, str, str, int, int], ...]:
    if not isinstance(value, list):
        raise EvidenceError("answer key forbidden must be a list")
    result = tuple(_answer_key_identity(raw) for raw in value)
    _validate_identities(result)
    return result


def _answer_key_identity(
    value: object,
) -> tuple[str, str, str, str, int, int]:
    if not isinstance(value, list) or len(value) != 6:
        raise EvidenceError("answer key identity has an invalid closed shape")
    identity = tuple(value)
    if (
        not all(isinstance(item, str) and item for item in identity[:4])
        or type(identity[4]) is not int
        or type(identity[5]) is not int
        or identity[4] < 1
        or identity[5] < identity[4]
    ):
        raise EvidenceError("answer key identity has an invalid closed shape")
    return (
        identity[0],
        identity[1],
        identity[2],
        identity[3],
        identity[4],
        identity[5],
    )


def _answer_key_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise EvidenceError(f"{label} must be non-empty text")
    return value


def _trial_grades_bind_answer_keys(
    ledger: EvaluationLedger,
    answer_keys: Mapping[str, AnswerKey],
) -> bool:
    if tuple(item.trial_id for item in ledger.trial_receipts) != ledger.manifest.trial_order:
        return False
    for receipt in ledger.trial_receipts:
        try:
            query, _identity = ledger._query_and_identity_for_trial(receipt.trial_id)
            grade = grade_candidate_result(
                answer_keys[query.identity], receipt.returned_identities
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
        self._query_plans: dict[str, QueryPlan] = {}
        self._decision_evidence: DecisionEvidence | None = None

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

    @property
    def query_plans(self) -> tuple[QueryPlan, ...]:
        """Return the bound immutable plans in manifest query order."""

        return tuple(self._query_plans[query.identity] for query in self._manifest.queries
                     if query.identity in self._query_plans)

    @property
    def decision_evidence(self) -> DecisionEvidence | None:
        return self._decision_evidence

    def record_decision_evidence(self, evidence: DecisionEvidence) -> None:
        """Append the one actual policy/topology comparison gate for this ledger."""

        if self._decision_evidence is not None:
            raise EvidenceError("decision evidence cannot be overwritten or retried")
        if not isinstance(evidence, DecisionEvidence):
            raise EvidenceError("decision evidence must have the closed receipt shape")
        if evidence.manifest_digest != self._manifest.digest:
            raise EvidenceError("decision evidence manifest digest does not bind this ledger")
        if evidence.path_policy_id not in self._manifest.path_policy_candidates:
            raise EvidenceError("decision evidence has an unregistered path policy")
        if evidence.topology_id not in {"T0", "T1", "NO_SAFE_TOPOLOGY"}:
            raise EvidenceError("decision evidence has an unknown topology")
        for label, value in (
            ("path_policy_measurements_digest", evidence.path_policy_measurements_digest),
            ("topology_measurements_digest", evidence.topology_measurements_digest),
            ("freshness_receipt_digest", evidence.freshness_receipt_digest),
            ("reproducibility_receipt_digest", evidence.reproducibility_receipt_digest),
        ):
            _require_sha256(value, label)
        if not isinstance(evidence.comparative, ComparativeEvidence):
            raise EvidenceError("decision evidence requires closed comparative measurements")
        _require_sha256(evidence.comparative.measurement_digest, "comparative measurement digest")
        _validate_comparative_metrics(evidence.comparative.metrics)
        for label, value in (
            ("safety_complete", evidence.safety_complete),
            ("correctness_complete", evidence.correctness_complete),
            ("freshness_complete", evidence.freshness_complete),
            ("reproducibility_complete", evidence.reproducibility_complete),
            ("path_policy_complete", evidence.path_policy_complete),
            ("topology_complete", evidence.topology_complete),
            ("constitutional_failure", evidence.constitutional_failure),
        ):
            if type(value) is not bool:
                raise EvidenceError(f"decision evidence {label} must be boolean")
        if evidence.path_policy_id == "P0":
            allowed = self._manifest.path_policy_rules.get(
                "p0_allowed_non_recall_justifications"
            )
            if (
                not isinstance(evidence.p0_non_recall_justification, str)
                or not isinstance(allowed, tuple)
                or evidence.p0_non_recall_justification not in allowed
            ):
                raise EvidenceError(
                    "P0 requires an actual preregistered non-recall justification"
                )
        elif evidence.p0_non_recall_justification is not None:
            raise EvidenceError("only P0 may carry a non-recall justification")
        self._decision_evidence = evidence

    def bind_query_plans(self, plans: Mapping[str, QueryPlan]) -> None:
        """Bind every manifest query to its one AnswerKey-derived execution plan.

        Plans must be bound before any receipt exists.  This prevents a caller
        from changing raw query bytes between the baseline execution, the
        Zoekt execution, and the grader's receipt validation.
        """

        if self._query_receipts or self._trial_receipts:
            raise EvidenceError("query plans must bind before any trial evidence")
        if not isinstance(plans, Mapping):
            raise EvidenceError("query plans must be a mapping")
        expected = {query.identity for query in self._manifest.queries}
        if set(plans) != expected:
            raise EvidenceError("query plans must cover every frozen manifest query")
        bound: dict[str, QueryPlan] = {}
        for query in self._manifest.queries:
            plan = plans[query.identity]
            if not isinstance(plan, QueryPlan):
                raise EvidenceError("query plans must contain QueryPlan entries")
            if (
                plan.query_identity != query.identity
                or plan.evaluation_manifest_digest != self._manifest.digest
                or plan.case_id != query.case_id
                or plan.family != query.family
                or plan.repetition_index != query.repetition_index
                or plan.warm_or_cold != query.warm_or_cold
                or plan.query_index != query.query_index
                or plan.candidate_order != query.candidate_order
                or plan.query_digest != query.query_digest
                or plan.filters_digest != query.filters_digest
                or plan.answer_key_digest != query.answer_key_digest
                or plan.forbidden_answer_digest != query.forbidden_answer_digest
                or plan.logical_repo_ids != query.logical_repo_ids
                or plan.refs != query.refs
                or plan.path_prefixes != query.path_prefixes
                or plan.languages != query.languages
                or plan.max_results != query.max_results
                or plan.max_context_lines != query.max_context_lines
                or plan.timeout_ms != query.timeout_ms
                or _SHA256_RE.fullmatch(plan.digest) is None
                or _SHA256_RE.fullmatch(plan.normalized_arguments_digest) is None
            ):
                raise EvidenceError("query plan does not bind its frozen manifest query")
            bound[query.identity] = plan
        self._query_plans = bound

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
        if receipt.execution is None:
            if self._run_kind == "real":
                raise EvidenceError("real generation requires measured execution receipt")
        else:
            self._validate_generation_execution(receipt, expected)
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
        query, identity = self._query_and_identity_for_trial(receipt.trial_id)
        if receipt.candidate != identity.candidate:
            raise EvidenceError("query receipt candidate does not bind trial_id")
        if receipt.query_identity != query.identity:
            raise EvidenceError("query receipt query identity does not bind trial_id")
        if receipt.query_index != query.query_index:
            raise EvidenceError("query receipt query index does not bind frozen query")
        plan = self._query_plans.get(query.identity)
        if plan is None:
            raise EvidenceError("query receipt requires a bound answer-key query plan")
        try:
            canonical_receipt = parse_normalized_query_receipt(
                receipt.canonical_bytes, query_plan=plan
            )
        except QueryReceiptError as error:
            raise EvidenceError(
                "query receipt canonical bytes do not satisfy the frozen query contract"
            ) from error
        if canonical_receipt != receipt:
            raise EvidenceError(
                "query receipt object does not bind its canonical normalized state"
            )
        if receipt.query_plan_digest != plan.digest:
            raise EvidenceError("query receipt query plan digest does not bind frozen query")
        if receipt.normalized_arguments_digest != plan.normalized_arguments_digest:
            raise EvidenceError(
                "query receipt normalized arguments do not bind frozen query plan"
            )
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
        source_statuses = receipt.payload["source_statuses"]
        assert isinstance(source_statuses, tuple)
        corpus_by_id = self._corpus_by_logical_id()
        source_ids: list[str] = []
        for source_status in source_statuses:
            if not isinstance(source_status, Mapping):
                raise EvidenceError("query receipt source status shape is invalid")
            logical_id = source_status["logical_repository"]
            if not isinstance(logical_id, str) or logical_id not in corpus_by_id:
                raise EvidenceError("query receipt source status identity is unregistered")
            expected_source = corpus_by_id[logical_id]
            canonical_digest = hashlib.sha256(
                expected_source["canonical_repository"].encode("utf-8")
            ).hexdigest()
            if (
                source_status["canonical_repository_digest"] != canonical_digest
                or source_status["requested_ref"] != expected_source["ref"]
                or source_status["requested_commit"] != expected_source["commit"]
                or source_status["requested_tree"] != expected_source["tree"]
                or source_status["indexed_commit"] != expected_source["commit"]
                or source_status["indexed_tree"] != expected_source["tree"]
                or source_status["generation_id"] != self._active_generation_id
            ):
                raise EvidenceError(
                    "query receipt source status does not bind frozen corpus/generation"
                )
            source_ids.append(logical_id)
        if tuple(source_ids) != plan.logical_repo_ids:
            raise EvidenceError(
                "query receipt source statuses do not bind the query source subset/order"
            )
        _observation_from_query_receipt(self, query, receipt)
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
        if receipt.failure_code not in self._manifest.failure_injections:
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
        execution = receipt.execution
        if not isinstance(execution, FailureExecutionReceipt):
            raise EvidenceError("failure injection requires a typed execution receipt")
        _require_identifier(execution.injection_id, "injection_id")
        if execution.injection_id != receipt.failure_code:
            raise EvidenceError("failure execution receipt does not bind preregistered injection")
        if (
            execution.expected_failure_code not in _FAILURE_CODES
            or execution.observed_failure_code != execution.expected_failure_code
        ):
            raise EvidenceError("failure execution receipt must retain the expected typed failure")
        if (
            execution.expected_effect not in {"PUBLISH_REFUSED", "NO_EFFECT"}
            or execution.observed_effect != execution.expected_effect
        ):
            raise EvidenceError("failure execution receipt effect does not match expected effect")
        if (
            execution.cleanup_state != "SUCCEEDED"
            or execution.cleanup_state != receipt.cleanup_state
        ):
            raise EvidenceError("failure execution receipt cleanup is not successful")
        _require_sha256(execution.execution_receipt_digest, "execution_receipt_digest")
        if receipt.evidence_digest != execution.execution_receipt_digest:
            raise EvidenceError("failure injection evidence must be its typed execution receipt")
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
        query, identity = self._query_and_identity_for_trial(receipt.trial_id)
        plan = self._query_plans.get(query.identity)
        if plan is None:
            raise EvidenceError("trial requires a bound answer-key query plan")
        query_receipt = next(
            (
                item
                for item in self._query_receipts
                if item.trial_id == receipt.trial_id
            ),
            None,
        )
        failure_receipt = next(
            (
                item
                for item in self._query_receipt_failure_receipts
                if item.trial_id == receipt.trial_id
            ),
            None,
        )
        if query_receipt is None and failure_receipt is None:
            raise EvidenceError(
                "trial requires its validated normalized query receipt or retained failure"
            )
        if (
            receipt.query_identity != query.identity
            or receipt.query_index != query.query_index
            or receipt.query_plan_digest != plan.digest
            or receipt.normalized_arguments_digest != plan.normalized_arguments_digest
        ):
            raise EvidenceError("trial does not bind its validated query receipt and plan")
        if query_receipt is not None and receipt.query_receipt_digest != query_receipt.digest:
            raise EvidenceError("trial does not bind its validated query receipt and plan")
        if failure_receipt is not None and receipt.query_receipt_digest != failure_receipt.evidence_digest:
            raise EvidenceError("trial does not bind its retained query receipt failure")
        if query_receipt is not None and query_receipt.candidate != identity.candidate:
            raise EvidenceError("trial receipt candidate does not bind query receipt")
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
        expected_observation = (
            _observation_from_query_receipt(self, query, query_receipt)
            if query_receipt is not None
            else _callback_failure("error", "RESULT_SCHEMA_INVALID")
        )
        if (
            receipt.outcome != expected_observation.outcome
            or receipt.query_completed != expected_observation.query_completed
            or receipt.truncated != expected_observation.truncated
            or receipt.returned_identities != expected_observation.returned_identities
            or receipt.resource != expected_observation.resource
            or receipt.failure_code != expected_observation.failure_code
        ):
            raise EvidenceError(
                "trial semantic observation must be mechanically derived from query receipt"
            )
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
        queries_by_identity = {
            item.identity: item for item in self._manifest.queries
        }
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
                queries_by_identity[
                    self._query_and_identity_for_trial(item.trial_id)[0].identity
                ],
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
        } == set(self._manifest.failure_injections)
        all_identity_bound = (
            self._active_generation_id is not None
            and all(item.generation_id == self._active_generation_id for item in self._trial_receipts)
            and all(
                item.source_census_digest == self._source_census_digest
                for item in self._trial_receipts
            )
        )
        all_generation_execution_eligible = all(
            _generation_execution_is_decision_eligible(item.execution)
            for item in self._generation_receipts
            if item.status == "succeeded"
        ) and bool(self._generation_receipts)
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
        if not all_generation_execution_eligible:
            reasons.append("INCOMPLETE_GENERATION_EXECUTION_RECEIPT")
        if self._decision_evidence is None:
            reasons.append("MISSING_PATH_TOPOLOGY_FRESHNESS_REPRODUCIBILITY_EVIDENCE")
        elif not _decision_evidence_is_complete(self._decision_evidence):
            reasons.append("INCOMPLETE_PATH_TOPOLOGY_FRESHNESS_REPRODUCIBILITY_EVIDENCE")
        if self._run_kind == "synthetic":
            reasons.append("SYNTHETIC_EVIDENCE")
        state = "NON_DECISION" if reasons else "ELIGIBLE_REAL_EMPIRICAL_EVIDENCE"
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
            required_failure_injection_count=len(self._manifest.failure_injections),
            recorded_failure_injection_count=len(self._failure_injection_receipts),
            all_resources_known=all_resources_known,
            all_identity_bound=all_identity_bound,
            decision=None,
            decision_evidence=self._decision_evidence,
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
            "decision_evidence": _decision_evidence_payload(self._decision_evidence),
        }

    def _corpus_by_logical_id(self) -> dict[str, dict[str, str]]:
        return {str(item["logical_repo_id"]): dict(item) for item in self._manifest.corpus}

    def _validate_generation_execution(
        self,
        receipt: GenerationReceipt,
        expected_source: Mapping[str, str],
    ) -> None:
        """Bind source, bundle, host safety, publish effect, and cleanup facts."""

        execution = receipt.execution
        assert isinstance(execution, GenerationExecutionReceipt)
        if execution.evaluation_manifest_digest != self._manifest.digest:
            raise EvidenceError("generation execution manifest digest does not bind ledger")
        if execution.source_blob_census_digest != expected_source["blob_census_digest"]:
            raise EvidenceError("generation execution source blob census does not bind corpus")
        if (
            execution.source_path_policy_digest
            != expected_source["include_exclude_policy_digest"]
        ):
            raise EvidenceError("generation execution path policy does not bind corpus")
        _require_sha1(execution.zoekt_source_commit, "zoekt_source_commit")
        for label, digest in (
            ("zoekt_binary_digest", execution.zoekt_binary_digest),
            ("go_toolchain_digest", execution.go_toolchain_digest),
            ("module_graph_digest", execution.module_graph_digest),
            ("ctags_disposition_digest", execution.ctags_disposition_digest),
            ("configuration_digest", execution.configuration_digest),
            ("sandbox_digest", execution.sandbox_digest),
            ("output_digest", execution.output_digest),
            ("cleanup_receipt_digest", execution.cleanup_receipt_digest),
        ):
            _require_sha256(digest, label)
        for label, value in (
            ("selected_file_count", execution.selected_file_count),
            ("selected_byte_count", execution.selected_byte_count),
            ("shard_count", execution.shard_count),
            ("build_ms", execution.build_ms),
            ("refresh_ms", execution.refresh_ms),
            ("query_ms", execution.query_ms),
            ("cpu_ms", execution.cpu_ms),
            ("rss_bytes", execution.rss_bytes),
            ("disk_bytes", execution.disk_bytes),
            ("disk_io_bytes", execution.disk_io_bytes),
            ("process_count", execution.process_count),
            ("open_file_peak", execution.open_file_peak),
            ("network_attempt_count", execution.network_attempt_count),
            ("credential_access_count", execution.credential_access_count),
            ("source_write_count", execution.source_write_count),
        ):
            if value != UNKNOWN_RESOURCE and (type(value) is not int or value < 0):
                raise EvidenceError(f"generation execution {label} is invalid")
        if execution.effect not in {"PUBLISHED", "PUBLISH_REFUSED", "UNKNOWN"}:
            raise EvidenceError("generation execution effect is not closed")
        if execution.cleanup_state not in {"SUCCEEDED", "FAILED", UNKNOWN_RESOURCE}:
            raise EvidenceError("generation execution cleanup state is not closed")
        if execution.correction_of is not None:
            _require_sha256(execution.correction_of, "generation execution correction_of")
        if receipt.status == "succeeded":
            if execution.effect not in {"PUBLISHED", "UNKNOWN"}:
                raise EvidenceError("successful generation has an invalid observed effect")
            if execution.published_generation_id not in {receipt.generation_id, None}:
                raise EvidenceError("generation execution published pointer is mismatched")
        elif execution.effect == "PUBLISHED":
            raise EvidenceError("failed or partial generation cannot publish")

    def _query_and_identity_for_trial(
        self, trial_id: str
    ) -> tuple[EvaluationQuery, TrialIdentity]:
        if not isinstance(trial_id, str) or ":" not in trial_id:
            raise EvidenceError("trial_id must bind a query identity and candidate")
        query_identity, candidate = trial_id.rsplit(":", 1)
        if candidate not in {"baseline", "zoekt"}:
            raise EvidenceError("trial candidate is not in the closed vocabulary")
        for query in self._manifest.queries:
            if query.identity == query_identity:
                return query, TrialIdentity(query_identity, candidate, trial_id)
        raise EvidenceError("trial_id is not in the preregistered query identity set")


def run_paired_trials(
    ledger: EvaluationLedger,
    *,
    baseline_executor: TrialExecutor,
    zoekt_executor: TrialExecutor,
    answer_keys: Mapping[str, AnswerKey],
    query_receipt_factory: QueryReceiptFactory,
) -> tuple[TrialReceipt, ...]:
    """Test-only paired harness over opaque transport inputs.

    Production uses :func:`run_empirical_evaluation`; this seam exists to
    exercise adversarial transport mutations.  It still gives both candidates
    the exact same immutable ``QueryPlan`` object for a query/repetition and
    derives every graded semantic field from a validated receipt, never from
    an executor-owned observation.
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
    if not _answer_keys_bind_manifest(ledger.manifest, ledger, answer_keys):
        raise EvidenceError("answer keys do not bind the frozen source-derived bytes")
    plans = {
        query.identity: build_query_plan(
            ledger.manifest,
            query,
            answer_keys[query.identity],
        )
        for query in ledger.manifest.queries
    }
    ledger.bind_query_plans(plans)
    receipts: list[TrialReceipt] = []
    for trial_id in ledger.manifest.trial_order:
        query, identity = ledger._query_and_identity_for_trial(trial_id)
        plan = plans[query.identity]
        query_receipt: NormalizedQueryReceipt | None = None
        query_receipt_failure_digest: str | None = None
        try:
            transport = executors[identity.candidate](plan)
            if not isinstance(transport, CandidateTransport):
                raise TypeError("candidate executor returned invalid transport material")
        except TimeoutError:
            error = TimeoutError("candidate transport timed out")
            _retain_query_receipt_failure(ledger, trial_id, "FACTORY", error)
            observation = _callback_failure("error", "RESULT_SCHEMA_INVALID")
            query_receipt_failure_digest = ledger.query_receipt_failure_receipts[-1].evidence_digest
        except Exception:
            error = RuntimeError("candidate transport failed")
            _retain_query_receipt_failure(ledger, trial_id, "FACTORY", error)
            observation = _callback_failure("error", "PROCESS_CRASH")
            query_receipt_failure_digest = ledger.query_receipt_failure_receipts[-1].evidence_digest
        else:
            try:
                query_receipt = query_receipt_factory(plan, identity, transport)
                if not isinstance(query_receipt, NormalizedQueryReceipt):
                    raise EvidenceError("query receipt factory returned an invalid receipt")
                ledger.record_query_receipt(query_receipt)
                observation = _observation_from_query_receipt(ledger, query, query_receipt)
            except Exception as error:
                _retain_query_receipt_failure(ledger, trial_id, "VALIDATION", error)
                observation = _callback_failure("error", "RESULT_SCHEMA_INVALID")
                query_receipt_failure_digest = ledger.query_receipt_failure_receipts[-1].evidence_digest
        grade = grade_candidate_result(
            answer_keys[query.identity], observation.returned_identities
        )
        receipt = TrialReceipt(
            trial_id=trial_id,
            query_identity=query.identity,
            query_index=query.query_index,
            query_plan_digest=plan.digest,
            normalized_arguments_digest=plan.normalized_arguments_digest,
            query_receipt_digest=(
                query_receipt.digest
                if query_receipt is not None
                else query_receipt_failure_digest
            ) or "0" * 64,
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


def run_empirical_evaluation(
    evaluation_manifest: EvaluationManifest,
    *,
    index_manifest: IndexManifest,
    source_census: SourceCensus,
    answer_keys: Mapping[str, AnswerKey],
    bundle: EvaluationBundleIdentity,
    capture: CapturedEvaluation,
    generated_at: str,
) -> EmpiricalEvaluationArtifacts:
    """Materialize one real evidence capture without launching a runtime.

    This is deliberately not a runner for Zoekt, a process manager, an endpoint
    creator, or an installation mechanism.  A separately authorized host may
    capture a disposable experiment, but this public entry point accepts only
    its typed receipts, proves them against the sealed source/bundle/plan, and
    returns canonical immutable artifact bytes.  An incomplete capture remains
    ``NON_DECISION``; it is never filled in, retried, or promoted here.
    """

    _validate_real_evaluation_inputs(
        evaluation_manifest,
        index_manifest=index_manifest,
        source_census=source_census,
        answer_keys=answer_keys,
        bundle=bundle,
        capture=capture,
        generated_at=generated_at,
    )
    ledger = EvaluationLedger(
        evaluation_manifest,
        run_kind="real",
        source_census_digest=source_census.digest,
    )
    if not _answer_keys_bind_manifest(evaluation_manifest, ledger, answer_keys):
        raise EvidenceError("answer keys do not bind the sealed real evaluation input")

    for receipt in capture.generation_receipts:
        _validate_generation_bundle_binding(receipt, bundle)
        ledger.record_generation(receipt)
    publication = ledger.publish_generation(capture.generation_id)

    plans = {
        query.identity: build_query_plan(
            evaluation_manifest,
            query,
            answer_keys[query.identity],
        )
        for query in evaluation_manifest.queries
    }
    ledger.bind_query_plans(plans)
    if publication.state == "PUBLISHED":
        _record_captured_paired_trials(
            ledger,
            plans=plans,
            answer_keys=answer_keys,
            bundle=bundle,
            baseline=capture.baseline,
            zoekt=capture.zoekt,
        )
    elif capture.baseline.transports or capture.zoekt.transports:
        raise EvidenceError(
            "captured query transports are forbidden when full generation publication failed"
        )

    for receipt in capture.failure_injection_receipts:
        ledger.record_failure_injection(receipt)
    if capture.decision_evidence is not None:
        ledger.record_decision_evidence(capture.decision_evidence)

    evidence = ledger.freeze()
    decision = build_decision_from_evidence(
        evidence,
        ledger=ledger,
        evaluation_manifest=evaluation_manifest,
        answer_keys=answer_keys,
    )
    ledger_bytes = _canonical_json(ledger.to_payload())
    ledger_digest = hashlib.sha256(ledger_bytes).hexdigest()
    result_payload = _result_payload_from_real_capture(
        ledger,
        evidence=evidence,
        decision=decision,
        bundle=bundle,
        generated_at=generated_at,
    )
    result_bytes = _canonical_json(result_payload)
    return EmpiricalEvaluationArtifacts(
        ledger_bytes=ledger_bytes,
        ledger_digest=ledger_digest,
        evidence=evidence,
        decision=decision,
        result_bytes=result_bytes,
        result_digest=hashlib.sha256(result_bytes).hexdigest(),
    )


def _validate_real_evaluation_inputs(
    evaluation_manifest: EvaluationManifest,
    *,
    index_manifest: IndexManifest,
    source_census: SourceCensus,
    answer_keys: Mapping[str, AnswerKey],
    bundle: EvaluationBundleIdentity,
    capture: CapturedEvaluation,
    generated_at: str,
) -> None:
    """Reject caller-made lookalikes before a real capture reaches the ledger."""

    if not isinstance(evaluation_manifest, EvaluationManifest):
        raise EvidenceError("real evaluation requires an EvaluationManifest")
    if not isinstance(index_manifest, IndexManifest):
        raise EvidenceError("real evaluation requires a sealed IndexManifest")
    if not isinstance(source_census, SourceCensus):
        raise EvidenceError("real evaluation requires a sealed SourceCensus")
    if not isinstance(answer_keys, Mapping):
        raise EvidenceError("real evaluation answer keys must be a mapping")
    if not isinstance(bundle, EvaluationBundleIdentity):
        raise EvidenceError("real evaluation requires exact bundle identities")
    if not isinstance(capture, CapturedEvaluation):
        raise EvidenceError("real evaluation requires a captured runtime result")
    if (
        not isinstance(generated_at, str)
        or not generated_at
        or len(generated_at.encode("utf-8")) > 128
        or any(ord(character) < 32 or ord(character) == 127 for character in generated_at)
    ):
        raise EvidenceError("generated_at must be bounded printable text")
    _validate_bundle_identity(bundle)
    _validate_sealed_source_binding(evaluation_manifest, index_manifest, source_census)
    _require_identifier(capture.generation_id, "captured generation_id")
    if not isinstance(capture.generation_receipts, tuple) or not capture.generation_receipts:
        raise EvidenceError("real evaluation requires captured generation receipts")
    if any(
        not isinstance(receipt, GenerationReceipt)
        or receipt.generation_id != capture.generation_id
        for receipt in capture.generation_receipts
    ):
        raise EvidenceError("captured generation receipts do not bind one generation")
    if (
        not isinstance(capture.baseline, CapturedCandidateAdapter)
        or capture.baseline.candidate != "baseline"
        or not isinstance(capture.zoekt, CapturedCandidateAdapter)
        or capture.zoekt.candidate != "zoekt"
    ):
        raise EvidenceError("real evaluation requires baseline and zoekt captured adapters")
    allowed_query_identities = {query.identity for query in evaluation_manifest.queries}
    for adapter in (capture.baseline, capture.zoekt):
        if set(adapter.transports) - allowed_query_identities:
            raise EvidenceError("captured adapter contains an unregistered query transport")
    if not isinstance(capture.failure_injection_receipts, tuple):
        raise EvidenceError("captured failure receipts must be an immutable tuple")
    if capture.decision_evidence is not None and not isinstance(
        capture.decision_evidence, DecisionEvidence
    ):
        raise EvidenceError("captured decision evidence has an invalid shape")


def _validate_bundle_identity(bundle: EvaluationBundleIdentity) -> None:
    """Require every captured executable/toolchain identity before ledger writes."""

    _require_sha1(bundle.zoekt_source_commit, "bundle zoekt_source_commit")
    for label, value in (
        ("bundle zoekt_git_index_digest", bundle.zoekt_git_index_digest),
        ("bundle zoekt_webserver_digest", bundle.zoekt_webserver_digest),
        ("bundle go_toolchain_digest", bundle.go_toolchain_digest),
        ("bundle module_graph_digest", bundle.module_graph_digest),
        ("bundle ctags_disposition_digest", bundle.ctags_disposition_digest),
        ("bundle configuration_digest", bundle.configuration_digest),
        ("bundle sandbox_digest", bundle.sandbox_digest),
        ("bundle tool_schema_digest", bundle.tool_schema_digest),
    ):
        _require_sha256(value, label)


def _validate_sealed_source_binding(
    evaluation_manifest: EvaluationManifest,
    index_manifest: IndexManifest,
    source_census: SourceCensus,
) -> None:
    """Bind the exact manifest corpus to both source types without rereading disk."""

    if (
        not isinstance(source_census.canonical_bytes, bytes)
        or hashlib.sha256(source_census.canonical_bytes).hexdigest() != source_census.digest
    ):
        raise EvidenceError("sealed source census digest does not bind canonical bytes")
    _require_sha256(source_census.digest, "sealed source census digest")
    try:
        observed_census = census_sealed_sources(index_manifest)
    except SourceCensusError as error:
        raise EvidenceError("source seal revalidation failed") from error
    if (
        observed_census.digest != source_census.digest
        or observed_census.canonical_bytes != source_census.canonical_bytes
    ):
        raise EvidenceError("sealed source census no longer matches the parent source seal")
    if index_manifest.schema_version != "mastermind.codeintel_index_manifest.v1":
        raise EvidenceError("IndexManifest has an unexpected sealed schema version")
    corpus_by_id = {
        str(row["logical_repo_id"]): row for row in evaluation_manifest.corpus
    }
    specs_by_id = {spec.repository_id: spec for spec in index_manifest.repositories}
    if set(specs_by_id) != set(corpus_by_id):
        raise EvidenceError("IndexManifest does not cover exactly the frozen source corpus")
    for logical_repo_id, row in corpus_by_id.items():
        spec = specs_by_id[logical_repo_id]
        if (
            spec.repository_name != row["canonical_repository"]
            or spec.ref_label != row["ref"]
            or spec.commit_sha != row["commit"]
        ):
            raise EvidenceError("IndexManifest source identity does not bind frozen corpus")
    if not isinstance(source_census.records, tuple):
        raise EvidenceError("sealed source census records must be immutable")
    for record in source_census.records:
        if not isinstance(record.logical_repo_id, str) or record.logical_repo_id not in corpus_by_id:
            raise EvidenceError("sealed source census names an unregistered repository")
        row = corpus_by_id[record.logical_repo_id]
        if (
            record.canonical_repository != row["canonical_repository"]
            or record.ref != row["ref"]
            or record.commit != row["commit"]
            or record.tree != row["tree"]
        ):
            raise EvidenceError("sealed source census identity does not bind frozen corpus")


def _validate_generation_bundle_binding(
    receipt: GenerationReceipt,
    bundle: EvaluationBundleIdentity,
) -> None:
    """Reject a generation whose observed build identity differs from its bundle."""

    if not isinstance(receipt, GenerationReceipt):
        raise EvidenceError("captured generation receipt has an invalid shape")
    execution = receipt.execution
    if not isinstance(execution, GenerationExecutionReceipt):
        raise EvidenceError("real generation lacks an observed execution receipt")
    if (
        execution.zoekt_source_commit != bundle.zoekt_source_commit
        or execution.zoekt_binary_digest != bundle.zoekt_git_index_digest
        or execution.go_toolchain_digest != bundle.go_toolchain_digest
        or execution.module_graph_digest != bundle.module_graph_digest
        or execution.ctags_disposition_digest != bundle.ctags_disposition_digest
        or execution.configuration_digest != bundle.configuration_digest
        or execution.sandbox_digest != bundle.sandbox_digest
    ):
        raise EvidenceError("generation execution receipt does not bind the exact bundle")


def _validate_query_bundle_binding(
    receipt: NormalizedQueryReceipt,
    bundle: EvaluationBundleIdentity,
) -> None:
    """Require the normalized response to attest the same query-side bundle."""

    identity = receipt.payload.get("index_identity")
    if not isinstance(identity, Mapping):
        raise EvidenceError("query receipt lacks an index identity")
    if (
        identity.get("zoekt_source_commit") != bundle.zoekt_source_commit
        or identity.get("zoekt_binary_digest") != bundle.zoekt_webserver_digest
        or identity.get("go_toolchain_digest") != bundle.go_toolchain_digest
        or identity.get("module_graph_digest") != bundle.module_graph_digest
        or identity.get("ctags_disposition_digest") != bundle.ctags_disposition_digest
        or identity.get("configuration_digest") != bundle.configuration_digest
        or identity.get("sandbox_digest") != bundle.sandbox_digest
    ):
        raise EvidenceError("query receipt does not bind the exact bundle")


def _record_captured_paired_trials(
    ledger: EvaluationLedger,
    *,
    plans: Mapping[str, QueryPlan],
    answer_keys: Mapping[str, AnswerKey],
    bundle: EvaluationBundleIdentity,
    baseline: CapturedCandidateAdapter,
    zoekt: CapturedCandidateAdapter,
) -> tuple[TrialReceipt, ...]:
    """Consume every frozen trial order from opaque captured transport only."""

    adapters = {"baseline": baseline, "zoekt": zoekt}
    receipts: list[TrialReceipt] = []
    for trial_id in ledger.manifest.trial_order:
        query, identity = ledger._query_and_identity_for_trial(trial_id)
        plan = plans[query.identity]
        query_receipt: NormalizedQueryReceipt | None = None
        query_receipt_failure_digest: str | None = None
        try:
            transport = adapters[identity.candidate].transport_for(plan)
            query_receipt = parse_normalized_query_receipt(
                transport.receipt_document, query_plan=plan
            )
            _validate_query_bundle_binding(query_receipt, bundle)
            ledger.record_query_receipt(query_receipt)
            observation = _observation_from_query_receipt(ledger, query, query_receipt)
        except Exception as error:
            _retain_query_receipt_failure(ledger, trial_id, "VALIDATION", error)
            observation = _callback_failure("error", "RESULT_SCHEMA_INVALID")
            query_receipt_failure_digest = ledger.query_receipt_failure_receipts[-1].evidence_digest
            query_receipt = None
        grade = grade_candidate_result(
            answer_keys[query.identity], observation.returned_identities
        )
        receipt = TrialReceipt(
            trial_id=trial_id,
            query_identity=query.identity,
            query_index=query.query_index,
            query_plan_digest=plan.digest,
            normalized_arguments_digest=plan.normalized_arguments_digest,
            query_receipt_digest=(
                query_receipt.digest
                if query_receipt is not None
                else query_receipt_failure_digest
            )
            or "0" * 64,
            attempt_index=1,
            outcome=observation.outcome,
            answer_key_digest=query.answer_key_digest,
            source_census_digest=ledger._source_census_digest,
            generation_id=ledger.active_generation_id or "",
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


def _result_payload_from_real_capture(
    ledger: EvaluationLedger,
    *,
    evidence: EvaluationEvidence,
    decision: str | None,
    bundle: EvaluationBundleIdentity,
    generated_at: str,
) -> dict[str, object]:
    """Build the strict result envelope from ledger-owned facts and bundle IDs."""

    payload = ledger.to_payload()
    corpus_by_id = ledger._corpus_by_logical_id()
    statuses = []
    for receipt in sorted(
        ledger.generation_receipts,
        key=lambda item: (item.generation_id, item.logical_repo_id),
    ):
        source = corpus_by_id[receipt.logical_repo_id]
        statuses.append(
            {
                "logical_repo_id": receipt.logical_repo_id,
                "canonical_repository": source["canonical_repository"],
                "ref": source["ref"],
                "source_commit": receipt.source_commit,
                "source_tree": receipt.source_tree,
                "indexed_commit_sha": receipt.indexed_commit_sha,
                "shard_digest": receipt.shard_digest,
                "generation_id": receipt.generation_id,
                "status": receipt.status,
            }
        )
    return {
        "schema_version": "mastermind.codeintel_z0_result.v1",
        "decision": decision,
        "generated_at": generated_at,
        "manifest_digest": ledger.manifest.digest,
        "source_census_digest": ledger._source_census_digest,
        "path_policy_digest": ledger.manifest.path_policy_rules["policy_document_digest"],
        "tool_schema_digest": bundle.tool_schema_digest,
        "zoekt_source_commit": bundle.zoekt_source_commit,
        "binary_digests": {
            "zoekt_git_index": bundle.zoekt_git_index_digest,
            "zoekt_webserver": bundle.zoekt_webserver_digest,
            "go_toolchain": bundle.go_toolchain_digest,
            "module_graph": bundle.module_graph_digest,
            "ctags_disposition": bundle.ctags_disposition_digest,
            "configuration": bundle.configuration_digest,
            "sandbox": bundle.sandbox_digest,
        },
        "source_bundle": {
            "protected_source": dict(ledger.manifest.protected_source),
            "authority_blobs": dict(ledger.manifest.authority_blobs),
            "real_preregistration_digest": ledger.manifest.real_preregistration_digest,
            "corpus": [dict(row) for row in ledger.manifest.corpus],
            "active_generation_id": ledger.active_generation_id,
        },
        "repository_statuses": statuses,
        "resource_observations": {
            "generation_receipts_digest": hashlib.sha256(
                _canonical_json(payload["generation_receipts"])
            ).hexdigest(),
            "query_receipts_digest": hashlib.sha256(
                _canonical_json(payload["query_receipts"])
            ).hexdigest(),
            "failure_injection_receipts_digest": hashlib.sha256(
                _canonical_json(payload["failure_injection_receipts"])
            ).hexdigest(),
        },
        "evaluation_evidence": evidence.to_result_payload(),
    }


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


def _observation_from_query_receipt(
    ledger: EvaluationLedger,
    query: EvaluationQuery,
    receipt: NormalizedQueryReceipt,
) -> CandidateTrialObservation:
    """Mechanically project one validated receipt into the grader's only truth.

    Candidate callbacks may supply transport bytes, but they cannot separately
    nominate returned identities, completion, resources, or failure status.
    This projection is used both when a trial is recorded and by the test-only
    harness, so a mismatch is retained as ``RESULT_SCHEMA_INVALID`` instead of
    being graded optimistically.
    """

    if not isinstance(ledger, EvaluationLedger) or not isinstance(query, EvaluationQuery):
        raise EvidenceError("query receipt observation requires bound ledger and query")
    payload = receipt.payload
    matches = payload["matches"]
    limits = payload["limits"]
    resources = payload["resource_observation"]
    if not isinstance(matches, tuple) or not isinstance(limits, Mapping) or not isinstance(resources, Mapping):
        raise EvidenceError("normalized query receipt has malformed semantic payload")
    corpus = ledger._corpus_by_logical_id()
    returned: list[tuple[str, str, str, str, int, int]] = []
    for raw_match in matches:
        if not isinstance(raw_match, Mapping):
            raise EvidenceError("normalized query receipt match has malformed shape")
        logical_id = raw_match["logical_repository"]
        if not isinstance(logical_id, str) or logical_id not in query.logical_repo_ids:
            raise EvidenceError("query receipt match escapes its requested source subset")
        source = corpus.get(logical_id)
        if source is None:
            raise EvidenceError("query receipt match names an unknown source")
        if (
            raw_match["ref"] != source["ref"]
            or raw_match["indexed_commit"] != source["commit"]
            or raw_match["indexed_tree"] != source["tree"]
        ):
            raise EvidenceError("query receipt match does not bind frozen source identity")
        path = raw_match["repository_relative_path"]
        range_value = raw_match["range"]
        if not isinstance(path, str) or not isinstance(range_value, Mapping):
            raise EvidenceError("query receipt match identity is malformed")
        start = range_value["start_line"]
        end = range_value["end_line"]
        if type(start) is not int or type(end) is not int or start < 1 or end < start:
            raise EvidenceError("query receipt match line range is invalid")
        returned.append(
            (
                logical_id,
                source["canonical_repository"],
                source["ref"],
                path,
                start,
                end,
            )
        )
    identities = tuple(returned)
    _validate_identities(identities)
    resource = ResourceObservation(
        cpu_ms=resources["cpu_ms"],
        rss_bytes=resources["peak_rss"],
        disk_bytes=resources["disk_io"],
    )
    status = receipt.status
    complete = receipt.query_completeness == "COMPLETE"
    truncated = bool(limits["truncated"]) or not complete
    if status in {"SUCCESS", "ZERO_RESULTS"} and complete and not truncated:
        return CandidateTrialObservation(
            outcome="completed",
            query_completed=True,
            truncated=False,
            returned_identities=identities,
            resource=resource,
            failure_code=None,
        )
    if status == "TIMEOUT":
        outcome, failure_code = "timeout", "TIMEOUT"
    elif status == "CANCELLED":
        outcome, failure_code = "cancelled", "QUERY_CANCELLED"
    elif status == "STALE":
        outcome, failure_code = "error", "SOURCE_MOVED"
    elif status == "INDEX_FAILED":
        outcome, failure_code = "error", "CORRUPT_INDEX"
    elif status == "REFUSED":
        outcome, failure_code = "error", "INCOMPLETE_DESIRED_SET"
    else:
        outcome, failure_code = "error", "RESULT_SCHEMA_INVALID"
    return CandidateTrialObservation(
        outcome=outcome,
        query_completed=False,
        truncated=True,
        returned_identities=identities,
        resource=resource,
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
    source_statuses = payload["source_statuses"]
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
    if not isinstance(source_statuses, tuple) or not source_statuses:
        return False
    if not all(
        isinstance(status, Mapping)
        and status.get("coverage") == "FULLY_COVERED"
        and status.get("health") == "HEALTHY"
        and status.get("freshness") == "EXACT_SHA_CURRENT"
        and status.get("requested_commit") == status.get("indexed_commit")
        and status.get("requested_tree") == status.get("indexed_tree")
        for status in source_statuses
    ):
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


def _generation_execution_is_decision_eligible(
    execution: GenerationExecutionReceipt | None,
) -> bool:
    if not isinstance(execution, GenerationExecutionReceipt):
        return False
    measured = (
        execution.selected_file_count,
        execution.selected_byte_count,
        execution.shard_count,
        execution.build_ms,
        execution.refresh_ms,
        execution.query_ms,
        execution.cpu_ms,
        execution.rss_bytes,
        execution.disk_bytes,
        execution.disk_io_bytes,
        execution.process_count,
        execution.open_file_peak,
        execution.network_attempt_count,
        execution.credential_access_count,
        execution.source_write_count,
    )
    return (
        all(type(value) is int and value >= 0 for value in measured)
        and execution.network_attempt_count == 0
        and execution.credential_access_count == 0
        and execution.source_write_count == 0
        and execution.cleanup_state == "SUCCEEDED"
        and execution.effect in {"PUBLISHED", "PUBLISH_REFUSED"}
        and execution.output_digest != UNKNOWN_RESOURCE
        and execution.cleanup_receipt_digest != UNKNOWN_RESOURCE
    )


def _query_receipt_payload(receipt: NormalizedQueryReceipt) -> dict[str, object]:
    payload = _thaw_receipt_json(receipt.payload)
    assert isinstance(payload, dict)
    return payload


def _decision_evidence_payload(evidence: DecisionEvidence | None) -> dict[str, object] | None:
    if evidence is None:
        return None
    return {
        "manifest_digest": evidence.manifest_digest,
        "path_policy_id": evidence.path_policy_id,
        "path_policy_measurements_digest": evidence.path_policy_measurements_digest,
        "p0_non_recall_justification": evidence.p0_non_recall_justification,
        "topology_id": evidence.topology_id,
        "topology_measurements_digest": evidence.topology_measurements_digest,
        "freshness_receipt_digest": evidence.freshness_receipt_digest,
        "reproducibility_receipt_digest": evidence.reproducibility_receipt_digest,
        "comparative": {
            "metrics": {
                str(metric): {
                    "baseline": values["baseline"],
                    "zoekt": values["zoekt"],
                }
                for metric, values in evidence.comparative.metrics.items()
            },
            "measurement_digest": evidence.comparative.measurement_digest,
        },
        "safety_complete": evidence.safety_complete,
        "correctness_complete": evidence.correctness_complete,
        "freshness_complete": evidence.freshness_complete,
        "reproducibility_complete": evidence.reproducibility_complete,
        "path_policy_complete": evidence.path_policy_complete,
        "topology_complete": evidence.topology_complete,
        "constitutional_failure": evidence.constitutional_failure,
    }


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


def _validate_source_statuses(
    value: object,
    *,
    index_generation_id: str,
) -> tuple[Mapping[str, object], ...]:
    """Validate one status row per requested source against one query generation.

    Coverage, health, and freshness deliberately live on the same row as the
    immutable source identity.  There is no independent list whose one healthy
    value could accidentally bless several requested repositories.
    """

    if not isinstance(value, list) or not value:
        raise QueryReceiptError("source_statuses must be a non-empty ordered list")
    statuses: list[Mapping[str, object]] = []
    logical_repositories: set[str] = set()
    for index, raw in enumerate(value):
        label = f"source_statuses[{index}]"
        source = _receipt_mapping(raw, label)
        _exact_receipt_fields(source, _SOURCE_STATUS_FIELDS, label)
        logical_repository = _receipt_text(source["logical_repository"], label)
        if logical_repository in logical_repositories:
            raise QueryReceiptError("source_statuses contains duplicate logical_repository")
        logical_repositories.add(logical_repository)
        _receipt_sha256(source["canonical_repository_digest"], label)
        _receipt_text(source["requested_ref"], label)
        _receipt_sha1(source["requested_commit"], label)
        _receipt_sha1(source["requested_tree"], label)
        _receipt_sha1(source["indexed_commit"], label)
        _receipt_sha1(source["indexed_tree"], label)
        generation_id = _receipt_text(source["generation_id"], label)
        if generation_id != index_generation_id:
            raise QueryReceiptError(
                "source_statuses generation_id must bind index_identity generation"
            )
        _receipt_closed_value(source["coverage"], _COVERAGE_VALUES, label)
        _receipt_closed_value(source["health"], _HEALTH_VALUES, label)
        _receipt_closed_value(source["freshness"], _FRESHNESS_VALUES, label)
        statuses.append(source)
    return tuple(statuses)


def _validate_receipt_binds_query_plan(
    *,
    query_plan: QueryPlan,
    trial_id: str,
    query_identity: str,
    query_index: int,
    candidate: str,
    query_plan_digest: str,
    query_digest: str,
    normalized_arguments_digest: str,
    evaluation_manifest_digest: str,
    source_statuses: tuple[Mapping[str, object], ...],
) -> None:
    """Reject a receipt unless its identity and source rows match one frozen plan."""

    if (
        trial_id != query_plan.trial_id(candidate)
        or query_identity != query_plan.query_identity
        or query_index != query_plan.query_index
        or query_plan_digest != query_plan.digest
        or query_digest != query_plan.query_digest
        or normalized_arguments_digest != query_plan.normalized_arguments_digest
        or evaluation_manifest_digest != query_plan.evaluation_manifest_digest
    ):
        raise QueryReceiptError("query receipt does not bind its immutable QueryPlan")
    source_ids = tuple(item["logical_repository"] for item in source_statuses)
    if source_ids != query_plan.logical_repo_ids:
        raise QueryReceiptError(
            "source_statuses do not bind the exact QueryPlan source subset/order"
        )
    if any(item["requested_ref"] not in query_plan.refs for item in source_statuses):
        raise QueryReceiptError("source_statuses requested_ref is outside the QueryPlan")


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
    execution = receipt.execution
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
        "execution_receipt": (
            None
            if execution is None
            else {
                "evaluation_manifest_digest": execution.evaluation_manifest_digest,
                "source_blob_census_digest": execution.source_blob_census_digest,
                "source_path_policy_digest": execution.source_path_policy_digest,
                "zoekt_source_commit": execution.zoekt_source_commit,
                "zoekt_binary_digest": execution.zoekt_binary_digest,
                "go_toolchain_digest": execution.go_toolchain_digest,
                "module_graph_digest": execution.module_graph_digest,
                "ctags_disposition_digest": execution.ctags_disposition_digest,
                "configuration_digest": execution.configuration_digest,
                "sandbox_digest": execution.sandbox_digest,
                "selected_file_count": execution.selected_file_count,
                "selected_byte_count": execution.selected_byte_count,
                "shard_count": execution.shard_count,
                "build_ms": execution.build_ms,
                "refresh_ms": execution.refresh_ms,
                "query_ms": execution.query_ms,
                "cpu_ms": execution.cpu_ms,
                "rss_bytes": execution.rss_bytes,
                "disk_bytes": execution.disk_bytes,
                "disk_io_bytes": execution.disk_io_bytes,
                "process_count": execution.process_count,
                "open_file_peak": execution.open_file_peak,
                "network_attempt_count": execution.network_attempt_count,
                "credential_access_count": execution.credential_access_count,
                "source_write_count": execution.source_write_count,
                "output_digest": execution.output_digest,
                "published_generation_id": execution.published_generation_id,
                "prior_generation_id": execution.prior_generation_id,
                "effect": execution.effect,
                "cleanup_state": execution.cleanup_state,
                "cleanup_receipt_digest": execution.cleanup_receipt_digest,
                "correction_of": execution.correction_of,
            }
        ),
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
    execution = receipt.execution
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
        "execution": (
            None
            if execution is None
            else {
                "injection_id": execution.injection_id,
                "expected_failure_code": execution.expected_failure_code,
                "observed_failure_code": execution.observed_failure_code,
                "expected_effect": execution.expected_effect,
                "observed_effect": execution.observed_effect,
                "cleanup_state": execution.cleanup_state,
                "execution_receipt_digest": execution.execution_receipt_digest,
            }
        ),
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
        "query_identity": receipt.query_identity,
        "query_index": receipt.query_index,
        "query_plan_digest": receipt.query_plan_digest,
        "normalized_arguments_digest": receipt.normalized_arguments_digest,
        "query_receipt_digest": receipt.query_receipt_digest,
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
