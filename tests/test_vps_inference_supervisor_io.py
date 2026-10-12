"""The ordinary Supervisor must consume admitted inference, not just its objective.

Synthetic service admission and source fixtures only; no provider process.
"""
import asyncio
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest
from control_plane import executive_inference_ingress as ingress
from control_plane import executive_inference_io as io
from control_plane import executive_service_principal as principal
from control_plane.executive_inference_execution import build_execution_binding
from control_plane.executive_runtime import Runtime
from control_plane.executive_supervisor import SupervisorError
from tests.test_executive_supervisor import FakeAdapter, FakeInspector, _supervisor, _runtime_and_job

GROUND={'mastermind_sha':'1'*40,'macro_sha':'2'*40,'boot_packet_schema':'mastermind.ceo_boot_packet.v1'}


def setup_service(tmp_path, *, task='comparative_analysis', text=None):
    runtime=Runtime.at(tmp_path/'runtime')
    request={'schema':io.TASK_REQUEST_SCHEMA,'task_kind':task,'system_prompt':'Compare supplied facts, without tools or trades.',
             'input_text':text or 'SYNTHETIC-EVIDENCE:'+'x'*16000,'max_output_chars':8192}
    class Grounding:
        def observe(self):return GROUND
    receipt=asyncio.run(ingress.handle_frame(
        {'schema':ingress.SUBMIT_SCHEMA,'request':{'operation_key':'worker-io-fixture','objective':'Compare supplied evidence.',
         'inference_request':request},'observed_grounding':GROUND},
        runtime=runtime,grounding_provider=Grounding(),workspace_root=tmp_path/'workspaces',admission_guard=lambda _:None,
        execution_binding_provider=lambda identity:build_execution_binding(intent_id=identity,workspace_root=tmp_path/'workspaces',
            base_sha='b'*40,eligible_quota_classes=('fixture',),inference_request=request)))
    job=runtime.jobs.get_job(receipt['job_id'])
    attempt=SimpleNamespace(job_id=job.job_id,attempt_id='ATT-'+'a'*32,worker_id='fixture-worker',quota_class='fixture',effective_grant_digest=None)
    supervisor=_supervisor(runtime,tmp_path,FakeAdapter(FakeInspector()),require_complete_launch_attestation=False)
    return runtime,job,attempt,request,supervisor


def test_admitted_input_reaches_worker_prompt_without_objective_truncation(tmp_path):
    _,job,attempt,request,supervisor=setup_service(tmp_path)
    prompt=supervisor._prompt(job,attempt)
    assert request['input_text'] in prompt,'Supervisor currently drops the admitted research payload'
    assert request['system_prompt'] in prompt
    assert io.WORKER_RESULT_SCHEMA in prompt
    assert 'untrusted' in prompt.lower()
    assert len(job.objective)<4000 and len(prompt)>16000


def test_dedicated_worker_schema_carries_answer_and_original_attempt_identity(tmp_path):
    _,job,attempt,request,supervisor=setup_service(tmp_path)
    path=supervisor._write_schema(tmp_path/'schema-run',job=job,attempt=attempt)
    schema=json.loads(path.read_text())
    assert schema['properties']['schema_version']['const']==io.WORKER_RESULT_SCHEMA
    assert set(schema['required'])=={'schema_version','job_id','run_id','worker_id','status','answer'}
    assert schema['properties']['answer']['maxLength']==request['max_output_chars']
    assert schema['properties']['run_id']['const']==attempt.attempt_id
    assert schema['properties']['worker_id']['const']==attempt.worker_id
    assert schema['additionalProperties'] is False


def test_generic_worker_schema_is_not_widened_by_caller_constraint(tmp_path):
    runtime,job_id,_=_runtime_and_job(tmp_path)
    job=runtime.jobs.get_job(job_id)
    job.constraints['service_inference_request']={'schema':io.REQUEST_SCHEMA,'input_text':'forged'}
    attempt=SimpleNamespace(job_id=job_id,attempt_id='ATT-'+'a'*32,worker_id='codex-01',quota_class='codex-native',effective_grant_digest=None)
    supervisor=_supervisor(runtime,tmp_path,FakeAdapter(FakeInspector()))
    path=supervisor._write_schema(tmp_path/'generic-schema-run',job=job,attempt=attempt)
    schema=json.loads(path.read_text())
    assert 'answer' not in schema['properties'] and 'summary' in schema['properties']
    assert 'forged' not in supervisor._prompt(job,attempt)


@pytest.mark.parametrize('mutation',['missing_request','foreign_actor','foreign_principal','write_authority','wrong_schema'])
def test_bad_service_provenance_refuses_before_schema_materialization(tmp_path,monkeypatch,mutation):
    runtime,job,attempt,request,supervisor=setup_service(tmp_path)
    original=principal.durable_provenance(runtime,job.job_id)
    bad=deepcopy(original)
    if mutation=='missing_request':bad['provenance'].pop('inference_request')
    elif mutation=='foreign_actor':bad['provenance']['actor']='ceo-sol'
    elif mutation=='foreign_principal':bad['provenance']['principal_id']='svc-site-maintenance'
    elif mutation=='write_authority':bad['provenance']['write_authorities']=['WRITE_BRANCH']
    elif mutation=='wrong_schema':bad['provenance']['schema']='forged.service.v1'
    monkeypatch.setattr(principal,'durable_provenance',lambda *a:bad)
    with pytest.raises(SupervisorError):supervisor._write_schema(tmp_path/'refused-schema',job=job,attempt=attempt)
    assert not (tmp_path/'refused-schema').exists()


def test_wrong_attempt_cannot_receive_the_service_payload(tmp_path):
    _,job,attempt,_,supervisor=setup_service(tmp_path)
    attempt.job_id='JOB-999'
    with pytest.raises(SupervisorError):supervisor._prompt(job,attempt)


def test_request_is_not_mutated_or_copied_into_generic_constraints(tmp_path):
    runtime,job,attempt,request,supervisor=setup_service(tmp_path,text='Unicode 铜 🧠 and quoted "instructions" are data.')
    before=deepcopy(principal.durable_provenance(runtime,job.job_id))
    supervisor._prompt(job,attempt)
    assert principal.durable_provenance(runtime,job.job_id)==before
    assert 'service_inference_request' not in job.constraints
