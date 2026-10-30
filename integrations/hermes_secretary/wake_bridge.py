"""Project only canonical, typed Agent Dialogue attention into shadow Wake.

A Slack message, syntactically plausible source reference, or cron tick is
not evidence of a pending canonical task. The sole projector is the existing
Agent Dialogue -> Wake adapter, which preserves source/root/workstream/seat.
Nothing here persists an obligation, dispatches a transport, schedules a
watcher, or proves a source is still current. That remains with its owner.
"""
from __future__ import annotations

from typing import Any

from constants import WAKE_SEAT
from control_plane.wake_events import WakeObligationError
from integrations.slack_agent_dialogue.turn_wake_adapter import (
    attention_to_wake_obligation,
)
from integrations.slack_agent_dialogue.turn_watcher import AgentDialogueAttention

_OWNER = "control_plane.wake_events.mint_obligation"


def _refused() -> dict[str, Any]:
    return {
        "status": "WAKE_SOURCE_NOT_ADMITTED",
        "schedule_backend": "hermes_cron",
        "owner": _OWNER,
    }


def try_mint_dialogue_wake(
    attention: object, *, emitted_at: str | None = None
) -> dict[str, Any]:
    """Return *only* a nonpersisted annotation for typed canonical attention.

    The caller must obtain AgentDialogueAttention from the existing dialogue
    source-observation owner, not construct it from Slack text or a source_ref.
    A valid dataclass is not current-source proof and cannot authorize Wake
    persistence, delivery, worker activation, or an agent session.
    """
    if not isinstance(attention, AgentDialogueAttention):
        return _refused()
    if attention.target_seat != WAKE_SEAT:
        return _refused()
    try:
        obligation = attention_to_wake_obligation(
            attention, emitted_at=emitted_at,
        )
    except (ValueError, TypeError, WakeObligationError):
        return _refused()
    return {
        "status": "MINTED",
        "schedule_backend": "hermes_cron",
        "owner": _OWNER,
        "obligation": obligation.to_dict(),
    }


def annotate(
    decision: dict[str, Any],
    message: dict[str, Any],
    *,
    attention: AgentDialogueAttention | None = None,
    emitted_at: str | None = None,
) -> dict[str, Any]:
    """Decorate a shadow decision, ignoring untrusted message Wake claims.

    No message field (including canonical_source_ref, wake_emitted_at, sender,
    channel or a claimed target seat) supplies Wake source authority.
    """
    del message
    decision["wake"] = try_mint_dialogue_wake(
        attention, emitted_at=emitted_at,
    )
    return decision
