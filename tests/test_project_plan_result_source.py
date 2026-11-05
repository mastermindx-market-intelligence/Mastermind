"""S24 against actual S19 signed-owner lifetime + Runtime/Supervisor terminal.

Physical adapter observations are simulated as in S19. No live worker/provider,
receipt validator or Runtime completion predicate is replaced.
"""
import asyncio
import dataclasses
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import pytest

# Run with the exact retained S19 source closure as import root. The adapter
# under test is this slice's own actual source, not a test-shaped replacement.
spec=importlib.util.spec_from_file_location('planning_proposal_result_source_under_test',Path(__file__).resolve().parents[1]/'control_plane/project_plan_result_source.py')
import sys
module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
from tests.test_project_planning_factory import fixture,invocation
from tests.test_direct_native_supervisor_runtime_join import make_direct_supervisor
from tests.test_fabric_result_projection import _bound_reader,_release
from control_plane.project_planning_admission import requalify_original
from control_plane.executive_orchestration_result import canonical_bytes
from control_plane.executive_runtime import JobStatus


def test_actual_s19_terminal_binds_exact_declared_data_and_rechecks_original(tmp_path,monkeypatch):
 factory,args,_,_=fixture(tmp_path,monkeypatch);args['stage']='plan'
 runtime=factory.service.runtime;old=factory.service.supervisor
 supervisor=make_direct_supervisor(runtime,workspace_root=factory.service.config.proof_workspace_root,runs_root=old.runs_root,provider_home=tmp_path/'provider-home')
 factory.service.supervisor=supervisor
 declaration='{"schema":"mastermind.project_plan_candidate.v1","declared":"data only"}'
 collect=supervisor.adapter.collect_result
 async def simulated_output(ref):
  receipt=await collect(ref); output=dict(receipt.result.structured_output,current_state=declaration)
  Path(receipt.process_ref.result_path).write_bytes(canonical_bytes(output))
  return dataclasses.replace(receipt,result=dataclasses.replace(receipt.result,structured_output=output),result_sha256=hashlib.sha256(canonical_bytes(output)).hexdigest())
 supervisor.adapter.collect_result=simulated_output  # Physical source fixture only.
 async def launch():
  admitted=factory.submit(**args);job=runtime.jobs.get_job(admitted['job_id']);source,executive=factory.prepare(**args)
  access=requalify_original(runtime,job_id=job.job_id,source=source,executive_admission=executive);binding=executive.binding
  metadata={key:binding[key] for key in ('routing_policy_version','execution_profile_id','execution_profile_digest','capability_policy_version','capability_policy_digest')};metadata['adapter_id']='codex-cli'
  runtime.workers.register_worker(binding['worker_id'],provider='codex',account_label='inert-planning',worker_type='codex-cli',capabilities=['read','research'],quota_classes={'default':dict(provider='codex',model=binding['model'],effort=binding['effort'],cost_class=binding['cost_class'],capabilities=['read','research'],metadata=metadata)})
  runtime.jobs.prepare_direct_native_workspace(job.job_id,source_repository=factory.service.config.proof_source_repository,shared_gid=os.getegid(),access=access)
  active=await supervisor.start_direct_native_job(job.job_id,access=access);terminal=await supervisor.finish_job(active)
  assert terminal.job.status is JobStatus.COMPLETED
  return dict(work_ref=args['work_ref'],job_id=job.job_id,attempt_id=terminal.attempt.attempt_id)
 selection=asyncio.run(invocation(factory,args,launch))
 frozen=[]
 async def inspect_result():
  source,executive=factory.prepare(**args);keeper,_,binding,reader=_bound_reader(runtime)
  try:
   evidence=module.capture_completed_planning_result(runtime,result_reader=reader,selection=selection,source=source,executive_admission=executive)
   data=evidence.check();assert data['stage']=='plan' and data['payload']['current_state']==declaration
   with pytest.raises(module.PlanResultUnavailable,match='ORIGINAL_RESULT_NOT_CONSUMED'):evidence.require_consumed()
   access=requalify_original(runtime,job_id=selection['job_id'],source=source,executive_admission=executive)
   acknowledged=runtime.consume_direct_native_result(dict(selection,result_digest=data['result_digest'],operation_key='explicit-parent-consume'),access=access)
   assert acknowledged['state']=='CONSUMED' and evidence.require_consumed()==acknowledged
   assert data['selection']==selection and len(data['result_digest'])==64
   detached=evidence.material();detached['payload']['current_state']='tampered';assert evidence.material()==data
   assert declaration not in repr(evidence)
   for bad in ({**selection,'attempt_id':'foreign-attempt'},{**selection,'job_id':'foreign-job'},{**selection,'work_ref':'WS:FOREIGN'}):
    with pytest.raises(ValueError):module.capture_completed_planning_result(runtime,result_reader=reader,selection=bad,source=source,executive_admission=executive)
   with pytest.raises(ValueError):module.capture_completed_planning_result(runtime,result_reader=reader,selection=selection,source=source.material(),executive_admission=executive)
   frozen.append(evidence)
  finally:_release(keeper,binding)
 asyncio.run(invocation(factory,args,inspect_result,operation='result'))
 # Request-local authority dies with the actual ForegroundOperation.
 with pytest.raises(ValueError):frozen[0].check()
 assert len(runtime.jobs.list_jobs())==1 and len(runtime.attempts.list_attempts())==1
