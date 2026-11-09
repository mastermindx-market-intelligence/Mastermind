"""Supervisor-side composition: child-request admission → placement Job.

WHAT IS MISSING IN THE RUNTIME (recorded honestly, not papered over):
``JobRegistry.admit_child_execution_request`` admits an idempotent
child-request and creates an admission-ledger Job whose constraints are
``{"required_capabilities": ["read"]}`` — a record of WHO ASKED, not a
unit of placement.  ``AttemptRegistry.claim_job``'s placement authority
(placement observations, fabric placement intent, the C v1.1 native
binding join) composes ONLY with a Job carrying a ``child_placement``
constraint spec.  There is no runtime seam that turns an admitted child
request into that placement Job; the two lanes are deliberately separate.

This module is the SMALLEST honest composition across that gap, used by
the E2E proof and any supervisor that drives a Hermes/T3 handoff to a
real claim:

  1. admit the request through the real idempotent admission API (NM-14
     semantics — replay is a REPLAY, a different digest under the same
     triple is a typed CHILD_REQUEST_DIGEST_CONFLICT, concurrent
     duplicates arbitrate on the events table's UNIQUE command id);
  2. create the placement Job under its own deterministic command id
     (``child-placement:<sha256(triple)>``) embedding the SAME request;
     a replay of the handoff reconciles to the surviving Job instead of
     minting a second one (the same UNIQUE invariant arbitrates).

Nothing here changes claim, placement, binding or seal law; it composes
existing, separately tested seams and owns no new state.
"""
from __future__ import annotations

import dataclasses
from hashlib import sha256
from typing import Any

from control_plane.child_execution_contracts import ChildExecutionRequest
from control_plane.child_request_admission import admission_command_id
from control_plane.executive_runtime import JobStatus, StateConflict

#: Provenance schema of the composed placement Job.
CHILD_PLACEMENT_COMPOSITION_SCHEMA = "mastermind.child_request_execution_composition/v1"


def placement_command_id(request: ChildExecutionRequest) -> str:
    """Deterministic durable command id of the placement Job for one triple.

    Mirrors ``admission_command_id``: the same idempotency triple maps to
    one command id, so the events table's UNIQUE command id arbitrates a
    concurrent duplicate composition atomically — exactly one placement
    Job can ever exist per triple.
    """
    material = "\x1f".join(request.idempotency_key())
    return "child-placement:" + sha256(material.encode("utf-8")).hexdigest()


@dataclasses.dataclass(frozen=True)
class ChildExecutionComposition:
    """Result of composing one child-request handoff.

    ``ready_to_claim`` is False when the placement Job already carries an
    attempt (a replayed handoff after claim/seal): the caller reconciles
    to the existing attempt and never claims or launches again.
    """

    admission: Any  # AdmissionOutcome (ADMITTED or REPLAY)
    placement_job: Any  # Job
    placement_created: bool
    ready_to_claim: bool


def compose_child_execution(
    runtime: Any,
    *,
    request: ChildExecutionRequest,
    spec: dict[str, Any],
    branch: str | None = None,
) -> ChildExecutionComposition:
    """Admit one child request and prepare its placement Job.

    ``branch`` names the source branch the child works on (used by the
    post-seal GitHub evidence read); it is placement metadata, never
    authority.

    Raises ``StateConflict(CHILD_REQUEST_DIGEST_CONFLICT...)`` unchanged
    when the triple was admitted with a different digest — the typed
    refusal the negative matrix requires, never a second Job.
    """
    outcome = runtime.jobs.admit_child_execution_request(request)
    command_id = placement_command_id(request)
    objective = (
        f"[child-placement] key={request.logical_child_key} "
        f"root={request.root_ref} parent={request.immediate_parent_run_ref} "
        f"digest={request.request_digest[:12]}"
    )
    provenance = {
        "child_placement_composition": {
            "schema": CHILD_PLACEMENT_COMPOSITION_SCHEMA,
            "admission_command_id": admission_command_id(request),
            "request_digest": request.request_digest,
        },
    }
    try:
        job = runtime.jobs.create_job(
            objective,
            constraints={"child_placement": spec},
            attempt_limit=1,
            command_id=command_id,
            provenance=provenance,
            branch=branch,
        )
        created = True
    except StateConflict:
        # A concurrent or replayed composition of the SAME handoff: the
        # events UNIQUE command id kept exactly one Job; reconcile to it.
        event = runtime.store.get_event_by_command_id(command_id)
        if event is None or event.event_type != "JOB_CREATED":
            raise
        job = runtime.jobs.get_job(str(event.job_id))
        if job is None:
            raise
        created = False
    ready_to_claim = (
        job.status is JobStatus.QUEUED and not job.current_attempt_id
    )
    return ChildExecutionComposition(
        admission=outcome,
        placement_job=job,
        placement_created=created,
        ready_to_claim=ready_to_claim,
    )


__all__ = [
    "CHILD_PLACEMENT_COMPOSITION_SCHEMA",
    "ChildExecutionComposition",
    "compose_child_execution",
    "placement_command_id",
]
