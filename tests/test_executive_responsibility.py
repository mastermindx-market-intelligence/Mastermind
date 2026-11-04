import dataclasses
import pytest
from control_plane.executive_responsibility import (
    SCHEMA, ResponsibilityIntent, ResponsibilityIntentError,
    normalize_responsibility_intent,
)


def intent(role='operator',mode='execute'):
    return dict(schema_version=SCHEMA,responsibility_role=role,execution_mode=mode)


def test_alias_is_one_canonical_digest():
    a=normalize_responsibility_intent(intent('sub-orchestrator','coordinate'))
    b=normalize_responsibility_intent(intent('sub_orchestrator','coordinate'))
    assert a==b and a.digest==b.digest
    assert a.to_dict()==intent('sub_orchestrator','coordinate')
    with pytest.raises(dataclasses.FrozenInstanceError):a.execution_mode='execute'


@pytest.mark.parametrize('role',['principal','sub_orchestrator','operator','worker'])
def test_role_does_not_bind_model_grant_or_children(role):
    result=normalize_responsibility_intent(intent(role))
    assert set(result.to_dict())=={'schema_version','responsibility_role','execution_mode'}
    assert not hasattr(result,'allowed_child_roles')


@pytest.mark.parametrize('extra',['root','parent','grant','allowed_child_roles','model','task_class','orchestration_role'])
def test_caller_authority_fields_refused(extra):
    with pytest.raises(ResponsibilityIntentError):normalize_responsibility_intent({**intent(),extra:'forged'})


@pytest.mark.parametrize('role',['orchestration','domain_orchestration','Worker',' worker','',None,True,17])
def test_task_classes_unknown_roles_and_coercions_refused(role):
    with pytest.raises(ResponsibilityIntentError):normalize_responsibility_intent(intent(role))


@pytest.mark.parametrize('value',[None,[],{},'operator',{'schema_version':SCHEMA},dict(intent(),schema_version='v2')])
def test_malformed_version_or_shape_refused(value):
    with pytest.raises(ResponsibilityIntentError):normalize_responsibility_intent(value)


def test_worker_never_gets_coordinate_mode():
    with pytest.raises(ResponsibilityIntentError,match='worker cannot coordinate'):
        normalize_responsibility_intent(intent('worker','coordinate'))


@pytest.mark.parametrize('role,mode,phase,valid',[
 ('operator','execute','work',True),('worker','execute','review',True),
 ('operator','execute','repair',True),('operator','execute','aggregation',False),
 ('sub_orchestrator','coordinate','plan',True),('operator','coordinate','aggregation',True),
 ('operator','coordinate','work',False),('operator','execute','unknown',False),
])
def test_phase_remains_separate_and_coherent(role,mode,phase,valid):
    result=normalize_responsibility_intent(intent(role,mode))
    if valid:result.require_phase(phase)
    else:
        with pytest.raises(ResponsibilityIntentError):result.require_phase(phase)


def test_detached_canonical_output_and_digest():
    raw=intent();result=normalize_responsibility_intent(raw);digest=result.digest
    raw['responsibility_role']='principal'
    projected=result.to_dict();projected['execution_mode']='coordinate'
    assert result.to_dict()==intent() and result.digest==digest
    assert ResponsibilityIntent('operator','coordinate').digest!=digest


def test_router_keeps_role_separate_from_model_and_capabilities():
    from control_plane.model_router import ModelRouter, WorkRequest
    router=ModelRouter.load()
    legacy=router.route(WorkRequest('implementation'))
    for name in ('worker','operator','principal','sub-orchestrator'):
        selected=router.route(WorkRequest('implementation',responsibility_intent=intent(name)))
        assert selected.suitability_tiers==legacy.suitability_tiers
        assert selected.required_capabilities==legacy.required_capabilities
        assert selected.execution_profile_digest==legacy.execution_profile_digest
        body=selected.to_dict();assert body['responsibility_intent']==intent(name.replace('-','_'))
        constraints=selected.job_constraints()
        assert constraints['responsibility_intent_digest']==selected.responsibility_intent.digest
        constraints.pop('responsibility_intent');constraints.pop('responsibility_intent_digest')
        assert constraints==legacy.job_constraints()
    assert 'responsibility_intent' not in legacy.to_dict()


def test_router_does_not_convert_coordinate_intent_to_worker_admission():
    from control_plane.model_router import ModelRouter, WorkRequest, RoutingPolicyError
    selected=ModelRouter.load().route(WorkRequest('implementation',responsibility_intent=intent('operator','coordinate')))
    with pytest.raises(RoutingPolicyError,match='coordinator admission'):selected.job_constraints()


@pytest.mark.parametrize('value',[intent('mystery'),dict(intent(),allowed_child_roles=['worker']),True])
def test_router_rejects_invalid_intent_at_request_construction(value):
    from control_plane.model_router import WorkRequest, RoutingPolicyError
    with pytest.raises(RoutingPolicyError):WorkRequest('implementation',responsibility_intent=value)


def test_runtime_persists_the_exact_direct_intent(tmp_path):
    from control_plane.executive_runtime import Runtime
    from control_plane.model_router import ModelRouter, WorkRequest
    decision=ModelRouter.load().route(WorkRequest('implementation',responsibility_intent=intent()))
    runtime=Runtime.at(tmp_path)
    job=runtime.jobs.create_job('Role-aware bounded work',constraints=decision.job_constraints())
    reread=runtime.jobs.get_job(job.job_id)
    assert reread.constraints['responsibility_intent']==intent()
    assert reread.constraints['responsibility_intent_digest']==decision.responsibility_intent.digest
    assert reread.orchestration_role is None
    assert 'children' not in reread.constraints


@pytest.mark.parametrize('fault',['unknown','digest','missing','extra','coordinate','orphan-digest'])
def test_runtime_rejects_bad_role_before_job_insert(tmp_path,fault):
    from control_plane.executive_runtime import Runtime, StateConflict
    role=ResponsibilityIntent('operator','execute')
    constraints={'responsibility_intent':role.to_dict(),'responsibility_intent_digest':role.digest}
    if fault=='unknown':constraints['responsibility_intent']['responsibility_role']='unknown'
    elif fault=='digest':constraints['responsibility_intent_digest']='0'*64
    elif fault=='missing':constraints.pop('responsibility_intent_digest')
    elif fault=='extra':constraints['responsibility_intent']['grant']='all'
    elif fault=='coordinate':
        role=ResponsibilityIntent('operator','coordinate');constraints={'responsibility_intent':role.to_dict(),'responsibility_intent_digest':role.digest}
    else:constraints.pop('responsibility_intent')
    runtime=Runtime.at(tmp_path)
    with pytest.raises(StateConflict):runtime.jobs.create_job('must not insert',constraints=constraints)
    import sqlite3
    with sqlite3.connect(runtime.store.path) as conn:
        assert conn.execute('select count(*) from jobs').fetchone()[0]==0


class _InertDataBoundary:
    """Test-only inert DATA boundary: no provider start, no transport, never paid."""

    adapter_id = "fixture"


def test_startup_prompt_retains_intent_without_new_authority(tmp_path):
    from types import MethodType, SimpleNamespace
    from control_plane.executive_runtime import Runtime
    from control_plane.executive_supervisor import ExecutiveSupervisor
    from control_plane.model_router import ModelRouter, WorkRequest
    import json
    runtime=Runtime.at(tmp_path)
    decision=ModelRouter.load().route(WorkRequest('implementation',responsibility_intent=intent()))
    job=runtime.jobs.create_job('role test',constraints=decision.job_constraints())
    host=SimpleNamespace(runtime=runtime,adapter=_InertDataBoundary(),
                         _commission_prompt_suffix=lambda *a:'')
    host._product_acceptance_review_suffix = MethodType(
        ExecutiveSupervisor._product_acceptance_review_suffix, host)
    host._reviewed_role_prompt_suffix = MethodType(
        ExecutiveSupervisor._reviewed_role_prompt_suffix, host)
    attempt=SimpleNamespace(attempt_id='test-attempt',worker_id='test-worker',quota_class='default')
    prompt=ExecutiveSupervisor._prompt(host,job,attempt)
    packet=json.loads(prompt[prompt.index('{'):])
    assert packet['responsibility_intent']==intent()
    assert packet['responsibility_intent_digest']==decision.responsibility_intent.digest
    assert 'grants no model, tools, children' in packet['responsibility_scope']
    assert packet['authorities']==job.requested_authorities
