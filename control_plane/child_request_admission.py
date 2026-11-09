"""Bounded, idempotent admission decisions for ``ChildExecutionRequest.v1``.

This module is the pure decision core for the Executive child-request
admission lane (Rev 4 §S1 l.56–65, §S2 "Queue and resource accounting"
l.101–105; work order WO-13).  It owns no store, no dispatcher, no lease
and no lifecycle: every input is either an immutable
:class:`~control_plane.child_execution_contracts.ChildExecutionRequest`
or plain numbers a caller read from its current Runtime transaction,
mirroring the contract of :mod:`control_plane.executive_coo_hierarchy`.

Law embedded here:

* **Idempotency is exactly-once.**  The child operation is idempotent
  within ``(root_ref, immediate_parent_run_ref, logical_child_key)``.
  A redelivery of the same triple with the same ``request_digest`` is a
  REPLAY returning the first admission's Job handle.  The same triple
  with a DIFFERENT digest is a CONFLICT — never a second Job, never a
  silent new execution (Rev 4 §S1 l.65).  Caller-supplied IDs are
  references, never credentials: none of them grants authority, and the
  digest is the only self-minted identity.
* **A full queue is backpressure, not an error and not a retry.**  When
  the per-root ready cap (default 32) or the fleet ready cap (default
  512) is reached, admission returns a precise WAIT reason for the
  parent planner.  The decision is a single synchronous answer; this
  module never loops, sleeps or re-queues.
* **Replay outranks the caps.**  A redelivery of an already-admitted
  request must always recover its existing handle, even when the queue
  is full — otherwise a network retry after a lost ACK would strand the
  caller outside the queue it already occupies.
* **Selection stays with the host.**  Nothing here names a worker,
  provider, host or account.  Admission queues bounded work; placement
  remains the incumbent claim/dispatch owner's separate decision
  (OQ-9: the envelope is a request; the host still selects).

Queue ordering (``select_next_ready``) is priority-first with bounded
aging, round-robin root fairness and skip-ineligible behaviour, so one
root's flood cannot starve another root and an ineligible head never
blocks the queue behind it.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from hashlib import sha256
from typing import Any, Mapping, Sequence

from control_plane.child_execution_contracts import (
    C0_MECHANICAL,
    C1_ROUTINE_BOUNDED,
    C2_COMPLEX_BOUNDED,
    C3_FRONTIER_JUDGMENT,
    REVIEW_LANE,
    ChildExecutionRequest,
)

__all__ = [
    "DEFAULT_FLEET_READY_LIMIT",
    "DEFAULT_ROOT_READY_LIMIT",
    "FLEET_READY_LIMIT_ENV",
    "ROOT_READY_LIMIT_ENV",
    "CHILD_QUEUE_ROOT_READY_FULL",
    "CHILD_QUEUE_FLEET_READY_FULL",
    "CHILD_REQUEST_DIGEST_CONFLICT",
    "ADMISSION_STATES",
    "ReadyQueuePolicy",
    "AdmissionOutcome",
    "ChildRequestAdmissionConflict",
    "ReadyQueueEntry",
    "admission_command_id",
    "request_priority",
    "decide_admission",
    "select_next_ready",
]

#: Rev 4 §S2 l.103: the proposed fleet-wide ready bound.
DEFAULT_FLEET_READY_LIMIT = 512
#: Rev 4 §S2 l.103: the proposed per-root ready bound.
DEFAULT_ROOT_READY_LIMIT = 32

FLEET_READY_LIMIT_ENV = "MMOS_CHILD_FLEET_READY_LIMIT"
ROOT_READY_LIMIT_ENV = "MMOS_CHILD_ROOT_READY_LIMIT"

#: Precise wait reasons returned to the parent planner (never a retry).
CHILD_QUEUE_ROOT_READY_FULL = "CHILD_QUEUE_ROOT_READY_FULL"
CHILD_QUEUE_FLEET_READY_FULL = "CHILD_QUEUE_FLEET_READY_FULL"
#: Same idempotency triple with a different request digest.
CHILD_REQUEST_DIGEST_CONFLICT = "CHILD_REQUEST_DIGEST_CONFLICT"

ADMISSION_STATES = ("ADMITTED", "REPLAY", "WAIT")

#: Queue-ordering defaults: one priority step per aging interval, capped,
#: so aging compensates starvation without ever outranking a full class.
DEFAULT_AGING_INTERVAL_SECONDS = 1800
DEFAULT_AGING_PRIORITY_STEP = 1
DEFAULT_AGING_PRIORITY_CAP = 3

#: Bounded priority mapping for the admitted class.  The reviewer lane
#: sits above complex-bounded work and below witnessed frontier judgment.
_COMPLEXITY_PRIORITY = {
    C0_MECHANICAL: 0,
    C1_ROUTINE_BOUNDED: 1,
    C2_COMPLEX_BOUNDED: 2,
    REVIEW_LANE: 3,
    C3_FRONTIER_JUDGMENT: 4,
}


class ChildRequestAdmissionConflict(ValueError):
    """Same idempotency triple redelivered with a different digest.

    This is never repaired by admitting a second Job: the caller must
    mint a new ``logical_child_key`` for genuinely different work.
    """


@dataclass(frozen=True)
class ReadyQueuePolicy:
    """The bounded ready-queue configuration (Rev 4 §S2 l.101–105).

    ``fleet_limit`` / ``root_limit`` bound how many admitted, not-yet-
    claimed child requests may wait simultaneously across the fleet and
    within one ``root_ref``.  Both are configurable through the
    environment so an operator can shrink them without a release.
    """

    fleet_limit: int = DEFAULT_FLEET_READY_LIMIT
    root_limit: int = DEFAULT_ROOT_READY_LIMIT
    aging_interval_seconds: int = DEFAULT_AGING_INTERVAL_SECONDS
    aging_priority_step: int = DEFAULT_AGING_PRIORITY_STEP
    aging_priority_cap: int = DEFAULT_AGING_PRIORITY_CAP
    root_fairness: bool = True

    def __post_init__(self) -> None:
        for name in ("fleet_limit", "root_limit"):
            value = getattr(self, name)
            if type(value) is not int or not 1 <= value <= 100_000:
                raise ValueError(f"{name} must be a positive integer")
        for name in ("aging_interval_seconds", "aging_priority_step"):
            value = getattr(self, name)
            if type(value) is not int or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        if type(self.aging_priority_cap) is not int or self.aging_priority_cap < 0:
            raise ValueError("aging_priority_cap must be a nonnegative integer")
        if type(self.root_fairness) is not bool:
            raise ValueError("root_fairness must be boolean")

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "ReadyQueuePolicy":
        source = os.environ if env is None else env
        values: dict[str, Any] = {}
        for key, env_name in (
            ("fleet_limit", FLEET_READY_LIMIT_ENV),
            ("root_limit", ROOT_READY_LIMIT_ENV),
        ):
            raw = source.get(env_name)
            if raw is None or str(raw).strip() == "":
                continue
            try:
                values[key] = int(str(raw).strip())
            except ValueError as exc:
                raise ValueError(
                    f"{env_name} must be an integer, got {raw!r}") from exc
        return cls(**values)


@dataclass(frozen=True)
class AdmissionOutcome:
    """One finite admission answer.

    ``state`` is one of ``ADMISSION_STATES``.  ``WAIT`` outcomes carry a
    precise ``wait_reason`` plus ``wait_detail`` for the parent planner;
    a CONFLICT is raised as :class:`ChildRequestAdmissionConflict`, never
    returned, so it can never be mistaken for a queued handle.
    """

    state: str
    command_id: str
    request_digest: str
    root_ref: str
    logical_child_key: str
    job_id: str | None = None
    wait_reason: str | None = None
    wait_detail: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.state not in ADMISSION_STATES:
            raise ValueError(f"unknown admission state {self.state!r}")
        if self.state == "WAIT":
            if not self.wait_reason:
                raise ValueError("a WAIT outcome requires a precise wait reason")
            if self.job_id is not None:
                raise ValueError("a WAIT outcome admits no Job")
        elif self.wait_reason is not None:
            raise ValueError("only a WAIT outcome carries a wait reason")


def admission_command_id(request: ChildExecutionRequest) -> str:
    """The deterministic durable command id for one idempotency triple.

    The triple (root, immediate parent, logical child key) maps to one
    command id, so the Runtime's existing ``events.command_id UNIQUE``
    invariant arbitrates concurrent duplicate admissions atomically —
    exactly one Job can ever be created per triple.
    """

    material = "\x1f".join(request.idempotency_key())
    return "child-request:" + sha256(material.encode("utf-8")).hexdigest()


def request_priority(request: ChildExecutionRequest) -> int:
    """Queue priority of the requested class (higher is served first).

    Business impact never feeds this value — consequence raises
    verification rigor, never scheduling strength.
    """

    return _COMPLEXITY_PRIORITY.get(request.requested_complexity, 0)


def decide_admission(
    request: ChildExecutionRequest,
    *,
    existing: tuple[str, str] | None,
    root_ready: int,
    fleet_ready: int,
    policy: ReadyQueuePolicy | None = None,
) -> AdmissionOutcome:
    """Decide one admission from pure facts; the caller owns durability.

    ``existing`` is the ``(job_id, request_digest)`` of a prior admis-
    sion under the same triple, or ``None``.  ``root_ready`` /
    ``fleet_ready`` are the current counts of admitted, not-yet-claimed
    child requests inside ``request.root_ref`` and across the fleet.
    """

    if not isinstance(request, ChildExecutionRequest):
        raise TypeError("decide_admission requires a ChildExecutionRequest")
    resolved = policy if policy is not None else ReadyQueuePolicy()
    command_id = admission_command_id(request)
    digest = request.request_digest
    common: dict[str, Any] = {
        "command_id": command_id,
        "request_digest": digest,
        "root_ref": request.root_ref,
        "logical_child_key": request.logical_child_key,
    }
    # Replay outranks the caps: a redelivery always recovers its handle.
    if existing is not None:
        job_id, existing_digest = existing
        if existing_digest == digest:
            return AdmissionOutcome(state="REPLAY", job_id=job_id, **common)
        raise ChildRequestAdmissionConflict(
            f"{CHILD_REQUEST_DIGEST_CONFLICT}: logical child key "
            f"{request.logical_child_key!r} under root {request.root_ref!r} "
            f"was admitted with digest {existing_digest!r}; this request "
            f"declares {digest!r} — a different task must use a new key")
    if root_ready >= resolved.root_limit:
        return AdmissionOutcome(
            state="WAIT", wait_reason=CHILD_QUEUE_ROOT_READY_FULL,
            wait_detail={
                "reason": CHILD_QUEUE_ROOT_READY_FULL,
                "root_ref": request.root_ref,
                "root_ready": int(root_ready),
                "root_limit": int(resolved.root_limit),
            },
            **common,
        )
    if fleet_ready >= resolved.fleet_limit:
        return AdmissionOutcome(
            state="WAIT", wait_reason=CHILD_QUEUE_FLEET_READY_FULL,
            wait_detail={
                "reason": CHILD_QUEUE_FLEET_READY_FULL,
                "fleet_ready": int(fleet_ready),
                "fleet_limit": int(resolved.fleet_limit),
            },
            **common,
        )
    return AdmissionOutcome(state="ADMITTED", **common)


@dataclass(frozen=True)
class ReadyQueueEntry:
    """One queued child request as observed by the queue's pop side."""

    job_id: str
    root_ref: str
    priority: int
    available_at_ms: int


def _effective_priority(
    entry: ReadyQueueEntry, *, now_ms: int, policy: ReadyQueuePolicy,
) -> int:
    age_seconds = max(0, int(now_ms) - int(entry.available_at_ms)) // 1000
    boost = min(
        policy.aging_priority_cap,
        (age_seconds // policy.aging_interval_seconds) * policy.aging_priority_step,
    )
    return int(entry.priority) + boost


def _ready(entry: ReadyQueueEntry, *, now_ms: int) -> bool:
    return int(entry.available_at_ms) <= int(now_ms)


def select_next_ready(
    entries: Sequence[ReadyQueueEntry | Mapping[str, Any]],
    *,
    now_ms: int,
    policy: ReadyQueuePolicy | None = None,
    eligible: Any = None,
) -> tuple[tuple[ReadyQueueEntry, ...], tuple[ReadyQueueEntry, ...]]:
    """Order the ready queue: priority, bounded aging, root fairness.

    Skip-ineligible: entries whose ``available_at_ms`` is in the future
    (or that fail the optional ``eligible`` predicate) are returned in
    ``skipped`` and never block the entries behind them.  Ordering is
    deterministic: effective priority first, then round-robin across
    roots (highest-priority waiting root first) so one root's flood
    cannot starve another, then age, then ``job_id``.
    """

    resolved = policy if policy is not None else ReadyQueuePolicy()
    queue: list[ReadyQueueEntry] = []
    skipped: list[ReadyQueueEntry] = []
    for value in entries:
        entry = value if isinstance(value, ReadyQueueEntry) else ReadyQueueEntry(
            job_id=str(value["job_id"]),
            root_ref=str(value["root_ref"]),
            priority=int(value.get("priority", 0)),
            available_at_ms=int(value.get("available_at_ms", 0)),
        )
        if not _ready(entry, now_ms=now_ms):
            skipped.append(entry)
            continue
        if eligible is not None and not eligible(entry):
            skipped.append(entry)
            continue
        queue.append(entry)
    by_root: dict[str, list[ReadyQueueEntry]] = {}
    for entry in queue:
        by_root.setdefault(entry.root_ref, []).append(entry)
    for bucket in by_root.values():
        bucket.sort(
            key=lambda item: (
                -_effective_priority(item, now_ms=now_ms, policy=resolved),
                item.available_at_ms,
                item.job_id,
            )
        )
    if not resolved.root_fairness:
        ordered = sorted(
            queue,
            key=lambda item: (
                -_effective_priority(item, now_ms=now_ms, policy=resolved),
                item.available_at_ms,
                item.job_id,
            ),
        )
        return tuple(ordered), tuple(skipped)
    # Round-robin interleave: repeatedly take each root's next entry,
    # roots ordered by the effective priority of their current head.
    remaining = {root: list(bucket) for root, bucket in by_root.items()}
    ordered: list[ReadyQueueEntry] = []
    while remaining:
        heads = {
            root: _effective_priority(bucket[0], now_ms=now_ms, policy=resolved)
            for root, bucket in remaining.items()
        }
        for root in sorted(remaining, key=lambda item: (-heads[item], item)):
            bucket = remaining[root]
            ordered.append(bucket.pop(0))
            if not bucket:
                del remaining[root]
            break
    return tuple(ordered), tuple(skipped)
