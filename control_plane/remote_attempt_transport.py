"""Attempt-bound remote Worker transport resolution after canonical claim.

This module closes the missing MH1 Task-4 seam without becoming a placement
owner. Executive Runtime/Capacity must already have selected and persisted the
Job/Attempt/Worker/quota identity. The resolver only proves that the current
claim's immutable Capacity join names one root-managed remote host binding, then
constructs an mTLS client whose wire identity is fixed to that same Attempt.

It owns no queue, Worker registry, provider selection, retry, failover, endpoint
discovery, credential store, or lifecycle state. Network I/O begins only when a
consumer uses the returned client. A launch resolution is available only while
the Attempt is still CLAIMED; if another owner advances the Attempt during
resolution, the resolver fails closed before any remote request.
"""
from __future__ import annotations

import dataclasses
from collections.abc import Callable, Mapping, Sequence
from enum import Enum
from typing import Any

from control_plane.executive_capacity_join import (
    CapacityJoinError,
    RegisteredCapacityJoin,
    read_remote_capacity_joins,
    validate_capacity_join,
)
from control_plane.executive_runtime import (
    Attempt,
    AttemptStatus,
    Job,
    JobStatus,
    Runtime,
    WorkerQuotaClass,
    WorkerStatus,
)
from control_plane.executive_worker_broker import (
    RemoteWorkerBrokerEndpoint,
    RemoteWorkerBrokerFleet,
)
from control_plane.remote_worker_broker_client import RemoteWorkerBrokerClient
from control_plane.remote_worker_transport import (
    BrokerTransportBinding,
    TransportValidationError,
    validate_host_ref,
)
from control_plane.worker_execution_contract import WorkerLaunchSpec


REMOTE_WORKER_OPERATIONS = frozenset(
    {"start", "status", "collect", "cancel", "validate"}
)
REMOTE_RECOVERY_OPERATIONS = frozenset(
    {"status", "collect", "cancel", "validate"}
)
_ACTIVE_RECOVERY_ATTEMPTS = frozenset(
    {
        AttemptStatus.CLAIMED,
        AttemptStatus.RUNNING,
        AttemptStatus.CHECKPOINTED,
        AttemptStatus.CANCEL_REQUESTED,
    }
)
_ACTIVE_RECOVERY_JOBS = frozenset(
    {
        JobStatus.RUNNING,
        JobStatus.CHECKPOINTED,
        JobStatus.CANCEL_REQUESTED,
    }
)
_ERROR_CODES = frozenset(
    {
        "INVALID_INPUT",
        "RUNTIME_UNAVAILABLE",
        "CLAIM_MISMATCH",
        "CLAIM_NOT_LAUNCHABLE",
        "CAPACITY_UNAVAILABLE",
        "HOST_BINDING_UNAVAILABLE",
        "HOST_BINDING_MISMATCH",
        "STATE_MOVED",
    }
)


class RemoteTransportPurpose(str, Enum):
    LAUNCH = "launch"
    RECOVERY = "recovery"


class RemoteAttemptTransportError(RuntimeError):
    """One sanitized zero-network-effect resolution refusal."""

    def __init__(self, code: str) -> None:
        if code not in _ERROR_CODES:
            raise ValueError("unknown remote transport resolution code")
        self.code = code
        super().__init__(f"remote attempt transport refused: {code}")


@dataclasses.dataclass(frozen=True)
class RemoteWorkerHostBinding:
    """Root-managed physical binding for one exact remote Worker identity.

    Endpoint/certificate paths and OS principal coordinates remain local host
    composition. They are never projected into Capacity metadata or Runtime.
    """

    host_ref: str
    worker_id: str
    transport: BrokerTransportBinding
    worker_user: str
    worker_uid: int
    worker_gid: int
    secret_canary_verdict: Mapping[str, Any] = dataclasses.field(default_factory=dict)

    def __post_init__(self) -> None:
        try:
            host_ref = validate_host_ref(self.host_ref)
        except TransportValidationError as exc:
            raise RemoteAttemptTransportError("HOST_BINDING_MISMATCH") from exc
        worker_id = str(self.worker_id or "").strip()
        if not worker_id or any(character.isspace() for character in worker_id):
            raise RemoteAttemptTransportError("HOST_BINDING_MISMATCH")
        if not isinstance(self.transport, BrokerTransportBinding):
            raise RemoteAttemptTransportError("HOST_BINDING_MISMATCH")
        verdict = self.secret_canary_verdict
        if not isinstance(verdict, Mapping):
            raise RemoteAttemptTransportError("HOST_BINDING_MISMATCH")
        object.__setattr__(self, "host_ref", host_ref)
        object.__setattr__(self, "worker_id", worker_id)
        object.__setattr__(self, "secret_canary_verdict", dict(verdict))

    def endpoint_for(self, client: RemoteWorkerBrokerClient) -> RemoteWorkerBrokerEndpoint:
        return RemoteWorkerBrokerEndpoint(
            worker_id=self.worker_id,
            client=client,
            worker_user=self.worker_user,
            worker_uid=self.worker_uid,
            worker_gid=self.worker_gid,
            secret_canary_verdict=self.secret_canary_verdict,
        )


RemoteWorkerHostBindingSource = Callable[
    [str, str], RemoteWorkerHostBinding | None
]


@dataclasses.dataclass(frozen=True)
class ResolvedRemoteAttemptTransport:
    """One no-I/O resolution of an already-claimed Attempt to one carrier."""

    purpose: RemoteTransportPurpose
    job_id: str
    attempt_id: str
    worker_id: str
    quota_class: str
    host_ref: str
    provider: str
    capacity_capability_id: str
    endpoint: RemoteWorkerBrokerEndpoint
    client: RemoteWorkerBrokerClient


def _require_identity(value: str, *, code: str = "INVALID_INPUT") -> str:
    token = str(value or "").strip()
    if not token or any(character.isspace() for character in token):
        raise RemoteAttemptTransportError(code)
    return token


def _claim_signature(
    job: Job,
    attempt: Attempt,
    quota: WorkerQuotaClass,
    join: RegisteredCapacityJoin,
) -> tuple[Any, ...]:
    """Critical claim facts; volatile observation timestamps are excluded."""

    return (
        job.job_id,
        job.status,
        job.current_attempt_id,
        job.assigned_worker_id,
        job.assigned_quota_class,
        attempt.attempt_id,
        attempt.job_id,
        attempt.worker_id,
        attempt.quota_class,
        attempt.status,
        attempt.fence_generation,
        attempt.version,
        quota.worker_id,
        quota.quota_class,
        quota.status,
        quota.active_attempt_id,
        quota.active_job_id,
        quota.fence_generation,
        quota.provider,
        join.worker_id,
        join.quota_class,
        join.provider,
        join.capacity_join.to_dict(),
    )


def _read_claim(
    runtime: Runtime,
    *,
    job_id: str,
    attempt_id: str,
    purpose: RemoteTransportPurpose,
) -> tuple[Job, Attempt, WorkerQuotaClass, RegisteredCapacityJoin]:
    job = runtime.jobs.get_job(job_id)
    attempt = runtime.attempts.get_attempt(attempt_id)
    if job is None or attempt is None:
        raise RemoteAttemptTransportError("RUNTIME_UNAVAILABLE")
    if (
        attempt.job_id != job.job_id
        or job.current_attempt_id != attempt.attempt_id
        or job.assigned_worker_id != attempt.worker_id
        or job.assigned_quota_class != attempt.quota_class
    ):
        raise RemoteAttemptTransportError("CLAIM_MISMATCH")

    if purpose is RemoteTransportPurpose.LAUNCH:
        if attempt.status is not AttemptStatus.CLAIMED or job.status is not JobStatus.RUNNING:
            raise RemoteAttemptTransportError("CLAIM_NOT_LAUNCHABLE")
    elif (
        attempt.status not in _ACTIVE_RECOVERY_ATTEMPTS
        or job.status not in _ACTIVE_RECOVERY_JOBS
    ):
        raise RemoteAttemptTransportError("CLAIM_MISMATCH")

    try:
        rows = read_remote_capacity_joins(
            runtime.workers,
            ((attempt.worker_id, attempt.quota_class),),
        )
    except CapacityJoinError as exc:
        raise RemoteAttemptTransportError("CAPACITY_UNAVAILABLE") from exc
    if len(rows) != 1:
        raise RemoteAttemptTransportError("CAPACITY_UNAVAILABLE")
    join = rows[0]

    quota = runtime.workers.get_quota_class(attempt.worker_id, attempt.quota_class)
    if quota is None:
        raise RemoteAttemptTransportError("CAPACITY_UNAVAILABLE")
    if (
        quota.worker_id != attempt.worker_id
        or quota.quota_class != attempt.quota_class
        or quota.status is not WorkerStatus.BUSY
        or quota.active_attempt_id != attempt.attempt_id
        or quota.active_job_id != job.job_id
        or quota.provider != join.provider
    ):
        raise RemoteAttemptTransportError("CLAIM_MISMATCH")
    try:
        current_join = validate_capacity_join(quota.metadata.get("capacity_join"))
    except (AttributeError, CapacityJoinError) as exc:
        raise RemoteAttemptTransportError("CAPACITY_UNAVAILABLE") from exc
    if current_join != join.capacity_join:
        raise RemoteAttemptTransportError("STATE_MOVED")
    return job, attempt, quota, join


def resolve_remote_attempt_transport(
    runtime: Runtime,
    *,
    job_id: str,
    attempt_id: str,
    binding_source: RemoteWorkerHostBindingSource,
    purpose: RemoteTransportPurpose | str = RemoteTransportPurpose.LAUNCH,
) -> ResolvedRemoteAttemptTransport:
    """Resolve one existing claim to one exact mTLS client with zero network I/O."""

    if not isinstance(runtime, Runtime) or not callable(binding_source):
        raise RemoteAttemptTransportError("INVALID_INPUT")
    job_token = _require_identity(job_id)
    attempt_token = _require_identity(attempt_id)
    try:
        resolved_purpose = RemoteTransportPurpose(purpose)
    except (TypeError, ValueError) as exc:
        raise RemoteAttemptTransportError("INVALID_INPUT") from exc

    job, attempt, quota, join = _read_claim(
        runtime,
        job_id=job_token,
        attempt_id=attempt_token,
        purpose=resolved_purpose,
    )
    host_ref = join.capacity_join.host_ref
    try:
        host_binding = binding_source(host_ref, attempt.worker_id)
    except Exception as exc:
        raise RemoteAttemptTransportError("HOST_BINDING_UNAVAILABLE") from exc
    if host_binding is None:
        raise RemoteAttemptTransportError("HOST_BINDING_UNAVAILABLE")
    if not isinstance(host_binding, RemoteWorkerHostBinding):
        raise RemoteAttemptTransportError("HOST_BINDING_MISMATCH")
    if host_binding.host_ref != host_ref or host_binding.worker_id != attempt.worker_id:
        raise RemoteAttemptTransportError("HOST_BINDING_MISMATCH")

    # Re-observe the complete critical claim after root-managed host resolution.
    # Any concurrent claim/lifecycle movement refuses before the client exists.
    final_job, final_attempt, final_quota, final_join = _read_claim(
        runtime,
        job_id=job_token,
        attempt_id=attempt_token,
        purpose=resolved_purpose,
    )
    if _claim_signature(job, attempt, quota, join) != _claim_signature(
        final_job, final_attempt, final_quota, final_join
    ):
        raise RemoteAttemptTransportError("STATE_MOVED")

    allowed_operations = (
        REMOTE_WORKER_OPERATIONS
        if resolved_purpose is RemoteTransportPurpose.LAUNCH
        else REMOTE_RECOVERY_OPERATIONS
    )
    identity = {
        "host_ref": host_ref,
        "job_id": job.job_id,
        "attempt_id": attempt.attempt_id,
        "worker_id": attempt.worker_id,
        # The existing Attempt is the operation identity for this transport
        # generation. No second lifecycle/operation identifier is minted here.
        "operation_id": attempt.attempt_id,
    }
    try:
        client = RemoteWorkerBrokerClient(
            host_binding.transport,
            identity,
            allowed_operations=allowed_operations,
        )
        endpoint = host_binding.endpoint_for(client)
    except (TransportValidationError, ValueError) as exc:
        raise RemoteAttemptTransportError("HOST_BINDING_MISMATCH") from exc

    return ResolvedRemoteAttemptTransport(
        purpose=resolved_purpose,
        job_id=job.job_id,
        attempt_id=attempt.attempt_id,
        worker_id=attempt.worker_id,
        quota_class=attempt.quota_class,
        host_ref=host_ref,
        provider=join.provider,
        capacity_capability_id=join.capacity_join.capacity_capability_id,
        endpoint=endpoint,
        client=client,
    )


def build_attempt_bound_worker_fleet(
    resolution: ResolvedRemoteAttemptTransport,
    *,
    validation_commands_for_spec: (
        Callable[[WorkerLaunchSpec], Sequence[Sequence[str]]] | None
    ) = None,
) -> RemoteWorkerBrokerFleet:
    """Compose the existing WorkerExecutionAdapter consumer for one Attempt.

    The returned fleet contains exactly one already-selected Worker. It cannot
    rank, spill, or fail over to another Worker/host.
    """

    if not isinstance(resolution, ResolvedRemoteAttemptTransport):
        raise RemoteAttemptTransportError("INVALID_INPUT")
    return RemoteWorkerBrokerFleet(
        (resolution.endpoint,),
        validation_commands_for_spec=validation_commands_for_spec,
    )


__all__ = [
    "REMOTE_RECOVERY_OPERATIONS",
    "REMOTE_WORKER_OPERATIONS",
    "RemoteAttemptTransportError",
    "RemoteTransportPurpose",
    "RemoteWorkerHostBinding",
    "ResolvedRemoteAttemptTransport",
    "build_attempt_bound_worker_fleet",
    "resolve_remote_attempt_transport",
]
