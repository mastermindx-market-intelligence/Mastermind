"""Current Runtime claim for the protected Memory owner, never a source grant.

Only the installed protected owner composes this primitive with its live Control
peer and independent Linux recipient/source authorization. The nominal object
keeps the actual Runtime/lease private; a JSON intent, thread ID or this handle
alone cannot authenticate an issuer or authorize a provider/source effect.
"""
from __future__ import annotations

import hashlib
import json
import os
import weakref
from dataclasses import dataclass, replace

from control_plane.executive_runtime import Runtime, RuntimeStore, Attempt, AttemptLease, AttemptStatus, JobStatus
from control_plane.worker_execution_contract import WorkerProcessRef

from common.native_memory_intent_contract import SCHEMA, normalize_memory_runtime_intent
_ISSUED = weakref.WeakKeyDictionary()


class MemoryAdmissionRefused(ValueError):
    def __init__(self):
        super().__init__('protected_memory_runtime_admission_required')


def _refuse():
    raise MemoryAdmissionRefused()


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
                      allow_nan=False).encode('utf-8')




class MemoryRuntimeClaim:
    __slots__ = ('__weakref__',)

    def __new__(cls):
        _refuse()

    def __repr__(self):
        return '<MemoryRuntimeClaim private>'


@dataclass(frozen=True)
class _State:
    runtime: Runtime
    lease: AttemptLease
    material: bytes
    runtime_root: str
    pid: int
    process: WorkerProcessRef | None = None


def _current(runtime, lease, *, process=None):
    if (type(runtime) is not Runtime or type(runtime.store) is not RuntimeStore
            or type(lease) is not AttemptLease or type(lease.attempt) is not Attempt
            or type(lease.lease_token) is not str):
        _refuse()
    attempt = lease.attempt
    timestamp = runtime.store.now_ms()
    try:
        with runtime.store.read() as con:
            runtime.attempts._leased_row(con, attempt_id=attempt.attempt_id,
                fence_generation=attempt.fence_generation, lease_token=lease.lease_token,
                timestamp=timestamp, statuses=({AttemptStatus.CLAIMED} if process is None else {AttemptStatus.RUNNING, AttemptStatus.CHECKPOINTED}))
            snapshot = runtime.attempts.current_authority_snapshot(con,
                job_id=attempt.job_id, attempt_id=attempt.attempt_id,
                fence_generation=attempt.fence_generation, timestamp=timestamp,
                statuses=({AttemptStatus.CLAIMED} if process is None else {AttemptStatus.RUNNING, AttemptStatus.CHECKPOINTED}))
            claims = con.execute("SELECT event_id,aggregate_type,aggregate_id,event_type,job_id,attempt_id,worker_id,quota_class,payload_json FROM events WHERE event_type='JOB_CLAIMED' AND job_id=? AND attempt_id=? LIMIT 2",
                (attempt.job_id, attempt.attempt_id)).fetchall()
            if (len(claims) != 1 or claims[0]['worker_id'] != snapshot.attempt.worker_id
                    or claims[0]['quota_class'] != snapshot.attempt.quota_class):
                _refuse()
            claim_ref = {'schema': 'mastermind.runtime_claim_ref.v1',
                'event_id': claims[0]['event_id'],
                'sha256': hashlib.sha256(_canonical(dict(claims[0]))).hexdigest()}
        job, current = snapshot.job, snapshot.attempt
        if (job.status is not JobStatus.RUNNING
                or (process is None and (current.pid is not None or current.provider_session_id is not None))
                or (process is not None and (type(process) is not WorkerProcessRef
                    or current.pid != process.pid or current.pgid != process.pgid
                    or current.process_start_identity != process.process_start_identity
                    or current.boot_id != process.boot_session_id
                    or current.stdout_path != process.stdout_path
                    or current.stderr_path != process.stderr_path
                    or current.result_path != process.result_path))
                or current.job_id != attempt.job_id or current.worker_id != attempt.worker_id
                or current.quota_class != attempt.quota_class
                or current.authority_policy_hash != attempt.authority_policy_hash
                or not set(job.requested_authorities).issubset({'READ', 'RESEARCH'})
                or 'READ' not in job.requested_authorities or job.allowed_write_paths):
            _refuse()
        from control_plane.executive_authority import ExecutiveAuthorityPolicy
        decision = ExecutiveAuthorityPolicy.load().authorize(job.requested_authorities,
            worktree=job.worktree, allowed_write_paths=job.allowed_write_paths,
            validation_commands=job.validation_commands)
        if decision.policy_sha256 != current.authority_policy_hash:
            _refuse()
        locator = _canonical(normalize_memory_runtime_intent(job.constraints.get('native_memory')))
        # Runtime IDs remain Runtime IDs. Native source intent IDs are separate
        # correlation values; no equality/relabel manufactures their admission.
        material = _canonical({'job_id': job.job_id, 'runtime_root': job.root_job_id,
            'parent_job_id': job.parent_job_id, 'owner_seat': job.owner_seat,
            'orchestration_provenance_digest': job.orchestration_provenance_digest,
            'attempt_id': current.attempt_id, 'worker_id': current.worker_id,
            'quota_class': current.quota_class, 'fence': current.fence_generation,
            'authority_policy_hash': current.authority_policy_hash, 'claim_ref': claim_ref,
            'locator_sha256': hashlib.sha256(locator).hexdigest()})
        return material, locator, job.root_job_id
    except MemoryAdmissionRefused:
        raise
    except Exception:
        raise MemoryAdmissionRefused() from None


def capture_memory_runtime_claim(runtime: Runtime, lease: AttemptLease) -> MemoryRuntimeClaim:
    """Read the real current owner/token; no reservation, source read or launch."""
    material, _, root = _current(runtime, lease)
    claim = object.__new__(MemoryRuntimeClaim)
    _ISSUED[claim] = _State(runtime, lease, material, root, os.getpid())
    return claim


def require_memory_runtime_claim(claim: MemoryRuntimeClaim) -> dict:
    """Fresh exact claim correlation for the protected owner only.

    This safe returned locator does not contain the Runtime lease or grant
    authority and cannot replace the qualified peer or Linux source grant.
    """
    if type(claim) is not MemoryRuntimeClaim or claim not in _ISSUED:
        _refuse()
    state = _ISSUED[claim]
    if state.pid != os.getpid():
        _refuse()
    material, locator, root = _current(state.runtime, state.lease, process=state.process)
    if material != state.material or root != state.runtime_root:
        _refuse()
    return json.loads(locator)


def bind_memory_runtime_process(claim, process):
    """After incumbent Runtime recorded/runs this exact observed original."""
    if type(claim) is not MemoryRuntimeClaim or claim not in _ISSUED:
        _refuse()
    state = _ISSUED[claim]
    if state.pid != os.getpid() or state.process is not None:
        _refuse()
    material, _, root = _current(state.runtime, state.lease, process=process)
    if material != state.material or root != state.runtime_root:
        _refuse()
    _ISSUED[claim] = replace(state, process=process)
