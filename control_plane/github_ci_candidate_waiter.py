"""Process-local exact-candidate waiter for H5 GitHub CI continuation.

This is a Class-T/Class-E compatible blocking primitive over owner-native
CandidateCIObservation snapshots. It owns no GitHub transport, persistence,
watcher database, scheduler, Wake delivery, reasoning invocation, rerun, merge,
deploy, Runtime Job, or Executive lifecycle state.

Registration is process-local and disappears on restart. The canonical
candidate identity and material-change semantics remain in
github_ci_candidate_observer; this module only prevents duplicate active waits
inside one host process and suppresses unchanged samples.
"""
from __future__ import annotations

import dataclasses
import secrets
from enum import Enum
from typing import Callable

from control_plane.github_ci_candidate_observer import (
    CandidateObserverDecision,
    CandidateObserverDisposition,
    CandidateObserverError,
    key_for_observation,
    observe_candidate_transition,
    observer_id,
    validate_candidate_observer_decision,
)
from control_plane.github_release_assessment import CandidateCIObservation

SCHEMA = "mastermind.github_ci_candidate_waiter.v1"

class CandidateWaiterError(ValueError):
    """One exact-candidate waiter operation was refused."""


class CandidateWaiterConflict(CandidateWaiterError):
    """Another active waiter already owns this exact candidate."""


class CandidateWaitDisposition(str, Enum):
    MATERIAL_RETURN = "MATERIAL_RETURN"
    QUIESCENT_BUDGET_EXHAUSTED = "QUIESCENT_BUDGET_EXHAUSTED"


@dataclasses.dataclass(frozen=True)
class CandidateWaiterRegistration:
    observer_id: str
    token: str


@dataclasses.dataclass(frozen=True)
class CandidateWaitResult:
    schema: str
    observer_id: str
    disposition: CandidateWaitDisposition
    sample_count: int
    latest_observation_digest: str
    decision: CandidateObserverDecision | None

    @property
    def wake_reasoning(self) -> bool:
        return (
            self.disposition is CandidateWaitDisposition.MATERIAL_RETURN
            and self.decision is not None
            and self.decision.wake_reasoning
        )


class CandidateWaiterRegistry:
    """One process-local exact-candidate registration set."""

    def __init__(self, *, token_factory: Callable[[], str] | None = None) -> None:
        self._token_factory = token_factory or (lambda: secrets.token_urlsafe(24))
        if not callable(self._token_factory):
            raise CandidateWaiterError("token_factory must be callable")
        self._tokens: dict[str, str] = {}
        self._retired_tokens: set[str] = set()

    def register(self, observation: CandidateCIObservation) -> CandidateWaiterRegistration:
        try:
            oid = observer_id(key_for_observation(observation))
        except CandidateObserverError as exc:
            raise CandidateWaiterError(str(exc)) from exc
        if oid in self._tokens:
            raise CandidateWaiterConflict("candidate waiter already active")
        try:
            token = self._token_factory()
        except Exception as exc:
            raise CandidateWaiterError("candidate waiter token unavailable") from exc
        if (
            type(token) is not str
            or len(token) < 16
            or len(token) > 256
            or not token.isascii()
            or any(ch.isspace() for ch in token)
            or token in self._retired_tokens
            or token in self._tokens.values()
        ):
            raise CandidateWaiterError("candidate waiter token invalid or reused")
        self._tokens[oid] = token
        return CandidateWaiterRegistration(observer_id=oid, token=token)

    def is_active(self, observer: str) -> bool:
        return type(observer) is str and observer in self._tokens

    def unregister(self, registration: CandidateWaiterRegistration) -> bool:
        if type(registration) is not CandidateWaiterRegistration:
            raise CandidateWaiterError("registration has wrong exact type")
        current = self._tokens.get(registration.observer_id)
        if current != registration.token:
            return False
        del self._tokens[registration.observer_id]
        self._retired_tokens.add(registration.token)
        return True

    def active_count(self) -> int:
        return len(self._tokens)


Sample = Callable[[], CandidateCIObservation]
Wait = Callable[[], None]


def wait_for_candidate_material(
    baseline: CandidateCIObservation,
    *,
    sample: Sample,
    wait: Wait,
    registry: CandidateWaiterRegistry,
    max_samples: int,
) -> CandidateWaitResult:
    """Block on one exact candidate until a material return or bounded exhaustion.

    sample owns the GitHub read and must return a complete H5-A observation.
    wait owns cadence/blocking. This function never reads the clock itself, so
    the host controls Class-E/Class-T cadence without a reasoning polling loop.
    """

    if type(registry) is not CandidateWaiterRegistry:
        raise CandidateWaiterError("registry has wrong exact type")
    if not callable(sample) or not callable(wait):
        raise CandidateWaiterError("sample and wait must be callable")
    if type(max_samples) is not int or not 1 <= max_samples <= 120:
        raise CandidateWaiterError("max_samples must be an integer between 1 and 120")

    try:
        initial = observe_candidate_transition(baseline)
    except CandidateObserverError as exc:
        raise CandidateWaiterError(str(exc)) from exc
    if initial.disposition is not CandidateObserverDisposition.QUIESCENT:
        raise CandidateWaiterError(
            "baseline is already material; consume it before arming a waiter"
        )

    registration = registry.register(baseline)
    previous = baseline
    sample_count = 0
    try:
        for index in range(max_samples):
            if index:
                try:
                    wait()
                except Exception as exc:
                    raise CandidateWaiterError("candidate waiter cadence failed") from exc
            try:
                current = sample()
                decision = validate_candidate_observer_decision(
                    observe_candidate_transition(current, previous=previous)
                )
            except CandidateObserverError as exc:
                raise CandidateWaiterError(str(exc)) from exc
            sample_count += 1
            if decision.observer_id != registration.observer_id:
                raise CandidateWaiterError("candidate waiter identity changed")
            if decision.disposition is not CandidateObserverDisposition.QUIESCENT:
                return CandidateWaitResult(
                    schema=SCHEMA,
                    observer_id=registration.observer_id,
                    disposition=CandidateWaitDisposition.MATERIAL_RETURN,
                    sample_count=sample_count,
                    latest_observation_digest=current.canonical_digest,
                    decision=decision,
                )
            previous = current

        return CandidateWaitResult(
            schema=SCHEMA,
            observer_id=registration.observer_id,
            disposition=CandidateWaitDisposition.QUIESCENT_BUDGET_EXHAUSTED,
            sample_count=sample_count,
            latest_observation_digest=previous.canonical_digest,
            decision=None,
        )
    finally:
        registry.unregister(registration)


__all__ = [
    "SCHEMA",
    "CandidateWaitDisposition",
    "CandidateWaitResult",
    "CandidateWaiterConflict",
    "CandidateWaiterError",
    "CandidateWaiterRegistration",
    "CandidateWaiterRegistry",
    "wait_for_candidate_material",
]
