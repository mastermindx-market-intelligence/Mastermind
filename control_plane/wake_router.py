"""Trusted source adapters plus route policy — not a semantic classifier.

Callers may not invent ``architectural_contradiction`` / ``mandate_change``
tokens.  The only legal inputs are:

* a canonical Executive Inbox v2 attention item, or
* a canonical Executive OS runtime event + hierarchy fact.

Inbox items already carry a reviewed ``target``.  This module does not
re-infer the executive seat from department, prose, or claimed fields.

Generic ``JOB_COMPLETED`` / worker-finished is ``NO_WAKE``.  The only runtime
continuation wake is ``review_required`` when the durable job says review is
required and no review job exists yet.
"""
from __future__ import annotations

import dataclasses
from enum import Enum
from pathlib import Path
from typing import Any, Mapping

from control_plane.executive_inbox import attention_id as inbox_attention_id
from control_plane.session_targets import (
    RuntimeBinding,
    SessionTargetError,
    SessionTargetRegistry,
    WakeRoute,
    build_route,
    load_session_targets,
    transport_implemented,
)
from control_plane.wake_events import (
    INBOX_WAKE_KINDS,
    JOB_ID_RE,
    SEATS,
    SourceKind,
    WakeKind,
    WakeObligation,
    WakeObligationError,
    mint_obligation,
    runtime_source_ref,
)


class WakeRouterError(ValueError):
    """The canonical source cannot be adapted or routed."""


class WakeAction(str, Enum):
    NO_WAKE = "NO_WAKE"
    WAKE = "WAKE"
    UNKNOWN_KIND = "UNKNOWN_KIND"


_INERT_ATTENTION_FIELDS = (
    "existing_next_actions",
    "claimed_session_alias",
    "claimed_command",
    "claimed_target_seat",
    "claimed_wake_kind",
)
_INERT_RUNTIME_FIELDS = (
    "next_actions",
    "worker_prose",
    "claimed_session_alias",
    "claimed_command",
    "claimed_target_seat",
    "claimed_wake_kind",
)
_RUNTIME_NO_WAKE_EVENTS = frozenset(
    {
        "WORKER_REGISTERED",
        "QUOTA_STATUS_CHANGED",
        "WORKER_STATUS_CHANGED",
        "QUOTA_RELEASED",
        "JOB_CREATED",
        "JOB_REQUEUED",
        "JOB_CLAIMED",
        "ATTEMPT_ADOPTED",
        "ATTEMPT_HEARTBEAT",
        "ATTEMPT_PROCESS_RECORDED",
        "ATTEMPT_RUNNING",
        "ATTEMPT_PROCESS_EXITED",
        "JOB_CHECKPOINTED",
        "JOB_COMPLETED",
        "JOB_FAILED",
        "ATTEMPT_LOST",
        "JOB_RATE_LIMITED",
        "JOB_CANCELLED",
    }
)


@dataclasses.dataclass(frozen=True)
class CanonicalInboxAttention:
    """Already-classified Inbox v2 item.  This adapter does not classify."""

    attention_id: str
    kind: str
    target: str
    source: str
    job_id: str | None = None
    root_job_id: str | None = None
    workstream: str | None = None
    reason: str = ""
    ordinal: int | None = None
    existing_next_actions: tuple[str, ...] = ()
    claimed_session_alias: str = ""
    claimed_command: str = ""
    claimed_target_seat: str = ""
    claimed_wake_kind: str = ""
    source_created_at: str | None = None
    emitted_at: str | None = None


@dataclasses.dataclass(frozen=True)
class CanonicalRuntimeFact:
    """One durable Executive OS event plus hierarchy flags from the job row."""

    aggregate_type: str
    aggregate_id: str
    sequence: int
    event_type: str
    job_id: str | None = None
    attempt_id: str | None = None
    root_job_id: str | None = None
    workstream: str | None = None
    review_required: bool = False
    reviews_job_id: str | None = None
    escalation_target: str = "coo"
    source_created_at: str | None = None
    emitted_at: str | None = None
    next_actions: tuple[str, ...] = ()
    worker_prose: str = ""
    claimed_session_alias: str = ""
    claimed_command: str = ""
    claimed_target_seat: str = ""
    claimed_wake_kind: str = ""


@dataclasses.dataclass(frozen=True)
class WakeDecision:
    action: WakeAction
    obligation: WakeObligation | None
    route: WakeRoute | None
    suppressed_inert_fields: tuple[str, ...]
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action.value,
            "obligation": None if self.obligation is None else self.obligation.to_dict(),
            "route": None if self.route is None else self.route.to_dict(),
            "suppressed_inert_fields": list(self.suppressed_inert_fields),
            "reason": self.reason,
        }


class WakeRouter:
    def __init__(self, registry: SessionTargetRegistry) -> None:
        self.registry = registry

    @classmethod
    def load(cls, path: Path | None = None) -> "WakeRouter":
        return cls(load_session_targets(path))

    def from_inbox(
        self,
        item: CanonicalInboxAttention | Mapping[str, Any],
        *,
        binding: RuntimeBinding | None = None,
    ) -> WakeDecision:
        attention = _inbox_item(item)
        suppressed = _present(attention, _INERT_ATTENTION_FIELDS)
        if attention.kind not in INBOX_WAKE_KINDS:
            return WakeDecision(
                action=WakeAction.UNKNOWN_KIND,
                obligation=None,
                route=None,
                suppressed_inert_fields=suppressed,
                reason=f"unknown inbox kind {attention.kind!r} remains attention",
            )
        expected_id = inbox_attention_id(
            target=attention.target,
            kind=attention.kind,
            source=attention.source,
            job_id=attention.job_id,
            workstream=attention.workstream,
            reason=attention.reason,
            ordinal=attention.ordinal,
        )
        if attention.attention_id != expected_id:
            raise WakeRouterError("attention_id does not match the Inbox identity function")
        try:
            obligation = mint_obligation(
                wake_kind=attention.kind,
                source_kind=SourceKind.EXECUTIVE_INBOX_ATTENTION,
                source_ref=attention.attention_id,
                declared_target_seat=attention.target,
                job_id=attention.job_id,
                root_job_id=attention.root_job_id,
                workstream=attention.workstream,
                source_created_at=attention.source_created_at,
                emitted_at=attention.emitted_at,
            )
        except WakeObligationError as exc:
            raise WakeRouterError(str(exc)) from exc
        return self._routed(obligation, suppressed, binding=binding)

    def from_runtime(
        self,
        fact: CanonicalRuntimeFact,
        *,
        binding: RuntimeBinding | None = None,
    ) -> WakeDecision:
        suppressed = _present(fact, _INERT_RUNTIME_FIELDS)
        event_type = str(fact.event_type or "").strip()
        if event_type not in _RUNTIME_NO_WAKE_EVENTS:
            raise WakeRouterError(f"unknown runtime event_type {event_type!r}")
        if not (
            event_type == "JOB_COMPLETED"
            and fact.review_required
            and not fact.reviews_job_id
        ):
            return WakeDecision(
                action=WakeAction.NO_WAKE,
                obligation=None,
                route=None,
                suppressed_inert_fields=suppressed,
                reason="canonical runtime fact does not require an executive wake",
            )
        try:
            source_ref = runtime_source_ref(
                aggregate_type=fact.aggregate_type,
                aggregate_id=fact.aggregate_id,
                sequence=fact.sequence,
            )
            obligation = mint_obligation(
                wake_kind=WakeKind.REVIEW_REQUIRED,
                source_kind=SourceKind.EXECUTIVE_RUNTIME_EVENT,
                source_ref=source_ref,
                declared_target_seat=fact.escalation_target,
                job_id=fact.job_id,
                attempt_id=fact.attempt_id,
                root_job_id=fact.root_job_id,
                workstream=fact.workstream,
                source_created_at=fact.source_created_at,
                emitted_at=fact.emitted_at,
            )
        except WakeObligationError as exc:
            raise WakeRouterError(str(exc)) from exc
        return self._routed(obligation, suppressed, binding=binding)

    def _routed(
        self,
        obligation: WakeObligation,
        suppressed: tuple[str, ...],
        *,
        binding: RuntimeBinding | None,
    ) -> WakeDecision:
        try:
            target = self.registry.resolve(
                obligation.declared_target_seat,
                workstream=obligation.workstream,
                root_job_id=obligation.root_job_id,
                binding=binding,
            )
        except SessionTargetError as exc:
            raise WakeRouterError(str(exc)) from exc
        route = build_route(
            obligation_id=obligation.obligation_id,
            target=target,
            registry=self.registry,
            transport_implemented=transport_implemented(target.wake_transport),
            root_job_id=obligation.root_job_id,
            workstream=obligation.workstream,
            binding=binding,
        )
        return WakeDecision(
            action=WakeAction.WAKE,
            obligation=obligation,
            route=route,
            suppressed_inert_fields=suppressed,
            reason="canonical source requires a wake obligation",
        )


def _inbox_item(item: CanonicalInboxAttention | Mapping[str, Any]) -> CanonicalInboxAttention:
    if isinstance(item, CanonicalInboxAttention):
        attention = item
    else:
        if not isinstance(item, Mapping):
            raise WakeRouterError("inbox attention must be a mapping")
        attention = CanonicalInboxAttention(
            attention_id=str(item.get("attention_id") or ""),
            kind=str(item.get("kind") or ""),
            target=str(item.get("target") or ""),
            source=str(item.get("source") or ""),
            job_id=item.get("job_id") or None,
            root_job_id=item.get("root_job_id") or None,
            workstream=item.get("workstream") or None,
            reason=str(item.get("reason") or ""),
            ordinal=item.get("ordinal"),
            existing_next_actions=tuple(item.get("existing_next_actions") or ()),
            claimed_session_alias=str(item.get("claimed_session_alias") or ""),
            claimed_command=str(item.get("claimed_command") or ""),
            claimed_target_seat=str(item.get("claimed_target_seat") or ""),
            claimed_wake_kind=str(item.get("claimed_wake_kind") or ""),
            source_created_at=item.get("source_created_at"),
            emitted_at=item.get("emitted_at"),
        )
    if attention.target not in SEATS:
        raise WakeRouterError(f"inbox target {attention.target!r} is not a canonical seat")
    if attention.job_id not in (None, "") and JOB_ID_RE.fullmatch(str(attention.job_id)) is None:
        raise WakeRouterError("inbox job_id is malformed")
    return attention


def _present(obj: object, names: tuple[str, ...]) -> tuple[str, ...]:
    found: list[str] = []
    for name in names:
        value = getattr(obj, name, None)
        if value:
            found.append(name)
    return tuple(found)


__all__ = [
    "CanonicalInboxAttention",
    "CanonicalRuntimeFact",
    "WakeAction",
    "WakeDecision",
    "WakeRouter",
    "WakeRouterError",
]
