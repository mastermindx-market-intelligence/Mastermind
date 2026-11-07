"""Inert source-owner fixture, real temporary Runtime and existing native sink.

No provider, installed Runtime, service registration or browser is exercised.
"""
import copy
import json
import os
from pathlib import Path

import pytest

from control_plane import direct_native_execution as dn, executive_runtime as er, ceo_intent
from control_plane import project_planning_admission as planning
from control_plane.agentos_project_creation_source import AgentOsProjectCreationReader


def fixture(tmp_path, monkeypatch):
    runtime = er.Runtime.at(tmp_path / 'runtime')
    workspaces = tmp_path / 'workspaces'; workspaces.mkdir()
    source = dict(repository='macro', commit='e'*40,
        path='agentos/workstreams/WS-NEW-PROJECT.md', content_sha256='a'*64, request_sha256='b'*64)
    access = dn._issue_access('c'*64, 'WS:NEW-PROJECT', 'd'*64, lambda:'d'*64)
    executing = [True]
    def execution_guard():
        if not executing[0]: raise ValueError('Executive execution withdrawn')
    execution = dn._issue_execution_access(access, execution_guard)
    dialogue = dict(schema_version=er.EXECUTIVE_DIALOGUE_SOURCE_SCHEMA,
        work_ref=access.work_ref, watch_mode=None,
        commission_ref=dict(repository='w13ss/Mastermind', commit='f'*40,
            path='commission.md', content_sha256='0'*64))
    binding = dict(worker_id='codex-inert',base_sha='f'*40,eligible_quota_classes=['default'],provider='codex',
        model='gpt-5.4',effort='high',cost_class='default',routing_policy_version='routing-v1',
        execution_profile_id='sealed.worker.readonly.no-extensions.v1',execution_profile_digest='1'*64,
        capability_policy_version='capability-v1',capability_policy_digest='2'*64)
    admission = dn._issue_admission(access, dialogue, binding, execution_access=execution)
    context = dict(schema=planning.SCHEMA, work_ref=access.work_ref, source=source,
        publication=None,operation_key='explicit-first-request',request_sha256='4'*64,
        stage='clarify',principal_scope=access.principal_scope,origin_root='original-root',
        return_ref='original-parent-return',budget_ref='existing-budget',executive_authority_sha256='d'*64)
    from control_plane.workspace_source_operations import SourceOperationEvents
    events=SourceOperationEvents(runtime.store)
    lookup=dict(schema='mastermind.workspace_source_operation_lookup.v1',action='publish_project_proposal',
        request_id='mmos-project-create-'+'a'*40,work_ref=access.work_ref)
    original_ref=dict(schema='mastermind.terminal_original_input_reference.v1',input_ref='terminal-input:'+'4'*64,
        artifact_sha256='5'*64,payload_sha256='6'*64)
    events.prepare(lookup,'7'*64,request_sha256='8'*64,recipe_fingerprint_sha256='9'*64,original_input=original_ref,
        permission_binding_digest='0'*64,guard=lambda:True,publication_binding=dict(expected_commit='e'*40,branch=None,
        postimages=[dict(path=source['path'],content_sha256=source['content_sha256'],expected_preimage_sha256=None)]))
    events.claim_phase(lookup,'7'*64,permission_binding_digest='0'*64,
        preview_witness=dict(original_input=original_ref,recipe_fingerprint_sha256='9'*64),guard=lambda:True)
    receipt=events.retain_observation(lookup,'7'*64,phase='PUBLICATION',sources=[{k:v for k,v in source.items() if k!='request_sha256'}],
        proposal=None,qualify_observation=lambda _:True,guard=lambda:True)
    context['publication']=dict(request_id=lookup['request_id'],principal_scope='7'*64,
        event_id=receipt['event_id'],receipt_sha256=receipt['receipt_sha256'])
    from control_plane.executive_supervisor import ExecutiveSupervisor
    runs = tmp_path / 'runs'; runs.mkdir(mode=0o700)
    input_owner = planning.ProjectPlanningInput(ExecutiveSupervisor(runtime, object(), runs_root=runs, inspector=object(), process_controller=object()))
    context['request_sha256'] = dn.hashlib.sha256(b'Private first request.').hexdigest()
    context['input_artifact_sha256'] = input_owner.prepare(context,b'Private first request.')
    current = [copy.deepcopy(context)]
    observed = [copy.deepcopy(source)]
    # This fixture represents only the nominal owner's deterministic read.
    # A separate test proves an unissued real facade refuses in production.
    monkeypatch.setattr(AgentOsProjectCreationReader, 'read', lambda self, **kw:copy.deepcopy(observed[0]))
    reader = AgentOsProjectCreationReader(macro_root=tmp_path)
    owner = planning._issue_source(reader=reader,executive=execution,context=context,
        authority_guard=lambda:copy.deepcopy(current[0]),input_owner=input_owner,events=events,publication_guard=lambda:True)
    return dict(runtime=runtime,source=owner,executive_admission=admission,
        request={k:context[k] for k in ('operation_key','stage','request_sha256')},
        grounding=dict(mastermind_sha='f'*40,macro_sha='e'*40),workspace_root=workspaces), current, observed, executing


def test_explicit_first_request_joins_existing_sink_and_preserves_original_return(tmp_path, monkeypatch):
    kwargs,current,_,_ = fixture(tmp_path,monkeypatch)
    runtime = kwargs['runtime']
    assert runtime.jobs.list_jobs() == []  # publication/source issuance creates zero Jobs
    first = planning.submit_initial_request(**kwargs)
    again = planning.submit_initial_request(**kwargs)
    assert first['job_id'] == again['job_id'] and again['duplicate'] is True
    assert first['dispatched'] is False and first['accepted'] is True
    job = runtime.jobs.get_job(first['job_id'])
    assert job.root_job_id == job.job_id and job.parent_job_id is None
    assert job.attempt_limit == 1 and set(job.requested_authorities) == {'READ','RESEARCH'}
    assert runtime.attempts.list_attempts() == [] and not Path(job.worktree).exists()
    material = runtime.jobs.direct_native_provenance(job.job_id)
    assert material['project_planning'] == current[0]
    assert material['source'] == kwargs['executive_admission'].source
    # No private prompt/record body can enter the fixed public objective/Event.
    events = json.dumps(runtime.store.find_event_by_command_id(ceo_intent.command_id_for(first['intent_id'])))
    assert 'Initial project clarification' in job.objective and 'request_sha256' in events
    execution = planning.requalify_original(runtime,job_id=job.job_id,source=kwargs['source'],executive_admission=kwargs['executive_admission'])
    assert type(execution) is dn.DirectNativeExecutionAccess
    assert len(runtime.jobs.list_jobs()) == 1


@pytest.mark.parametrize('field', ['origin_root','return_ref','budget_ref','operation_key','request_sha256','publication','stage','principal_scope'])
def test_current_authority_change_refuses_without_job(tmp_path,monkeypatch,field):
    kwargs,current,_,_ = fixture(tmp_path,monkeypatch)
    current[0][field] = ('f'*64 if field.endswith('sha256') or field=='principal_scope' else 'changed')
    with pytest.raises(ValueError):planning.submit_initial_request(**kwargs)
    assert kwargs['runtime'].jobs.list_jobs() == []


def test_publication_and_source_dto_cannot_replace_actual_executive_capability(tmp_path,monkeypatch):
    kwargs,current,_,_ = fixture(tmp_path,monkeypatch)
    with pytest.raises(ValueError):planning._issue_source(reader=AgentOsProjectCreationReader(macro_root=tmp_path),
        executive=current[0],context=current[0],authority_guard=lambda:current[0],input_owner=kwargs['source']._input_owner,events=kwargs['source']._events,publication_guard=lambda:True)
    with pytest.raises(ValueError):planning.compose_admission(source=current[0],executive_admission=kwargs['executive_admission'])
    kwargs['executive_admission'] = dn._issue_admission(kwargs['executive_admission'].access,
        kwargs['executive_admission'].source,kwargs['executive_admission'].binding)
    with pytest.raises(ValueError):planning.submit_initial_request(**kwargs)
    assert kwargs['runtime'].jobs.list_jobs() == []


def test_nominal_facade_without_installed_binding_refuses(tmp_path):
    with pytest.raises(ValueError):AgentOsProjectCreationReader(macro_root=tmp_path).read(work_ref='WS:NEW-PROJECT',record_commit='e'*40)


@pytest.mark.parametrize('part',['source','executive','request','grounding'])
def test_source_withdrawal_and_private_request_mismatch_refuse(tmp_path,monkeypatch,part):
    kwargs,_,observed,executing=fixture(tmp_path,monkeypatch)
    if part=='source':observed[0]['content_sha256']='f'*64
    if part=='executive':executing[0]=False
    if part=='request':kwargs['request']['request_sha256']='f'*64
    if part=='grounding':kwargs['grounding']['macro_sha']='f'*40
    with pytest.raises(ValueError):planning.submit_initial_request(**kwargs)
    assert kwargs['runtime'].jobs.list_jobs()==[]


def test_context_participates_in_canonical_original_command_fingerprint(tmp_path,monkeypatch):
    kwargs,current,_,_=fixture(tmp_path,monkeypatch)
    captured=[]
    original=ceo_intent.submit_intent
    def record(runtime,intent,**kw):
        captured.append(copy.deepcopy(intent))
        return original(runtime,intent,**kw)
    monkeypatch.setattr(ceo_intent,'submit_intent',record)
    first=planning.submit_initial_request(**kwargs)
    intent=captured[0]
    assert intent['project_planning_sha256']==dn.digest(current[0])
    altered=copy.deepcopy(intent);altered['project_planning_sha256']='f'*64
    assert ceo_intent.intent_fingerprint(intent)!=ceo_intent.intent_fingerprint(altered)
    admission=planning.compose_admission(source=kwargs['source'],executive_admission=kwargs['executive_admission'])
    with pytest.raises(ceo_intent.CeoIntentError,match='fingerprint differs'):
        original(kwargs['runtime'],altered,workspace_root=kwargs['workspace_root'],direct_admission=admission)
    assert len(kwargs['runtime'].jobs.list_jobs())==1
    current[0]['return_ref']='another-return'
    with pytest.raises(ValueError):planning.requalify_original(kwargs['runtime'],job_id=first['job_id'],source=kwargs['source'],
        executive_admission=kwargs['executive_admission'])


def test_late_authority_change_rolls_back_job_and_event(tmp_path,monkeypatch):
    kwargs,current,_,_=fixture(tmp_path,monkeypatch)
    store=kwargs['runtime'].store;append=store.append_event
    def revoke(connection, **event):
        result=append(connection,**event)
        if event.get('event_type')=='JOB_CREATED':current[0]['budget_ref']='withdrawn-budget'
        return result
    monkeypatch.setattr(store,'append_event',revoke)
    with pytest.raises(ceo_intent.CeoIntentError):planning.submit_initial_request(**kwargs)
    assert kwargs['runtime'].jobs.list_jobs()==[]


def test_mutating_issued_context_or_forging_intent_digest_is_rejected(tmp_path,monkeypatch):
    kwargs,_,_,_=fixture(tmp_path,monkeypatch)
    admission=planning.compose_admission(source=kwargs['source'],executive_admission=kwargs['executive_admission'])
    admission._project_planning['return_ref']='another-parent'
    with pytest.raises(ValueError):admission.check()
    assert kwargs['runtime'].jobs.list_jobs()==[]


def prepared_fixture(tmp_path,monkeypatch):
    """Use the incumbent real Git allocator fixture without any live provider."""
    from test_direct_native_runtime_admission import fixture as native_fixture
    base=tmp_path/'native';base.mkdir()
    real=native_fixture(base)
    kwargs,current,observed,executing=fixture(tmp_path,monkeypatch)
    executive=kwargs['executive_admission']
    dialogue=copy.deepcopy(real[2].source);dialogue['work_ref']=executive.access.work_ref
    binding=copy.deepcopy(real[2].binding)
    kwargs['executive_admission']=dn._issue_admission(executive.access,dialogue,binding,
        execution_access=executive._execution_access)
    kwargs['grounding']['mastermind_sha']=binding['base_sha']
    first=planning.submit_initial_request(**kwargs)
    runtime=kwargs['runtime'];job_id=first['job_id']
    access=planning.requalify_original(runtime,job_id=job_id,source=kwargs['source'],executive_admission=kwargs['executive_admission'])
    runtime.jobs.prepare_direct_native_workspace(job_id,source_repository=real[4],shared_gid=os.getegid(),access=access)
    runtime.workers.register_worker(binding['worker_id'],provider='codex',account_label='offline',worker_type='test',
        quota_classes={'default':dict(provider='codex',model=binding['model'],effort=binding['effort'],cost_class=binding['cost_class'],
            capabilities=['read'],metadata={k:binding[k] for k in ('routing_policy_version','execution_profile_id',
                'execution_profile_digest','capability_policy_version','capability_policy_digest')})})
    return kwargs,current,observed,executing,job_id,access


def test_existing_allocator_claim_and_launch_gate_preserve_planning_source(tmp_path,monkeypatch):
    kwargs,_,_,_,job_id,access=prepared_fixture(tmp_path,monkeypatch)
    runtime=kwargs['runtime']
    lease=runtime.attempts.claim_job(job_id,command_id=f'direct-native-dispatch:{job_id}',lease_owner='inert',_direct_native_access=access)
    assert type(lease) is er.AttemptLease
    assert set(lease.attempt.effective_grant['authorities'])=={'READ','RESEARCH'}
    runtime.require_direct_native_launch_access(job_id,lease.attempt.attempt_id,access,lease=lease)
    assert kwargs['source']._input_owner.turn_input(runtime,job_id,source=kwargs['source'],executive_admission=kwargs['executive_admission'])=='Private first request.'
    with pytest.raises(ValueError,match='already exists'):
        kwargs['source']._input_owner.prepare(kwargs['source'].material(),b'Private first request.')
    assert len(runtime.attempts.list_attempts())==1


@pytest.mark.parametrize('change',['source','budget','executive','input'])
def test_fresh_claim_rechecks_actual_source_authority_and_private_custody(tmp_path,monkeypatch,change):
    kwargs,current,observed,executing,job_id,access=prepared_fixture(tmp_path,monkeypatch)
    runtime=kwargs['runtime']
    if change=='source':observed[0]['content_sha256']='f'*64
    if change=='budget':current[0]['budget_ref']='withdrawn'
    if change=='executive':executing[0]=False
    if change=='input':
        for path in (tmp_path/'runs').rglob('input.bin'):path.unlink()
    with pytest.raises((ValueError,er.StateConflict)):
        runtime.attempts.claim_job(job_id,command_id=f'direct-native-dispatch:{job_id}',lease_owner='inert',_direct_native_access=access)
    assert runtime.attempts.list_attempts()==[]
    assert runtime.jobs.get_job(job_id).status=='QUEUED'


def test_concurrent_identical_explicit_requests_create_one_original_job(tmp_path,monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    kwargs,_,_,_=fixture(tmp_path,monkeypatch)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:planning.submit_initial_request(**kwargs),range(2)))
    assert results[0]['job_id']==results[1]['job_id']
    assert sorted(row['duplicate'] for row in results)==[False,True]
    assert len(kwargs['runtime'].jobs.list_jobs())==1


def test_planning_dto_cannot_be_attached_to_unqualified_legacy_native_access(tmp_path,monkeypatch):
    kwargs,current,_,_=fixture(tmp_path,monkeypatch)
    executive=kwargs['executive_admission']
    with pytest.raises(ValueError):dn._issue_admission(executive.access,executive.source,executive.binding,
        execution_access=executive._execution_access,project_planning=current[0])


@pytest.mark.parametrize('field',['event_id','receipt_sha256','principal_scope','request_id'])
def test_publication_dto_must_rejoin_its_actual_original_event(tmp_path,monkeypatch,field):
    kwargs,current,_,_=fixture(tmp_path,monkeypatch)
    context=copy.deepcopy(current[0])
    context['publication'][field]=99999 if field=='event_id' else (
        'mmos-project-create-'+'b'*40 if field=='request_id' else 'f'*64)
    current[0]=copy.deepcopy(context)
    owner=kwargs['source']
    with pytest.raises(ValueError):planning._issue_source(reader=owner._reader,executive=owner._executive,
        context=context,authority_guard=lambda:copy.deepcopy(current[0]),input_owner=owner._input_owner,
        events=owner._events,publication_guard=lambda:True)
    assert kwargs['runtime'].jobs.list_jobs()==[]


def test_workspace_publication_revocation_cannot_use_executive_scope_as_substitute(tmp_path,monkeypatch):
    from dataclasses import replace
    kwargs,_,_,_=fixture(tmp_path,monkeypatch)
    original=kwargs['source']
    kwargs['source']=replace(original,_publication_guard=lambda:False)
    with pytest.raises(PermissionError):planning.submit_initial_request(**kwargs)
    assert kwargs['runtime'].jobs.list_jobs()==[]


def test_runtime_prevents_context_downgrade_in_immutable_original_command(tmp_path,monkeypatch):
    kwargs,_,_,_=fixture(tmp_path,monkeypatch)
    first=planning.submit_initial_request(**kwargs);runtime=kwargs['runtime']
    command=ceo_intent.command_id_for(first['intent_id'])
    event=runtime.store.find_event_by_command_id(command)
    payload=copy.deepcopy(event['payload']);del payload['provenance']['direct_native']['project_planning']
    with pytest.raises(er.StateConflict,match='events are immutable'):
        with runtime.store.transaction() as connection:
            connection.execute('UPDATE events SET payload_json=? WHERE command_id=?',(dn.canonical(payload).decode(),command))
    assert 'project_planning' in runtime.jobs.direct_native_provenance(first['job_id'])
