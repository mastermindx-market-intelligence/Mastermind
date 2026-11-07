"""Current native target uses its held slot, not aggregate Worker availability."""
import dataclasses

import pytest

from control_plane.executive_current_target import CurrentTargetUnavailable, read_current_target
from control_plane.executive_delegation_identity import derive_delegation_identity
from control_plane.executive_runtime import WorkerStatus
from integrations.session_bridge.runtime_owner import RuntimeCodexTargetProjector, RuntimeFabricTargetProjector
from tests import test_company_inbox_iac1 as fixtures
from tests.test_company_consultation_target_resolution import _seed

def _case(tmp_path, monkeypatch):
    original = fixtures._workers
    monkeypatch.setattr(fixtures,"_workers",lambda runtime: original(runtime,extra_available_quota=True))
    s = _seed(tmp_path, monkeypatch)
    job = s.runtime.jobs.get_job(s.a[0])
    operation = derive_delegation_identity(job).operation_key
    return s, job, operation

def test_native_target_remains_current_with_another_available_class(tmp_path, monkeypatch):
    s, job, operation = _case(tmp_path, monkeypatch)
    worker = s.runtime.workers.get_worker(s.a[2])
    assert worker.status is WorkerStatus.AVAILABLE
    current = read_current_target(s.runtime, operation)
    assert current.job_id == job.job_id and current.attempt_id == s.a[1]
    assert current.worker_status is WorkerStatus.BUSY
    view = RuntimeCodexTargetProjector(RuntimeFabricTargetProjector(s.runtime),owner_configured=lambda:True)
    assert len(view.project()) == 2

@pytest.mark.parametrize("change", [
    {"status":WorkerStatus.AVAILABLE}, {"active_attempt_id":"foreign-attempt"},
    {"active_job_id":"JOB-999"}, {"worker_id":"foreign-worker"},
    {"quota_class":"foreign-quota"}, {"fence_generation":999},
])
def test_current_target_refuses_changed_exact_quota(tmp_path, monkeypatch, change):
    s, job, operation = _case(tmp_path, monkeypatch)
    original = s.runtime.workers.get_quota_class
    monkeypatch.setattr(s.runtime.workers,"get_quota_class",lambda *args: dataclasses.replace(original(*args),**change))
    with pytest.raises(CurrentTargetUnavailable):
        read_current_target(s.runtime,operation)

def test_current_target_refuses_worker_identity_offline_even_if_quota_is_busy(tmp_path, monkeypatch):
    s, job, operation = _case(tmp_path, monkeypatch)
    original = s.runtime.workers.get_worker
    monkeypatch.setattr(s.runtime.workers,"get_worker",lambda *args:dataclasses.replace(original(*args),status=WorkerStatus.OFFLINE))
    with pytest.raises(CurrentTargetUnavailable):
        read_current_target(s.runtime,operation)
