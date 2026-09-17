"""Pure deterministic classification of accepted Agent Dialogue V2 turns."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Sequence

from common.agent_dialogue_contract import DialogueContractError
from common.agent_dialogue_contract_v2 import (
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

    bound_operation_key: str
    bound_commission_fingerprint: str
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
    if (
        not isinstance(routing.bound_operation_key, str)
        or not routing.bound_operation_key
        or routing.bound_operation_key != routing.bound_operation_key.strip()
        or len(routing.bound_operation_key) > 128
    ):
        return False
    if (
        not isinstance(routing.bound_commission_fingerprint, str)
        or len(routing.bound_commission_fingerprint) != 64
        or any(
            character not in "0123456789abcdef"
            for character in routing.bound_commission_fingerprint
        )
    ):
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


def _ordered_semantic_chain(
    messages: Sequence[Mapping[str, Any]],
) -> tuple[tuple[Mapping[str, Any], ...], str | None]:
    """Reduce accepted messages into one semantic order.

    A contributor may append a linear ACK/PROGRESS annotation chain while a
    material return is waiting.  A single CEO disposition that still replies
    to the original material return is not a competing semantic leaf: the
    worker's request-bound consumer requires that exact reference.  Any second
    command, second annotation branch, material side branch, or non-quiet
    descendant remains a fork.
    """
    by_key: dict[str, Mapping[str, Any]] = {}
    for message in messages:
        key = str(message["message_key"])
        previous = by_key.get(key)
        if previous is not None:
            if previous["fingerprint"] != message["fingerprint"]:
                return (), "MESSAGE_KEY_CONFLICT"
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
            return (), "REPLY_LINEAGE_INVALID"
        children[str(reply_to)].append(key)

    if len(roots) != 1:
        return (), "DIALOGUE_FORKED"

    def quiet_annotation(key: str) -> bool:
        message = by_key[key]
        return _is_contributor(message) and message["message_type"] in {
            "ACK",
            "PROGRESS",
        }

    def parent_command(key: str) -> bool:
        message = by_key[key]
        return _is_ceo(message) and message["message_type"] in {
            "RULING",
            "CONTINUE",
            "STOP",
            "AMENDMENT_AVAILABLE",
        }

    current_key = roots[0]
    visited: set[str] = set()
    ordered: list[Mapping[str, Any]] = []
    while True:
        if current_key in visited:
            return (), "REPLY_LINEAGE_INVALID"
        visited.add(current_key)
        current = by_key[current_key]
        ordered.append(current)
        next_keys = children[current_key]
        if not next_keys:
            if len(visited) != len(by_key):
                return (), "DIALOGUE_FORKED"
            return tuple(ordered), None
        if len(next_keys) == 1:
            current_key = next_keys[0]
            continue

        if not (
            _is_contributor(current)
            and current["message_type"] in {"BLOCKED", "DECISION_REQUEST", "RESULT"}
        ):
            return (), "DIALOGUE_FORKED"
        quiet_roots = [key for key in next_keys if quiet_annotation(key)]
        command_roots = [key for key in next_keys if parent_command(key)]
        if (
            len(quiet_roots) != 1
            or len(command_roots) != 1
            or len(next_keys) != 2
        ):
            return (), "DIALOGUE_FORKED"

        quiet_key = quiet_roots[0]
        while True:
            if quiet_key in visited or not quiet_annotation(quiet_key):
                return (), "DIALOGUE_FORKED"
            visited.add(quiet_key)
            ordered.append(by_key[quiet_key])
            quiet_children = children[quiet_key]
            if not quiet_children:
                break
            if len(quiet_children) != 1 or not quiet_annotation(quiet_children[0]):
                return (), "DIALOGUE_FORKED"
            quiet_key = quiet_children[0]
        current_key = command_roots[0]


def _reduce_semantic_leaf(
    messages: Sequence[Mapping[str, Any]],
) -> tuple[Mapping[str, Any] | None, Mapping[str, Any] | None, str | None]:
    """Preserve the existing leaf API over the single chain reducer."""
    ordered, error = _ordered_semantic_chain(messages)
    if error is not None:
        return None, None, error
    return ordered[-1], ordered[-2] if len(ordered) > 1 else None, None


def _ceo_reply_lineage_valid(
    message: Mapping[str, Any],
    previous: Mapping[str, Any] | None,
    pending_return: Mapping[str, Any] | None = None,
) -> bool:
    if pending_return is not None:
        # Quiet contributor annotations do not become the subject of the
        # decision.  The command must retain the exact original request key so
        # the existing request-bound waiter can consume it.
        if message["reply_to_message_key"] != pending_return["message_key"]:
            return False
        subject = pending_return
    else:
        if previous is None or not _is_contributor(previous):
            return False
        if message["reply_to_message_key"] != previous["message_key"]:
            return False
        subject = previous
    message_type = message["message_type"]
    previous_type = subject["message_type"]
    if message_type == "RULING":
        return previous_type == "DECISION_REQUEST" and any(
            option["id"] == message["body"]["selected_option"]
            for option in subject["body"]["options"]
        )
    if message_type == "CONTINUE":
        if previous_type not in {"ACK", "PROGRESS", "BLOCKED", "RESULT"}:
            return False
        return not (
            previous_type == "BLOCKED"
            and subject["body"]["needed_from"] != "sol"
        )
    return message_type in {"STOP", "AMENDMENT_AVAILABLE"}


def _classify_accepted_history(
    *,
    normalized_parent: Mapping[str, Any],
    normalized_messages: Sequence[Mapping[str, Any]],
    routing: TurnRoutingFacts,
) -> TurnDecision:
    """Interpret an already-normalized history, without storing new state.

    The public entry point owns schema, parent, routing and context validation.
    This fold keeps one unresolved material return per child. Competing returns
    with no explicit disposition refuse instead of inventing a supersession or
    a second queue. All accumulators are discarded after this call.
    """
    ordered, reduction_error = _ordered_semantic_chain(normalized_messages)
    if reduction_error is not None:
        return _refuse(reduction_error)

    pending_return: Mapping[str, Any] | None = None
    pending_command: Mapping[str, Any] | None = None
    pending_command_valid: bool | None = None
    previous: Mapping[str, Any] | None = None
    terminal_consumed = False
    for message in ordered:
        message_type = message["message_type"]
        if terminal_consumed:
            # A terminal consumption is not assignment of a successor child.
            return _refuse("REPLY_LINEAGE_INVALID")
        if pending_command is not None and pending_command["message_type"] == "STOP":
            actor = message["actor_ref"]
            if not (
                pending_command_valid is True
                and message_type == "ACK"
                and actor["kind"] == "executive_surface"
                and actor["seat"] == "coo"
                and message["reply_to_message_key"] == pending_command["message_key"]
            ):
                return _refuse("REPLY_LINEAGE_INVALID")
            terminal_consumed = True
            pending_command = None
            pending_command_valid = None
        elif _is_contributor(message):
            if message_type in {"ACK", "PROGRESS"}:
                # A quiet annotation may preserve a pending material return
                # only for the exact same contributor identity and target.
                # Otherwise a foreign or stale branch would be silently
                # admitted into the accepted semantic history.
                if pending_return is not None and (
                    message["actor_ref"] != pending_return["actor_ref"]
                    or message["applies_to"] != pending_return["applies_to"]
                ):
                    return _refuse("REPLY_LINEAGE_INVALID")
                # The contributor can acknowledge a parent command, but its
                # own routine update cannot answer its pending material return.
                pending_command = None
                pending_command_valid = None
            elif message_type in {"BLOCKED", "DECISION_REQUEST", "RESULT"}:
                if pending_return is not None:
                    return _refuse("REPLY_LINEAGE_INVALID")
                pending_return = message
                pending_command = None
                pending_command_valid = None
            else:
                return _refuse("MESSAGE_TYPE_UNCLASSIFIED")
        else:
            if not _is_ceo(message):
                return _refuse("DIALOGUE_SENDER_INVALID")
            # Preserve the existing source-reconciliation boundary: a command
            # that remains the actionable leaf must be valid, while a later
            # quiet contributor leaf leaves exact successor validation to the
            # source owner.  This prevents a historical invalid successor from
            # being relabeled as a whole-history semantics failure.
            pending_command_valid = _ceo_reply_lineage_valid(
                message, previous, pending_return
            )
            pending_return = None
            pending_command = message
        previous = message

    if terminal_consumed:
        return TurnDecision(
            action=TurnAction.TERMINAL,
            attention=None,
            reason="DIALOGUE_STOP_CONSUMED",
            refusal_code=None,
        )
    if pending_return is not None:
        return _requires_attention(
            action=TurnAction.WAKE_CEO,
            target_seat="ceo",
            parent=normalized_parent,
            message=pending_return,
            routing=routing,
        )
    if pending_command is not None:
        if pending_command_valid is not True:
            return _refuse("REPLY_LINEAGE_INVALID")
        action = (
            TurnAction.WAKE_COO_TERMINAL
            if pending_command["message_type"] == "STOP"
            else TurnAction.WAKE_COO
        )
        return _requires_attention(
            action=action,
            target_seat="coo",
            parent=normalized_parent,
            message=pending_command,
            routing=routing,
        )
    if previous is None:
        return _refuse("DIALOGUE_HISTORY_EMPTY")
    return _no_action(
        "DIALOGUE_ACKNOWLEDGED"
        if previous["message_type"] == "ACK"
        else "DIALOGUE_PROGRESS"
    )


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

    if not _routing_is_valid(routing):
        return _refuse("ROUTING_FACTS_INVALID")
    if (
        routing.bound_operation_key != normalized_parent["operation_key"]
        or routing.bound_commission_fingerprint
        != normalized_parent["fingerprint"]
    ):
        return _refuse("DIALOGUE_BINDING_MISMATCH")
    if normalized_parent["watch_mode"] != TURN_WATCH_MODE_V1:
        return _no_action("WATCH_DISABLED")
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

    return _classify_accepted_history(
        normalized_parent=normalized_parent,
        normalized_messages=normalized_messages,
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
