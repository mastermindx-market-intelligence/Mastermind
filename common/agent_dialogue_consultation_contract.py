"""Versioned, non-command peer-consultation dialogue contract."""
from __future__ import annotations

import copy
import hashlib
import json
import re
from collections.abc import Mapping
from enum import Enum
from types import MappingProxyType
from typing import Any

from common.agent_dialogue_contract import (
    DialogueContractError,
    MAX_EVIDENCE_REFS,
    MAX_FRAME_BYTES,
    validate_evidence_ref,
)
from common.agent_dialogue_contract_v2 import (
    _MESSAGE_KEY_RE,
    _SHA64_RE,
    _UTC_RE,
    _reject_secret_shaped_leaves,
    validate_actor_ref as validate_actor_ref_v2,
)

CONSULTATION_SCHEMA = "mastermind.agent_dialogue_consultation.v1"
CONSULTATION_V2_SCHEMA = "mastermind.agent_dialogue_consultation.v2"
GROK_CONSULTATION_SCHEMA = "mastermind.agent_dialogue_consultation.v3"
CONSULTATION_PACKET_DISCRIMINATOR = (
    "MMX/AGENT_DIALOGUE_CONSULTATION_PACKET_V1"
)
CONSULTATION_PACKET_MAX_BYTES = MAX_FRAME_BYTES
CONSULTATION_PURPOSES = frozenset({"QUESTION", "ANSWER", "NOTICE", "CORRECTION"})
CONSULTATION_KEYS = frozenset(
    {
        "schema",
        "message_key",
        "consultation_id",
        "purpose",
        "requester_actor_ref",
        "recipient_actor_ref",
        "recipient_peer_ref",
        "recipient_binding",
        "correlation",
        "question",
        "answer",
        "evidence_refs",
        "artifact_revisions",
        "valid_until",
        "deadline_ms",
        "response_budget",
        "supersedes_message_key",
        "receipts",
        "fingerprint",
    }
)
CONSULTATION_V2_KEYS = CONSULTATION_KEYS | {"question_message_key"}
CONSULTATION_SCHEMA_REASONING_SURFACES = MappingProxyType(
    {
        CONSULTATION_SCHEMA: frozenset({"codex", "claude"}),
        CONSULTATION_V2_SCHEMA: frozenset({"codex", "claude"}),
        GROK_CONSULTATION_SCHEMA: frozenset({"grok-bot"}),
    }
)
_PRODUCER_SCHEMA_BY_REASONING_SURFACE = MappingProxyType(
    {
        "codex": CONSULTATION_SCHEMA,
        "claude": CONSULTATION_SCHEMA,
        "grok-bot": GROK_CONSULTATION_SCHEMA,
    }
)
RECIPIENT_BINDING_KEYS = frozenset(
    {"binding_id", "binding_generation", "reasoning_surface"}
)
CORRELATION_KEYS = frozenset(
    {
        "parent_fingerprint",
        "request_message_key",
        "consultation_id",
        "requester_actor_digest",
        "recipient_actor_digest",
    }
)
ANSWER_KEYS = frozenset({"text", "evidence_refs"})
ARTIFACT_REVISION_KEYS = frozenset(
    {"repository", "path", "commit", "content_sha256"}
)
RESPONSE_BUDGET_KEYS = frozenset(
    {
        "max_answers",
        "max_evidence_reads",
        "max_forward_hops",
        "max_payload_bytes",
    }
)
RESPONSE_BUDGET_MAXIMA = {
    "max_answers": 1,
    "max_evidence_reads": 4,
    "max_forward_hops": 0,
    "max_payload_bytes": 32768,
}
RECEIPT_KEYS = frozenset(
    {
        "accepted_for_processing",
        "recorded_on_carrier",
        "native_input_accepted",
        "consumed_in_recipient_turn",
        "answer_available",
        "consumed_by_requester",
        "work_accepted",
    }
)
RECEIPT_KEYS_BY_INDEX = tuple(sorted(RECEIPT_KEYS))
_PEER_REF_RE = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._:-]{7,127}\Z")
_CONSULTATION_ID_RE = re.compile(r"\Aconsult-[0-9a-f]{32}\Z")
# Mirrors runtime_binding_id_for in control_plane.operator_harness_contract:
# "bind-" plus a 40-hex SHA-256 prefix.  Kept literal so common/ remains free
# of control_plane imports; a producer-composition test pins the shapes equal.
_BINDING_ID_RE = re.compile(r"\Abind-[0-9a-f]{40}\Z")
_REPOSITORY_RE = re.compile(r"\A[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")
_PATH_RE = re.compile(r"\A[A-Za-z0-9_][A-Za-z0-9_./-]{0,254}\Z")
_COMMIT_RE = re.compile(r"\A[0-9a-f]{40}\Z")
_FORBIDDEN_NAME_RE = re.compile(
    r"(?i)^(provider|account|host|session_id|native_session_id|channel|channel_id|"
    r"thread|thread_ts|runtime_binding|binding_id|binding_generation|job_id|"
    r"attempt_id|worker_id|operation_key|session_ref|work_ref|commission_ref|"
    r"reply_to_message_key|token|secret|credential|password|api[_-]?key)$"
)


class DuplicateClassification(str, Enum):
    IDEMPOTENT = "IDEMPOTENT"
    CONFLICT = "CONFLICT"


def canonical_consultation_json(value: Mapping[str, Any]) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError):
        raise DialogueContractError("FRAME_INVALID") from None


def consultation_semantic_fingerprint(value: Mapping[str, Any]) -> str:
    semantic = {
        key: item
        for key, item in value.items()
        if key not in {"fingerprint", "receipts"}
    }
    receipts = value.get("receipts")
    if isinstance(receipts, Mapping):
        semantic["receipts"] = {
            key: (
                {
                    nested_key: nested_value
                    for nested_key, nested_value in receipt.items()
                    if nested_key != "observed_at"
                }
                if isinstance(receipt, Mapping)
                else receipt
            )
            for key, receipt in receipts.items()
        }
    return hashlib.sha256(
        canonical_consultation_json(semantic).encode("utf-8")
    ).hexdigest()


def _exact_keys(value: Any, keys: frozenset[str]) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != keys:
        raise DialogueContractError("MESSAGE_INVALID")
    return copy.deepcopy(dict(value))


def _schema_keys(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise DialogueContractError("MESSAGE_INVALID")
    schema = value.get("schema")
    keys = (
        CONSULTATION_V2_KEYS
        if schema == CONSULTATION_V2_SCHEMA
        else CONSULTATION_KEYS
    )
    return _exact_keys(value, keys)


def consultation_schema_for_reasoning_surface(reasoning_surface: Any) -> str:
    if not isinstance(reasoning_surface, str):
        raise DialogueContractError("MESSAGE_INVALID")
    schema = _PRODUCER_SCHEMA_BY_REASONING_SURFACE.get(reasoning_surface)
    if schema is None:
        raise DialogueContractError("MESSAGE_INVALID")
    return schema


def _require_string(
    value: Any,
    *,
    max_chars: int,
    min_chars: int = 1,
    pattern: Any | None = None,
) -> str:
    if not isinstance(value, str) or not min_chars <= len(value) <= max_chars:
        raise DialogueContractError("MESSAGE_INVALID")
    if pattern is not None and pattern.fullmatch(value) is None:
        raise DialogueContractError("MESSAGE_INVALID")
    if value.strip() != value or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise DialogueContractError("MESSAGE_INVALID")
    return value


def _reject_forbidden_names(value: Any) -> None:
    if isinstance(value, Mapping):
        if set(value) == RECIPIENT_BINDING_KEYS:
            return
        for key, nested in value.items():
            if key in {"requester_actor_ref", "recipient_actor_ref"}:
                continue
            if isinstance(key, str) and _FORBIDDEN_NAME_RE.fullmatch(key):
                raise DialogueContractError("MESSAGE_INVALID")
            _reject_forbidden_names(nested)
    elif isinstance(value, (list, tuple)):
        for nested in value:
            _reject_forbidden_names(nested)


def _validated_actor(value: Any) -> dict[str, Any]:
    actor = validate_actor_ref_v2(copy.deepcopy(value))
    if actor["kind"] != "worker_attempt":
        raise DialogueContractError("MESSAGE_INVALID")
    return actor


def _validated_actor_digest(value: str) -> str:
    if not isinstance(value, str) or _SHA64_RE.fullmatch(value) is None:
        raise DialogueContractError("MESSAGE_INVALID")
    return value


def _validated_receipt(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping) or set(value) != {
        "evidence_ref",
        "observed_at",
    }:
        raise DialogueContractError("MESSAGE_INVALID")
    result = {
        "evidence_ref": validate_evidence_ref(value["evidence_ref"]),
        "observed_at": value["observed_at"],
    }
    if not isinstance(result["observed_at"], str) or _UTC_RE.fullmatch(result["observed_at"]) is None:
        raise DialogueContractError("MESSAGE_INVALID")
    return result


def validate_consultation(value: Any) -> dict[str, Any]:
    _reject_secret_shaped_leaves(value, code="MESSAGE_INVALID")
    _reject_forbidden_names(value)
    item = _schema_keys(value)
    schema = item["schema"]
    if schema == CONSULTATION_V2_SCHEMA:
        if item["purpose"] not in {"ANSWER", "CORRECTION"}:
            raise DialogueContractError("MESSAGE_INVALID")
        question_key = item["question_message_key"]
        if not isinstance(question_key, str) or _MESSAGE_KEY_RE.fullmatch(question_key) is None:
            raise DialogueContractError("MESSAGE_INVALID")
        if item["message_key"] == question_key:
            raise DialogueContractError("MESSAGE_INVALID")
    elif schema == GROK_CONSULTATION_SCHEMA:
        if item["purpose"] != "QUESTION":
            raise DialogueContractError("MESSAGE_INVALID")
    elif schema != CONSULTATION_SCHEMA:
        raise DialogueContractError("MESSAGE_INVALID")
    if not isinstance(item["message_key"], str) or _MESSAGE_KEY_RE.fullmatch(item["message_key"]) is None:
        raise DialogueContractError("MESSAGE_INVALID")
    if not isinstance(item["consultation_id"], str) or _CONSULTATION_ID_RE.fullmatch(item["consultation_id"]) is None:
        raise DialogueContractError("MESSAGE_INVALID")
    if item["purpose"] not in CONSULTATION_PURPOSES:
        raise DialogueContractError("MESSAGE_INVALID")

    requester = _validated_actor(item["requester_actor_ref"])
    recipient = _validated_actor(item["recipient_actor_ref"])
    if requester == recipient:
        raise DialogueContractError("MESSAGE_INVALID")
    if not isinstance(item["recipient_peer_ref"], str) or _PEER_REF_RE.fullmatch(item["recipient_peer_ref"]) is None:
        raise DialogueContractError("MESSAGE_INVALID")

    binding_raw = _exact_keys(item["recipient_binding"], RECIPIENT_BINDING_KEYS)
    if not isinstance(binding_raw["binding_id"], str) or _BINDING_ID_RE.fullmatch(binding_raw["binding_id"]) is None:
        raise DialogueContractError("MESSAGE_INVALID")
    if type(binding_raw["binding_generation"]) is not int or binding_raw["binding_generation"] < 1:
        raise DialogueContractError("MESSAGE_INVALID")
    reasoning_surface = binding_raw["reasoning_surface"]
    allowed_surfaces = CONSULTATION_SCHEMA_REASONING_SURFACES.get(schema)
    if (
        not isinstance(reasoning_surface, str)
        or allowed_surfaces is None
        or reasoning_surface not in allowed_surfaces
    ):
        raise DialogueContractError("MESSAGE_INVALID")
    item["recipient_binding"] = binding_raw

    correlation = _exact_keys(item["correlation"], CORRELATION_KEYS)
    for key in ("parent_fingerprint", "requester_actor_digest", "recipient_actor_digest"):
        correlation[key] = _validated_actor_digest(correlation[key])
    for key in ("request_message_key", "consultation_id"):
        if not isinstance(correlation[key], str):
            raise DialogueContractError("MESSAGE_INVALID")
    if (
        schema in {CONSULTATION_SCHEMA, GROK_CONSULTATION_SCHEMA}
        and correlation["request_message_key"] != item["message_key"]
    ):
        raise DialogueContractError("MESSAGE_INVALID")
    if schema == CONSULTATION_V2_SCHEMA:
        if item["question_message_key"] != correlation["request_message_key"]:
            raise DialogueContractError("MESSAGE_INVALID")
    if correlation["consultation_id"] != item["consultation_id"]:
        raise DialogueContractError("MESSAGE_INVALID")
    item["correlation"] = correlation

    question = item["question"]
    answer = item["answer"]
    if question is not None:
        question = _require_string(question, max_chars=16000)
    if answer is not None:
        answer_raw = _exact_keys(answer, ANSWER_KEYS)
        answer = {
            "text": _require_string(answer_raw["text"], max_chars=16000),
            "evidence_refs": _validated_evidence_refs(answer_raw["evidence_refs"]),
        }
    if (question is None) == (answer is None):
        raise DialogueContractError("MESSAGE_INVALID")
    if item["purpose"] == "QUESTION" and question is None:
        raise DialogueContractError("MESSAGE_INVALID")
    if item["purpose"] in {"ANSWER", "CORRECTION"} and answer is None:
        raise DialogueContractError("MESSAGE_INVALID")
    item["question"] = question
    item["answer"] = answer

    item["evidence_refs"] = _validated_evidence_refs(item["evidence_refs"])
    item["artifact_revisions"] = _validated_artifact_revisions(item["artifact_revisions"])
    if not isinstance(item["valid_until"], str) or _UTC_RE.fullmatch(item["valid_until"]) is None:
        raise DialogueContractError("MESSAGE_INVALID")
    if type(item["deadline_ms"]) is not int or not 1 <= item["deadline_ms"] <= 604800000:
        raise DialogueContractError("MESSAGE_INVALID")
    item["response_budget"] = _validated_budget(item["response_budget"])

    supersedes = item["supersedes_message_key"]
    if supersedes is not None and (
        not isinstance(supersedes, str) or _MESSAGE_KEY_RE.fullmatch(supersedes) is None
    ):
        raise DialogueContractError("MESSAGE_INVALID")
    if (item["purpose"] == "CORRECTION") != (supersedes is not None):
        raise DialogueContractError("MESSAGE_INVALID")
    if (
        item["schema"] == CONSULTATION_V2_SCHEMA
        and item["purpose"] == "CORRECTION"
        and supersedes in {
            item["message_key"],
            item["question_message_key"],
        }
    ):
        raise DialogueContractError("MESSAGE_INVALID")
    item["supersedes_message_key"] = supersedes

    receipts = _exact_keys(item["receipts"], RECEIPT_KEYS)
    item["receipts"] = {
        key: _validated_receipt(receipt) for key, receipt in receipts.items()
    }
    fingerprint = item["fingerprint"]
    if fingerprint not in {"", None} and (
        not isinstance(fingerprint, str) or _SHA64_RE.fullmatch(fingerprint) is None
    ):
        raise DialogueContractError("MESSAGE_INVALID")
    expected = consultation_semantic_fingerprint(item)
    if fingerprint not in {"", None} and fingerprint != expected:
        raise DialogueContractError("MESSAGE_INVALID")
    item["fingerprint"] = fingerprint if fingerprint else ""
    return item


def _validated_evidence_refs(value: Any) -> list[str]:
    if not isinstance(value, list) or len(value) > MAX_EVIDENCE_REFS:
        raise DialogueContractError("MESSAGE_INVALID")
    refs = [validate_evidence_ref(item) for item in value]
    if len(refs) != len(set(refs)):
        raise DialogueContractError("MESSAGE_INVALID")
    return refs


def _validated_artifact_revisions(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list) or not 1 <= len(value) <= 8:
        raise DialogueContractError("MESSAGE_INVALID")
    result = []
    for revision_raw in value:
        revision = _exact_keys(revision_raw, ARTIFACT_REVISION_KEYS)
        revision = {
            "repository": _require_string(revision["repository"], max_chars=200, pattern=_REPOSITORY_RE),
            "path": _require_string(revision["path"], max_chars=255, pattern=_PATH_RE),
            "commit": _require_string(revision["commit"], max_chars=40, pattern=_COMMIT_RE),
            "content_sha256": _require_string(revision["content_sha256"], max_chars=64, pattern=_SHA64_RE),
        }
        result.append(revision)
    if len({canonical_consultation_json(revision) for revision in result}) != len(result):
        raise DialogueContractError("MESSAGE_INVALID")
    return result


def _validated_budget(value: Any) -> dict[str, int]:
    budget = _exact_keys(value, RESPONSE_BUDGET_KEYS)
    for key, maximum in RESPONSE_BUDGET_MAXIMA.items():
        if type(budget[key]) is not int or not 0 <= budget[key] <= maximum:
            raise DialogueContractError("MESSAGE_INVALID")
        if key in {"max_evidence_reads", "max_payload_bytes"}:
            budget[key] = min(budget[key], maximum)
    if budget["max_answers"] != 1 or budget["max_forward_hops"] != 0:
        raise DialogueContractError("MESSAGE_INVALID")
    return budget


def build_consultation(value: Any) -> dict[str, Any]:
    item = validate_consultation(value)
    item["fingerprint"] = consultation_semantic_fingerprint(item)
    return item


def _strict_packet_loads(raw: str) -> dict[str, Any]:
    def reject_constant(_value: str) -> Any:
        raise ValueError("non-finite JSON is not canonical")

    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON object key")
            result[key] = value
        return result

    try:
        value = json.loads(
            raw,
            parse_constant=reject_constant,
            object_pairs_hook=unique_object,
        )
    except (TypeError, ValueError, json.JSONDecodeError):
        raise DialogueContractError("FRAME_INVALID") from None
    if not isinstance(value, dict):
        raise DialogueContractError("FRAME_INVALID")
    return value


def _wire_packet(value: Any) -> dict[str, Any]:
    item = validate_consultation(copy.deepcopy(value))
    if item["purpose"] not in {"QUESTION", "ANSWER"}:
        raise DialogueContractError("MESSAGE_INVALID")
    if not item["fingerprint"]:
        raise DialogueContractError("MESSAGE_INVALID")
    return item


def render_consultation_packet(value: Mapping[str, Any]) -> str:
    packet = _wire_packet(value)
    text = (
        f"{CONSULTATION_PACKET_DISCRIMINATOR}\n"
        f"{canonical_consultation_json(packet)}"
    )
    if len(text.encode("utf-8")) > CONSULTATION_PACKET_MAX_BYTES:
        raise DialogueContractError("FRAME_TOO_LARGE")
    return text


def parse_consultation_packet(raw: str | bytes) -> dict[str, Any]:
    if isinstance(raw, bytes):
        try:
            text = raw.decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            raise DialogueContractError("FRAME_INVALID") from None
    elif isinstance(raw, str):
        text = raw
    else:
        raise DialogueContractError("FRAME_INVALID")

    lines = text.split("\n")
    if (
        len(lines) != 2
        or lines[0] != CONSULTATION_PACKET_DISCRIMINATOR
        or not lines[1]
    ):
        raise DialogueContractError("FRAME_INVALID")
    if len(text.encode("utf-8")) > CONSULTATION_PACKET_MAX_BYTES:
        raise DialogueContractError("FRAME_TOO_LARGE")

    document = _strict_packet_loads(lines[1])
    packet = _wire_packet(document)
    if lines[1] != canonical_consultation_json(packet):
        raise DialogueContractError("FRAME_INVALID")
    return packet


def classify_duplicate(
    original: Mapping[str, Any], replay: Mapping[str, Any]
) -> DuplicateClassification:
    left = validate_consultation(original)
    right = validate_consultation(replay)
    if consultation_semantic_fingerprint(left) == consultation_semantic_fingerprint(right):
        return DuplicateClassification.IDEMPOTENT
    return DuplicateClassification.CONFLICT


__all__ = [
    "ANSWER_KEYS",
    "ARTIFACT_REVISION_KEYS",
    "CONSULTATION_KEYS",
    "CONSULTATION_PACKET_DISCRIMINATOR",
    "CONSULTATION_PACKET_MAX_BYTES",
    "CONSULTATION_V2_KEYS",
    "CONSULTATION_V2_SCHEMA",
    "CONSULTATION_PURPOSES",
    "CONSULTATION_SCHEMA",
    "CONSULTATION_SCHEMA_REASONING_SURFACES",
    "CORRELATION_KEYS",
    "GROK_CONSULTATION_SCHEMA",
    "DuplicateClassification",
    "RECEIPT_KEYS",
    "RECIPIENT_BINDING_KEYS",
    "RESPONSE_BUDGET_KEYS",
    "RESPONSE_BUDGET_MAXIMA",
    "build_consultation",
    "canonical_consultation_json",
    "classify_duplicate",
    "parse_consultation_packet",
    "render_consultation_packet",
    "consultation_schema_for_reasoning_surface",
    "consultation_semantic_fingerprint",
    "validate_consultation",
]
