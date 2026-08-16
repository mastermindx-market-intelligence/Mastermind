"""Trusted source adapters plus route policy — not a semantic classifier.

Callers may not invent ``architectural_contradiction`` / ``mandate_change``
tokens.  The only legal inputs are:

* a projected Executive Inbox v2 attention item, admitted through
  :func:`admit_inbox_projection`, or
* a canonical Executive OS runtime event plus Phase 1F hierarchy facts.

Inbox ``attention_id`` is an opaque canonical ``source_ref``.  This adapter
does not recompute it and does not reverse-engineer hidden hash ingredients
such as Agent OS row ordinal.  Content-addressed identity is not
authentication: only projector output belongs inside this trust boundary.

Generic ``JOB_COMPLETED`` / worker-finished is ``NO_WAKE``.  The only runtime
continuation wake is ``review_required`` when the durable job requires review
and no sibling review job exists (Phase 1F pointer:
``review.reviews_job_id == builder.job_id``).  Ordinary continuation uses
``owner_seat``, never ``escalation_target``.
"""
from __future__ import annotations

import dataclasses
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Sequence

from control_plane.session_targets import (
    RuntimeBinding,
    SessionTargetError,
    SessionTargetRegistry,
    WakeRoute,
    build_route,
    load_session_targets,
)
from control_plane.wake_events import (
    ATTENTION_ID_RE,
    INBOX_WAKE_KINDS,
    JOB_ID_RE,
    SEATS,
    WORKSTREAM_RE,
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


_INBOX_ITEM_REQUIRED_KEYS = frozenset(
    {
        "attention_id",
        "target",
        "kind",
        "source",
        "job_id",
        "workstream",
        "status",
        "reason",
        "evidence",
        "existing_next_actions",
    }
)
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
    """Admitted Inbox v2 projector row.  Construct via :func:`admit_inbox_projection`."""

    attention_id: str
    kind: str
    target: str
    source: str
    job_id: str | None = None
    root_job_id: str | None = None
    workstream: str | None = None
    reason: str = ""
    existing_next_actions: tuple[str, ...] = ()
    claimed_session_alias: str = ""
    claimed_command: str = ""
    claimed_target_seat: str = ""
    claimed_wake_kind: str = ""
    source_created_at: str | None = None
    emitted_at: str | None = None


@dataclasses.dataclass(frozen=True)
class CanonicalRuntimeFact:
    """One durable Executive OS event plus Phase 1F hierarchy facts.

    ``owner_seat`` shepherds ordinary continuation.  ``escalation_target`` is
    the terminal-exception seat and must not be used for review continuation.
    ``review_job_exists`` is the derived sibling fact
    ``review.reviews_job_id == builder.job_id``.  The builder's own
    ``reviews_job_id`` column is not that pointer.
    """

    aggregate_type: str
    aggregate_id: str
    sequence: int
    event_type: str
    owner_seat: str
    review_job_exists: bool
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


def sibling_review_exists(
    *, builder_job_id: str, review_jobs: Sequence[Mapping[str, Any]]
) -> bool:
    """Phase 1F pointer direction: a review job points AT the builder."""

    builder = str(builder_job_id or "").strip()
    if JOB_ID_RE.fullmatch(builder) is None:
        raise WakeRouterError("builder_job_id must be a canonical JOB-* identity")
    return any(str(row.get("reviews_job_id") or "").strip() == builder for row in review_jobs)


def admit_inbox_projection(item: Mapping[str, Any]) -> CanonicalInboxAttention:
    """Admit Executive Inbox v2 projector output into the wake adapter.

    Treats ``attention_id`` as an opaque canonical source_ref.  Does not
    recompute the Inbox hash.  A mapping that merely contains an ``eia-*``
    string without the projector item shape is refused.
    """

    if not isinstance(item, Mapping):
        raise WakeRouterError("inbox projection must be a mapping")
    missing = sorted(_INBOX_ITEM_REQUIRED_KEYS - set(item))
    if missing:
        raise WakeRouterError(
            "mapping is not Executive Inbox v2 projector output; "
            f"missing {', '.join(missing)}"
        )
    if not isinstance(item.get("evidence"), list):
        raise WakeRouterError("inbox projection evidence must be a list")
    if not isinstance(item.get("existing_next_actions"), list):
        raise WakeRouterError("inbox projection existing_next_actions must be a list")
    attention_id = str(item.get("attention_id") or "").strip()
    if ATTENTION_ID_RE.fullmatch(attention_id) is None:
        raise WakeRouterError("inbox projection attention_id is not a canonical eia-* id")
    target = str(item.get("target") or "").strip().lower()
    if target not in SEATS:
        raise WakeRouterError(f"inbox target {target!r} is not a canonical seat")
    job_raw = item.get("job_id")
    job_id = None if job_raw in (None, "") else str(job_raw).strip()
    if job_id is not None and JOB_ID_RE.fullmatch(job_id) is None:
        raise WakeRouterError("inbox job_id is malformed")
    root_raw = item.get("root_job_id")
    root_job_id = None if root_raw in (None, "") else str(root_raw).strip()
    if root_job_id is not None and JOB_ID_RE.fullmatch(root_job_id) is None:
        raise WakeRouterError("inbox root_job_id is malformed")
    stream_raw = item.get("workstream")
    stream = None if stream_raw in (None, "") else str(stream_raw).strip().lower()
    if stream is not None and WORKSTREAM_RE.fullmatch(stream) is None:
        # Agent OS labels such as WS:PROPHET-FUSION are not Wake Fabric aliases.
        stream = None
    return CanonicalInboxAttention(
        attention_id=attention_id,
        kind=str(item.get("kind") or "").strip(),
        target=target,
        source=str(item.get("source") or "").strip(),
        job_id=job_id,
        root_job_id=root_job_id,
        workstream=stream,
        reason=str(item.get("reason") or ""),
        existing_next_actions=tuple(str(entry) for entry in item.get("existing_next_actions") or ()),
        claimed_session_alias=str(item.get("claimed_session_alias") or ""),
        claimed_command=str(item.get("claimed_command") or ""),
        claimed_target_seat=str(item.get("claimed_target_seat") or ""),
        claimed_wake_kind=str(item.get("claimed_wake_kind") or ""),
        source_created_at=item.get("source_created_at"),
        emitted_at=item.get("emitted_at"),
    )


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
        attention = (
            item
            if isinstance(item, CanonicalInboxAttention)
            else admit_inbox_projection(item)
        )
        suppressed = _present(attention, _INERT_ATTENTION_FIELDS)
        if attention.kind not in INBOX_WAKE_KINDS:
            return WakeDecision(
                action=WakeAction.UNKNOWN_KIND,
                obligation=None,
                route=None,
                suppressed_inert_fields=suppressed,
                reason=f"unknown inbox kind {attention.kind!r} remains attention",
            )
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
        owner = str(fact.owner_seat or "").strip().lower()
        if owner not in SEATS:
            raise WakeRouterError(f"unsupported owner_seat {owner!r}")
        if not (
            event_type == "JOB_COMPLETED"
            and fact.review_required
            and not fact.review_job_exists
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
                declared_target_seat=owner,
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
    "admit_inbox_projection",
    "sibling_review_exists",
]
