"""Consumed actual S19 result -> PLAN owner/Event/Git -> current S5 Compare.

Reuses the accepted actual CREATE fixture. Physical native observations, Root
source seal, credential qualification, principal enrollment and PR API remain
its explicit inert seams. Runtime completion/consumption, nominal DATA/result
owners, compiler/parser, private files, source Events and Git are actual.
The actual production installed factory supplies the proposal owner.
"""
import asyncio
import copy
import dataclasses
import hashlib
import inspect
import fcntl
import json
import os
import time
from pathlib import Path

import pytest

from tests.test_project_journey_canonical_create import joined,owner,env,isolated_git_env,identity
from tests.test_project_planning_factory import invocation
from tests.test_direct_native_supervisor_runtime_join import make_direct_supervisor
from tests.test_workspace_project_git_publisher import git,rev_parse
from control_plane.project_plan_canonical_basis import capture_current_plan_basis
from control_plane.project_plan_result_source import capture_completed_planning_result,PlanResultUnavailable
from control_plane.project_planning_admission import requalify_original
from control_plane.executive_runtime import JobStatus
from control_plane.executive_orchestration_result import canonical_bytes
from integrations.mastermind_workspace_app.project_plan_proposal_service import ProjectPlanProposalSourceOwner
from integrations.mastermind_workspace_app.project_journey_recipes import InstalledProjectPlanProposalRecipeAdapter
from integrations.mastermind_workspace_app.source_operations import WorkspaceSourceOperationService
from integrations.mastermind_workspace_app.source_operation_principal import source_principal_scope
from integrations.mastermind_executive_app.project_plan_preparation import prepare_project_plan_proposal_for_original
from common import project_planning_private_contract as private_wire
from control_plane.foreground_operation import _project_planning_foreground_dispatch,current_foreground_operation


async def proposal_invocation(j,request,call):
    factory,args=j['factory'],j['args']
    principal=dataclasses.asdict(args['principal']);principal['scopes']=list(principal['scopes'])
    workspace=dataclasses.asdict(j['workspace']);workspace['scopes']=list(workspace['scopes'])
    frame=dict(schema=private_wire.SCHEMA,operation='prepare_proposal',principal=principal,
        workspace_principal=workspace,arguments=dict(operation_key=args['operation_key'],
            work_ref=args['work_ref'],proposal_request=request))
    async with _project_planning_foreground_dispatch(j['runtime'],frame,lambda:None):
        value=call(frame,current_foreground_operation())
        return await value if inspect.isawaitable(value) else value


@pytest.fixture
def completed(joined,monkeypatch,request):
    started=time.monotonic()
    def phase(name):print(json.dumps({'s24_phase':name,'elapsed':round(time.monotonic()-started,3)}),flush=True)
    phase('CREATE_SOURCE_OBSERVED')
    j=joined;factory,args=j['factory'],j['args'];runtime=j['runtime']
    mode=getattr(request,'param','plan');args['stage']='clarify' if mode=='clarify' else 'plan'
    if os.environ.get('MM_PROJECT_CONSUMER_FIXTURE_OUTPUT'):
        # NEW fixture input, before any S19 input/Job. Match the incumbent App
        # producer's canonical key material; the consumer must independently
        # verify this with actual planningOperationKey(), never rewrite a DTO.
        from integrations.mastermind_executive_app.principal_namespace import principal_scope_from_identity
        who=args['principal']
        scope=principal_scope_from_identity(issuer_digest=who.issuer_digest,subject_digest=who.subject_digest,
            client_ref=who.client_ref,resource=who.resource)
        material=dict(v=1,principalScope=scope,**{k:args[k] for k in
            ('work_ref','stage','project_source','publication','grounding')},private_request=args['private_request'].decode())
        args['operation_key']='mmos-project-planning-'+hashlib.sha256(canonical_bytes(material)).hexdigest()[:40]
    view=j['data'].view(j['workspace'],work_ref=args['work_ref'])
    with view.capture_scope():basis=capture_current_plan_basis(view,work_ref=args['work_ref']).material()
    declaration=dict(schema='mastermind.project_plan_candidate.v1',work_ref=args['work_ref'],
        base_source=basis['base_source'],base_adoption=basis['base_adoption'],
        plan=dict(objective='An explicit plan from the consumed result.',
            waves=[dict(id='W1',title='Compare the exact proposed source',status='todo')],
            next_action='Review this proposal without adoption.',body='Literal proposed body. 中文\n'),
        rationale='The same original returned result explicitly declares this candidate.',evidence=[])
    output_text='Plain returned research; no declared plan.' if mode=='plain' else json.dumps(declaration)
    old=factory.service.supervisor
    supervisor=make_direct_supervisor(runtime,workspace_root=factory.service.config.proof_workspace_root,
        runs_root=old.runs_root,provider_home=j['tmp_path']/'s24-physical-native-fixture')
    factory.service.supervisor=supervisor
    collect=supervisor.adapter.collect_result
    async def physical_output(ref):
        receipt=await collect(ref);output=dict(receipt.result.structured_output,current_state=output_text)
        raw=canonical_bytes(output);Path(receipt.process_ref.result_path).write_bytes(raw)
        return dataclasses.replace(receipt,result=dataclasses.replace(receipt.result,structured_output=output),
            result_sha256=hashlib.sha256(raw).hexdigest())
    supervisor.adapter.collect_result=physical_output
    async def launch():
        admitted=factory.submit(**args);job=runtime.jobs.get_job(admitted['job_id'])
        source,executive=factory.prepare(**args)
        access=requalify_original(runtime,job_id=job.job_id,source=source,executive_admission=executive)
        bound=executive.binding
        metadata={key:bound[key] for key in ('routing_policy_version','execution_profile_id',
            'execution_profile_digest','capability_policy_version','capability_policy_digest')}
        metadata['adapter_id']='codex-cli'
        runtime.workers.register_worker(bound['worker_id'],provider='codex',account_label='inert-planning',
            worker_type='codex-cli',capabilities=['read','research'],quota_classes={'default':dict(provider='codex',
                model=bound['model'],effort=bound['effort'],cost_class=bound['cost_class'],
                capabilities=['read','research'],metadata=metadata)})
        runtime.jobs.prepare_direct_native_workspace(job.job_id,source_repository=factory.service.config.proof_source_repository,
            shared_gid=os.getegid(),access=access)
        active=await supervisor.start_direct_native_job(job.job_id,access=access)
        terminal=await supervisor.finish_job(active)
        assert terminal.job.status is JobStatus.COMPLETED
        return dict(work_ref=args['work_ref'],job_id=job.job_id,attempt_id=terminal.attempt.attempt_id)
    phase('S19_LAUNCH_BEGIN')
    selected=asyncio.run(invocation(factory,args,launch))
    phase('S19_COMPLETED')
    from control_plane.runtime_namespace_custody import ServiceRuntimeNamespaceCustody
    directory=runtime.store.path.parent;lock=directory/'executive-service.lock'
    fd=os.open(lock,os.O_CREAT|os.O_RDWR,0o600);fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
    marker=directory/'executive-service.running'
    marker.write_text(json.dumps(dict(instance_id='S24-source-fixture',pid=os.getpid())));marker.chmod(0o600)
    keeper=ServiceRuntimeNamespaceCustody(runtime=runtime,service_lock_fd=fd,lock_path=lock,
        marker_path=marker,instance_id='S24-source-fixture')
    keeper.start();factory.service._namespace_custody=keeper
    def result_and_consume(consume=True):
        source,executive=factory.prepare(**args)
        if consume:
            # The explicit parent submits the digest from its earlier actual
            # read. Runtime checks that digest/current access at the mutation.
            access=requalify_original(runtime,job_id=selected['job_id'],source=source,executive_admission=executive)
            runtime.consume_direct_native_result(dict(selected,result_digest=material['result_digest'],
                operation_key='explicit-S24-parent-consume'),access=access)
        evidence=capture_completed_planning_result(runtime,result_reader=keeper.bound_runtime(runtime),selection=selected,
            source=source,executive_admission=executive)
        # capture_completed already finished its full current postcheck;
        # copying its owned DTO does not add another user read operation.
        observed=evidence.material()
        if consume:
            with factory.canonical_read_scope(principal=args['principal'],operation_key=args['operation_key'],
                    work_ref=args['work_ref']):
                evidence.require_consumed()
        return observed
    material=asyncio.run(invocation(factory,args,lambda:result_and_consume(False),operation='result'))
    phase('S19_UNCONSUMED_READ')
    proposal_request=dict(schema='mastermind.project_plan_proposal_request.v1',
        request_id='mmos-project-plan-proposal-'+'8'*40,work_ref=args['work_ref'],
        expected_commit=basis['source']['commit'],expected_adoption=basis['base_adoption'],
        base_source=basis['base_source'],selection=selected,result_digest=material['result_digest'])
    slot=j['document']['profiles'][j['document']['primary_profile']]
    slot['project_plan_proposal_publish']={'work_ref':args['work_ref'],'permission_digest':'c'*64}
    # The actual installed factory now issues the fixed SAME-S19 owner; no
    # fixture provider/qualification callback substitutes for that composition.
    assert factory.app_binding.source_operation_provider_factory is j['installed']
    def prepare(value=None):
        value=proposal_request if value is None else value
        return asyncio.run(proposal_invocation(j,value,lambda frame,operation:
            prepare_project_plan_proposal_for_original(factory,frame,operation,args['principal'])))
    def consume():return asyncio.run(invocation(factory,args,result_and_consume,operation='result'))
    def source_owner():return j['installed'](runtime,supervisor).owner._proposal
    yield locals()
    keeper.close();os.close(fd)
