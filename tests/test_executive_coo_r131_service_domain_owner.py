"""Actual Service initial custody; public Runtime work/review and hermetic RPC."""
import asyncio
import dataclasses
import json
from types import SimpleNamespace

import pytest

from control_plane.executive_operator_supervisor import ExecutiveOperatorSupervisor, ExecutiveOperatorSupervisorError
from control_plane.executive_runtime import AttemptLease, AttemptStatus, JobStatus, StateConflict
from control_plane.executive_service import ExecutiveControlService
from control_plane.operator_harness_contract import EventCursor, HarnessAdapterCapabilities, ProcessGenerationRef, TurnRef, TurnStartObservation
from control_plane.operator_harness_orchestrator import OperatorEffectUnknown
from control_plane.operator_harness_wire import to_wire
from control_plane.remote_operator_harness_adapter import RemoteOperatorHarnessAdapter, _REQUIRED_REMOTE_OPERATIONS
from tests.test_executive_coo_r130_service_domain_host import _host, _root
from tests.test_executive_coo_r119_later_turn import _inventory
from tests.test_executive_coo_r124_domain_turn import _wrap_start_attempt_to_capture_receipt
from tests.test_executive_coo_r125_domain_seal import ObservedConsumptionAdapter
from tests.test_executive_operator_supervisor import _DomainAdapter, _PromptSource
from tests.test_executive_coo_hierarchy import (
    _r7a_domain_envelope_review_required, _r7a_complete_work, _r7a_complete_review,
    _r7a_plan_digest_for_domain,
)


def _context(tmp_path, monkeypatch, *, proof_before_domain=False):
    service, rt, _ = _host(tmp_path, monkeypatch)
    service._register_worker()
    proof=asyncio.run(service._create_proof_job()) if proof_before_domain else None
    root, domain = _root(service, rt, name='r131')
    receipts, captured_adapters = _wrap_start_attempt_to_capture_receipt(monkeypatch)
    calls, rpc, initial_adapters = [], [], []
    later = {"proof":proof}

    class Initial(_DomainAdapter):
        def _canonical_result(self, turn):
            attempt = rt.attempts.get_attempt(turn.attempt_id)
            return _r7a_domain_envelope_review_required(rt.jobs.get_job(attempt.job_id), attempt)

    class Client:
        def request_sync(self, operation, payload, **kwargs):
            rpc.append((operation, payload))
            transport, session = later['transport'], later['session']
            if operation == 'ohf-begin-turn':
                return {'observation':to_wire(transport.begin_turn(operation_id=payload['operation_id'],
                    turn=TurnRef(**payload['turn']), generation=ProcessGenerationRef(**payload['generation']),
                    launch=session.launch))}
            if operation == 'ohf-collect-turn':
                turn=TurnRef(**payload['turn'])
                events,cursor=transport.read_events(EventCursor(**payload['cursor']))
                return dict(events=to_wire(events),cursor=to_wire(cursor),
                    candidate=to_wire(transport.collect_candidate_result(turn)),
                    raw_role_result=to_wire(transport.observe_raw_role_result(turn)))
            raise AssertionError('forbidden RPC '+operation)

    capabilities=HarnessAdapterCapabilities(interface_version='mastermind.operator_harness/v1',
        supported_required_operations=_REQUIRED_REMOTE_OPERATIONS,supported_optional_operations=(),
        supports_native_resume=False,supports_native_fork=False,supports_steering=False,
        supports_approval_response=False,supports_checkpoint=False,supports_config_staging=False,
        supports_subagent_capability_ceiling=False,supports_structured_events=True)

    def factory(attempt, requested, loader, *, recovery):
        calls.append((attempt.attempt_id,recovery))
        if not recovery:
            adapter=Initial(rt,loader);initial_adapters.append(adapter);return adapter
        session=receipts[attempt.attempt_id]
        adapter=RemoteOperatorHarnessAdapter(Client(),turn_input_loader=loader,capabilities=capabilities)
        # Only actual initial G1 data captured in this same Supervisor's factory.
        adapter._start_receipts[session.generation.process_generation_id]={'attestation':session.observed}
        return adapter

    sup=ExecutiveOperatorSupervisor(rt,claimed_adapter_factory=factory,prompt_source=_PromptSource(),
        instance_id='r131-source-service-owner')
    service.operator_supervisor=sup
    service.supervisor=SimpleNamespace(reconcile_restart=lambda **kwargs:pytest.fail('healthy owner recovery'))
    service._service_state='READY'
    command=f'coo-cycle:{root.job_id}:dispatch:{domain.job_id}:attempt:1'
    outcome=asyncio.run(service._dispatch_cycle_job_exact(domain.job_id,command))
    assert outcome.outcome=='ACTIVE' and outcome.attempt.status is AttemptStatus.CHECKPOINTED
    session=receipts[outcome.attempt.attempt_id]
    later['session']=session
    return service,rt,root,rt.jobs.get_job(domain.job_id),outcome,session,calls,rpc,initial_adapters,later,command


def _settle(ctx):
    service,rt,root,domain,outcome,session,calls,rpc,initial,later,command=ctx
    quota=rt.workers.get_quota_class(service.config.worker_id,service.config.coo_quota_class)
    for name in ('work','review'):
        rt.workers.register_worker('r131-'+name,provider=quota.provider,
            account_label='independent-r131-'+name,worker_type='fixture',capabilities=[],
            quota_classes={service.config.coo_quota_class:dict(provider=quota.provider,model=quota.model,
                effort=quota.effort,cost_class=quota.cost_class,capabilities=list(quota.capabilities),
                metadata=dict(quota.metadata))})
    attempt=outcome.attempt.attempt_id
    work=rt.jobs.admit_cycle_plan(root.job_id,command_id=f'coo-cycle:{root.job_id}:admit-plan:{attempt}')[0]
    digest=_r7a_plan_digest_for_domain(rt,root.job_id,attempt)
    wd=rt.attempts.dispatch_cycle_job(work.job_id,
        command_id=f'coo-cycle:{root.job_id}:dispatch:{work.job_id}:attempt:1',worker_id='r131-work',
        quota_class=service.config.coo_quota_class)
    assert wd is not None
    sealed=_r7a_complete_work(rt,wd,plan_attempt_id=attempt,plan_digest=digest,identity_seed=19311)
    review=rt.jobs.create_cycle_review(root.job_id,work.job_id,
        command_id=f'coo-cycle:{root.job_id}:create-review:{work.job_id}:1')
    rd=rt.attempts.dispatch_cycle_job(review.job_id,
        command_id=f'coo-cycle:{root.job_id}:dispatch:{review.job_id}:attempt:1',worker_id='r131-review',
        quota_class=service.config.coo_quota_class)
    assert rd is not None
    _r7a_complete_review(rt,rd,plan_attempt_id=attempt,plan_digest=digest,reviewed_job_id=work.job_id,
        reviewed_attempt_id=wd.attempt.attempt_id,reviewed_result_digest=sealed['role_result_digest'],identity_seed=19312)
    projection=rt.jobs.project_cycle_domain_consumption(root.job_id,domain_attempt_id=attempt)
    body=dict(schema_version='mastermind.executive_coo_domain_consumption/v1',root_job_id=root.job_id,
        domain_job_id=domain.job_id,domain_attempt_id=attempt,
        consumption_projection_digest=projection['consumption_projection_digest'],
        consumed_result='Same original Service owner consumed complete work and independent review.')
    later['transport']=ObservedConsumptionAdapter(session.observation.provider_session_id,body)
    return projection,body


def test_actual_initial_return_retains_original_token_and_does_not_restart_reconcile(tmp_path,monkeypatch):
    service,rt,root,domain,outcome,session,calls,rpc,initial,later,command=_context(tmp_path,monkeypatch)
    owner=service._coo_domain_owners[domain.job_id]
    assert owner.lease.lease_token==outcome.lease_token
    assert owner.supervisor is service.operator_supervisor and owner.runtime is rt
    before=_inventory(rt)
    asyncio.run(service._reconcile_unowned_cycle_attempts())
    assert _inventory(rt)==before and calls==[(outcome.attempt.attempt_id,False)] and not rpc
    assert service._service_state=='READY'
    assert outcome.lease_token not in repr(owner) and outcome.lease_token not in json.dumps(outcome.to_dict())


def test_real_service_settled_dispatch_sends_actual_bodies_and_full_seal_without_fresh_start(tmp_path,monkeypatch):
    ctx=_context(tmp_path,monkeypatch)
    service,rt,root,domain,outcome,session,calls,rpc,initial,later,command=ctx
    projection,body=_settle(ctx)
    original_plan=rt.events.get_event_by_command_id('orchestration-result-seal:'+outcome.attempt.attempt_id)
    before=_inventory(rt)
    result=asyncio.run(service._run_coo_cycle_once(root.job_id))
    assert result.action=='DISPATCHED'
    returned=result.to_dict()
    receipt=returned['receipt'] if 'receipt' in returned else returned['detail']
    assert receipt['consumption_seal']['consumption_result']==body
    sent=[payload for name,payload in rpc if name=='ohf-begin-turn']
    assert len(sent)==1 and outcome.lease_token not in json.dumps(returned)
    complete=sent[0]['prompt'].split('CANONICAL_REVIEWED_RESULTS_JSON:\n')[1].split('\nOUTPUT_SCHEMA_JSON:\n')[0]
    assert json.loads(complete)==projection
    assert calls==[(outcome.attempt.attempt_id,False),(outcome.attempt.attempt_id,True)]
    assert initial[0].begin_turn_calls==1 and initial[0].stop_calls==0
    assert rt.events.get_event_by_command_id(original_plan.command_id)==original_plan
    assert rt.attempts.get_attempt(outcome.attempt.attempt_id).status is AttemptStatus.CHECKPOINTED
    assert rt.jobs.get_job(domain.job_id).status is JobStatus.CHECKPOINTED
    after=_inventory(rt)
    for table in ('jobs','harness_session_epochs','process_generations'):
        if table in before:assert after[table]==before[table]
    with rt.store.read() as c:
        assert c.execute("SELECT COUNT(*) FROM coo_provider_charges WHERE root_job_id=? AND effect_class='FINAL'",(root.job_id,)).fetchone()[0]==1
    with pytest.raises(ExecutiveOperatorSupervisorError,match='INTENT cardinality'):
        asyncio.run(service._dispatch_cycle_job_exact(domain.job_id,command))
    assert _inventory(rt)==after and len(sent)==1
    assert service._service_state=='QUARANTINED' and domain.job_id in service._coo_domain_owners


@pytest.mark.parametrize('bad',['new_service','same_name_new_supervisor','missing_handle','fence','profile_data','token','command','root',
    'current_worker','current_quota','current_owner','current_principal','expired'])
def test_foreign_or_moved_original_owner_refuses_without_new_claim_or_rpc(tmp_path,monkeypatch,bad):
    ctx=_context(tmp_path,monkeypatch)
    service,rt,root,domain,outcome,session,calls,rpc,initial,later,command=ctx
    if bad=='new_service':
        other=ExecutiveControlService(service.config,autonomy_guard=lambda:None)
        other.runtime=rt;other.operator_supervisor=service.operator_supervisor;other.supervisor=service.supervisor
        service=other
    if bad=='same_name_new_supervisor':
        old=service.operator_supervisor
        service.operator_supervisor=ExecutiveOperatorSupervisor(rt,claimed_adapter_factory=old._claimed_adapter_factory,
            prompt_source=_PromptSource(),instance_id=old.instance_id)
    if bad=='missing_handle':service._coo_domain_owners.clear()
    if bad in {'fence','profile_data','token'}:
        owner=service._coo_domain_owners[domain.job_id];lease=owner.lease
        if bad=='fence':lease=AttemptLease(dataclasses.replace(lease.attempt,fence_generation=lease.attempt.fence_generation+1),lease.lease_token)
        if bad=='profile_data':lease=AttemptLease(dataclasses.replace(lease.attempt,requested_execution_profile={'foreign':'snapshot'}),lease.lease_token)
        if bad=='token':lease=AttemptLease(lease.attempt,'foreign-token')
        service._coo_domain_owners[domain.job_id]=dataclasses.replace(owner,lease=lease)
    if bad=='command':command+='-foreign'
    if bad=='root':_,domain=_root(service,rt,name='r131-foreign')
    if bad.startswith('current_'):
        original=rt.attempts.get_attempt
        fields={'current_worker':'worker_id','current_quota':'quota_class','current_owner':'lease_owner',
            'current_principal':'execution_principal_snapshot_digest'}
        def moved(attempt_id):
            value=original(attempt_id)
            return dataclasses.replace(value,**{fields[bad]:'foreign'}) if value and attempt_id==outcome.attempt.attempt_id else value
        monkeypatch.setattr(rt.attempts,'get_attempt',moved)
    if bad=='expired':
        expiry=__import__('datetime').datetime.fromisoformat(outcome.attempt.lease_expires_at).timestamp()
        monkeypatch.setattr(rt.store,'now_ms',lambda:int(expiry*1000)+1)
    before=_inventory(rt)
    with pytest.raises((StateConflict,ExecutiveOperatorSupervisorError)):
        asyncio.run(service._dispatch_cycle_job_exact(domain.job_id,command))
    assert _inventory(rt)==before and not rpc and len(calls)==1


def test_new_service_reconciliation_never_recovers_healthy_domain_by_owner_name(tmp_path,monkeypatch):
    service,rt,root,domain,outcome,session,calls,rpc,initial,later,command=_context(tmp_path,monkeypatch)
    fresh=ExecutiveControlService(service.config,autonomy_guard=lambda:None)
    fresh.runtime=rt;fresh.operator_supervisor=service.operator_supervisor;fresh.supervisor=service.supervisor
    before=_inventory(rt)
    with pytest.raises(StateConflict,match='original-owner adjudication'):
        asyncio.run(fresh._reconcile_unowned_cycle_attempts())
    assert _inventory(rt)==before and not rpc and len(calls)==1
    assert fresh._service_state=='QUARANTINED'


def test_unowned_active_sibling_quarantines_before_any_healthy_owner_recovery(tmp_path,monkeypatch):
    service,rt,root,domain,outcome,session,calls,rpc,initial,later,command=_context(tmp_path,monkeypatch)
    _,foreign=_root(service,rt,name='r131-unowned')
    q=rt.workers.get_quota_class(service.config.worker_id,service.config.coo_operator_quota_class)
    rt.workers.register_worker('r131-foreign',provider=q.provider,account_label='foreign-r131',worker_type='fixture',
        capabilities=[],quota_classes={q.quota_class:dict(provider=q.provider,model=q.model,effort=q.effort,
            cost_class=q.cost_class,capabilities=list(q.capabilities),metadata=dict(q.metadata))})
    claimed=rt.attempts.dispatch_cycle_job(foreign.job_id,
        command_id=f'coo-cycle:{foreign.root_job_id}:dispatch:{foreign.job_id}:attempt:1',
        worker_id='r131-foreign',quota_class=q.quota_class,lease_owner='unowned-r131')
    assert claimed is not None
    before=_inventory(rt)
    with pytest.raises(StateConflict,match='unowned'):
        asyncio.run(service._reconcile_unowned_cycle_attempts())
    assert _inventory(rt)==before and not rpc and len(calls)==1
    assert service._service_state=='QUARANTINED' and domain.job_id in service._coo_domain_owners


def test_failure_after_final_admission_retains_original_custody_without_retry(tmp_path,monkeypatch):
    ctx=_context(tmp_path,monkeypatch)
    service,rt,root,domain,outcome,session,calls,rpc,initial,later,command=ctx
    _settle(ctx)
    def unavailable(*args,**kwargs):raise RuntimeError('original G1 factory unavailable')
    service.operator_supervisor._claimed_adapter_factory=unavailable
    with pytest.raises(ExecutiveOperatorSupervisorError,match='construction refused'):
        asyncio.run(service._dispatch_cycle_job_exact(domain.job_id,command))
    held=_inventory(rt)
    assert service._service_state=='QUARANTINED' and not rpc
    assert service._coo_domain_owners[domain.job_id].lease.lease_token==outcome.lease_token
    with rt.store.read() as c:
        assert c.execute("SELECT COUNT(*) FROM coo_provider_charges WHERE root_job_id=? AND effect_class='FINAL'",(root.job_id,)).fetchone()[0]==1
    with pytest.raises(StateConflict,match='QUARANTINED'):
        asyncio.run(service._run_coo_cycle_once(root.job_id))
    assert _inventory(rt)==held and initial[0].stop_calls==0


def test_unknown_later_ack_preserves_generation_credit_and_original_owner(tmp_path,monkeypatch):
    ctx=_context(tmp_path,monkeypatch)
    service,rt,root,domain,outcome,session,calls,rpc,initial,later,command=ctx
    _settle(ctx)
    monkeypatch.setattr(later['transport'],'begin_turn',lambda **kwargs:TurnStartObservation(None,True))
    with pytest.raises(OperatorEffectUnknown):
        asyncio.run(service._dispatch_cycle_job_exact(domain.job_id,command))
    held=_inventory(rt)
    assert service._service_state=='QUARANTINED'
    assert service._coo_domain_owners[domain.job_id].lease.lease_token==outcome.lease_token
    assert rt.attempts.get_attempt(outcome.attempt.attempt_id).status is AttemptStatus.CHECKPOINTED
    assert initial[0].stop_calls==0
    assert len([name for name,payload in rpc if name=='ohf-begin-turn'])==1
    with rt.store.read() as c:
        assert c.execute("SELECT COUNT(*) FROM coo_provider_charges WHERE root_job_id=? AND effect_class='FINAL'",(root.job_id,)).fetchone()[0]==1
        assert c.execute("SELECT COUNT(*) FROM events WHERE attempt_id=? AND event_type='OPERATOR_OPERATION_EFFECT_UNKNOWN'",(outcome.attempt.attempt_id,)).fetchone()[0]>=1
    with pytest.raises(StateConflict,match='QUARANTINED'):
        asyncio.run(service._run_coo_cycle_once(root.job_id))
    assert _inventory(rt)==held


def test_close_discards_only_execution_local_custody_without_terminalizing_domain(tmp_path,monkeypatch):
    service,rt,root,domain,outcome,session,calls,rpc,initial,later,command=_context(tmp_path,monkeypatch)
    before=_inventory(rt)
    asyncio.run(service.close())
    assert not service._coo_domain_owners and _inventory(rt)==before
    assert rt.attempts.get_attempt(outcome.attempt.attempt_id).status is AttemptStatus.CHECKPOINTED
    assert initial[0].stop_calls==0 and not rpc


@pytest.mark.parametrize('status',['CLAIMED','RUNNING','CHECKPOINTED','CANCEL_REQUESTED'])
@pytest.mark.parametrize('expired',[False,True])
def test_real_cold_start_preflight_refuses_before_both_recovery_paths(tmp_path,monkeypatch,status,expired):
    if status in {'CHECKPOINTED','CANCEL_REQUESTED'}:
        service,rt,root,domain,outcome,session,calls,rpc,initial,later,command=_context(tmp_path,monkeypatch)
        if status=='CANCEL_REQUESTED':rt.jobs.cancel_job(domain.job_id)
    else:
        service,rt,_=_host(tmp_path,monkeypatch);service._register_worker()
        root,domain=_root(service,rt,name='r131-cold-'+status.lower())
        command=f'coo-cycle:{root.job_id}:dispatch:{domain.job_id}:attempt:1'
        if status=='CLAIMED':
            outcome=rt.attempts.dispatch_cycle_job(domain.job_id,command_id=command,
                worker_id=service.config.worker_id,quota_class=service.config.coo_operator_quota_class,
                lease_owner='r131-original-before-cold-start')
            assert outcome is not None
        else:
            class InitialUnknownCheckpoint(_DomainAdapter):
                def _canonical_result(self,turn):
                    a=rt.attempts.get_attempt(turn.attempt_id)
                    return _r7a_domain_envelope_review_required(rt.jobs.get_job(a.job_id),a)
            original=ExecutiveOperatorSupervisor(rt,
                claimed_adapter_factory=lambda a,r,l,**kw:InitialUnknownCheckpoint(rt,l,fail_checkpoint=True),
                prompt_source=_PromptSource(),instance_id='r131-original-before-cold-start')
            with pytest.raises(OperatorEffectUnknown):
                asyncio.run(original.start_cycle_job(domain.job_id,command_id=command))
    attempt=rt.attempts.list_attempts(domain.job_id)[0]
    assert attempt.status.value==status
    if expired:
        expiry=__import__('datetime').datetime.fromisoformat(attempt.lease_expires_at).timestamp()
        monkeypatch.setattr(rt.store,'now_ms',lambda:int(expiry*1000)+1)
    recovery=[]
    def must_not_recover(label):
        def reconcile(**kwargs):
            recovery.append(label)
            pytest.fail('startup recovery ran before original-owner preflight: '+label)
        return reconcile
    base=SimpleNamespace(runtime=rt,reconcile_restart=must_not_recover('sealed'))
    operator=ExecutiveOperatorSupervisor(rt,adapter_factory=lambda loader:pytest.fail('cold provider factory'),
        prompt_source=_PromptSource(),instance_id=attempt.lease_owner)
    monkeypatch.setattr(operator,'reconcile_restart',must_not_recover('operator'))
    async def identity():return None
    fresh=ExecutiveControlService(service.config,runtime_factory=lambda path:rt,
        supervisor_factory=lambda opened:base,operator_supervisor_factory=lambda opened,parent:operator,
        operator_identity_verifier=identity,autonomy_guard=lambda:None)
    before=_inventory(rt)
    with pytest.raises(StateConflict,match='original-owner adjudication'):
        asyncio.run(fresh.start())
    assert recovery==[] and _inventory(rt)==before
    assert fresh._service_state=='QUARANTINED' and fresh._lock_fd is None
    assert fresh._server is None and not fresh._coo_domain_owners


def test_actual_autonomous_tick_advances_retained_root_before_higher_priority_foreign_root(tmp_path,monkeypatch):
    from control_plane import ceo_intent
    from tests.test_executive_service import _coo_intent
    ctx=_context(tmp_path,monkeypatch)
    service,rt,root,domain,outcome,session,calls,rpc,initial,later,command=ctx
    projection,body=_settle(ctx)
    foreign_intent=_coo_intent(service.config,'r131-priority-foreign')
    foreign_intent['priority']=100
    accepted=ceo_intent.submit_intent(rt,foreign_intent,
        workspace_root=service.config.proof_workspace_root,execution_binding=service._coo_execution_binding)
    foreign=rt.jobs.get_job(accepted['job_id'])
    assert foreign is not None and foreign.priority>root.priority
    assert service._next_bound_coo_root()==foreign.job_id
    selected=[]
    real=service._run_coo_cycle
    async def exercise():
        service._coo_shutdown_event=asyncio.Event()
        async def observed(root_id):
            selected.append(root_id)
            try:return await real(root_id)
            finally:service._coo_shutdown_event.set()
        monkeypatch.setattr(service,'_run_coo_cycle',observed)
        service.config=dataclasses.replace(service.config,coo_tick_interval_seconds=1.0)
        await asyncio.wait_for(service._coo_tick_loop(),timeout=10)
    asyncio.run(exercise())
    assert selected==[root.job_id]
    assert service._coo_last_outcome['action']=='DISPATCHED'
    assert service._service_state=='READY' and service._coo_last_error is None
    assert not rt.attempts.list_attempts(foreign.job_id)
    assert not [j for j in rt.jobs.list_jobs() if j.parent_job_id==foreign.job_id]
    assert calls==[(outcome.attempt.attempt_id,False),(outcome.attempt.attempt_id,True)]
    seals=[e for e in rt.events.list_events(job_id=root.job_id) if e.event_type=='COO_DOMAIN_CONSUMPTION_SEALED']
    assert len(seals)==1 and seals[0].payload['consumption_result']==body
    assert not [e for e in rt.events.list_events(job_id=foreign.job_id) if e.event_type=='COO_SERVICE_TICK_REFUSED']


@pytest.mark.parametrize('command',['dispatch','create-proof-job','requeue','reconcile'])
@pytest.mark.parametrize('invalid_owner',[False,True])
def test_retained_domain_blocks_existing_proof_and_recovery_effect_boundaries(tmp_path,monkeypatch,command,invalid_owner):
    import control_plane.executive_service as module
    ctx=_context(tmp_path,monkeypatch,proof_before_domain=True)
    service,rt,root,domain,outcome,session,calls,rpc,initial,later,original_command=ctx
    proof=later['proof'];assert proof is not None
    owner=service._coo_domain_owners[domain.job_id]
    if invalid_owner:
        lease=AttemptLease(dataclasses.replace(owner.lease.attempt,fence_generation=owner.lease.attempt.fence_generation+1),owner.lease.lease_token)
        owner=dataclasses.replace(owner,lease=lease);service._coo_domain_owners[domain.job_id]=owner
    boundary=[]
    def effect(name):
        def stop(*a,**k):boundary.append(name);raise AssertionError('forbidden proof effect: '+name)
        return stop
    async def start(job_id):return effect('start')(job_id)
    service.supervisor=SimpleNamespace(start_job=start,reconcile_restart=effect('recovery'))
    monkeypatch.setattr(module,'prepare_credentialless_clone',effect('clone'))
    monkeypatch.setattr(service,'_rotate_proof_workspace',effect('rotation'))
    assert not service._dispatch_tasks and service._service_state=='READY'
    before=_inventory(rt)
    args={'job_id':proof.job_id} if command in {'dispatch','requeue'} else {}
    with pytest.raises(StateConflict,match='active dispatch|worker dispatch is active'):
        asyncio.run(service._dispatch_request(dict(version=module.CONTROL_PROTOCOL_VERSION,command=command,args=args)))
    assert boundary==[] and _inventory(rt)==before and not rpc and len(calls)==1
    assert service._coo_domain_owners[domain.job_id] is owner
    assert not rt.attempts.list_attempts(proof.job_id) and initial[0].stop_calls==0


@pytest.mark.parametrize('drift',['installed_binding','root_binding'])
@pytest.mark.parametrize('entry',['owner','cycle'])
def test_host_binding_drift_quarantines_original_owner_without_effects(tmp_path,monkeypatch,drift,entry):
    from control_plane.executive_service import ServiceError
    service,rt,root,domain,outcome,session,calls,rpc,initial,later,command=_context(tmp_path,monkeypatch)
    owner=service._coo_domain_owners[domain.job_id]
    if drift=='installed_binding':
        service.config=dataclasses.replace(service.config,proof_base_sha='b'*40)
    else:
        original=rt.jobs.get_job
        def moved(job_id):
            value=original(job_id)
            return dataclasses.replace(value,constraints=dict(value.constraints,model='foreign-root-host')) if job_id==root.job_id else value
        monkeypatch.setattr(rt.jobs,'get_job',moved)
    before=_inventory(rt)
    with pytest.raises((StateConflict,ServiceError)):
        if entry=='owner':service._require_owned_coo_domain(domain)
        else:asyncio.run(service._run_coo_cycle_once(root.job_id))
    assert service._service_state=='QUARANTINED'
    assert service._coo_domain_owners[domain.job_id] is owner
    assert _inventory(rt)==before and not rpc and len(calls)==1 and initial[0].stop_calls==0
