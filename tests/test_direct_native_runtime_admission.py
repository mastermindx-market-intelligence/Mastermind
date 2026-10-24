"""Real temporary Runtime/allocator; private host/source grant is fixture-only."""
import copy
import os
from pathlib import Path
import subprocess
import pytest
from control_plane import direct_native_execution as dn, executive_runtime as er, ceo_intent, ceo_request


def fixture(tmp_path):
    source=tmp_path/'source';source.mkdir()
    def git(*argv):
        return subprocess.check_output(['git','-C',str(source),*argv],text=True).strip()
    git('init','-q');git('config','user.name','Offline');git('config','user.email','offline@example.invalid')
    (source/'commission.md').write_text('Read the inert fixture only.\n')
    git('add','commission.md');git('commit','-qm','fixture')
    base=git('rev-parse','HEAD')
    source_data=dict(schema_version=er.EXECUTIVE_DIALOGUE_SOURCE_SCHEMA,work_ref='WS:H2',watch_mode=None,
        commission_ref=dict(repository='w13ss/Mastermind',commit=base,path='commission.md',content_sha256=dn.hashlib.sha256((source/'commission.md').read_bytes()).hexdigest()))
    binding=dict(base_sha=base,eligible_quota_classes=['default'],provider='codex',model='gpt-5.4',effort='high',cost_class='default',
        routing_policy_version='routing-v1',execution_profile_id='sealed.worker.readonly.no-extensions.v1',execution_profile_digest='a'*64,
        capability_policy_version='capability-v1',capability_policy_digest='b'*64)
    generation=['c'*64]
    access=dn._issue_access('d'*64,'WS:H2',generation[0],lambda:generation[0])
    admission=dn._issue_admission(access,source_data,binding)
    workspaces=tmp_path/'workspaces';workspaces.mkdir()
    intent=ceo_request.build_trusted_envelope(ceo_request.normalize_high_level_request(dict(operation_key='h2-native-runtime',
        objective='Read inert source.',department='executive-infrastructure',priority=0,execution_profile='native_research_only',
        workstream='WS:H2',attempt_limit=1)),intent_id='ceo-h2-native-runtime',workspace_root=str(workspaces),grounding=dict(mastermind_sha=base,macro_sha='e'*40))
    intent.update(schema=ceo_intent.INTENT_SCHEMA_DIRECT,intent_kind='direct_native_readonly',business_impact='routine')
    runtime=er.Runtime.at(tmp_path/'runtime')
    return runtime,intent,admission,access,source,workspaces,generation


def create(f):
    runtime,intent,admission,_,_,workspaces,_=f
    return runtime.jobs.create_direct_native_job(intent,fingerprint=ceo_intent.intent_fingerprint(intent),
        command_id=ceo_intent.command_id_for(intent['intent_id']),workspace_root=workspaces,admission=admission)


def test_actual_direct_creation_and_allocator_completion(tmp_path):
    f=fixture(tmp_path);runtime,_,_,access,source,workspaces,_=f
    job=create(f)
    assert job.orchestration_role is None and job.root_job_id==job.job_id and job.parent_job_id is None
    assert job.attempt_limit==1 and set(job.requested_authorities)=={'READ','RESEARCH'}
    assert Path(job.worktree)==workspaces/job.job_id.lower()
    material=runtime.jobs.direct_native_provenance(job.job_id)
    assert material['principal_scope']==access.principal_scope
    receipt=runtime.jobs.prepare_direct_native_workspace(job.job_id,source_repository=source,shared_gid=os.getegid(),access=access)
    assert receipt['receipt']['remote_count']==0
    assert runtime.jobs.prepare_direct_native_workspace(job.job_id,source_repository=source,shared_gid=os.getegid(),access=access)==receipt
    assert runtime.jobs.list_jobs()==[runtime.jobs.get_job(job.job_id)]
    with pytest.raises(er.StateConflict,match='exact host dispatch'):
        runtime.attempts.claim_job(job.job_id)


def test_caller_policy_or_provenance_cannot_create_direct_job(tmp_path):
    runtime,*_=fixture(tmp_path)
    for kwargs in (dict(constraints={dn.POLICY_KEY:dn.POLICY}),dict(provenance={'direct_native':{}})):
        with pytest.raises(er.StateConflict,match='private host admission'):
            runtime.jobs.create_job('foreign',**kwargs)
    assert runtime.jobs.list_jobs()==[]


def test_late_generation_change_rolls_back_all_job_events(tmp_path):
    f=fixture(tmp_path);f[-1][0]='f'*64
    with pytest.raises(ValueError,match='generation changed'):create(f)
    assert f[0].jobs.list_jobs()==[]


def test_genuine_sink_replay_and_private_direct_claim(tmp_path):
    f=fixture(tmp_path);runtime,intent,admission,access,source,workspaces,_=f
    first=ceo_intent.submit_intent(runtime,intent,workspace_root=workspaces,direct_admission=admission)
    again=ceo_intent.submit_intent(runtime,intent,workspace_root=workspaces,direct_admission=admission)
    assert first['schema']==ceo_intent.RECEIPT_SCHEMA_DIRECT
    assert not first['duplicate'] and again['duplicate'] and first['job_id']==again['job_id']
    assert first['dispatched'] is False
    job=runtime.jobs.get_job(first['job_id'])
    runtime.jobs.prepare_direct_native_workspace(job.job_id,source_repository=source,shared_gid=os.getegid(),access=access)
    runtime.workers.register_worker('codex-offline',provider='codex',account_label='offline',worker_type='test',
        quota_classes={'default':dict(provider='codex',model='gpt-5.4',effort='high',cost_class='default',capabilities=['read'],metadata={k:admission.binding[k] for k in ('routing_policy_version','execution_profile_id','execution_profile_digest','capability_policy_version','capability_policy_digest')})})
    lease=runtime.attempts.claim_job(job.job_id,command_id=f'direct-native-dispatch:{job.job_id}',
        lease_owner='offline-supervisor',_direct_native_access=access)
    assert type(lease) is er.AttemptLease and lease.attempt.effective_grant['role'] is None
    assert set(lease.attempt.effective_grant['authorities'])=={'READ','RESEARCH'}
    replay=runtime.attempts.claim_job(job.job_id,command_id=f'direct-native-dispatch:{job.job_id}',
        lease_owner='offline-supervisor',_direct_native_access=access)
    assert type(replay) is er.OrchestrationDispatchOutcome and replay.attempt.attempt_id==lease.attempt.attempt_id
    assert len(runtime.attempts.list_attempts())==1
    runtime.require_direct_native_launch_access(job.job_id,lease.attempt.attempt_id,access,lease=lease)
    assert runtime.read_direct_native_result_bounded(dict(work_ref='WS:H2',job_id=job.job_id,attempt_id=None),access=access)['availability']=='UNAVAILABLE'


@pytest.mark.parametrize('mutation', ['expiry','token','fence','quota'])
def test_final_launch_reuses_exact_live_lease_predicate(tmp_path,mutation):
    f=fixture(tmp_path);runtime,_,_,access,source,_,_=f;job=create(f)
    runtime.jobs.prepare_direct_native_workspace(job.job_id,source_repository=source,shared_gid=os.getegid(),access=access)
    binding=f[2].binding
    runtime.workers.register_worker('codex-offline',provider='codex',account_label='offline',worker_type='test',quota_classes={
        'default':dict(provider='codex',model='gpt-5.4',effort='high',cost_class='default',capabilities=['read'],
        metadata={k:binding[k] for k in ('routing_policy_version','execution_profile_id','execution_profile_digest','capability_policy_version','capability_policy_digest')})})
    lease=runtime.attempts.claim_job(job.job_id,command_id=f'direct-native-dispatch:{job.job_id}',lease_owner='inert',_direct_native_access=access)
    runtime.require_direct_native_launch_access(job.job_id,lease.attempt.attempt_id,access,lease=lease)
    if mutation=='expiry':
        runtime.store.clock=lambda:10**15
    elif mutation=='token':
        lease=er.dataclasses.replace(lease,lease_token='foreign-token')
    elif mutation=='fence':
        lease=er.dataclasses.replace(lease,attempt=er.dataclasses.replace(lease.attempt,fence_generation=lease.attempt.fence_generation+1))
    else:
        with runtime.store.transaction() as connection:
            connection.execute("UPDATE worker_quota_classes SET held_attempt_id=NULL,status='OFFLINE' WHERE worker_id='codex-offline'")
    with pytest.raises(er.StateConflict):
        runtime.require_direct_native_launch_access(job.job_id,lease.attempt.attempt_id,access,lease=lease)
    assert len(runtime.attempts.list_attempts())==1
