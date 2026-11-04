"""Offline normal Runtime integration, never an authenticated host/run claim.

The fixture uses real Runtime admission/events and real temporary Control Git
and files. Remote host observations are explicitly inert DATA; no provider,
SSH, broker lease, enrollment, installed binding or launch is exercised.
"""
import copy
import hashlib
import json
from pathlib import Path
import subprocess

from control_plane.ceo_intent import submit_intent
from control_plane.executive_paid_fabric_composition import PaidWorkPlacement, placement_member
from control_plane.executive_runtime import Runtime, OrchestrationDispatchOutcome
from control_plane.model_router import ModelRouter
from control_plane.executive_orchestration_result import canonical_digest
from control_plane.paid_model_execution_contract import paid_host_reference
from test_executive_os_phase1fc import _v2_intent, _v3_execution_binding, _complete_ohf_role
from test_executive_paid_runtime import _paid_source_document


def paid_cycle_claim(tmp_path):
    workspace = tmp_path/'workspaces'/'control-source'
    workspace.mkdir(parents=True, mode=0o700)
    subprocess.run(['git','init','-q',str(workspace)],check=True)
    content=b'# Offline paid worker integration commission\n\nRead supplied evidence only.\n'
    path=workspace/'research'/'commission.md';path.parent.mkdir();path.write_bytes(content)
    subprocess.run(['git','-C',str(workspace),'add','research/commission.md'],check=True)
    subprocess.run(['git','-C',str(workspace),'-c','user.name=Runtime Unit',
        '-c','user.email=unit@example.invalid','-c','commit.gpgsign=false','commit','-qm','unit source'],check=True)
    head=subprocess.check_output(['git','-C',str(workspace),'rev-parse','HEAD'],text=True).strip()
    runtime=Runtime.at(tmp_path)
    router=ModelRouter.load();review=router.resolve_model_alias('standard.review')
    plan=router.resolve_model_alias('coo.sealed')
    paid=router.resolve_model_alias('glm.paid.sealed-input')
    member=placement_member(router,PaidWorkPlacement(paid.model_alias,'paid-read'))
    def identity(alias):
        return {key:getattr(alias,key) for key in ('execution_profile_id','execution_profile_digest',
            'capability_policy_version','capability_policy_digest')}
    def codex_quota(alias,cost,**metadata):
        return {'provider':'codex','capabilities':['read','research'],'model':alias.model,
            'effort':alias.effort,'cost_class':cost,'metadata':{**identity(alias),
                'adapter_id':'codex-cli','model_alias':alias.model_alias,
                'provider_alias':'codex','routing_policy_version':router.policy_version,**metadata}}
    # All three quotas are views of one physical Worker/account. The readonly
    # member does not mint capacity. Completion must release the prior owner.
    runtime.workers.register_worker('codex-plan',provider='codex',account_label='codex-account',
        worker_type='codex-cli',capabilities=['read','research'],quota_classes={
            'codex-plan-small':codex_quota(plan,'small'),
            'codex-root-default':codex_quota(plan,'default'),
            'codex-read':codex_quota(review,'default',single_worker_capacity=True)})
    source=_paid_source_document()
    source.update(worker_id='paid-subject',model=paid.model,execution_profile_digest=paid.execution_profile_digest)
    from test_executive_paid_runtime import _capacity_join_wire
    join=_capacity_join_wire(canonical_digest(source))
    runtime.workers.register_worker('paid-subject',provider='glm',account_label='glm-account-unit',
        worker_type='canonical-paid-fabric',capabilities=['read','research'],quota_classes={'paid-read':{
            'provider':'glm','capabilities':['read','research'],'model':paid.model,'effort':paid.effort,
            'cost_class':paid.cost_class,'metadata':{**identity(paid),'adapter_id':'canonical-paid-fabric',
                'model_alias':paid.model_alias,'provider_alias':'glm','routing_policy_version':router.policy_version,
                'paid_execution_route':member['paid_execution_route'],'capacity_join':join}}})
    binding=_v3_execution_binding()
    binding.update(**identity(plan),provider='codex',eligible_quota_classes=['codex-plan-small','codex-root-default'],
        model=plan.model,effort=plan.effort,cost_class='default',
        routing_policy_version=router.policy_version,base_sha=head,
        work_placement_union=[{'provider_realm':'codex','quota_class':'codex-plan-small'},member],
        paid_subject_review_binding={'schema_version':'mastermind.paid_subject_review_binding/v1',
            'model_alias':'standard.review','eligible_quota_classes':['codex-read'],'provider':'codex',
            'model':review.model,'effort':review.effort,'cost_class':'default',
            'routing_policy_version':router.policy_version,**identity(review),'authorities':['READ']})
    intent=_v2_intent(intent_id='CEO-PAID-UNIT-1',business_impact='routine',workstream='WS:PAID-UNIT')
    intent['grounding']['mastermind_sha']=head
    intent['execution_contract']['worktree']=str(workspace.resolve())
    receipt=submit_intent(runtime,intent,execution_binding=binding,workspace_root=workspace.parent,
        dialogue_source={'schema_version':'mastermind.executive_dialogue_source/v1','work_ref':'WS:PAID-UNIT',
            'commission_ref':{'repository':'mastermindx-market-intelligence/Mastermind','commit':head,
                'path':'research/commission.md','content_sha256':hashlib.sha256(content).hexdigest()},'watch_mode':None},
        require_dialogue_source=True)
    root=runtime.jobs.get_job(receipt['job_id'])
    planner=runtime.jobs.create_cycle_planner(root.job_id,command_id=f'coo-cycle:{root.job_id}:create-planner:0')
    planning=runtime.attempts.dispatch_cycle_job(planner.job_id,command_id=f'coo-cycle:{root.job_id}:dispatch:{planner.job_id}:attempt:1',
        worker_id='codex-plan',quota_class='codex-plan-small')
    assert isinstance(planning,OrchestrationDispatchOutcome)
    body={'schema_version':'mastermind.execution_plan/v3','root_job_id':root.job_id,
        'plan_attempt_id':planning.attempt.attempt_id,'steps':[{'ordinal':0,'step_id':'paid-step',
            'objective':'Analyze only supplied immutable evidence.','business_impact':'routine','review_required':True,
            'requested_authorities':['READ'],'allowed_write_paths':[],'validation_ids':[],
            'attempt_limit':1,'cost_class':'small','placement':{'provider_realm':'glm','quota_class':'paid-read'},
            'prerequisite_step_ids':[]}]}
    _complete_ohf_role(runtime,planning,body,identity_seed=9901)
    admitted=runtime.jobs.admit_cycle_plan(root.job_id,command_id=f'coo-cycle:{root.job_id}:admit-plan:{planning.attempt.attempt_id}')
    assert len(admitted)==1
    job=admitted[0]
    claimed=runtime.attempts.dispatch_cycle_job(job.job_id,command_id=f'coo-cycle:{root.job_id}:dispatch:{job.job_id}:attempt:1',
        worker_id='paid-subject',quota_class='paid-read')
    assert isinstance(claimed,OrchestrationDispatchOutcome)
    return runtime,root,job,claimed,source,body,planning


def test_paid_claim_uses_existing_root_plan_capacity_and_claim_owners(tmp_path):
    runtime,root,job,claimed,source,body,planner=paid_cycle_claim(tmp_path)
    assert job.root_job_id==root.job_id and job.parent_job_id==root.job_id
    assert job.plan_attempt_id==planner.attempt.attempt_id
    assert job.constraints['execution_profile_id']=='fabric.paid.glm.sealed-input.v1'
    assert claimed.attempt.worker_id=='paid-subject'
    events=runtime.events.list_events(attempt_id=claimed.attempt.attempt_id)
    claims=[e for e in events if e.event_type=='JOB_CLAIMED']
    assert len(claims)==1
    frozen=claims[0].payload['paid_capacity_binding']
    assert frozen['capacity_join']['worker_source_config_digest']==canonical_digest(source)
    assert frozen['account_label']=='glm-account-unit'
    assert frozen['execution_profile_digest']==job.constraints['execution_profile_digest']


def paid_running(tmp_path):
    """Real Runtime/Control composition of explicitly inert owner observations."""
    from types import SimpleNamespace
    from control_plane.executive_paid_fabric_adapter import CanonicalPaidFabricWorkerAdapter
    from control_plane.executive_supervisor import ExecutiveSupervisor, CleanupPolicy, _write_private_recovery_prompt
    from control_plane.executive_worker_broker import _launch_spec_to_json
    from control_plane.executive_runtime import AttemptLease
    from control_plane.worker_execution_contract import PaidModelProcessRef
    from control_plane import paid_model_execution_contract as contract, paid_fabric_wire as wire
    from control_plane.executive_paid_runtime import paid_physical_binding_from_worker_source
    runtime,root,job,claimed,source,body,planner=paid_cycle_claim(tmp_path)
    lease=AttemptLease(attempt=claimed.attempt,lease_token=claimed.lease_token)
    adapter=object.__new__(CanonicalPaidFabricWorkerAdapter)
    adapter.runtime=runtime;adapter.inspector=object()
    runs=tmp_path/'runs';runs.mkdir(mode=0o700)
    supervisor=ExecutiveSupervisor(runtime,adapter,runs_root=runs,
        isolation_roots=(Path(job.worktree).parent,runs),worker_user=source['worker_user'],
        worker_uid=source['worker_uid'],worker_gid=source['worker_gid'],
        cleanup_policy=CleanupPolicy.FABRIC_PROCESS_GROUP,require_complete_launch_attestation=True)
    grant=supervisor._effective_grant(job,lease.attempt)
    supervisor._validate_execution_profile(job,lease,grant)
    schema=supervisor._write_schema(supervisor._run_dir(lease.attempt.attempt_id),job=job,
        attempt=lease.attempt,effective_grant=grant)
    commission=supervisor.verified_commission(job,Path(job.worktree))
    packet=supervisor.materialize_commission(commission,input_dir=schema.parent)
    spec=supervisor._launch_spec(job,lease,schema,grant,packet,commission.content.decode('utf-8'))
    prompt=schema.parent/'worker-prompt.txt';_write_private_recovery_prompt(prompt,spec.prompt)
    context={'input_root':str(schema.parent.resolve()),'source_workspace':str(Path(job.worktree).resolve())}
    physical=paid_physical_binding_from_worker_source(source,worker_source_config_digest=canonical_digest(source))
    payload={'binding':{'root_id':root.job_id,'job_id':job.job_id,'attempt_id':lease.attempt.attempt_id,
        'effective_grant_digest':lease.attempt.effective_grant_digest,
        'commission_sha256':hashlib.sha256(commission.content).hexdigest()},
        'physical_binding_sha256':canonical_digest(physical),'launch_spec':_launch_spec_to_json(spec),
        'validation_commands':[],'paid_route':{'provider':'glm','host_ref':source['host_ref'],
            'model':source['model'],'parent_job_id':root.job_id},
        'paid_input':{'prompt':spec.prompt,'result_schema':json.loads(schema.read_text())},
        'paid_physical_binding':physical,'paid_source_config':source,'paid_account':'glm-account-unit',
        'paid_quota_class':'paid-read','control_recovery':context}
    identity={'physical_binding_sha256':canonical_digest(physical),'request':payload}
    pinned=runtime.attempts.pin_remote_launch_identity(lease.attempt.attempt_id,
        fence_generation=lease.attempt.fence_generation,lease_token=lease.lease_token,
        expected_version=lease.attempt.version,identity_digest=canonical_digest(identity))
    runtime.attempts.validate_pinned_remote_launch(pinned,lease_token=lease.lease_token)
    binary=source['binary'];pid=4444
    image={key:binary[key] for key in ('sha256','device','inode','mode','uid','gid','size','mtime_ns')}
    image.update(start_identity='unit-process-generation',boot_id=source['qualification']['boot_id'],
        pgid=pid,session_id=pid,parent_pid=1111,ctime_ns=binary['mtime_ns'],
        effective_uid=source['worker_uid'],real_uid=source['worker_uid'],
        effective_gid=source['worker_gid'],real_gid=source['worker_gid'])
    capture=Path(source['capture_root'])/(pinned.attempt_id+'.paid')
    capsule={'offline_fixture_data':'never a broker lease or admission'}
    frame={'schema':'mastermind.paid_model_owned_launch/v1','run_id':pinned.attempt_id,
        'model':source['model'],'transport_host':source['qualification']['registry_key'],
        'lease_id':'unit-data-lease','pid':pid,'process_identity':image,
        'observed_user':source['worker_user'],'launch_nonce':'unit-launch-generation',
        'started_at':'2026-10-22T20:00:00+00:00','python_path':binary['path'],
        'python_version':binary['version'],'source_manifest_sha256':'7'*64,
        'request_body_sha256':contract.descriptor(payload)['request_body_sha256'],
        'capsule_binding_sha256':contract.digest(capsule),
        'capture_contract':{'schema':'mastermind.paid_model_capture/v1','capture_limit_bytes':262144,
            'stdout_encoding':'utf-8','stderr_encoding':'utf-8','require_complete':True,'require_cleanup':True},
        'capture_paths':{'stdout_path':str(capture/'stdout'),'stderr_path':str(capture/'stderr'),
            'result_path':str(capture/'result.json')},
        'host_context':{key:source['qualification'][key] for key in
            ('host_env_path','host_env_sha256','boot_id','capture_identity')}}
    # Pure projection DATA only. No authority object, endpoint or provider is created.
    projection=SimpleNamespace(fence_generation=pinned.fence_generation,pin_version=pinned.version,
        pin_identity_sha256=canonical_digest(identity))
    raw_lease={'id':'unit-data-lease','orchestrator_id':root.job_id,'pool':'glm','account':'glm-account-unit',
        'host':source['qualification']['registry_key'],'model':source['model'],'pid':2222}
    start=wire.paid_start_from_owned_launch(payload,frame,capsule=capsule,lease=raw_lease,
        controller={'process_start_identity':'unit-controller','boot_id':'unit-Control-boot'},authority=projection)
    ref,att=wire.validate_paid_start_wire(start,payload)
    # These inert receipt DATA accessors do not implement or simulate transport.
    adapter.launch_attestation=lambda _ref:copy.deepcopy(att)
    adapter.paid_launch_identity=lambda _ref:copy.deepcopy(identity)
    adapter.control_recovery_context=lambda _spec:dict(context)
    metadata=supervisor._launch_metadata(job=job,lease=lease,spec=spec,process_ref=ref,
        effective_grant=grant,recovery_prompt_path=prompt)
    runtime.attempts.record_process(pinned.attempt_id,fence_generation=pinned.fence_generation,
        lease_token=lease.lease_token,pid=ref.pid,pgid=ref.pgid,process_start_identity=ref.process_start_identity,
        boot_id=ref.boot_session_id,provider_session_id=None,stdout_path=ref.stdout_path,
        stderr_path=ref.stderr_path,result_path=ref.result_path,launch_metadata=metadata)
    running=runtime.attempts.mark_running(pinned.attempt_id,fence_generation=pinned.fence_generation,
        lease_token=lease.lease_token,required_launch_attestation_schema=contract.ATTESTATION_SCHEMA)
    return dict(runtime=runtime,root=root,job=job,lease=lease,running=running,source=source,
        supervisor=supervisor,adapter=adapter,spec=spec,ref=ref,att=att,payload=payload,identity=identity,
        frame=frame,start=start,grant=grant,plan_body=body,planner=planner)


def test_paid_running_seals_actual_contract_principal_from_original_owner_chain(tmp_path):
    state=paid_running(tmp_path)
    attempt=state['runtime'].attempts.get_attempt(state['running'].attempt_id)
    assert attempt.execution_principal_snapshot['schema_version']=='mastermind.paid_model_execution_principal/v1'
    assert attempt.execution_principal_snapshot['worker_id']=='paid-subject'
    assert attempt.execution_principal_snapshot['account_label']=='glm-account-unit'
    assert 'provider_home_identity' not in attempt.execution_principal_snapshot


def paid_completed(tmp_path):
    import asyncio
    from control_plane.executive_runtime import AttemptLease
    from control_plane.executive_supervisor import ActiveRun
    from control_plane.executive_orchestration_result import RESULT_SCHEMA, canonical_bytes
    from control_plane import paid_fabric_wire as wire
    state=paid_running(tmp_path)
    runtime,job,attempt=state['runtime'],state['job'],state['running']
    envelope={'schema_version':RESULT_SCHEMA,'job_id':job.job_id,'run_id':attempt.attempt_id,
        'worker_id':attempt.worker_id,'role':'work','status':'COMPLETED',
        'role_result':{'schema_version':'mastermind.work_result/v1','root_job_id':job.root_job_id,
            'plan_attempt_id':job.plan_attempt_id,'plan_digest':job.plan_digest,
            'plan_step_id':job.plan_step_id,'repair_round':0,'artifacts':[],'evidence_digests':[]},
        'summary':'Offline retained result: supplied evidence analysis only.',
        'current_state':'complete','next_actions':[],'errors':[],'validations':[]}
    raw=canonical_bytes(envelope);empty=hashlib.sha256(b'').hexdigest()
    cleanup={'census_proven':True,'identity_verified':True,'residual_count':0,
        'status':'terminated','session_id':state['ref'].session_id,
        'stdout_capture_complete':True,'stderr_capture_complete':True,'stdin_delivery_complete':True}
    terminal={'schema':'mastermind.local_owned_process_receipt.v1','label':attempt.attempt_id,
        'pid':state['ref'].pid,'pgid':state['ref'].pgid,'started_at':state['ref'].started_at,
        'ended_at':'2026-10-22T20:00:10+00:00','returncode':0,'timed_out':False,
        'nice_requested':None,'nice_applied':0,'stdout_bytes':len(raw),
        'stdout_sha256':hashlib.sha256(raw).hexdigest(),'stderr_bytes':0,'stderr_sha256':empty,
        'stdout_truncated':False,'stderr_truncated':False,'runtime_failure_code':None,'cleanup':cleanup}
    frame={'schema':'mastermind.paid_model_owned_terminal/v1','run_id':attempt.attempt_id,
        'launch_sha256':hashlib.sha256(json.dumps(state['frame'],sort_keys=True,separators=(',',':'),
            ensure_ascii=True,allow_nan=False).encode('ascii')).hexdigest(),'terminal':terminal}
    wire.validate_owned_terminal(frame,state['frame'])
    value=wire.paid_collection_from_owned_terminal(state['payload'],state['start'],frame,raw)
    capture={'schema_version':'mastermind.paid_model_capture_evidence/v1','stdout_utf8':raw.decode(),
        'stdout_sha256':terminal['stdout_sha256'],'stdout_bytes':len(raw),'stderr_sha256':empty,'stderr_bytes':0}
    observation={'owned_launch':state['frame'],'owned_terminal':frame,'capture':capture}
    adapter=state['adapter'];adapter._paid_observations={}
    async def retained_data_only(_ref,_operation):
        assert _operation=='collect'
        return {'collection':copy.deepcopy(value),'paid_observation':copy.deepcopy(observation)}
    # The real adapter decoder is exercised against inert retained DATA. This
    # supplies no socket/SSH transport and never stands in for live admission.
    adapter._paid_request=retained_data_only
    adapter._known=lambda _ref:(None,copy.deepcopy(state['payload']))
    collection=asyncio.run(adapter.collect_result(state['ref']))
    active=ActiveRun(AttemptLease(attempt=attempt,lease_token=state['lease'].lease_token),
        state['ref'],state['spec'],state['grant'])
    supervisor=state['supervisor'];path=supervisor._persist_collection(active,collection)
    completed,validations,validation_path,assignment=asyncio.run(supervisor._terminalize(active,collection,path))
    assert completed.status.value=='COMPLETED' and validations==()
    state.update(completed=completed,envelope=envelope,collection=collection,
        collection_path=path,assignment_path=assignment,validation_path=validation_path)
    return state


def test_paid_retained_result_is_read_by_actual_runtime_owner(tmp_path):
    state=paid_completed(tmp_path)
    result=state['runtime'].validated_role_completion(state['job'].job_id,
        expected_attempt_id=state['running'].attempt_id)
    assert result.result_envelope==state['envelope']


def test_paid_original_pin_survives_real_lease_adoption_and_rejects_chain_drift(tmp_path):
    import pytest
    from control_plane.executive_paid_runtime import validated_paid_launch_material
    from control_plane.executive_runtime import StateConflict
    state=paid_running(tmp_path)
    runtime,attempt=state['runtime'],state['running']
    adopted=runtime.attempts.adopt_attempt(attempt.attempt_id,
        expected_fence_generation=attempt.fence_generation,lease_owner='offline-successor')
    assert adopted.attempt.fence_generation==attempt.fence_generation+1
    with runtime.store.read() as connection:
        row=connection.execute('SELECT * FROM attempts WHERE attempt_id=?',(attempt.attempt_id,)).fetchone()
        material=validated_paid_launch_material(connection,row)
        assert material
    events=runtime.events.list_events(attempt_id=attempt.attempt_id)
    assert len([e for e in events if e.event_type=='ATTEMPT_REMOTE_LAUNCH_PINNED'])==1
    adoption=[e for e in events if e.event_type=='ATTEMPT_ADOPTED']
    assert len(adoption)==1
    # Existing immutability prevents rewriting the original adoption evidence.
    with pytest.raises(StateConflict,match='events are immutable'):
        with runtime.store.transaction() as connection:
            connection.execute("DELETE FROM events WHERE event_id=?",(adoption[0].event_id,))
    with runtime.store.read() as connection:
        row=connection.execute('SELECT * FROM attempts WHERE attempt_id=?',(attempt.attempt_id,)).fetchone()
        # No matching adoption event exists for a caller-supplied future fence.
        changed=dict(row);changed['fence_generation']+=1
        with pytest.raises(StateConflict):validated_paid_launch_material(connection,changed)


def test_paid_recovery_revalidates_control_prompt_before_async_owner_adoption(tmp_path):
    from control_plane.executive_supervisor import ProcessPresence,ReconcileStatus
    state=paid_running(tmp_path)
    supervisor,adapter=state['supervisor'],state['adapter']
    checks=[]
    # Component seams assert ordering only; these inert callbacks confer no
    # remote authentication or installed-source qualification.
    def coordinates(spec,binding):
        assert spec==state['spec'] and binding.process_ref==state['ref']
        checks.append('coordinates')
    adapter.validate_remote_recovery_coordinates=coordinates
    async def same_owner_status(spec,binding,*,lease):
        assert lease.attempt.fence_generation==state['running'].fence_generation+1
        assert state['runtime'].attempts.get_attempt(lease.attempt.attempt_id)==lease.attempt
        assert binding.process_ref==state['ref'] and spec==state['spec']
        checks.append('awaited-original-status')
        return state['ref']
    adapter.reattach=same_owner_status
    receipt=supervisor._recover_existing_attempt(state['running'],presence=ProcessPresence.LIVE)
    assert receipt.status is ReconcileStatus.LIVE_RECOVERED,receipt.error
    assert checks==['coordinates','awaited-original-status']
    adopted=supervisor._recovered_runs[state['running'].attempt_id]
    assert adopted.process_ref==state['ref']
    assert adopted.launch_spec.run_dir==state['spec'].run_dir
    assert len([e for e in state['runtime'].events.list_events(attempt_id=state['running'].attempt_id)
        if e.event_type=='ATTEMPT_REMOTE_LAUNCH_PINNED'])==1


def test_paid_recovery_changed_private_prompt_refuses_before_owner_status(tmp_path):
    from control_plane.executive_supervisor import ProcessPresence,ReconcileStatus
    state=paid_running(tmp_path)
    adapter=state['adapter'];calls=[]
    adapter.validate_remote_recovery_coordinates=lambda *_:calls.append('coordinates')
    async def forbidden(*_args,**_kwargs):
        calls.append('status');raise AssertionError('changed prompt must stop before owner status')
    adapter.reattach=forbidden
    path=Path(state['running'].launch_metadata['paid_recovery_binding']['launch_spec']['prompt_path'])
    path.write_text('changed supplied input',encoding='utf-8')
    receipt=state['supervisor']._recover_existing_attempt(state['running'],presence=ProcessPresence.LIVE)
    assert receipt.status is ReconcileStatus.LIVE_QUARANTINED
    assert calls==[]
    assert state['runtime'].attempts.get_attempt(state['running'].attempt_id).fence_generation==state['running'].fence_generation


def test_paid_subject_real_codex_review_prompt_and_serial_worker_schedule(tmp_path):
    import asyncio,dataclasses,os,pwd
    from control_plane.executive_coo_cycle import CooCycle
    from control_plane.executive_supervisor import ExecutiveSupervisor
    from control_plane.executive_orchestration_result import canonical_bytes
    from control_plane.reviewed_role_input import reviewed_role_input,reviewed_role_prompt_suffix
    from test_executive_terminal_return import _PlannerSealedWorkerAdapter,_SEALED_WORKER_SECRET_CANARY
    from test_executive_supervisor import FakeInspector,FakeProcessController
    state=paid_completed(tmp_path)
    runtime,root,subject=state['runtime'],state['root'],state['completed']
    # The original planner is terminal; none of its same-Worker quotas remain
    # held. This is the legal release before readonly review, not an extra slot.
    assert runtime.workers.get_quota_class('codex-plan','codex-plan-small').active_attempt_id is None
    assert runtime.workers.get_quota_class('codex-plan','codex-read').active_attempt_id is None
    cycle=CooCycle(runtime)
    created=cycle.run_once(root.job_id)
    assert created.action=='REVIEW_CREATED',created
    review=runtime.jobs.get_job(created.selected_job_id)
    assert review.constraints['cost_class']=='default'
    assert subject.constraints['cost_class']=='small'
    assert root.constraints['cost_class']=='default'
    assert review.requested_authorities==['READ'] and review.validation_commands==[]
    assert review.constraints['preferred_model_aliases']==['standard.review']
    target=runtime.validated_role_completion(subject.job_id,expected_attempt_id=state['running'].attempt_id)
    body={'schema_version':'mastermind.review_result/v1','root_job_id':root.job_id,
        'plan_attempt_id':subject.plan_attempt_id,'plan_digest':subject.plan_digest,
        'plan_step_id':subject.plan_step_id,'reviewed_job_id':subject.job_id,
        'reviewed_attempt_id':target.attempt.attempt_id,'reviewed_result_digest':target.role_result_digest,
        'repair_round':0,'verdict':'approve','evidence_digests':[],'findings':[]}
    class ReadonlyReviewAdapter(_PlannerSealedWorkerAdapter):
        async def collect_result(self,ref):
            receipt=await super().collect_result(ref)
            envelope=dict(receipt.result.structured_output,role='review',role_result=copy.deepcopy(body))
            raw=canonical_bytes(envelope);Path(ref.result_path).write_bytes(raw)
            return dataclasses.replace(receipt,result=dataclasses.replace(receipt.result,
                structured_output=envelope),result_sha256=hashlib.sha256(raw).hexdigest())
    uid,gid=os.geteuid(),os.getegid()
    home=tmp_path/'review-codex-home';home.mkdir(mode=0o700)
    # Match the fixture's worker group even when temporary directories inherit another group.
    os.chown(home,-1,gid)
    adapter=ReadonlyReviewAdapter(FakeInspector(),root_job_id=root.job_id,provider_home=home)
    runs=tmp_path/'codex-runs'
    supervisor=ExecutiveSupervisor(runtime,adapter,runs_root=runs,
        isolation_roots=(Path(root.worktree).parent,runs),worker_user=pwd.getpwuid(uid).pw_name,
        worker_uid=uid,worker_gid=gid,inspector=adapter.inspector,
        process_controller=FakeProcessController(adapter.inspector),
        secret_canary_verdict=_SEALED_WORKER_SECRET_CANARY,require_complete_launch_attestation=True)
    active=asyncio.run(supervisor.start_cycle_job(review.job_id,
        command_id=f'coo-cycle:{root.job_id}:dispatch:{review.job_id}:attempt:1'))
    assert active.lease.attempt.worker_id=='codex-plan'
    assert active.lease.attempt.quota_class=='codex-read'
    actual=runtime.jobs.get_job(review.job_id)
    current_review_attempt=runtime.attempts.get_attempt(active.lease.attempt.attempt_id)
    projection=reviewed_role_input(runtime,job=actual,attempt=current_review_attempt)
    assert projection['reviewed_result_envelope']==state['envelope']
    assert projection['reviewed_result_envelope_digest']==target.result_digest
    assert projection['reviewed_role_result_digest']==target.role_result_digest
    suffix=reviewed_role_prompt_suffix(runtime,job=actual,attempt=current_review_attempt)
    assert suffix and suffix in adapter.spec.prompt
    assert 'Offline retained result: supplied evidence analysis only.' in adapter.spec.prompt
    # The held readonly member blocks the same physical Worker's other quotas.
    assert runtime.workers.get_quota_class('codex-plan','codex-read').active_attempt_id==active.lease.attempt.attempt_id
    receipt=asyncio.run(supervisor.finish_job(active))
    assert receipt.job.status.value=='COMPLETED'
    with runtime.store.read() as connection:
        from control_plane.executive_runtime import _review_attempt_is_independent
        assert _review_attempt_is_independent(connection,review_attempt_id=receipt.attempt.attempt_id,
            reviewed_attempt_id=state['running'].attempt_id)
    assert runtime.workers.get_quota_class('codex-plan','codex-read').active_attempt_id is None
    handoff=cycle.run_once(root.job_id)
    assert handoff.action=='HANDOFF_CREATED',handoff
    def dispatch_root(job_id,command_id):
        assert job_id==root.job_id
        return runtime.attempts.dispatch_cycle_job(job_id,command_id=command_id,
            worker_id='codex-plan',quota_class='codex-root-default')
    aggregate=CooCycle(runtime,dispatcher=dispatch_root).run_once(root.job_id)
    assert aggregate.action=='DISPATCHED',aggregate
    aggregate_attempt=runtime.attempts.get_attempt(runtime.jobs.get_job(root.job_id).current_attempt_id)
    assert aggregate_attempt.worker_id=='codex-plan' and aggregate_attempt.quota_class=='codex-root-default'


def test_cycle_waits_on_same_paid_attempt_before_parent_or_review_admission(tmp_path):
    from control_plane.executive_coo_cycle import CooCycle
    state=paid_running(tmp_path)
    runtime,root,job=state['runtime'],state['root'],state['job']
    def existing_dispatch(job_id,command_id):
        assert job_id==job.job_id
        return runtime.attempts.dispatch_cycle_job(job_id,command_id=command_id,
            worker_id='paid-subject',quota_class='paid-read')
    outcome=CooCycle(runtime,dispatcher=existing_dispatch).run_once(root.job_id)
    assert outcome.action=='DISPATCHED' and outcome.selected_job_id==job.job_id
    assert runtime.jobs.get_job(job.job_id).current_attempt_id==state['running'].attempt_id
    assert runtime.jobs.get_job(root.job_id).current_attempt_id is None
    assert not [j for j in runtime.jobs.list_jobs() if j.orchestration_role=='review']
    assert runtime.workers.get_quota_class('codex-plan','codex-read').active_attempt_id is None
    assert len([e for e in runtime.events.list_events(attempt_id=state['running'].attempt_id)
        if e.event_type=='ATTEMPT_REMOTE_LAUNCH_PINNED'])==1
