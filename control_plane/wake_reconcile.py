"""Deterministic Wake reconciliation — snapshot, plan, apply.

Source reads happen before any ``BEGIN IMMEDIATE``.  Automatic apply writes
only ``WAKE_REQUESTED`` and ``SOURCE_RESOLVED``.  No routing, transport,
delivery attempt, or acknowledgement.
"""
from __future__ import annotations

import dataclasses
import hashlib
from typing import Mapping, Sequence

from control_plane.executive_inbox import (
    BOOT_PACKET_SCHEMA,
    SCHEMA as INBOX_SCHEMA,
    build_inbox,
)
from control_plane.executive_runtime import (
    Job,
    JobStatus,
    Runtime,
    StateConflict,
)
from control_plane.wake_events import INBOX_WAKE_KINDS, WakeObligation, canonical_json_bytes
from control_plane.wake_ledger import (
    LedgerPhase,
    ObligationStatus,
    SourceReadHealth,
    WAKE_AGGREGATE_TYPE,
    WakeLedgerError,
    WakeLedgerRecord,
    expected_resolution_code,
    identity_payload,
    reconstruct_status,
    requested_record,
    resolve_source,
    resolved_record,
)
from control_plane.wake_persist import PersistedWakeEvent, WakeLedgerRepository
from control_plane.wake_router import (
    WakeRouterError,
    admit_inbox_projection,
    admit_runtime_review_source,
    obligation_from_inbox,
    obligation_from_runtime,
)


@dataclasses.dataclass(frozen=True)
class WakeSourceSnapshot:
    observed: tuple[WakeObligation, ...]
    runtime_health: SourceReadHealth
    inbox_runtime_health: SourceReadHealth
    agentos_health: SourceReadHealth
    degraded: tuple[str, ...]
    grounding: dict[str, object]
    digest: str
    unsupported_attention: tuple[str, ...] = ()
    contradictions: tuple[str, ...] = ()


@dataclasses.dataclass(frozen=True)
class WakeLedgerSnapshot:
    events: tuple[PersistedWakeEvent, ...]
    by_obligation: dict[str, tuple[PersistedWakeEvent, ...]]
    contradictions: tuple[str, ...] = ()


@dataclasses.dataclass(frozen=True)
class WakeReconcilePlan:
    to_request: tuple[WakeObligation, ...]
    already_requested: tuple[str, ...]
    to_resolve: tuple[WakeObligation, ...]
    already_closed: tuple[str, ...]
    unsupported_attention: tuple[str, ...]
    degraded: tuple[str, ...]
    contradictions: tuple[str, ...]


@dataclasses.dataclass(frozen=True)
class WakeReconcileResult:
    snapshot: WakeSourceSnapshot
    plan: WakeReconcilePlan
    requested: tuple[str, ...]
    resolved: tuple[str, ...]
    transport_invocations: int = 0
    delivery_attempts: int = 0


def collect_source_snapshot(
    runtime: Runtime,
    *,
    boot_packet: Mapping[str, object] | None = None,
    include_boot_packet: bool = True,
) -> WakeSourceSnapshot:
    """Read canonical sources.  Never opens a write transaction."""

    degraded: list[str] = []
    observed: list[WakeObligation] = []
    unsupported: list[str] = []
    runtime_health = SourceReadHealth.HEALTHY
    jobs: list[Job] = []
    try:
        jobs = list(runtime.jobs.list_jobs())
        observed.extend(_runtime_review_obligations(runtime, jobs))
    except Exception as exc:
        runtime_health = SourceReadHealth.DEGRADED
        degraded.append(f"runtime source unreadable: {type(exc).__name__}")

    inbox = build_inbox(
        repo_root=runtime.store.root,
        boot_packet=boot_packet,
        include_boot_packet=include_boot_packet,
        environ={},
    )
    inbox_degraded = tuple(str(item) for item in (inbox.get("degraded") or ()))
    degraded.extend(inbox_degraded)
    admission_uncertain = inbox.get("schema") != INBOX_SCHEMA
    if inbox.get("schema") != INBOX_SCHEMA:
        degraded.append(
            f"inbox schema is {inbox.get('schema')!r}, expected {INBOX_SCHEMA!r}"
        )
        admission_uncertain = True
    else:
        for item in inbox.get("attention") or ():
            if not isinstance(item, Mapping):
                unsupported.append("inbox attention row is not a mapping")
                admission_uncertain = True
                continue
            try:
                attention = admit_inbox_projection(item)
            except WakeRouterError as exc:
                aid = str(item.get("attention_id") or "").strip()
                unsupported.append(aid or f"{item.get('kind') or 'unknown'}:{exc.__class__.__name__}")
                admission_uncertain = True
                continue
            if attention.kind == "review_required":
                unsupported.append("inbox review_required is not a runtime-direct source")
                continue
            if attention.kind not in INBOX_WAKE_KINDS:
                unsupported.append(attention.kind or "unknown")
                admission_uncertain = True
                continue
            try:
                observed.append(obligation_from_inbox(attention))
            except WakeRouterError as exc:
                unsupported.append(f"{attention.kind}:{exc.__class__.__name__}")
                admission_uncertain = True
    grounding_raw = inbox.get("grounding") if isinstance(inbox.get("grounding"), Mapping) else {}
    runtime_db = grounding_raw.get("runtime_db") if isinstance(grounding_raw.get("runtime_db"), Mapping) else {}
    runtime_counts = (
        inbox.get("runtime_counts") if isinstance(inbox.get("runtime_counts"), Mapping) else {}
    )
    jobs_projected = runtime_counts.get("jobs") is not None
    inbox_runtime_health = (
        SourceReadHealth.DEGRADED
        if admission_uncertain or not jobs_projected or not runtime_db.get("present")
        else SourceReadHealth.HEALTHY
    )
    agentos_health = (
        SourceReadHealth.HEALTHY
        if grounding_raw.get("boot_packet_schema") == BOOT_PACKET_SCHEMA
        and inbox.get("schema") == INBOX_SCHEMA
        and not admission_uncertain
        else SourceReadHealth.DEGRADED
    )

    unique: dict[str, WakeObligation] = {}
    dropped: set[str] = set()
    contradictions: list[str] = []
    for obligation in observed:
        oid = obligation.obligation_id
        if oid in dropped:
            continue
        previous = unique.get(oid)
        if previous is None:
            unique[oid] = obligation
            continue
        if identity_payload(previous) == identity_payload(obligation):
            continue
        unique.pop(oid, None)
        dropped.add(oid)
        contradictions.append(f"{oid}:disagreeing observed envelope")
    ordered = tuple(sorted(unique.values(), key=lambda item: item.obligation_id))
    grounding = {
        "runtime_root": str(runtime.store.root),
        "inbox_schema": inbox.get("schema"),
        "boot_packet_schema": grounding_raw.get("boot_packet_schema"),
        "observed_count": len(ordered),
    }
    digest = hashlib.sha256(
        canonical_json_bytes(
            {
                "observed": [item.obligation_id for item in ordered],
                "degraded": degraded,
                "runtime_health": runtime_health.value,
                "inbox_runtime_health": inbox_runtime_health.value,
                "agentos_health": agentos_health.value,
            }
        )
    ).hexdigest()[:16]
    return WakeSourceSnapshot(
        observed=ordered,
        runtime_health=runtime_health,
        inbox_runtime_health=inbox_runtime_health,
        agentos_health=agentos_health,
        degraded=tuple(degraded),
        grounding=grounding,
        digest=digest,
        unsupported_attention=tuple(unsupported),
        contradictions=tuple(contradictions),
    )


def collect_ledger_snapshot(runtime: Runtime) -> WakeLedgerSnapshot:
    repo = WakeLedgerRepository(runtime)
    wake_events = runtime.events.list_events(aggregate_type=WAKE_AGGREGATE_TYPE)
    stolen = runtime.events.list_events(command_id_prefix="WAKE-")
    hydrated: list[PersistedWakeEvent] = []
    contradictions: list[str] = []
    grouped: dict[str, list[PersistedWakeEvent]] = {}
    for event in stolen:
        if event.aggregate_type != WAKE_AGGREGATE_TYPE:
            contradictions.append(
                f"{event.command_id}:foreign Executive event stole a Wake command id"
            )
    for event in wake_events:
        try:
            item = repo._hydrate(event)
        except (WakeLedgerError, StateConflict) as exc:
            contradictions.append(f"{event.command_id}:{exc}")
            continue
        hydrated.append(item)
        grouped.setdefault(event.aggregate_id, []).append(item)
    by_obligation = {oid: tuple(items) for oid, items in grouped.items()}
    return WakeLedgerSnapshot(
        events=tuple(hydrated),
        by_obligation=by_obligation,
        contradictions=tuple(contradictions),
    )


def plan_wake_reconciliation(
    source_snapshot: WakeSourceSnapshot,
    ledger_snapshot: WakeLedgerSnapshot,
) -> WakeReconcilePlan:
    observed_ids = {item.obligation_id: item for item in source_snapshot.observed}
    to_request: list[WakeObligation] = []
    already_requested: list[str] = []
    to_resolve: list[WakeObligation] = []
    already_closed: list[str] = []
    contradictions = list(ledger_snapshot.contradictions) + list(
        source_snapshot.contradictions
    )

    known_ids = set(observed_ids) | set(ledger_snapshot.by_obligation)
    for oid in sorted(known_ids):
        if _contradicted(oid, contradictions):
            continue
        rows = ledger_snapshot.by_obligation.get(oid, ())
        records = tuple(item.record for item in rows)
        try:
            status = reconstruct_status(oid, records) if records else ObligationStatus.NOT_SEEN
        except WakeLedgerError as exc:
            contradictions.append(f"{oid}:{exc}")
            continue
        if status is ObligationStatus.SOURCE_RESOLVED:
            already_closed.append(oid)
            continue
        observed = observed_ids.get(oid)
        if observed is not None:
            if status is ObligationStatus.NOT_SEEN:
                to_request.append(observed)
            else:
                already_requested.append(oid)
            continue
        if status is ObligationStatus.NOT_SEEN:
            continue
        if status is not ObligationStatus.TARGET_ACKNOWLEDGED:
            # Delivery may close only after an exact ACK.  A healthy source
            # reread that no longer observes the obligation is not authority
            # to skip TARGET_ACKNOWLEDGED and write SOURCE_RESOLVED directly.
            already_requested.append(oid)
            continue
        stored = _obligation_from_rows(rows)
        if stored is None:
            contradictions.append(f"{oid}:WAKE_REQUESTED missing obligation envelope")
            continue
        if not _may_resolve(stored, source_snapshot):
            continue
        to_resolve.append(stored)
    return WakeReconcilePlan(
        to_request=tuple(to_request),
        already_requested=tuple(already_requested),
        to_resolve=tuple(to_resolve),
        already_closed=tuple(already_closed),
        unsupported_attention=source_snapshot.unsupported_attention,
        degraded=source_snapshot.degraded,
        contradictions=tuple(contradictions),
    )


def apply_wake_reconciliation(
    runtime: Runtime,
    plan: WakeReconcilePlan,
    *,
    source_snapshot: WakeSourceSnapshot,
    boot_packet: Mapping[str, object] | None = None,
    include_boot_packet: bool = True,
) -> WakeReconcileResult:
    live = collect_source_snapshot(
        runtime, boot_packet=boot_packet, include_boot_packet=include_boot_packet
    )
    live_ids = {item.obligation_id for item in live.observed}
    repo = WakeLedgerRepository(runtime)
    writes: list[tuple[WakeLedgerRecord, WakeObligation | None]] = []
    requested_ids: list[str] = []
    resolved_ids: list[str] = []
    for obligation in plan.to_request:
        if obligation.obligation_id not in live_ids:
            continue
        writes.append((requested_record(obligation), obligation))
        requested_ids.append(obligation.obligation_id)
    for obligation in plan.to_resolve:
        if obligation.obligation_id in live_ids:
            continue
        if not _may_resolve(obligation, live):
            continue
        resolution = resolve_source(
            obligation,
            code=expected_resolution_code(obligation),
            health=SourceReadHealth.HEALTHY,
            source_present=False,
            snapshot_digest=live.digest,
            annotation=_resolution_annotation(obligation),
        )
        writes.append((resolved_record(obligation, resolution), obligation))
        resolved_ids.append(obligation.obligation_id)
    if writes:
        repo.append_records_atomic(writes)
    return WakeReconcileResult(
        snapshot=source_snapshot,
        plan=plan,
        requested=tuple(requested_ids),
        resolved=tuple(resolved_ids),
        transport_invocations=0,
        delivery_attempts=0,
    )


def reconcile_wakes(
    runtime: Runtime,
    *,
    boot_packet: Mapping[str, object] | None = None,
    include_boot_packet: bool = True,
) -> WakeReconcileResult:
    snapshot = collect_source_snapshot(
        runtime, boot_packet=boot_packet, include_boot_packet=include_boot_packet
    )
    ledger = collect_ledger_snapshot(runtime)
    plan = plan_wake_reconciliation(snapshot, ledger)
    return apply_wake_reconciliation(
        runtime,
        plan,
        source_snapshot=snapshot,
        boot_packet=boot_packet,
        include_boot_packet=include_boot_packet,
    )


def _runtime_review_obligations(runtime: Runtime, jobs: Sequence[Job]) -> list[WakeObligation]:
    candidates = [
        job
        for job in jobs
        if job.review_required is True and job.status is JobStatus.COMPLETED
    ]
    found: list[WakeObligation] = []
    for job in candidates:
        events = runtime.events.list_events(
            aggregate_type="job", aggregate_id=job.job_id
        )
        completed = [
            event
            for event in events
            if event.event_type == "JOB_COMPLETED"
        ]
        if not completed:
            continue
        event = completed[-1]
        try:
            fact = admit_runtime_review_source(event=event, job=job, sibling_jobs=tuple(jobs))
            obligation = obligation_from_runtime(fact)
        except WakeRouterError:
            continue
        if obligation is not None:
            found.append(obligation)
    return found


def _may_resolve(obligation: WakeObligation, snapshot: WakeSourceSnapshot) -> bool:
    if obligation.source_ref in snapshot.unsupported_attention:
        return False
    if obligation.wake_kind.value == "ceo_decision_pending":
        return False
    if obligation.source_kind.value == "executive_runtime_event":
        return snapshot.runtime_health is SourceReadHealth.HEALTHY
    return snapshot.inbox_runtime_health is SourceReadHealth.HEALTHY


def _resolution_annotation(obligation: WakeObligation) -> str:
    if obligation.wake_kind.value == "review_required":
        return "healthy runtime read: sibling review exists or review_required source is absent"
    return "healthy Inbox rebuild no longer contains this attention item"


def _obligation_from_rows(rows: Sequence[PersistedWakeEvent]) -> WakeObligation | None:
    for item in rows:
        if item.record.phase is LedgerPhase.WAKE_REQUESTED:
            return item.obligation
    return None


def _contradicted(obligation_id: str, contradictions: Sequence[str]) -> bool:
    return any(entry.split(":", 1)[0] == obligation_id for entry in contradictions)


__all__ = [
    "WakeLedgerSnapshot",
    "WakeReconcilePlan",
    "WakeReconcileResult",
    "WakeSourceSnapshot",
    "apply_wake_reconciliation",
    "collect_ledger_snapshot",
    "collect_source_snapshot",
    "plan_wake_reconciliation",
    "reconcile_wakes",
]
