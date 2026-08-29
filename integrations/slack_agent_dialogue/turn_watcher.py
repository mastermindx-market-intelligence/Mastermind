"""Pure deterministic classification of accepted Agent Dialogue V2 turns."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Sequence

from integrations.slack_agent_dialogue.contract import DialogueContractError
from integrations.slack_agent_dialogue.contract_v2 import (
    MESSAGE_SCHEMA_V2,
    PARENT_SCHEMA_V2,
    TURN_WATCH_MODE_V1,
    validate_message_v2,
    validate_parent_v2,
)

ATTENTION_SCHEMA = "mastermind.agent_dialogue_attention.v1"
ATTENTION_SOURCE_KIND = "agent_dialogue_attention"
ATTENTION_WAKE_KIND = "dialogue_turn_pending"


class TurnAction(str, Enum):
    """Closed result vocabulary for one accepted semantic dialogue turn."""

    NO_ACTION = "NO_ACTION"
    WAKE_CEO = "WAKE_CEO"
    WAKE_COO = "WAKE_COO"
    WAKE_COO_TERMINAL = "WAKE_COO_TERMINAL"
    TERMINAL = "TERMINAL"
    REFUSE = "REFUSE"


@dataclass(frozen=True)
class TurnRoutingFacts:
    """Trusted, caller-derived correlation and target-binding facts."""

    root_job_id: str | None
    routing_workstream: str | None
    source_workstream: str | None
    ceo_target_bound: bool
    coo_target_bound: bool


@dataclass(frozen=True)
class AgentDialogueAttention:
    """Derived, non-persisted source fact for a later adapter."""

    schema: str
    source_kind: str
    source_ref: str
    source_dialogue_schema: str
    message_key: str
    message_fingerprint: str
    commission_fingerprint: str
    operation_key: str
    target_seat: str
    attention_kind: str
    root_job_id: str | None
    routing_workstream: str | None
    source_workstream: str | None
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            self.schema != ATTENTION_SCHEMA
            or self.source_kind != ATTENTION_SOURCE_KIND
            or self.source_dialogue_schema
            not in {MESSAGE_SCHEMA_V2, PARENT_SCHEMA_V2}
            or self.target_seat not in {"ceo", "coo"}
            or self.attention_kind != ATTENTION_WAKE_KIND
        ):
            raise ValueError("invalid agent dialogue attention")


@dataclass(frozen=True)
class TurnDecision:
    """One complete stateless turn-classification result."""

    action: TurnAction
    attention: AgentDialogueAttention | None
    reason: str
    refusal_code: str | None


def _refuse(code: str) -> TurnDecision:
    return TurnDecision(
        action=TurnAction.REFUSE,
        attention=None,
        reason="DIALOGUE_REFUSED",
        refusal_code=code,
    )


def _no_action(reason: str, *, code: str | None = None) -> TurnDecision:
    return TurnDecision(
        action=TurnAction.NO_ACTION,
        attention=None,
        reason=reason,
        refusal_code=code,
    )


def _routing_is_valid(routing: TurnRoutingFacts) -> bool:
    if not isinstance(routing, TurnRoutingFacts):
        return False
    if not isinstance(routing.ceo_target_bound, bool) or not isinstance(
        routing.coo_target_bound, bool
    ):
        return False
    for value in (
        routing.root_job_id,
        routing.routing_workstream,
        routing.source_workstream,
    ):
        if value is not None and (
            not isinstance(value, str)
            or not value
            or value != value.strip()
            or len(value) > 200
            or any(ord(character) < 32 for character in value)
        ):
            return False
    return True


def _canonical_identity(
    *,
    commission_fingerprint: str,
    message_key: str,
    target_seat: str,
) -> bytes:
    return json.dumps(
        {
            "attention_kind": ATTENTION_WAKE_KIND,
            "commission_fingerprint": commission_fingerprint,
            "message_key": message_key,
            "source_kind": ATTENTION_SOURCE_KIND,
            "target_seat": target_seat,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("ascii")


def _project_attention(
    *,
    parent: Mapping[str, Any],
    message: Mapping[str, Any],
    routing: TurnRoutingFacts,
    target_seat: str,
) -> AgentDialogueAttention:
    commission_fingerprint = str(parent["fingerprint"])
    message_key = str(message["message_key"])
    source_ref = ATTENTION_SOURCE_KIND + ":" + hashlib.sha256(
        _canonical_identity(
            commission_fingerprint=commission_fingerprint,
            message_key=message_key,
            target_seat=target_seat,
        )
    ).hexdigest()
    return AgentDialogueAttention(
        schema=ATTENTION_SCHEMA,
        source_kind=ATTENTION_SOURCE_KIND,
        source_ref=source_ref,
        source_dialogue_schema=str(message["schema"]),
        message_key=message_key,
        message_fingerprint=str(message["fingerprint"]),
        commission_fingerprint=commission_fingerprint,
        operation_key=str(parent["operation_key"]),
        target_seat=target_seat,
        attention_kind=ATTENTION_WAKE_KIND,
        root_job_id=routing.root_job_id,
        routing_workstream=routing.routing_workstream,
        source_workstream=routing.source_workstream,
        evidence_refs=tuple(message["evidence_refs"]),
    )


def _requires_attention(
    *,
    action: TurnAction,
    target_seat: str,
    parent: Mapping[str, Any],
    message: Mapping[str, Any],
    routing: TurnRoutingFacts,
) -> TurnDecision:
    bound = (
        routing.ceo_target_bound
        if target_seat == "ceo"
        else routing.coo_target_bound
    )
    if not bound:
        return _no_action(
            "DIALOGUE_WAKE_TARGET_UNBOUND",
            code="DIALOGUE_WAKE_TARGET_UNBOUND",
        )
    return TurnDecision(
        action=action,
        attention=_project_attention(
            parent=parent,
            message=message,
            routing=routing,
            target_seat=target_seat,
        ),
        reason="DIALOGUE_TURN_PENDING",
        refusal_code=None,
    )


def _same_parent_context(
    parent: Mapping[str, Any], message: Mapping[str, Any]
) -> bool:
    return all(
        message[field] == parent[field]
        for field in ("work_ref", "commission_ref", "session_ref")
    )


def _is_contributor(message: Mapping[str, Any]) -> bool:
    actor = message["actor_ref"]
    return actor["kind"] == "worker_attempt" or (
        actor["kind"] == "executive_surface" and actor["seat"] == "coo"
    )


def _is_ceo(message: Mapping[str, Any]) -> bool:
    actor = message["actor_ref"]
    return actor["kind"] == "executive_surface" and actor["seat"] == "ceo"


def _reduce_semantic_leaf(
    messages: Sequence[Mapping[str, Any]],
) -> tuple[Mapping[str, Any] | None, Mapping[str, Any] | None, str | None]:
    by_key: dict[str, Mapping[str, Any]] = {}
    for message in messages:
        key = str(message["message_key"])
        previous = by_key.get(key)
        if previous is not None:
            if previous["fingerprint"] != message["fingerprint"]:
                return None, None, "MESSAGE_KEY_CONFLICT"
            continue
        by_key[key] = message

    roots: list[str] = []
    children: dict[str, list[str]] = {key: [] for key in by_key}
    for key, message in by_key.items():
        reply_to = message["reply_to_message_key"]
        if reply_to is None:
            roots.append(key)
            continue
        if reply_to not in by_key:
            return None, None, "REPLY_LINEAGE_INVALID"
        children[str(reply_to)].append(key)

    if len(roots) != 1 or any(len(values) > 1 for values in children.values()):
        return None, None, "DIALOGUE_FORKED"

    current_key = roots[0]
    visited: set[str] = set()
    previous: Mapping[str, Any] | None = None
    while True:
        if current_key in visited:
            return None, None, "REPLY_LINEAGE_INVALID"
        visited.add(current_key)
        current = by_key[current_key]
        next_keys = children[current_key]
        if not next_keys:
            if len(visited) != len(by_key):
                return None, None, "DIALOGUE_FORKED"
            return current, previous, None
        previous = current
        current_key = next_keys[0]


def _ceo_reply_lineage_valid(
    message: Mapping[str, Any], previous: Mapping[str, Any] | None
) -> bool:
    if previous is None or not _is_contributor(previous):
        return False
    if message["reply_to_message_key"] != previous["message_key"]:
        return False
    message_type = message["message_type"]
    previous_type = previous["message_type"]
    if message_type == "RULING":
        return previous_type == "DECISION_REQUEST"
    if message_type == "CONTINUE":
        if previous_type not in {"ACK", "PROGRESS", "BLOCKED"}:
            return False
        return not (
            previous_type == "BLOCKED"
            and previous["body"]["needed_from"] != "sol"
        )
    return message_type in {"STOP", "AMENDMENT_AVAILABLE"}


def classify_turn(
    *,
    parent: Mapping[str, Any],
    messages: Sequence[Mapping[str, Any]],
    routing: TurnRoutingFacts,
) -> TurnDecision:
    """Classify one complete accepted V2 history without side effects."""

    try:
        normalized_parent = validate_parent_v2(dict(parent))
    except DialogueContractError as error:
        return _refuse(error.code)

    if normalized_parent["watch_mode"] != TURN_WATCH_MODE_V1:
        return _no_action("WATCH_DISABLED")
    if not _routing_is_valid(routing):
        return _refuse("ROUTING_FACTS_INVALID")
    if not messages:
        parent_fingerprint = str(normalized_parent["fingerprint"])
        initial_source = {
            "schema": PARENT_SCHEMA_V2,
            "message_key": f"asd-initial-{parent_fingerprint}",
            "fingerprint": parent_fingerprint,
            "evidence_refs": (),
        }
        return _requires_attention(
            action=TurnAction.WAKE_COO,
            target_seat="coo",
            parent=normalized_parent,
            message=initial_source,
            routing=routing,
        )

    normalized_messages: list[Mapping[str, Any]] = []
    for message in messages:
        try:
            normalized = validate_message_v2(dict(message))
        except DialogueContractError as error:
            return _refuse(error.code)
        if not _same_parent_context(normalized_parent, normalized):
            return _refuse("DIALOGUE_CONTEXT_MISMATCH")
        normalized_messages.append(normalized)

    first_scope = normalized_messages[0]["applies_to"]
    if any(message["applies_to"] != first_scope for message in normalized_messages[1:]):
        return _refuse("DIALOGUE_CONTEXT_MISMATCH")

    leaf, previous, reduction_error = _reduce_semantic_leaf(normalized_messages)
    if reduction_error is not None:
        return _refuse(reduction_error)
    if leaf is None:
        return _refuse("DIALOGUE_HISTORY_EMPTY")

    message_type = leaf["message_type"]
    if _is_contributor(leaf):
        if (
            message_type == "ACK"
            and previous is not None
            and previous["message_type"] == "STOP"
            and leaf["reply_to_message_key"] == previous["message_key"]
        ):
            actor = leaf["actor_ref"]
            if actor["kind"] != "executive_surface" or actor["seat"] != "coo":
                return _refuse("REPLY_LINEAGE_INVALID")
            return TurnDecision(
                action=TurnAction.TERMINAL,
                attention=None,
                reason="DIALOGUE_STOP_CONSUMED",
                refusal_code=None,
            )
        if message_type == "ACK":
            return _no_action("DIALOGUE_ACKNOWLEDGED")
        if message_type == "PROGRESS":
            return _no_action("DIALOGUE_PROGRESS")
        if message_type in {"BLOCKED", "DECISION_REQUEST", "RESULT"}:
            return _requires_attention(
                action=TurnAction.WAKE_CEO,
                target_seat="ceo",
                parent=normalized_parent,
                message=leaf,
                routing=routing,
            )
        return _refuse("MESSAGE_TYPE_UNCLASSIFIED")

    if not _is_ceo(leaf):
        return _refuse("DIALOGUE_SENDER_INVALID")
    if not _ceo_reply_lineage_valid(leaf, previous):
        return _refuse("REPLY_LINEAGE_INVALID")
    action = {
        "RULING": TurnAction.WAKE_COO,
        "CONTINUE": TurnAction.WAKE_COO,
        "AMENDMENT_AVAILABLE": TurnAction.WAKE_COO,
        "STOP": TurnAction.WAKE_COO_TERMINAL,
    }.get(message_type)
    if action is None:
        return _refuse("MESSAGE_TYPE_UNCLASSIFIED")
    return _requires_attention(
        action=action,
        target_seat="coo",
        parent=normalized_parent,
        message=leaf,
        routing=routing,
    )


__all__ = [
    "ATTENTION_SCHEMA",
    "ATTENTION_SOURCE_KIND",
    "ATTENTION_WAKE_KIND",
    "TURN_WATCH_MODE_V1",
    "AgentDialogueAttention",
    "TurnAction",
    "TurnDecision",
    "TurnRoutingFacts",
    "classify_turn",
]
