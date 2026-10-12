"""Task-fit source proof on the existing request/binding/Runtime owners."""
import asyncio
from copy import deepcopy

import pytest
from control_plane import executive_inference_io as io
from control_plane import executive_inference_execution as execution
from control_plane import executive_inference_ingress as service
from control_plane import executive_service_principal as esp
from control_plane.executive_inference_contract import intent_id
from control_plane.executive_ceo_ingress import CeoIngressError
from control_plane.executive_runtime import Runtime

V2='mastermind.executive_service_inference_request.v2'
GROUND={'mastermind_sha':'1'*40,'macro_sha':'2'*40,'boot_packet_schema':'mastermind.ceo_boot_packet.v1'}


def legacy():
    return {'schema':io.REQUEST_SCHEMA,'system_prompt':'Research only.','input_text':'Synthetic evidence.','max_output_chars':4096}


def request(task='comparative_analysis'):
    return dict(legacy(),schema=V2,task_kind=task)


def bind(root,wire=None,identity='task-fit-fixture'):
    kwargs=dict(intent_id=identity,workspace_root=root,base_sha='a'*40,eligible_quota_classes=('fixture',))
    if wire is not None:
        kwargs['inference_request']=wire
    return execution.build_execution_binding(**kwargs)


def test_legacy_request_stays_exact_and_routes_routine(tmp_path):
    value=legacy();before=deepcopy(value)
    assert io.normalize_request(value)==before and value==before
    assert set(value)=={'schema','system_prompt','input_text','max_output_chars'}
    binding=bind(tmp_path)
    assert binding['constraints']['risk']=='routine'
    assert binding['constraints']['preferred_model_aliases']==['fast.research','standard.research']


def test_closed_v2_request_preserves_named_task_intent_and_bytes():
    value=request();before=deepcopy(value)
    try:normalized=io.normalize_request(value)
    except io.InferenceIOError:pytest.fail('closed v2 task intent is not yet supported')
    assert normalized==before and value==before
    assert len(io.canonical_bytes(normalized))<=io.MAX_REQUEST_BYTES


@pytest.mark.parametrize('value',[
    dict(legacy(),task_kind='comparative_analysis'),
    dict(legacy(),schema=V2),
    dict(request(),task_kind='use-expensive-model'),
    dict(request(),task_kind=True),dict(request(),task_kind=[]),
    dict(request(),schema=[]),dict(request(),schema='unknown'),
    dict(request(),model='untrusted'),dict(request(),provider='untrusted'),
    dict(request(),host='untrusted'),dict(request(),quota_class='untrusted'),
])
def test_invalid_or_selector_bearing_request_refuses(value):
    with pytest.raises(io.InferenceIOError):io.normalize_request(value)


def test_extraction_and_comparison_use_existing_first_lawful_tiers(tmp_path):
    try:
        ordinary=bind(tmp_path,request('evidence_extraction'))
        comparison=bind(tmp_path,request('comparative_analysis'))
    except TypeError:pytest.fail('host binding does not yet consume task intent')
    assert ordinary['constraints']['preferred_model_aliases']==['fast.research','standard.research']
    assert comparison['constraints']['preferred_model_aliases']==['standard.research']
    assert ordinary['constraints']['risk']=='routine' and comparison['constraints']['risk']=='elevated'
    assert ordinary['constraints']['execution_profile_id']==comparison['constraints']['execution_profile_id']
    assert comparison['constraints']['eligible_quota_classes']==['fixture']


def test_frontier_judgment_cannot_enter_ordinary_worker_lane(tmp_path):
    try:
        with pytest.raises(execution.InferenceExecutionBindingError,match='governed'):
            bind(tmp_path,request('contradiction_adjudication'))
    except TypeError:pytest.fail('host binding does not yet recognize frontier task intent')


def test_binding_cannot_downgrade_or_relabel_task(tmp_path):
    try:comparison=bind(tmp_path,request())
    except TypeError:pytest.fail('host binding does not yet consume task intent')
    assert execution.validate_execution_binding(comparison,intent_id='task-fit-fixture',workspace_root=tmp_path,inference_request=request())==comparison
    for value,wire in [(bind(tmp_path),request()),(comparison,legacy()),(dict(comparison,constraints=dict(comparison['constraints'],preferred_model_aliases=['fast.research'])),request())]:
        with pytest.raises(execution.InferenceExecutionBindingError):
            execution.validate_execution_binding(value,intent_id='task-fit-fixture',workspace_root=tmp_path,inference_request=wire)


class Grounding:
    def observe(self):return GROUND


def submit(root,runtime,wire,*,binding_wire=None,operation='compare-fixture'):
    body={'operation_key':operation,'objective':'Compare the supplied research evidence.','inference_request':wire}
    return service.handle_frame({'schema':service.SUBMIT_SCHEMA,'request':body,'observed_grounding':GROUND},
        runtime=runtime,grounding_provider=Grounding(),workspace_root=root,
        admission_guard=lambda _:None,
        execution_binding_provider=lambda identity:bind(root,binding_wire,identity=identity))


def test_real_sink_retains_comparison_route_and_declares_no_dispatch(tmp_path):
    runtime=Runtime.at(tmp_path/'runtime');wire=request()
    try:first=asyncio.run(submit(tmp_path,runtime,wire,binding_wire=wire))
    except CeoIngressError as exc:pytest.fail('task-aware service admission is missing: '+exc.code)
    job=runtime.jobs.get_job(first['job_id'])
    assert job.constraints['risk']=='elevated'
    assert job.constraints['preferred_model_aliases']==['standard.research']
    assert not job.allowed_write_paths and not job.validation_commands
    assert not runtime.attempts.list_attempts(job_id=job.job_id)
    stamp=esp.durable_provenance(runtime,job.job_id)['provenance']
    assert stamp['inference_request']==wire


def test_real_sink_refuses_stale_routine_binding_for_comparison(tmp_path):
    runtime=Runtime.at(tmp_path/'runtime')
    with pytest.raises(CeoIngressError):asyncio.run(submit(tmp_path,runtime,request()))
    assert len(runtime.jobs.list_jobs())==0


def test_task_change_under_same_operation_conflicts_without_second_job(tmp_path):
    runtime=Runtime.at(tmp_path/'runtime');first=request('evidence_extraction')
    try:receipt=asyncio.run(submit(tmp_path,runtime,first,binding_wire=first))
    except CeoIngressError as exc:pytest.fail('task-aware service admission is missing: '+exc.code)
    changed=request('comparative_analysis')
    with pytest.raises(CeoIngressError) as error:
        asyncio.run(submit(tmp_path,runtime,changed,binding_wire=changed))
    assert error.value.code=='operation_conflict'
    assert len(runtime.jobs.list_jobs())==1
    assert runtime.jobs.list_jobs()[0].job_id==receipt['job_id']


def test_task_kind_changes_fingerprint_but_not_logical_operation_id():
    from control_plane.executive_inference_contract import derive
    base={'operation_key':'task-identity','objective':'Compare evidence.','inference_request':request('evidence_extraction')}
    try:left=derive(base,GROUND);right=derive(dict(base,inference_request=request()),GROUND)
    except ValueError:pytest.fail('task-aware inference schema is missing')
    assert left['intent_id']==right['intent_id']==intent_id('task-identity')
    assert esp.fingerprint(left)!=esp.fingerprint(right)


def test_advertised_service_schema_accepts_both_versions_but_not_raw_model_selectors():
    from jsonschema import Draft202012Validator
    from integrations.executive_mcp.inference import TOOL_SPECS
    schema=TOOL_SPECS[0].input_schema
    validator=Draft202012Validator(schema)
    def envelope(value):return {'operation_key':'schema-fit','objective':'Research evidence.','inference_request':value}
    assert not list(validator.iter_errors(envelope(legacy())))
    assert not list(validator.iter_errors(envelope(request()))),'advertised tool does not support its v2 task request'
    assert list(validator.iter_errors(envelope(dict(request(),model='untrusted'))))


def test_v2_byte_limit_still_applies_to_the_complete_request():
    valid=request();valid['input_text']='x'*50000
    with pytest.raises(io.InferenceIOError):io.normalize_request(valid)


def test_validator_cannot_accept_comparison_binding_without_corresponding_request(tmp_path):
    try:value=bind(tmp_path,request())
    except TypeError:pytest.fail('task-aware binding support is missing')
    with pytest.raises(execution.InferenceExecutionBindingError):
        execution.validate_execution_binding(value,intent_id='task-fit-fixture',workspace_root=tmp_path)
