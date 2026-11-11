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


# --- WO-05 (census C4.4): admitted classification records at the boundary ------

ROOT=Path(__file__).parents[1]


def _binding():
    return dict(root_id='JOB-root',job_id='JOB-child',attempt_id='ATT-1',
                effective_grant_digest='a'*64,commission_sha256='b'*64)


def test_admitted_record_issuer_derives_from_claim_authorities():
    from control_plane.child_execution_contracts import C2_COMPLEX_BOUNDED, POLICY_REVISION
    from control_plane.executive_paid_fabric_adapter import paid_child_admission_record
    from control_plane.paid_fabric_backend import (PAID_CHILD_ADMISSION_SCHEMA,
                                                   admitted_child_class_record)
    binding=_binding()
    research=SimpleNamespace(requested_authorities=['READ','RESEARCH'],
                             orchestration_role='work')
    record=paid_child_admission_record(research,binding)
    assert record['schema']==PAID_CHILD_ADMISSION_SCHEMA
    assert record['task_kind']=='research'
    assert record['effective_complexity']==C2_COMPLEX_BOUNDED
    assert record['witness_disposition']=='not_required'
    assert record['policy_revision']==POLICY_REVISION
    read_only=SimpleNamespace(requested_authorities=['READ'],
                              orchestration_role='repair')
    assert paid_child_admission_record(read_only,binding)['task_kind']=='repair'
    derived=admitted_child_class_record(dict(binding=binding,paid_child_admission=record))
    assert derived==('research',C2_COMPLEX_BOUNDED,'not_required',POLICY_REVISION)


def test_admission_digest_conflicts_on_replay_with_different_claim():
    from control_plane.executive_paid_fabric_adapter import paid_child_admission_record
    job=SimpleNamespace(requested_authorities=['READ','RESEARCH'],
                        orchestration_role='work')
    record=paid_child_admission_record(job,_binding())
    other=paid_child_admission_record(job,dict(_binding(),attempt_id='ATT-2'))
    # Same child key with a different claim digest is a conflict, never a reuse.
    assert record['admission_digest']!=other['admission_digest']
    assert paid_child_admission_record(job,_binding())==record


def test_witness_disposition_follows_shared_routing_law():
    from control_plane.child_execution_contracts import (ChildRoutingPolicy,
                                                         WITNESS_DISPOSITIONS,
                                                         witness_disposition_of)
    downgraded=ChildRoutingPolicy().evaluate('frontier','ungated frontier work','')
    assert witness_disposition_of(downgraded)=='downgraded'
    plain=ChildRoutingPolicy().evaluate('routine','ordinary bounded work','')
    assert witness_disposition_of(plain)=='not_required'
    assert set(WITNESS_DISPOSITIONS)=={'not_required','accepted','insufficient','downgraded'}


def test_runtime_floor_consumes_every_projected_complexity():
    from control_plane.child_execution_contracts import CANONICAL_TASK_COMPLEXITIES
    source=(ROOT/'ops/native_fabric/quota_continuity/candidate/remote_sub.sh').read_text()
    case=source.split('case "${POOL_TASK_COMPLEXITY:-}" in')[1].split('esac')[0]
    # fabric_task.py reads POOL_TASK_COMPLEXITY as existing economic metadata and
    # the lane runtime lifts its floor on exactly the canonical long names.
    for name in CANONICAL_TASK_COMPLEXITIES:
        assert name in case


def test_operator_issue_consumer_requires_the_mapped_literal():
    from control_plane.paid_fabric_backend import (LEGACY_OPERATOR_TASK_CLASS,
                                                   legacy_pool_task_class)
    issue=(ROOT/'integrations/session_bridge/paid_operator/fabric_operator_issue.py').read_text()
    client=(ROOT/'integrations/session_bridge/paid_operator/fabric_operator_client.py').read_text()
    assert "os.environ.get('POOL_TASK_CLASS') != 'domain_orchestration'" in issue
    assert "env.get('POOL_TASK_CLASS') != 'domain_orchestration'" in client
    assert legacy_pool_task_class(
        'domain_orchestration')==LEGACY_OPERATOR_TASK_CLASS=='domain_orchestration'
    assert legacy_pool_task_class('research')=='research'


def test_fabric_task_complexity_consumer_env_name_unchanged():
    source=(ROOT/'integrations/session_bridge/prospective_completion/'
            'candidate/fabric_task.py').read_text()
    assert 'env.get("POOL_TASK_COMPLEXITY", "")' in source
