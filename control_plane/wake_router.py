"""Deterministic Wake Router — who to wake, never what they should decide.

The router consumes a closed vocabulary of lifecycle *transitions*.  It does
not read Executive Inbox ``next_actions``, worker summaries, GUI titles, or
any other model-authored string as a routing instruction.  Those fields may
be supplied on the stimulus so tests can prove they are inert.

No LLM call.  No SQLite write.  No Job/Attempt/lease mutation.  A healthy
running state produces ``NO_WAKE`` rather than an event.
"""
from __future__ import annotations

import dataclasses
from enum import Enum
from pathlib import Path
from typing import Any

from control_plane.session_targets import (
    SessionTarget,
    SessionTargetRegistry,
    load_session_targets,
)
from control_plane.wake_events import (
    JOB_ID_RE,
    WakeEvent,
    WakeEventError,
    WakeEventType,
    mint_wake_event,
)


class WakeRouterError(ValueError):
    """The stimulus is outside the closed routing vocabulary."""


class WakeAction(str, Enum):
    NO_WAKE = "NO_WAKE"
    WAKE = "WAKE"


TRANSITIONS = frozenset(
    {
        "healthy_running",
        "queued",
        "worker_completed",
        "revision_completed",
        "architectural_contradiction",
        "strategic_ambiguity",
        "mandate_change",
    }
)
_NO_WAKE_TRANSITIONS = frozenset({"healthy_running", "queued"})
_ROUTE_TABLE: dict[str, tuple[WakeEventType, str, str]] = {
    "worker_completed": (
        WakeEventType.REVIEW_REQUIRED,
        "coo",
        "worker_completion_requires_review",
    ),
    "revision_completed": (
        WakeEventType.REVISION_COMPLETED,
        "coo",
        "revision_completed_requires_review",
    ),
    "architectural_contradiction": (
        WakeEventType.ARCHITECTURAL_CONTRADICTION,
        "coo",
        "architectural_contradiction",
    ),
    "strategic_ambiguity": (
        WakeEventType.STRATEGIC_AMBIGUITY,
        "ceo",
        "strategic_ambiguity",
    ),
    "mandate_change": (
        WakeEventType.MANDATE_CHANGE,
        "ceo",
        "mandate_change",
    ),
}
_INERT_FIELDS = (
    "next_actions",
    "worker_prose",
    "claimed_session_alias",
    "claimed_target_seat",
    "claimed_command",
    "claimed_event_type",
)


@dataclasses.dataclass(frozen=True)
class WakeStimulus:
    """Lifecycle fact presented to the router.

    Routing reads ``transition``, ``job_id``, ``attempt_id``, ``project_id``,
    and ``workstream`` only.  Every ``claimed_*`` / prose field is stored so
    it can be listed as suppressed; it never selects a seat, alias, command,
    or event type.
    """

    job_id: str
    transition: str
    attempt_id: str | None = None
    project_id: str | None = None
    workstream: str | None = None
    next_actions: tuple[str, ...] = ()
    worker_prose: str = ""
    claimed_session_alias: str = ""
    claimed_target_seat: str = ""
    claimed_command: str = ""
    claimed_event_type: str = ""
    created_at: str | None = None

    def __post_init__(self) -> None:
        job_id = str(self.job_id or "").strip()
        if JOB_ID_RE.fullmatch(job_id) is None:
            raise WakeRouterError("job_id must be a canonical JOB-* identity")
        transition = str(self.transition or "").strip().lower()
        if transition not in TRANSITIONS:
            raise WakeRouterError(f"unsupported wake transition {transition!r}")
        if not isinstance(self.next_actions, tuple):
            raise WakeRouterError("next_actions must be a tuple of strings")
        object.__setattr__(self, "job_id", job_id)
        object.__setattr__(self, "transition", transition)
        object.__setattr__(self, "next_actions", tuple(str(item) for item in self.next_actions))
        object.__setattr__(self, "worker_prose", str(self.worker_prose or ""))
        object.__setattr__(self, "claimed_session_alias", str(self.claimed_session_alias or ""))
        object.__setattr__(self, "claimed_target_seat", str(self.claimed_target_seat or ""))
        object.__setattr__(self, "claimed_command", str(self.claimed_command or ""))
        object.__setattr__(self, "claimed_event_type", str(self.claimed_event_type or ""))


@dataclasses.dataclass(frozen=True)
class WakeDecision:
    action: WakeAction
    transition: str
    reason_code: str
    target_seat: str | None
    session_alias: str | None
    event: WakeEvent | None
    suppressed_inert_fields: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action.value,
            "transition": self.transition,
            "reason_code": self.reason_code,
            "target_seat": self.target_seat,
            "session_alias": self.session_alias,
            "event": None if self.event is None else self.event.to_dict(),
            "suppressed_inert_fields": list(self.suppressed_inert_fields),
        }


class WakeRouter:
    """Policy-driven, deterministic, LLM-free wake routing."""

    def __init__(self, registry: SessionTargetRegistry) -> None:
        self.registry = registry

    @classmethod
    def load(cls, path: Path | None = None) -> "WakeRouter":
        return cls(load_session_targets(path))

    def route(self, stimulus: WakeStimulus) -> WakeDecision:
        suppressed = _suppressed_fields(stimulus)
        if stimulus.transition in _NO_WAKE_TRANSITIONS:
            return WakeDecision(
                action=WakeAction.NO_WAKE,
                transition=stimulus.transition,
                reason_code="ordinary_healthy_state",
                target_seat=None,
                session_alias=None,
                event=None,
                suppressed_inert_fields=suppressed,
            )
        event_type, seat, reason_code = _ROUTE_TABLE[stimulus.transition]
        target: SessionTarget = self.registry.resolve(
            seat,
            workstream=stimulus.workstream,
            claimed_session_alias=stimulus.claimed_session_alias,
        )
        try:
            event = mint_wake_event(
                event_type=event_type,
                job_id=stimulus.job_id,
                attempt_id=stimulus.attempt_id,
                project_id=stimulus.project_id,
                target_seat=target.target_seat,
                session_alias=target.session_alias,
                reason_code=reason_code,
                created_at=stimulus.created_at,
            )
        except WakeEventError as exc:
            raise WakeRouterError(str(exc)) from exc
        return WakeDecision(
            action=WakeAction.WAKE,
            transition=stimulus.transition,
            reason_code=reason_code,
            target_seat=target.target_seat,
            session_alias=target.session_alias,
            event=event,
            suppressed_inert_fields=suppressed,
        )


def _suppressed_fields(stimulus: WakeStimulus) -> tuple[str, ...]:
    present: list[str] = []
    for name in _INERT_FIELDS:
        value = getattr(stimulus, name)
        if value:
            present.append(name)
    return tuple(present)


__all__ = [
    "TRANSITIONS",
    "WakeAction",
    "WakeDecision",
    "WakeRouter",
    "WakeRouterError",
    "WakeStimulus",
]
