"""Genuine disposable Runtime/Supervisor join with explicit physical seams.

Only host grant issuance, process/binary/UID/broker observations and cleanup are
simulated. Immutable source Git, allocator, direct claim, Runtime launch/terminal
validators, Event-backed principal, bounded read and consumption writes are real.
No live worker, service, credential, provider or host observation is used.
"""
from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import json
import os
import pwd
import subprocess
import time
from pathlib import Path

import pytest

from control_plane import ceo_intent, ceo_request, direct_native_execution as dn
from control_plane import executive_runtime as er
from control_plane.direct_native_result import DirectResultProjectionError, EVENT_TYPE
from control_plane.executive_agent_capabilities import ExecutionCapabilityRegistry
from control_plane.executive_orchestration_result import canonical_bytes
from control_plane.executive_supervisor import ExecutiveSupervisor, RESULT_SCHEMA_VERSION
from control_plane.worker_execution_contract import CollectionReceipt, WorkerRunStatus
from control_plane.codex_worker import WorkerResult
from tests.test_executive_supervisor import FakeInspector, FakeProcessController
from tests.test_executive_terminal_return import _PlannerSealedWorkerAdapter, _SEALED_WORKER_SECRET_CANARY
from tests.test_fabric_result_projection import _bound_reader, _release


class DirectSealedAdapter(_PlannerSealedWorkerAdapter):
    """Physical observations simulated; actual direct producer is unmodified."""
    start_count = 0

    def __init__(self, inspector, *, provider_home):
        super().__init__(inspector, root_job_id="", provider_home=provider_home)

    async def start(self, spec):
        self.root_job_id = spec.job_id  # Physical fixture only; no role terminal is produced.
        self.start_count += 1
        return await super().start(spec)

    async def collect_result(self, ref):
        assert ref == self.ref and self.spec is not None
        output = dict(schema_version=RESULT_SCHEMA_VERSION, job_id=self.spec.job_id,
            run_id=self.spec.run_id, worker_id=self.spec.worker_id, status='COMPLETED',
            summary='Retained direct research findings', current_state='Complete',
            completed_steps=['Read the immutable admitted commission'],
            next_actions=['Original parent may explicitly acknowledge this result'],
            artifacts=[], errors=[], validations=[])
        result_path = Path(ref.result_path)
        result_path.write_bytes(canonical_bytes(output)); result_path.chmod(0o600)
        provider_session = 'thread-inert-direct'
        collected = dataclasses.replace(ref, provider_session_id=provider_session)
        result = WorkerResult(job_id=self.spec.job_id, run_id=self.spec.run_id,
            worker_id=self.spec.worker_id, status=WorkerRunStatus.SUCCEEDED,
            structured_output=output, artifact_manifest=(),
            git_manifest={'base_sha':self.spec.expected_base_sha,'head_sha':self.spec.expected_base_sha},
            usage={'input_tokens':10,'output_tokens':5}, provider_session_id=provider_session,
            exit_code=0, started_at=ref.started_at, finished_at='2026-08-11T00:00:01+00:00', error=None)
        return CollectionReceipt(process_ref=collected, result=result,
            stdout_sha256=hashlib.sha256(Path(ref.stdout_path).read_bytes()).hexdigest(),
            stderr_sha256=hashlib.sha256(Path(ref.stderr_path).read_bytes()).hexdigest(),
            result_sha256=hashlib.sha256(result_path.read_bytes()).hexdigest())


def make_direct_supervisor(runtime, *, workspace_root, runs_root, provider_home):
    """Actual Supervisor with only native physical execution/cleanup simulated.

    The caller owns genuine Runtime admission/allocator/current host grant.
    No terminal, claim, Event, receipt validator or current-access method is stubbed.
    """
    provider_home=Path(provider_home)
    provider_home.mkdir(mode=0o700,parents=True,exist_ok=True)
    adapter=DirectSealedAdapter(FakeInspector(),provider_home=provider_home)
    return ExecutiveSupervisor(runtime,adapter,runs_root=Path(runs_root),
        isolation_roots=(Path(workspace_root),Path(runs_root)),
        worker_user=pwd.getpwuid(os.geteuid()).pw_name,worker_uid=os.geteuid(),worker_gid=os.getegid(),
        heartbeat_interval_seconds=.01,inspector=adapter.inspector,
        process_controller=FakeProcessController(adapter.inspector),
        secret_canary_verdict=_SEALED_WORKER_SECRET_CANARY,require_complete_launch_attestation=True,
        instance_id='joined-direct-supervisor')


def _source(root):
    source=root/'source'; source.mkdir(mode=0o700)
    home=root/'git-home'; home.mkdir(mode=0o700)
    env={'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C','HOME':str(home),'GIT_CONFIG_GLOBAL':'/dev/null',
         'GIT_CONFIG_NOSYSTEM':'1','GIT_TERMINAL_PROMPT':'0'}
    def git(*args):
        return subprocess.check_output(['git','-c','core.hooksPath=/dev/null','-c','core.fsmonitor=false',
            '-C',str(source),*args],env=env,text=True).strip()
    git('init','-q');git('config','user.name','Offline fixture');git('config','user.email','offline@example.invalid')
    (source/'commission.md').write_text('Read this inert immutable research commission only.\n')
    git('add','commission.md');git('commit','-qm','Fixture commission')
    return source,git('rev-parse','HEAD')


@pytest.fixture
def joined(tmp_path):
    source,base=_source(tmp_path)
    registry=ExecutionCapabilityRegistry.load()
    profile=registry.resolve('sealed.worker.readonly.no-extensions.v1')
    source_data=dict(schema_version=er.EXECUTIVE_DIALOGUE_SOURCE_SCHEMA,work_ref='WS:H2',watch_mode=None,
        commission_ref=dict(repository='mastermindx-market-intelligence/Mastermind',commit=base,
            path='commission.md',content_sha256=hashlib.sha256((source/'commission.md').read_bytes()).hexdigest()))
    binding=dict(base_sha=base,eligible_quota_classes=['default'],provider='codex',model='gpt-5.6-sol',
        effort='high',cost_class='default',routing_policy_version='inert-direct-v1',
        execution_profile_id=profile.profile_id,execution_profile_digest=profile.profile_digest,
        capability_policy_version=registry.policy_version,capability_policy_digest=registry.policy_digest)
    generation=['c'*64]
    # Explicit host/current grant seam. Runtime receives its genuine private
    # access type; no Runtime claim/source/terminal validator is monkeypatched.
    access=dn._issue_access('d'*64,'WS:H2',generation[0],lambda:generation[0])
    admission=dn._issue_admission(access,source_data,binding)
    workspaces=tmp_path/'workspaces';workspaces.mkdir(mode=0o700)
    intent=ceo_request.build_trusted_envelope(ceo_request.normalize_high_level_request(dict(
        operation_key='direct-joined-source',objective='Read one inert research commission.',
        department='executive-infrastructure',priority=0,execution_profile='native_research_only',
        workstream='WS:H2',attempt_limit=1)),intent_id='ceo-direct-joined',workspace_root=str(workspaces),
        grounding=dict(mastermind_sha=base,macro_sha='e'*40))
    intent.update(schema=ceo_intent.INTENT_SCHEMA_DIRECT,intent_kind='direct_native_readonly',business_impact='routine')
    now=[int(time.time()*1000)]
    runtime=er.Runtime.at(tmp_path/'runtime',clock=lambda:now[0],lease_seconds=30)
    receipt=ceo_intent.submit_intent(runtime,intent,workspace_root=workspaces,direct_admission=admission)
    job=runtime.jobs.get_job(receipt['job_id'])
    runtime.jobs.prepare_direct_native_workspace(job.job_id,source_repository=source,
        shared_gid=os.getegid(),access=access)
    metadata={k:binding[k] for k in ('routing_policy_version','execution_profile_id',
        'execution_profile_digest','capability_policy_version','capability_policy_digest')}
    metadata['adapter_id']='codex-cli'
    runtime.workers.register_worker('codex-01',provider='codex',account_label='inert-direct-account',
        worker_type='codex-cli',capabilities=['read','research'],quota_classes={'default':dict(
            provider='codex',model=binding['model'],effort=binding['effort'],cost_class=binding['cost_class'],
            capabilities=['read','research'],metadata=metadata)})
    supervisor=make_direct_supervisor(runtime,workspace_root=workspaces,
        runs_root=tmp_path/'runs',provider_home=tmp_path/'provider-home')
    adapter=supervisor.adapter
    supervisor._joined_clock=now  # Test-owned controllable clock, not an authority predicate.
    return runtime,job,access,generation,adapter,supervisor


def _complete(f):
    runtime,job,access,_,adapter,supervisor=f
    active=asyncio.run(supervisor.start_direct_native_job(job.job_id,access=access))
    replay=asyncio.run(supervisor.start_direct_native_job(job.job_id,access=access))
    assert type(replay) is er.OrchestrationDispatchOutcome
    assert replay.attempt.attempt_id==active.lease.attempt.attempt_id and adapter.start_count==1
    receipt=asyncio.run(supervisor.finish_job(active))
    assert receipt.job.status is er.JobStatus.COMPLETED
    assert receipt.attempt.status is er.AttemptStatus.COMPLETED
    assert adapter.start_count==1
    assert receipt.job.result['schema_version']==dn.TERMINAL_SCHEMA
    assert receipt.job.orchestration_role is None and receipt.job.root_job_id==job.job_id
    assert len(runtime.attempts.list_attempts())==1
    return receipt


def test_actual_direct_producer_bounded_result_explicit_consume_replay_and_reopen(joined):
    runtime,job,access,_,adapter,supervisor=joined
    receipt=_complete(joined)
    attempt_id=receipt.attempt.attempt_id
    with runtime.store.read() as connection:
        raw=connection.execute('SELECT * FROM attempts WHERE attempt_id=?',(attempt_id,)).fetchone()
        assert raw['effective_grant_json'] is None and raw['execution_principal_snapshot_json'] is None
        assert connection.execute("SELECT count(*) FROM events WHERE event_type='DIRECT_NATIVE_LAUNCH_PRINCIPAL' AND attempt_id=?",(attempt_id,)).fetchone()[0]==1
    assert receipt.attempt.effective_grant['role'] is None
    assert receipt.attempt.execution_principal_snapshot is not None
    keeper,namespace,binding,reader=_bound_reader(runtime)
    try:
        request=dict(work_ref='WS:H2',job_id=job.job_id,attempt_id=None)
        view=reader.read_direct_native_result_bounded(request,access=access)
        assert view['availability']=='AVAILABLE',view
        assert view['selection']['attempt_id']==attempt_id
        assert view['result']['summary']=='Retained direct research findings'
        assert view['consumption']==dict(state='UNCONSUMED',receipt_digest=None)
        assert namespace.entries==namespace.exits
        selected=dict(view['selection'],result_digest=view['result']['result_digest'],operation_key='ack-original-parent')
        consumed=runtime.consume_direct_native_result(selected,access=access)
        assert set(consumed)=={'state','receipt_digest'} and consumed['state']=='CONSUMED'
        acknowledged=reader.read_direct_native_result_bounded(request,access=access)
        assert acknowledged['consumption']['state']=='CONSUMED'
        original_receipt=acknowledged['consumption']['receipt_digest']
        runtime.consume_direct_native_result(selected,access=access)
        assert reader.read_direct_native_result_bounded(request,access=access)==acknowledged
        with runtime.store.read() as connection:
            assert connection.execute('SELECT count(*) FROM events WHERE event_type=?',(EVENT_TYPE,)).fetchone()[0]==1
        for changed in (dict(selected,result_digest='f'*64),dict(selected,operation_key='another-ack')):
            with pytest.raises((er.StateConflict,DirectResultProjectionError)):
                runtime.consume_direct_native_result(changed,access=access)
        reopened=er.Runtime.at(runtime.store.root,create=False,read_binding=binding)
        again=reopened.read_direct_native_result_bounded(request,access=access)
        assert again==acknowledged and again['consumption']['receipt_digest']==original_receipt
        terminal_replay=asyncio.run(supervisor.start_direct_native_job(job.job_id,access=access))
        assert type(terminal_replay) is er.OrchestrationDispatchOutcome and adapter.start_count==1
    finally:
        _release(keeper,binding)


@pytest.mark.parametrize('refusal',['foreign-parent','changed-generation'])
def test_actual_foreign_parent_or_changed_generation_cannot_read_or_consume(joined,refusal):
    runtime,job,access,generation,_,_ = joined
    receipt=_complete(joined)
    selected=dict(work_ref='WS:H2',job_id=job.job_id,attempt_id=receipt.attempt.attempt_id)
    keeper,namespace,binding,reader=_bound_reader(runtime)
    try:
        actual=reader.read_direct_native_result_bounded(selected,access=access)
        assert actual['availability']=='AVAILABLE'
        command=dict(selected,result_digest=actual['result']['result_digest'],operation_key='ack-original')
        if refusal=='foreign-parent':
            rejected=dn._issue_access('a'*64,'WS:H2',generation[0],lambda:generation[0])
        else:
            generation[0]='f'*64
            rejected=access
        assert reader.read_direct_native_result_bounded(selected,access=rejected)['availability']=='UNAVAILABLE'
        with pytest.raises((er.StateConflict,ValueError)):
            runtime.consume_direct_native_result(command,access=rejected)
        with runtime.store.read() as connection:
            assert connection.execute('SELECT count(*) FROM events WHERE event_type=?',(EVENT_TYPE,)).fetchone()[0]==0
    finally:
        _release(keeper,binding)


def test_actual_expired_lease_during_preparation_never_starts_adapter(joined,monkeypatch):
    runtime,job,access,_,adapter,supervisor=joined
    original=supervisor._launch_spec
    def advance_after_sealing(*args,**kwargs):
        spec=original(*args,**kwargs)
        supervisor._joined_clock[0]+=60_000
        return spec
    monkeypatch.setattr(supervisor,'_launch_spec',advance_after_sealing)
    with pytest.raises(er.RuntimeProofError):
        asyncio.run(supervisor.start_direct_native_job(job.job_id,access=access))
    assert adapter.start_count==0
    attempts=runtime.attempts.list_attempts(job.job_id)
    assert len(attempts)==1 and attempts[0].status is er.AttemptStatus.CLAIMED
    assert attempts[0].pid is None
    with runtime.store.read() as connection:
        assert connection.execute("SELECT count(*) FROM events WHERE event_type='ATTEMPT_PROCESS_RECORDED' AND job_id=?",(job.job_id,)).fetchone()[0]==0


@pytest.mark.parametrize('field',['token','fence','worker','quota'])
def test_actual_final_gate_refuses_other_lease_identity(joined,field):
    runtime,job,access,_,adapter,supervisor=joined
    lease=runtime.attempts.claim_job(job.job_id,command_id='direct-native-dispatch:'+job.job_id,
        lease_owner=supervisor.instance_id,_direct_native_access=access)
    assert type(lease) is er.AttemptLease
    if field=='token':
        wrong=er.AttemptLease(attempt=lease.attempt,lease_token='wrong-token')
    else:
        change=dict(fence_generation=lease.attempt.fence_generation+1) if field=='fence' else {
            'worker_id' if field=='worker' else 'quota_class':'foreign-identity'}
        wrong=er.AttemptLease(attempt=dataclasses.replace(lease.attempt,**change),lease_token=lease.lease_token)
    with pytest.raises(er.RuntimeProofError):
        runtime.require_direct_native_launch_access(job.job_id,lease.attempt.attempt_id,access,lease=wrong)
    assert adapter.start_count==0


def test_actual_bound_direct_read_refuses_oversized_event_before_python_materialization(joined,monkeypatch):
    runtime,job,access,_,_,_=joined
    receipt=_complete(joined)
    # Adversarial extra immutable Event in this disposable DB only; do not
    # bypass the actual immutable Event/terminal Attempt SQL triggers.
    with runtime.store.transaction() as connection:
        runtime.store.append_event(connection,aggregate_type='job',aggregate_id=job.job_id,
            job_id=job.job_id,event_type='JOB_CREATED',actor='inert-adversarial-fixture',
            command_id='inert-oversize-event',payload={'oversized_sentinel':'x'*(er.BOUNDED_ROLE_RESULT_MAX_CELL_BYTES+1)})
    keeper,namespace,binding,reader=_bound_reader(runtime)
    original_connect=er.sqlite3.connect
    materialized=[]
    def connect(*args,**kwargs):
        connection=original_connect(*args,**kwargs)
        def bounded_factory(cursor,row):
            if any(isinstance(value,(str,bytes)) and len(value)>er.BOUNDED_ROLE_RESULT_MAX_CELL_BYTES for value in row):
                materialized.append('oversized-cell')
                raise AssertionError('oversized Event reached Python materialization')
            return er.sqlite3.Row(cursor,row)
        connection.row_factory=bounded_factory
        return connection
    monkeypatch.setattr(er.sqlite3,'connect',connect)
    try:
        with pytest.raises(er.RuntimeRoleResultOverBudget):
            reader.read_direct_native_result_bounded(dict(work_ref='WS:H2',job_id=job.job_id,
                attempt_id=receipt.attempt.attempt_id),access=access)
        assert materialized==[]
    finally:
        _release(keeper,binding)
