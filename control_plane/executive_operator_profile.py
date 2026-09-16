"""Pure provider-neutral binding for one already-claimed rich operator realm.

This module does not choose workers, providers, accounts, endpoints, or models.
It validates that the current Job, claimed Attempt, quota registration,
accepted capability policy, and an explicitly supplied implementation-support
record all describe the *same* already-claimed realm.  The result is inert
configuration for the existing Executive Operator Harness lifecycle.
"""
from __future__ import annotations

import dataclasses
import re

from control_plane.executive_agent_capabilities import (
    CapabilityPolicyError,
    ExecutionCapabilityRegistry,
)
from control_plane.executive_runtime import (
    Attempt,
    AttemptStatus,
    Job,
    WorkerQuotaClass,
)
from control_plane.operator_harness_contract import (
    OPERATOR_HARNESS_INTERFACE_VERSION,
    AttemptExecutionMode,
    AuthRealmRequirement,
    HarnessAdapterCapabilities,
)


_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")


class OperatorProfileResolutionError(ValueError):
    """The claimed operator realm cannot be represented without drift."""


def _token(name: str, value: object) -> str:
    if not isinstance(value, str) or _TOKEN_RE.fullmatch(value) is None:
        raise OperatorProfileResolutionError(f"{name} must be a bounded opaque token")
    return value


def _sha256(name: str, value: object) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise OperatorProfileResolutionError(f"{name} must be lowercase sha256")
    return value


@dataclasses.dataclass(frozen=True, slots=True)
class OperatorImplementationSupport:
    """Reviewed implementation facts for one already-selected Worker realm.

    ``worker_provider`` is the provider identity already registered on the
    Worker quota row (for example the current ``codex`` provider alias).
    ``provider`` and ``harness_kind`` are the exact OHF requested-profile
    identities exposed by that realm implementation.  Supplying this record
    is not routing: the resolver rejects a mismatch instead of selecting or
    falling back to another support record.
    """

    worker_provider: str
    provider: str
    execution_surface: str
    harness_kind: str
    capability_auth_realm: str
    auth_realm_requirement: AuthRealmRequirement
    remote_capabilities: HarnessAdapterCapabilities

    def __post_init__(self) -> None:
        _token("worker_provider", self.worker_provider)
        _token("provider", self.provider)
        _token("execution_surface", self.execution_surface)
        _token("harness_kind", self.harness_kind)
        _token("capability_auth_realm", self.capability_auth_realm)
        if not isinstance(self.auth_realm_requirement, AuthRealmRequirement):
            raise TypeError("auth_realm_requirement must be AuthRealmRequirement")
        if not isinstance(self.remote_capabilities, HarnessAdapterCapabilities):
            raise TypeError("remote_capabilities must be HarnessAdapterCapabilities")
        if self.remote_capabilities.interface_version != OPERATOR_HARNESS_INTERFACE_VERSION:
            raise OperatorProfileResolutionError(
                "remote_capabilities interface_version is unsupported"
            )


@dataclasses.dataclass(frozen=True, slots=True)
class OperatorExecutionBinding:
    provider: str
    harness_kind: str
    harness_binary_digest: str
    harness_version: str
    model: str
    effort: str
    capability_profile_id: str
    capability_profile_digest: str
    auth_realm_requirement: AuthRealmRequirement
    remote_capabilities: HarnessAdapterCapabilities

    def __post_init__(self) -> None:
        _token("provider", self.provider)
        _token("harness_kind", self.harness_kind)
        _sha256("harness_binary_digest", self.harness_binary_digest)
        _token("harness_version", self.harness_version)
        _token("model", self.model)
        _token("effort", self.effort)
        _token("capability_profile_id", self.capability_profile_id)
        _sha256("capability_profile_digest", self.capability_profile_digest)
        if not isinstance(self.auth_realm_requirement, AuthRealmRequirement):
            raise TypeError("auth_realm_requirement must be AuthRealmRequirement")
        if not isinstance(self.remote_capabilities, HarnessAdapterCapabilities):
            raise TypeError("remote_capabilities must be HarnessAdapterCapabilities")


def resolve_operator_execution_binding(
    *,
    job: Job,
    attempt: Attempt,
    quota: WorkerQuotaClass,
    capability_registry: ExecutionCapabilityRegistry,
    implementation: OperatorImplementationSupport,
) -> OperatorExecutionBinding:
    """Resolve one exact rich-operator binding without performing placement.

    Every authority/identity check is fail-closed.  The provider implementation
    record must match the Worker realm that Executive Runtime already claimed;
    there is no lookup table, provider registry, retry path, or fallback here.
    """

    if not isinstance(job, Job):
        raise TypeError("job must be Job")
    if not isinstance(attempt, Attempt):
        raise TypeError("attempt must be Attempt")
    if not isinstance(quota, WorkerQuotaClass):
        raise TypeError("quota must be WorkerQuotaClass")
    if not isinstance(capability_registry, ExecutionCapabilityRegistry):
        raise TypeError("capability_registry must be ExecutionCapabilityRegistry")
    if not isinstance(implementation, OperatorImplementationSupport):
        raise TypeError("implementation must be OperatorImplementationSupport")

    if attempt.job_id != job.job_id:
        raise OperatorProfileResolutionError("Attempt does not belong to Job")
    # `job` may be the immutable pre-claim snapshot the supervisor already
    # held when Runtime atomically installed the lease.  When the snapshot
    # carries current/assignment fields they must agree; absence is not
    # evidence of a different realm.  Attempt + quota are the claimed-realm
    # identity at this boundary.
    if job.current_attempt_id is not None and job.current_attempt_id != attempt.attempt_id:
        raise OperatorProfileResolutionError("Job current Attempt identity drifted")
    if job.assigned_worker_id is not None and job.assigned_worker_id != attempt.worker_id:
        raise OperatorProfileResolutionError("Job assigned Worker identity drifted")
    if (
        job.assigned_quota_class is not None
        and job.assigned_quota_class != attempt.quota_class
    ):
        raise OperatorProfileResolutionError("Job assigned quota identity drifted")
    if quota.worker_id != attempt.worker_id or quota.quota_class != attempt.quota_class:
        raise OperatorProfileResolutionError(
            "Attempt and quota do not identify one current claimed realm"
        )
    if attempt.status is not AttemptStatus.CLAIMED:
        raise OperatorProfileResolutionError(
            "operator profile resolution requires the current CLAIMED Attempt"
        )
    if attempt.execution_mode not in {
        None,
        AttemptExecutionMode.OPERATOR_HARNESS.value,
    }:
        raise OperatorProfileResolutionError(
            "claimed Attempt is bound to a different execution mode"
        )
    if quota.provider != implementation.worker_provider:
        raise OperatorProfileResolutionError(
            "claimed Worker provider lacks the supplied operator implementation"
        )

    identity_keys = (
        "execution_profile_id",
        "execution_profile_digest",
        "capability_policy_version",
        "capability_policy_digest",
    )
    if any(
        quota.metadata.get(key) != job.constraints.get(key)
        for key in identity_keys
    ):
        raise OperatorProfileResolutionError(
            "operator quota execution-profile identity drifted after claim"
        )
    if (
        capability_registry.policy_version
        != job.constraints.get("capability_policy_version")
        or capability_registry.policy_digest
        != job.constraints.get("capability_policy_digest")
    ):
        raise OperatorProfileResolutionError(
            "operator capability policy identity drifted after claim"
        )

    profile_id = str(job.constraints.get("execution_profile_id") or "")
    try:
        profile = capability_registry.resolve(profile_id)
    except CapabilityPolicyError as exc:
        raise OperatorProfileResolutionError(
            "operator execution profile is not accepted by capability policy"
        ) from exc
    if profile.profile_digest != job.constraints.get("execution_profile_digest"):
        raise OperatorProfileResolutionError(
            "operator capability profile digest drifted after claim"
        )
    if (
        profile.execution_surface != implementation.execution_surface
        or profile.auth_realm != implementation.capability_auth_realm
    ):
        raise OperatorProfileResolutionError(
            "operator capability profile has no matching implementation support"
        )

    # Authority ceiling common to the currently reviewed rich planner lane.
    # Provider identity cannot widen these fields and is never consulted to
    # infer owner_seat or orchestration_role.
    if (
        profile.sandbox_policy != "read-only"
        or profile.approval_policy != "never"
        or profile.write_capable
    ):
        raise OperatorProfileResolutionError(
            "operator capability profile would widen read-only authority"
        )

    harness_binary_digest = _sha256(
        "harness_binary_digest", job.constraints.get("harness_binary_digest")
    )
    harness_version = _token(
        "harness_version", job.constraints.get("harness_version")
    )
    if (
        quota.metadata.get("harness_binary_digest") != harness_binary_digest
        or quota.metadata.get("harness_version") != harness_version
    ):
        raise OperatorProfileResolutionError(
            "operator quota harness identity drifted after claim"
        )

    model = _token("model", quota.model)
    effort = _token("effort", quota.effort)
    if model != job.constraints.get("model") or effort != job.constraints.get("effort"):
        raise OperatorProfileResolutionError(
            "operator planner model or effort drifted after claim"
        )

    return OperatorExecutionBinding(
        provider=implementation.provider,
        harness_kind=implementation.harness_kind,
        harness_binary_digest=harness_binary_digest,
        harness_version=harness_version,
        model=model,
        effort=effort,
        capability_profile_id=profile.profile_id,
        capability_profile_digest=profile.profile_digest,
        auth_realm_requirement=implementation.auth_realm_requirement,
        remote_capabilities=implementation.remote_capabilities,
    )


__all__ = [
    "OperatorExecutionBinding",
    "OperatorImplementationSupport",
    "OperatorProfileResolutionError",
    "resolve_operator_execution_binding",
]
