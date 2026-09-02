"""Closed contracts for the Outcome Learning V1 (OL-V1) vertical.

One sealed prospective decision-expectation receipt, one reversible GitHub PR-title
canary effect, and the deterministic evaluation/self-model/Agent-OS-projection chain
built on top of it. This module is a pure adapter: stdlib plus
:mod:`control_plane.wake_events` only. It performs no file, network, subprocess, or
environment I/O and never reads the clock — every timestamp is supplied by the caller.

Every builder here produces a closed document and validates it before returning.
Every validator raises :class:`OutcomeLearningContractError` naming the exact defect.
Missing AND unknown keys are both errors (closed-mapping validation throughout,
mirroring ``_closed_mapping`` in :mod:`control_plane.chairman_cognition_sources`).

Digest family: every ``*_digest`` / ``sealed_hash`` / ``*_sha256`` artifact-content
field (schema-level identity) is ``"sha256:" + hashlib.sha256(canonical_json_bytes(obj))
.hexdigest()``. Fields explicitly named ``*_sha256`` that identify externally observed
raw content (a git blob, a PR title string) are bare lowercase hex64 with no prefix,
mirroring the git/PR-owned identities they represent. There is exactly one canonical-
JSON implementation in this codebase; it is imported, never reimplemented.
"""
from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from typing import Any

from control_plane.wake_events import canonical_json_bytes

# --------------------------------------------------------------------------- schemas

EXPECTATION_SCHEMA = "mastermind.decision_expectation_receipt.v2"
CANARY_REQUEST_SCHEMA = "mastermind.olv1_canary_request.v1"
OUTCOME_SCHEMA = "mastermind.olv1_outcome.v1"
EVALUATION_SCHEMA = "mastermind.olv1_evaluation.v1"
SELF_MODEL_SCHEMA = "mastermind.olv1_self_model.v1"
AGENTOS_PROJECTION_SCHEMA = "mastermind.olv1_agentos_projection.v1"

PRIVACY_CLASS = "PUBLIC_SAFE"

CANARY_TOKEN = "[OL-V1-CANARY]"

RESOLUTIONS = frozenset({"HELD", "FALSIFIED", "UNRESOLVED", "NOT_TESTED", "CONFOUNDED"})
EFFECT_STATES = frozenset(
    {
        "APPLIED_AND_RESTORED",
        "EFFECT_UNKNOWN",
        "NOT_ATTEMPTED",
        "INVALIDATED_BEFORE_EFFECT",
    }
)
ASSUMPTION_ROLES = frozenset({"LOAD_BEARING", "CONTEXTUAL"})
MEMORY_INFLUENCE = frozenset(
    {"MATERIALLY_CHANGED", "CONSULTED_NO_CHANGE", "REJECTED_INAPPLICABLE"}
)
EXPECTATION_KINDS = frozenset({"probability", "count", "duration_seconds"})
EFFECT_CALL_KINDS = ("TITLE_APPLY", "TITLE_RESTORE")
PROJECTION_CANDIDATE_KINDS = frozenset(
    {"DSC_CANDIDATE", "WS_UPDATE_CANDIDATE", "DEC_CANDIDATE"}
)

FORBIDDEN_SELF_REFERENTIAL_KEYS = frozenset({"containing_commit_sha", "current_pr_head"})

_SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_HEX_RE = re.compile(r"^[0-9a-f]{64}$")
_SHA256_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")

_PUBLIC_SAFE_PATTERNS = (
    re.compile(r"\b17\d{8}\.\d{6}\b"),
    re.compile(r"xox[a-z]-"),
    re.compile(r"ghp_"),
    re.compile(r"github_pat_"),
    re.compile(r"-----BEGIN "),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    # Principal-review additions (2026-09-02, MAJOR 13):
    re.compile(r"sk-ant-"),
    re.compile(r"\bgh[sou]_"),
    re.compile(r"/Users/[A-Za-z0-9_.-]+/"),
    re.compile(
        r"\b[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b"
    ),
)


class OutcomeLearningContractError(ValueError):
    """One closed OL-V1 artifact failed a structural or semantic contract."""


# --------------------------------------------------------------------------- digests


def canonical_digest(value: Any) -> str:
    """``"sha256:" + hex`` digest over the canonical JSON bytes of ``value``."""
    return "sha256:" + hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def seal_document(doc: Mapping[str, Any], *, field: str = "sealed_hash") -> dict[str, Any]:
    """Return a copy of ``doc`` with ``field`` set to its own content digest.

    ``doc`` must NOT already carry ``field`` — sealing is a one-way act performed
    exactly once over every other key.
    """
    if not isinstance(doc, Mapping):
        raise OutcomeLearningContractError("document to seal must be a mapping")
    if field in doc:
        raise OutcomeLearningContractError(f"{field} must be absent before sealing")
    sealed = dict(doc)
    sealed[field] = canonical_digest(doc)
    return sealed


def verify_sealed(doc: Mapping[str, Any], *, field: str = "sealed_hash") -> None:
    """Raise unless ``doc[field]`` is the exact digest of every other key."""
    if not isinstance(doc, Mapping) or field not in doc:
        raise OutcomeLearningContractError(f"{field} is missing")
    stated = doc[field]
    unsealed = {key: value for key, value in doc.items() if key != field}
    expected = canonical_digest(unsealed)
    if stated != expected:
        raise OutcomeLearningContractError(
            f"{field} does not match the recomputed digest — sealed content was mutated"
        )


# --------------------------------------------------------------------------- guards


def scan_public_safe_text(doc: Any) -> None:
    """Recursively reject any string in ``doc`` matching a PUBLIC_SAFE secret shape."""
    _walk_public_safe(doc, "$")


def _walk_public_safe(value: Any, path: str) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            _walk_public_safe(item, f"{path}.{key}")
        return
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _walk_public_safe(item, f"{path}[{index}]")
        return
    if isinstance(value, str):
        for pattern in _PUBLIC_SAFE_PATTERNS:
            if pattern.search(value):
                raise OutcomeLearningContractError(
                    f"{path} fails the PUBLIC_SAFE scan (matches {pattern.pattern!r})"
                )


def _reject_forbidden_self_referential_keys(value: Any, path: str) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if key in FORBIDDEN_SELF_REFERENTIAL_KEYS:
                raise OutcomeLearningContractError(
                    f"{path}.{key} is a forbidden self-referential key"
                )
            _reject_forbidden_self_referential_keys(item, f"{path}.{key}")
        return
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _reject_forbidden_self_referential_keys(item, f"{path}[{index}]")


def _require_public_safe(doc: Mapping[str, Any], where: str) -> None:
    if doc.get("privacy_class") != PRIVACY_CLASS:
        raise OutcomeLearningContractError(f"{where}.privacy_class must be PUBLIC_SAFE")
    scan_public_safe_text(doc)


# --------------------------------------------------------------------------- primitives


def _closed_mapping(value: Any, *, required: set[str], where: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise OutcomeLearningContractError(f"{where} must be a mapping")
    keys = set(value)
    missing = required - keys
    extra = keys - required
    if missing:
        raise OutcomeLearningContractError(
            f"{where} is missing required fields: {sorted(missing)}"
        )
    if extra:
        raise OutcomeLearningContractError(
            f"{where} contains unknown fields: {sorted(extra)}"
        )
    return value


def _text(value: Any, name: str, max_len: int = 500) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise OutcomeLearningContractError(f"{name} must be a non-empty trimmed string")
    if len(value) > max_len or any(ord(char) < 32 for char in value):
        raise OutcomeLearningContractError(f"{name} is out of bounds")
    return value


def _nullable_text(value: Any, name: str, max_len: int = 500) -> str | None:
    if value is None:
        return None
    return _text(value, name, max_len)


def _bool(value: Any, name: str) -> bool:
    if type(value) is not bool:
        raise OutcomeLearningContractError(f"{name} must be a boolean")
    return value


def _true(value: Any, name: str) -> bool:
    if _bool(value, name) is not True:
        raise OutcomeLearningContractError(f"{name} must be True")
    return True


def _false(value: Any, name: str) -> bool:
    if _bool(value, name) is not False:
        raise OutcomeLearningContractError(f"{name} must be False")
    return False


def _int(value: Any, name: str, *, minimum: int | None = None, maximum: int | None = None) -> int:
    if type(value) is not int:
        raise OutcomeLearningContractError(f"{name} must be an integer")
    if minimum is not None and value < minimum:
        raise OutcomeLearningContractError(f"{name} must be >= {minimum}")
    if maximum is not None and value > maximum:
        raise OutcomeLearningContractError(f"{name} must be <= {maximum}")
    return value


def _number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise OutcomeLearningContractError(f"{name} must be a number")
    return float(value)


def _enum(value: Any, allowed: frozenset[str] | tuple[str, ...], name: str) -> str:
    text = _text(value, name, 128)
    if text not in allowed:
        raise OutcomeLearningContractError(f"unknown {name}: {text!r}")
    return text


def _sha40(value: Any, name: str) -> str:
    text = _text(value, name, 40)
    if _SHA40_RE.fullmatch(text) is None:
        raise OutcomeLearningContractError(f"{name} must be 40 lowercase hex characters")
    return text


def _sha256_hex(value: Any, name: str) -> str:
    text = _text(value, name, 64)
    if _SHA256_HEX_RE.fullmatch(text) is None:
        raise OutcomeLearningContractError(f"{name} must be 64 lowercase hex characters")
    return text


def _sha256_digest(value: Any, name: str) -> str:
    text = _text(value, name, 71)
    if _SHA256_DIGEST_RE.fullmatch(text) is None:
        raise OutcomeLearningContractError(f"{name} must be sha256:<64 lowercase hex>")
    return text


def _str_list(value: Any, name: str, *, min_len: int = 0, max_len: int = 64) -> list[str]:
    if not isinstance(value, list) or not min_len <= len(value) <= max_len:
        raise OutcomeLearningContractError(f"{name} must be a bounded list of strings")
    return [_text(item, f"{name}[{index}]", 500) for index, item in enumerate(value)]


def _unique_str_list(value: Any, name: str, *, min_len: int = 0, max_len: int = 64) -> list[str]:
    items = _str_list(value, name, min_len=min_len, max_len=max_len)
    if len(set(items)) != len(items):
        raise OutcomeLearningContractError(f"{name} contains duplicates")
    return items


def _nullable_pair(
    value: Any,
    reason: Any,
    *,
    value_name: str,
    reason_name: str,
    value_range: tuple[float, float] | None = None,
) -> tuple[float | None, str | None]:
    """Enforce "value is None XOR reason is None" (the null-reason grammar)."""
    if value is None and reason is None:
        raise OutcomeLearningContractError(
            f"exactly one of {value_name}/{reason_name} must be set"
        )
    if value is not None and reason is not None:
        raise OutcomeLearningContractError(
            f"exactly one of {value_name}/{reason_name} must be set"
        )
    if value is None:
        return None, _text(reason, reason_name, 200)
    number = _number(value, value_name)
    if value_range is not None and not value_range[0] <= number <= value_range[1]:
        raise OutcomeLearningContractError(
            f"{value_name} must be within [{value_range[0]}, {value_range[1]}]"
        )
    return number, None


# --------------------------------------------------------------------------- expectation


def _validate_decision_ref(value: Any) -> Mapping[str, Any]:
    item = _closed_mapping(value, required={"owner", "type", "id"}, where="decision_ref")
    _text(item["owner"], "decision_ref.owner", 128)
    _text(item["type"], "decision_ref.type", 128)
    _text(item["id"], "decision_ref.id", 200)
    return item


def _validate_context(value: Any) -> Mapping[str, Any]:
    item = _closed_mapping(
        value,
        required={
            "source_refs",
            "task_kind",
            "risk",
            "ambiguity",
            "program",
            "repository",
            "source_cutoff",
            "applicability_cohort",
        },
        where="context",
    )
    _unique_str_list(item["source_refs"], "context.source_refs", min_len=1, max_len=32)
    for field in ("task_kind", "risk", "ambiguity", "program", "repository", "source_cutoff"):
        _text(item[field], f"context.{field}", 200)
    _text(item["applicability_cohort"], "context.applicability_cohort", 500)
    return item


def _validate_alternatives(value: Any, chosen_action: str) -> list[Mapping[str, Any]]:
    if not isinstance(value, list) or len(value) < 2:
        raise OutcomeLearningContractError("alternatives must list at least two entries")
    seen: set[str] = set()
    chosen_eligible = False
    for index, raw in enumerate(value):
        item = _closed_mapping(
            raw,
            required={"action_id", "eligible", "exclusion_reason"},
            where=f"alternatives[{index}]",
        )
        action_id = _text(item["action_id"], f"alternatives[{index}].action_id", 128)
        if action_id in seen:
            raise OutcomeLearningContractError("duplicate alternatives[*].action_id")
        seen.add(action_id)
        eligible = _bool(item["eligible"], f"alternatives[{index}].eligible")
        reason = item["exclusion_reason"]
        if eligible and reason is not None:
            raise OutcomeLearningContractError(
                "an eligible alternative must not carry exclusion_reason"
            )
        if not eligible and reason is None:
            raise OutcomeLearningContractError(
                "an ineligible alternative must carry exclusion_reason"
            )
        if reason is not None:
            _text(reason, f"alternatives[{index}].exclusion_reason", 300)
        if action_id == chosen_action:
            chosen_eligible = eligible
    if chosen_action not in seen:
        raise OutcomeLearningContractError("chosen_action is not one of the alternatives")
    if not chosen_eligible:
        raise OutcomeLearningContractError("chosen_action must be eligible")
    return value


def _validate_assignment(value: Any) -> Mapping[str, Any]:
    item = _closed_mapping(
        value,
        required={
            "method",
            "probability",
            "probability_null_reason",
            "policy_version",
            "randomization_unit",
        },
        where="assignment",
    )
    _text(item["method"], "assignment.method", 128)
    _nullable_pair(
        item["probability"],
        item["probability_null_reason"],
        value_name="assignment.probability",
        reason_name="assignment.probability_null_reason",
        value_range=(0.0, 1.0),
    )
    _text(item["policy_version"], "assignment.policy_version", 128)
    _text(item["randomization_unit"], "assignment.randomization_unit", 128)
    return item


def _validate_expectations(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, list) or not value:
        raise OutcomeLearningContractError("expectations must be a non-empty list")
    seen: set[str] = set()
    for index, raw in enumerate(value):
        item = _closed_mapping(
            raw,
            required={"metric_id", "horizon", "estimate", "lower", "upper", "kind"},
            where=f"expectations[{index}]",
        )
        metric_id = _text(item["metric_id"], f"expectations[{index}].metric_id", 128)
        if metric_id in seen:
            raise OutcomeLearningContractError("duplicate expectations[*].metric_id")
        seen.add(metric_id)
        _text(item["horizon"], f"expectations[{index}].horizon", 32)
        kind = _enum(item["kind"], EXPECTATION_KINDS, f"expectations[{index}].kind")
        lower = _number(item["lower"], f"expectations[{index}].lower")
        estimate = _number(item["estimate"], f"expectations[{index}].estimate")
        upper = _number(item["upper"], f"expectations[{index}].upper")
        if not lower <= estimate <= upper:
            raise OutcomeLearningContractError(
                f"expectations[{index}] must satisfy lower <= estimate <= upper"
            )
        if kind == "probability" and not (0.0 <= lower and upper <= 1.0):
            raise OutcomeLearningContractError(
                f"expectations[{index}] probability values must lie within [0, 1]"
            )
        if kind in {"count", "duration_seconds"} and lower < 0:
            raise OutcomeLearningContractError(
                f"expectations[{index}] {kind} values must be non-negative"
            )
    return value


def _validate_guardrails(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, list) or not value:
        raise OutcomeLearningContractError("guardrails must be a non-empty list")
    seen: set[str] = set()
    for index, raw in enumerate(value):
        item = _closed_mapping(
            raw, required={"guardrail_id", "statement"}, where=f"guardrails[{index}]"
        )
        guardrail_id = _text(item["guardrail_id"], f"guardrails[{index}].guardrail_id", 64)
        if guardrail_id in seen:
            raise OutcomeLearningContractError("duplicate guardrails[*].guardrail_id")
        seen.add(guardrail_id)
        _text(item["statement"], f"guardrails[{index}].statement", 500)
    return value


def _validate_assumptions(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, list) or not value:
        raise OutcomeLearningContractError("assumptions must be a non-empty list")
    seen: set[str] = set()
    for index, raw in enumerate(value):
        item = _closed_mapping(
            raw,
            required={
                "assumption_id",
                "role",
                "statement",
                "evidence_refs",
                "ex_ante_confidence",
                "confidence_null_reason",
                "falsifier",
            },
            where=f"assumptions[{index}]",
        )
        assumption_id = _text(item["assumption_id"], f"assumptions[{index}].assumption_id", 64)
        if assumption_id in seen:
            raise OutcomeLearningContractError("duplicate assumptions[*].assumption_id")
        seen.add(assumption_id)
        _enum(item["role"], ASSUMPTION_ROLES, f"assumptions[{index}].role")
        _text(item["statement"], f"assumptions[{index}].statement", 500)
        _str_list(item["evidence_refs"], f"assumptions[{index}].evidence_refs", max_len=32)
        _nullable_pair(
            item["ex_ante_confidence"],
            item["confidence_null_reason"],
            value_name=f"assumptions[{index}].ex_ante_confidence",
            reason_name=f"assumptions[{index}].confidence_null_reason",
            value_range=(0.0, 1.0),
        )
        _text(item["falsifier"], f"assumptions[{index}].falsifier", 500)
    return value


def _validate_memory_exposure(value: Any) -> Mapping[str, Any]:
    item = _closed_mapping(
        value,
        required={
            "pre_memory_option_set_digest",
            "final_option_set_digest",
            "final_decision_digest",
            "consulted",
            "source_packet_digests",
        },
        where="memory_exposure",
    )
    for field in (
        "pre_memory_option_set_digest",
        "final_option_set_digest",
        "final_decision_digest",
    ):
        _sha256_digest(item[field], f"memory_exposure.{field}")
    consulted = item["consulted"]
    if not isinstance(consulted, list):
        raise OutcomeLearningContractError("memory_exposure.consulted must be a list")
    for index, raw in enumerate(consulted):
        entry = _closed_mapping(
            raw,
            required={"record_ref", "influence", "why"},
            where=f"memory_exposure.consulted[{index}]",
        )
        _text(entry["record_ref"], f"memory_exposure.consulted[{index}].record_ref", 256)
        _enum(
            entry["influence"],
            MEMORY_INFLUENCE,
            f"memory_exposure.consulted[{index}].influence",
        )
        _text(entry["why"], f"memory_exposure.consulted[{index}].why", 500)
    digests = item["source_packet_digests"]
    if not isinstance(digests, list) or not digests:
        raise OutcomeLearningContractError(
            "memory_exposure.source_packet_digests must be a non-empty list"
        )
    for index, digest in enumerate(digests):
        _sha256_digest(digest, f"memory_exposure.source_packet_digests[{index}]")
    return item


_EXPECTATION_REQUIRED = {
    "schema",
    "decision_ref",
    "operation_key",
    "decision_kind",
    "recorded_at",
    "sealed_hash",
    "context",
    "alternatives",
    "chosen_action",
    "assignment",
    "expectations",
    "guardrails",
    "causal_question",
    "known_confounders",
    "privacy_class",
    "assumptions",
    "assumption_resolutions",
    "memory_exposure",
}


def build_expectation(
    *,
    decision_ref: Mapping[str, Any],
    operation_key: str,
    decision_kind: str,
    recorded_at: str,
    context: Mapping[str, Any],
    alternatives: Sequence[Mapping[str, Any]],
    chosen_action: str,
    assignment: Mapping[str, Any],
    expectations: Sequence[Mapping[str, Any]],
    guardrails: Sequence[Mapping[str, Any]],
    causal_question: str,
    known_confounders: Sequence[str],
    assumptions: Sequence[Mapping[str, Any]],
    memory_exposure: Mapping[str, Any],
) -> dict[str, Any]:
    """Build and seal one ``mastermind.decision_expectation_receipt.v2`` document."""
    unsealed = {
        "schema": EXPECTATION_SCHEMA,
        "decision_ref": dict(decision_ref),
        "operation_key": _text(operation_key, "operation_key", 192),
        "decision_kind": _text(decision_kind, "decision_kind", 128),
        "recorded_at": _text(recorded_at, "recorded_at", 40),
        "context": dict(context),
        "alternatives": [dict(item) for item in alternatives],
        "chosen_action": _text(chosen_action, "chosen_action", 128),
        "assignment": dict(assignment),
        "expectations": [dict(item) for item in expectations],
        "guardrails": [dict(item) for item in guardrails],
        "causal_question": _text(causal_question, "causal_question", 500),
        "known_confounders": list(known_confounders),
        "privacy_class": PRIVACY_CLASS,
        "assumptions": [dict(item) for item in assumptions],
        "assumption_resolutions": [],
        "memory_exposure": dict(memory_exposure),
    }
    sealed = seal_document(unsealed, field="sealed_hash")
    validate_expectation(sealed)
    return sealed


def validate_expectation(doc: Mapping[str, Any]) -> Mapping[str, Any]:
    item = _closed_mapping(doc, required=_EXPECTATION_REQUIRED, where="expectation")
    if item["schema"] != EXPECTATION_SCHEMA:
        raise OutcomeLearningContractError("unsupported expectation schema")
    _validate_decision_ref(item["decision_ref"])
    _text(item["operation_key"], "operation_key", 192)
    _text(item["decision_kind"], "decision_kind", 128)
    _text(item["recorded_at"], "recorded_at", 40)
    _validate_context(item["context"])
    chosen_action = _text(item["chosen_action"], "chosen_action", 128)
    _validate_alternatives(item["alternatives"], chosen_action)
    _validate_assignment(item["assignment"])
    _validate_expectations(item["expectations"])
    _validate_guardrails(item["guardrails"])
    _text(item["causal_question"], "causal_question", 500)
    _unique_str_list(item["known_confounders"], "known_confounders", max_len=32)
    _validate_assumptions(item["assumptions"])
    if item["assumption_resolutions"] != []:
        raise OutcomeLearningContractError(
            "the sealed expectation receipt must carry assumption_resolutions == []"
        )
    _validate_memory_exposure(item["memory_exposure"])
    _require_public_safe(item, "expectation")
    _reject_forbidden_self_referential_keys(item, "expectation")
    verify_sealed(item, field="sealed_hash")
    return item


# --------------------------------------------------------------------------- canary request

_CANARY_REQUEST_REQUIRED = {
    "schema",
    "operation_key",
    "expectation_sealed_hash",
    "effect_class",
    "repository",
    "branch",
    "pr_selector",
    "canary_token",
    "apply_rule",
    "restore_rule",
    "max_effect_calls",
    "retry_policy",
    "ambiguity_policy",
    "expected_parent_head",
    "effect_owner_revalidation_required",
    "supervised",
    "execution_authority_granted",
    "recorded_at",
    "privacy_class",
}


def build_canary_request(
    *,
    operation_key: str,
    expectation_sealed_hash: str,
    repository: str,
    branch: str,
    expected_parent_head: str,
    recorded_at: str,
) -> dict[str, Any]:
    doc = {
        "schema": CANARY_REQUEST_SCHEMA,
        "operation_key": _text(operation_key, "operation_key", 192),
        "expectation_sealed_hash": _sha256_digest(
            expectation_sealed_hash, "expectation_sealed_hash"
        ),
        "effect_class": "GITHUB_PR_TITLE_APPEND_RESTORE",
        "repository": _text(repository, "repository", 200),
        "branch": _text(branch, "branch", 256),
        "pr_selector": {"method": "single_open_pr_for_branch"},
        "canary_token": CANARY_TOKEN,
        "apply_rule": "original_title_plus_single_space_token",
        "restore_rule": "byte_identical_original",
        "max_effect_calls": 2,
        "retry_policy": "NONE",
        "ambiguity_policy": "EFFECT_UNKNOWN_STOP",
        "expected_parent_head": _sha40(expected_parent_head, "expected_parent_head"),
        "effect_owner_revalidation_required": True,
        "supervised": True,
        "execution_authority_granted": False,
        "recorded_at": _text(recorded_at, "recorded_at", 40),
        "privacy_class": PRIVACY_CLASS,
    }
    validate_canary_request(doc)
    return doc


def validate_canary_request(doc: Mapping[str, Any]) -> Mapping[str, Any]:
    item = _closed_mapping(doc, required=_CANARY_REQUEST_REQUIRED, where="canary_request")
    if item["schema"] != CANARY_REQUEST_SCHEMA:
        raise OutcomeLearningContractError("unsupported canary request schema")
    _text(item["operation_key"], "operation_key", 192)
    _sha256_digest(item["expectation_sealed_hash"], "expectation_sealed_hash")
    if item["effect_class"] != "GITHUB_PR_TITLE_APPEND_RESTORE":
        raise OutcomeLearningContractError("effect_class is frozen for OL-V1")
    _text(item["repository"], "repository", 200)
    _text(item["branch"], "branch", 256)
    if item["pr_selector"] != {"method": "single_open_pr_for_branch"}:
        raise OutcomeLearningContractError("pr_selector is frozen for OL-V1")
    if item["canary_token"] != CANARY_TOKEN:
        raise OutcomeLearningContractError("canary_token must equal the frozen token")
    if item["apply_rule"] != "original_title_plus_single_space_token":
        raise OutcomeLearningContractError("apply_rule is frozen for OL-V1")
    if item["restore_rule"] != "byte_identical_original":
        raise OutcomeLearningContractError("restore_rule is frozen for OL-V1")
    if item["max_effect_calls"] != 2:
        raise OutcomeLearningContractError("max_effect_calls must be exactly 2")
    if item["retry_policy"] != "NONE":
        raise OutcomeLearningContractError("retry_policy is frozen to NONE")
    if item["ambiguity_policy"] != "EFFECT_UNKNOWN_STOP":
        raise OutcomeLearningContractError("ambiguity_policy is frozen for OL-V1")
    _sha40(item["expected_parent_head"], "expected_parent_head")
    _true(item["effect_owner_revalidation_required"], "effect_owner_revalidation_required")
    _true(item["supervised"], "supervised")
    _false(item["execution_authority_granted"], "execution_authority_granted")
    _text(item["recorded_at"], "recorded_at", 40)
    _require_public_safe(item, "canary_request")
    _reject_forbidden_self_referential_keys(item, "canary_request")
    return item


# --------------------------------------------------------------------------- preflight

_PREFLIGHT_REQUIRED = {
    "observed_at",
    "repository",
    "pr_number",
    "pr_url",
    "head_sha",
    "base_ref",
    "original_title_sha256",
    "original_title_length",
    "sealed_commit_sha",
    "expectation_blob_sha",
    "request_blob_sha",
    "expectation_content_sha256",
    "request_content_sha256",
    "head_equals_sealed_commit",
}


def validate_preflight(doc: Mapping[str, Any]) -> Mapping[str, Any]:
    item = _closed_mapping(doc, required=_PREFLIGHT_REQUIRED, where="preflight")
    _text(item["observed_at"], "preflight.observed_at", 40)
    _text(item["repository"], "preflight.repository", 200)
    _int(item["pr_number"], "preflight.pr_number", minimum=1)
    _text(item["pr_url"], "preflight.pr_url", 500)
    _sha40(item["head_sha"], "preflight.head_sha")
    _text(item["base_ref"], "preflight.base_ref", 200)
    _sha256_hex(item["original_title_sha256"], "preflight.original_title_sha256")
    _int(item["original_title_length"], "preflight.original_title_length", minimum=0)
    _sha40(item["sealed_commit_sha"], "preflight.sealed_commit_sha")
    _sha40(item["expectation_blob_sha"], "preflight.expectation_blob_sha")
    _sha40(item["request_blob_sha"], "preflight.request_blob_sha")
    _sha256_hex(item["expectation_content_sha256"], "preflight.expectation_content_sha256")
    _sha256_hex(item["request_content_sha256"], "preflight.request_content_sha256")
    _bool(item["head_equals_sealed_commit"], "preflight.head_equals_sealed_commit")
    return item


# --------------------------------------------------------------------------- outcome

_OUTCOME_REQUIRED = {
    "schema",
    "operation_key",
    "expectation_sealed_hash",
    "request_digest",
    "preflight",
    "effect_calls",
    "effect_state",
    "restoration",
    "recorded_at",
    "privacy_class",
}
_EFFECT_CALL_REQUIRED = {
    "seq",
    "kind",
    "requested_at",
    "method",
    "endpoint",
    "payload_title_sha256",
    "response_status",
    "readback",
}
_READBACK_REQUIRED = {"observed_at", "title_sha256", "title_length", "head_sha"}
_RESTORATION_REQUIRED = {
    "byte_identical",
    "prestate_title_sha256",
    "poststate_title_sha256",
    "head_unchanged",
}


def _validate_readback(value: Any, where: str) -> Mapping[str, Any]:
    item = _closed_mapping(value, required=_READBACK_REQUIRED, where=where)
    _text(item["observed_at"], f"{where}.observed_at", 40)
    _sha256_hex(item["title_sha256"], f"{where}.title_sha256")
    _int(item["title_length"], f"{where}.title_length", minimum=0)
    _sha40(item["head_sha"], f"{where}.head_sha")
    return item


def _response_status(value: Any, name: str) -> int | str:
    """int 100-599, OR the literal "UNOBSERVED" (no response was ever confirmed)."""
    if value == "UNOBSERVED":
        return value
    return _int(value, name, minimum=100, maximum=599)


def _validate_effect_calls(value: Any) -> list[Mapping[str, Any]]:
    """Structural note: the position-locked seq/kind check below (seq must equal its
    1-based position; kind must equal EFFECT_CALL_KINDS[index]) makes a duplicate seq
    or an out-of-order kind unreachable by construction — there is no separate
    "duplicate seq" branch to fall through to, and none is needed."""
    if not isinstance(value, list):
        raise OutcomeLearningContractError("effect_calls must be a list")
    if len(value) > 2:
        raise OutcomeLearningContractError("effect_calls may never exceed 2 entries")
    for index, raw in enumerate(value):
        item = _closed_mapping(raw, required=_EFFECT_CALL_REQUIRED, where=f"effect_calls[{index}]")
        seq = _int(item["seq"], f"effect_calls[{index}].seq", minimum=1, maximum=2)
        if seq != index + 1:
            raise OutcomeLearningContractError(
                f"effect_calls[{index}].seq must equal its 1-based position"
            )
        kind = _enum(item["kind"], EFFECT_CALL_KINDS, f"effect_calls[{index}].kind")
        expected_kind = EFFECT_CALL_KINDS[index] if index < 2 else None
        if kind != expected_kind:
            raise OutcomeLearningContractError(
                f"effect_calls[{index}].kind must be {expected_kind}"
            )
        _text(item["requested_at"], f"effect_calls[{index}].requested_at", 40)
        if item["method"] != "PATCH":
            raise OutcomeLearningContractError(f"effect_calls[{index}].method must be PATCH")
        _text(item["endpoint"], f"effect_calls[{index}].endpoint", 300)
        _sha256_hex(
            item["payload_title_sha256"], f"effect_calls[{index}].payload_title_sha256"
        )
        _response_status(item["response_status"], f"effect_calls[{index}].response_status")
        _validate_readback(item["readback"], f"effect_calls[{index}].readback")
    return value


def _validate_restoration(value: Any) -> Mapping[str, Any]:
    """``poststate_title_sha256`` is 64-hex when the post-effect title was actually
    observed (a direct readback or the single reconciliation GET), or the literal
    "UNOBSERVED" when neither ever confirmed it — an outcome must never assert a
    poststate it never actually saw. ``byte_identical`` is a DERIVED fact, never a free
    choice: True/False exactly when ``prestate == poststate`` and poststate is
    observed; None if and only if poststate is "UNOBSERVED" (identity is genuinely
    unknown, not merely unequal)."""
    item = _closed_mapping(value, required=_RESTORATION_REQUIRED, where="restoration")
    prestate = _sha256_hex(item["prestate_title_sha256"], "restoration.prestate_title_sha256")
    poststate_raw = item["poststate_title_sha256"]
    if poststate_raw == "UNOBSERVED":
        poststate: str | None = "UNOBSERVED"
    else:
        poststate = _sha256_hex(poststate_raw, "restoration.poststate_title_sha256")
    byte_identical = item["byte_identical"]
    if poststate == "UNOBSERVED":
        if byte_identical is not None:
            raise OutcomeLearningContractError(
                "restoration.byte_identical must be None when poststate_title_sha256 "
                "is UNOBSERVED"
            )
    else:
        expected = prestate == poststate
        if type(byte_identical) is not bool or byte_identical != expected:
            raise OutcomeLearningContractError(
                "restoration.byte_identical must equal (prestate == poststate) "
                "whenever poststate_title_sha256 is observed"
            )
    _bool(item["head_unchanged"], "restoration.head_unchanged")
    return item


def build_outcome(
    *,
    operation_key: str,
    expectation_sealed_hash: str,
    request: Mapping[str, Any],
    preflight: Mapping[str, Any],
    effect_calls: Sequence[Mapping[str, Any]],
    effect_state: str,
    restoration: Mapping[str, Any],
    recorded_at: str,
) -> dict[str, Any]:
    doc = {
        "schema": OUTCOME_SCHEMA,
        "operation_key": _text(operation_key, "operation_key", 192),
        "expectation_sealed_hash": _sha256_digest(
            expectation_sealed_hash, "expectation_sealed_hash"
        ),
        "request_digest": canonical_digest(request),
        "preflight": dict(preflight),
        "effect_calls": [dict(item) for item in effect_calls],
        "effect_state": _enum(effect_state, EFFECT_STATES, "effect_state"),
        "restoration": dict(restoration),
        "recorded_at": _text(recorded_at, "recorded_at", 40),
        "privacy_class": PRIVACY_CLASS,
    }
    validate_outcome(doc, expectation=None, request=request)
    return doc


def validate_outcome(
    doc: Mapping[str, Any],
    expectation: Mapping[str, Any] | None,
    request: Mapping[str, Any],
) -> Mapping[str, Any]:
    item = _closed_mapping(doc, required=_OUTCOME_REQUIRED, where="outcome")
    if item["schema"] != OUTCOME_SCHEMA:
        raise OutcomeLearningContractError("unsupported outcome schema")
    _text(item["operation_key"], "operation_key", 192)
    _sha256_digest(item["expectation_sealed_hash"], "expectation_sealed_hash")
    validate_canary_request(request)
    if item["request_digest"] != canonical_digest(request):
        raise OutcomeLearningContractError(
            "outcome.request_digest does not match the supplied canary request"
        )
    if expectation is not None:
        verify_sealed(expectation, field="sealed_hash")
        if item["expectation_sealed_hash"] != expectation["sealed_hash"]:
            raise OutcomeLearningContractError(
                "outcome.expectation_sealed_hash does not match the sealed expectation"
            )
        if request["expectation_sealed_hash"] != expectation["sealed_hash"]:
            raise OutcomeLearningContractError(
                "canary request does not bind to the sealed expectation"
            )
    preflight = validate_preflight(item["preflight"])
    effect_calls = _validate_effect_calls(item["effect_calls"])
    effect_state = _enum(item["effect_state"], EFFECT_STATES, "effect_state")
    restoration = _validate_restoration(item["restoration"])
    _text(item["recorded_at"], "recorded_at", 40)
    _require_public_safe(item, "outcome")

    if effect_state in {"NOT_ATTEMPTED", "INVALIDATED_BEFORE_EFFECT"} and effect_calls:
        raise OutcomeLearningContractError(
            f"effect_state {effect_state} requires empty effect_calls"
        )
    if len(effect_calls) > 2:
        raise OutcomeLearningContractError("more than 2 effect calls is never valid")

    if effect_state == "APPLIED_AND_RESTORED":
        if len(effect_calls) != 2:
            raise OutcomeLearningContractError(
                "APPLIED_AND_RESTORED requires exactly 2 effect_calls"
            )
        call1, call2 = effect_calls
        original_sha = preflight["original_title_sha256"]
        sealed_head = preflight["sealed_commit_sha"]
        if preflight["head_equals_sealed_commit"] is not True:
            raise OutcomeLearningContractError(
                "APPLIED_AND_RESTORED requires preflight.head_equals_sealed_commit == True"
            )
        if preflight["head_sha"] != sealed_head:
            raise OutcomeLearningContractError(
                "APPLIED_AND_RESTORED requires preflight.head_sha == sealed_commit_sha"
            )
        if call1["readback"]["title_sha256"] != call1["payload_title_sha256"]:
            raise OutcomeLearningContractError(
                "call1 readback title does not match the applied payload"
            )
        if call2["readback"]["title_sha256"] != original_sha:
            raise OutcomeLearningContractError(
                "call2 readback title does not match the original preflight title"
            )
        if restoration["poststate_title_sha256"] != original_sha:
            raise OutcomeLearningContractError(
                "restoration.poststate_title_sha256 must equal the original title hash"
            )
        if restoration["prestate_title_sha256"] != original_sha:
            raise OutcomeLearningContractError(
                "restoration.prestate_title_sha256 must equal the original title hash"
            )
        if restoration["byte_identical"] is not True:
            raise OutcomeLearningContractError(
                "APPLIED_AND_RESTORED requires restoration.byte_identical == True"
            )
        if restoration["head_unchanged"] is not True:
            raise OutcomeLearningContractError(
                "APPLIED_AND_RESTORED requires restoration.head_unchanged == True"
            )
        heads = {
            preflight["head_sha"],
            call1["readback"]["head_sha"],
            call2["readback"]["head_sha"],
        }
        if heads != {sealed_head}:
            raise OutcomeLearningContractError(
                "APPLIED_AND_RESTORED requires every head_sha to equal sealed_commit_sha"
            )
    elif effect_state != "EFFECT_UNKNOWN" and effect_calls:
        # NOT_ATTEMPTED / INVALIDATED_BEFORE_EFFECT already required empty above; any
        # other state carrying calls without matching the exact contract is invalid.
        raise OutcomeLearningContractError(
            f"effect_state {effect_state} may not carry effect_calls that do not satisfy "
            "the APPLIED_AND_RESTORED contract"
        )
    return item


# --------------------------------------------------------------------------- evaluation

_EVALUATION_REQUIRED = {
    "schema",
    "operation_key",
    "expectation_sealed_hash",
    "outcome_digest",
    "process_quality",
    "forecast",
    "realized_consequence",
    "assumption_resolutions",
    "confounding",
    "restoration_check",
    "causal_grade",
    "promotion",
    "recorded_at",
    "privacy_class",
}
_PROCESS_QUALITY_REQUIRED = {
    "sealed_before_effect",
    "single_apply_single_restore",
    "readback_after_each_call",
    "no_retry_used",
    "effect_owner_revalidated",
}
_FORECAST_ENTRY_REQUIRED = {
    "metric_id",
    "kind",
    "estimate",
    "lower",
    "upper",
    "realized",
    "within_interval",
    "brier_score",
}
_BRIER_TOLERANCE = 1e-9
_ASSUMPTION_RESOLUTION_REQUIRED = {"assumption_id", "resolution", "evidence_refs"}
_CONFOUNDING_REQUIRED = {"known_confounders_assessed", "additional_observed"}
_CONFOUNDER_ASSESSED_REQUIRED = {"confounder", "observed", "note"}


def _validate_process_quality(value: Any) -> Mapping[str, Any]:
    item = _closed_mapping(value, required=_PROCESS_QUALITY_REQUIRED, where="process_quality")
    for field in _PROCESS_QUALITY_REQUIRED:
        _bool(item[field], f"process_quality.{field}")
    return item


def _validate_forecast(value: Any, expectation: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """Each entry is bound VERBATIM to its matching sealed-expectation metric
    (kind/estimate/lower/upper compared field-by-field, not merely referenced by
    metric_id) — a forecast can never silently drift from what was actually sealed.

    Scoring is kind-specific and mutually exclusive: a probability-kind metric is
    scored with ``brier_score = (estimate - realized) ** 2`` and NEVER carries
    ``within_interval`` (always None) — an interval-hit/miss framing is incoherent for
    a point probability forecast. A count/duration_seconds metric keeps the interval
    framing (``within_interval``) and never carries a ``brier_score`` (always None).
    Both are None together only when ``realized`` is None (permitted solely for a
    delayed-horizon metric)."""
    if not isinstance(value, list) or not value:
        raise OutcomeLearningContractError("forecast must be a non-empty list")
    metrics_by_id = {item["metric_id"]: item for item in expectation["expectations"]}
    metric_ids = set(metrics_by_id)
    seen: set[str] = set()
    for index, raw in enumerate(value):
        item = _closed_mapping(raw, required=_FORECAST_ENTRY_REQUIRED, where=f"forecast[{index}]")
        metric_id = _text(item["metric_id"], f"forecast[{index}].metric_id", 128)
        if metric_id not in metric_ids:
            raise OutcomeLearningContractError(
                f"forecast[{index}].metric_id does not reference an expectation metric"
            )
        seen.add(metric_id)
        metric = metrics_by_id[metric_id]
        kind = _enum(item["kind"], EXPECTATION_KINDS, f"forecast[{index}].kind")
        lower = _number(item["lower"], f"forecast[{index}].lower")
        estimate = _number(item["estimate"], f"forecast[{index}].estimate")
        upper = _number(item["upper"], f"forecast[{index}].upper")
        if not lower <= estimate <= upper:
            raise OutcomeLearningContractError(f"forecast[{index}] bounds are inconsistent")
        if (
            kind != metric["kind"]
            or estimate != _number(metric["estimate"], "expectation.estimate")
            or lower != _number(metric["lower"], "expectation.lower")
            or upper != _number(metric["upper"], "expectation.upper")
        ):
            raise OutcomeLearningContractError(
                f"forecast[{index}] kind/estimate/lower/upper does not match the "
                "sealed expectation's metric"
            )
        horizon = metric["horizon"]
        realized = item["realized"]
        within = item["within_interval"]
        brier = item["brier_score"]
        if realized is None:
            if horizon != "delayed":
                raise OutcomeLearningContractError(
                    f"forecast[{index}].realized may only be None for a delayed horizon"
                )
            if within is not None:
                raise OutcomeLearningContractError(
                    f"forecast[{index}].within_interval must be None when realized is None"
                )
            if brier is not None:
                raise OutcomeLearningContractError(
                    f"forecast[{index}].brier_score must be None when realized is None"
                )
            continue
        realized_number = _number(realized, f"forecast[{index}].realized")
        if kind == "probability":
            if realized_number not in (0.0, 1.0):
                raise OutcomeLearningContractError(
                    f"forecast[{index}].realized must be 0.0 or 1.0 for a probability metric"
                )
            if within is not None:
                raise OutcomeLearningContractError(
                    f"forecast[{index}].within_interval must be None for a "
                    "probability-kind metric (see brier_score)"
                )
            brier_number = _number(brier, f"forecast[{index}].brier_score")
            expected_brier = (estimate - realized_number) ** 2
            if abs(brier_number - expected_brier) > _BRIER_TOLERANCE:
                raise OutcomeLearningContractError(
                    f"forecast[{index}].brier_score must equal (estimate - realized) ** 2"
                )
        else:
            if brier is not None:
                raise OutcomeLearningContractError(
                    f"forecast[{index}].brier_score only applies to a probability-kind "
                    "metric"
                )
            expected_within = lower <= realized_number <= upper
            if not isinstance(within, bool) or within != expected_within:
                raise OutcomeLearningContractError(
                    f"forecast[{index}].within_interval does not match lower<=realized<=upper"
                )
    if seen != metric_ids:
        raise OutcomeLearningContractError(
            "forecast must contain exactly one entry per expectation metric"
        )
    return value


def _validate_assumption_resolutions(
    value: Any, expectation: Mapping[str, Any]
) -> list[Mapping[str, Any]]:
    if not isinstance(value, list) or not value:
        raise OutcomeLearningContractError("assumption_resolutions must be a non-empty list")
    expected_ids = {item["assumption_id"] for item in expectation["assumptions"]}
    seen: set[str] = set()
    for index, raw in enumerate(value):
        item = _closed_mapping(
            raw, required=_ASSUMPTION_RESOLUTION_REQUIRED, where=f"assumption_resolutions[{index}]"
        )
        assumption_id = _text(
            item["assumption_id"], f"assumption_resolutions[{index}].assumption_id", 64
        )
        if assumption_id in seen:
            raise OutcomeLearningContractError("duplicate assumption_resolutions[*].assumption_id")
        seen.add(assumption_id)
        resolution = item["resolution"]
        if resolution not in RESOLUTIONS:
            raise OutcomeLearningContractError(
                f"assumption_resolutions[{index}].resolution is outside the closed vocabulary"
            )
        _str_list(
            item["evidence_refs"], f"assumption_resolutions[{index}].evidence_refs", max_len=16
        )
    if seen != expected_ids:
        raise OutcomeLearningContractError(
            "assumption_resolutions must cover exactly the expectation's assumption_ids"
        )
    return value


def _validate_confounding(value: Any, expectation: Mapping[str, Any]) -> Mapping[str, Any]:
    item = _closed_mapping(value, required=_CONFOUNDING_REQUIRED, where="confounding")
    assessed = item["known_confounders_assessed"]
    if not isinstance(assessed, list):
        raise OutcomeLearningContractError("confounding.known_confounders_assessed must be a list")
    expected = set(expectation["known_confounders"])
    seen: set[str] = set()
    for index, raw in enumerate(assessed):
        entry = _closed_mapping(
            raw,
            required=_CONFOUNDER_ASSESSED_REQUIRED,
            where=f"confounding.known_confounders_assessed[{index}]",
        )
        confounder = _text(
            entry["confounder"],
            f"confounding.known_confounders_assessed[{index}].confounder",
            300,
        )
        seen.add(confounder)
        _bool(
            entry["observed"], f"confounding.known_confounders_assessed[{index}].observed"
        )
        _text(entry["note"], f"confounding.known_confounders_assessed[{index}].note", 500)
    if seen != expected:
        raise OutcomeLearningContractError(
            "confounding.known_confounders_assessed must cover exactly the expectation's "
            "known_confounders"
        )
    _str_list(item["additional_observed"], "confounding.additional_observed", max_len=16)
    return item


def validate_evaluation(
    doc: Mapping[str, Any],
    expectation: Mapping[str, Any],
    outcome: Mapping[str, Any],
) -> Mapping[str, Any]:
    item = _closed_mapping(doc, required=_EVALUATION_REQUIRED, where="evaluation")
    if item["schema"] != EVALUATION_SCHEMA:
        raise OutcomeLearningContractError("unsupported evaluation schema")
    validate_expectation(expectation)
    if item["expectation_sealed_hash"] != expectation["sealed_hash"]:
        raise OutcomeLearningContractError(
            "evaluation.expectation_sealed_hash does not match the sealed expectation"
        )
    if item["outcome_digest"] != canonical_digest(outcome):
        raise OutcomeLearningContractError(
            "evaluation.outcome_digest does not match the supplied outcome"
        )
    _text(item["operation_key"], "operation_key", 192)
    _validate_process_quality(item["process_quality"])
    _validate_forecast(item["forecast"], expectation)
    if item["realized_consequence"] not in EFFECT_STATES:
        raise OutcomeLearningContractError(
            "realized_consequence must be a closed effect state"
        )
    if item["realized_consequence"] != outcome["effect_state"]:
        raise OutcomeLearningContractError(
            "realized_consequence must equal the outcome's effect_state"
        )
    _validate_assumption_resolutions(item["assumption_resolutions"], expectation)
    _validate_confounding(item["confounding"], expectation)
    restoration_check = _closed_mapping(
        item["restoration_check"], required=_RESTORATION_REQUIRED, where="restoration_check"
    )
    if dict(restoration_check) != dict(outcome["restoration"]):
        raise OutcomeLearningContractError(
            "restoration_check must be a verbatim copy of outcome.restoration"
        )
    if item["causal_grade"] != "DESCRIPTIVE_ONLY":
        raise OutcomeLearningContractError("causal_grade must be DESCRIPTIVE_ONLY")
    if item["promotion"] != "NONE":
        raise OutcomeLearningContractError("evaluation promotion must be NONE")
    _text(item["recorded_at"], "recorded_at", 40)
    _require_public_safe(item, "evaluation")
    return item


# --------------------------------------------------------------------------- self-model

_SELF_MODEL_REQUIRED = {
    "schema",
    "operation_key",
    "evaluation_digest",
    "sample_size",
    "sample_state",
    "promotion",
    "authority",
    "universal_score",
    "cohort",
    "observations",
    "memory_law",
    "recorded_at",
    "privacy_class",
}
_COHORT_REQUIRED = {"decision_class", "domain", "ambiguity", "blast_radius"}
_OBSERVATION_REQUIRED = {"observation_id", "statement", "basis_refs"}
_MEMORY_LAW_REQUIRED = {
    "remembered_action_is_not_authorized_action",
    "remembered_success_is_not_current_procedure",
    "remembered_tool_sequence_is_not_replayable_effect",
}


def validate_self_model(
    doc: Mapping[str, Any], evaluation: Mapping[str, Any] | None = None
) -> Mapping[str, Any]:
    item = _closed_mapping(doc, required=_SELF_MODEL_REQUIRED, where="self_model")
    if item["schema"] != SELF_MODEL_SCHEMA:
        raise OutcomeLearningContractError("unsupported self_model schema")
    if evaluation is not None and item["evaluation_digest"] != canonical_digest(evaluation):
        raise OutcomeLearningContractError(
            "self_model.evaluation_digest does not match the supplied evaluation"
        )
    else:
        _sha256_digest(item["evaluation_digest"], "evaluation_digest")
    _text(item["operation_key"], "operation_key", 192)
    if item["sample_size"] != 1:
        raise OutcomeLearningContractError("self_model.sample_size must be exactly 1")
    if item["sample_state"] != "INSUFFICIENT_SAMPLE":
        raise OutcomeLearningContractError(
            "self_model.sample_state must be INSUFFICIENT_SAMPLE"
        )
    if item["promotion"] != "NONE":
        raise OutcomeLearningContractError("self_model.promotion must be NONE")
    if item["authority"] != "NONE":
        raise OutcomeLearningContractError("self_model.authority must be NONE")
    if "universal_score" not in item or item["universal_score"] is not None:
        raise OutcomeLearningContractError("self_model.universal_score must be present and None")
    cohort = _closed_mapping(item["cohort"], required=_COHORT_REQUIRED, where="cohort")
    for field in _COHORT_REQUIRED:
        _text(cohort[field], f"cohort.{field}", 200)
    observations = item["observations"]
    if not isinstance(observations, list) or not observations:
        raise OutcomeLearningContractError("observations must be a non-empty list")
    seen: set[str] = set()
    for index, raw in enumerate(observations):
        entry = _closed_mapping(
            raw, required=_OBSERVATION_REQUIRED, where=f"observations[{index}]"
        )
        observation_id = _text(
            entry["observation_id"], f"observations[{index}].observation_id", 64
        )
        if observation_id in seen:
            raise OutcomeLearningContractError("duplicate observations[*].observation_id")
        seen.add(observation_id)
        _text(entry["statement"], f"observations[{index}].statement", 500)
        _str_list(entry["basis_refs"], f"observations[{index}].basis_refs", min_len=1, max_len=16)
    memory_law = _closed_mapping(
        item["memory_law"], required=_MEMORY_LAW_REQUIRED, where="memory_law"
    )
    for field in _MEMORY_LAW_REQUIRED:
        _true(memory_law[field], f"memory_law.{field}")
    _text(item["recorded_at"], "recorded_at", 40)
    _require_public_safe(item, "self_model")
    return item


# --------------------------------------------------------------------------- agentos projection

_PROJECTION_REQUIRED = {
    "schema",
    "operation_key",
    "evaluation_digest",
    "automatic_writes",
    "grants_authority",
    "candidates",
    "recorded_at",
    "privacy_class",
}
_CANDIDATE_REQUIRED = {
    "kind",
    "target_repository",
    "key_hint",
    "summary",
    "falsifier",
    "so_what",
    "payload_digest",
    "status",
}


def _candidate_payload(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "kind": item["kind"],
        "target_repository": item["target_repository"],
        "key_hint": item["key_hint"],
        "summary": item["summary"],
        "falsifier": item["falsifier"],
        "so_what": item["so_what"],
    }


def validate_agentos_projection(
    doc: Mapping[str, Any], evaluation: Mapping[str, Any] | None = None
) -> Mapping[str, Any]:
    item = _closed_mapping(doc, required=_PROJECTION_REQUIRED, where="agentos_projection")
    if item["schema"] != AGENTOS_PROJECTION_SCHEMA:
        raise OutcomeLearningContractError("unsupported agentos_projection schema")
    if evaluation is not None and item["evaluation_digest"] != canonical_digest(evaluation):
        raise OutcomeLearningContractError(
            "agentos_projection.evaluation_digest does not match the supplied evaluation"
        )
    else:
        _sha256_digest(item["evaluation_digest"], "evaluation_digest")
    _text(item["operation_key"], "operation_key", 192)
    _false(item["automatic_writes"], "automatic_writes")
    _false(item["grants_authority"], "grants_authority")
    candidates = item["candidates"]
    if not isinstance(candidates, list) or not candidates:
        raise OutcomeLearningContractError("candidates must be a non-empty list")
    kinds_seen: list[str] = []
    for index, raw in enumerate(candidates):
        entry = _closed_mapping(
            raw, required=_CANDIDATE_REQUIRED, where=f"candidates[{index}]"
        )
        kind = _enum(entry["kind"], PROJECTION_CANDIDATE_KINDS, f"candidates[{index}].kind")
        kinds_seen.append(kind)
        _text(entry["target_repository"], f"candidates[{index}].target_repository", 200)
        _text(entry["key_hint"], f"candidates[{index}].key_hint", 128)
        _text(entry["summary"], f"candidates[{index}].summary", 800)
        _text(entry["falsifier"], f"candidates[{index}].falsifier", 500)
        _text(entry["so_what"], f"candidates[{index}].so_what", 500)
        if entry["payload_digest"] != canonical_digest(_candidate_payload(entry)):
            raise OutcomeLearningContractError(
                f"candidates[{index}].payload_digest does not match its own content"
            )
        if entry["status"] != "CANDIDATE_ONLY":
            raise OutcomeLearningContractError(
                f"candidates[{index}].status must be CANDIDATE_ONLY"
            )
    if "DSC_CANDIDATE" not in kinds_seen or "WS_UPDATE_CANDIDATE" not in kinds_seen:
        raise OutcomeLearningContractError(
            "candidates must include at least one DSC_CANDIDATE and one WS_UPDATE_CANDIDATE"
        )
    _text(item["recorded_at"], "recorded_at", 40)
    _require_public_safe(item, "agentos_projection")
    return item


__all__ = [
    "AGENTOS_PROJECTION_SCHEMA",
    "ASSUMPTION_ROLES",
    "CANARY_REQUEST_SCHEMA",
    "CANARY_TOKEN",
    "EFFECT_STATES",
    "EVALUATION_SCHEMA",
    "EXPECTATION_SCHEMA",
    "MEMORY_INFLUENCE",
    "OUTCOME_SCHEMA",
    "PRIVACY_CLASS",
    "PROJECTION_CANDIDATE_KINDS",
    "RESOLUTIONS",
    "SELF_MODEL_SCHEMA",
    "OutcomeLearningContractError",
    "build_canary_request",
    "build_expectation",
    "build_outcome",
    "canonical_digest",
    "scan_public_safe_text",
    "seal_document",
    "validate_agentos_projection",
    "validate_canary_request",
    "validate_evaluation",
    "validate_expectation",
    "validate_outcome",
    "validate_preflight",
    "validate_self_model",
    "verify_sealed",
]
