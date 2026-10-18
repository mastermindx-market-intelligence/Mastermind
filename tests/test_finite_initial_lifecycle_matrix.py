"""Additional actual SQLite lifecycle cases. Completion never bypasses its seal.

The matrix directly stages the pre-existing terminal owner's final row updates
inside the real Runtime transaction, to exercise its new common invariant. This
is explicitly NOT a positive completed worker/result validation or physical run.
"""
import pytest
from control_plane import executive_runtime as rt
from control_plane import finite_initial_admission as initial
from tests.test_finite_initial_transaction import setup,claim,snap


def test_real_completion_rejects_unsealed_result_without_releasing(setup):
    s=setup;lease=claim(s);before=snap(s)
    with pytest.raises(rt.StateConflict):
        s.runtime.attempts.complete_attempt(lease.attempt.attempt_id,
            fence_generation=lease.attempt.fence_generation,lease_token=lease.lease_token,
            payload={'schema_version':'mastermind.work_result/v1'})
    assert snap(s)==before


@pytest.mark.parametrize('terminal',['COMPLETED','FAILED','CANCELLED','LOST','RATE_LIMITED'])
def test_durable_terminal_invariant_matrix_survives_new_runtime(terminal,setup):
    s=setup;lease=claim(s)
    # Terminal fixture authority only; no result/exit evidence manufactured.
    with s.runtime.store.transaction() as c:
        c.execute('UPDATE attempts SET status=?,lease_token=NULL,finished_at_ms=?,result_json=? WHERE attempt_id=?',(terminal,s.clock.value,'{"fixture_only":true}',lease.attempt.attempt_id))
        c.execute('UPDATE jobs SET status=?,result_json=? WHERE job_id=?',(terminal,'{"fixture_only":true}',s.job.job_id))
        c.execute("UPDATE worker_quota_classes SET status='AVAILABLE',held_attempt_id=NULL WHERE worker_id=?",(initial.WORKER,))
    reopened=rt.Runtime.at(s.runtime.store.root)
    reopened.workers.release_worker(initial.WORKER)
    q=reopened.workers.get_quota_class(initial.WORKER,initial.QUOTA)
    assert q.status==rt.WorkerStatus.OFFLINE and q.active_attempt_id is None


@pytest.mark.parametrize('action',['rate-limit','verified-lost'])
def test_real_uncertain_process_lifecycle_keeps_custody_offline(setup,action):
    s=setup;lease=claim(s)
    kw=dict(fence_generation=lease.attempt.fence_generation,lease_token=lease.lease_token)
    if action=='rate-limit':
        s.runtime.attempts.rate_limit_attempt(lease.attempt.attempt_id,**kw)
    else:
        # Synthetic persisted identity; no provider/process was started.
        s.runtime.attempts.record_process(lease.attempt.attempt_id,provider_session_id='inert-owner-fixture',**kw)
        s.runtime.attempts.mark_lost(lease.attempt.attempt_id,reason='fixture identity absent',verified_process_absent=True,**kw)
    q=s.runtime.workers.get_quota_class(initial.WORKER,initial.QUOTA)
    assert q.status==rt.WorkerStatus.OFFLINE and q.active_attempt_id==lease.attempt.attempt_id
    before=snap(s)
    with pytest.raises(rt.StateConflict):s.runtime.workers.release_worker(initial.WORKER)
    assert snap(s)==before
