"""Actual Runtime/SQLite claim and lifecycle; explicit synthetic owner fixtures.

The foreground principal, host probes and policy file are synthetic seams; the
M2 schema candidate is enabled only by monkeypatch. The physical reservation and
BEGIN rows are written by the real ResourceBroker through the sealed caller
composer, and the common Runtime checks, canonical plan/claim/events, rollback
and SQLite concurrency are real.
"""
import dataclasses
import json
import time
from types import SimpleNamespace
import pytest
from control_plane import executive_runtime as rt
from control_plane import finite_initial_admission as initial
from control_plane import foreground_operation as fg
from control_plane import executive_physical_admission as adm
from control_plane.fabric_attended_routing import installed_control_placements, placement_member
from control_plane.model_router import ModelRouter
from control_plane.native_capacity_v2 import canonical
from tests import test_executive_finite_guards as helpers
from tests.test_installed_finite_control import finite_raw
from tests.test_native_capacity_v2 import good_snapshot

SUBJECT='subject-'+'5'*64
CLIENT='client-finite-test'
HOST='host-'+'a'*64
BOOT='boot-'+'b'*64
POOL_REF='capacity-pool-'+'c'*64
GiB=1024**3


def _finite_demands(boot,*,io=False):
    def demand(dimension,pool,peak,unit):
        return {'dimension':dimension,'capacity_pool_id':pool,'qualified_incremental_peak':peak,
                'window_binding':{'unit':unit,'window_ms':1000,'baseline_id':'finite-base-1','boot_id':boot}}
    demands=[demand('memory_bytes','memory',GiB//2,'bytes'),demand('disk_bytes','finite-runs',GiB,'bytes'),
             demand('cpu_us_per_window','cpu',1_000_000,'cpu_us'),demand('heavy_phase_count','heavy',1,'count')]
    if io:demands.append(demand('io_bytes_per_window','io',1,'io_bytes'))
    return demands


def finite_policy(*,host=HOST,boot=BOOT,armed=True,qualification='QUALIFIED',callers=None,disk_reserve=10*GiB,io=False,runtime=None):
    """A QUALIFIED armed v2 shape for tests only; never written to config/."""
    if not armed:
        return {'schema':'mastermind.physical_resource_policy.v2','production_armed':False,'qualification':'UNQUALIFIED',
            'policy_revision':None,'authority_receipt':None,'qualification_evidence':[],
            'canonical_runtime':dict.fromkeys(('runtime_id','host_id','boot_id','endpoint','database_identity','schema_identity')),
            'allowed_callers':[],'host_qualifications':[],
            'freshness':dict.fromkeys(('sample_max_age_ms','sample_cadence_ms','decision_to_effect_max_ms')),
            'waits':dict.fromkeys(('service_request_max_ms','database_lock_max_ms')),
            'recovery':dict.fromkeys(('reservation_horizon_ms','reconciliation_interval_ms'))}
    return {'schema':'mastermind.physical_resource_policy.v2','production_armed':True,'qualification':qualification,
        'policy_revision':'finite-policy-1','authority_receipt':'test-authority','qualification_evidence':['test-qualification'],
        'canonical_runtime':{'runtime_id':'runtime-test','host_id':host,'boot_id':boot,'endpoint':'test://runtime',
            'database_identity':'db-test','schema_identity':'schema-test',**(runtime or {})},
        'allowed_callers':[{'owner_id':SUBJECT,'carrier_id':'minimax-finite-01','session_id':CLIENT}] if callers is None else callers,
        'host_qualifications':[{'host_id':host,'boot_id':boot,'capacity_pool_ref':POOL_REF,
            'qualification_revision':'host-qualification-1','qualification_evidence':['test-host-evidence'],
            'physical_pools':[{'capacity_pool_id':'memory','protected_reserve':GiB},
                {'capacity_pool_id':'finite-runs','protected_reserve':disk_reserve},
                {'capacity_pool_id':'cpu','protected_reserve':1_000_000},
                {'capacity_pool_id':'heavy','protected_reserve':0},{'capacity_pool_id':'io','protected_reserve':0}],
            'profiles':[{'profile':adm.FINITE_PROFILE,'qualified_duration_ms':60_000,
                'qualification_evidence':['test-profile-evidence'],'effect_scope':['finite_native_worker_attempt'],
                'qualified_demands':_finite_demands(boot,io=io)}],
            'windows':{'cpu_window_ms':1000,'io_window_ms':1000,'normalization_evidence':'test'},
            'limits':{'cpu_budget_us':8_000_000,'cpu_protected_us':1_000_000,'memory_budget_bytes':8*GiB,
                'memory_protected_bytes':GiB,'internal_protected_bytes':GiB,'external_protected_bytes':GiB,
                'io_budget_bytes':GiB,'io_protected_bytes':0,'max_heavy_phases':2}}],
        'freshness':{'sample_max_age_ms':2000,'sample_cadence_ms':500,'decision_to_effect_max_ms':10_000},
        'waits':{'service_request_max_ms':10_000,'database_lock_max_ms':10_000},
        'recovery':{'reservation_horizon_ms':120_000,'reconciliation_interval_ms':1000}}


def physical_world(monkeypatch,tmp_path,clock,store=None,**policy):
    """Replace only the owner probe seams; the broker/composer stay real.

    The policy's canonical Runtime identity is derived from the real store.
    """
    from tests.test_executive_physical_resources import _fp1b_capacity_snapshot,_host_pressure_snapshot
    root=tmp_path/'physical';(root/'git').mkdir(parents=True);(root/'runs').mkdir()
    w=SimpleNamespace(host=HOST,boot=BOOT,start='start-1',pool_free=300*GiB,age=0,
        policy_path=root/'policy.json',probe_error=None,hp0=[])
    def write(**kw):
        merged={**policy,**kw}
        if store is not None:
            with store.read() as c:identity=adm.runtime_identity(store,c)
            merged['runtime']={**identity,**merged.get('runtime',{})}
        w.policy_path.write_text(json.dumps(finite_policy(**merged),sort_keys=True))
    w.write=write;write()
    def pressure(host,boot):
        if w.probe_error:raise w.probe_error
        return _host_pressure_snapshot(host_ref=host,boot_ref=boot,observed_at_ms=clock.value-5-w.age)
    def capacity(host,boot,pool_ref,hp0,disk_root):
        assert disk_root==str(root/'runs');w.hp0.append(hp0)
        snap=dict(_fp1b_capacity_snapshot(host_ref=host,boot_ref=boot,capacity_pool_ref=pool_ref,observed_at_ms=clock.value-2-w.age))
        snap['pool_free_bytes']=w.pool_free
        return snap
    monkeypatch.setattr(adm,'POLICY_PATH',w.policy_path)
    monkeypatch.setattr(adm,'_boot_reference',lambda:w.boot)
    monkeypatch.setattr(adm,'_process_start_identity',lambda pid:w.start)
    monkeypatch.setattr(adm,'_collect_pressure',pressure)
    monkeypatch.setattr(adm,'_collect_capacity',capacity)
    monkeypatch.setattr(adm,'_finite_host_inputs',lambda source:{'host_ref':w.host,'helper_sha256':'d'*64,
        'commit_sha':'e'*40,'git_store':str(root/'git'),'run_root':str(root/'runs')})
    return w


def enable_m2_schema(monkeypatch):
    from tests.test_executive_os_sqlite import _c2_enable_physical_candidate_schema
    _c2_enable_physical_candidate_schema(monkeypatch)


def physical_begin(s,source=None):
    """Real sealed composition plus ResourceBroker reserve/BEGIN; no claim."""
    ctx,reservation=adm.compose(s.runtime.store,s.operation,source,job_id=s.job.job_id,
        root_job_id=s.job.root_job_id,parent_job_id=s.job.parent_job_id,dispatch_command_id=s.command,
        provider_row=s.provider_row,monotonic_deadline=time.monotonic()+15)
    reserved=s.runtime.broker.reserve_physical(reservation,caller_context=ctx)
    assert reserved['code']=='RESERVED',reserved
    refs=[{'commitment_id':c['commitment_id'],'allocation_generation':c['allocation_generation'],
           'expected_revision':c['revision']} for c in reserved['receipt']['commitments']]
    begun=s.runtime.broker.begin_physical({'reservation':dict(reservation,command_id=ctx.begin_command_id),
        'commitments':refs},caller_context=ctx)
    assert begun['code']=='BEGUN' and begun['fresh_begin'] is True,begun
    return ctx,begun,s.runtime.store.get_event_by_command_id(ctx.begin_command_id)


def _build(tmp_path,monkeypatch,*,schema=True,physical=True):
    if schema:enable_m2_schema(monkeypatch)
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
    operation._principal=SimpleNamespace(issued_at=int(time.time())-1,expires_at=int(time.time())+1000,
        scopes=tuple(fg._SCOPES),subject_digest=SUBJECT,client_ref=CLIENT)
    operation._root_event_sha256=fg._digest(runtime.store.find_event_by_command_id(operation._command))
    operation._host_current=lambda:None
    world=physical_world(monkeypatch,tmp_path,clock,store=runtime.store)
    s=SimpleNamespace(runtime=runtime,job=job,command=command,p=None,clock=clock,operation=operation,
        world=world,snapshot=snapshot,join=join,epoch=epoch,
        provider_row={'host_ref':join['host_ref'],'boot_ref':snapshot['slots'][0]['boot_ref']})
    token=fg._ACTIVE.set(operation)
    try:
        if physical:
            ctx,begun,event=physical_begin(s)
            deadline=min(clock.value+10000,begun['start_deadline_ms'])
            evidence={'schema':'mastermind.finite_initial_claim/v1','provider_capacity':snapshot,
                'physical_capacity':{'host_ref':ctx.host_ref,'boot_ref':ctx.boot_ref,'deadline_ms':deadline,
                    'request_fingerprint':ctx.fingerprint,'begin_event_id':event.event_id}}
            s.p=initial._Prepared(runtime.store,job.job_id,command,canonical(epoch),canonical(evidence),
                deadline,time.monotonic()+10,operation,initial._MINT)
        yield s
    finally:fg._ACTIVE.reset(token)


@pytest.fixture
def setup(tmp_path,monkeypatch):
    yield from _build(tmp_path,monkeypatch)


@pytest.fixture
def unbegun(tmp_path,monkeypatch):
    """Admitted v6 Runtime and probes with no physical outcome yet."""
    yield from _build(tmp_path,monkeypatch,physical=False)


@pytest.fixture
def v5(tmp_path,monkeypatch):
    """The actual production schema: no M2 tables are active."""
    yield from _build(tmp_path,monkeypatch,schema=False,physical=False)

def claim(s,prepared=True):
    return s.runtime.attempts.claim_job(s.job.job_id,worker_id=initial.WORKER,
        quota_class=initial.QUOTA,command_id=s.command,
        _coo_cycle_dispatch_capability=rt._COO_CYCLE_DISPATCH_CAPABILITY,
        _initial_prepared=s.p if prepared else None)

def snap(s):
    with s.runtime.store.read() as c:
        tables=['jobs','attempts','workers','worker_quota_classes','events']
        tables+=[r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' "
            "AND name LIKE 'physical_resource_%' ORDER BY name")]
        return {t:[dict(r) for r in c.execute('SELECT * FROM '+t)] for t in tables}

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

@pytest.mark.parametrize('fault',['root','parent','command','candidate','grant','expiry','origin','physical','provider',
    'begin-event','fingerprint'])
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
    elif fault in {'begin-event','fingerprint'}:
        evidence=s.p.evidence;physical=evidence['physical_capacity']
        if fault=='begin-event':physical['begin_event_id']=s.runtime.store.get_event_by_command_id(s.operation._command).event_id
        else:physical['request_fingerprint']='0'*64
        s.p=dataclasses.replace(s.p,evidence_json=canonical(evidence))
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

def test_begin_commitment_cannot_drift_without_bound_event(setup):
    s=setup;before=snap(s)
    with pytest.raises(rt.StateConflict,match='requires a new bound Event'):
        with s.runtime.store.transaction() as c:
            c.execute("UPDATE physical_resource_commitments SET state='RECONCILIATION_REQUIRED',revision=revision+1")
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
