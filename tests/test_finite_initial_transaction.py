"""Actual Runtime/SQLite claim and lifecycle; explicit synthetic owner fixtures.

No physical/foreground authentication is claimed by the private fixture mint.
The common Runtime checks, canonical plan/claim/events, rollback and SQLite
concurrency are real, unlike the prior prospective reference model.
"""
import dataclasses
import json
import time
from types import SimpleNamespace
import pytest
from control_plane import executive_runtime as rt
from control_plane import finite_initial_admission as initial
from control_plane import foreground_operation as fg
from control_plane.fabric_attended_routing import installed_control_placements, placement_member
from control_plane.model_router import ModelRouter
from control_plane.native_capacity_v2 import canonical
from tests import test_executive_finite_guards as helpers
from tests.test_installed_finite_control import finite_raw
from tests.test_native_capacity_v2 import good_snapshot

@pytest.fixture
def setup(tmp_path,monkeypatch):
    selected=installed_control_placements(finite_raw())[0]
    member=placement_member(ModelRouter.load(),selected)
    def binding():
        b=helpers._v3_execution_binding()
        b['operator_harness_armed']=True
        b['work_placement_union'].append(member)
        return b
    steps=helpers._plan_steps
    def plan(count,**kw):
        return [dict(s,attempt_limit=1,placement={'provider_realm':'minimax','quota_class':initial.QUOTA})
                for s in steps(count,**kw)]
    monkeypatch.setattr(helpers,'_v2_armed_binding',binding)
    monkeypatch.setattr(helpers,'_plan_steps',plan)
    finish=helpers._complete_ohf_role
    def completed(runtime,dispatch,body,**kw):
        if body.get('schema_version')=='mastermind.execution_plan/v1':
            body=dict(body,schema_version='mastermind.execution_plan/v2')
        return finish(runtime,dispatch,body,**kw)
    monkeypatch.setattr(helpers,'_complete_ohf_role',completed)
    clock=helpers.MutableClock(time.time_ns()//1_000_000)
    state=helpers._drive_to_admitted(tmp_path/'runtime',clock,steps=1)
    runtime=state.runtime;job=state.work_jobs[0]
    snapshot,join=good_snapshot(clock.value)
    route=member['attended_route']
    runtime.workers.register_worker(initial.WORKER,provider='minimax',account_label='mastermind-minimax',
        worker_type='attended-fabric',status=rt.WorkerStatus.OFFLINE,capabilities=['research'],
        quota_classes={initial.QUOTA:dict(provider='minimax',model=route['model'],effort=route['effort'],
            cost_class=route['cost_class'],capabilities=['research'],
            metadata=dict(route,attended_route=route,capacity_join=join,finite_initial_capacity=initial.CLASSIFICATION))})
    command=f'coo-cycle:{job.root_job_id}:dispatch:{job.job_id}:attempt:1'
    with runtime.store.read() as c: epoch=initial._read_epoch(c,job.job_id,command)
    operation=object.__new__(fg.ForegroundOperation)
    operation._runtime=runtime;operation._root=job.root_job_id;operation._closed=False
    operation._command=epoch['root_creation']['command_id'];operation._operation_key=initial.OPERATION
    operation._arguments_sha256=initial.ARGUMENTS
    operation._principal=SimpleNamespace(issued_at=int(time.time())-1,expires_at=int(time.time())+1000,scopes=tuple(fg._SCOPES))
    operation._root_event_sha256=fg._digest(runtime.store.find_event_by_command_id(operation._command))
    operation._host_current=lambda:None
    evidence={'schema':'mastermind.finite_initial_claim/v1','provider_capacity':snapshot,
        'physical_capacity':{'host_ref':join['host_ref'],'boot_ref':snapshot['slots'][0]['boot_ref'],
                             'deadline_ms':clock.value+10000}}
    prepared=initial._Prepared(runtime.store,job.job_id,command,canonical(epoch),canonical(evidence),
        clock.value+10000,time.monotonic()+10,operation,initial._MINT)
    token=fg._ACTIVE.set(operation)
    try:yield SimpleNamespace(runtime=runtime,job=job,command=command,p=prepared,clock=clock,operation=operation)
    finally:fg._ACTIVE.reset(token)

def claim(s,prepared=True):
    return s.runtime.attempts.claim_job(s.job.job_id,worker_id=initial.WORKER,
        quota_class=initial.QUOTA,command_id=s.command,
        _coo_cycle_dispatch_capability=rt._COO_CYCLE_DISPATCH_CAPABILITY,
        _initial_prepared=s.p if prepared else None)

def snap(s):
    with s.runtime.store.read() as c:
        return {t:[dict(r) for r in c.execute('SELECT * FROM '+t)]
                for t in ('jobs','attempts','workers','worker_quota_classes','events')}

def test_real_atomic_claim_has_one_attempt_and_no_available_interval(setup):
    s=setup;lease=claim(s)
    assert isinstance(lease,rt.AttemptLease)
    quota=s.runtime.workers.get_quota_class(initial.WORKER,initial.QUOTA)
    assert quota.status==rt.WorkerStatus.BUSY and quota.active_attempt_id==lease.attempt.attempt_id
    event=s.runtime.store.get_event_by_command_id(s.command)
    assert event.payload['capacity_evidence']['provider_capacity']['schema']=='mastermind.provider_capacity.v2'
    before=snap(s);s.clock.advance(seconds=60);s.operation._closed=True
    replay=claim(s,False)
    assert replay.attempt.attempt_id==lease.attempt.attempt_id and not replay.claimed_now
    assert snap(s)==before

@pytest.mark.parametrize('fault',['root','parent','command','candidate','grant','expiry','origin','physical','provider'])
def test_drift_rolls_back_all_actual_rows(setup,fault):
    s=setup
    if fault=='command':s.command+='-foreign'
    elif fault=='expiry':s.clock.advance(seconds=11)
    elif fault=='origin':s.operation._closed=True
    elif fault in {'root','parent'}:
        epoch=json.loads(s.p.epoch_json)
        epoch['lineage'][0]['root_job_id' if fault=='root' else 'parent_job_id']='foreign'
        if fault=='root':s.operation._root='foreign'
        s.p=dataclasses.replace(s.p,epoch_json=canonical(epoch))
    elif fault in {'physical','provider'}:
        evidence=s.p.evidence
        if fault=='physical':evidence['physical_capacity']['boot_ref']='boot-'+'9'*64
        else:evidence['provider_capacity']['slots'][0]['provider_enabled']=None
        if fault=='provider':
            from control_plane.native_capacity_v2 import digest
            v=evidence['provider_capacity'];v['snapshot_hash']=digest({k:x for k,x in v.items() if k!='snapshot_hash'})
        s.p=dataclasses.replace(s.p,evidence_json=canonical(evidence))
    else:
        with s.runtime.store.transaction() as c:
            if fault=='candidate':c.execute('UPDATE worker_quota_classes SET version=version+1 WHERE worker_id=?',(initial.WORKER,))
            if fault=='grant':c.execute('UPDATE jobs SET priority=priority+1 WHERE job_id=?',(s.job.job_id,))
    before=snap(s)
    with pytest.raises((rt.RuntimeProofError,ValueError)):claim(s)
    assert snap(s)==before

def test_exception_after_activation_before_common_claim_rolls_back(setup,monkeypatch):
    s=setup;before=snap(s)
    monkeypatch.setattr(rt,'_capacity_matches_route',lambda *a:False)
    with pytest.raises(rt.StateConflict,match='common claim refused'):claim(s)
    assert snap(s)==before

def test_generic_status_or_release_cannot_enable_unused_quota(setup):
    s=setup;before=snap(s)
    with pytest.raises(rt.StateConflict,match='cannot commit AVAILABLE'):
        s.runtime.workers.set_worker_status(initial.WORKER,rt.WorkerStatus.AVAILABLE)
    assert snap(s)==before
    with pytest.raises(rt.StateConflict,match='cannot commit AVAILABLE'):
        s.runtime.workers.release_worker(initial.WORKER)
    assert snap(s)==before

def test_terminal_failure_and_restart_keep_quota_offline(setup):
    s=setup;lease=claim(s)
    s.runtime.attempts.fail_attempt(lease.attempt.attempt_id,fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token,payload={'reason':'inert fixture'})
    assert s.runtime.workers.get_quota_class(initial.WORKER,initial.QUOTA).status==rt.WorkerStatus.OFFLINE
    reopened=rt.Runtime.at(s.runtime.store.root)
    reopened.workers.release_worker(initial.WORKER)
    assert reopened.workers.get_quota_class(initial.WORKER,initial.QUOTA).status==rt.WorkerStatus.OFFLINE
    replay=claim(s,False)
    assert replay.outcome=='TERMINAL' and replay.lease_token is None


def test_concurrent_same_command_has_exactly_one_claim_and_one_attempt(setup):
    import contextvars
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    s=setup;barrier=Barrier(2)
    def run():
        barrier.wait(timeout=5)
        return claim(s)
    contexts=[contextvars.copy_context(),contextvars.copy_context()]
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(ctx.run,run) for ctx in contexts]
        results=[f.result(timeout=10) for f in futures]
    assert sum(isinstance(r,rt.AttemptLease) for r in results)==1
    assert sum(getattr(r,"claimed_now",False) is False for r in results if not isinstance(r,rt.AttemptLease))==1
    assert len({r.attempt.attempt_id for r in results})==1
    with s.runtime.store.read() as c:
        assert c.execute('SELECT COUNT(*) FROM attempts WHERE worker_id=?',(initial.WORKER,)).fetchone()[0]==1
        assert c.execute('SELECT COUNT(*) FROM events WHERE command_id=?',(s.command,)).fetchone()[0]==1
        assert c.execute('SELECT fence_counter FROM worker_quota_classes WHERE worker_id=?',(initial.WORKER,)).fetchone()[0]==1


def test_event_failure_after_attempt_insert_rolls_back_activation_and_claim(setup,monkeypatch):
    s=setup;before=snap(s);append=s.runtime.store.append_event
    def fail(c,**kw):
        if kw.get('event_type')=='JOB_CLAIMED' and kw.get('worker_id')==initial.WORKER:
            assert c.execute('SELECT COUNT(*) FROM attempts WHERE worker_id=?',(initial.WORKER,)).fetchone()[0]==1
            raise RuntimeError('injected persistence failure')
        return append(c,**kw)
    monkeypatch.setattr(s.runtime.store,'append_event',fail)
    with pytest.raises(RuntimeError,match='injected'):claim(s)
    assert snap(s)==before


@pytest.mark.parametrize('action',['remove','replace','extra-quota'])
def test_classification_cannot_be_removed_or_extended_after_registration(setup,action):
    s=setup;before=snap(s)
    with pytest.raises(rt.StateConflict):
        with s.runtime.store.transaction() as c:
            if action=='extra-quota':
                c.execute('INSERT INTO worker_quota_classes(worker_id,quota_class,status,provider,capabilities_json,metadata_json,created_at_ms,updated_at_ms) VALUES(?,?,?,?,?,?,?,?)',
                    (initial.WORKER,'other','OFFLINE','minimax','[]','{}',s.clock.value,s.clock.value))
            else:
                metadata=json.loads(initial._read_epoch(c,s.job.job_id,s.command)['quota']['metadata_json'])
                if action=='remove':metadata.pop('finite_initial_capacity')
                else:metadata['capacity_join']['capability_generation']+=1
                c.execute('UPDATE worker_quota_classes SET metadata_json=? WHERE worker_id=?',(canonical(metadata),initial.WORKER))
    assert snap(s)==before


@pytest.mark.parametrize('method',['checkpoint-cancel','expiry','cancel-expiry'])
def test_existing_lifecycle_never_releases_one_shot_capacity(setup,method):
    s=setup;lease=claim(s)
    kw=dict(fence_generation=lease.attempt.fence_generation,lease_token=lease.lease_token)
    if method=='checkpoint-cancel':
        s.runtime.attempts.checkpoint_attempt(lease.attempt.attempt_id,payload={'reason':'fixture'},**kw)
        q=s.runtime.workers.get_quota_class(initial.WORKER,initial.QUOTA)
        assert q.status==rt.WorkerStatus.BUSY
        s.runtime.jobs.cancel_job(s.job.job_id)
        s.runtime.attempts.acknowledge_cancel(lease.attempt.attempt_id,**kw)
    else:
        if method=='cancel-expiry':s.runtime.jobs.cancel_job(s.job.job_id)
        s.clock.advance(seconds=s.runtime.store.lease_seconds+1)
        lost=s.runtime.attempts.reconcile_expired(attempt_id=lease.attempt.attempt_id)
        assert len(lost)==1
    q=s.runtime.workers.get_quota_class(initial.WORKER,initial.QUOTA)
    assert q.status==rt.WorkerStatus.OFFLINE
    if method=='expiry':
        assert q.active_attempt_id==lease.attempt.attempt_id  # Unknown process custody retained.
    else:assert q.active_attempt_id is None
    assert s.runtime.workers.get_worker(initial.WORKER).status==rt.WorkerStatus.OFFLINE
    before=snap(s)
    replay=claim(s,False)
    assert replay.outcome=='TERMINAL' and replay.lease_token is None and snap(s)==before


def test_public_or_unsealed_preparation_does_not_admit(setup):
    s=setup;before=snap(s)
    for untrusted in (s.p.evidence,dataclasses.replace(s.p,_seal=object())):
        s.p=untrusted
        with pytest.raises(rt.StateConflict,match='owner-issued'):claim(s)
        assert snap(s)==before
