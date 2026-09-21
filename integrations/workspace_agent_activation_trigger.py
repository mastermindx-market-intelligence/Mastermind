"""Build one sealed self-returning Workspace Agent trigger package without I/O.

The package joins already-owned contracts only:

* Workspace profile activation freezes the reviewed agent/channel/economic envelope.
* the current DialogueBinding is supplied by the incumbent Executive target owner.
* WorkspaceReturnTicketCodec mints the short-lived opaque candidate return capability.
* build_trigger_plan freezes the provider POST payload and idempotency material.

This module performs no provider trigger, network call, persistence, lifecycle mutation,
target lookup, result acceptance, Wake acknowledgement, publication, or credential read.
The existing Executive operation/event owner must durably bind the returned exact plan
before any effectful trigger transport is invoked.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import re
from collections.abc import Mapping
from typing import Any

from integrations.mastermind_company_mcp.adapter import DialogueBinding
from integrations.workspace_agent_profiles import (
    WorkspaceProfileError,
    activation_binding_digest,
    validate_activation_binding,
)
from integrations.workspace_agent_return import (
    MAX_TICKET_TTL_MS,
    TOOL_NAME,
    WorkspaceReturnError,
    WorkspaceReturnTicketCodec,
    binding_digest,
)
from integrations.workspace_agent_trigger import (
    WorkspaceAgentTriggerPlan,
    build_trigger_plan,
)
from integrations.workspace_agent_api import InvalidObservation


PACKAGE_SCHEMA = "mastermind.workspace_agent_self_returning_trigger.v1"
PROMPT_SCHEMA = "mastermind.workspace_agent_supervisory_trigger_input.v1"
MAX_TASK_CHARS = 12_000
_EVENT_REF = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._:-]{7,127}\Z", re.ASCII)
_OPERATION_KEY = re.compile(r"\A[a-z0-9][a-z0-9-]{2,95}\Z", re.ASCII)
_SHA256 = re.compile(r"\A[0-9a-f]{64}\Z", re.ASCII)


class WorkspaceActivationTriggerError(RuntimeError):
    """Closed pre-effect refusal; caller/provider content never crosses it."""

    _CODES = frozenset(
        {
            "INVALID_EVENT",
            "INVALID_OPERATION",
            "INVALID_TASK_INPUT",
            "ACTIVATION_REFUSED",
            "CURRENT_BINDING_REFUSED",
            "EVENT_OUTSIDE_ACTIVATION",
            "RETURN_WINDOW_EXPIRED",
            "RETURN_REF_REFUSED",
            "TRIGGER_PLAN_REFUSED",
        }
    )

    def __init__(self, code: str) -> None:
        if code not in self._CODES:
            raise ValueError("unknown Workspace activation-trigger error")
        self.code = code
        super().__init__(code)


@dataclasses.dataclass(frozen=True, slots=True)
class WorkspaceSelfReturningTriggerPackage:
    """Safe-to-log manifest plus the opaque trigger plan.

    The trigger plan itself excludes its request body from repr. The raw return_ref
    exists only inside that body; this manifest exposes its digest and ticket identity.
    """

    schema: str
    profile_id: str
    profile_revision: str
    agent_version_ref: str
    activation_digest: str
    event_digest: str
    binding_digest: str
    ticket_id: str
    return_ref_sha256: str
    conversation_key: str
    event_issued_at_ms: int
    ticket_expires_at_ms: int
    trigger_plan: WorkspaceAgentTriggerPlan


def _refuse(code: str) -> None:
    raise WorkspaceActivationTriggerError(code)


def _canonical_json(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    except (TypeError, ValueError, UnicodeError, RecursionError):
        _refuse("INVALID_TASK_INPUT")
    raise AssertionError("unreachable")


def _event_ref(value: object) -> str:
    if type(value) is not str or _EVENT_REF.fullmatch(value) is None:
        _refuse("INVALID_EVENT")
    return value


def _operation_key(value: object) -> str:
    if type(value) is not str or _OPERATION_KEY.fullmatch(value) is None:
        _refuse("INVALID_OPERATION")
    return value


def _task_input(value: object) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or len(value) > MAX_TASK_CHARS
        or "\x00" in value
        or any(ord(char) < 32 and char not in {"\n", "\t"} for char in value)
    ):
        _refuse("INVALID_TASK_INPUT")
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeError:
        _refuse("INVALID_TASK_INPUT")
    return value


def _timestamp(value: object, *, code: str) -> int:
    if type(value) is not int or isinstance(value, bool) or value < 0:
        _refuse(code)
    return value


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _ticket_id(
    *,
    event_digest: str,
    activation_digest: str,
    current_binding_digest: str,
) -> str:
    material = {
        "schema": PACKAGE_SCHEMA,
        "event_digest": event_digest,
        "activation_digest": activation_digest,
        "binding_digest": current_binding_digest,
    }
    return "wr-" + _digest(material)[:32]


def _conversation_key(
    *,
    operation_key: str,
    channel_id: str,
    profile_digest: str,
) -> str:
    return "mmx-wa-" + _digest(
        {
            "schema": PROMPT_SCHEMA,
            "operation_key": operation_key,
            "channel_id": channel_id,
            "profile_digest": profile_digest,
        }
    )[:32]


def build_self_returning_trigger_package(
    *,
    catalog: Mapping[str, Any],
    activation_binding: Mapping[str, Any],
    expected_return_subject_digest: str,
    current_binding: DialogueBinding,
    operation_key: str,
    event_ref: str,
    event_issued_at_ms: int,
    now_ms: int,
    task_input: str,
    ticket_codec: WorkspaceReturnTicketCodec,
) -> WorkspaceSelfReturningTriggerPackage:
    """Freeze a complete self-returning trigger payload without crossing an effect boundary."""

    operation = _operation_key(operation_key)
    event = _event_ref(event_ref)
    issued = _timestamp(event_issued_at_ms, code="INVALID_EVENT")
    now = _timestamp(now_ms, code="INVALID_EVENT")
    if issued > now:
        _refuse("INVALID_EVENT")
    task = _task_input(task_input)
    if not isinstance(current_binding, DialogueBinding):
        _refuse("CURRENT_BINDING_REFUSED")
    if current_binding.operation_key != operation:
        _refuse("CURRENT_BINDING_REFUSED")
    if not isinstance(ticket_codec, WorkspaceReturnTicketCodec):
        _refuse("RETURN_REF_REFUSED")

    try:
        activation = validate_activation_binding(
            activation_binding,
            catalog=catalog,
            now_ms=now,
            expected_return_subject_digest=expected_return_subject_digest,
        )
        activation_digest = activation_binding_digest(
            activation,
            catalog=catalog,
            now_ms=now,
            expected_return_subject_digest=expected_return_subject_digest,
        )
    except WorkspaceProfileError:
        _refuse("ACTIVATION_REFUSED")
    except Exception:
        _refuse("ACTIVATION_REFUSED")

    envelope = activation["economic_envelope"]
    if issued < envelope["issued_at_ms"]:
        _refuse("EVENT_OUTSIDE_ACTIVATION")
    expires = min(issued + MAX_TICKET_TTL_MS, envelope["expires_at_ms"])
    if expires <= issued or now > expires:
        _refuse("RETURN_WINDOW_EXPIRED")

    try:
        current_digest = binding_digest(current_binding)
    except WorkspaceReturnError:
        _refuse("CURRENT_BINDING_REFUSED")
    except Exception:
        _refuse("CURRENT_BINDING_REFUSED")

    event_digest = hashlib.sha256(event.encode("ascii")).hexdigest()
    ticket_id = _ticket_id(
        event_digest=event_digest,
        activation_digest=activation_digest,
        current_binding_digest=current_digest,
    )
    try:
        return_ref = ticket_codec.mint(
            binding=current_binding,
            ticket_id=ticket_id,
            issued_at_ms=issued,
            expires_at_ms=expires,
        )
    except WorkspaceReturnError:
        _refuse("RETURN_REF_REFUSED")
    except Exception:
        _refuse("RETURN_REF_REFUSED")

    conversation_key = _conversation_key(
        operation_key=operation,
        channel_id=activation["provider_channel_ref"],
        profile_digest=activation["profile_digest"],
    )
    prompt = {
        "schema": PROMPT_SCHEMA,
        "activation_digest": activation_digest,
        "event_digest": event_digest,
        "profile": {
            "profile_id": activation["profile_id"],
            "profile_revision": activation["profile_revision"],
            "profile_digest": activation["profile_digest"],
            "agent_version_ref": activation["agent_version_ref"],
        },
        "task_input": task,
        "return_contract": {
            "tool": TOOL_NAME,
            "return_ref": return_ref,
            "candidate_only": True,
        },
    }
    try:
        plan = build_trigger_plan(
            channel_id=activation["provider_channel_ref"],
            operation_key=operation,
            input_text=_canonical_json(prompt).decode("ascii"),
            conversation_key=conversation_key,
        )
    except InvalidObservation:
        _refuse("TRIGGER_PLAN_REFUSED")
    except Exception:
        _refuse("TRIGGER_PLAN_REFUSED")

    return WorkspaceSelfReturningTriggerPackage(
        schema=PACKAGE_SCHEMA,
        profile_id=activation["profile_id"],
        profile_revision=activation["profile_revision"],
        agent_version_ref=activation["agent_version_ref"],
        activation_digest=activation_digest,
        event_digest=event_digest,
        binding_digest=current_digest,
        ticket_id=ticket_id,
        return_ref_sha256=hashlib.sha256(return_ref.encode("ascii")).hexdigest(),
        conversation_key=conversation_key,
        event_issued_at_ms=issued,
        ticket_expires_at_ms=expires,
        trigger_plan=plan,
    )


__all__ = [
    "MAX_TASK_CHARS",
    "PACKAGE_SCHEMA",
    "PROMPT_SCHEMA",
    "WorkspaceActivationTriggerError",
    "WorkspaceSelfReturningTriggerPackage",
    "build_self_returning_trigger_package",
]
