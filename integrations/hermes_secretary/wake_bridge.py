"""Map a secretary observation onto the existing Wake obligation envelope.

The Wake fabric (``control_plane.wake_events``) has no scheduler. Masterplan
P4 says timer observations become Wake obligations only when a canonical
source already exists. This module mints that envelope in memory when the
caller already holds an ``agent_dialogue_attention:<64 hex>`` source ref
produced by the dialogue resolver. A Slack ts is not that identity.

Nothing here writes the wake ledger, dispatches a transport, or invents a
source kind.
"""

from __future__ import annotations

from typing import Any

from constants import WAKE_SEAT
from control_plane.wake_events import (
    DIALOGUE_ATTENTION_REF_RE,
    WakeObligationError,
    mint_obligation,
)


def try_mint_dialogue_wake(source_ref: object, *, emitted_at: str | None = None) -> dict[str, Any]:
    """Return a shadow wake annotation. Never persists it."""

    if not isinstance(source_ref, str) or DIALOGUE_ATTENTION_REF_RE.fullmatch(source_ref) is None:
        return {
            "status": "WAKE_SOURCE_NOT_ADMITTED",
            "schedule_backend": "hermes_cron",
            "owner": "control_plane.wake_events.mint_obligation",
        }
    try:
        obligation = mint_obligation(
            wake_kind="dialogue_turn_pending",
            source_kind="agent_dialogue_attention",
            source_ref=source_ref,
            declared_target_seat=WAKE_SEAT,
            emitted_at=emitted_at,
        )
    except WakeObligationError:
        return {
            "status": "WAKE_SOURCE_NOT_ADMITTED",
            "schedule_backend": "hermes_cron",
            "owner": "control_plane.wake_events.mint_obligation",
        }
    return {
        "status": "MINTED",
        "schedule_backend": "hermes_cron",
        "owner": "control_plane.wake_events.mint_obligation",
        "obligation": obligation.to_dict(),
    }


def annotate(decision: dict[str, Any], message: dict[str, Any]) -> dict[str, Any]:
    """Attach a wake annotation. The Slack body cannot choose the seat."""

    decision["wake"] = try_mint_dialogue_wake(
        message.get("canonical_source_ref"),
        emitted_at=message.get("wake_emitted_at") if isinstance(message.get("wake_emitted_at"), str) else None,
    )
    return decision
