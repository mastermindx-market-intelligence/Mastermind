"""Canonical stateless join of a current Executive Job, Attempt, Worker and harness.

Integration adapters reuse this owner and translate only their public errors.
"""
from __future__ import annotations
import dataclasses
import re
from typing import Any
from control_plane.executive_delegation_identity import derive_delegation_identity
from control_plane.executive_runtime import AttemptStatus, JobStatus, WorkerStatus

_OPERATION_KEY = re.compile(r"\Aexec-(job-[0-9]{3,})\Z")

class CurrentTargetUnavailable(ValueError):
    """The operation has no admissible current writer."""

def _refuse() -> None:
    raise CurrentTargetUnavailable("BINDING_UNAVAILABLE")

@dataclasses.dataclass(frozen=True, slots=True)
class CurrentTargetEpoch:
    root_job_id: str
    job_id: str
    session_ref: str
    attempt_id: str
    worker_id: str
    job_status: JobStatus
    attempt_status: AttemptStatus
    fence_generation: int
    worker_status: WorkerStatus
    harness_session_epoch_id: str
    harness_generation_number: int
    harness_provider_session_id: str
    harness_provider: str
    harness_account_label: str
    harness_owner_seat: str


def job_id_from_operation_key(operation_key: object) -> str:
    if type(operation_key) is not str:
        _refuse()
    match = _OPERATION_KEY.fullmatch(operation_key)
    if match is None:
        _refuse()
    return match.group(1).upper()


def _current_target_job_identity(*, operation_key: str, job_id: str, job: Any) -> Any:
    """Validate the acquired Job before selecting its current Attempt."""

    if job is None:
        _refuse()
    identity = derive_delegation_identity(job)
    if (
        identity.operation_key != operation_key
        or identity.job_id != job_id
        or job.status not in {JobStatus.RUNNING, JobStatus.CHECKPOINTED}
        or not job.current_attempt_id
    ):
        _refuse()
    return identity


def _validate_current_target_attempt(*, job_id: str, job: Any, attempt: Any) -> None:
    """Validate the acquired current Attempt before selecting its Worker."""

    if (
        attempt is None
        or attempt.job_id != job_id
        or attempt.status
        not in {
            AttemptStatus.CLAIMED,
            AttemptStatus.RUNNING,
            AttemptStatus.CHECKPOINTED,
        }
        or not attempt.worker_id
        or job.assigned_worker_id != attempt.worker_id
    ):
        _refuse()


def _validate_current_target_worker_quota(
    *, job_id: str, job: Any, attempt: Any, worker: Any, quota: Any,
) -> None:
    """Validate aggregate Worker availability and the exact held quota."""

    if (
        worker is None
        or worker.status not in {WorkerStatus.AVAILABLE, WorkerStatus.BUSY}
        or quota is None
        or job.assigned_quota_class != attempt.quota_class
        or quota.worker_id != attempt.worker_id
        or quota.quota_class != attempt.quota_class
        or quota.status is not WorkerStatus.BUSY
        or quota.active_attempt_id != attempt.attempt_id
        or quota.active_job_id != job_id
        or quota.fence_generation != attempt.fence_generation
    ):
        _refuse()


def _current_target_epoch_from_facts(
    *, job_id: str, identity: Any, job: Any, attempt: Any, quota: Any, harness: Any,
) -> CurrentTargetEpoch:
    """Build the epoch after the preceding stages and exact harness read."""

    if harness.attempt_id != attempt.attempt_id:
        _refuse()
    return CurrentTargetEpoch(
        root_job_id=identity.root_job_id,
        job_id=job_id,
        session_ref=identity.session_ref,
        attempt_id=attempt.attempt_id,
        worker_id=attempt.worker_id,
        job_status=job.status,
        attempt_status=attempt.status,
        fence_generation=attempt.fence_generation,
        worker_status=quota.status,
        harness_session_epoch_id=harness.session_epoch_id,
        harness_generation_number=harness.generation_number,
        harness_provider_session_id=harness.provider_session_id,
        harness_provider=harness.provider,
        harness_account_label=harness.account_label,
        harness_owner_seat=harness.owner_seat,
    )


def read_current_target(runtime: Any, operation_key: str) -> CurrentTargetEpoch:
    """Read one current Executive target through public Runtime registries."""

    try:
        job_id = job_id_from_operation_key(operation_key)
        job = runtime.jobs.get_job(job_id)
        identity = _current_target_job_identity(
            operation_key=operation_key, job_id=job_id, job=job)
        attempt = runtime.attempts.get_attempt(job.current_attempt_id)
        _validate_current_target_attempt(job_id=job_id, job=job, attempt=attempt)
        worker = runtime.workers.get_worker(attempt.worker_id)
        # Worker availability aggregates independent quota classes. Another
        # available slot must not hide this exact held native writer.
        quota = runtime.workers.get_quota_class(attempt.worker_id, attempt.quota_class)
        _validate_current_target_worker_quota(
            job_id=job_id, job=job, attempt=attempt, worker=worker, quota=quota)
        harness = runtime.current_harness_binding_source(attempt.attempt_id)
        return _current_target_epoch_from_facts(
            job_id=job_id, identity=identity, job=job, attempt=attempt,
            quota=quota, harness=harness)
    except CurrentTargetUnavailable:
        raise
    except Exception:
        _refuse()
