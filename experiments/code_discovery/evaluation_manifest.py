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


MANIFEST_SCHEMA_VERSION: Final = "mastermind.codeintel_evaluation_manifest.v1"
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
        "case_id",
        "family",
        "query_digest",
        "logical_repo_ids",
        "refs",
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
    }
)
_REQUIRED_CASES: Final = frozenset({"E1", "X3", "R3", "A1"})
_PATH_POLICIES: Final = ("P0", "P1", "P2")
_RESOURCE_ENVELOPE_FIELDS: Final = frozenset(
    {"max_cpu_ms", "max_rss_bytes", "max_disk_bytes"}
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
    filters_digest: str
    answer_key_digest: str
    forbidden_answer_digest: str
    deterministic_grader_id: str
    recall_threshold: float
    completeness_threshold: float
    false_positive_ceiling: int
    max_results: int
    max_context_lines: int
    timeout_ms: int
    warm_or_cold: str
    repetition_index: int


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
    queries: list[EvaluationQuery] = []
    for index, raw in enumerate(rows):
        row = _mapping(raw, f"queries[{index}]")
        _exact_fields(row, _QUERY_FIELDS, f"queries[{index}]")
        case_id = _identifier(row["case_id"], "case_id")
        if case_id in cases:
            raise EvaluationManifestError("queries contain duplicate case_id")
        logical_repo_ids = _identifier_list(row["logical_repo_ids"], "logical_repo_ids")
        refs = _identifier_list(row["refs"], "refs")
        if not set(logical_repo_ids) <= known_ids:
            raise EvaluationManifestError("query names an unregistered logical_repo_id")
        if not set(refs) <= known_refs:
            raise EvaluationManifestError("query names an unregistered ref")
        warm_or_cold = row["warm_or_cold"]
        if warm_or_cold not in {"warm", "cold"}:
            raise EvaluationManifestError("warm_or_cold must be warm or cold")
        query = EvaluationQuery(
            case_id=case_id,
            family=_identifier(row["family"], "family"),
            query_digest=_sha256(row["query_digest"], "query_digest"),
            logical_repo_ids=logical_repo_ids,
            refs=refs,
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
            false_positive_ceiling=_nonnegative_int(
                row["false_positive_ceiling"], "false_positive_ceiling"
            ),
            max_results=_bounded_int(row["max_results"], "max_results", 1, 100),
            max_context_lines=_bounded_int(
                row["max_context_lines"], "max_context_lines", 0, 8
            ),
            timeout_ms=_bounded_int(row["timeout_ms"], "timeout_ms", 1, 60_000),
            warm_or_cold=warm_or_cold,
            repetition_index=_nonnegative_int(row["repetition_index"], "repetition_index"),
        )
        cases.add(case_id)
        queries.append(query)
    if not _REQUIRED_CASES <= cases:
        raise EvaluationManifestError("queries must include E1, X3, R3 and A1")
    return tuple(queries)


def _parse_trial_order(value: object, queries: Sequence[EvaluationQuery]) -> tuple[str, ...]:
    trial_order = _nonempty_list(value, "trial_order")
    if not all(isinstance(item, str) for item in trial_order):
        raise EvaluationManifestError("trial_order must contain strings")
    order = tuple(trial_order)
    if len(order) != len(set(order)):
        raise EvaluationManifestError("trial_order must not contain duplicates")
    expected = {
        f"{query.case_id}:{candidate}"
        for query in queries
        for candidate in ("baseline", "zoekt")
    }
    if set(order) != expected:
        raise EvaluationManifestError("trial_order must bind baseline and zoekt once per query")
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
