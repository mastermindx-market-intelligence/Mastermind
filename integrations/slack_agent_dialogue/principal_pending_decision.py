"""Observe one unanswered decision in an already acquired principal source.

This is an in-memory source predicate, not an authority or a reservation. It
uses the existing semantic history reducer without requiring or inventing a
Wake target. The host must acquire the current source again at its effect
boundary; this result never authorizes reuse of an earlier observation.
"""
from __future__ import annotations

from common.agent_dialogue_turn_watcher import (
    TurnAction, TurnRoutingFacts, _classify_accepted_history,
    _ordered_semantic_chain,
)
from integrations.slack_agent_dialogue.contract_v2 import (
    validate_message_v2, validate_parent_v2,
)
from integrations.slack_agent_dialogue.engine import ReadMessage
from integrations.slack_agent_dialogue.principal_current_reader import (
    PrincipalCurrentSourceRead, _wire,
)


class PrincipalDecisionSourceUnavailable(RuntimeError):
    def __init__(self) -> None:
        super().__init__("PRINCIPAL_DECISION_SOURCE_UNAVAILABLE")


def require_unanswered_principal_decision(
    read: PrincipalCurrentSourceRead,
) -> ReadMessage:
    """Return only the original unresolved DECISION_REQUEST, with no effects.

    Accepted source acquisition and caller admission remain with their existing
    owners. The pure reducer is shared with the turn watcher; both routing flags
    stay false. Its unbound-target result is evidence of pending semantics only,
    never a route, a delivery request, or an authorization to answer.
    """
    try:
        if type(read) is not PrincipalCurrentSourceRead:
            raise PrincipalDecisionSourceUnavailable()
        source, binding = read.source, read.binding
        if source.thread.mutated_count != 0 or source.thread.historical_messages:
            raise PrincipalDecisionSourceUnavailable()
        parent = validate_parent_v2(_wire(source.parent))
        messages = [validate_message_v2(_wire(item.message))
                    for item in source.thread.messages]
        predecessor = validate_message_v2(_wire(source.predecessor.message))
        worker = dict(binding.applies_to)
        worker["kind"] = "worker_attempt"
        if (predecessor["message_type"] != "DECISION_REQUEST"
                or predecessor["actor_ref"] != worker
                or predecessor["applies_to"] != dict(binding.applies_to)
                or predecessor["message_key"] != binding.reply_to_message_key
                or source.thread_ts != binding.thread_ts
                or any(message[field] != parent[field]
                       for message in messages
                       for field in ("work_ref", "commission_ref", "session_ref"))):
            raise PrincipalDecisionSourceUnavailable()
        ordered, error = _ordered_semantic_chain(messages)
        if error is not None:
            raise PrincipalDecisionSourceUnavailable()
        positions = [i for i, message in enumerate(ordered)
                     if message["message_key"] == predecessor["message_key"]
                     and message["fingerprint"] == predecessor["fingerprint"]]
        if len(positions) != 1 or any(
            message["message_type"] not in {"ACK", "PROGRESS"}
            or message["actor_ref"] != predecessor["actor_ref"]
            or message["applies_to"] != predecessor["applies_to"]
            for message in ordered[positions[0] + 1:]
        ):
            raise PrincipalDecisionSourceUnavailable()
        decision = _classify_accepted_history(
            normalized_parent=parent, normalized_messages=messages,
            routing=TurnRoutingFacts(
                bound_operation_key=parent["operation_key"],
                bound_commission_fingerprint=parent["fingerprint"],
                root_job_id=binding.actor_ref["root_job_id"],
                routing_workstream=None, source_workstream=None,
                ceo_target_bound=False, coo_target_bound=False,
            ),
        )
        if (decision.action is not TurnAction.NO_ACTION
                or decision.reason != "DIALOGUE_WAKE_TARGET_UNBOUND"
                or decision.attention is not None):
            raise PrincipalDecisionSourceUnavailable()
        return source.predecessor
    except Exception:
        raise PrincipalDecisionSourceUnavailable() from None
