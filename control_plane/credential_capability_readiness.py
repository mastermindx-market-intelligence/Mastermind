"""Pure credential-readiness adapter for the existing Sol Capability Fabric.

This module owns no credential, registry, store, host placement, lifecycle, or
effect.  It accepts secret-free owner facts and augments one existing
``CapabilityFact`` with credential/host/actuator dependencies.  The canonical
SCF projector remains the only capability-status projection.

No API in this module accepts a password, token, key, cookie, authorization
header, Keychain coordinate, secret value, executable path, URL, or command.
"""
from __future__ import annotations

import dataclasses
import re
from enum import Enum

from control_plane.sol_capability_status import (
    CapabilityFact,
    CapabilityState,
    DependencyFact,
)

_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
_SOURCE = re.compile(r"^(?:receipt|runtime|owner|evidence):[A-Za-z0-9][A-Za-z0-9:._/@-]{0,239}$")
_FORBIDDEN_SOURCE = re.compile(
    r"(?:github_pat_|\bgh[pousr]_|\bxox[baprs]-|\bsk-|bearer|authorization|password|-----begin)",
    re.IGNORECASE,
)
_RESERVED_DEPENDENCIES = frozenset(
    {
        "credential.binding",
        "credential.host-binding",
        "credential.actuator-binding",
    }
)


class CredentialReadinessError(ValueError):
    """Secret-free owner facts are malformed or collide with reserved facts."""


class CredentialBindingState(str, Enum):
    READY = "READY"
    NOT_ENROLLED = "NOT_ENROLLED"
    STALE_GENERATION = "STALE_GENERATION"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"
    REQUIRES_USER_UNLOCK = "REQUIRES_USER_UNLOCK"
    REQUIRES_HUMAN_MFA = "REQUIRES_HUMAN_MFA"
    BACKEND_UNAVAILABLE = "BACKEND_UNAVAILABLE"
    NATIVE_SESSION_INVALID = "NATIVE_SESSION_INVALID"
    HOST_UNREACHABLE = "HOST_UNREACHABLE"


@dataclasses.dataclass(frozen=True)
class CredentialReadinessObservation:
    """One owner-authored, secret-free point-in-time readiness observation."""

    state: CredentialBindingState
    expected_host_binding: str
    observed_host_binding: str | None
    expected_credential_generation: str
    observed_credential_generation: str | None
    expected_actuator_generation: str
    observed_actuator_generation: str | None
    source_ref: str
    live_proof_current: bool


def _identifier(value: object, field: str, *, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    if type(value) is not str or value != value.strip() or _ID.fullmatch(value) is None:
        raise CredentialReadinessError(f"{field} must be a bounded lowercase identifier")
    if _FORBIDDEN_SOURCE.search(value):
        raise CredentialReadinessError(f"{field} contains secret-shaped text")
    return value


def _source_ref(value: object) -> str:
    if type(value) is not str or value != value.strip() or _SOURCE.fullmatch(value) is None:
        raise CredentialReadinessError(
            "source_ref must be a bounded owner/evidence/receipt/runtime reference"
        )
    if _FORBIDDEN_SOURCE.search(value):
        raise CredentialReadinessError("source_ref contains secret-shaped text")
    return value


def _normalize(observation: CredentialReadinessObservation) -> CredentialReadinessObservation:
    if not isinstance(observation, CredentialReadinessObservation):
        raise CredentialReadinessError(
            "observation must be CredentialReadinessObservation"
        )
    if not isinstance(observation.state, CredentialBindingState):
        raise CredentialReadinessError("state must be CredentialBindingState")
    if type(observation.live_proof_current) is not bool:
        raise CredentialReadinessError("live_proof_current must be boolean")
    return CredentialReadinessObservation(
        observation.state,
        _identifier(observation.expected_host_binding, "expected_host_binding"),
        _identifier(observation.observed_host_binding, "observed_host_binding", optional=True),
        _identifier(
            observation.expected_credential_generation,
            "expected_credential_generation",
        ),
        _identifier(
            observation.observed_credential_generation,
            "observed_credential_generation",
            optional=True,
        ),
        _identifier(
            observation.expected_actuator_generation,
            "expected_actuator_generation",
        ),
        _identifier(
            observation.observed_actuator_generation,
            "observed_actuator_generation",
            optional=True,
        ),
        _source_ref(observation.source_ref),
        observation.live_proof_current,
    )


def _positive_state(current: bool) -> CapabilityState:
    return CapabilityState.PROVEN_LIVE if current else CapabilityState.BUILT_NOT_PROVEN


def _binding_dependency(observation: CredentialReadinessObservation) -> DependencyFact:
    source = observation.source_ref
    if observation.state is CredentialBindingState.READY:
        if observation.observed_credential_generation is None:
            return DependencyFact(
                "credential.binding",
                CapabilityState.DARK_OR_DISCONNECTED,
                True,
                False,
                source,
                ("CREDENTIAL_GENERATION_UNOBSERVED",),
            )
        if observation.observed_credential_generation != observation.expected_credential_generation:
            return DependencyFact(
                "credential.binding",
                CapabilityState.DARK_OR_DISCONNECTED,
                True,
                False,
                source,
                ("CREDENTIAL_GENERATION_STALE",),
            )
        issues = () if observation.live_proof_current else ("CREDENTIAL_LIVE_PROOF_MISSING",)
        return DependencyFact(
            "credential.binding",
            _positive_state(observation.live_proof_current),
            True,
            True,
            source,
            issues,
        )

    mappings = {
        CredentialBindingState.NOT_ENROLLED: (
            CapabilityState.NOT_BUILT,
            "CREDENTIAL_NOT_ENROLLED",
        ),
        CredentialBindingState.STALE_GENERATION: (
            CapabilityState.DARK_OR_DISCONNECTED,
            "CREDENTIAL_GENERATION_STALE",
        ),
        CredentialBindingState.EXPIRED: (
            CapabilityState.DARK_OR_DISCONNECTED,
            "CREDENTIAL_EXPIRED",
        ),
        CredentialBindingState.REVOKED: (
            CapabilityState.DARK_OR_DISCONNECTED,
            "CREDENTIAL_REVOKED",
        ),
        CredentialBindingState.REQUIRES_USER_UNLOCK: (
            CapabilityState.DARK_OR_DISCONNECTED,
            "CREDENTIAL_REQUIRES_USER_UNLOCK",
        ),
        CredentialBindingState.REQUIRES_HUMAN_MFA: (
            CapabilityState.PARTIAL,
            "CREDENTIAL_REQUIRES_HUMAN_MFA",
        ),
        CredentialBindingState.BACKEND_UNAVAILABLE: (
            CapabilityState.DARK_OR_DISCONNECTED,
            "CREDENTIAL_BACKEND_UNAVAILABLE",
        ),
        CredentialBindingState.NATIVE_SESSION_INVALID: (
            CapabilityState.BROKEN,
            "CREDENTIAL_NATIVE_SESSION_INVALID",
        ),
        CredentialBindingState.HOST_UNREACHABLE: (
            CapabilityState.DARK_OR_DISCONNECTED,
            "CREDENTIAL_HOST_UNREACHABLE",
        ),
    }
    state, issue = mappings[observation.state]
    return DependencyFact("credential.binding", state, True, False, source, (issue,))


def _host_dependency(observation: CredentialReadinessObservation) -> DependencyFact:
    source = observation.source_ref
    if observation.observed_host_binding is None:
        return DependencyFact(
            "credential.host-binding",
            CapabilityState.DARK_OR_DISCONNECTED,
            True,
            False,
            source,
            ("HOST_BINDING_UNOBSERVED",),
        )
    if observation.observed_host_binding != observation.expected_host_binding:
        return DependencyFact(
            "credential.host-binding",
            CapabilityState.DARK_OR_DISCONNECTED,
            True,
            False,
            source,
            ("HOST_BINDING_MISMATCH",),
        )
    return DependencyFact(
        "credential.host-binding",
        _positive_state(observation.live_proof_current),
        True,
        True,
        source,
        () if observation.live_proof_current else ("HOST_BINDING_LIVE_PROOF_MISSING",),
    )


def _actuator_dependency(observation: CredentialReadinessObservation) -> DependencyFact:
    source = observation.source_ref
    if observation.observed_actuator_generation is None:
        return DependencyFact(
            "credential.actuator-binding",
            CapabilityState.DARK_OR_DISCONNECTED,
            True,
            False,
            source,
            ("ACTUATOR_GENERATION_UNOBSERVED",),
        )
    if observation.observed_actuator_generation != observation.expected_actuator_generation:
        return DependencyFact(
            "credential.actuator-binding",
            CapabilityState.DARK_OR_DISCONNECTED,
            True,
            False,
            source,
            ("ACTUATOR_GENERATION_MISMATCH",),
        )
    return DependencyFact(
        "credential.actuator-binding",
        _positive_state(observation.live_proof_current),
        True,
        True,
        source,
        () if observation.live_proof_current else ("ACTUATOR_LIVE_PROOF_MISSING",),
    )


def augment_credential_readiness(
    base: CapabilityFact,
    observation: CredentialReadinessObservation,
) -> CapabilityFact:
    """Attach closed credential readiness dependencies to one existing SCF fact."""
    if not isinstance(base, CapabilityFact):
        raise CredentialReadinessError("base must be CapabilityFact")
    observation = _normalize(observation)
    if not isinstance(base.dependencies, tuple):
        raise CredentialReadinessError("base dependencies must be an immutable tuple")
    existing: set[str] = set()
    for dependency in base.dependencies:
        if not isinstance(dependency, DependencyFact) or type(dependency.name) is not str:
            raise CredentialReadinessError("base dependencies must contain DependencyFact")
        existing.add(dependency.name.strip().lower())
    collision = existing & _RESERVED_DEPENDENCIES
    if collision:
        names = ",".join(sorted(collision))
        raise CredentialReadinessError(
            f"base capability already owns reserved credential dependencies: {names}"
        )

    credential_dependencies = (
        _binding_dependency(observation),
        _host_dependency(observation),
        _actuator_dependency(observation),
    )
    return dataclasses.replace(
        base,
        dependencies=tuple(base.dependencies) + credential_dependencies,
    )


__all__ = [
    "CredentialBindingState",
    "CredentialReadinessError",
    "CredentialReadinessObservation",
    "augment_credential_readiness",
]
