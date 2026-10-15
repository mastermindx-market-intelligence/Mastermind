"""Read-only Relay source adapter for R2 principal composition.

One bounded read of the exact canonical parent and thread named by an already
minted physical source.  The trusted host supplies the dialogue context derived
from the canonical Runtime source and an authenticated principal; neither those
labels nor this module authenticate or authorize a caller, assert unresolved
decision semantics or the current attempt, transmit, select another thread,
create a parent, or mint authority.  Those belong to the parent host and the
existing Runtime fences.

The adapter reuses the existing closed ``status``, ``read_bound_parent`` and
``read_thread`` service operations on one socket, one attempt each, with no
second attempt and no alternate carrier path.  Every refusal is one fixed
non-sensitive code; no service, transport, or caller detail is carried.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from control_plane.dialogue_source_resolution import PhysicalDialogueSourceIdentity
from integrations.slack_agent_dialogue.contract_v2 import (
    DialogueContractError,
    validate_message_v2,
    validate_parent_v2,
)
from integrations.slack_agent_dialogue.engine import ReadMessage, ThreadRead
from integrations.slack_agent_dialogue.engine_v2 import DialogueContextV2
from integrations.slack_agent_dialogue.service import (
    CONTROL_VERSION_V2,
    RELAY_PARENT_ATTESTATION,
    call_service,
)

PRINCIPAL_SOURCE_ERROR_CODE = "PRINCIPAL_SOURCE_UNAVAILABLE"
_STATUS_SCHEMA_V2 = "mastermind.agent_dialogue_status.v2"
_PARENT_BOUND_KEYS = {"attestation", "thread_ts", "parent"}
_THREAD_KEYS = {
    "thread_ts",
    "messages",
    "historical_messages",
    "ineligible_count",
    "mutated_count",
}
_READ_ENTRY_KEYS = {"message", "primary_ts", "duplicate_timestamps"}
_MESSAGE_PARENT_FIELDS = ("work_ref", "commission_ref", "session_ref")
_PARENT_IDENTITY_FIELDS = (
    "work_ref",
    "commission_ref",
    "session_ref",
    "operation_key",
    "watch_mode",
)
_TS_RE = re.compile(r"\A[0-9]{10,16}\.[0-9]{6}\Z")
_MAX_THREAD_ENTRIES = 256


class PrincipalSourceError(RuntimeError):
    """One fixed non-sensitive refusal code; no underlying detail is carried."""

    def __init__(self) -> None:
        super().__init__(PRINCIPAL_SOURCE_ERROR_CODE)
        self.code = PRINCIPAL_SOURCE_ERROR_CODE


@dataclass(frozen=True)
class PrincipalSourceRead:
    """Frozen canonical parent, thread, and exact predecessor for one source.

    ``predecessor`` is the single message carrying the physical source's exact
    predecessor key and fingerprint; it is never the newest message by choice.
    """

    thread_ts: str
    parent: Mapping[str, Any]
    thread: ThreadRead
    predecessor: ReadMessage


def _frozen(value: Any) -> Any:
    """Return one detached, deeply read-only snapshot of validated wire state."""

    if isinstance(value, Mapping):
        return MappingProxyType({key: _frozen(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_frozen(item) for item in value)
    return value


def _identity(value: Mapping[str, Any]) -> tuple[Any, ...]:
    return tuple(value[field] for field in _PARENT_IDENTITY_FIELDS)


def _decode_thread(
    result: Any,
    *,
    thread_ts: str,
    parent: Mapping[str, Any],
) -> ThreadRead:
    """Decode the closed ThreadRead wire shape against the canonical parent."""

    if (
        type(result) is not dict
        or set(result) != _THREAD_KEYS
        or result["thread_ts"] != thread_ts
        or result["historical_messages"] != []
        or type(result["ineligible_count"]) is not int
        or result["ineligible_count"] < 0
        or type(result["mutated_count"]) is not int
        # Created-text reconstruction is useful for reconciliation, but is not
        # an unchanged source for a new principal disposition. Match the
        # existing reply owners: any mutation evidence closes this read.
        or result["mutated_count"] != 0
        or not isinstance(result["messages"], list)
        or len(result["messages"]) > _MAX_THREAD_ENTRIES
    ):
        raise PrincipalSourceError()
    messages: list[ReadMessage] = []
    for entry in result["messages"]:
        if (
            type(entry) is not dict
            or set(entry) != _READ_ENTRY_KEYS
            or type(entry["primary_ts"]) is not str
            or _TS_RE.fullmatch(entry["primary_ts"]) is None
            or not isinstance(entry["duplicate_timestamps"], list)
            or any(
                type(stamp) is not str or _TS_RE.fullmatch(stamp) is None
                for stamp in entry["duplicate_timestamps"]
            )
            or len(set(entry["duplicate_timestamps"])) != len(entry["duplicate_timestamps"])
            or thread_ts in entry["duplicate_timestamps"]
        ):
            raise PrincipalSourceError()
        try:
            message = validate_message_v2(entry["message"])
        except (DialogueContractError, TypeError, ValueError):
            raise PrincipalSourceError() from None
        if any(
            message[field] != parent[field] for field in _MESSAGE_PARENT_FIELDS
        ):
            raise PrincipalSourceError()
        # Physical duplicate timestamps survive only inside one semantic
        # message entry; distinct message keys are never merged here.
        messages.append(
            ReadMessage(
                message=_frozen(message),
                primary_ts=entry["primary_ts"],
                duplicate_timestamps=tuple(entry["duplicate_timestamps"]),
            )
        )
    return ThreadRead(
        thread_ts=thread_ts,
        messages=tuple(messages),
        historical_messages=(),
        ineligible_count=result["ineligible_count"],
        mutated_count=result["mutated_count"],
    )


def _exact_predecessor(
    thread: ThreadRead,
    *,
    physical_source: PhysicalDialogueSourceIdentity,
) -> ReadMessage:
    """Select only the exact physical predecessor key and fingerprint."""

    key_matches = [
        item
        for item in thread.messages
        if item.message["message_key"] == physical_source.predecessor_message_key
    ]
    fingerprint_matches = [
        item
        for item in thread.messages
        if item.message["fingerprint"]
        == physical_source.predecessor_message_fingerprint
    ]
    if (
        len(key_matches) != 1
        or len(fingerprint_matches) != 1
        or key_matches[0] is not fingerprint_matches[0]
    ):
        raise PrincipalSourceError()
    return key_matches[0]


async def _read(
    *,
    socket_path: Path,
    context: DialogueContextV2,
    physical_source: PhysicalDialogueSourceIdentity,
    service_call,
) -> PrincipalSourceRead:
    if isinstance(socket_path, Path):
        path = socket_path
    elif isinstance(socket_path, str):
        path = Path(socket_path)
    else:
        raise PrincipalSourceError()
    if (
        not path.is_absolute()
        or type(context) is not DialogueContextV2
        or type(physical_source) is not PhysicalDialogueSourceIdentity
        or not callable(service_call)
    ):
        raise PrincipalSourceError()
    normalized = context.normalized()
    if normalized["operation_key"] != physical_source.operation_key:
        raise PrincipalSourceError()

    async def request(operation: str, args: Mapping[str, Any]) -> dict[str, Any]:
        response = await service_call(
            path,
            {
                "version": CONTROL_VERSION_V2,
                "operation": operation,
                "args": dict(args),
            },
        )
        if (
            not isinstance(response, dict)
            or response.get("ok") is not True
            or not isinstance(response.get("result"), dict)
        ):
            raise PrincipalSourceError()
        return response["result"]

    status = await request("status", {})
    if (
        status.get("schema") != _STATUS_SCHEMA_V2
        or status.get("workspace_id") != physical_source.workspace_id
        or status.get("channel_id") != physical_source.channel_id
    ):
        raise PrincipalSourceError()

    bound = await request(
        "read_bound_parent",
        {"context": normalized, "thread_ts": physical_source.thread_ts},
    )
    if (
        type(bound) is not dict
        or set(bound) != _PARENT_BOUND_KEYS
        or bound["attestation"] != RELAY_PARENT_ATTESTATION
        or bound["thread_ts"] != physical_source.thread_ts
    ):
        raise PrincipalSourceError()
    try:
        parent = validate_parent_v2(bound["parent"])
    except (DialogueContractError, TypeError, ValueError):
        raise PrincipalSourceError() from None
    if (
        parent["fingerprint"] != physical_source.parent_fingerprint
        or parent["operation_key"] != physical_source.operation_key
        or _identity(parent) != _identity(normalized)
    ):
        raise PrincipalSourceError()

    thread_read = await request(
        "read_thread",
        {"context": normalized, "thread_ts": physical_source.thread_ts},
    )
    thread = _decode_thread(
        thread_read,
        thread_ts=physical_source.thread_ts,
        parent=parent,
    )
    return PrincipalSourceRead(
        thread_ts=physical_source.thread_ts,
        parent=_frozen(parent),
        thread=thread,
        predecessor=_exact_predecessor(thread, physical_source=physical_source),
    )


async def read_principal_source(
    *,
    socket_path: Path,
    context: DialogueContextV2,
    physical_source: PhysicalDialogueSourceIdentity,
    service_call=call_service,
) -> PrincipalSourceRead:
    """Read one exact canonical Relay source for an already-minted physical id.

    The trusted host owns caller authentication, principal authorization, and
    every unresolved decision semantic; this read returns canonical evidence
    only and grants nothing.
    """

    try:
        return await _read(
            socket_path=socket_path,
            context=context,
            physical_source=physical_source,
            service_call=service_call,
        )
    except PrincipalSourceError:
        raise
    except Exception:
        raise PrincipalSourceError() from None


__all__ = [
    "PRINCIPAL_SOURCE_ERROR_CODE",
    "PrincipalSourceError",
    "PrincipalSourceRead",
    "read_principal_source",
]
