"""Trusted host-side join from one candidate continuation to the Wake ledger.

This module owns no GitHub transport, observer, waiter, scheduler, watcher
database, Wake delivery, reasoning invocation, Runtime lifecycle, rerun,
merge, deploy, or result store.  It closes exactly one gap: it persists an
already-validated ``CandidateCIContinuationResult`` as one canonical
``WAKE_REQUESTED`` row in the existing Wake ledger, through the existing
``WakeLedgerRepository`` and the existing ``requested_record`` construction.

Identity, replay, and equality stay with their existing owners.  The Wake
obligation id is minted by ``wake_events`` from the observer decision's
canonical digest, so the same canonical observer decision always maps to the
same canonical obligation and a repeat delivery is a canonical replay rather
than a second event.  This module adds no second cache, lockfile, registry,
or lifecycle owner.

The caller must be the trusted host-side continuation owner. This adapter checks
canonical projection consistency; it does not authenticate the original root,
workstream, account or admission grant. A coherently reminted binding is still
caller input. Do not expose this function as a model-writable tool or use its
receipt as execution authority.

The function is a persistence join only.  It does not dispatch Wake, so its
receipt is explicitly not START, not wake-delivered, not worker-accepted, and
not parent-accepted.
"""
from __future__ import annotations

import dataclasses
from enum import Enum

from control_plane.executive_runtime import Runtime, StateConflict
from control_plane.github_ci_candidate_continuation import (
    SCHEMA as CONTINUATION_SCHEMA,
    CandidateCIContinuationResult,
)
from control_plane.github_ci_candidate_observer import (
    CandidateObserverDecision,
    CandidateObserverDisposition,
    CandidateObserverError,
    validate_candidate_observer_decision,
)
from control_plane.github_ci_candidate_waiter import (
    SCHEMA as WAITER_SCHEMA,
    CandidateWaitDisposition,
    CandidateWaitResult,
)
from control_plane.github_ci_candidate_wake import (
    CandidateCIWakeBinding,
    CandidateCIWakeError,
    obligation_from_candidate_ci,
)
from control_plane.wake_events import (
    SourceKind,
    WakeKind,
    WakeObligation,
    WakeObligationError,
    parse_obligation,
)
from control_plane.wake_ledger import WakeLedgerError, requested_record
from control_plane.wake_persist import PersistedWakeEvent, WakeLedgerRepository


SCHEMA = "mastermind.github_ci_candidate_delivery.v1"


class CandidateCIContinuationDeliveryError(ValueError):
    """The candidate continuation delivery was refused before any write.

    A refusal is deterministic: no Wake row was created, changed, or deleted.
    """


class CandidateCIContinuationDeliveryEffectUnknown(RuntimeError):
    """The candidate continuation write outcome has not been established.

    The canonical obligation identity is unchanged and is carried on this
    error.  Reconcile the canonical Wake ledger against that exact obligation
    id; never resend this continuation under a different id.
    """

    def __init__(self, obligation_id: str, message: str) -> None:
        super().__init__(message)
        self.obligation_id = obligation_id


class CandidateCIContinuationDeliveryDisposition(str, Enum):
    """What the join did, and nothing beyond it."""

    MATERIAL_REQUESTED = "MATERIAL_REQUESTED"
    MATERIAL_ALREADY_PERSISTED = "MATERIAL_ALREADY_PERSISTED"
    QUIESCENT_NO_WRITE = "QUIESCENT_NO_WRITE"


@dataclasses.dataclass(frozen=True)
class CandidateCIContinuationDelivery:
    """Canonical persisted evidence for one candidate continuation.

    ``inserted`` is True only when this call created the canonical
    ``WAKE_REQUESTED`` row.  ``already_persisted`` is True when the canonical
    row already existed and was replayed unchanged.

    The four negative fields are the honest boundary of this join: it persists
    a Wake *request* and dispatches nothing.  It is not START, it is not
    wake-delivered, it is not worker-accepted, and it is not parent-accepted.
    """

    schema: str
    disposition: CandidateCIContinuationDeliveryDisposition
    obligation_id: str | None
    command_id: str | None
    event_id: int | None
    inserted: bool
    already_persisted: bool
    persisted: PersistedWakeEvent | None
    start_issued: bool = False
    wake_delivered: bool = False
    worker_accepted: bool = False
    parent_accepted: bool = False


def persist_candidate_continuation(
    runtime: Runtime,
    result: CandidateCIContinuationResult,
) -> CandidateCIContinuationDelivery:
    """Persist one validated candidate continuation as one canonical Wake request.

    A quiescent exhaustion writes nothing at all.  A material continuation
    writes exactly one ``WAKE_REQUESTED`` row for the canonical obligation the
    observer decision already identified; a repeat delivery of the same
    decision replays that same row instead of creating a second one.

    This function never dispatches Wake and never accepts a caller-supplied
    transport, native session, action argv, provider, schedule, or credential.
    The material binding is whatever the trusted continuation owner already
    projected, re-checked here against the canonical COO target.
    """

    if not isinstance(runtime, Runtime):
        raise CandidateCIContinuationDeliveryError(
            "candidate continuation delivery requires an Executive Runtime"
        )

    obligation = _validated_obligation(result)
    if obligation is None:
        return CandidateCIContinuationDelivery(
            schema=SCHEMA,
            disposition=CandidateCIContinuationDeliveryDisposition.QUIESCENT_NO_WRITE,
            obligation_id=None,
            command_id=None,
            event_id=None,
            inserted=False,
            already_persisted=False,
            persisted=None,
        )

    # Pure construction precedes the durable-effect boundary. A constructor
    # failure has not attempted a ledger write and must not be called unknown.
    try:
        record = requested_record(obligation)
    except Exception as exc:
        raise CandidateCIContinuationDeliveryError(
            "candidate request construction failed before write"
        ) from exc
    repository = WakeLedgerRepository(runtime)
    try:
        persisted = repository.append_record(
            record,
            obligation=obligation,
        )
    except (WakeLedgerError, StateConflict) as exc:
        # Deterministic refusal: the canonical ledger declined this exact
        # request, so no row was created, changed, or deleted.
        raise CandidateCIContinuationDeliveryError(
            f"wake ledger refused the canonical candidate request: {exc}"
        ) from exc
    except Exception as exc:
        # The durable effect is not established.  The canonical obligation id
        # is unchanged and must be reconciled against that exact id.
        raise CandidateCIContinuationDeliveryEffectUnknown(
            obligation.obligation_id,
            "candidate continuation write did not establish a durable effect; "
            "reconcile the canonical wake ledger against this obligation id "
            "and never resend it under a different id",
        ) from exc

    return CandidateCIContinuationDelivery(
        schema=SCHEMA,
        disposition=(
            CandidateCIContinuationDeliveryDisposition.MATERIAL_REQUESTED
            if persisted.inserted
            else CandidateCIContinuationDeliveryDisposition.MATERIAL_ALREADY_PERSISTED
        ),
        obligation_id=obligation.obligation_id,
        command_id=persisted.event.command_id,
        event_id=persisted.event.event_id,
        inserted=persisted.inserted,
        already_persisted=not persisted.inserted,
        persisted=persisted,
    )


def _validated_obligation(
    result: CandidateCIContinuationResult,
) -> WakeObligation | None:
    """Return the canonical obligation to persist, or None for a quiescent end.

    Every refusal happens here, before any write.
    """

    if type(result) is not CandidateCIContinuationResult:
        raise CandidateCIContinuationDeliveryError(
            "candidate continuation result has the wrong exact type"
        )
    if result.schema != CONTINUATION_SCHEMA:
        raise CandidateCIContinuationDeliveryError(
            "candidate continuation result schema is not canonical"
        )

    waited = result.wait_result
    if type(waited) is not CandidateWaitResult:
        raise CandidateCIContinuationDeliveryError(
            "candidate wait result has the wrong exact type"
        )
    if waited.schema != WAITER_SCHEMA:
        raise CandidateCIContinuationDeliveryError(
            "candidate wait result schema is not canonical"
        )

    disposition = waited.disposition
    if disposition is CandidateWaitDisposition.QUIESCENT_BUDGET_EXHAUSTED:
        if waited.decision is not None or result.wake_obligation is not None:
            raise CandidateCIContinuationDeliveryError(
                "quiescent candidate continuation carries wake evidence"
            )
        return None
    if disposition is not CandidateWaitDisposition.MATERIAL_RETURN:
        raise CandidateCIContinuationDeliveryError(
            "candidate wait disposition is not a canonical disposition"
        )

    decision = waited.decision
    if type(decision) is not CandidateObserverDecision:
        raise CandidateCIContinuationDeliveryError(
            "material candidate continuation has no exact observer decision"
        )
    if decision.disposition is CandidateObserverDisposition.QUIESCENT:
        raise CandidateCIContinuationDeliveryError(
            "quiescent observer decision cannot request a wake"
        )
    if not waited.wake_reasoning:
        raise CandidateCIContinuationDeliveryError(
            "material candidate continuation does not wake reasoning"
        )
    try:
        validated = validate_candidate_observer_decision(decision)
    except CandidateObserverError as exc:
        raise CandidateCIContinuationDeliveryError(
            f"observer decision is not canonical: {exc}"
        ) from exc
    if validated.observer_id != waited.observer_id:
        raise CandidateCIContinuationDeliveryError(
            "observer decision does not match the wait observer identity"
        )
    if validated.current_digest != waited.latest_observation_digest:
        raise CandidateCIContinuationDeliveryError(
            "observer decision does not match the latest observation digest"
        )

    obligation = result.wake_obligation
    if type(obligation) is not WakeObligation:
        raise CandidateCIContinuationDeliveryError(
            "material candidate continuation has no exact wake obligation"
        )
    if obligation.wake_kind is not WakeKind.CI_CANDIDATE_MATERIAL:
        raise CandidateCIContinuationDeliveryError(
            "wake obligation kind is not the candidate material kind"
        )
    if obligation.source_kind is not SourceKind.GITHUB_CI_CANDIDATE_OBSERVATION:
        raise CandidateCIContinuationDeliveryError(
            "wake obligation source is not the candidate observation source"
        )
    try:
        canonical = parse_obligation(obligation.to_dict())
    except WakeObligationError as exc:
        raise CandidateCIContinuationDeliveryError(
            f"wake obligation envelope is not canonical: {exc}"
        ) from exc
    if canonical != obligation:
        raise CandidateCIContinuationDeliveryError(
            "wake obligation envelope is not the canonical projection"
        )

    try:
        projected = obligation_from_candidate_ci(
            validated,
            binding=_binding_from(canonical),
        )
    except CandidateCIWakeError as exc:
        raise CandidateCIContinuationDeliveryError(
            f"candidate wake projection refused: {exc}"
        ) from exc
    if projected != canonical:
        raise CandidateCIContinuationDeliveryError(
            "wake obligation is not the original projection of the decision"
        )
    return canonical


def _binding_from(obligation: WakeObligation) -> CandidateCIWakeBinding:
    """Recover the caller's asserted binding for projection consistency only.

    The seat, routing, source, root, and timestamps are read back off the
    canonical envelope.  The canonical COO target is not negotiable here: the
    existing wake owner refuses any other seat. This is not independent proof
    of that root's admission or the caller's permission to write it.
    """

    return CandidateCIWakeBinding(
        target_seat=obligation.declared_target_seat,
        routing_workstream=obligation.workstream,
        source_workstream=obligation.source_workstream,
        root_job_id=obligation.root_job_id,
        source_created_at=obligation.source_created_at,
        emitted_at=obligation.emitted_at,
    )


__all__ = [
    "SCHEMA",
    "CandidateCIContinuationDelivery",
    "CandidateCIContinuationDeliveryDisposition",
    "CandidateCIContinuationDeliveryEffectUnknown",
    "CandidateCIContinuationDeliveryError",
    "persist_candidate_continuation",
]
