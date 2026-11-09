"""Discriminating regressions for original independent review P2-1/2/3."""
import dataclasses
import pytest
from control_plane import executive_runtime as rt
from control_plane import finite_initial_admission as initial
from control_plane.native_capacity_v2 import canonical
from tests.test_finite_initial_transaction import setup,claim,snap


@pytest.mark.parametrize('fault',['missing-object','missing-host','missing-boot','missing-deadline','extra','bool-deadline','string-deadline','bool-host'])
def test_private_physical_fixture_is_closed_and_typed(setup,fault):
    s=setup;e=s.p.evidence
    if fault=='missing-object':e.pop('physical_capacity')
    elif fault.startswith('missing-'):e['physical_capacity'].pop({'missing-host':'host_ref','missing-boot':'boot_ref','missing-deadline':'deadline_ms'}[fault])
    elif fault=='extra':e['physical_capacity']['admitted']=True
    elif fault=='bool-deadline':e['physical_capacity']['deadline_ms']=True
    elif fault=='string-deadline':e['physical_capacity']['deadline_ms']=str(s.clock.value+9999)
    elif fault=='bool-host':e['physical_capacity']['host_ref']=True
    s.p=dataclasses.replace(s.p,evidence_json=canonical(e));before=snap(s)
    with pytest.raises(rt.StateConflict,match='physical identity incomplete'):claim(s)
    assert snap(s)==before


def test_even_terminal_history_requires_original_admission_event(setup):
    s=setup;lease=claim(s)
    s.runtime.attempts.fail_attempt(lease.attempt.attempt_id,
        fence_generation=lease.attempt.fence_generation,lease_token=lease.lease_token,payload={})
    before=snap(s)
    # Immutable events cannot be rewritten through Runtime. Inject only the
    # read result inside this invariant to model a future malformed terminal
    # writer; all writes/rollback underneath are real SQLite.
    class MissingClaim:
        def __init__(self,c):self.c=c
        def execute(self,sql,args=()):
            if "SELECT payload_json FROM events WHERE attempt_id" in sql:
                return self.c.execute("SELECT payload_json FROM events WHERE 0")
            return self.c.execute(sql,args)
    with pytest.raises(rt.StateConflict,match='canonical admission evidence'):
        with s.runtime.store.transaction() as c:
            c.execute("UPDATE worker_quota_classes SET status='AVAILABLE' WHERE worker_id=?",(initial.WORKER,))
            initial._finish_transaction(MissingClaim(c),initial._classification_before_transaction(c))
    assert snap(s)==before


@pytest.mark.parametrize('status',[rt.WorkerStatus.OFFLINE,rt.WorkerStatus.DRAINING,rt.WorkerStatus.ERROR])
def test_existing_active_quarantine_keeps_original_custody(setup,status):
    s=setup;lease=claim(s)
    s.runtime.workers.set_worker_status(initial.WORKER,status)
    quota=s.runtime.workers.get_quota_class(initial.WORKER,initial.QUOTA)
    assert quota.status==status and quota.active_attempt_id==lease.attempt.attempt_id
    assert s.runtime.attempts.get_attempt(lease.attempt.attempt_id).status==rt.AttemptStatus.CLAIMED
