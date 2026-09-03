"""Pure closed reduction for the Executive dialogue-observation boundary.

The owning Executive service prepares current Runtime and terminal-projection
facts.  This module performs no I/O and owns no lifecycle state; it validates
one untrusted V2 parent lookup and emits either one bounded observation or a
payload-free fixed refusal.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping

from common.commission_ref import CommissionRefError, normalize_commission_ref
from control_plane.executive_runtime import ExecutiveDialogueSource
from control_plane.executive_terminal_return import TerminalReturnCandidate


REQUEST_SCHEMA = "mastermind.dialogue_observation_request/v1"
RESPONSE_SCHEMA = "mastermind.dialogue_observation_response/v1"
ACTIVE_CURRENT_WORKER = "ACTIVE_CURRENT_WORKER"
TERMINAL_RESULT = "TERMINAL_RESULT"
MAX_REQUEST_BYTES = 64 * 1024
MAX_RESPONSE_BYTES = 64 * 1024

_REQUEST_KEYS = frozenset({"schema", "parent"})
_PARENT_SCHEMA = "mastermind.agent_dialogue_parent.v2"
_PARENT_KEYS = frozenset(
    {
        "schema",
        "work_ref",
        "commission_ref",
        "session_ref",
        "operation_key",
        "watch_mode",
        "allowed_sol_user_ids",
        "created_at",
        "fingerprint",
    }
)
_DIGEST_RE = re.compile(r"\A[0-9a-f]{64}\Z")
_PUBLIC_TOKEN_RE = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._:-]{0,255}\Z")
_WORK_REF_RE = re.compile(r"\AWS:[A-Z0-9][A-Z0-9-]{1,63}\Z")
_SESSION_REF_RE = re.compile(r"\Aasd-session-[a-z0-9][a-z0-9-]{7,63}\Z")
_OPERATION_KEY_RE = re.compile(r"\A[a-z0-9][a-z0-9._-]{7,127}\Z")
_SLACK_USER_ID_RE = re.compile(r"\A[UW][A-Z0-9]{8,31}\Z")
_UTC_RE = re.compile(r"\A\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")
_SECRET_SHAPED_RE = re.compile(
    r"(?i)(?:xox[a-z]-[A-Za-z0-9-]{10,}|xapp-[A-Za-z0-9-]{10,}|"
    r"github_pat_[A-Za-z0-9_]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|"
    r"sk-[A-Za-z0-9_-]{20,})"
)
_SLACK_MENTION_SHAPED_RE = re.compile(
    r"<@[UW][A-Z0-9]{8,31}(?:\|[^>\r\n]{1,80})?>"
)
_ACTIVE_ATTEMPT_STATUSES = frozenset({"CLAIMED", "RUNNING", "CHECKPOINTED"})
_TERMINAL_RECEIPT_ACTIONS = frozenset({"POSTED", "RECOVERED", "DUPLICATE"})
_TERMINAL_RECEIPT_FIELDS = frozenset(
    {
        "action",
        "message_key",
        "fingerprint",
        "message_ts",
        "duplicate_timestamps",
        "thread_ts",
        "parent_author_user_id",
        "parent_fingerprint",
    }
)
_AUTHORITY_FLAGS = {
    "action_authoritative": False,
    "provider_action_authorized": False,
    "wake_write_authorized": False,
    "lifecycle_write_authorized": False,
}


class DialogueObservationProtocolError(ValueError):
    """A wire value is not one exact bounded observation protocol value."""

    def __init__(self, code: str = "REQUEST_REFUSED") -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class ObservationRequest:
    parent: dict[str, Any]


@dataclass(frozen=True)
class PublicRuntimeBindingFacts:
    session_alias: str
    binding_id: str
    binding_generation: int
    reasoning_surface: str


@dataclass(frozen=True)
class ActiveObservationFacts:
    root_job_id: str
    job_id: str
    attempt_id: str
    worker_id: str
    attempt_status: str
    worker_status: str
    execution_profile_id: str
    execution_profile_digest: str
    capability_policy_digest: str
    runtime_binding: PublicRuntimeBindingFacts
    parent_fingerprint: str
    company_dialogue_server_identity: str
    company_dialogue_server_version: str
    company_dialogue_tool_schema_digest: str
    company_dialogue_attested: bool


@dataclass(frozen=True)
class TerminalObservationFacts:
    candidate: TerminalReturnCandidate
    projection_receipt: Any
    projection_effect: str
    binding_revalidated: bool


@dataclass(frozen=True)
class TerminalProjectionReceiptFacts:
    """The exact public R2 receipt shape, independent of integrations."""

    action: str
    message_key: str
    fingerprint: str
    message_ts: str
    duplicate_timestamps: tuple[str, ...]
    thread_ts: str
    parent_author_user_id: str
    parent_fingerprint: str


@dataclass(frozen=True)
class DialogueObservationFacts:
    active: tuple[ActiveObservationFacts, ...] = ()
    terminal: tuple[TerminalObservationFacts, ...] = ()
    complete: bool = True


def _reject_constant(_value: str) -> None:
    raise DialogueObservationProtocolError()


def _pairs_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DialogueObservationProtocolError()
        result[key] = value
    return result


def _contains_forbidden_leaf(value: Any) -> bool:
    if isinstance(value, str):
        return bool(
            _SECRET_SHAPED_RE.search(value)
            or "\u2028" in value
            or "\u2029" in value
            or _SLACK_MENTION_SHAPED_RE.search(value)
        )
    if isinstance(value, Mapping):
        return any(_contains_forbidden_leaf(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_forbidden_leaf(item) for item in value)
    return False


def _parent_fingerprint(value: Mapping[str, Any]) -> str:
    semantic = {
        key: item
        for key, item in value.items()
        if key not in {"created_at", "fingerprint"}
    }
    try:
        encoded = json.dumps(
            semantic,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError):
        raise DialogueObservationProtocolError() from None
    return hashlib.sha256(encoded).hexdigest()


def _validate_parent(value: Any) -> dict[str, Any]:
    """Validate the neutral closed V2 lookup without importing integrations."""

    if (
        not isinstance(value, dict)
        or set(value) != _PARENT_KEYS
        or value.get("schema") != _PARENT_SCHEMA
        or _contains_forbidden_leaf(value)
    ):
        raise DialogueObservationProtocolError()
    work_ref = value.get("work_ref")
    session_ref = value.get("session_ref")
    operation_key = value.get("operation_key")
    watch_mode = value.get("watch_mode")
    allowed = value.get("allowed_sol_user_ids")
    created_at = value.get("created_at")
    fingerprint = value.get("fingerprint")
    if (
        not isinstance(work_ref, str)
        or _WORK_REF_RE.fullmatch(work_ref) is None
        or not isinstance(session_ref, str)
        or _SESSION_REF_RE.fullmatch(session_ref) is None
        or not isinstance(operation_key, str)
        or _OPERATION_KEY_RE.fullmatch(operation_key) is None
        or (watch_mode is not None and watch_mode != "turn_watch_v1")
        or not isinstance(allowed, list)
        or not 1 <= len(allowed) <= 8
        or any(
            not isinstance(item, str)
            or _SLACK_USER_ID_RE.fullmatch(item) is None
            for item in allowed
        )
        or allowed != sorted(set(allowed))
        or not isinstance(created_at, str)
        or _UTC_RE.fullmatch(created_at) is None
        or not isinstance(fingerprint, str)
        or _DIGEST_RE.fullmatch(fingerprint) is None
    ):
        raise DialogueObservationProtocolError()
    try:
        datetime.strptime(created_at, "%Y-%m-%dT%H:%M:%SZ")
        commission_ref = normalize_commission_ref(value.get("commission_ref")).to_dict()
    except (CommissionRefError, TypeError, ValueError):
        raise DialogueObservationProtocolError() from None
    normalized = {
        "schema": _PARENT_SCHEMA,
        "work_ref": work_ref,
        "commission_ref": commission_ref,
        "session_ref": session_ref,
        "operation_key": operation_key,
        "watch_mode": watch_mode,
        "allowed_sol_user_ids": allowed,
        "created_at": created_at,
        "fingerprint": fingerprint,
    }
    if _parent_fingerprint(normalized) != fingerprint:
        raise DialogueObservationProtocolError()
    return normalized


def parse_observation_request(raw: bytes) -> ObservationRequest:
    """Strictly parse one request and reuse the canonical V2 parent validator."""

    if not isinstance(raw, bytes) or not raw or len(raw) > MAX_REQUEST_BYTES:
        raise DialogueObservationProtocolError()
    try:
        text = raw.decode("utf-8", errors="strict")
        value = json.loads(
            text,
            object_pairs_hook=_pairs_object,
            parse_constant=_reject_constant,
        )
        if not isinstance(value, dict) or set(value) != _REQUEST_KEYS:
            raise DialogueObservationProtocolError()
        if value.get("schema") != REQUEST_SCHEMA:
            raise DialogueObservationProtocolError()
        parent = _validate_parent(value.get("parent"))
        if parent != value.get("parent"):
            raise DialogueObservationProtocolError()
    except DialogueObservationProtocolError:
        raise
    except (TypeError, UnicodeDecodeError, ValueError):
        raise DialogueObservationProtocolError() from None
    return ObservationRequest(parent=parent)


def _canonical_json(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError):
        raise DialogueObservationProtocolError("FACTS_REFUSED") from None


def response_bytes(response: Mapping[str, Any]) -> bytes:
    """Serialize one closed response under the dedicated 64 KiB ceiling."""

    raw = _canonical_json(dict(response)) + b"\n"
    if len(raw) > MAX_RESPONSE_BYTES:
        return _canonical_json(
            {"schema": RESPONSE_SCHEMA, "state": "HELD", "reason": "RESPONSE_TOO_LARGE"}
        ) + b"\n"
    return raw


def _closed(state: str, reason: str) -> dict[str, Any]:
    return {"schema": RESPONSE_SCHEMA, "state": state, "reason": reason}


def _is_digest(value: Any) -> bool:
    return isinstance(value, str) and _DIGEST_RE.fullmatch(value) is not None


def _is_token(value: Any) -> bool:
    return isinstance(value, str) and _PUBLIC_TOKEN_RE.fullmatch(value) is not None


def _binding_wire(binding: PublicRuntimeBindingFacts) -> dict[str, Any] | None:
    if (
        not isinstance(binding, PublicRuntimeBindingFacts)
        or not _is_token(binding.session_alias)
        or not _is_token(binding.binding_id)
        or type(binding.binding_generation) is not int
        or binding.binding_generation < 1
        or not _is_token(binding.reasoning_surface)
    ):
        return None
    return {
        "session_alias": binding.session_alias,
        "binding_id": binding.binding_id,
        "binding_generation": binding.binding_generation,
        "reasoning_surface": binding.reasoning_surface,
    }


def _active_response(
    parent: Mapping[str, Any], facts: ActiveObservationFacts
) -> dict[str, Any]:
    if facts.parent_fingerprint != parent["fingerprint"]:
        return _closed("HELD", "DIALOGUE_PARENT_STALE")
    if facts.attempt_status not in _ACTIVE_ATTEMPT_STATUSES:
        return _closed("UNAVAILABLE", "CURRENT_ATTEMPT_INACTIVE")
    if facts.worker_status != "BUSY":
        return _closed("UNAVAILABLE", "CURRENT_WORKER_INACTIVE")
    if facts.company_dialogue_attested is not True:
        return _closed("HELD", "CAPABILITY_NOT_ATTESTED")
    binding = _binding_wire(facts.runtime_binding)
    if binding is None:
        return _closed("UNKNOWN", "CURRENT_RUNTIME_UNAVAILABLE")
    tokens = (
        facts.root_job_id,
        facts.job_id,
        facts.attempt_id,
        facts.worker_id,
        facts.execution_profile_id,
        facts.company_dialogue_server_identity,
        facts.company_dialogue_server_version,
    )
    digests = (
        facts.execution_profile_digest,
        facts.capability_policy_digest,
        facts.company_dialogue_tool_schema_digest,
        facts.parent_fingerprint,
    )
    if any(not _is_token(value) for value in tokens) or any(
        not _is_digest(value) for value in digests
    ):
        return _closed("HELD", "ACTIVE_FACTS_INVALID")
    observation = {
        "root_job_id": facts.root_job_id,
        "job_id": facts.job_id,
        "attempt_id": facts.attempt_id,
        "worker_id": facts.worker_id,
        "attempt_status": facts.attempt_status,
        "worker_status": facts.worker_status,
        "execution_profile_id": facts.execution_profile_id,
        "execution_profile_digest": facts.execution_profile_digest,
        "capability_policy_digest": facts.capability_policy_digest,
        "runtime_binding": binding,
        "parent_fingerprint": facts.parent_fingerprint,
        "company_dialogue_server_identity": facts.company_dialogue_server_identity,
        "company_dialogue_server_version": facts.company_dialogue_server_version,
        "company_dialogue_tool_schema_digest": facts.company_dialogue_tool_schema_digest,
        "company_dialogue_attested": True,
    }
    observation["evidence_digest"] = hashlib.sha256(
        _canonical_json(observation)
    ).hexdigest()
    return {
        "schema": RESPONSE_SCHEMA,
        "state": "RESOLVED",
        "mode": ACTIVE_CURRENT_WORKER,
        "observation": observation,
        **_AUTHORITY_FLAGS,
    }


def _source_wire(source: ExecutiveDialogueSource | None) -> dict[str, Any] | None:
    if not isinstance(source, ExecutiveDialogueSource):
        return None
    try:
        return source.to_dict()
    except (AttributeError, TypeError, ValueError):
        return None


def _terminal_response(
    parent: Mapping[str, Any], facts: TerminalObservationFacts
) -> dict[str, Any]:
    if facts.projection_effect == "EFFECT_UNKNOWN":
        return _closed("UNKNOWN", "R2_EFFECT_UNKNOWN")
    if facts.projection_effect != "APPLIED":
        return _closed("HELD", "R2_RECEIPT_MISSING")
    if facts.binding_revalidated is not True:
        return _closed("HELD", "R2_BINDING_UNAVAILABLE")
    candidate = facts.candidate
    receipt = facts.projection_receipt
    if (
        not isinstance(candidate, TerminalReturnCandidate)
        or not dataclasses.is_dataclass(receipt)
        or isinstance(receipt, type)
        or {field.name for field in dataclasses.fields(receipt)}
        != _TERMINAL_RECEIPT_FIELDS
    ):
        return _closed("HELD", "TERMINAL_FACTS_INVALID")
    source = _source_wire(candidate.dialogue_source)
    if (
        source is None
        or source.get("work_ref") != parent["work_ref"]
        or source.get("commission_ref") != parent["commission_ref"]
        or source.get("watch_mode") != parent["watch_mode"]
        or candidate.operation_key != parent["operation_key"]
        or candidate.session_ref != parent["session_ref"]
        or receipt.parent_fingerprint != parent["fingerprint"]
    ):
        return _closed("HELD", "DIALOGUE_PARENT_STALE")
    if (
        candidate.runtime_status != "COMPLETED"
        or candidate.result_status != "RESULT"
        or receipt.action not in _TERMINAL_RECEIPT_ACTIONS
        or receipt.message_key != candidate.message_key
        or receipt.duplicate_timestamps != ()
        or not isinstance(candidate.summary, str)
        or len(candidate.summary.encode("utf-8")) > 4096
    ):
        return _closed("HELD", "TERMINAL_FACTS_INVALID")
    candidate_wire = {
        "job_id": candidate.job_id,
        "attempt_id": candidate.attempt_id,
        "worker_id": candidate.worker_id,
        "root_job_id": candidate.root_job_id,
        "role": candidate.role,
        "operation_key": candidate.operation_key,
        "session_ref": candidate.session_ref,
        "runtime_status": candidate.runtime_status,
        "result_status": candidate.result_status,
        "result_envelope_digest": candidate.result_envelope_digest,
        "terminal_evidence_digest": candidate.terminal_evidence_digest,
        "artifact_receipt_digest": candidate.artifact_receipt_digest,
        "validation_receipt_digest": candidate.validation_receipt_digest,
        "effective_grant_digest": candidate.effective_grant_digest,
        "terminal_at": candidate.terminal_at,
        "message_key": candidate.message_key,
        "summary": candidate.summary,
        "review_verdict": candidate.review_verdict,
        "dialogue_source": source,
    }
    receipt_wire = dataclasses.asdict(receipt)
    receipt_wire["duplicate_timestamps"] = list(receipt.duplicate_timestamps)
    scalar_tokens = (
        candidate.job_id,
        candidate.attempt_id,
        candidate.worker_id,
        candidate.root_job_id,
        candidate.role,
        candidate.operation_key,
        candidate.session_ref,
        candidate.message_key,
        candidate.terminal_at,
        receipt.action,
        receipt.message_key,
        receipt.message_ts,
        receipt.thread_ts,
        receipt.parent_author_user_id,
    )
    digest_values = (
        candidate.result_envelope_digest,
        candidate.terminal_evidence_digest,
        candidate.artifact_receipt_digest,
        candidate.validation_receipt_digest,
        candidate.effective_grant_digest,
        receipt.fingerprint,
        receipt.parent_fingerprint,
    )
    if any(not _is_token(value) for value in scalar_tokens) or any(
        not _is_digest(value) for value in digest_values
    ):
        return _closed("HELD", "TERMINAL_FACTS_INVALID")
    projection_receipt_digest = hashlib.sha256(
        _canonical_json(receipt_wire)
    ).hexdigest()
    observation = {
        "candidate": candidate_wire,
        "projection_receipt": receipt_wire,
        "projection_receipt_digest": projection_receipt_digest,
        "projection_effect": "APPLIED",
    }
    observation["evidence_digest"] = hashlib.sha256(
        _canonical_json(observation)
    ).hexdigest()
    return {
        "schema": RESPONSE_SCHEMA,
        "state": "RESOLVED",
        "mode": TERMINAL_RESULT,
        "observation": observation,
        **_AUTHORITY_FLAGS,
    }


def reduce_dialogue_observation(
    *, parent: Mapping[str, Any], facts: DialogueObservationFacts
) -> dict[str, Any]:
    """Select exactly one non-interchangeable observation from prepared facts."""

    try:
        canonical_parent = _validate_parent(dict(parent))
    except (DialogueObservationProtocolError, TypeError, ValueError):
        return _closed("HELD", "DIALOGUE_PARENT_INVALID")
    if not isinstance(facts, DialogueObservationFacts):
        return _closed("HELD", "OBSERVATION_FACTS_UNAVAILABLE")
    if (
        type(facts.active) is not tuple
        or type(facts.terminal) is not tuple
        or type(facts.complete) is not bool
    ):
        return _closed("HELD", "OBSERVATION_FACTS_UNAVAILABLE")
    if not facts.complete:
        return _closed("UNKNOWN", "OBSERVATION_SCAN_INCOMPLETE")
    if len(facts.active) > 1:
        return _closed("CONFLICT", "MULTIPLE_ACTIVE_BINDINGS")
    if len(facts.terminal) > 1:
        return _closed("CONFLICT", "MULTIPLE_TERMINAL_BINDINGS")
    if facts.active and facts.terminal:
        return _closed("CONFLICT", "OBSERVATION_MODE_CONFLICT")
    if facts.active:
        return _active_response(canonical_parent, facts.active[0])
    if facts.terminal:
        return _terminal_response(canonical_parent, facts.terminal[0])
    return _closed("UNAVAILABLE", "PARENT_NOT_EXECUTIVE_BOUND")


__all__ = [
    "ACTIVE_CURRENT_WORKER",
    "MAX_REQUEST_BYTES",
    "MAX_RESPONSE_BYTES",
    "REQUEST_SCHEMA",
    "RESPONSE_SCHEMA",
    "TERMINAL_RESULT",
    "ActiveObservationFacts",
    "DialogueObservationFacts",
    "DialogueObservationProtocolError",
    "ObservationRequest",
    "PublicRuntimeBindingFacts",
    "TerminalObservationFacts",
    "TerminalProjectionReceiptFacts",
    "parse_observation_request",
    "reduce_dialogue_observation",
    "response_bytes",
]
