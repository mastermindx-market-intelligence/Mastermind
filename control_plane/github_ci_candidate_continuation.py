"""Pure H5 composition from exact-candidate wait to existing Wake obligation.

This module owns no GitHub transport, cadence, persistence, watcher database,
Wake delivery, reasoning invocation, Runtime lifecycle, rerun, merge, or deploy.
It composes the already-bounded waiter with the existing Wake projection.
"""
from __future__ import annotations

import dataclasses

from control_plane.github_ci_candidate_waiter import (
    CandidateWaitDisposition,
    CandidateWaitResult,
    CandidateWaiterError,
    CandidateWaiterRegistry,
    Sample,
    Wait,
    wait_for_candidate_material,
)
from control_plane.github_ci_candidate_wake import (
    CandidateCIWakeBinding,
    CandidateCIWakeError,
    obligation_from_candidate_ci,
)
from control_plane.github_release_assessment import CandidateCIObservation
from control_plane.wake_events import WakeObligation


SCHEMA = "mastermind.github_ci_candidate_continuation.v1"


class CandidateCIContinuationError(ValueError):
    """The exact-candidate continuation composition was refused."""


@dataclasses.dataclass(frozen=True)
class CandidateCIContinuationResult:
    schema: str
    wait_result: CandidateWaitResult
    wake_obligation: WakeObligation | None

    @property
    def material_return(self) -> bool:
        return self.wake_obligation is not None


def wait_for_candidate_continuation(
    baseline: CandidateCIObservation,
    *,
    sample: Sample,
    wait: Wait,
    registry: CandidateWaiterRegistry,
    max_samples: int,
    wake_binding: CandidateCIWakeBinding,
) -> CandidateCIContinuationResult:
    """Return quiescent exhaustion or one material Wake obligation.

    The injected sample owner supplies H5-A observations and the injected wait
    owner supplies Class-E/Class-T cadence. This function never reads GitHub or
    dispatches the returned Wake obligation.
    """

    try:
        waited = wait_for_candidate_material(
            baseline,
            sample=sample,
            wait=wait,
            registry=registry,
            max_samples=max_samples,
        )
    except CandidateWaiterError as exc:
        raise CandidateCIContinuationError(str(exc)) from exc

    if waited.disposition is CandidateWaitDisposition.QUIESCENT_BUDGET_EXHAUSTED:
        if waited.decision is not None or waited.wake_reasoning:
            raise CandidateCIContinuationError("quiescent waiter result is inconsistent")
        return CandidateCIContinuationResult(
            schema=SCHEMA,
            wait_result=waited,
            wake_obligation=None,
        )

    if (
        waited.disposition is not CandidateWaitDisposition.MATERIAL_RETURN
        or waited.decision is None
        or waited.wake_reasoning is not True
    ):
        raise CandidateCIContinuationError("material waiter result is inconsistent")

    try:
        obligation = obligation_from_candidate_ci(
            waited.decision,
            binding=wake_binding,
        )
    except CandidateCIWakeError as exc:
        raise CandidateCIContinuationError(str(exc)) from exc

    return CandidateCIContinuationResult(
        schema=SCHEMA,
        wait_result=waited,
        wake_obligation=obligation,
    )


__all__ = [
    "SCHEMA",
    "CandidateCIContinuationError",
    "CandidateCIContinuationResult",
    "wait_for_candidate_continuation",
]
