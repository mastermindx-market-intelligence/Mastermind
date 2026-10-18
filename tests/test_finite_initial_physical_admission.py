"""Negative and race proofs for the sealed finite physical admission composer.

The Runtime, reviewed SQLite schema, ResourceBroker and evaluator are real;
only owner probe seams and the foreground principal are synthetic (see
tests.test_finite_initial_transaction).
"""
import asyncio
import contextvars
import dataclasses
import json
import threading
import time
from types import SimpleNamespace
import pytest
from control_plane import executive_runtime as rt
from control_plane import executive_physical_admission as adm
from control_plane import finite_initial_admission as initial
from control_plane import native_capacity_acquisition as acquisition
from control_plane.executive_physical_resources import PhysicalResourceRefusal
from tests.test_finite_initial_transaction import (
    BOOT, GiB, physical_begin, snap, unbegun, v5, setup)
from tests.test_native_capacity_v2 import composed, reader, native, bound, enrolled, good_snapshot

FOREIGN_BOOT='boot-'+'9'*64


def _compose(s,**kw):
    args=dict(job_id=s.job.job_id,root_job_id=s.job.root_job_id,parent_job_id=s.job.parent_job_id,
        dispatch_command_id=s.command,provider_row=s.provider_row,monotonic_deadline=time.monotonic()+15)
    args.update(kw)
    return adm.compose(s.runtime.store,s.operation,None,**args)


def _refused(code,fn,*a,**kw):
    with pytest.raises(PhysicalResourceRefusal) as exc:fn(*a,**kw)
    assert exc.value.code==code,exc.value
    return exc.value


def _reserve(s,ctx,reservation):
    return s.runtime.broker.reserve_physical(reservation,caller_context=ctx)


def _job_attempts(s):
    with s.runtime.store.read() as c:
        return c.execute('SELECT COUNT(*) FROM attempts WHERE job_id=?',(s.job.job_id,)).fetchone()[0]


def _commitments(s):
    with s.runtime.store.read() as c:
        return [dict(r) for r in c.execute('SELECT * FROM physical_resource_commitments')]


@pytest.fixture
def dispatcher(unbegun,composed,monkeypatch):
    s=unbegun;source,_=composed
    async def acquire(_self):
        assert not s.runtime.store._write_connections
        return s.snapshot
    monkeypatch.setattr(acquisition.NativeCapacitySource,'acquire',acquire)
    def run():
        return asyncio.run(initial.FiniteInitialAdmission(source).dispatch(
            s.runtime,s.job.job_id,s.command,lease_owner='fixture'))
    s.dispatch=run
    return s


# --- production default stays closed -------------------------------------

def test_production_policy_and_caller_stay_closed_with_admitted_schema(tmp_path):
    _refused('POLICY_UNARMED',adm.load_admitted_policy)
    runtime=rt.Runtime.at(tmp_path/'prod')
    with runtime.store.read() as c:
        adm.require_physical_schema(c)
    for ctx in (None,{'owner_id':'forged'}):
        out=runtime.broker.reserve_physical({'command_id':'x'},caller_context=ctx)
        assert out['admitted'] is False and out['code']=='CALLER_BINDING_UNAVAILABLE'


def test_v5_compose_refuses_before_any_probe(v5):
    s=v5;before=snap(s)
    _refused('RESOURCE_SCHEMA_UNADMITTED',_compose,s)
    assert s.world.hp0==[] and snap(s)==before


# --- host / boot / policy identity -----------------------------------------

def test_foreign_host_and_boot_refuse_at_compose(unbegun):
    s=unbegun;before=snap(s)
    s.world.host='host-'+'f'*64
    _refused('HOST_MISMATCH',_compose,s)
    s.world.host=s.provider_row['host_ref'];s.world.boot=FOREIGN_BOOT
    _refused('BOOT_MISMATCH',_compose,s)
    assert s.world.hp0==[] and snap(s)==before


def test_policy_for_another_boot_generation_refuses(unbegun):
    s=unbegun;before=snap(s)
    # Runtime identity still names this boot; only the host qualification moved.
    s.world.write(boot=FOREIGN_BOOT,runtime={'boot_id':BOOT})
    _refused('HOST_QUALIFICATION_GENERATION_MISMATCH',_compose,s)
    assert snap(s)==before


# --- canonical Runtime -------------------------------------------------------

@pytest.mark.parametrize('field,value',[
    ('host_id','host-'+'f'*64),('boot_id',FOREIGN_BOOT),
    ('database_identity','sqlite-file-sha256:'+'0'*64),('schema_identity','executive-schema-sha256:'+'0'*64),
])
def test_policy_naming_another_runtime_refuses(unbegun,field,value):
    s=unbegun;before=snap(s);s.world.write(runtime={field:value})
    _refused('RUNTIME_MISMATCH',_compose,s)
    assert s.world.hp0==[] and snap(s)==before


def test_second_store_under_same_policy_refuses(unbegun,tmp_path):
    s=unbegun;other=rt.Runtime.at(tmp_path/'second')
    with other.store.read() as c:theirs=adm.runtime_identity(other.store,c)
    with s.runtime.store.read() as c:ours=adm.runtime_identity(s.runtime.store,c)
    # The second file is distinct even where its migrated schema is identical.
    assert theirs['database_identity']!=ours['database_identity']
    _refused('RUNTIME_MISMATCH',adm.compose,other.store,s.operation,None,job_id=s.job.job_id,
        root_job_id=s.job.root_job_id,parent_job_id=s.job.parent_job_id,dispatch_command_id=s.command,
        provider_row=s.provider_row,monotonic_deadline=time.monotonic()+15)


def test_boot_or_process_change_after_compose_refuses_reserve(unbegun):
    s=unbegun;before=snap(s)
    ctx,reservation=_compose(s)
    s.world.boot=FOREIGN_BOOT
    assert _reserve(s,ctx,reservation)['code']=='BOOT_MISMATCH'
    s.world.boot=BOOT;s.world.start='start-2'
    assert _reserve(s,ctx,reservation)['code']=='CALLER_BINDING_UNAVAILABLE'
    assert snap(s)==before


def test_process_identity_change_refuses(unbegun,monkeypatch):
    s=unbegun;before=snap(s);ctx,reservation=_compose(s)
    with monkeypatch.context() as m:
        m.setattr(adm.os,'getpid',lambda:ctx.pid+1)
        assert _reserve(s,ctx,reservation)['code']=='CALLER_BINDING_UNAVAILABLE'
    assert snap(s)==before


@pytest.mark.parametrize('stage',['before-reserve','before-begin'])
def test_policy_change_moves_admission(unbegun,stage):
    s=unbegun;ctx,reservation=_compose(s)
    if stage=='before-reserve':
        before=snap(s);s.world.write(disk_reserve=11*GiB)
        assert _reserve(s,ctx,reservation)['code']=='POLICY_MOVED'
        assert snap(s)==before;return
    reserved=_reserve(s,ctx,reservation);assert reserved['code']=='RESERVED'
    before=snap(s);s.world.write(disk_reserve=11*GiB)
    refs=[{'commitment_id':c['commitment_id'],'allocation_generation':c['allocation_generation'],
           'expected_revision':c['revision']} for c in reserved['receipt']['commitments']]
    begun=s.runtime.broker.begin_physical({'reservation':dict(reservation,command_id=ctx.begin_command_id),
        'commitments':refs},caller_context=ctx)
    assert begun['code']=='POLICY_MOVED' and snap(s)==before
    assert {r['state'] for r in _commitments(s)}=={'RESERVED'}


@pytest.mark.parametrize('kw,code',[
    (dict(armed=False),'POLICY_UNARMED'),
    (dict(io=True),'POOL_UNOBSERVED'),
])
def test_unqualified_policy_shapes_refuse_at_compose(unbegun,kw,code):
    s=unbegun;before=snap(s);s.world.write(**kw)
    _refused(code,_compose,s)
    assert snap(s)==before


def test_synthetic_policy_never_admits_production_caller(unbegun):
    s=unbegun;before=snap(s);s.world.write(qualification='SYNTHETIC_TEST_ONLY')
    _refused('SYNTHETIC_POLICY_REFUSED',_compose,s)
    assert snap(s)==before


def test_wait_budget_below_store_lock_refuses(unbegun):
    s=unbegun;policy=json.loads(s.world.policy_path.read_text())
    policy['waits']['database_lock_max_ms']=s.runtime.store.busy_timeout_ms-1
    s.world.policy_path.write_text(json.dumps(policy,sort_keys=True))
    before=snap(s);ctx,reservation=_compose(s)
    assert _reserve(s,ctx,reservation)['code']=='WAIT_BUDGET_EXCEEDED'
    assert snap(s)==before


def test_probe_failure_and_expired_deadline_refuse(unbegun):
    s=unbegun;before=snap(s)
    s.world.probe_error=OSError('probe refused')
    _refused('PHYSICAL_OBSERVATION_UNAVAILABLE',_compose,s)
    s.world.probe_error=None
    ctx,reservation=_compose(s,monotonic_deadline=time.monotonic()-1)
    assert _reserve(s,ctx,reservation)['code']=='DECISION_DEADLINE_EXPIRED'
    assert snap(s)==before


# --- Job / root / parent / caller ------------------------------------------

def test_wrong_root_or_parent_refuses_without_rows(unbegun):
    s=unbegun;before=snap(s)
    _refused('JOB_BINDING_MISMATCH',_compose,s,root_job_id='JOB-foreign')
    ctx,reservation=_compose(s,parent_job_id='JOB-foreign')
    assert _reserve(s,ctx,reservation)['code']=='JOB_BINDING_MISMATCH'
    assert snap(s)==before


def test_forged_or_foreign_contexts_refuse(unbegun,tmp_path):
    s=unbegun;before=snap(s);ctx,reservation=_compose(s)
    forged=[dataclasses.replace(ctx),dataclasses.replace(ctx,job_id='JOB-other'),
            object.__new__(adm.PhysicalCallerContext),{'binding':ctx.binding()}]
    for f in forged:
        assert _reserve(s,f,reservation)['code']=='CALLER_BINDING_UNAVAILABLE'
    other=rt.Runtime.at(tmp_path/'other')
    assert other.broker.reserve_physical(reservation,caller_context=ctx)['code']=='CALLER_BINDING_UNAVAILABLE'
    tampered=dict(reservation,acquisition_time_ms=reservation['acquisition_time_ms']+1,
        caller_binding=dict(reservation['caller_binding'],session_id='client-forged'))
    assert _reserve(s,ctx,tampered)['code']=='REQUEST_BINDING_MISMATCH'
    assert snap(s)==before


def test_closed_operation_and_missing_principal_identity_refuse(unbegun):
    s=unbegun;before=snap(s);ctx,reservation=_compose(s)
    s.operation._closed=True
    assert _reserve(s,ctx,reservation)['code']=='CALLER_NOT_CURRENT'
    s.operation._closed=False
    s.operation._principal.client_ref=None
    _refused('CALLER_BINDING_UNAVAILABLE',_compose,s)
    assert snap(s)==before


def test_caller_outside_policy_allowlist_is_unqualified(dispatcher):
    s=dispatcher;s.world.write(callers=[{'owner_id':'subject-'+'6'*64,'carrier_id':'minimax-finite-01','session_id':'client-other'}])
    _refused('CALLER_UNQUALIFIED',s.dispatch)
    assert _job_attempts(s)==0 and _commitments(s)==[]


# --- observations / capacity -------------------------------------------------

def test_stale_observation_refusal_is_sticky(dispatcher):
    s=dispatcher;s.world.age=5000
    _refused('STALE_OBSERVATION',s.dispatch)
    before=snap(s);s.world.age=0
    _refused('STALE_OBSERVATION',s.dispatch)
    assert snap(s)==before and _job_attempts(s)==0 and _commitments(s)==[]


def test_insufficient_capacity_refuses_without_attempt(dispatcher):
    s=dispatcher;s.world.pool_free=10*GiB
    _refused('INSUFFICIENT_CAPACITY',s.dispatch)
    assert _job_attempts(s)==0 and _commitments(s)==[]


# --- pre-BEGIN release ---------------------------------------------------------

def _abandon(s,ctx,reservation,refs,evidence=None,command=None,action='settle'):
    request={'reservation':dict(reservation,command_id=command or ctx.abandon_command_id),'commitments':refs,
             'evidence':dict(adm.ABANDON_EVIDENCE) if evidence is None else evidence}
    return getattr(s.runtime.broker,action+'_physical')(request,caller_context=ctx)


def _reserved(s):
    ctx,reservation=_compose(s)
    out=_reserve(s,ctx,reservation);assert out['code']=='RESERVED',out
    refs=[{'commitment_id':c['commitment_id'],'allocation_generation':c['allocation_generation'],
           'expected_revision':c['revision']} for c in out['receipt']['commitments']]
    return ctx,reservation,refs


def _demand_charges(s):
    with s.runtime.store.read() as c:
        return [r[0] for r in c.execute('SELECT remaining_charge FROM physical_resource_demands')]


@pytest.mark.parametrize('failure',['refused','raised'])
def test_begin_failure_releases_reservation_without_effect(dispatcher,monkeypatch,failure):
    s=dispatcher;original=s.runtime.broker.begin_physical
    def begin(request,*,caller_context):
        if failure=='raised':raise RuntimeError('writer lost before BEGIN commit')
        s.world.write(disk_reserve=11*GiB)
        return original(request,caller_context=caller_context)
    with monkeypatch.context() as m:
        m.setattr(s.runtime.broker,'begin_physical',begin)
        with pytest.raises(PhysicalResourceRefusal if failure=='refused' else RuntimeError) as exc:s.dispatch()
    if failure=='refused':assert exc.value.code=='POLICY_MOVED'
    rows=_commitments(s)
    assert rows and {r['state'] for r in rows}=={'ABANDONED_NO_EFFECT'}
    assert all(r['begin_event_id'] is None and r['settlement_event_id'] for r in rows)
    assert set(_demand_charges(s))=={0} and _job_attempts(s)==0
    before=snap(s)
    _refused('PHYSICAL_ADMISSION_ABANDONED',s.dispatch)
    assert snap(s)==before and _job_attempts(s)==0


def test_abandon_skips_deadline_but_keeps_caller_binding(unbegun,monkeypatch):
    s=unbegun;ctx,reservation,refs=_reserved(s)
    with monkeypatch.context() as m:
        m.setattr(adm,'time',SimpleNamespace(monotonic=lambda:ctx.monotonic_deadline+1,time=time.time))
        begun=s.runtime.broker.begin_physical({'reservation':dict(reservation,command_id=ctx.begin_command_id),
            'commitments':refs},caller_context=ctx)
        assert begun['code']=='DECISION_DEADLINE_EXPIRED'
        with monkeypatch.context() as n:
            n.setattr(adm.os,'getpid',lambda:ctx.pid+1)
            assert _abandon(s,ctx,reservation,refs)['code']=='CALLER_BINDING_UNAVAILABLE'
        assert {r['state'] for r in _commitments(s)}=={'RESERVED'}
        out=_abandon(s,ctx,reservation,refs)
    assert out['code']=='SETTLEMENT_RECORDED',out
    assert {r['state'] for r in _commitments(s)}=={'ABANDONED_NO_EFFECT'} and set(_demand_charges(s))=={0}


def test_abandon_after_begin_is_refused(unbegun):
    s=unbegun;ctx,begun,event=physical_begin(s)
    refs=[{'commitment_id':c['commitment_id'],'allocation_generation':c['allocation_generation'],
           'expected_revision':c['revision']} for c in begun['receipt']['commitments']]
    before=snap(s)
    assert _abandon(s,ctx,ctx.reservation,refs)['code']=='PHYSICAL_OUTCOME_AMBIGUOUS'
    assert snap(s)==before and {r['state'] for r in _commitments(s)}=={'EFFECT_MAY_HAVE_BEGUN'}


@pytest.mark.parametrize('kw,code',[
    (dict(evidence={'terminal_effect_state':'TERMINAL','pools':{},'process_terminal':True,'descendants_terminal':True}),
     'CALLER_BINDING_UNAVAILABLE'),
    (dict(evidence={'terminal_effect_state':'NO_EFFECT','pools':{},'positive_no_effect':1}),'CALLER_BINDING_UNAVAILABLE'),
    (dict(evidence=dict(adm.ABANDON_EVIDENCE,process_terminal=True)),'CALLER_BINDING_UNAVAILABLE'),
    (dict(command='begin'),'CALLER_BINDING_UNAVAILABLE'),
    (dict(command='reserve'),'CALLER_BINDING_UNAVAILABLE'),
    (dict(action='observe'),'OBSERVATION_INVALID'),
])
def test_forged_release_evidence_or_command_refuses(unbegun,kw,code):
    s=unbegun;ctx,reservation,refs=_reserved(s);before=snap(s)
    if 'command' in kw:kw['command']=getattr(ctx,kw['command']+'_command_id')
    assert _abandon(s,ctx,reservation,refs,**kw)['code']==code
    assert snap(s)==before and {r['state'] for r in _commitments(s)}=={'RESERVED'}


def test_job_cancelled_before_begin_still_releases(dispatcher,monkeypatch):
    s=dispatcher;original=s.runtime.broker.begin_physical
    def begin(request,*,caller_context):
        s.runtime.jobs.cancel_job(s.job.job_id)
        return original(request,caller_context=caller_context)
    with monkeypatch.context() as m:
        m.setattr(s.runtime.broker,'begin_physical',begin)
        _refused('JOB_BINDING_MISMATCH',s.dispatch)
    rows=_commitments(s)
    assert rows and {r['state'] for r in rows}=={'ABANDONED_NO_EFFECT'} and set(_demand_charges(s))=={0}
    assert _job_attempts(s)==0


@pytest.mark.parametrize('field',['database_identity','schema_identity'])
def test_runtime_change_after_compose_refuses_inside_writer(unbegun,monkeypatch,field):
    s=unbegun;ctx,reservation=_compose(s);real=adm.runtime_identity;before=snap(s)
    with monkeypatch.context() as m:
        m.setattr(adm,'runtime_identity',lambda store,c:dict(real(store,c),**{field:'replaced'}))
        assert _reserve(s,ctx,reservation)['code']=='RUNTIME_MISMATCH'
    assert snap(s)==before and _commitments(s)==[]
    out=_reserve(s,ctx,reservation);assert out['code']=='RESERVED',out
    refs=[{'commitment_id':c['commitment_id'],'allocation_generation':c['allocation_generation'],
           'expected_revision':c['revision']} for c in out['receipt']['commitments']]
    with monkeypatch.context() as m:
        m.setattr(adm,'runtime_identity',lambda store,c:dict(real(store,c),**{field:'replaced'}))
        assert _abandon(s,ctx,reservation,refs)['code']=='RUNTIME_MISMATCH'
    assert {r['state'] for r in _commitments(s)}=={'RESERVED'}


def test_begin_committed_after_deadline_is_never_released(dispatcher,monkeypatch):
    s=dispatcher;original=s.runtime.broker.begin_physical;settles=[]
    def begin(request,*,caller_context):
        out=original(request,caller_context=caller_context);assert out['code']=='BEGUN',out
        return dict(out,code='BEGIN_COMMITTED_DEADLINE_EXPIRED',fresh_begin=False)
    with monkeypatch.context() as m:
        m.setattr(s.runtime.broker,'begin_physical',begin)
        m.setattr(s.runtime.broker,'settle_physical',lambda *a,**kw:settles.append(a) or {})
        _refused('BEGIN_COMMITTED_DEADLINE_EXPIRED',s.dispatch)
    assert settles==[] and {r['state'] for r in _commitments(s)}=={'EFFECT_MAY_HAVE_BEGUN'}
    before=snap(s)
    _refused('PHYSICAL_OUTCOME_AMBIGUOUS',s.dispatch)
    assert snap(s)==before and _job_attempts(s)==0


# --- replay / ambiguity / concurrency ----------------------------------------

def test_prior_physical_outcome_is_never_replayed(dispatcher):
    s=dispatcher;physical_begin(s);before=snap(s)
    _refused('PHYSICAL_OUTCOME_AMBIGUOUS',s.dispatch)
    assert snap(s)==before and _job_attempts(s)==0


def test_crash_left_reservation_is_not_auto_abandoned(dispatcher):
    s=dispatcher;_reserved(s);before=snap(s)
    _refused('PHYSICAL_OUTCOME_AMBIGUOUS',s.dispatch)
    assert snap(s)==before and {r['state'] for r in _commitments(s)}=={'RESERVED'}


def test_claim_requires_exact_begin_command_aggregate_and_row(unbegun):
    s=unbegun;ctx,_,event=physical_begin(s)
    physical={'host_ref':ctx.host_ref,'request_fingerprint':ctx.fingerprint,'begin_event_id':event.event_id}
    with s.runtime.store.read() as c:
        initial._require_physical_begin(c,s.job.job_id,s.command,physical)
        for job_id,command,changed in [
                (s.job.job_id,s.command+':other',{}),
                (s.job.job_id,s.command,{'host_ref':'host-'+'f'*64}),
                (s.job.job_id,s.command,{'begin_event_id':event.event_id-1}),
                ('JOB-other',s.command,{})]:
            with pytest.raises(rt.StateConflict):
                initial._require_physical_begin(c,job_id,command,dict(physical,**changed))


def test_claimed_dispatch_cannot_reserve_again(dispatcher):
    s=dispatcher;first=s.dispatch();assert first.outcome=='ACTIVE'
    before=snap(s);ctx,reservation=_compose(s)
    out=_reserve(s,ctx,reservation)
    assert out['admitted'] is False and out['code']=='JOB_BINDING_MISMATCH'
    assert snap(s)==before and s.dispatch().attempt.attempt_id==first.attempt.attempt_id


def test_failure_after_begin_leaves_effect_ambiguous(dispatcher,monkeypatch):
    s=dispatcher
    def boom(*a,**kw):raise RuntimeError('carrier lost after BEGIN')
    with monkeypatch.context() as m:
        m.setattr(s.runtime.attempts,'dispatch_cycle_job',boom)
        with pytest.raises(RuntimeError):s.dispatch()
    assert {r['state'] for r in _commitments(s)}=={'EFFECT_MAY_HAVE_BEGUN'}
    before=snap(s)
    _refused('PHYSICAL_OUTCOME_AMBIGUOUS',s.dispatch)
    assert snap(s)==before and _job_attempts(s)==0


def test_concurrent_dispatch_has_one_winner(unbegun,composed,monkeypatch):
    # Threads share one process; cross-process exclusion is the same SQLite
    # writer lock plus the unique (host, operation, phase) commitment row.
    s=unbegun;source,_=composed;barrier=threading.Barrier(2,timeout=30)
    async def acquire(_self):
        barrier.wait();return s.snapshot
    monkeypatch.setattr(acquisition.NativeCapacitySource,'acquire',acquire)
    results=[None,None]
    def run(i,ctx):
        try:
            results[i]=ctx.run(lambda:asyncio.run(initial.FiniteInitialAdmission(source).dispatch(
                s.runtime,s.job.job_id,s.command,lease_owner=f'racer-{i}')))
        except Exception as exc:results[i]=exc
    threads=[threading.Thread(target=run,args=(i,contextvars.copy_context())) for i in range(2)]
    for t in threads:t.start()
    for t in threads:t.join(60)
    wins=[r for r in results if not isinstance(r,Exception)]
    losses=[r for r in results if isinstance(r,Exception)]
    assert wins,results
    # A loser never writes a second outcome: it sees the winner's durable rows.
    assert all(isinstance(e,PhysicalResourceRefusal) and e.code in
        {'RECONCILED','PHYSICAL_OUTCOME_AMBIGUOUS','JOB_BINDING_MISMATCH','COMMAND_REPLAYED'} for e in losses),losses
    assert len({w.attempt.attempt_id for w in wins})==1 and _job_attempts(s)==1
    rows=_commitments(s)
    assert rows and {r['state'] for r in rows}=={'EFFECT_MAY_HAVE_BEGUN'}
    assert len({r['request_fingerprint'] for r in rows})==1
