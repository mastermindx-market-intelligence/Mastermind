"""Pure closed contracts for the Executive dialogue-coordination boundary.

The owning Executive service prepares current Runtime and terminal-projection
facts and remains the only authority for Wake effects. This module performs no
I/O and owns no lifecycle state; it validates one untrusted V2 parent lookup or
non-authoritative Wake proposal and emits a bounded payload-free result.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Mapping

from common.commission_ref import CommissionRefError, normalize_commission_ref
from control_plane.executive_runtime import (
    ExecutiveDialogueSource,
    JobStatus,
    PersistenceError,
    Runtime,
    RuntimeProofError,
    StateConflict,
    ValidatedRoleCompletion,
    _attempt_from_row,
    _dialogue_source_from_root_creation,
    _job_from_row,
    _strict_canonical_json_loads,
    _validated_role_completion_material,
)
from control_plane.session_targets import BINDING_ID_RE, WakeRoute
from control_plane.executive_terminal_return import (
    TerminalReturnCandidate,
    TerminalReturnError,
    reduce_terminal_return,
)
from control_plane.operator_harness_contract import AttemptExecutionMode
from control_plane.wake_events import (
    SourceKind,
    WakeKind,
    WakeObligation,
    WakeObligationError,
    parse_obligation,
)


REQUEST_SCHEMA = "mastermind.executive_dialogue_observation_request.v1"
RESPONSE_SCHEMA = "mastermind.executive_dialogue_observation_response.v1"
WAKE_REQUEST_SCHEMA = "mastermind.dialogue_wake_request/v1"
WAKE_RESPONSE_SCHEMA = "mastermind.dialogue_wake_response/v1"
RESOLVE_PARENT = "RESOLVE_PARENT"
RECONCILE_WAKE = "RECONCILE_WAKE"
SUBMIT_WAKE = "SUBMIT_WAKE"
ACTIVE_CURRENT_WORKER = "ACTIVE_CURRENT_WORKER"
TERMINAL_RESULT = "TERMINAL_RESULT"
MAX_REQUEST_BYTES = 64 * 1024
MAX_RESPONSE_BYTES = 64 * 1024
CANONICAL_WAKE_EVENT_BUDGET = 64
TERMINAL_SOURCE_OWNER = "executive_terminal_return"
WAKE_SOURCE_OWNER = "wake_ledger"
TERMINAL_RETURN_PROJECTION_SCHEMA = "mastermind.executive_terminal_return_projection/v1"
TERMINAL_RETURN_PREPARED_EVENT = "EXECUTIVE_TERMINAL_RETURN_PREPARED"
TERMINAL_RETURN_ATTEMPTED_EVENT = "EXECUTIVE_TERMINAL_RETURN_ATTEMPTED"
TERMINAL_RETURN_PRE_SUBMIT_REFUSED_EVENT = (
    "EXECUTIVE_TERMINAL_RETURN_PRE_SUBMIT_REFUSED"
)
TERMINAL_RETURN_EFFECT_UNKNOWN_EVENT = "EXECUTIVE_TERMINAL_RETURN_EFFECT_UNKNOWN"
TERMINAL_RETURN_PROVEN_NO_EFFECT_EVENT = (
    "EXECUTIVE_TERMINAL_RETURN_PROVEN_NO_EFFECT"
)
TERMINAL_RETURN_APPLIED_EVENT = "EXECUTIVE_TERMINAL_RETURN_APPLIED"
TERMINAL_RETURN_RECEIPT_ACTIONS = frozenset({"POSTED", "RECOVERED", "DUPLICATE"})

_REQUEST_KEYS = frozenset({"schema", "request_id", "parent"})
_WAKE_REQUEST_KEYS = frozenset(
    {
        "schema",
        "operation",
        "parent",
        "thread_ts",
        "candidate",
        "obligation",
        "route",
    }
)
_CANDIDATE_KEYS = frozenset(
    {"mode", "root_job_id", "job_id", "attempt_id", "worker_id", "evidence_digest"}
)
_WAKE_ROUTE_KEYS = frozenset(
    {
        "obligation_id",
        "session_alias",
        "target_seat",
        "reasoning_surface",
        "wake_transport",
        "binding_id",
        "binding_generation",
        "route_digest",
        "destination_digest",
        "policy_digest",
        "root_job_id",
        "workstream",
        "production_armed",
        "target_enabled",
        "transport_implemented",
        "requires_runtime_binding",
        "binding_ready",
        "human_required",
        "policy_version",
        "interface_version",
        "delivery_allowed",
    }
)
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
_SHORT_DIGEST_RE = re.compile(r"\A[0-9a-f]{16}\Z")
_THREAD_TS_RE = re.compile(r"\A[1-9][0-9]{9,15}\.[0-9]{6}\Z")
_REASON_RE = re.compile(r"\A[A-Z][A-Z0-9_]{2,127}\Z")
_PUBLIC_TOKEN_RE = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._:-]{0,255}\Z")
_ROUTE_TOKEN_RE = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}\Z")
_WORK_REF_RE = re.compile(r"\AWS:[A-Z0-9][A-Z0-9-]{1,63}\Z")
_SESSION_REF_RE = re.compile(r"\Aasd-session-[a-z0-9][a-z0-9-]{7,63}\Z")
_OPERATION_KEY_RE = re.compile(r"\A[a-z0-9][a-z0-9._-]{7,127}\Z")
_SLACK_USER_ID_RE = re.compile(r"\A[UW][A-Z0-9]{8,31}\Z")
_TERMINAL_RETURN_SLACK_TS_RE = re.compile(r"\A[0-9]{10,16}\.[0-9]{6}\Z")
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
    request_id: str
    parent: dict[str, Any]


@dataclass(frozen=True)
class DialogueCandidateReference:
    mode: str
    root_job_id: str
    job_id: str
    attempt_id: str
    worker_id: str
    evidence_digest: str

    def to_dict(self) -> dict[str, str]:
        return dataclasses.asdict(self)


@dataclass(frozen=True)
class DialogueWakeRequest:
    operation: str
    parent: dict[str, Any]
    thread_ts: str
    candidate: DialogueCandidateReference
    obligation: WakeObligation
    proposed_route: WakeRoute


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
    target_bindings: Mapping[str, PublicRuntimeBindingFacts | None] = (
        dataclasses.field(default_factory=lambda: {"coo": None, "ceo": None})
    )


@dataclass(frozen=True)
class TerminalObservationFacts:
    candidate: TerminalReturnCandidate
    projection_receipt: Any
    projection_effect: str
    binding_revalidated: bool
    target_bindings: Mapping[str, PublicRuntimeBindingFacts | None] = (
        dataclasses.field(default_factory=lambda: {"coo": None, "ceo": None})
    )


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
class TerminalProjectionReceiptReference:
    """Closed public reference to one fully validated physical receipt."""

    action: str
    message_fingerprint: str
    receipt_digest: str


@dataclass(frozen=True)
class DialogueObservationFacts:
    active: tuple[ActiveObservationFacts, ...] = ()
    terminal: tuple[TerminalObservationFacts, ...] = ()
    complete: bool = True


@dataclass(frozen=True)
class CanonicalTerminalWakeCandidate:
    """Exact candidate identity accepted by the bounded Control Room read."""

    root_job_id: str
    job_id: str
    attempt_id: str
    worker_id: str


@dataclass(frozen=True)
class CanonicalTerminalProjection:
    """Minimal public terminal identity produced by the canonical owner."""

    state: str
    root_job_id: str
    job_id: str
    attempt_id: str
    worker_id: str
    result_status: str
    terminal_at: str
    result_envelope_digest: str
    terminal_evidence_digest: str
    artifact_receipt_digest: str
    validation_receipt_digest: str
    effective_grant_digest: str
    evidence_digest: str
    projection_receipt_digest: str
    source_owner: str = TERMINAL_SOURCE_OWNER


@dataclass(frozen=True)
class CanonicalWakeProjection:
    """Minimal public identity/status for one correlated persisted Wake."""

    obligation_id: str
    status: str
    declared_target_seat: str
    source_ref_digest: str
    source_observed_at: str
    source_owner: str = WAKE_SOURCE_OWNER


@dataclass(frozen=True)
class CanonicalSourceReceipt:
    """Bounded read-snapshot identity without raw source identifiers."""

    observed_at: str
    freshness: str
    snapshot_digest: str
    terminal_source_owner: str = TERMINAL_SOURCE_OWNER
    wake_source_owner: str = WAKE_SOURCE_OWNER


@dataclass(frozen=True)
class CanonicalTerminalWakeRead:
    """Public read-only terminal/Wake result with no provider or payload data."""

    state: str
    reason: str
    terminal_state: str
    wake_state: str
    terminal_applied: bool
    terminal: CanonicalTerminalProjection | None = None
    wake: CanonicalWakeProjection | None = None
    source_receipt: CanonicalSourceReceipt | None = None
    action_authoritative: bool = False
    provider_action_authorized: bool = False
    wake_write_authorized: bool = False
    lifecycle_write_authorized: bool = False

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


CanonicalDialogueFactsProvider = Callable[
    [Any, CanonicalTerminalWakeCandidate, Any], DialogueObservationFacts
]


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
        request_id = value.get("request_id")
        if not _is_token(request_id):
            raise DialogueObservationProtocolError()
        parent = _validate_parent(value.get("parent"))
        if parent != value.get("parent"):
            raise DialogueObservationProtocolError()
    except DialogueObservationProtocolError:
        raise
    except (TypeError, UnicodeDecodeError, ValueError):
        raise DialogueObservationProtocolError() from None
    return ObservationRequest(
        request_id=request_id,
        parent=parent,
    )


def _validate_candidate(value: Any) -> DialogueCandidateReference:
    if (
        not isinstance(value, dict)
        or set(value) != _CANDIDATE_KEYS
        or value.get("mode") not in {ACTIVE_CURRENT_WORKER, TERMINAL_RESULT}
        or any(
            not _is_route_token(value.get(name))
            for name in ("root_job_id", "job_id", "attempt_id", "worker_id")
        )
        or not _is_digest(value.get("evidence_digest"))
        or _contains_forbidden_leaf(value)
    ):
        raise DialogueObservationProtocolError()
    return DialogueCandidateReference(**value)


def _validate_proposed_route(
    value: Any,
    *,
    obligation: WakeObligation,
) -> WakeRoute:
    if (
        not isinstance(value, dict)
        or set(value) != _WAKE_ROUTE_KEYS
        or _contains_forbidden_leaf(value)
    ):
        raise DialogueObservationProtocolError()
    bool_fields = (
        "production_armed",
        "target_enabled",
        "transport_implemented",
        "requires_runtime_binding",
        "binding_ready",
        "human_required",
        "delivery_allowed",
    )
    if any(type(value.get(name)) is not bool for name in bool_fields):
        raise DialogueObservationProtocolError()
    generation = value.get("binding_generation")
    if type(generation) is not int or generation < 0:
        raise DialogueObservationProtocolError()
    if value.get("binding_ready"):
        if generation < 1 or BINDING_ID_RE.fullmatch(str(value.get("binding_id"))) is None:
            raise DialogueObservationProtocolError()
    elif generation != 0 or value.get("binding_id") != "":
        raise DialogueObservationProtocolError()
    scalar_fields = (
        "obligation_id",
        "session_alias",
        "target_seat",
        "reasoning_surface",
        "wake_transport",
        "policy_version",
        "interface_version",
    )
    if any(not _is_route_token(value.get(name)) for name in scalar_fields):
        raise DialogueObservationProtocolError()
    if (
        value.get("obligation_id") != obligation.obligation_id
        or value.get("target_seat") != obligation.declared_target_seat
        or value.get("root_job_id") != obligation.root_job_id
        or value.get("workstream") != obligation.routing_workstream
        or _SHORT_DIGEST_RE.fullmatch(str(value.get("route_digest"))) is None
        or _SHORT_DIGEST_RE.fullmatch(str(value.get("destination_digest"))) is None
        or _SHORT_DIGEST_RE.fullmatch(str(value.get("policy_digest"))) is None
    ):
        raise DialogueObservationProtocolError()
    try:
        route = WakeRoute(
            **{
                key: item
                for key, item in value.items()
                if key != "delivery_allowed"
            }
        )
    except (TypeError, ValueError):
        raise DialogueObservationProtocolError() from None
    if route.delivery_allowed is not value.get("delivery_allowed"):
        raise DialogueObservationProtocolError()
    return route


def parse_wake_request(raw: bytes) -> DialogueWakeRequest:
    """Parse one non-authoritative Relay Wake proposal on the same socket."""

    if not isinstance(raw, bytes) or not raw or len(raw) > MAX_REQUEST_BYTES:
        raise DialogueObservationProtocolError()
    try:
        value = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_pairs_object,
            parse_constant=_reject_constant,
        )
        if (
            not isinstance(value, dict)
            or set(value) != _WAKE_REQUEST_KEYS
            or value.get("schema") != WAKE_REQUEST_SCHEMA
            or value.get("operation") not in {RECONCILE_WAKE, SUBMIT_WAKE}
        ):
            raise DialogueObservationProtocolError()
        parent = _validate_parent(value.get("parent"))
        if parent != value.get("parent"):
            raise DialogueObservationProtocolError()
        thread_ts = value.get("thread_ts")
        if not isinstance(thread_ts, str) or _THREAD_TS_RE.fullmatch(thread_ts) is None:
            raise DialogueObservationProtocolError()
        candidate = _validate_candidate(value.get("candidate"))
        obligation_value = value.get("obligation")
        if not isinstance(obligation_value, dict):
            raise DialogueObservationProtocolError()
        obligation = parse_obligation(obligation_value)
        if (
            obligation.source_kind is not SourceKind.AGENT_DIALOGUE_ATTENTION
            or obligation.wake_kind is not WakeKind.DIALOGUE_TURN_PENDING
        ):
            raise DialogueObservationProtocolError()
        route = _validate_proposed_route(
            value.get("route"),
            obligation=obligation,
        )
    except DialogueObservationProtocolError:
        raise
    except (TypeError, UnicodeDecodeError, ValueError, WakeObligationError):
        raise DialogueObservationProtocolError() from None
    return DialogueWakeRequest(
        operation=value["operation"],
        parent=parent,
        thread_ts=thread_ts,
        candidate=candidate,
        obligation=obligation,
        proposed_route=route,
    )


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


def wake_response_bytes(*, state: str, reason: str) -> bytes:
    """Serialize one payload-free Wake coordination result."""

    if state not in {"MISSING", "RECORDED", "EFFECT_UNKNOWN"}:
        raise DialogueObservationProtocolError("FACTS_REFUSED")
    if not isinstance(reason, str) or _REASON_RE.fullmatch(reason) is None:
        raise DialogueObservationProtocolError("FACTS_REFUSED")
    raw = _canonical_json(
        {"schema": WAKE_RESPONSE_SCHEMA, "state": state, "reason": reason}
    ) + b"\n"
    if len(raw) > MAX_RESPONSE_BYTES:
        raise DialogueObservationProtocolError("FACTS_REFUSED")
    return raw


def _closed(state: str, reason: str) -> dict[str, Any]:
    return {"schema": RESPONSE_SCHEMA, "state": state, "reason": reason}


def _is_digest(value: Any) -> bool:
    return isinstance(value, str) and _DIGEST_RE.fullmatch(value) is not None


def _is_token(value: Any) -> bool:
    return isinstance(value, str) and _PUBLIC_TOKEN_RE.fullmatch(value) is not None


def _is_route_token(value: Any) -> bool:
    return isinstance(value, str) and _ROUTE_TOKEN_RE.fullmatch(value) is not None


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


def _target_bindings_wire(
    bindings: Mapping[str, PublicRuntimeBindingFacts | None],
) -> dict[str, dict[str, Any] | None] | None:
    if not isinstance(bindings, Mapping) or set(bindings) != {"coo", "ceo"}:
        return None
    result: dict[str, dict[str, Any] | None] = {}
    for seat in ("coo", "ceo"):
        value = bindings[seat]
        if value is None:
            result[seat] = None
            continue
        encoded = _binding_wire(value)
        if encoded is None:
            return None
        result[seat] = encoded
    return result


def terminal_projection_receipt_reference(
    receipt: Any,
) -> TerminalProjectionReceiptReference | None:
    """Reduce one exact full receipt to the public information boundary."""

    if (
        not dataclasses.is_dataclass(receipt)
        or isinstance(receipt, type)
        or {field.name for field in dataclasses.fields(receipt)}
        != _TERMINAL_RECEIPT_FIELDS
    ):
        return None
    try:
        receipt_wire = dataclasses.asdict(receipt)
        if (
            receipt.action not in _TERMINAL_RECEIPT_ACTIONS
            or not _is_token(receipt.message_key)
            or not _is_digest(receipt.fingerprint)
            or _THREAD_TS_RE.fullmatch(str(receipt.message_ts)) is None
            or receipt.duplicate_timestamps != ()
            or _THREAD_TS_RE.fullmatch(str(receipt.thread_ts)) is None
            or _SLACK_USER_ID_RE.fullmatch(str(receipt.parent_author_user_id))
            is None
            or not _is_digest(receipt.parent_fingerprint)
        ):
            return None
        receipt_wire["duplicate_timestamps"] = list(receipt.duplicate_timestamps)
        return TerminalProjectionReceiptReference(
            action=receipt.action,
            message_fingerprint=receipt.fingerprint,
            receipt_digest=hashlib.sha256(_canonical_json(receipt_wire)).hexdigest(),
        )
    except (AttributeError, DialogueObservationProtocolError, TypeError, ValueError):
        return None


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
    target_bindings = _target_bindings_wire(facts.target_bindings)
    if binding is None or target_bindings is None:
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
        "target_bindings": target_bindings,
        **_AUTHORITY_FLAGS,
    }


def _source_wire(source: ExecutiveDialogueSource | None) -> dict[str, Any] | None:
    if not isinstance(source, ExecutiveDialogueSource):
        return None
    try:
        return source.to_dict()
    except (AttributeError, TypeError, ValueError):
        return None


def _terminal_public_material(
    facts: TerminalObservationFacts,
) -> tuple[dict[str, Any], TerminalProjectionReceiptReference, dict[str, Any]] | None:
    """Validate once and return the secret-safe canonical terminal material."""

    candidate = facts.candidate
    receipt = facts.projection_receipt
    receipt_reference = terminal_projection_receipt_reference(receipt)
    if not isinstance(candidate, TerminalReturnCandidate) or receipt_reference is None:
        return None
    source = _source_wire(candidate.dialogue_source)
    if (
        source is None
        or candidate.runtime_status != "COMPLETED"
        or candidate.result_status != "RESULT"
        or receipt.action not in _TERMINAL_RECEIPT_ACTIONS
        or receipt.message_key != candidate.message_key
        or receipt.duplicate_timestamps != ()
        or not isinstance(candidate.summary, str)
        or len(candidate.summary.encode("utf-8")) > 4096
    ):
        return None
    terminal_digest = str(candidate.terminal_digest or "")
    if not _is_digest(terminal_digest):
        return None
    projection_command_digest = hashlib.sha256(
        (
            f"terminal-return:{candidate.attempt_id}:"
            f"{terminal_digest}:applied"
        ).encode("ascii")
    ).hexdigest()
    candidate_wire = {
        "job_id": candidate.job_id,
        "attempt_id": candidate.attempt_id,
        "worker_id": candidate.worker_id,
        "root_job_id": candidate.root_job_id,
        "runtime_status": candidate.runtime_status,
        "result_status": candidate.result_status,
        "result_envelope_digest": candidate.result_envelope_digest,
        "terminal_evidence_digest": candidate.terminal_evidence_digest,
        "artifact_receipt_digest": candidate.artifact_receipt_digest,
        "validation_receipt_digest": candidate.validation_receipt_digest,
        "effective_grant_digest": candidate.effective_grant_digest,
        "terminal_at": candidate.terminal_at,
        "projection_command_digest": projection_command_digest,
    }
    scalar_tokens = (
        candidate.job_id,
        candidate.attempt_id,
        candidate.worker_id,
        candidate.root_job_id,
        candidate.role,
        candidate.operation_key,
        candidate.session_ref,
        candidate.message_key,
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
    ) or _UTC_RE.fullmatch(str(candidate.terminal_at)) is None:
        return None
    return candidate_wire, receipt_reference, source


def _terminal_response(
    parent: Mapping[str, Any],
    facts: TerminalObservationFacts,
    *,
    thread_ts: str | None,
) -> dict[str, Any]:
    if facts.projection_effect == "EFFECT_UNKNOWN":
        return _closed("UNKNOWN", "R2_EFFECT_UNKNOWN")
    if facts.projection_effect != "APPLIED":
        return _closed("HELD", "R2_RECEIPT_MISSING")
    if facts.binding_revalidated is not True:
        return _closed("HELD", "R2_BINDING_UNAVAILABLE")
    material = _terminal_public_material(facts)
    target_bindings = _target_bindings_wire(facts.target_bindings)
    if material is None or target_bindings is None:
        return _closed("HELD", "TERMINAL_FACTS_INVALID")
    candidate_wire, receipt_reference, source = material
    candidate = facts.candidate
    receipt = facts.projection_receipt
    if (
        source.get("work_ref") != parent["work_ref"]
        or source.get("commission_ref") != parent["commission_ref"]
        or source.get("watch_mode") != parent["watch_mode"]
        or candidate.operation_key != parent["operation_key"]
        or candidate.session_ref != parent["session_ref"]
        or receipt.parent_fingerprint != parent["fingerprint"]
        or (thread_ts is not None and receipt.thread_ts != thread_ts)
    ):
        return _closed("HELD", "DIALOGUE_PARENT_STALE")
    receipt_wire = dataclasses.asdict(receipt_reference)
    observation = {
        "candidate": candidate_wire,
        "projection_receipt": receipt_wire,
        "projection_receipt_digest": receipt_reference.receipt_digest,
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
        "target_bindings": target_bindings,
        **_AUTHORITY_FLAGS,
    }


def reduce_dialogue_observation(
    *,
    parent: Mapping[str, Any],
    facts: DialogueObservationFacts,
    thread_ts: str | None = None,
) -> dict[str, Any]:
    """Select exactly one non-interchangeable observation from prepared facts."""

    try:
        canonical_parent = _validate_parent(dict(parent))
    except (DialogueObservationProtocolError, TypeError, ValueError):
        return _closed("HELD", "DIALOGUE_PARENT_INVALID")
    if thread_ts is not None and (
        not isinstance(thread_ts, str) or _THREAD_TS_RE.fullmatch(thread_ts) is None
    ):
        return _closed("HELD", "DIALOGUE_THREAD_INVALID")
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
    if facts.active:
        return _active_response(canonical_parent, facts.active[0])
    if len(facts.terminal) > 1:
        return _closed("CONFLICT", "MULTIPLE_TERMINAL_BINDINGS")
    if facts.terminal:
        return _terminal_response(
            canonical_parent,
            facts.terminal[0],
            thread_ts=thread_ts,
        )
    return _closed("UNAVAILABLE", "PARENT_NOT_EXECUTIVE_BOUND")


def terminal_return_event_material(
    candidate: TerminalReturnCandidate,
) -> tuple[str, dict[str, Any]]:
    """Derive the immutable projection command family and Event material."""

    terminal_digest = str(candidate.terminal_digest or "")
    if re.fullmatch(r"[0-9a-f]{64}", terminal_digest) is None:
        raise StateConflict("terminal-return candidate lacks a canonical terminal digest")
    candidate_bytes = (
        json.dumps(
            dataclasses.asdict(candidate),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )
    candidate_digest = hashlib.sha256(candidate_bytes).hexdigest()
    command_base = f"terminal-return:{candidate.attempt_id}:{terminal_digest}"
    return command_base, {
        "schema_version": TERMINAL_RETURN_PROJECTION_SCHEMA,
        "job_id": candidate.job_id,
        "attempt_id": candidate.attempt_id,
        "worker_id": candidate.worker_id,
        "root_job_id": candidate.root_job_id,
        "message_key": candidate.message_key,
        "terminal_digest": terminal_digest,
        "candidate_digest": candidate_digest,
    }


def normalize_terminal_return_projection_receipt(
    receipt: Any,
    *,
    message_key: str,
) -> dict[str, Any]:
    """Freeze only one exact physical Relay RESULT as durable APPLIED proof."""

    if dataclasses.is_dataclass(receipt) and not isinstance(receipt, type):
        value = dataclasses.asdict(receipt)
    elif isinstance(receipt, Mapping):
        value = dict(receipt)
    else:
        raise StateConflict("terminal-return projection receipt is invalid")
    expected = {
        "action",
        "message_key",
        "fingerprint",
        "message_ts",
        "duplicate_timestamps",
        "thread_ts",
        "parent_author_user_id",
        "parent_fingerprint",
    }
    duplicates = value.get("duplicate_timestamps")
    if (
        set(value) != expected
        or value.get("action") not in TERMINAL_RETURN_RECEIPT_ACTIONS
        or value.get("message_key") != message_key
        or not isinstance(value.get("fingerprint"), str)
        or re.fullmatch(r"[0-9a-f]{64}", value["fingerprint"]) is None
        or not isinstance(value.get("message_ts"), str)
        or _TERMINAL_RETURN_SLACK_TS_RE.fullmatch(value["message_ts"]) is None
        or not isinstance(value.get("thread_ts"), str)
        or _TERMINAL_RETURN_SLACK_TS_RE.fullmatch(value["thread_ts"]) is None
        or not isinstance(value.get("parent_author_user_id"), str)
        or re.fullmatch(r"[UW][A-Z0-9]{8,31}", value["parent_author_user_id"])
        is None
        or not isinstance(value.get("parent_fingerprint"), str)
        or re.fullmatch(r"[0-9a-f]{64}", value["parent_fingerprint"])
        is None
        or not isinstance(duplicates, (list, tuple))
        or len(duplicates) != 0
    ):
        raise StateConflict("terminal-return projection receipt is invalid")
    return {
        "action": value["action"],
        "message_key": value["message_key"],
        "fingerprint": value["fingerprint"],
        "message_ts": value["message_ts"],
        "duplicate_timestamps": [],
        "thread_ts": value["thread_ts"],
        "parent_author_user_id": value["parent_author_user_id"],
        "parent_fingerprint": value["parent_fingerprint"],
    }


def validate_terminal_return_event(
    event: Any,
    *,
    event_type: str,
    command_id: str,
    material: Mapping[str, Any],
    applied: bool,
) -> None:
    """Validate one immutable member of the terminal projection Event family."""

    expected_keys = set(material) | ({"projection_receipt"} if applied else set())
    payload = getattr(event, "payload", None)
    if (
        event is None
        or event.event_type != event_type
        or event.command_id != command_id
        or event.aggregate_type != "terminal_return_projection"
        or event.aggregate_id != material["attempt_id"]
        or event.job_id != material["job_id"]
        or event.attempt_id != material["attempt_id"]
        or event.worker_id != material["worker_id"]
        or not isinstance(payload, dict)
        or set(payload) != expected_keys
        or any(payload.get(key) != value for key, value in material.items())
    ):
        raise StateConflict("terminal-return projection event drifted")
    if applied:
        normalized_receipt = normalize_terminal_return_projection_receipt(
            payload.get("projection_receipt"),
            message_key=str(material["message_key"]),
        )
        if payload.get("projection_receipt") != normalized_receipt:
            raise StateConflict("terminal-return projection receipt drifted")


def terminal_return_phase_spec(
    command_base: str,
) -> tuple[tuple[str, str, str], ...]:
    """Return the sole ordered phase, Event, and stable-command vocabulary."""

    return (
        (
            "PREPARED",
            TERMINAL_RETURN_PREPARED_EVENT,
            f"{command_base}:prepared",
        ),
        (
            "PRE_SUBMIT_REFUSED",
            TERMINAL_RETURN_PRE_SUBMIT_REFUSED_EVENT,
            f"{command_base}:pre-submit-refused",
        ),
        (
            "ATTEMPTED",
            TERMINAL_RETURN_ATTEMPTED_EVENT,
            f"{command_base}:attempted",
        ),
        (
            "PROVEN_NO_EFFECT",
            TERMINAL_RETURN_PROVEN_NO_EFFECT_EVENT,
            f"{command_base}:proven-no-effect",
        ),
        (
            "EFFECT_UNKNOWN",
            TERMINAL_RETURN_EFFECT_UNKNOWN_EVENT,
            f"{command_base}:effect-unknown",
        ),
        (
            "APPLIED",
            TERMINAL_RETURN_APPLIED_EVENT,
            f"{command_base}:applied",
        ),
    )


def inspect_terminal_return_history(
    runtime: Runtime,
    connection: sqlite3.Connection,
    *,
    candidate: TerminalReturnCandidate,
    material: Mapping[str, Any],
) -> str | None:
    """Validate one exact immutable projection family without mutating it."""

    command_base, expected_material = terminal_return_event_material(candidate)
    if dict(material) != expected_material:
        raise StateConflict("terminal-return projection material drifted")
    phase_spec = terminal_return_phase_spec(command_base)
    expected_by_command = {
        command_id: (phase_name, event_type)
        for phase_name, event_type, command_id in phase_spec
    }
    rows = connection.execute(
        """
        SELECT command_id,event_type,event_id
        FROM events
        WHERE aggregate_type='terminal_return_projection'
          AND aggregate_id=?
        ORDER BY event_id
        LIMIT ?
        """,
        (candidate.attempt_id, len(phase_spec) + 1),
    ).fetchall()
    if not rows:
        return None
    if len(rows) > len(phase_spec):
        raise StateConflict("terminal-return projection event drifted")

    phases: list[str] = []
    applied_receipt: dict[str, Any] | None = None
    seen: set[str] = set()
    for row in rows:
        command_id = str(row["command_id"] or "")
        expected = expected_by_command.get(command_id)
        if (
            expected is None
            or row["event_type"] != expected[1]
            or expected[0] in seen
        ):
            raise StateConflict("terminal-return projection event drifted")
        phase_name, event_type = expected
        event = runtime.store.get_event_by_command_id(
            command_id,
            connection=connection,
        )
        validate_terminal_return_event(
            event,
            event_type=event_type,
            command_id=command_id,
            material=material,
            applied=phase_name == "APPLIED",
        )
        if phase_name == "APPLIED":
            applied_receipt = normalize_terminal_return_projection_receipt(
                event.payload.get("projection_receipt"),
                message_key=candidate.message_key,
            )
        phases.append(phase_name)
        seen.add(phase_name)

    if phases[0] != "PREPARED":
        raise StateConflict("terminal-return projection event drifted")
    phase_rank = {
        phase_name: index
        for index, (phase_name, _event_type, _command_id) in enumerate(phase_spec)
    }
    if any(
        phase_rank[current] >= phase_rank[following]
        for current, following in zip(phases, phases[1:])
    ):
        raise StateConflict("terminal-return projection phase order drifted")
    if "APPLIED" in seen and phases[-1] != "APPLIED":
        raise StateConflict("terminal-return projection phase order drifted")
    if "EFFECT_UNKNOWN" in seen and "ATTEMPTED" not in seen:
        raise StateConflict("terminal-return projection phase order drifted")
    if "PROVEN_NO_EFFECT" in seen and "ATTEMPTED" not in seen:
        raise StateConflict("terminal-return projection phase order drifted")
    if "APPLIED" in seen:
        assert applied_receipt is not None
        action = applied_receipt["action"]
        prior_phase = phases[-2] if len(phases) >= 2 else None
        if action == "POSTED" and (
            "ATTEMPTED" not in seen
            or prior_phase not in {"ATTEMPTED", "PROVEN_NO_EFFECT"}
        ):
            raise StateConflict("terminal-return projection phase order drifted")
        if action == "RECOVERED" and (
            "ATTEMPTED" not in seen
            or prior_phase
            not in {"ATTEMPTED", "PROVEN_NO_EFFECT", "EFFECT_UNKNOWN"}
        ):
            raise StateConflict("terminal-return projection phase order drifted")
        if action == "DUPLICATE" and prior_phase not in {
            "PREPARED",
            "PRE_SUBMIT_REFUSED",
            "ATTEMPTED",
            "PROVEN_NO_EFFECT",
        }:
            raise StateConflict("terminal-return projection phase order drifted")
    return phases[-1]


def runtime_canonical_terminal_facts(
    runtime: Runtime,
    candidate: CanonicalTerminalWakeCandidate,
    connection: sqlite3.Connection,
) -> DialogueObservationFacts:
    """Reconstruct one exact terminal projection inside the caller's snapshot."""

    from control_plane.executive_delegation_identity import (
        derive_delegation_identity,
    )

    rows = connection.execute(
        """
        SELECT * FROM jobs
        WHERE root_job_id=?
          AND job_id=?
          AND current_attempt_id=?
          AND status=?
          AND orchestration_role IN ('plan','work','review','repair')
        ORDER BY job_id
        LIMIT 2
        """,
        (
            candidate.root_job_id,
            candidate.job_id,
            candidate.attempt_id,
            JobStatus.COMPLETED.value,
        ),
    ).fetchall()
    if len(rows) > 1:
        return DialogueObservationFacts(complete=False)
    if not rows:
        return DialogueObservationFacts()

    job_row = rows[0]
    root_job_id = str(job_row["root_job_id"] or "")
    role = str(job_row["orchestration_role"] or "")
    try:
        source = _dialogue_source_from_root_creation(
            connection,
            root_job_id=root_job_id,
        )
        job = _job_from_row(job_row)
        identity = derive_delegation_identity(job)
        attempt_row, seal, terminal_receipt, role_result_digest = (
            _validated_role_completion_material(
                connection,
                job_row=job_row,
                expected_role=role,
                root_job_id=root_job_id,
            )
        )
        if (
            str(attempt_row["attempt_id"] or "") != candidate.attempt_id
            or str(attempt_row["worker_id"] or "") != candidate.worker_id
        ):
            return DialogueObservationFacts()
        job_result = _strict_canonical_json_loads(
            str(job_row["result_json"]),
            name="canonical terminal Job result",
        )
        attempt_result = _strict_canonical_json_loads(
            str(attempt_row["result_json"]),
            name="canonical terminal Attempt result",
        )
        if job_result != terminal_receipt or attempt_result != terminal_receipt:
            raise StateConflict("terminal result receipt drifted")
        envelope = seal.get("result_envelope")
        envelope_digest = seal.get("result_envelope_digest")
        if (
            not isinstance(envelope, dict)
            or not isinstance(envelope_digest, str)
            or not isinstance(role_result_digest, str)
        ):
            raise StateConflict("terminal result material is incomplete")
        completion = ValidatedRoleCompletion(
            job=job,
            attempt=_attempt_from_row(attempt_row),
            result_envelope=dict(envelope),
            terminal_receipt=dict(terminal_receipt),
            result_digest=envelope_digest,
            role_result_digest=role_result_digest,
            execution_mode=str(
                attempt_row["execution_mode"]
                or AttemptExecutionMode.SEALED_WORKER.value
            ),
            dialogue_source=source,
        )
        terminal_candidate = reduce_terminal_return(material=completion)
        if (
            terminal_candidate.root_job_id != candidate.root_job_id
            or terminal_candidate.job_id != candidate.job_id
            or terminal_candidate.attempt_id != candidate.attempt_id
            or terminal_candidate.worker_id != candidate.worker_id
            or terminal_candidate.dialogue_source != source
            or identity.root_job_id != terminal_candidate.root_job_id
            or identity.operation_key != terminal_candidate.operation_key
            or identity.session_ref != terminal_candidate.session_ref
        ):
            return DialogueObservationFacts()
        command_base, event_material = terminal_return_event_material(
            terminal_candidate
        )
    except (
        RuntimeProofError,
        PersistenceError,
        TerminalReturnError,
        TypeError,
        ValueError,
    ):
        return DialogueObservationFacts(complete=False)

    try:
        phase = inspect_terminal_return_history(
            runtime,
            connection,
            candidate=terminal_candidate,
            material=event_material,
        )
    except (RuntimeProofError, PersistenceError, TypeError, ValueError):
        return DialogueObservationFacts(
            terminal=(
                TerminalObservationFacts(
                    candidate=terminal_candidate,
                    projection_receipt=None,
                    projection_effect="CONFLICT",
                    binding_revalidated=False,
                ),
            )
        )

    receipt: TerminalProjectionReceiptFacts | None = None
    if phase == "APPLIED":
        try:
            applied_command = terminal_return_phase_spec(command_base)[-1][2]
            applied_event = runtime.store.get_event_by_command_id(
                applied_command,
                connection=connection,
            )
            if applied_event is None:
                raise StateConflict("terminal APPLIED receipt disappeared")
            normalized = normalize_terminal_return_projection_receipt(
                applied_event.payload.get("projection_receipt"),
                message_key=terminal_candidate.message_key,
            )
            normalized["duplicate_timestamps"] = tuple(
                normalized["duplicate_timestamps"]
            )
            receipt = TerminalProjectionReceiptFacts(**normalized)
        except (RuntimeProofError, PersistenceError, TypeError, ValueError):
            return DialogueObservationFacts(
                terminal=(
                    TerminalObservationFacts(
                        candidate=terminal_candidate,
                        projection_receipt=None,
                        projection_effect="CONFLICT",
                        binding_revalidated=False,
                    ),
                )
            )

    return DialogueObservationFacts(
        terminal=(
            TerminalObservationFacts(
                candidate=terminal_candidate,
                projection_receipt=receipt,
                projection_effect=phase or "MISSING",
                binding_revalidated=True,
            ),
        )
    )


def read_runtime_canonical_terminal_wake(
    *,
    runtime: Runtime,
    source_root_job_id: str,
    candidate: CanonicalTerminalWakeCandidate,
    connection: sqlite3.Connection | None = None,
) -> CanonicalTerminalWakeRead:
    """Read canonical terminal/Wake truth without constructing a service."""

    return read_canonical_terminal_wake(
        runtime=runtime,
        source_root_job_id=source_root_job_id,
        candidate=candidate,
        facts_provider=runtime_canonical_terminal_facts,
        connection=connection,
    )


def _canonical_read_result(
    state: str,
    reason: str,
    *,
    terminal_state: str = "UNAVAILABLE",
    wake_state: str = "UNAVAILABLE",
    terminal_applied: bool = False,
    terminal: CanonicalTerminalProjection | None = None,
    wake: CanonicalWakeProjection | None = None,
    source_receipt: CanonicalSourceReceipt | None = None,
) -> CanonicalTerminalWakeRead:
    return CanonicalTerminalWakeRead(
        state=state,
        reason=reason,
        terminal_state=terminal_state,
        wake_state=wake_state,
        terminal_applied=terminal_applied,
        terminal=terminal,
        wake=wake,
        source_receipt=source_receipt,
    )


def read_canonical_terminal_wake(
    *,
    runtime: Any,
    source_root_job_id: str,
    candidate: CanonicalTerminalWakeCandidate,
    facts_provider: CanonicalDialogueFactsProvider,
    connection: Any | None = None,
) -> CanonicalTerminalWakeRead:
    """Read one exact canonical terminal projection and correlated Wake.

    Terminal truth is delegated to the existing Executive observation facts
    provider and reducer.  Wake truth is read from the existing persisted Wake
    Event family in one bounded Runtime snapshot.  The result deliberately
    exposes no raw Event payload, Slack text, provider/native handle, mutable
    authority, or write seam.
    """

    if (
        not isinstance(candidate, CanonicalTerminalWakeCandidate)
        or any(
            not _is_route_token(getattr(candidate, name, None))
            for name in ("root_job_id", "job_id", "attempt_id", "worker_id")
        )
        or source_root_job_id != candidate.root_job_id
        or not callable(facts_provider)
        or runtime is None
        or not hasattr(runtime, "store")
    ):
        return _canonical_read_result("UNAVAILABLE", "READ_REQUEST_INVALID")
    if connection is not None:
        if not bool(getattr(connection, "in_transaction", False)):
            return _canonical_read_result(
                "UNAVAILABLE", "READ_CONNECTION_INVALID"
            )
        return _read_canonical_terminal_wake_on_connection(
            runtime=runtime,
            source_root_job_id=source_root_job_id,
            candidate=candidate,
            facts_provider=facts_provider,
            connection=connection,
        )
    try:
        with runtime.store.read() as owned_connection:
            return _read_canonical_terminal_wake_on_connection(
                runtime=runtime,
                source_root_job_id=source_root_job_id,
                candidate=candidate,
                facts_provider=facts_provider,
                connection=owned_connection,
            )
    except Exception:
        return _canonical_read_result(
            "UNAVAILABLE", "CANONICAL_TERMINAL_UNAVAILABLE"
        )


def _read_canonical_terminal_wake_on_connection(
    *,
    runtime: Any,
    source_root_job_id: str,
    candidate: CanonicalTerminalWakeCandidate,
    facts_provider: CanonicalDialogueFactsProvider,
    connection: Any,
) -> CanonicalTerminalWakeRead:
    from control_plane.wake_events import SourceKind, WakeKind
    from control_plane.wake_ledger import (
        ATTEMPT_PHASES,
        LedgerPhase,
        WAKE_AGGREGATE_TYPE,
        assert_causal,
        reconstruct_status,
    )
    from control_plane.wake_persist import WakeLedgerRepository

    try:
        facts = facts_provider(runtime, candidate, connection)
    except Exception:
        return _canonical_read_result(
            "UNAVAILABLE", "CANONICAL_TERMINAL_UNAVAILABLE"
        )
    if not isinstance(facts, DialogueObservationFacts) or not facts.complete:
        return _canonical_read_result(
            "UNAVAILABLE", "CANONICAL_TERMINAL_UNAVAILABLE"
        )
    if facts.active or len(facts.terminal) > 1:
        return _canonical_read_result(
            "CONFLICT",
            "CANONICAL_TERMINAL_CONFLICT",
            terminal_state="CONFLICT",
        )
    if not facts.terminal:
        return _canonical_read_result(
            "ABSENT",
            "CANONICAL_TERMINAL_ABSENT",
            terminal_state="MISSING",
        )
    terminal_facts = facts.terminal[0]
    if terminal_facts.projection_effect == "CONFLICT":
        return _canonical_read_result(
            "CONFLICT",
            "CANONICAL_TERMINAL_CONFLICT",
            terminal_state="CONFLICT",
        )
    if terminal_facts.projection_effect == "EFFECT_UNKNOWN":
        return _canonical_read_result(
            "EFFECT_UNKNOWN",
            "CANONICAL_TERMINAL_EFFECT_UNKNOWN",
            terminal_state="EFFECT_UNKNOWN",
        )
    if terminal_facts.projection_effect in {"MISSING", "PROVEN_NO_EFFECT", "PRE_SUBMIT_REFUSED"}:
        return _canonical_read_result(
            "ABSENT",
            "CANONICAL_TERMINAL_ABSENT",
            terminal_state="MISSING",
        )
    if (
        terminal_facts.projection_effect != "APPLIED"
        or terminal_facts.binding_revalidated is not True
    ):
        return _canonical_read_result(
            "UNAVAILABLE", "CANONICAL_TERMINAL_UNAVAILABLE"
        )
    try:
        material = _terminal_public_material(terminal_facts)
        if material is None:
            raise ValueError("canonical terminal material is invalid")
        terminal_candidate, receipt_reference, source = material
        observed_identity = tuple(
            terminal_candidate[name]
            for name in ("root_job_id", "job_id", "attempt_id", "worker_id")
        )
        requested_identity = (
            candidate.root_job_id,
            candidate.job_id,
            candidate.attempt_id,
            candidate.worker_id,
        )
        if observed_identity != requested_identity:
            return _canonical_read_result(
                "ABSENT",
                "CANDIDATE_NOT_CANONICAL",
                terminal_state="MISSING",
            )
        observation = {
            "candidate": terminal_candidate,
            "projection_receipt": dataclasses.asdict(receipt_reference),
            "projection_receipt_digest": receipt_reference.receipt_digest,
            "projection_effect": "APPLIED",
        }
        observation["evidence_digest"] = hashlib.sha256(
            _canonical_json(observation)
        ).hexdigest()
        terminal = CanonicalTerminalProjection(
            state="APPLIED",
            root_job_id=candidate.root_job_id,
            job_id=candidate.job_id,
            attempt_id=candidate.attempt_id,
            worker_id=candidate.worker_id,
            result_status=terminal_candidate["result_status"],
            terminal_at=terminal_candidate["terminal_at"],
            result_envelope_digest=terminal_candidate[
                "result_envelope_digest"
            ],
            terminal_evidence_digest=terminal_candidate[
                "terminal_evidence_digest"
            ],
            artifact_receipt_digest=terminal_candidate[
                "artifact_receipt_digest"
            ],
            validation_receipt_digest=terminal_candidate[
                "validation_receipt_digest"
            ],
            effective_grant_digest=terminal_candidate[
                "effective_grant_digest"
            ],
            evidence_digest=observation["evidence_digest"],
            projection_receipt_digest=observation[
                "projection_receipt_digest"
            ],
        )
        source_workstream = str(source["work_ref"])
    except (KeyError, TypeError, ValueError):
        return _canonical_read_result(
            "UNAVAILABLE", "CANONICAL_TERMINAL_UNAVAILABLE"
        )

    def source_receipt(
        *,
        wake_state: str,
        wake_identity: Any = None,
        wake_time: str | None = None,
    ) -> CanonicalSourceReceipt:
        source_times = tuple(
            value
            for value in (terminal.terminal_at, wake_time)
            if isinstance(value, str) and value
        )
        observed_at = min(
            source_times,
            key=lambda value: datetime.fromisoformat(
                value.replace("Z", "+00:00")
            ),
        )
        return CanonicalSourceReceipt(
            observed_at=observed_at,
            freshness="SOURCE_EVIDENCE_TIME",
            snapshot_digest=hashlib.sha256(
                _canonical_json(
                    {
                        "terminal": dataclasses.asdict(terminal),
                        "wake_state": wake_state,
                        "wake_identity": wake_identity,
                        "observed_at": observed_at,
                    }
                )
            ).hexdigest(),
        )

    receipt: CanonicalSourceReceipt | None = None
    try:
        repository = WakeLedgerRepository(runtime)
        rows = connection.execute(
            """
            SELECT aggregate_id
            FROM events
            WHERE aggregate_type=?
              AND event_type='WAKE_REQUESTED'
              AND json_extract(payload_json, '$.wake_kind')=?
              AND json_extract(payload_json, '$.source_kind')=?
              AND json_extract(payload_json, '$.root_job_id')=?
              AND json_extract(payload_json, '$.job_id')=?
              AND json_extract(payload_json, '$.attempt_id')=?
              AND json_extract(payload_json, '$.source_workstream')=?
            ORDER BY event_id
            LIMIT 2
            """,
            (
                WAKE_AGGREGATE_TYPE,
                WakeKind.DIALOGUE_TURN_PENDING.value,
                SourceKind.AGENT_DIALOGUE_ATTENTION.value,
                source_root_job_id,
                candidate.job_id,
                candidate.attempt_id,
                source_workstream,
            ),
        ).fetchall()
        aggregate_ids = tuple(dict.fromkeys(str(row["aggregate_id"]) for row in rows))
        if not aggregate_ids:
            receipt = source_receipt(wake_state="ABSENT")
            return _canonical_read_result(
                "ABSENT", "CORRELATED_WAKE_ABSENT",
                terminal_state="APPLIED", wake_state="ABSENT",
                terminal_applied=True, terminal=terminal, source_receipt=receipt,
            )
        if len(aggregate_ids) != 1:
            receipt = source_receipt(
                wake_state="AMBIGUOUS",
                wake_identity=sorted(aggregate_ids),
            )
            return _canonical_read_result(
                "AMBIGUOUS", "MULTIPLE_WAKE_OBLIGATIONS",
                terminal_state="APPLIED", wake_state="AMBIGUOUS",
                terminal_applied=True, terminal=terminal, source_receipt=receipt,
            )
        obligation_id = aggregate_ids[0]
        count_row = connection.execute(
            "SELECT COUNT(*) AS event_count FROM events "
            "WHERE aggregate_type=? AND aggregate_id=?",
            (WAKE_AGGREGATE_TYPE, obligation_id),
        ).fetchone()
        if count_row is None or int(count_row["event_count"]) > CANONICAL_WAKE_EVENT_BUDGET:
            receipt = source_receipt(
                wake_state="OVERFLOW", wake_identity=obligation_id
            )
            return _canonical_read_result(
                "UNAVAILABLE", "WAKE_EVENT_BUDGET_EXCEEDED",
                terminal_state="APPLIED", wake_state="OVERFLOW",
                terminal_applied=True, terminal=terminal, source_receipt=receipt,
            )
        records = repository.list_ledger_records_on_connection(connection, obligation_id)
        assert_causal(records)
        requested = [record for record in records if record.phase is LedgerPhase.WAKE_REQUESTED]
        if len(requested) != 1 or requested[0].obligation is None:
            raise ValueError("Wake request identity is not exact")
        obligation = requested[0].obligation
        if (
            obligation.obligation_id != obligation_id
            or obligation.root_job_id != source_root_job_id
            or obligation.job_id != candidate.job_id
            or obligation.attempt_id != candidate.attempt_id
            or obligation.source_workstream != source_workstream
            or obligation.wake_kind is not WakeKind.DIALOGUE_TURN_PENDING
            or obligation.source_kind is not SourceKind.AGENT_DIALOGUE_ATTENTION
        ):
            raise ValueError("Wake request correlation drifted")
        attempt_records = [record for record in records if record.phase in ATTEMPT_PHASES]
        destination_digest = None
        if attempt_records:
            latest_attempt = max(int(record.attempt_n or 0) for record in attempt_records)
            latest_destinations = {
                record.destination_digest
                for record in attempt_records
                if record.attempt_n == latest_attempt
            }
            if len(latest_destinations) != 1:
                raise ValueError("Wake destination identity is ambiguous")
            destination_digest = latest_destinations.pop()
        wake_status = reconstruct_status(
            obligation_id, records, destination_digest=destination_digest
        ).value
        wake_time = obligation.source_created_at or obligation.emitted_at
        receipt = source_receipt(
            wake_state=wake_status,
            wake_identity=obligation_id,
            wake_time=wake_time,
        )
    except Exception:
        return _canonical_read_result(
            "CONFLICT",
            "WAKE_HISTORY_INVALID",
            terminal_state="APPLIED",
            wake_state="CONFLICT",
            terminal_applied=True,
            terminal=terminal,
            source_receipt=receipt,
        )
    return _canonical_read_result(
        "RESOLVED",
        "CANONICAL_TERMINAL_WAKE_RESOLVED",
        terminal_state="APPLIED",
        wake_state=wake_status,
        terminal_applied=True,
        terminal=terminal,
        wake=CanonicalWakeProjection(
            obligation_id=obligation.obligation_id,
            status=wake_status,
            declared_target_seat=obligation.declared_target_seat,
            source_ref_digest=hashlib.sha256(
                obligation.source_ref.encode("utf-8")
            ).hexdigest(),
            source_observed_at=(
                obligation.source_created_at or obligation.emitted_at
            ),
        ),
        source_receipt=receipt,
    )


__all__ = [
    "ACTIVE_CURRENT_WORKER",
    "CANONICAL_WAKE_EVENT_BUDGET",
    "MAX_REQUEST_BYTES",
    "MAX_RESPONSE_BYTES",
    "RECONCILE_WAKE",
    "REQUEST_SCHEMA",
    "RESOLVE_PARENT",
    "RESPONSE_SCHEMA",
    "SUBMIT_WAKE",
    "WAKE_REQUEST_SCHEMA",
    "WAKE_RESPONSE_SCHEMA",
    "TERMINAL_RESULT",
    "TERMINAL_RETURN_APPLIED_EVENT",
    "TERMINAL_RETURN_ATTEMPTED_EVENT",
    "TERMINAL_RETURN_EFFECT_UNKNOWN_EVENT",
    "TERMINAL_RETURN_PREPARED_EVENT",
    "TERMINAL_RETURN_PRE_SUBMIT_REFUSED_EVENT",
    "TERMINAL_RETURN_PROJECTION_SCHEMA",
    "TERMINAL_RETURN_PROVEN_NO_EFFECT_EVENT",
    "TERMINAL_RETURN_RECEIPT_ACTIONS",
    "ActiveObservationFacts",
    "CanonicalTerminalWakeCandidate",
    "CanonicalTerminalProjection",
    "CanonicalTerminalWakeRead",
    "CanonicalWakeProjection",
    "CanonicalSourceReceipt",
    "DialogueObservationFacts",
    "DialogueObservationProtocolError",
    "DialogueCandidateReference",
    "DialogueWakeRequest",
    "ObservationRequest",
    "PublicRuntimeBindingFacts",
    "TerminalObservationFacts",
    "TerminalProjectionReceiptFacts",
    "TerminalProjectionReceiptReference",
    "parse_observation_request",
    "parse_wake_request",
    "inspect_terminal_return_history",
    "normalize_terminal_return_projection_receipt",
    "reduce_dialogue_observation",
    "read_canonical_terminal_wake",
    "read_runtime_canonical_terminal_wake",
    "response_bytes",
    "runtime_canonical_terminal_facts",
    "terminal_return_event_material",
    "terminal_return_phase_spec",
    "terminal_projection_receipt_reference",
    "validate_terminal_return_event",
    "wake_response_bytes",
]
