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

from control_plane.executive_runtime import Event, Job, JobStatus
from control_plane.session_targets import (
    RouteRefusalError,
    RuntimeBinding,
    SessionTargetError,
    SessionTargetRegistry,
    WakeRoute,
    load_session_targets,
    route_obligation,
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
    UNROUTABLE = "UNROUTABLE"


_INBOX_CEO_KIND = "ceo_decision_pending"
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
    source_workstream: str | None = None
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
    source_workstream: str | None = None
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
    refusal: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action.value,
            "obligation": None if self.obligation is None else self.obligation.to_dict(),
            "route": None if self.route is None else self.route.to_dict(),
            "suppressed_inert_fields": list(self.suppressed_inert_fields),
            "reason": self.reason,
            "refusal": self.refusal,
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
    kind = str(item.get("kind") or "").strip()
    source = str(item.get("source") or "").strip()
    if kind == _INBOX_CEO_KIND:
        if source != "agent_os" or target != "ceo":
            raise WakeRouterError(
                "ceo_decision_pending must be Agent OS CEO attention"
            )
    elif kind in INBOX_WAKE_KINDS:
        if source != "runtime":
            raise WakeRouterError(
                f"inbox kind {kind!r} must be runtime-projected attention"
            )
    job_raw = item.get("job_id")
    job_id = None if job_raw in (None, "") else str(job_raw).strip()
    if job_id is not None and JOB_ID_RE.fullmatch(job_id) is None:
        raise WakeRouterError("inbox job_id is malformed")
    root_raw = item.get("root_job_id")
    root_job_id = None if root_raw in (None, "") else str(root_raw).strip()
    if root_job_id is not None and JOB_ID_RE.fullmatch(root_job_id) is None:
        raise WakeRouterError("inbox root_job_id is malformed")
    stream_raw = item.get("workstream")
    source_stream = None if stream_raw in (None, "") else str(stream_raw).strip()
    routing_stream = None
    if source_stream is not None and WORKSTREAM_RE.fullmatch(source_stream.lower()):
        routing_stream = source_stream.lower()
    return CanonicalInboxAttention(
        attention_id=attention_id,
        kind=kind,
        target=target,
        source=source,
        job_id=job_id,
        root_job_id=root_job_id,
        workstream=routing_stream,
        source_workstream=source_stream,
        reason=str(item.get("reason") or ""),
        existing_next_actions=tuple(str(entry) for entry in item.get("existing_next_actions") or ()),
        claimed_session_alias=str(item.get("claimed_session_alias") or ""),
        claimed_command=str(item.get("claimed_command") or ""),
        claimed_target_seat=str(item.get("claimed_target_seat") or ""),
        claimed_wake_kind=str(item.get("claimed_wake_kind") or ""),
        source_created_at=item.get("source_created_at"),
        emitted_at=item.get("emitted_at"),
    )


def obligation_from_inbox(item: CanonicalInboxAttention | Mapping[str, Any]) -> WakeObligation:
    attention = (
        item if isinstance(item, CanonicalInboxAttention) else admit_inbox_projection(item)
    )
    if attention.kind not in INBOX_WAKE_KINDS:
        raise WakeRouterError(f"unknown inbox kind {attention.kind!r} remains attention")
    try:
        return mint_obligation(
            wake_kind=attention.kind,
            source_kind=SourceKind.EXECUTIVE_INBOX_ATTENTION,
            source_ref=attention.attention_id,
            declared_target_seat=attention.target,
            job_id=attention.job_id,
            root_job_id=attention.root_job_id,
            workstream=attention.workstream,
            source_workstream=attention.source_workstream,
            source_created_at=attention.source_created_at,
            emitted_at=attention.emitted_at,
        )
    except WakeObligationError as exc:
        raise WakeRouterError(str(exc)) from exc


def obligation_from_runtime(fact: CanonicalRuntimeFact) -> WakeObligation | None:
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
        return None
    try:
        source_ref = runtime_source_ref(
            aggregate_type=fact.aggregate_type,
            aggregate_id=fact.aggregate_id,
            sequence=fact.sequence,
        )
        return mint_obligation(
            wake_kind=WakeKind.REVIEW_REQUIRED,
            source_kind=SourceKind.EXECUTIVE_RUNTIME_EVENT,
            source_ref=source_ref,
            declared_target_seat=owner,
            job_id=fact.job_id,
            attempt_id=fact.attempt_id,
            root_job_id=fact.root_job_id,
            workstream=fact.workstream,
            source_workstream=fact.source_workstream,
            source_created_at=fact.source_created_at,
            emitted_at=fact.emitted_at,
        )
    except WakeObligationError as exc:
        raise WakeRouterError(str(exc)) from exc


def admit_runtime_review_source(
    *,
    event: Event,
    job: Job,
    sibling_jobs: Sequence[Job] = (),
) -> CanonicalRuntimeFact:
    """Admit typed Phase 1F Job+Event state.  Callers cannot claim owner/review independently."""

    if event.aggregate_type != "job":
        raise WakeRouterError("runtime review source aggregate_type must be job")
    if event.aggregate_id != job.job_id:
        raise WakeRouterError("runtime event aggregate_id must equal job.job_id")
    if int(event.sequence) < 1:
        raise WakeRouterError("runtime event sequence must be >= 1")
    if event.event_type != "JOB_COMPLETED":
        raise WakeRouterError("runtime review source must be JOB_COMPLETED")
    if job.status is not JobStatus.COMPLETED:
        raise WakeRouterError("runtime review source job.status must be COMPLETED")
    if job.review_required is not True:
        raise WakeRouterError("runtime review source requires review_required=True")
    root = str(job.root_job_id or "").strip()
    if JOB_ID_RE.fullmatch(root) is None:
        raise WakeRouterError("runtime review source requires canonical root_job_id")
    owner = str(job.owner_seat or "").strip().lower()
    if owner not in SEATS:
        raise WakeRouterError("runtime review source owner_seat is not a canonical seat")
    exists = sibling_review_exists(
        builder_job_id=job.job_id,
        review_jobs=[{"reviews_job_id": sibling.reviews_job_id} for sibling in sibling_jobs],
    )
    routing = None
    source_stream = None
    return CanonicalRuntimeFact(
        aggregate_type="job",
        aggregate_id=job.job_id,
        sequence=int(event.sequence),
        event_type=event.event_type,
        owner_seat=owner,
        review_job_exists=exists,
        job_id=job.job_id,
        root_job_id=root,
        workstream=routing,
        source_workstream=source_stream,
        review_required=True,
        reviews_job_id=job.reviews_job_id,
        escalation_target=str(job.escalation_target or "coo"),
        source_created_at=event.created_at,
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
        obligation = obligation_from_inbox(attention)
        return self._routed(obligation, suppressed, binding=binding)

    def from_runtime(
        self,
        fact: CanonicalRuntimeFact,
        *,
        binding: RuntimeBinding | None = None,
    ) -> WakeDecision:
        suppressed = _present(fact, _INERT_RUNTIME_FIELDS)
        obligation = obligation_from_runtime(fact)
        if obligation is None:
            return WakeDecision(
                action=WakeAction.NO_WAKE,
                obligation=None,
                route=None,
                suppressed_inert_fields=suppressed,
                reason="canonical runtime fact does not require an executive wake",
            )
        return self._routed(obligation, suppressed, binding=binding)

    def _routed(
        self,
        obligation: WakeObligation,
        suppressed: tuple[str, ...],
        *,
        binding: RuntimeBinding | None,
    ) -> WakeDecision:
        try:
            route = route_obligation(obligation, self.registry, binding=binding)
        except RouteRefusalError as exc:
            return WakeDecision(
                action=WakeAction.UNROUTABLE,
                obligation=obligation,
                route=None,
                suppressed_inert_fields=suppressed,
                reason="canonical source requires a wake obligation",
                refusal=str(exc),
            )
        except SessionTargetError as exc:
            return WakeDecision(
                action=WakeAction.UNROUTABLE,
                obligation=obligation,
                route=None,
                suppressed_inert_fields=suppressed,
                reason="canonical source requires a wake obligation",
                refusal=str(exc),
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
    "admit_runtime_review_source",
    "obligation_from_inbox",
    "obligation_from_runtime",
    "sibling_review_exists",
]
