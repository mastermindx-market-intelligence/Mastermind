"""Deterministic material-change filter for one exact GitHub CI candidate.

This module composes the pure github_release_assessment candidate classifier.
It does not call GitHub, poll, sleep, schedule, persist, wake a model, register a
watcher, rerun CI, merge, deploy, or mutate Executive state.

A host-owned Class-E/Class-T observer may use the deterministic observer_id to
coalesce one observer per exact candidate and call observe_candidate_transition
for owner-native samples. Unchanged/progressive PENDING samples remain quiescent;
only terminal CI, stale-head, or observer-health transitions return as material.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import re
from enum import Enum
from typing import Any

from control_plane.github_release_assessment import (
    CandidateCIObservation,
    CandidateCIState,
    CheckIdentity,
)

SCHEMA = "mastermind.github_ci_candidate_observer.v1"
_ID_RE = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._/-]{0,255}\Z")
_SHA_RE = re.compile(r"\A[0-9a-f]{40}\Z")
_SHA256_RE = re.compile(r"\A[0-9a-f]{64}\Z")


class CandidateObserverError(ValueError):
    """The observation cannot belong to this exact observer generation."""


class CandidateObserverDisposition(str, Enum):
    QUIESCENT = "QUIESCENT"
    MATERIAL_RETURN = "MATERIAL_RETURN"
    TERMINAL_RETURN = "TERMINAL_RETURN"


@dataclasses.dataclass(frozen=True)
class CandidateObserverKey:
    repository: str
    repository_id: int
    pull_request_number: int
    candidate_ref: str
    expected_head_sha: str
    policy_revision: str
    required_checks: tuple[CheckIdentity, ...]


@dataclasses.dataclass(frozen=True)
class CandidateObserverDecision:
    schema: str
    observer_id: str
    disposition: CandidateObserverDisposition
    reason: str
    candidate_state: CandidateCIState
    terminal: bool
    wake_reasoning: bool
    previous_digest: str | None
    current_digest: str
    canonical_digest: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "observer_id": self.observer_id,
            "disposition": self.disposition.value,
            "reason": self.reason,
            "candidate_state": self.candidate_state.value,
            "terminal": self.terminal,
            "wake_reasoning": self.wake_reasoning,
            "previous_digest": self.previous_digest,
            "current_digest": self.current_digest,
            "canonical_digest": self.canonical_digest,
        }


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _identity(identity: CheckIdentity) -> tuple[str, int]:
    if type(identity) is not CheckIdentity:
        raise CandidateObserverError("required check identity has wrong exact type")
    if (
        not isinstance(identity.context, str)
        or not identity.context
        or (
            identity.app_id is not None
            and (type(identity.app_id) is not int or identity.app_id <= 0)
        )
    ):
        raise CandidateObserverError("required check identity is invalid")
    return identity.context, -1 if identity.app_id is None else identity.app_id


def _validate_observation(observation: CandidateCIObservation) -> None:
    if type(observation) is not CandidateCIObservation:
        raise CandidateObserverError("candidate observation has wrong exact type")
    if (
        not isinstance(observation.repository, str)
        or "/" not in observation.repository
        or type(observation.repository_id) is not int
        or observation.repository_id <= 0
        or type(observation.pull_request_number) is not int
        or observation.pull_request_number <= 0
        or not isinstance(observation.candidate_ref, str)
        or _ID_RE.fullmatch(observation.candidate_ref) is None
        or not isinstance(observation.expected_head_sha, str)
        or _SHA_RE.fullmatch(observation.expected_head_sha) is None
        or not isinstance(observation.observed_head_sha, str)
        or _SHA_RE.fullmatch(observation.observed_head_sha) is None
        or not isinstance(observation.policy_revision, str)
        or not observation.policy_revision
        or type(observation.required_checks) is not tuple
        or not observation.required_checks
        or type(observation.state) is not CandidateCIState
        or type(observation.terminal) is not bool
        or not isinstance(observation.input_digest, str)
        or _SHA256_RE.fullmatch(observation.input_digest) is None
        or not isinstance(observation.canonical_digest, str)
        or _SHA256_RE.fullmatch(observation.canonical_digest) is None
    ):
        raise CandidateObserverError("candidate observation is malformed")
    identities = tuple(_identity(item) for item in observation.required_checks)
    if len(set(identities)) != len(identities):
        raise CandidateObserverError("candidate observation required checks changed")
    expected_terminal = observation.state in {
        CandidateCIState.GREEN,
        CandidateCIState.FAILED,
        CandidateCIState.STALE,
    }
    if observation.terminal is not expected_terminal:
        raise CandidateObserverError("candidate observation terminal flag is inconsistent")

    rendered = observation.to_dict()
    claimed = rendered.pop("canonical_digest", None)
    if (
        claimed != observation.canonical_digest
        or _digest(rendered) != observation.canonical_digest
    ):
        raise CandidateObserverError("candidate observation canonical digest is invalid")


def key_for_observation(observation: CandidateCIObservation) -> CandidateObserverKey:
    _validate_observation(observation)
    return CandidateObserverKey(
        repository=observation.repository,
        repository_id=observation.repository_id,
        pull_request_number=observation.pull_request_number,
        candidate_ref=observation.candidate_ref,
        expected_head_sha=observation.expected_head_sha,
        policy_revision=observation.policy_revision,
        required_checks=observation.required_checks,
    )


def observer_id(key: CandidateObserverKey) -> str:
    if type(key) is not CandidateObserverKey:
        raise CandidateObserverError("observer key has wrong exact type")
    if (
        not isinstance(key.repository, str)
        or "/" not in key.repository
        or type(key.repository_id) is not int
        or key.repository_id <= 0
        or type(key.pull_request_number) is not int
        or key.pull_request_number <= 0
        or not isinstance(key.candidate_ref, str)
        or _ID_RE.fullmatch(key.candidate_ref) is None
        or not isinstance(key.expected_head_sha, str)
        or _SHA_RE.fullmatch(key.expected_head_sha) is None
        or not isinstance(key.policy_revision, str)
        or not key.policy_revision
        or type(key.required_checks) is not tuple
        or not key.required_checks
    ):
        raise CandidateObserverError("observer key is invalid")
    identities = tuple(sorted(_identity(item) for item in key.required_checks))
    if len(identities) != len(set(identities)):
        raise CandidateObserverError("observer key contains duplicate required checks")
    payload = {
        "repository": key.repository,
        "repository_id": key.repository_id,
        "pull_request_number": key.pull_request_number,
        "candidate_ref": key.candidate_ref,
        "expected_head_sha": key.expected_head_sha,
        "policy_revision": key.policy_revision,
        "required_checks": [
            {"context": context, "app_id": None if app_id == -1 else app_id}
            for context, app_id in identities
        ],
    }
    return "github-ci-observer-" + _digest(payload)[:32]


def _same_key(left: CandidateCIObservation, right: CandidateCIObservation) -> bool:
    return key_for_observation(left) == key_for_observation(right)


def _decision(
    current: CandidateCIObservation,
    *,
    disposition: CandidateObserverDisposition,
    reason: str,
    previous_digest: str | None,
) -> CandidateObserverDecision:
    key = key_for_observation(current)
    oid = observer_id(key)
    wake = disposition is not CandidateObserverDisposition.QUIESCENT
    payload = {
        "schema": SCHEMA,
        "observer_id": oid,
        "disposition": disposition.value,
        "reason": reason,
        "candidate_state": current.state.value,
        "terminal": current.terminal,
        "wake_reasoning": wake,
        "previous_digest": previous_digest,
        "current_digest": current.canonical_digest,
    }
    return CandidateObserverDecision(
        schema=SCHEMA,
        observer_id=oid,
        disposition=disposition,
        reason=reason,
        candidate_state=current.state,
        terminal=current.terminal,
        wake_reasoning=wake,
        previous_digest=previous_digest,
        current_digest=current.canonical_digest,
        canonical_digest=_digest(payload),
    )


def observe_candidate_transition(
    current: CandidateCIObservation,
    *,
    previous: CandidateCIObservation | None = None,
) -> CandidateObserverDecision:
    """Classify one supplied observation as quiescent, material, or terminal.

    The caller owns all sampling and wait cadence. This reducer never polls.
    """

    _validate_observation(current)
    if previous is None:
        if current.terminal:
            return _decision(
                current,
                disposition=CandidateObserverDisposition.TERMINAL_RETURN,
                reason=f"TERMINAL_{current.state.value}",
                previous_digest=None,
            )
        if current.state is CandidateCIState.UNKNOWN:
            return _decision(
                current,
                disposition=CandidateObserverDisposition.MATERIAL_RETURN,
                reason="OBSERVER_EVIDENCE_UNKNOWN",
                previous_digest=None,
            )
        return _decision(
            current,
            disposition=CandidateObserverDisposition.QUIESCENT,
            reason="BASELINE_PENDING",
            previous_digest=None,
        )

    _validate_observation(previous)
    if not _same_key(previous, current):
        raise CandidateObserverError("candidate observer identity changed")
    if previous.terminal:
        raise CandidateObserverError("terminal observer cannot be reused")

    if current.canonical_digest == previous.canonical_digest:
        return _decision(
            current,
            disposition=CandidateObserverDisposition.QUIESCENT,
            reason="NO_MATERIAL_CHANGE",
            previous_digest=previous.canonical_digest,
        )

    if current.terminal:
        return _decision(
            current,
            disposition=CandidateObserverDisposition.TERMINAL_RETURN,
            reason=f"TERMINAL_{current.state.value}",
            previous_digest=previous.canonical_digest,
        )

    if current.state is CandidateCIState.UNKNOWN:
        if (
            previous.state is CandidateCIState.UNKNOWN
            and current.issues == previous.issues
        ):
            return _decision(
                current,
                disposition=CandidateObserverDisposition.QUIESCENT,
                reason="UNKNOWN_UNCHANGED",
                previous_digest=previous.canonical_digest,
            )
        return _decision(
            current,
            disposition=CandidateObserverDisposition.MATERIAL_RETURN,
            reason="OBSERVER_EVIDENCE_UNKNOWN",
            previous_digest=previous.canonical_digest,
        )

    if (
        previous.state is CandidateCIState.UNKNOWN
        and current.state is CandidateCIState.PENDING
    ):
        return _decision(
            current,
            disposition=CandidateObserverDisposition.MATERIAL_RETURN,
            reason="OBSERVER_EVIDENCE_RECOVERED",
            previous_digest=previous.canonical_digest,
        )

    # PENDING check progress is deliberately suppressed. A Class-T sampler may
    # inspect frequently without re-entering principal reasoning for queue/running
    # changes that do not alter the release decision.
    return _decision(
        current,
        disposition=CandidateObserverDisposition.QUIESCENT,
        reason="NO_MATERIAL_CHANGE",
        previous_digest=previous.canonical_digest,
    )


__all__ = [
    "SCHEMA",
    "CandidateObserverDecision",
    "CandidateObserverDisposition",
    "CandidateObserverError",
    "CandidateObserverKey",
    "key_for_observation",
    "observe_candidate_transition",
    "observer_id",
]
