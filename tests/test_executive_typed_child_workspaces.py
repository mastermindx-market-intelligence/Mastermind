"""Offline actual owners; no worker/provider or live consumer repository.

Runtime role completions/physical owner observations use the explicitly inert
accepted fixtures. Authenticated HTTP/Unix producer, allocator, Git, Runtime
reservations, Service binding and Supervisor launch-spec stay real.
"""
import asyncio
import builtins
import copy
import dataclasses
import io
import json
import os
from pathlib import Path
import socket
import subprocess

import pytest
from control_plane import executive_runtime as er, executive_workspace as ew
from control_plane.executive_service import ExecutiveControlService
from control_plane.executive_paid_fabric_composition import PaidWorkPlacement
from tests import test_paid_authenticated_launch_producer as app
from tests import test_paid_runtime_owner_integration as paid
from tests.test_executive_service import _config

rsa_key=app.rsa_key
short_socket_root=app.short_socket_root


@pytest.fixture(autouse=True)
def offline_boundary(monkeypatch,tmp_path):
    # Install before fixture constructors: a high-level fake does not stop an
    # incumbent constructor's provider/status/credential fallback.
    real_connect=socket.socket.connect
    def connect(sock,address):
        if sock.family != socket.AF_UNIX: raise AssertionError('offline network forbidden')
        return real_connect(sock,address)
    monkeypatch.setattr(socket.socket,'connect',connect)
    real_popen=subprocess.Popen
    def popen(argv,*args,**kwargs):
        if not isinstance(argv,(list,tuple)) or Path(str(argv[0])).name not in {'git','node'}:
            raise AssertionError('offline provider/process fallback forbidden')
        if Path(str(argv[0])).name=='git' and any(str(x) in {'fetch','push','pull','ls-remote'} for x in argv):
            raise AssertionError('offline Git network forbidden')
        return real_popen(argv,*args,**kwargs)
    monkeypatch.setattr(subprocess,'Popen',popen)
    def forbid_credential(path):
        value=os.fspath(path) if isinstance(path,(str,bytes,os.PathLike)) else ''
        if isinstance(value,str) and (value.endswith('/auth.json') or '/Library/Keychains/' in value or '/.ssh/' in value):
            raise AssertionError('credential fallback forbidden')
    for owner in (os,builtins,io):
        real_open=owner.open
        def safe_open(path,*args,_open=real_open,**kwargs):
            forbid_credential(path)
            return _open(path,*args,**kwargs)
        monkeypatch.setattr(owner,'open',safe_open)


def _policy_from_normal_service(tmp_path):
    config=_config(tmp_path,coo_paid_work_placements=(PaidWorkPlacement('glm.paid.sealed-input','offline-paid-read'),))
    service=ExecutiveControlService(config,supervisor_factory=lambda _:object())
    policy=service._coo_execution_binding[er.CHILD_WORKSPACE_POLICY_KEY]
    assert policy==er.CHILD_WORKSPACE_POLICY
    return policy


def test_authenticated_normal_host_composes_two_distinct_allocator_owned_children(
    rsa_key,tmp_path,short_socket_root,monkeypatch,
):
    services=[]
    real_class=app.ExecutiveControlService
    def factory(*args,**kwargs):
        args=(dataclasses.replace(args[0],proof_shared_gid=os.getegid()),*args[1:])
        value=real_class(*args,**kwargs);services.append(value);return value
    monkeypatch.setattr(app,'ExecutiveControlService',factory)
    real_admit=er.JobRegistry.admit_cycle_plan
    def admit(registry,*args,**kwargs):
        children=real_admit(registry,*args,**kwargs)
        service=services[-1];root=registry.get_job(children[0].root_job_id)
        assert root.constraints[er.CHILD_WORKSPACE_POLICY_KEY]==er.CHILD_WORKSPACE_POLICY
        records=[]
        for child in children:
            assert child.worktree!=root.worktree
            with pytest.raises(er.StateConflict,match='allocator provenance'):
                registry.coo_child_workspace_completion(child.job_id)
            records.append(registry.prepare_coo_child_workspace(child.job_id,
                source_repository=service.config.proof_source_repository,shared_gid=service.config.proof_shared_gid))
            assert registry.prepare_coo_child_workspace(child.job_id,
                source_repository=service.config.proof_source_repository,shared_gid=service.config.proof_shared_gid)==records[-1]
            service._require_coo_workspace(child)
        assert len({c.worktree for c in children})==2
        assert len({r['identity']['git']['inode'] for r in records})==2
        assert all(r['receipt']['remote_count']==0 and r['receipt']['base_sha']==service.config.proof_base_sha for r in records)
        assert all(r['binding']['root_job_id']==root.job_id and r['binding']['role']=='work' for r in records)
        with registry.store.read() as connection:
            assert connection.execute("SELECT count(*) FROM events WHERE event_type='COO_CHILD_WORKSPACE_REQUESTED'").fetchone()[0]==2
        return children
    monkeypatch.setattr(er.JobRegistry,'admit_cycle_plan',admit)
    app.test_authenticated_launch_uses_actual_host_paid_recipe_and_unchanged_reserve(
        rsa_key,tmp_path,short_socket_root,monkeypatch)


def _install_paid_policy(tmp_path,monkeypatch,*,allocate=True):
    policy=_policy_from_normal_service(tmp_path/'normal-factory')
    real_binding=paid._v3_execution_binding
    monkeypatch.setattr(paid,'_v3_execution_binding',lambda:dict(real_binding(),**{er.CHILD_WORKSPACE_POLICY_KEY:policy}))
    real_dispatch=er.AttemptRegistry.dispatch_cycle_job
    def dispatch(registry,job_id,**kwargs):
        job=er.JobRegistry(registry.store).get_job(job_id)
        if allocate and job.orchestration_role in {'work','review','repair'}:
            er.JobRegistry(registry.store).prepare_coo_child_workspace(job_id,
                source_repository=Path(job.worktree).parent/'control-source',shared_gid=os.getegid())
        return real_dispatch(registry,job_id,**kwargs)
    monkeypatch.setattr(er.AttemptRegistry,'dispatch_cycle_job',dispatch)


def _paid_claim(tmp_path,monkeypatch,*,allocate=True):
    _install_paid_policy(tmp_path,monkeypatch,allocate=allocate)
    return paid.paid_cycle_claim(tmp_path/'cycle')


def test_actual_paid_claim_requires_committed_child_allocator_provenance(tmp_path,monkeypatch):
    with pytest.raises(er.StateConflict,match='allocator provenance'):
        _paid_claim(tmp_path,monkeypatch,allocate=False)


def test_real_runtime_paid_claim_uses_distinct_workspace_and_same_job_replay(tmp_path,monkeypatch):
    runtime,root,job,claimed,source,body,planner=_paid_claim(tmp_path,monkeypatch)
    record=runtime.jobs.coo_child_workspace_completion(job.job_id)
    assert job.worktree!=root.worktree and record['binding']['job_id']==job.job_id
    before=runtime.jobs.get_job(job.job_id).to_dict()
    assert runtime.jobs.prepare_coo_child_workspace(job.job_id,
        source_repository=Path(job.worktree).parent/'control-source',shared_gid=os.getegid())==record
    assert runtime.jobs.get_job(job.job_id).to_dict()==before
    assert runtime.jobs.admit_cycle_plan(root.job_id,
        command_id=f'coo-cycle:{root.job_id}:admit-plan:{planner.attempt.attempt_id}')[0].to_dict()==before
    assert claimed.attempt.job_id==job.job_id and job.constraints['execution_profile_id']=='fabric.paid.glm.sealed-input.v1'


def test_actual_paid_terminal_to_independent_codex_review_clone_and_launchspec(tmp_path,monkeypatch):
    _install_paid_policy(tmp_path,monkeypatch)
    paid.test_paid_subject_real_codex_review_prompt_and_serial_worker_schedule(tmp_path/'cycle')


class _BeforeWorkDispatch(Exception): pass


def _queued_child(tmp_path,monkeypatch):
    _install_paid_policy(tmp_path,monkeypatch,allocate=False)
    real_dispatch=er.AttemptRegistry.dispatch_cycle_job
    saved={}
    def stop(registry,job_id,**kwargs):
        runtime=er.Runtime.from_store(registry.store);job=runtime.jobs.get_job(job_id)
        if job.orchestration_role=='work':
            saved.update(runtime=runtime,job=job,source=Path(job.worktree).parent/'control-source')
            raise _BeforeWorkDispatch()
        return real_dispatch(registry,job_id,**kwargs)
    monkeypatch.setattr(er.AttemptRegistry,'dispatch_cycle_job',stop)
    with pytest.raises(_BeforeWorkDispatch): paid.paid_cycle_claim(tmp_path/'cycle')
    return saved['runtime'],saved['job'],saved['source']


@pytest.mark.parametrize('fault',['existing-path','partial-after-clone','failed-before-clone','forged-return','cancel-during-clone'])
def test_unknown_partial_foreign_or_forged_allocation_is_never_adopted(tmp_path,monkeypatch,fault):
    runtime,job,source=_queued_child(tmp_path,monkeypatch)
    root=runtime.jobs.get_job(job.root_job_id);before=root.to_dict()
    real=ew.create_readonly_child_clone;calls=[]
    def allocate(*args,**kwargs):
        calls.append(1)
        if fault=='failed-before-clone': raise ew.WorkspaceError('inert failure')
        if fault=='forged-return': return {'receipt':{'workspace_path':job.worktree}}
        value=real(*args,**kwargs)
        if fault=='partial-after-clone': raise ew.WorkspaceError('lost reply after real clone')
        if fault=='cancel-during-clone': runtime.jobs.cancel_job(job.job_id)
        return value
    monkeypatch.setattr(ew,'create_readonly_child_clone',allocate)
    if fault=='existing-path': Path(job.worktree).mkdir()
    for _ in range(2):
        with pytest.raises((er.StateConflict,ew.WorkspaceError,FileExistsError)):
            runtime.jobs.prepare_coo_child_workspace(job.job_id,source_repository=source,shared_gid=os.getegid())
    assert len(calls)==1
    events=runtime.events.list_events(job_id=job.job_id)
    assert sum(e.event_type=='COO_CHILD_WORKSPACE_REQUESTED' for e in events)==1
    assert not any(e.event_type=='COO_CHILD_WORKSPACE_COMPLETED' for e in events)
    assert runtime.jobs.get_job(root.job_id).to_dict()==before
    assert runtime.jobs.get_job(job.job_id).attempt_count==0


@pytest.mark.parametrize('fault',['replace-workspace','replace-git','remote','branch','ref','dirty','source-replay'])
def test_committed_assignment_cannot_be_rebound_by_path_coincidence(tmp_path,monkeypatch,fault):
    runtime,job,source=_queued_child(tmp_path,monkeypatch)
    record=runtime.jobs.prepare_coo_child_workspace(job.job_id,source_repository=source,shared_gid=os.getegid())
    workspace=Path(job.worktree)
    if fault in {'replace-workspace','replace-git'}:
        path=workspace if fault=='replace-workspace' else workspace/'.git'
        path.chmod(0o700);path.rename(path.with_name(path.name+'-original'));path.mkdir()
    elif fault=='remote':
        path=workspace/'.git/config';path.chmod(0o600);path.write_text(path.read_text()+'\n[remote "forged"]\n url=https://example.invalid/\n');path.chmod(0o440)
    elif fault=='branch':
        path=workspace/'.git/HEAD';path.chmod(0o600);path.write_text('ref: refs/heads/forged\n');path.chmod(0o440)
    elif fault=='ref':
        path=workspace/'.git/refs/heads'/job.branch;path.chmod(0o600);path.write_text('0'*40+'\n');path.chmod(0o440)
    elif fault=='dirty':
        path=workspace/'research/commission.md';path.chmod(0o600);path.write_text('changed analysis source\n');path.chmod(0o440)
    else: source=workspace
    with pytest.raises((er.StateConflict,ew.WorkspaceError)):
        runtime.jobs.prepare_coo_child_workspace(job.job_id,source_repository=source,shared_gid=os.getegid())
    assert sum(e.event_type=='COO_CHILD_WORKSPACE_COMPLETED' for e in runtime.events.list_events(job_id=job.job_id))==1


def test_host_policy_cannot_be_caller_injected_or_attached_to_legacy_root(tmp_path,monkeypatch):
    from tests.test_executive_os_phase1fc import _v3_execution_binding
    with pytest.raises(er.StateConflict,match='host-owned'):
        er._constraints_with_host_execution_binding({er.CHILD_WORKSPACE_POLICY_KEY:er.CHILD_WORKSPACE_POLICY},_v3_execution_binding())
    # Actual old admitted fixture remains root-shared and gains no new event.
    runtime,root,job,*_=paid.paid_cycle_claim(tmp_path/'legacy')
    assert er.CHILD_WORKSPACE_POLICY_KEY not in root.constraints
    assert job.worktree==root.worktree
    assert runtime.jobs.prepare_coo_child_workspace(job.job_id,
        source_repository=Path(job.worktree),shared_gid=os.getegid()) is None
    assert runtime.jobs.prepare_coo_child_workspace(job.job_id,
        source_repository=Path(job.worktree)/'unused-legacy-source',shared_gid=None) is None
    assert not any(e.event_type.startswith('COO_CHILD_WORKSPACE_') for e in runtime.events.list_events(job_id=job.job_id))


def test_concurrent_owner_calls_reserve_once_and_never_adopt_inflight(tmp_path,monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    runtime,job,source=_queued_child(tmp_path,monkeypatch)
    entered,release=Event(),Event();calls=[];real=ew.create_readonly_child_clone
    def allocate(*args,**kwargs):
        calls.append(1);entered.set()
        assert release.wait(15)
        return real(*args,**kwargs)
    monkeypatch.setattr(ew,'create_readonly_child_clone',allocate)
    with ThreadPoolExecutor(max_workers=1) as executor:
        pending=executor.submit(runtime.jobs.prepare_coo_child_workspace,job.job_id,
            source_repository=source,shared_gid=os.getegid())
        assert entered.wait(15)
        try:
            with pytest.raises(er.StateConflict,match='unresolved'):
                runtime.jobs.prepare_coo_child_workspace(job.job_id,source_repository=source,shared_gid=os.getegid())
        finally: release.set()
        completed=pending.result(timeout=20)
    assert len(calls)==1
    assert runtime.jobs.prepare_coo_child_workspace(job.job_id,source_repository=source,
        shared_gid=os.getegid())==completed


def test_repair_clone_binds_both_actual_subject_and_rejected_review(tmp_path,monkeypatch):
    from control_plane.executive_coo_cycle import CooCycle
    import hashlib,pwd
    from tests.test_executive_os_phase1fc import _review_body
    from control_plane.executive_supervisor import ExecutiveSupervisor
    from control_plane.executive_orchestration_result import canonical_bytes
    from tests.test_executive_terminal_return import _PlannerSealedWorkerAdapter,_SEALED_WORKER_SECRET_CANARY
    from tests.test_executive_supervisor import FakeInspector,FakeProcessController
    _install_paid_policy(tmp_path,monkeypatch)
    state=paid.paid_completed(tmp_path/'cycle');runtime=state['runtime'];subject=state['completed'];root=state['root']
    cycle=CooCycle(runtime);created=cycle.run_once(root.job_id)
    review=runtime.jobs.get_job(created.selected_job_id)
    target=runtime.validated_role_completion(subject.job_id,expected_attempt_id=state['running'].attempt_id)
    body=_review_body(root_id=root.job_id,plan_attempt_id=subject.plan_attempt_id,plan_digest=subject.plan_digest,
        target_job_id=subject.job_id,target_attempt_id=target.attempt.attempt_id,
        target_result_digest=target.role_result_digest,repair_round=0,verdict='reject',plan_step_id=subject.plan_step_id)
    class RejectionAdapter(_PlannerSealedWorkerAdapter):
        async def collect_result(self,ref):
            receipt=await super().collect_result(ref)
            envelope=dict(receipt.result.structured_output,role='review',role_result=copy.deepcopy(body))
            raw=canonical_bytes(envelope);Path(ref.result_path).write_bytes(raw)
            return dataclasses.replace(receipt,result=dataclasses.replace(receipt.result,structured_output=envelope),
                result_sha256=hashlib.sha256(raw).hexdigest())
    home=tmp_path/'review-home';home.mkdir(mode=0o700)
    adapter=RejectionAdapter(FakeInspector(),root_job_id=root.job_id,provider_home=home)
    runs=tmp_path/'review-runs'
    supervisor=ExecutiveSupervisor(runtime,adapter,runs_root=runs,
        isolation_roots=(Path(root.worktree).parent,runs),worker_user=pwd.getpwuid(os.geteuid()).pw_name,
        worker_uid=os.geteuid(),worker_gid=os.getegid(),inspector=adapter.inspector,
        process_controller=FakeProcessController(adapter.inspector),
        secret_canary_verdict=_SEALED_WORKER_SECRET_CANARY,require_complete_launch_attestation=True)
    active=asyncio.run(supervisor.start_cycle_job(review.job_id,
        command_id=f'coo-cycle:{root.job_id}:dispatch:{review.job_id}:attempt:1'))
    finished=asyncio.run(supervisor.finish_job(active))
    seal=runtime.validated_role_completion(review.job_id,expected_attempt_id=finished.attempt.attempt_id)
    repair_created=cycle.run_once(root.job_id);assert repair_created.action=='REPAIR_CREATED'
    repair=runtime.jobs.get_job(repair_created.selected_job_id)
    record=runtime.jobs.prepare_coo_child_workspace(repair.job_id,
        source_repository=Path(subject.worktree).parent/'control-source',shared_gid=os.getegid())
    binding=record['binding']['subject']
    assert binding['job_id']==subject.job_id and binding['result_digest']==target.role_result_digest
    assert binding['rejected_review']['job_id']==review.job_id
    assert binding['rejected_review']['result_digest']==seal.role_result_digest
    assert len({subject.worktree,review.worktree,repair.worktree})==3


@pytest.mark.parametrize('authorities,paths,commands',[
    (['READ','WRITE_BRANCH'],['research/commission.md'],[]),
    (['READ','RUN_TESTS'],[],[['python3','-m','pytest']]),
    (['READ'],['research/commission.md'],[]),
])
def test_new_profile_refuses_write_or_test_grants_before_insertion(tmp_path,monkeypatch,authorities,paths,commands):
    runtime,job,source=_queued_child(tmp_path,monkeypatch)
    before=len(runtime.jobs.list_jobs())
    with pytest.raises(er.StateConflict,match='READ/RESEARCH only'):
        with runtime.store.transaction() as connection:
            row=connection.execute('SELECT * FROM jobs WHERE job_id=?',(job.root_job_id,)).fetchone()
            er._insert_cycle_child(connection,runtime.store,root_row=row,role='work',objective='forbidden write',
                requested_authorities=authorities,allowed_write_paths=paths,validation_commands=commands,
                cost_class='small',attempt_limit=1,review_required=True,command_id='new-profile-grant-negative',
                plan_attempt_id=job.plan_attempt_id,plan_digest=job.plan_digest,plan_step_id=job.plan_step_id,repair_round=0)
    assert len(runtime.jobs.list_jobs())==before


def test_normal_service_dispatch_owns_allocation_before_supervisor_edge(tmp_path,monkeypatch):
    real_submit=paid.submit_intent
    def submit(runtime,intent,**kwargs):
        intent=copy.deepcopy(intent)
        source=Path(intent['execution_contract']['worktree'])
        intent['execution_contract']['branch']=subprocess.check_output(
            ['git','-C',str(source),'symbolic-ref','--short','HEAD'],text=True).strip()
        return real_submit(runtime,intent,**kwargs)
    monkeypatch.setattr(paid,'submit_intent',submit)
    runtime,job,source=_queued_child(tmp_path,monkeypatch)
    root=runtime.jobs.get_job(job.root_job_id)
    normal_source=tmp_path/'normal-control-source'
    subprocess.run(['git','clone','-q','--no-hardlinks',str(source),str(normal_source)],check=True)
    service=ExecutiveControlService(_config(tmp_path/'service',runtime_root=tmp_path/'cycle',
        proof_source_repository=normal_source,proof_workspace_root=Path(job.worktree).parent,
        proof_base_sha=root.constraints['base_sha']),supervisor_factory=lambda _:object())
    service.runtime=runtime
    # Existing admitted host binding and attendance are fixture inputs only.
    # Keep real Service lineage/plan/workspace/grant validators and physical owner.
    monkeypatch.setattr(service,'_require_current_coo_binding',lambda:dict(root.constraints))
    monkeypatch.setattr(service,'_require_foreground_only_source',lambda _:None)
    class AtSupervisorBoundary(Exception): pass
    class Supervisor:
        async def start_cycle_job(self,job_id,**kwargs):
            assert job_id==job.job_id
            record=runtime.jobs.coo_child_workspace_completion(job_id)
            assert record['binding']['worktree']==job.worktree
            assert runtime.jobs.get_job(job_id).attempt_count==0
            raise AtSupervisorBoundary()
    service.supervisor=Supervisor()
    async def exercise():
        with pytest.raises(AtSupervisorBoundary):
            await service._dispatch_cycle_job_exact(job.job_id,'service-allocation-edge')
    asyncio.run(exercise())
    assert sum(e.event_type=='COO_CHILD_WORKSPACE_COMPLETED' for e in runtime.events.list_events(job_id=job.job_id))==1
