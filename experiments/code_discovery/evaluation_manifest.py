"""Strict, immutable preregistration for paired Z0 empirical evaluation.

The manifest is evidence, not a mutable run configuration.  It binds the
source epoch, authority sources, query budgets, answer-key identities, and
mechanical selection rules before either candidate is allowed to run.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Final

from .baseline_search import AnswerKey


MANIFEST_SCHEMA_VERSION: Final = "mastermind.codeintel_evaluation_manifest.v1"
REAL_EVALUATION_PREREGISTRATION_SCHEMA_VERSION: Final = (
    "mastermind.codeintel_z0_real_evaluation_preregistration.v1"
)
_SHA1_RE: Final = re.compile(r"[0-9a-f]{40}\Z")
_SHA256_RE: Final = re.compile(r"[0-9a-f]{64}\Z")
_TOP_LEVEL_FIELDS: Final = frozenset(
    {
        "schema_version",
        "operation_key",
        "protected_source",
        "authority_blobs",
        "corpus",
        "queries",
        "path_policy_candidates",
        "trial_order",
        "freshness_targets",
        "resource_envelopes",
        "materiality_bands",
        "hard_failure_rules_digest",
        "tie_break_rule_digest",
        "real_preregistration_digest",
        "failure_injections",
        "path_policy_rules",
        "decision_law",
    }
)
_PROTECTED_SOURCE_FIELDS: Final = frozenset(
    {"repository", "commit", "tree", "skillpack_index_blob"}
)
_AUTHORITY_BLOB_FIELDS: Final = frozenset({"f0", "language_amendment", "z0_plan"})
_CORPUS_FIELDS: Final = frozenset(
    {
        "logical_repo_id",
        "canonical_repository",
        "ref",
        "commit",
        "tree",
        "blob_census_digest",
        "include_exclude_policy_digest",
        "submodule_lfs_generated_vendor_oversize_disposition_digest",
    }
)
_QUERY_FIELDS: Final = frozenset(
    {
        "candidate_order",
        "case_id",
        "family",
        "query_digest",
        "logical_repo_ids",
        "refs",
        "path_prefixes",
        "languages",
        "filters_digest",
        "answer_key_digest",
        "forbidden_answer_digest",
        "deterministic_grader_id",
        "recall_threshold",
        "completeness_threshold",
        "false_positive_ceiling",
        "max_results",
        "max_context_lines",
        "timeout_ms",
        "warm_or_cold",
        "repetition_index",
        "query_index",
    }
)
_REQUIRED_CASES: Final = frozenset({"E1", "X3", "R3", "A1"})
_PATH_POLICIES: Final = ("P0", "P1", "P2")
_RESOURCE_ENVELOPE_FIELDS: Final = frozenset(
    {"max_cpu_ms", "max_rss_bytes", "max_disk_bytes"}
)
_REAL_PREREGISTRATION_FIELDS: Final = frozenset(
    {
        "schema_version",
        "operation_key",
        "authority",
        "source_epoch",
        "case_definitions",
        "corpus_policy",
        "queries",
        "resource_envelopes",
        "freshness_targets",
        "hard_failure_rules",
        "failure_injections",
        "materiality_rule",
        "decision_law",
    }
)
_REAL_SOURCE_EPOCH_REPOSITORIES: Final = frozenset(
    {"mastermind", "macro", "terminal"}
)
_REAL_CASE_IDS: Final = frozenset({"E1", "X3", "R3", "A1", "T1"})
_FINAL_DECISIONS: Final = frozenset(
    {
        "ZOEKT_FACADE_ACCEPTED_FOR_CI3",
        "ZOEKT_REQUIRES_ARCHITECTURE_REVISION",
        "NO_SAFE_GLOBAL_INDEX",
    }
)


class EvaluationManifestError(ValueError):
    """The preregistration does not bind one safe, deterministic experiment."""


@dataclass(frozen=True)
class EvaluationQuery:
    """One immutable candidate-paired query trial declaration."""

    case_id: str
    family: str
    query_digest: str
    logical_repo_ids: tuple[str, ...]
    refs: tuple[str, ...]
    path_prefixes: tuple[str, ...]
    languages: tuple[str, ...]
    filters_digest: str
    answer_key_digest: str
    forbidden_answer_digest: str
    deterministic_grader_id: str
    recall_threshold: float
    completeness_threshold: float
    false_positive_ceiling: float
    max_results: int
    max_context_lines: int
    timeout_ms: int
    warm_or_cold: str
    repetition_index: int
    query_index: int
    candidate_order: tuple[str, str]

    @property
    def identity(self) -> str:
        """Return the immutable repetition-level identity shared by both candidates."""

        return ":".join(
            (
                self.case_id,
                self.family,
                str(self.repetition_index),
                self.warm_or_cold,
                str(self.query_index),
            )
        )

    def trial_id(self, candidate: str) -> str:
        """Bind a candidate to the unique query/repetition, never only its case."""

        if candidate not in {"baseline", "zoekt"}:
            raise EvaluationManifestError("trial candidate is not in the closed vocabulary")
        return f"{self.identity}:{candidate}"


@dataclass(frozen=True)
class EvaluationManifest:
    """Canonical manifest bytes plus the parsed, immutable execution projection."""

    canonical_bytes: bytes
    digest: str
    operation_key: str
    protected_source: Mapping[str, str]
    authority_blobs: Mapping[str, str]
    corpus: tuple[Mapping[str, str], ...]
    queries: tuple[EvaluationQuery, ...]
    path_policy_candidates: tuple[str, ...]
    trial_order: tuple[str, ...]
    freshness_targets: Mapping[str, object]
    resource_envelopes: Mapping[str, object]
    materiality_bands: Mapping[str, object]
    hard_failure_rules_digest: str
    tie_break_rule_digest: str
    real_preregistration_digest: str
    failure_injections: tuple[str, ...]
    path_policy_rules: Mapping[str, object]
    decision_law: Mapping[str, object]


@dataclass(frozen=True)
class RealEvaluationPreregistration:
    """A byte-exact pre-result Epoch record, never a result or run authorization."""

    canonical_bytes: bytes
    digest: str
    schema_version: str
    operation_key: str
    authority: Mapping[str, object]
    source_epoch: Mapping[str, Mapping[str, str]]
    case_definitions: tuple[Mapping[str, object], ...]
    corpus_policy: Mapping[str, object]
    queries: tuple[Mapping[str, object], ...]
    resource_envelopes: Mapping[str, object]
    freshness_targets: Mapping[str, object]
    hard_failure_rules: tuple[str, ...]
    failure_injections: tuple[str, ...]
    materiality_rule: Mapping[str, object]
    decision_law: Mapping[str, object]

    @property
    def required_trial_count(self) -> int:
        """Each preregistered query must receive one receipt from each candidate."""

        return len(self.queries) * 2

    @property
    def required_failure_injection_count(self) -> int:
        return len(self.failure_injections)

    @property
    def incomplete_state(self) -> str:
        value = self.decision_law["incomplete_or_synthetic_state"]
        assert isinstance(value, str)
        return value

    @property
    def incomplete_decision(self) -> None:
        value = self.decision_law["incomplete_or_synthetic_decision"]
        assert value is None
        return None


def load_evaluation_manifest(path: Path) -> EvaluationManifest:
    """Read one regular UTF-8 JSON manifest and retain its canonical evidence bytes."""

    manifest_path = Path(path)
    try:
        metadata = manifest_path.lstat()
        if not manifest_path.is_file() or metadata.st_mode & 0o170000 == 0o120000:
            raise EvaluationManifestError("evaluation manifest must be a regular file")
        document = manifest_path.read_bytes()
    except OSError as error:
        raise EvaluationManifestError("evaluation manifest cannot be read") from error
    return parse_evaluation_manifest(document)


def load_real_evaluation_preregistration(path: Path) -> RealEvaluationPreregistration:
    """Load an exact canonical pre-result study record from one regular file."""

    preregistration_path = Path(path)
    try:
        metadata = preregistration_path.lstat()
        if (
            not preregistration_path.is_file()
            or metadata.st_mode & 0o170000 == 0o120000
        ):
            raise EvaluationManifestError("real evaluation preregistration must be a regular file")
        document = preregistration_path.read_bytes()
    except OSError as error:
        raise EvaluationManifestError("real evaluation preregistration cannot be read") from error
    return parse_real_evaluation_preregistration(document)


def parse_real_evaluation_preregistration(
    document: bytes | bytearray | str,
) -> RealEvaluationPreregistration:
    """Validate the closed, byte-exact preregistration contract before a run exists."""

    if isinstance(document, (bytes, bytearray)):
        raw = bytes(document)
    elif isinstance(document, str):
        raw = document.encode("utf-8")
    else:
        raise EvaluationManifestError("real evaluation preregistration must be UTF-8 JSON")
    payload = _strict_json_loads(raw)
    if not isinstance(payload, Mapping):
        raise EvaluationManifestError("real evaluation preregistration must be an object")
    _exact_fields(payload, _REAL_PREREGISTRATION_FIELDS, "real evaluation preregistration")
    if payload["schema_version"] != REAL_EVALUATION_PREREGISTRATION_SCHEMA_VERSION:
        raise EvaluationManifestError("real evaluation preregistration has an unknown schema_version")
    canonical = canonical_manifest_bytes(payload)
    if raw != canonical:
        raise EvaluationManifestError("real evaluation preregistration must use canonical compact JSON")

    authority = _json_object(payload["authority"], "authority")
    if any(
        not (
            (isinstance(value, str) and value)
            or (type(value) is int and value > 0)
        )
        for value in authority.values()
    ):
        raise EvaluationManifestError("authority must contain closed non-empty identities")
    source_epoch = _parse_real_source_epoch(payload["source_epoch"])
    case_definitions = _parse_real_case_definitions(payload["case_definitions"])
    queries = _parse_real_queries(payload["queries"], source_epoch, case_definitions)
    failure_injections = _parse_closed_text_list(
        payload["failure_injections"],
        "failure_injections",
        expected_count=21,
    )
    hard_failure_rules = _parse_closed_text_list(
        payload["hard_failure_rules"], "hard_failure_rules"
    )
    decision_law = _parse_real_decision_law(payload["decision_law"])
    frozen_authority = _freeze_json(authority)
    frozen_source_epoch = _freeze_json(source_epoch)
    assert isinstance(frozen_source_epoch, Mapping)
    frozen_cases = tuple(_freeze_json(row) for row in case_definitions)
    frozen_queries = tuple(_freeze_json(row) for row in queries)
    frozen_mappings = tuple(
        _freeze_json(_json_object(payload[field], field))
        for field in (
            "corpus_policy",
            "resource_envelopes",
            "freshness_targets",
            "materiality_rule",
        )
    )
    frozen_decision_law = _freeze_json(decision_law)
    if (
        not isinstance(frozen_authority, Mapping)
        or not all(isinstance(value, Mapping) for value in frozen_cases)
        or not all(isinstance(value, Mapping) for value in frozen_queries)
        or not all(isinstance(value, Mapping) for value in frozen_mappings)
        or not isinstance(frozen_decision_law, Mapping)
    ):
        raise AssertionError("real evaluation preregistration freezing changed object shape")
    return RealEvaluationPreregistration(
        canonical_bytes=canonical,
        digest=hashlib.sha256(canonical).hexdigest(),
        schema_version=REAL_EVALUATION_PREREGISTRATION_SCHEMA_VERSION,
        operation_key=_identifier(payload["operation_key"], "operation_key"),
        authority=frozen_authority,
        source_epoch=frozen_source_epoch,  # type: ignore[arg-type]
        case_definitions=frozen_cases,  # type: ignore[arg-type]
        corpus_policy=frozen_mappings[0],
        queries=frozen_queries,  # type: ignore[arg-type]
        resource_envelopes=frozen_mappings[1],
        freshness_targets=frozen_mappings[2],
        hard_failure_rules=hard_failure_rules,
        failure_injections=failure_injections,
        materiality_rule=frozen_mappings[3],
        decision_law=frozen_decision_law,
    )


def materialize_real_evaluation_manifest(
    preregistration: RealEvaluationPreregistration,
    *,
    protected_source: Mapping[str, object],
    authority_blobs: Mapping[str, object],
    corpus: Sequence[Mapping[str, object]],
    source_census_digest: str,
    answer_keys: Mapping[str, AnswerKey],
    path_policy_rules: Mapping[str, object],
) -> EvaluationManifest:
    """Materialize Epoch evidence into a strict run manifest without running it.

    This is a pure construction step.  It consumes the byte-exact Epoch 1
    preregistration, already sealed path/blob census rows, and source-derived
    answer keys.  It opens no service, indexes no repository, reads no
    credentials, and cannot emit a decision.  Any policy/path mutation changes
    the manifest input and fails the corresponding answer-key binding.
    """

    if not isinstance(preregistration, RealEvaluationPreregistration):
        raise EvaluationManifestError("real materialization requires frozen preregistration")
    protected = _parse_protected_source(protected_source)
    authority = _parse_authority_blobs(authority_blobs)
    parsed_corpus = _parse_corpus(list(corpus))
    _sha256(source_census_digest, "source_census_digest")
    policy_rules = _json_object(path_policy_rules, "path_policy_rules")
    policy_document_digest = _sha256(
        policy_rules.get("policy_document_digest"), "path_policy_rules.policy_document_digest"
    )
    allowed_p0 = _identifier_list(
        policy_rules.get("p0_allowed_non_recall_justifications"),
        "path_policy_rules.p0_allowed_non_recall_justifications",
    )
    if authority["f0"] != preregistration.authority["f0_blob"]:
        raise EvaluationManifestError("materialized authority f0 does not bind preregistration")
    if authority["language_amendment"] != preregistration.authority["language_deployment_blob"]:
        raise EvaluationManifestError(
            "materialized language authority does not bind preregistration"
        )
    if authority["z0_plan"] != preregistration.authority["z0_plan_blob"]:
        raise EvaluationManifestError("materialized Z0 plan does not bind preregistration")
    if (
        protected["repository"] != preregistration.source_epoch["mastermind"]["repository"]
        or protected["commit"] != preregistration.source_epoch["mastermind"]["commit"]
        or protected["tree"] != preregistration.source_epoch["mastermind"]["tree"]
    ):
        raise EvaluationManifestError("protected source does not bind frozen Mastermind epoch")

    corpus_by_id = {row["logical_repo_id"]: row for row in parsed_corpus}
    if set(corpus_by_id) != set(preregistration.source_epoch):
        raise EvaluationManifestError("materialized corpus must cover exactly the frozen source epoch")
    for logical_repo_id, epoch in preregistration.source_epoch.items():
        row = corpus_by_id[logical_repo_id]
        if (
            row["canonical_repository"] != epoch["repository"]
            or row["ref"] != epoch["ref"]
            or row["commit"] != epoch["commit"]
            or row["tree"] != epoch["tree"]
        ):
            raise EvaluationManifestError(
                "materialized corpus identity does not bind frozen source epoch"
            )

    queries: list[dict[str, object]] = []
    expected_answer_key_ids: set[str] = set()
    trial_order: list[str] = []
    for raw_query in preregistration.queries:
        case_id = str(raw_query["case_id"])
        family = str(raw_query["family"])
        repetition_index = raw_query["repetition_index"]
        query_index = raw_query["query_index"]
        warm_or_cold = str(raw_query["warm_or_cold"]).lower()
        if type(repetition_index) is not int or type(query_index) is not int:
            raise EvaluationManifestError("preregistration query identity is malformed")
        query_identity = ":".join(
            (case_id, family, str(repetition_index), warm_or_cold, str(query_index))
        )
        expected_answer_key_ids.add(query_identity)
        answer_key = answer_keys.get(query_identity)
        if not isinstance(answer_key, AnswerKey):
            raise EvaluationManifestError("materialization is missing a query-specific AnswerKey")
        answer_payload = _materialized_answer_key_payload(
            answer_key,
            source_census_digest=source_census_digest,
            path_policy_digest=policy_document_digest,
        )
        answer_query = _mapping(answer_payload["query"], "AnswerKey query")
        logical_repo_ids = tuple(raw_query["logical_repo_ids"])
        refs_by_id = _mapping(raw_query["refs"], "preregistration query refs")
        refs = tuple(str(refs_by_id[logical_repo_id]) for logical_repo_id in logical_repo_ids)
        path_prefixes = tuple(raw_query["path_prefixes"])
        languages = tuple(raw_query["languages"])
        filters_material = {
            "logical_repo_ids": list(logical_repo_ids),
            "refs": list(refs),
            "path_prefixes": list(path_prefixes),
            "languages": list(languages),
            "max_results": raw_query["max_results"],
            "max_context_lines": raw_query["max_context_lines"],
            "timeout_ms": raw_query["timeout_ms"],
        }
        query_material = {
            "query": raw_query["query"],
            "regex": raw_query["regex"],
            "case_sensitive": raw_query["case_sensitive"],
        }
        if (
            answer_key.case_id != case_id
            or answer_query["query"] != raw_query["query"]
            or answer_query["regex"] != raw_query["regex"]
            or answer_query["case_sensitive"] != raw_query["case_sensitive"]
            or tuple(answer_query["repository_ids"]) != logical_repo_ids
            or tuple(answer_query["refs"]) != refs
            or tuple(answer_query["path_prefixes"]) != path_prefixes
            or tuple(answer_query["languages"]) != languages
            or answer_query["limit"] != raw_query["max_results"]
            or answer_query["context_lines"] != raw_query["max_context_lines"]
            or answer_query["timeout_ms"] != raw_query["timeout_ms"]
        ):
            raise EvaluationManifestError("AnswerKey query bytes do not bind preregistered query")
        candidate_order = tuple(str(item).lower() for item in raw_query["candidate_order"])
        if candidate_order not in {("baseline", "zoekt"), ("zoekt", "baseline")}:
            raise EvaluationManifestError("preregistration candidate order is malformed")
        row = {
            "case_id": case_id,
            "family": family,
            "query_digest": _digest_json(query_material),
            "logical_repo_ids": list(logical_repo_ids),
            "refs": list(refs),
            "path_prefixes": list(path_prefixes),
            "languages": list(languages),
            "filters_digest": _digest_json(filters_material),
            "answer_key_digest": answer_key.digest,
            "forbidden_answer_digest": _digest_json(
                [list(identity) for identity in answer_key.forbidden_identities]
            ),
            "deterministic_grader_id": raw_query["deterministic_grader_id"],
            "recall_threshold": raw_query["recall_threshold"],
            "completeness_threshold": raw_query["completeness_threshold"],
            "false_positive_ceiling": raw_query["false_positive_ceiling"],
            "max_results": raw_query["max_results"],
            "max_context_lines": raw_query["max_context_lines"],
            "timeout_ms": raw_query["timeout_ms"],
            "warm_or_cold": warm_or_cold,
            "repetition_index": repetition_index,
            "query_index": query_index,
            "candidate_order": list(candidate_order),
        }
        queries.append(row)
        trial_order.extend(f"{query_identity}:{candidate}" for candidate in candidate_order)
    if set(answer_keys) != expected_answer_key_ids:
        raise EvaluationManifestError("materialization AnswerKeys do not match frozen query identities")

    common_envelope = _mapping(preregistration.resource_envelopes["common"], "common envelope")
    resource_envelopes = {
        topology_id: {
            "max_cpu_ms": common_envelope["full_build_ms_max"],
            "max_rss_bytes": preregistration.resource_envelopes[topology_id][
                "peak_rss_bytes_max"
            ],
            "max_disk_bytes": 8_589_934_592,
        }
        for topology_id in ("T0", "T1")
    }
    payload: dict[str, object] = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "operation_key": preregistration.operation_key,
        "protected_source": protected,
        "authority_blobs": authority,
        "corpus": list(parsed_corpus),
        "queries": queries,
        "path_policy_candidates": ["P0", "P1", "P2"],
        "trial_order": trial_order,
        "freshness_targets": _thaw_json(preregistration.freshness_targets),
        "resource_envelopes": resource_envelopes,
        "materiality_bands": _thaw_json(preregistration.materiality_rule),
        "hard_failure_rules_digest": _digest_json(list(preregistration.hard_failure_rules)),
        "tie_break_rule_digest": _digest_json(_thaw_json(preregistration.materiality_rule)),
        "real_preregistration_digest": preregistration.digest,
        "failure_injections": list(preregistration.failure_injections),
        "path_policy_rules": {
            "policy_document_digest": policy_document_digest,
            "p0_allowed_non_recall_justifications": list(allowed_p0),
        },
        "decision_law": _thaw_json(preregistration.decision_law),
    }
    return parse_evaluation_manifest(canonical_manifest_bytes(payload))


def parse_evaluation_manifest(document: bytes | bytearray | str) -> EvaluationManifest:
    """Parse duplicate-key-safe JSON and validate every frozen experiment field."""

    payload = _strict_json_loads(document)
    if not isinstance(payload, Mapping):
        raise EvaluationManifestError("evaluation manifest must be an object")
    _exact_fields(payload, _TOP_LEVEL_FIELDS, "evaluation manifest")
    if payload["schema_version"] != MANIFEST_SCHEMA_VERSION:
        raise EvaluationManifestError("schema_version is not the frozen evaluation manifest version")

    operation_key = _identifier(payload["operation_key"], "operation_key")
    protected_source = _parse_protected_source(payload["protected_source"])
    authority_blobs = _parse_authority_blobs(payload["authority_blobs"])
    corpus = _parse_corpus(payload["corpus"])
    queries = _parse_queries(payload["queries"], corpus)
    trial_order = _parse_trial_order(payload["trial_order"], queries)
    policies = _parse_path_policies(payload["path_policy_candidates"])
    freshness_targets = _json_object(payload["freshness_targets"], "freshness_targets")
    resource_envelopes = _parse_resource_envelopes(payload["resource_envelopes"])
    materiality_bands = _json_object(payload["materiality_bands"], "materiality_bands")
    hard_failure_rules_digest = _sha256(
        payload["hard_failure_rules_digest"], "hard_failure_rules_digest"
    )
    tie_break_rule_digest = _sha256(payload["tie_break_rule_digest"], "tie_break_rule_digest")
    real_preregistration_digest = _sha256(
        payload["real_preregistration_digest"], "real_preregistration_digest"
    )
    failure_injections = _parse_closed_text_list(
        payload["failure_injections"], "failure_injections"
    )
    path_policy_rules = _json_object(payload["path_policy_rules"], "path_policy_rules")
    decision_law = _parse_generic_decision_law(payload["decision_law"])

    canonical = canonical_manifest_bytes(payload)
    return EvaluationManifest(
        canonical_bytes=canonical,
        digest=hashlib.sha256(canonical).hexdigest(),
        operation_key=operation_key,
        protected_source=MappingProxyType(protected_source),
        authority_blobs=MappingProxyType(authority_blobs),
        corpus=tuple(MappingProxyType(row) for row in corpus),
        queries=queries,
        path_policy_candidates=policies,
        trial_order=trial_order,
        freshness_targets=_frozen_mapping(freshness_targets),
        resource_envelopes=_frozen_mapping(resource_envelopes),
        materiality_bands=_frozen_mapping(materiality_bands),
        hard_failure_rules_digest=hard_failure_rules_digest,
        tie_break_rule_digest=tie_break_rule_digest,
        real_preregistration_digest=real_preregistration_digest,
        failure_injections=failure_injections,
        path_policy_rules=_frozen_mapping(path_policy_rules),
        decision_law=_frozen_mapping(decision_law),
    )


def canonical_manifest_bytes(payload: Mapping[str, object]) -> bytes:
    """Return the only byte representation eligible for the manifest digest."""

    try:
        _assert_json_finite(payload)
        return json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise EvaluationManifestError("evaluation manifest cannot be canonical JSON") from error


def _digest_json(value: object) -> str:
    """Hash one canonical closed JSON value without trusting caller formatting."""

    try:
        _assert_json_finite(value)
        encoded = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise EvaluationManifestError("materialized value cannot be canonical JSON") from error
    return hashlib.sha256(encoded).hexdigest()


def _materialized_answer_key_payload(
    answer_key: AnswerKey,
    *,
    source_census_digest: str,
    path_policy_digest: str,
) -> Mapping[str, object]:
    """Parse and bind an AnswerKey before it can materialize a real manifest."""

    if not isinstance(answer_key, AnswerKey):
        raise EvaluationManifestError("AnswerKey must use the closed source-derived type")
    if hashlib.sha256(answer_key.canonical_bytes).hexdigest() != answer_key.digest:
        raise EvaluationManifestError("AnswerKey digest does not bind canonical bytes")
    payload = _strict_json_loads(answer_key.canonical_bytes)
    mapping = _mapping(payload, "AnswerKey")
    expected = frozenset(
        {"case_id", "census_digest", "path_policy_digest", "query", "expected", "forbidden"}
    )
    _exact_fields(mapping, expected, "AnswerKey")
    if canonical_manifest_bytes(mapping) != answer_key.canonical_bytes:
        raise EvaluationManifestError("AnswerKey must use canonical JSON")
    if mapping["census_digest"] != source_census_digest:
        raise EvaluationManifestError("AnswerKey does not bind sealed source census")
    if mapping["path_policy_digest"] != path_policy_digest:
        raise EvaluationManifestError("AnswerKey does not bind selected path policy")
    if answer_key.path_policy_digest != path_policy_digest:
        raise EvaluationManifestError("AnswerKey public path policy identity disagrees")
    _sha256(mapping["census_digest"], "AnswerKey census_digest")
    _sha256(mapping["path_policy_digest"], "AnswerKey path_policy_digest")
    return mapping


def _thaw_json(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    if isinstance(value, list):
        return [_thaw_json(item) for item in value]
    return value


def _strict_json_loads(document: bytes | bytearray | str) -> object:
    try:
        if isinstance(document, (bytes, bytearray)):
            text = bytes(document).decode("utf-8")
        elif isinstance(document, str):
            text = document
        else:
            raise TypeError("document must be UTF-8 bytes or text")
        return json.loads(
            text,
            object_pairs_hook=_no_duplicate_object,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as error:
        if isinstance(error, EvaluationManifestError):
            raise
        raise EvaluationManifestError(str(error)) from error


def _parse_protected_source(value: object) -> dict[str, str]:
    source = _mapping(value, "protected_source")
    _exact_fields(source, _PROTECTED_SOURCE_FIELDS, "protected_source")
    return {
        "repository": _repository(source["repository"], "protected_source.repository"),
        "commit": _sha1(source["commit"], "protected_source.commit"),
        "tree": _sha1(source["tree"], "protected_source.tree"),
        "skillpack_index_blob": _sha1(
            source["skillpack_index_blob"], "protected_source.skillpack_index_blob"
        ),
    }


def _parse_authority_blobs(value: object) -> dict[str, str]:
    blobs = _mapping(value, "authority_blobs")
    _exact_fields(blobs, _AUTHORITY_BLOB_FIELDS, "authority_blobs")
    return {key: _sha1(blobs[key], f"authority_blobs.{key}") for key in sorted(blobs)}


def _parse_corpus(value: object) -> tuple[dict[str, str], ...]:
    rows = _nonempty_list(value, "corpus")
    parsed: list[dict[str, str]] = []
    logical_ids: set[str] = set()
    repository_refs: set[tuple[str, str]] = set()
    for index, raw in enumerate(rows):
        row = _mapping(raw, f"corpus[{index}]")
        _exact_fields(row, _CORPUS_FIELDS, f"corpus[{index}]")
        parsed_row = {
            "logical_repo_id": _identifier(row["logical_repo_id"], "logical_repo_id"),
            "canonical_repository": _repository(
                row["canonical_repository"], "canonical_repository"
            ),
            "ref": _identifier(row["ref"], "ref"),
            "commit": _sha1(row["commit"], "commit"),
            "tree": _sha1(row["tree"], "tree"),
            "blob_census_digest": _sha256(row["blob_census_digest"], "blob_census_digest"),
            "include_exclude_policy_digest": _sha256(
                row["include_exclude_policy_digest"], "include_exclude_policy_digest"
            ),
            "submodule_lfs_generated_vendor_oversize_disposition_digest": _sha256(
                row["submodule_lfs_generated_vendor_oversize_disposition_digest"],
                "submodule_lfs_generated_vendor_oversize_disposition_digest",
            ),
        }
        if parsed_row["logical_repo_id"] in logical_ids:
            raise EvaluationManifestError("corpus contains duplicate logical_repo_id")
        identity = (parsed_row["canonical_repository"], parsed_row["ref"])
        if identity in repository_refs:
            raise EvaluationManifestError("corpus contains duplicate canonical_repository/ref")
        logical_ids.add(parsed_row["logical_repo_id"])
        repository_refs.add(identity)
        parsed.append(parsed_row)
    return tuple(parsed)


def _parse_queries(
    value: object, corpus: Sequence[Mapping[str, str]]
) -> tuple[EvaluationQuery, ...]:
    rows = _nonempty_list(value, "queries")
    known_ids = {row["logical_repo_id"] for row in corpus}
    known_refs = {row["ref"] for row in corpus}
    cases: set[str] = set()
    query_indices: set[int] = set()
    query_identities: set[tuple[str, str, int, str]] = set()
    queries: list[EvaluationQuery] = []
    for index, raw in enumerate(rows):
        row = _mapping(raw, f"queries[{index}]")
        _exact_fields(row, _QUERY_FIELDS, f"queries[{index}]")
        case_id = _identifier(row["case_id"], "case_id")
        logical_repo_ids = _identifier_list(row["logical_repo_ids"], "logical_repo_ids")
        refs = _identifier_list(row["refs"], "refs")
        if not set(logical_repo_ids) <= known_ids:
            raise EvaluationManifestError("query names an unregistered logical_repo_id")
        if not set(refs) <= known_refs:
            raise EvaluationManifestError("query names an unregistered ref")
        warm_or_cold = row["warm_or_cold"]
        if warm_or_cold not in {"warm", "cold"}:
            raise EvaluationManifestError("warm_or_cold must be warm or cold")
        family = _identifier(row["family"], "family")
        repetition_index = _nonnegative_int(row["repetition_index"], "repetition_index")
        query_index = _positive_int(row["query_index"], "query_index")
        identity = (case_id, family, repetition_index, warm_or_cold)
        if identity in query_identities:
            raise EvaluationManifestError(
                "queries contain duplicate case/family/repetition/warm-cold identity"
            )
        if query_index in query_indices:
            raise EvaluationManifestError("queries contain duplicate query_index")
        candidate_order = tuple(row["candidate_order"])
        if candidate_order not in {
            ("baseline", "zoekt"),
            ("zoekt", "baseline"),
        }:
            raise EvaluationManifestError(
                "candidate_order must counterbalance baseline and zoekt"
            )
        query = EvaluationQuery(
            case_id=case_id,
            family=family,
            query_digest=_sha256(row["query_digest"], "query_digest"),
            logical_repo_ids=logical_repo_ids,
            refs=refs,
            path_prefixes=_path_prefix_list(row["path_prefixes"], "path_prefixes"),
            languages=_optional_identifier_list(row["languages"], "languages"),
            filters_digest=_sha256(row["filters_digest"], "filters_digest"),
            answer_key_digest=_sha256(row["answer_key_digest"], "answer_key_digest"),
            forbidden_answer_digest=_sha256(
                row["forbidden_answer_digest"], "forbidden_answer_digest"
            ),
            deterministic_grader_id=_identifier(
                row["deterministic_grader_id"], "deterministic_grader_id"
            ),
            recall_threshold=_probability(row["recall_threshold"], "recall_threshold"),
            completeness_threshold=_probability(
                row["completeness_threshold"], "completeness_threshold"
            ),
            false_positive_ceiling=_probability(
                row["false_positive_ceiling"], "false_positive_ceiling"
            ),
            max_results=_bounded_int(row["max_results"], "max_results", 1, 100),
            max_context_lines=_bounded_int(
                row["max_context_lines"], "max_context_lines", 0, 8
            ),
            timeout_ms=_bounded_int(row["timeout_ms"], "timeout_ms", 1, 60_000),
            warm_or_cold=warm_or_cold,
            repetition_index=repetition_index,
            query_index=query_index,
            candidate_order=(candidate_order[0], candidate_order[1]),
        )
        cases.add(case_id)
        query_indices.add(query_index)
        query_identities.add(identity)
        queries.append(query)
    if not _REQUIRED_CASES <= cases:
        raise EvaluationManifestError("queries must include E1, X3, R3 and A1")
    for case_id in _REQUIRED_CASES:
        case_queries = tuple(query for query in queries if query.case_id == case_id)
        thermal_states = {query.warm_or_cold for query in case_queries}
        first_candidates = {query.candidate_order[0] for query in case_queries}
        if thermal_states != {"cold", "warm"}:
            raise EvaluationManifestError(
                f"{case_id} requires both cold and warm query repetitions"
            )
        if first_candidates != {"baseline", "zoekt"}:
            raise EvaluationManifestError(
                f"{case_id} cold/warm repetitions must counterbalance candidate order"
            )
    return tuple(queries)


def _parse_trial_order(value: object, queries: Sequence[EvaluationQuery]) -> tuple[str, ...]:
    trial_order = _nonempty_list(value, "trial_order")
    if not all(isinstance(item, str) for item in trial_order):
        raise EvaluationManifestError("trial_order must contain strings")
    order = tuple(trial_order)
    if len(order) != len(set(order)):
        raise EvaluationManifestError("trial_order must not contain duplicates")
    expected = {query.trial_id(candidate) for query in queries for candidate in ("baseline", "zoekt")}
    if set(order) != expected:
        raise EvaluationManifestError("trial_order must bind baseline and zoekt once per query")
    for query in queries:
        first = query.trial_id(query.candidate_order[0])
        second = query.trial_id(query.candidate_order[1])
        first_index = order.index(first)
        second_index = order.index(second)
        if second_index != first_index + 1:
            raise EvaluationManifestError(
                "trial_order must retain each query's frozen adjacent candidate order"
            )
    return order


def _parse_path_policies(value: object) -> tuple[str, ...]:
    policies = _nonempty_list(value, "path_policy_candidates")
    if tuple(policies) != _PATH_POLICIES:
        raise EvaluationManifestError("path_policy_candidates must be P0, P1, P2 in frozen order")
    return _PATH_POLICIES


def _parse_resource_envelopes(value: object) -> dict[str, object]:
    envelopes = _json_object(value, "resource_envelopes")
    if set(envelopes) != {"T0", "T1"}:
        raise EvaluationManifestError("resource_envelopes must bind exactly T0 and T1")
    parsed: dict[str, object] = {}
    for topology_id in ("T0", "T1"):
        envelope = _mapping(envelopes[topology_id], f"resource_envelopes.{topology_id}")
        _exact_fields(
            envelope,
            _RESOURCE_ENVELOPE_FIELDS,
            f"resource_envelopes.{topology_id}",
        )
        parsed[topology_id] = {
            key: _positive_int(
                envelope[key],
                f"resource_envelopes.{topology_id}.{key}",
            )
            for key in sorted(envelope)
        }
    return parsed


def _parse_real_source_epoch(value: object) -> dict[str, dict[str, str]]:
    """Validate each immutable repository/ref/commit/tree coordinate once."""

    epoch = _mapping(value, "source_epoch")
    _exact_fields(epoch, _REAL_SOURCE_EPOCH_REPOSITORIES, "source_epoch")
    parsed: dict[str, dict[str, str]] = {}
    for logical_repo_id in sorted(_REAL_SOURCE_EPOCH_REPOSITORIES):
        row = _mapping(epoch[logical_repo_id], f"source_epoch.{logical_repo_id}")
        _exact_fields(
            row,
            frozenset({"repository", "ref", "commit", "tree"}),
            f"source_epoch.{logical_repo_id}",
        )
        parsed[logical_repo_id] = {
            "repository": _repository(row["repository"], f"{logical_repo_id}.repository"),
            "ref": _identifier(row["ref"], f"{logical_repo_id}.ref"),
            "commit": _sha1(row["commit"], f"{logical_repo_id}.commit"),
            "tree": _sha1(row["tree"], f"{logical_repo_id}.tree"),
        }
    return parsed


def _parse_real_case_definitions(value: object) -> tuple[dict[str, object], ...]:
    """Keep the charter case definitions closed before query plans reference them."""

    rows = _nonempty_list(value, "case_definitions")
    expected_fields = frozenset(
        {
            "case_id",
            "category",
            "question",
            "repositories",
            "critical_files",
            "critical_symbols",
            "must_not_conclude",
        }
    )
    cases: set[str] = set()
    parsed: list[dict[str, object]] = []
    for index, raw in enumerate(rows):
        row = _mapping(raw, f"case_definitions[{index}]")
        _exact_fields(row, expected_fields, f"case_definitions[{index}]")
        case_id = _identifier(row["case_id"], "case_id")
        if case_id not in _REAL_CASE_IDS or case_id in cases:
            raise EvaluationManifestError("case_definitions must contain each frozen case once")
        repositories = _identifier_list(row["repositories"], "case repositories")
        if not set(repositories) <= _REAL_SOURCE_EPOCH_REPOSITORIES:
            raise EvaluationManifestError("case_definitions names an unknown source repository")
        parsed.append(
            {
                "case_id": case_id,
                "category": _identifier(row["category"], "case category"),
                "question": _identifier(row["question"], "case question"),
                "repositories": list(repositories),
                "critical_files": list(
                    _identifier_list(row["critical_files"], "critical_files")
                ),
                "critical_symbols": list(
                    _identifier_list(row["critical_symbols"], "critical_symbols")
                ),
                "must_not_conclude": list(
                    _identifier_list(row["must_not_conclude"], "must_not_conclude")
                ),
            }
        )
        cases.add(case_id)
    if cases != _REAL_CASE_IDS:
        raise EvaluationManifestError("case_definitions must cover E1, X3, R3, A1 and T1")
    return tuple(parsed)


def _parse_real_queries(
    value: object,
    source_epoch: Mapping[str, Mapping[str, str]],
    case_definitions: tuple[Mapping[str, object], ...],
) -> tuple[dict[str, object], ...]:
    """Validate executable query plans before answer keys or candidates can consume them."""

    rows = _nonempty_list(value, "queries")
    expected_fields = frozenset(
        {
            "candidate_order",
            "case_id",
            "case_sensitive",
            "completeness_threshold",
            "deterministic_grader_id",
            "false_positive_ceiling",
            "family",
            "languages",
            "logical_repo_ids",
            "max_context_lines",
            "max_results",
            "path_prefixes",
            "query",
            "query_index",
            "recall_threshold",
            "refs",
            "regex",
            "repetition_index",
            "timeout_ms",
            "warm_or_cold",
        }
    )
    known_cases = {str(row["case_id"]) for row in case_definitions}
    query_indices: set[int] = set()
    unique_trials: set[tuple[str, str, int, str]] = set()
    parsed: list[dict[str, object]] = []
    for index, raw in enumerate(rows):
        row = _mapping(raw, f"queries[{index}]")
        _exact_fields(row, expected_fields, f"queries[{index}]")
        case_id = _identifier(row["case_id"], "query case_id")
        if case_id not in known_cases:
            raise EvaluationManifestError("query names an unknown case")
        family = _identifier(row["family"], "query family")
        query_index = _positive_int(row["query_index"], "query_index")
        if query_index in query_indices:
            raise EvaluationManifestError("queries must not duplicate query_index")
        repetition_index = _nonnegative_int(row["repetition_index"], "repetition_index")
        warm_or_cold = row["warm_or_cold"]
        if warm_or_cold not in {"COLD", "WARM"}:
            raise EvaluationManifestError("warm_or_cold must be COLD or WARM")
        identity = (case_id, family, repetition_index, warm_or_cold)
        if identity in unique_trials:
            raise EvaluationManifestError("queries duplicate a case/family/repetition/warm-cold identity")
        if tuple(row["candidate_order"]) not in {
            ("BASELINE", "ZOEKT"),
            ("ZOEKT", "BASELINE"),
        }:
            raise EvaluationManifestError("candidate_order must counterbalance baseline and zoekt")
        if type(row["regex"]) is not bool or type(row["case_sensitive"]) is not bool:
            raise EvaluationManifestError("query regex and case_sensitive must be booleans")
        logical_repo_ids = _identifier_list(row["logical_repo_ids"], "logical_repo_ids")
        if not set(logical_repo_ids) <= set(source_epoch):
            raise EvaluationManifestError("query names an unknown source repository")
        refs = _mapping(row["refs"], "query refs")
        if set(refs) != set(logical_repo_ids):
            raise EvaluationManifestError("query refs must bind exactly its selected repositories")
        parsed_refs: dict[str, str] = {}
        for logical_repo_id in logical_repo_ids:
            ref = _identifier(refs[logical_repo_id], f"query refs.{logical_repo_id}")
            if ref != source_epoch[logical_repo_id]["ref"]:
                raise EvaluationManifestError("query ref does not bind the frozen source epoch")
            parsed_refs[logical_repo_id] = ref
        false_positive_ceiling = _probability(
            row["false_positive_ceiling"], "false_positive_ceiling"
        )
        parsed.append(
            {
                "candidate_order": list(row["candidate_order"]),
                "case_id": case_id,
                "case_sensitive": row["case_sensitive"],
                "completeness_threshold": _probability(
                    row["completeness_threshold"], "completeness_threshold"
                ),
                "deterministic_grader_id": _identifier(
                    row["deterministic_grader_id"], "deterministic_grader_id"
                ),
                "false_positive_ceiling": false_positive_ceiling,
                "family": family,
                "languages": list(_optional_identifier_list(row["languages"], "languages")),
                "logical_repo_ids": list(logical_repo_ids),
                "max_context_lines": _bounded_int(
                    row["max_context_lines"], "max_context_lines", 0, 8
                ),
                "max_results": _bounded_int(row["max_results"], "max_results", 1, 100),
                "path_prefixes": list(
                    _optional_identifier_list(row["path_prefixes"], "path_prefixes")
                ),
                "query": _identifier(row["query"], "query"),
                "query_index": query_index,
                "recall_threshold": _probability(
                    row["recall_threshold"], "recall_threshold"
                ),
                "refs": parsed_refs,
                "regex": row["regex"],
                "repetition_index": repetition_index,
                "timeout_ms": _bounded_int(row["timeout_ms"], "timeout_ms", 1, 60_000),
                "warm_or_cold": warm_or_cold,
            }
        )
        query_indices.add(query_index)
        unique_trials.add(identity)
    if len(parsed) != 20 or query_indices != set(range(1, 21)):
        raise EvaluationManifestError("Epoch 1 must contain exactly 20 ordered query rows")
    if not _REAL_CASE_IDS <= {str(row["case_id"]) for row in parsed}:
        raise EvaluationManifestError("queries must cover every frozen benchmark case")
    return tuple(parsed)


def _parse_closed_text_list(
    value: object, label: str, *, expected_count: int | None = None
) -> tuple[str, ...]:
    values = _identifier_list(value, label)
    if expected_count is not None and len(values) != expected_count:
        raise EvaluationManifestError(f"{label} must contain exactly {expected_count} entries")
    return values


def _parse_real_decision_law(value: object) -> dict[str, object]:
    law = _mapping(value, "decision_law")
    _exact_fields(
        law,
        frozenset(
            {
                "all_final_decisions_require_complete_real_evidence",
                "final_decisions",
                "incomplete_or_synthetic_decision",
                "incomplete_or_synthetic_state",
            }
        ),
        "decision_law",
    )
    if law["all_final_decisions_require_complete_real_evidence"] is not True:
        raise EvaluationManifestError("decision_law must require complete real evidence")
    final_decisions = _identifier_list(law["final_decisions"], "final_decisions")
    if set(final_decisions) != _FINAL_DECISIONS:
        raise EvaluationManifestError("decision_law final decisions are not closed")
    if law["incomplete_or_synthetic_decision"] is not None:
        raise EvaluationManifestError("incomplete or synthetic evidence must not emit a final decision")
    if law["incomplete_or_synthetic_state"] != "NON_DECISION":
        raise EvaluationManifestError("incomplete or synthetic evidence must be NON_DECISION")
    return {
        "all_final_decisions_require_complete_real_evidence": True,
        "final_decisions": list(final_decisions),
        "incomplete_or_synthetic_decision": None,
        "incomplete_or_synthetic_state": "NON_DECISION",
    }


def _parse_generic_decision_law(value: object) -> dict[str, object]:
    """Require the materialized manifest to preserve the preregistered result law."""

    return _parse_real_decision_law(value)


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise EvaluationManifestError(f"{label} must be an object")
    if not all(isinstance(key, str) for key in value):
        raise EvaluationManifestError(f"{label} must use string keys")
    return value


def _json_object(value: object, label: str) -> dict[str, object]:
    mapping = _mapping(value, label)
    if not mapping:
        raise EvaluationManifestError(f"{label} must not be empty")
    _assert_json_finite(mapping)
    return dict(mapping)


def _nonempty_list(value: object, label: str) -> list[object]:
    if not isinstance(value, list) or not value:
        raise EvaluationManifestError(f"{label} must be a non-empty list")
    return value


def _exact_fields(value: Mapping[str, object], expected: frozenset[str], label: str) -> None:
    missing = expected - set(value)
    unknown = set(value) - expected
    if missing:
        raise EvaluationManifestError(f"{label} missing fields: {sorted(missing)}")
    if unknown:
        raise EvaluationManifestError(f"{label} has unknown fields: {sorted(unknown)}")


def _identifier(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value.encode("utf-8")) > 256
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise EvaluationManifestError(f"{label} must be bounded printable text")
    return value


def _repository(value: object, label: str) -> str:
    repository = _identifier(value, label)
    if repository.startswith(("/", "\\")) or "\\" in repository or repository.count("/") != 1:
        raise EvaluationManifestError(f"{label} must be an owner/repository identity")
    return repository


def _identifier_list(value: object, label: str) -> tuple[str, ...]:
    values = _nonempty_list(value, label)
    identifiers = tuple(_identifier(item, label) for item in values)
    if len(identifiers) != len(set(identifiers)):
        raise EvaluationManifestError(f"{label} must not contain duplicates")
    return identifiers


def _optional_identifier_list(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise EvaluationManifestError(f"{label} must be a list")
    identifiers = tuple(_identifier(item, label) for item in value)
    if len(identifiers) != len(set(identifiers)):
        raise EvaluationManifestError(f"{label} must not contain duplicates")
    return identifiers


def _path_prefix_list(value: object, label: str) -> tuple[str, ...]:
    """Accept only explicit repository-relative path filters in a query plan."""

    if not isinstance(value, list):
        raise EvaluationManifestError(f"{label} must be a list")
    prefixes: list[str] = []
    for raw in value:
        prefix = _identifier(raw, label)
        if (
            prefix.startswith(("/", "\\"))
            or "\\" in prefix
            or any(part in {"", ".", ".."} for part in prefix.split("/"))
        ):
            raise EvaluationManifestError(f"{label} must use repository-relative paths")
        prefixes.append(prefix.rstrip("/"))
    if len(prefixes) != len(set(prefixes)):
        raise EvaluationManifestError(f"{label} must not contain duplicates")
    return tuple(prefixes)


def _sha1(value: object, label: str) -> str:
    if not isinstance(value, str) or _SHA1_RE.fullmatch(value) is None:
        raise EvaluationManifestError(f"{label} must be a lowercase SHA-1")
    return value


def _sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise EvaluationManifestError(f"{label} must be a lowercase SHA-256")
    return value


def _probability(value: object, label: str) -> float:
    if type(value) not in {int, float} or not math.isfinite(float(value)) or not 0 <= value <= 1:
        raise EvaluationManifestError(f"{label} must be a finite probability in 0..1")
    return float(value)


def _nonnegative_int(value: object, label: str) -> int:
    if type(value) is not int or value < 0:
        raise EvaluationManifestError(f"{label} must be a non-negative integer")
    return value


def _bounded_int(value: object, label: str, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise EvaluationManifestError(f"{label} must be an integer in {minimum}..{maximum}")
    return value


def _positive_int(value: object, label: str) -> int:
    if type(value) is not int or value < 1:
        raise EvaluationManifestError(f"{label} must be a positive integer")
    return value


def _no_duplicate_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise EvaluationManifestError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> object:
    raise EvaluationManifestError(f"non-finite JSON constant: {value}")


def _assert_json_finite(value: object) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise EvaluationManifestError("non-finite JSON value")
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise EvaluationManifestError("JSON object keys must be strings")
        for item in value.values():
            _assert_json_finite(item)
    elif isinstance(value, list):
        for item in value:
            _assert_json_finite(item)


def _frozen_mapping(value: Mapping[str, object]) -> Mapping[str, object]:
    frozen = _freeze_json(value)
    assert isinstance(frozen, Mapping)
    return frozen


def _freeze_json(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {str(key): _freeze_json(item) for key, item in value.items()}
        )
    if isinstance(value, list):
        return tuple(_freeze_json(item) for item in value)
    return value
