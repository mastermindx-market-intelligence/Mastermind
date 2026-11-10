"""Native scope declarations are not an owner-enforced execution capability."""
import asyncio

import pytest

from control_plane.executive_runtime import AttemptStatus, JobStatus, WorkerStatus
from control_plane.executive_supervisor import SupervisorError
from control_plane.t3_native_composition import T3NativeCompositionError
from tests.test_t3_native_composition import _record_original_native_attempt
from tests.test_t3_native_terminal_supervisor import _case


def test_governed_native_start_refuses_before_any_native_effect(tmp_path):
    case = _case(tmp_path)
    runtime, job, _workspace, wire, composition, mixed, lease = case
    owner = mixed._select(lease.attempt)
    with pytest.raises((SupervisorError, T3NativeCompositionError), match="scope.*quiescence"):
        asyncio.run(mixed._start(owner, job.job_id, lease, None))
    assert wire.calls == []
    assert composition.adapter.launch_intent(lease.attempt.attempt_id) is None
    attempt = runtime.attempts.get_attempt(lease.attempt.attempt_id)
    assert attempt.status is AttemptStatus.FAILED
    assert attempt.exit_code is None
    assert runtime.jobs.get_job(job.job_id).status is JobStatus.FAILED
    quota = runtime.workers.get_quota_class(attempt.worker_id, attempt.quota_class)
    assert quota.status is WorkerStatus.AVAILABLE
    assert quota.active_attempt_id is quota.active_job_id is None
    assert runtime.workers.get_worker(attempt.worker_id).active_job_id is None
    # No native assignment ran, so no native writer-revocation receipt is claimed.
    assert not owner._terminal_assignment_receipt_path(attempt.attempt_id).exists()
    assert mixed._active == mixed._unsettled == {}


def test_governed_native_finish_refuses_before_blocking_transport_or_acceptance(tmp_path):
    case = _case(tmp_path)
    runtime, job, _workspace, wire, composition, mixed, lease = case
    active = asyncio.run(_record_original_native_attempt(mixed, job.job_id, lease))
    before = list(wire.calls)
    with pytest.raises((SupervisorError, T3NativeCompositionError), match="scope.*quiescence"):
        asyncio.run(mixed.finish_job(active))
    assert wire.calls == before
    assert runtime.jobs.get_job(job.job_id).status is JobStatus.RUNNING
    assert runtime.attempts.get_attempt(lease.attempt.attempt_id).status is AttemptStatus.RUNNING
    assert runtime.attempts.get_attempt(lease.attempt.attempt_id).exit_code is None
    assert composition.adapter.result_ledger_entry(lease.attempt.attempt_id) is None
    assert lease.attempt.attempt_id in mixed._unsettled


def test_parsed_native_text_cannot_bypass_terminal_scope_fence(tmp_path):
    case = _case(tmp_path)
    runtime, job, _workspace, wire, _composition, mixed, lease = case
    active = asyncio.run(_record_original_native_attempt(mixed, job.job_id, lease))
    owner = mixed._select(lease.attempt)
    observation = asyncio.run(owner.adapter.collect_result(active.process_ref))
    assert observation.native_terminal.native_status == "completed"
    path = owner._persist_collection(active, observation)
    with pytest.raises((SupervisorError, T3NativeCompositionError), match="scope.*quiescence"):
        asyncio.run(owner._terminalize(active, observation, path))
    assert runtime.jobs.get_job(job.job_id).status is JobStatus.RUNNING
    assert not owner._terminal_assignment_receipt_path(lease.attempt.attempt_id).exists()


def test_boundary_adapter_start_cannot_bypass_governed_profile_fence(tmp_path):
    case = _case(tmp_path)
    _runtime, job, _workspace, wire, _composition, mixed, lease = case
    owner = mixed._select(lease.attempt)
    schema = owner._write_schema(owner._run_dir(lease.attempt.attempt_id),
        job=job, attempt=lease.attempt, effective_grant=None)
    spec = owner._launch_spec(job, lease, schema, None, None, None)
    with pytest.raises(T3NativeCompositionError, match="scope.*quiescence"):
        asyncio.run(owner.adapter.start(spec))
    assert wire.calls == []
