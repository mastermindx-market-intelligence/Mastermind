"""Source-safe Wake projection for material exact-candidate CI observations.

This module is an adapter into the existing Wake Fabric. It owns no sampler,
watcher registry, timer, persistence, GitHub client, retry policy, routing
registry, transport, or reasoning lifecycle.
"""
from __future__ import annotations

import dataclasses
from typing import Any

from control_plane.github_ci_candidate_observer import (
    CandidateObserverDecision,
    CandidateObserverDisposition,
    CandidateObserverError,
    validate_candidate_observer_decision,
)
from control_plane.wake_events import (
    SourceKind,
    WakeKind,
    WakeObligation,
    WakeObligationError,
    mint_obligation,
)


class CandidateCIWakeError(ValueError):
    """The material CI decision cannot lawfully enter Wake Fabric."""


@dataclasses.dataclass(frozen=True)
class CandidateCIWakeBinding:
    """Trusted host-side return facts, never model-selectable CI semantics."""

    target_seat: str
    routing_workstream: str | None
    source_workstream: str | None
    root_job_id: str | None
    source_created_at: str | None
    emitted_at: str


def _binding(value: Any) -> CandidateCIWakeBinding:
    if type(value) is not CandidateCIWakeBinding:
        raise CandidateCIWakeError("candidate CI wake binding has wrong exact type")
    if value.target_seat != "coo":
        raise CandidateCIWakeError("candidate CI material return is COO-bound")
    if not isinstance(value.emitted_at, str) or not value.emitted_at:
        raise CandidateCIWakeError("candidate CI wake binding requires emitted_at")
    return value


def github_ci_source_ref(decision: CandidateObserverDecision) -> str:
    """Bind one material return to the observer decision's canonical digest."""

    try:
        validated = validate_candidate_observer_decision(decision)
    except CandidateObserverError as exc:
        raise CandidateCIWakeError(str(exc)) from exc
    return f"github_ci_candidate:{validated.canonical_digest}"


def obligation_from_candidate_ci(
    decision: CandidateObserverDecision,
    *,
    binding: CandidateCIWakeBinding,
) -> WakeObligation:
    """Mint one Wake obligation for a material/terminal H5 observer return.

    Quiescent samples are not wake sources. Route selection and delivery remain
    with SessionTargetRegistry / Wake Fabric after this source projection.
    """

    trusted = _binding(binding)
    try:
        current = validate_candidate_observer_decision(decision)
    except CandidateObserverError as exc:
        raise CandidateCIWakeError(str(exc)) from exc

    if (
        current.disposition is CandidateObserverDisposition.QUIESCENT
        or current.wake_reasoning is not True
    ):
        raise CandidateCIWakeError("quiescent candidate CI observation cannot wake reasoning")

    source_ref = github_ci_source_ref(current)
    try:
        return mint_obligation(
            wake_kind=WakeKind.CI_CANDIDATE_MATERIAL,
            source_kind=SourceKind.GITHUB_CI_CANDIDATE_OBSERVATION,
            source_ref=source_ref,
            declared_target_seat=trusted.target_seat,
            root_job_id=trusted.root_job_id,
            workstream=trusted.routing_workstream,
            source_workstream=trusted.source_workstream,
            source_created_at=trusted.source_created_at,
            emitted_at=trusted.emitted_at,
        )
    except WakeObligationError as exc:
        raise CandidateCIWakeError(str(exc)) from exc


__all__ = [
    "CandidateCIWakeBinding",
    "CandidateCIWakeError",
    "github_ci_source_ref",
    "obligation_from_candidate_ci",
]
