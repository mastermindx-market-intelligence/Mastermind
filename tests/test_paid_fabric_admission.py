"""Real local Runtime status ownership and inert admission-gate DATA tests."""
import copy
from types import SimpleNamespace
from pathlib import Path
import pytest
from control_plane.executive_runtime import Runtime,StateConflict
from control_plane import paid_fabric_admission as admission
from control_plane import paid_fabric_bootstrap as helper
from control_plane.executive_service import ExecutiveControlService
from tests.test_paid_fabric_capacity import _Base,_FakeGateway


@pytest.fixture
def runtime(tmp_path):
    r=Runtime.at(tmp_path)
    r.workers.register_worker('status-worker',provider='glm',account_label='selected',
        worker_type='canonical-paid-fabric',capabilities=['read','research'],quota_classes={
            'paid-read':dict(provider='glm',model='glm-5.3-flash',effort='none',cost_class='small',
                             capabilities=['read','research'])})
    return r


def reserve(r,scope=None):
    return admission._reserve_status(r,'status-worker','paid-read',scope or {'source':'actual-fixture-source'})


def test_pending_owner_reconciles_same_original_id_never_replaces(runtime):
    operation,mode=reserve(runtime);assert mode=='bootstrap'
    assert reserve(runtime)==(operation,'reconcile')
    with pytest.raises(StateConflict):reserve(runtime,{'source':'drift'})
    assert len(runtime.events.list_events())>=1


@pytest.mark.parametrize('state,reason',[(helper.STATE_AUTH_REFUSED,helper.REASON_AUTH_REFUSED),
    (helper.STATE_RATE_LIMITED,helper.REASON_RATE_LIMITED),(helper.STATE_UNKNOWN,helper.REASON_LOST)])
def test_retained_refusal_unknown_blocks_new_status_operation(runtime,state,reason):
    scope={'source':'actual-fixture-source'};operation,_=reserve(runtime,scope)
    result=helper._result(state,reason,'selected',1,previous_reading_retained=True)
    admission._retain_status(runtime,'status-worker','paid-read',scope,operation,result)
    admission._retain_status(runtime,'status-worker','paid-read',scope,operation,result)
    assert reserve(runtime,scope)==(operation,'reconcile')
    with pytest.raises(StateConflict):
        admission._retain_status(runtime,'status-worker','paid-read',scope,'replacement',result)


def test_only_retained_complete_observed_outcome_allows_another_explicit_status_intent(runtime):
    scope={'source':'actual-fixture-source'};operation,_=reserve(runtime,scope)
    result=helper._result(helper.STATE_OBSERVED,helper.REASON_OBSERVED,'selected',1,
        observed_at=1,pct_5h=1,pct_week=2,pair_complete=True,fresh=True,committed=True)
    admission._retain_status(runtime,'status-worker','paid-read',scope,operation,result)
    successor,mode=reserve(runtime,scope)
    assert mode=='bootstrap' and successor!=operation
    assert reserve(runtime,scope)==(successor,'reconcile')


@pytest.fixture
def observation():
    fixture=_Base();fixture.setUp()
    try:
        _,value=fixture.observe(fixture.full_table(),_FakeGateway(Path(fixture.db_path)))
        yield fixture.now,value
    finally:fixture.doCleanups()


def service(monkeypatch,now):
    from control_plane import executive_service as module
    from control_plane import codex_worker
    monkeypatch.setattr(module.time,'time',lambda:now)
    s=object.__new__(ExecutiveControlService)
    s.config=SimpleNamespace(coo_autonomy_armed=True);s._service_state='READY'
    s._require_current_autonomy=lambda:None
    s._require_coo_worker_composed=lambda:None
    # Explicit inert R1 validation seam tests Boolean composition only; it does
    # not qualify a real canary, provider, worker or installed authority.
    s._canary_loader=lambda:{'fixture':'not-a-real-canary'}
    monkeypatch.setattr(codex_worker,'validate_secret_canary_verdict',lambda *a,**kw:None)
    return s


def test_gate_requires_current_status_and_preserves_unknown_provider_readiness(monkeypatch,observation):
    now,value=observation;s=service(monkeypatch,now)
    assert value['provider_readiness']=='UNKNOWN'
    assert s._paid_capacity_available(value)
    monkeypatch.setattr(__import__('control_plane.executive_service',fromlist=['time']).time,'time',lambda:now+20)
    assert not s._paid_capacity_available(value)
    s._canary_loader=None
    assert not s._paid_capacity_available(value)


@pytest.mark.parametrize('gate',['autonomy','coo','arm','service','canary'])
def test_each_existing_admission_guard_remains_required(monkeypatch,observation,gate):
    now,value=observation;s=service(monkeypatch,now)
    def refuse():raise ValueError('inert guard refusal')
    if gate=='autonomy':s._require_current_autonomy=refuse
    if gate=='coo':s._require_coo_worker_composed=refuse
    if gate=='arm':s.config.coo_autonomy_armed=False
    if gate=='service':s._service_state='OFFLINE'
    if gate=='canary':s._canary_loader=refuse
    assert not s._paid_capacity_available(value)


@pytest.mark.parametrize('field',['held_pool','held_account','held_model','held_host','held_route','legacy_model_count'])
def test_retained_occupancy_does_not_create_paid_capacity(monkeypatch,observation,field):
    now,value=observation;s=service(monkeypatch,now);value=copy.deepcopy(value)
    value['broker']['rows_observed']=1
    value['broker'][field]=1
    if field in {'held_account','held_model','held_route','legacy_model_count'}:value['broker']['held_pool']=1
    if field in {'held_model','held_route','legacy_model_count'}:value['broker']['held_account']=1
    if field=='held_route':value['broker'].update(held_model=1,held_host=1)
    assert not s._paid_capacity_available(value)
