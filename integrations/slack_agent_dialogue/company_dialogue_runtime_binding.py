"""Pure current-worker resolver for the bounded Company Dialogue gateway.

The resolver consumes trusted snapshots supplied by the existing Executive,
RuntimeBinding, capability-policy, and Agent Dialogue owners.  It derives one
immutable ``DialogueBinding`` or a closed refusal.  It owns no persistence,
transport, process, credential, placement, or lifecycle state.
"""
from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
import re
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping

from control_plane.executive_delegation_identity import ExecutiveDelegationIdentity
from control_plane.executive_runtime import AttemptStatus, WorkerStatus
from control_plane.session_targets import RuntimeBinding
from integrations.mastermind_company_mcp.adapter import DialogueBinding
from integrations.mastermind_company_mcp.schemas import (
    SERVER_IDENTITY,
    SERVER_VERSION,
    TOOL_SCHEMA_DIGEST,
)
from integrations.slack_agent_dialogue.contract import DialogueContractError
from integrations.slack_agent_dialogue.contract_v2 import validate_parent_v2


BINDING_SCHEMA = "mastermind.company_dialogue_runtime_binding.v1"

_ALLOWED_MESSAGE_TYPES = (
    "ACK",
    "BLOCKED",
    "DECISION_REQUEST",
    "PROGRESS",
    "RESULT",
)
_ACTIVE_ATTEMPT_STATUSES = frozenset(
    {
        AttemptStatus.CLAIMED,
        AttemptStatus.RUNNING,
        AttemptStatus.CHECKPOINTED,
    }
)
_THREAD_TS_RE = re.compile(r"\A[1-9][0-9]{9,15}\.[0-9]{6}\Z")
_JOB_ID_RE = re.compile(r"\AJOB-[1-9][0-9]*\Z")
_ATTEMPT_ID_RE = re.compile(r"\AATT-[1-9][0-9]*\Z")
_WORKER_ID_RE = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")
_PROFILE_ID_RE = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_SHA256_RE = re.compile(r"\A[0-9a-f]{64}\Z")
_PUBLIC_TOKEN_RE = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._:-]{0,255}\Z")


class BindingState(str, Enum):
    RESOLVED = "RESOLVED"
    REFUSED = "REFUSED"
    UNKNOWN = "UNKNOWN"


class BindingReason(str, Enum):
    EXACT_CURRENT_WORKER = "EXACT_CURRENT_WORKER"
    CURRENT_RUNTIME_UNAVAILABLE = "CURRENT_RUNTIME_UNAVAILABLE"
    DIALOGUE_PARENT_INVALID = "DIALOGUE_PARENT_INVALID"
    DIALOGUE_IDENTITY_MISMATCH = "DIALOGUE_IDENTITY_MISMATCH"
    DIALOGUE_PARENT_STALE = "DIALOGUE_PARENT_STALE"
    CURRENT_JOB_MISMATCH = "CURRENT_JOB_MISMATCH"
    CURRENT_ATTEMPT_INACTIVE = "CURRENT_ATTEMPT_INACTIVE"
    CURRENT_WORKER_INACTIVE = "CURRENT_WORKER_INACTIVE"
    CAPABILITY_PROFILE_MISMATCH = "CAPABILITY_PROFILE_MISMATCH"
    CAPABILITY_NOT_ATTESTED = "CAPABILITY_NOT_ATTESTED"
    ACTOR_ATTEMPT_MISMATCH = "ACTOR_ATTEMPT_MISMATCH"
    ACTOR_WORKER_MISMATCH = "ACTOR_WORKER_MISMATCH"
    ACTOR_PROFILE_MISMATCH = "ACTOR_PROFILE_MISMATCH"
    ACTOR_RUNTIME_BINDING_MISMATCH = "ACTOR_RUNTIME_BINDING_MISMATCH"
    THREAD_INVALID = "THREAD_INVALID"


@dataclasses.dataclass(frozen=True)
class CurrentWorkerDialogueSnapshot:
    root_job_id: str
    job_id: str
    attempt_id: str
    worker_id: str
    attempt_status: AttemptStatus
    worker_status: WorkerStatus
    execution_profile_id: str
    execution_profile_digest: str
    capability_policy_digest: str
    runtime_binding: RuntimeBinding
    parent_fingerprint: str
    company_dialogue_server_identity: str
    company_dialogue_server_version: str
    company_dialogue_tool_schema_digest: str
    company_dialogue_attested: bool


@dataclasses.dataclass(frozen=True)
class WorkerDialogueCaller:
    attempt_id: str
    worker_id: str
    execution_profile_id: str
    execution_profile_digest: str
    capability_policy_digest: str
    runtime_binding: RuntimeBinding


@dataclasses.dataclass(frozen=True)
class CompanyDialogueBindingResolution:
    schema: str
    state: BindingState
    reason: BindingReason
    binding: DialogueBinding | None
    evidence_digest: str


class CompanyDialogueBindingError(RuntimeError):
    """A caller is not the exact current worker for the dialogue context."""

    def __init__(self, resolution: CompanyDialogueBindingResolution) -> None:
        self.resolution = resolution
        super().__init__(
            "company dialogue binding refused: "
            f"{resolution.state.value}/{resolution.reason.value}"
        )


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _digest(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _frozen_mapping(value: Mapping[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType(copy.deepcopy(dict(value)))


def _runtime_public(binding: RuntimeBinding) -> dict[str, Any] | None:
    if not isinstance(binding, RuntimeBinding):
        return None
    if (
        not isinstance(binding.session_alias, str)
        or _PUBLIC_TOKEN_RE.fullmatch(binding.session_alias) is None
        or not isinstance(binding.binding_id, str)
        or _PUBLIC_TOKEN_RE.fullmatch(binding.binding_id) is None
        or type(binding.binding_generation) is not int
        or binding.binding_generation < 1
        or not isinstance(binding.reasoning_surface, str)
        or _PUBLIC_TOKEN_RE.fullmatch(binding.reasoning_surface) is None
    ):
        return None
    return {
        "session_alias": binding.session_alias,
        "binding_id": binding.binding_id,
        "binding_generation": binding.binding_generation,
        "reasoning_surface": binding.reasoning_surface,
    }


def _valid_identity(identity: ExecutiveDelegationIdentity) -> bool:
    return bool(
        isinstance(identity, ExecutiveDelegationIdentity)
        and isinstance(identity.job_id, str)
        and _JOB_ID_RE.fullmatch(identity.job_id)
        and isinstance(identity.root_job_id, str)
        and _JOB_ID_RE.fullmatch(identity.root_job_id)
        and isinstance(identity.operation_key, str)
        and _PUBLIC_TOKEN_RE.fullmatch(identity.operation_key)
        and isinstance(identity.session_ref, str)
        and _PUBLIC_TOKEN_RE.fullmatch(identity.session_ref)
    )


def _valid_current_shape(current: CurrentWorkerDialogueSnapshot) -> bool:
    return bool(
        isinstance(current, CurrentWorkerDialogueSnapshot)
        and isinstance(current.root_job_id, str)
        and _JOB_ID_RE.fullmatch(current.root_job_id)
        and isinstance(current.job_id, str)
        and _JOB_ID_RE.fullmatch(current.job_id)
        and isinstance(current.attempt_id, str)
        and _ATTEMPT_ID_RE.fullmatch(current.attempt_id)
        and isinstance(current.worker_id, str)
        and _WORKER_ID_RE.fullmatch(current.worker_id)
        and isinstance(current.execution_profile_id, str)
        and _PROFILE_ID_RE.fullmatch(current.execution_profile_id)
        and isinstance(current.execution_profile_digest, str)
        and _SHA256_RE.fullmatch(current.execution_profile_digest)
        and isinstance(current.capability_policy_digest, str)
        and _SHA256_RE.fullmatch(current.capability_policy_digest)
        and isinstance(current.parent_fingerprint, str)
        and _SHA256_RE.fullmatch(current.parent_fingerprint)
        and _runtime_public(current.runtime_binding) is not None
    )


def _valid_actor_shape(actor: WorkerDialogueCaller) -> bool:
    return bool(
        isinstance(actor, WorkerDialogueCaller)
        and isinstance(actor.attempt_id, str)
        and _ATTEMPT_ID_RE.fullmatch(actor.attempt_id)
        and isinstance(actor.worker_id, str)
        and _WORKER_ID_RE.fullmatch(actor.worker_id)
        and isinstance(actor.execution_profile_id, str)
        and _PROFILE_ID_RE.fullmatch(actor.execution_profile_id)
        and isinstance(actor.execution_profile_digest, str)
        and _SHA256_RE.fullmatch(actor.execution_profile_digest)
        and isinstance(actor.capability_policy_digest, str)
        and _SHA256_RE.fullmatch(actor.capability_policy_digest)
        and _runtime_public(actor.runtime_binding) is not None
    )


def _result(
    state: BindingState,
    reason: BindingReason,
    *,
    binding: DialogueBinding | None = None,
    evidence: Mapping[str, Any] | None = None,
) -> CompanyDialogueBindingResolution:
    document: dict[str, Any] = {
        "schema": BINDING_SCHEMA,
        "state": state.value,
        "reason": reason.value,
    }
    if evidence:
        document["evidence"] = copy.deepcopy(dict(evidence))
    return CompanyDialogueBindingResolution(
        schema=BINDING_SCHEMA,
        state=state,
        reason=reason,
        binding=binding,
        evidence_digest=_digest(document),
    )


def resolve_company_dialogue_binding(
    *,
    delegation_identity: ExecutiveDelegationIdentity,
    dialogue_parent: Mapping[str, Any],
    thread_ts: str,
    current: CurrentWorkerDialogueSnapshot | None,
    actor: WorkerDialogueCaller,
) -> CompanyDialogueBindingResolution:
    """Resolve one exact current worker to the existing dialogue parent."""

    if current is None:
        return _result(
            BindingState.UNKNOWN,
            BindingReason.CURRENT_RUNTIME_UNAVAILABLE,
        )
    if not isinstance(thread_ts, str) or _THREAD_TS_RE.fullmatch(thread_ts) is None:
        return _result(BindingState.REFUSED, BindingReason.THREAD_INVALID)
    try:
        parent = validate_parent_v2(copy.deepcopy(dict(dialogue_parent)))
    except (DialogueContractError, TypeError, ValueError):
        return _result(BindingState.REFUSED, BindingReason.DIALOGUE_PARENT_INVALID)

    if not _valid_identity(delegation_identity) or not _valid_current_shape(current):
        return _result(BindingState.REFUSED, BindingReason.CURRENT_JOB_MISMATCH)
    if not _valid_actor_shape(actor):
        return _result(BindingState.REFUSED, BindingReason.ACTOR_PROFILE_MISMATCH)

    if (
        current.root_job_id != delegation_identity.root_job_id
        or current.job_id != delegation_identity.job_id
    ):
        return _result(BindingState.REFUSED, BindingReason.CURRENT_JOB_MISMATCH)
    if (
        parent["operation_key"] != delegation_identity.operation_key
        or parent["session_ref"] != delegation_identity.session_ref
    ):
        return _result(BindingState.REFUSED, BindingReason.DIALOGUE_IDENTITY_MISMATCH)
    if current.parent_fingerprint != parent["fingerprint"]:
        return _result(BindingState.REFUSED, BindingReason.DIALOGUE_PARENT_STALE)
    if current.attempt_status not in _ACTIVE_ATTEMPT_STATUSES:
        return _result(BindingState.REFUSED, BindingReason.CURRENT_ATTEMPT_INACTIVE)
    if current.worker_status is not WorkerStatus.BUSY:
        return _result(BindingState.REFUSED, BindingReason.CURRENT_WORKER_INACTIVE)

    if (
        current.company_dialogue_attested is not True
        or current.company_dialogue_server_identity != SERVER_IDENTITY
        or current.company_dialogue_server_version != SERVER_VERSION
        or current.company_dialogue_tool_schema_digest != TOOL_SCHEMA_DIGEST
    ):
        return _result(BindingState.REFUSED, BindingReason.CAPABILITY_NOT_ATTESTED)

    if actor.attempt_id != current.attempt_id:
        return _result(BindingState.REFUSED, BindingReason.ACTOR_ATTEMPT_MISMATCH)
    if actor.worker_id != current.worker_id:
        return _result(BindingState.REFUSED, BindingReason.ACTOR_WORKER_MISMATCH)
    if (
        actor.execution_profile_id != current.execution_profile_id
        or actor.execution_profile_digest != current.execution_profile_digest
        or actor.capability_policy_digest != current.capability_policy_digest
    ):
        return _result(BindingState.REFUSED, BindingReason.ACTOR_PROFILE_MISMATCH)
    if actor.runtime_binding != current.runtime_binding:
        return _result(
            BindingState.REFUSED,
            BindingReason.ACTOR_RUNTIME_BINDING_MISMATCH,
        )

    actor_ref = {
        "kind": "worker_attempt",
        "job_id": current.job_id,
        "attempt_id": current.attempt_id,
        "worker_id": current.worker_id,
    }
    applies_to = {
        "kind": "executive_attempt",
        "job_id": current.job_id,
        "attempt_id": current.attempt_id,
        "worker_id": current.worker_id,
    }
    binding = DialogueBinding(
        actor_ref=_frozen_mapping(actor_ref),
        work_ref=parent["work_ref"],
        commission_ref=_frozen_mapping(parent["commission_ref"]),
        session_ref=parent["session_ref"],
        operation_key=parent["operation_key"],
        watch_mode=parent["watch_mode"],
        applies_to=_frozen_mapping(applies_to),
        thread_ts=thread_ts,
        allowed_message_types=_ALLOWED_MESSAGE_TYPES,
        reply_to_message_key=None,
    )
    runtime = _runtime_public(current.runtime_binding)
    assert runtime is not None
    evidence = {
        "root_job_id": current.root_job_id,
        "job_id": current.job_id,
        "attempt_id": current.attempt_id,
        "worker_id": current.worker_id,
        "operation_key": parent["operation_key"],
        "session_ref": parent["session_ref"],
        "parent_fingerprint": parent["fingerprint"],
        "thread_ts": thread_ts,
        "execution_profile_id": current.execution_profile_id,
        "execution_profile_digest": current.execution_profile_digest,
        "capability_policy_digest": current.capability_policy_digest,
        "runtime_binding": runtime,
        "company_dialogue_server_identity": current.company_dialogue_server_identity,
        "company_dialogue_server_version": current.company_dialogue_server_version,
        "company_dialogue_tool_schema_digest": current.company_dialogue_tool_schema_digest,
    }
    return _result(
        BindingState.RESOLVED,
        BindingReason.EXACT_CURRENT_WORKER,
        binding=binding,
        evidence=evidence,
    )


def require_company_dialogue_binding(
    *,
    delegation_identity: ExecutiveDelegationIdentity,
    dialogue_parent: Mapping[str, Any],
    thread_ts: str,
    current: CurrentWorkerDialogueSnapshot | None,
    actor: WorkerDialogueCaller,
) -> DialogueBinding:
    """Re-resolve current facts and return only an exact current binding."""

    resolution = resolve_company_dialogue_binding(
        delegation_identity=delegation_identity,
        dialogue_parent=dialogue_parent,
        thread_ts=thread_ts,
        current=current,
        actor=actor,
    )
    if resolution.state is not BindingState.RESOLVED or resolution.binding is None:
        raise CompanyDialogueBindingError(resolution)
    return resolution.binding
