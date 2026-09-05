"""Pure Agent Dialogue attention adapter for the canonical Wake Fabric."""
from __future__ import annotations

from control_plane.wake_events import SourceKind, WakeKind, WakeObligation, mint_obligation
from integrations.slack_agent_dialogue.turn_watcher import (
    ATTENTION_SOURCE_KIND,
    ATTENTION_WAKE_KIND,
    AgentDialogueAttention,
)


def attention_to_wake_obligation(
    attention: AgentDialogueAttention,
    *,
    emitted_at: str | None = None,
) -> WakeObligation:
    """Project one accepted attention identity without inventing transport state."""

    if not isinstance(attention, AgentDialogueAttention):
        raise TypeError("attention must be an AgentDialogueAttention")
    if (
        attention.source_kind != ATTENTION_SOURCE_KIND
        or attention.attention_kind != ATTENTION_WAKE_KIND
    ):
        raise ValueError("attention vocabulary does not match the accepted adapter")
    evidence_refs = [attention.source_ref]
    if attention.root_job_id is not None:
        evidence_refs.append(attention.root_job_id)
    return mint_obligation(
        wake_kind=WakeKind.DIALOGUE_TURN_PENDING,
        source_kind=SourceKind.AGENT_DIALOGUE_ATTENTION,
        source_ref=attention.source_ref,
        declared_target_seat=attention.target_seat,
        root_job_id=attention.root_job_id,
        workstream=attention.routing_workstream,
        source_workstream=attention.source_workstream,
        emitted_at=emitted_at,
        evidence_refs=evidence_refs,
    )


__all__ = ["attention_to_wake_obligation"]
