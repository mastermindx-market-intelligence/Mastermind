"""Real credentialless clone and actual wire-policy join; no provider or service."""
import dataclasses
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest
from control_plane import fabric_attended_assignment as assignment
from control_plane.executive_worker_broker import BrokerPolicy, _launch_spec_from_wire, _launch_spec_to_json
from control_plane.worker_execution_contract import OrchestrationLaunchSpec


def git(cwd,*args):
    return subprocess.run(['git','-C',str(cwd),*args],check=True,capture_output=True,text=True).stdout.strip()


@pytest.fixture
def case(tmp_path):
    source=tmp_path/'original';source.mkdir();git(source,'init','-q')
    (source/'source.txt').write_text('original source')
    git(source,'add','source.txt');git(source,'-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-qm','fixture')
    base=git(source,'rev-parse','HEAD')
    seat=tmp_path/'host/workers/finite';ws=seat/'jobs/workspaces';runs=seat/'jobs/runs';home=seat/'provider-home'
    for path in (ws,runs,home):path.mkdir(parents=True,mode=0o710)
    home.chmod(0o700)
    run=runs/'attempt1';run.mkdir(mode=0o770);run.chmod(0o770)
    inp=run/'input';inp.mkdir(mode=0o750)
    schema=inp/'worker-result.schema.json';schema.write_text('{}');schema.chmod(0o640)
    worker=dict(control_uid=os.getuid(),worker_uid=os.getuid()+1,worker_gid=os.getgid(),worker_id='finite',
        workspace_root=str(ws),run_root=str(runs),provider_home=str(home))
    spec=OrchestrationLaunchSpec(run_id='attempt1',job_id='job1',worker_id='finite',workspace_path=source,
        run_dir=run,result_schema_path=schema,prompt='original verified prompt',authorities=('READ',),
        worker_user='finite',expected_base_sha=base,expected_worker_uid=worker['worker_uid'],
        expected_worker_gid=worker['worker_gid'],shared_run_gid=worker['worker_gid'],
        require_secret_canary=True,effective_grant_digest='a'*64)
    job=SimpleNamespace(job_id='job1',worktree=str(source),branch='codex/fixture-assignment',constraints={'base_sha':base})
    return spec,worker,job


def test_actual_assignment_reaches_actual_broker_wire_policy(case, monkeypatch):
    spec,worker,job=case
    projected,context=assignment.prepare_assignment(spec,worker,job)
    assert spec.workspace_path==Path(job.worktree) and projected.workspace_path != spec.workspace_path
    assert projected.run_dir==spec.run_dir and projected.prompt==spec.prompt
    assert projected.result_schema_path==spec.result_schema_path
    assert projected.effective_grant_digest==spec.effective_grant_digest
    assert context=={'source_workspace':str(spec.workspace_path),'input_root':str(spec.result_schema_path.parent)}
    assert git(projected.workspace_path,'remote')==''
    assert git(projected.workspace_path,'rev-parse','HEAD')==spec.expected_base_sha
    # Only the enrolled private HOME UID is a metadata fixture; assignment
    # ownership, Git preparation, schema and manifest observations are actual.
    original_lstat=Path.lstat
    def private_home_identity(path):
        info=original_lstat(path)
        if path==Path(worker['provider_home']):
            values=list(info);values[4]=worker['worker_uid'];return os.stat_result(values)
        return info
    monkeypatch.setattr(Path,'lstat',private_home_identity)
    policy=BrokerPolicy(control_uid=worker['control_uid'],worker_uid=worker['worker_uid'],worker_gid=worker['worker_gid'],
        worker_user='finite',worker_id='finite',workspace_root=Path(worker['workspace_root']),run_root=Path(worker['run_root']),
        provider_home=Path(worker['provider_home']),require_assignment_seal=True)
    assert _launch_spec_from_wire(_launch_spec_to_json(projected),policy)==projected
    assert projected.workspace_path.stat().st_uid==worker['control_uid']
    assert projected.workspace_path.stat().st_gid==worker['worker_gid']
    assert not git(spec.workspace_path,'status','--porcelain')


@pytest.mark.parametrize('fault',['wrong_store','wrong_run','wrong_base','write','missing_group','store_writable','occupied'])
def test_invalid_or_existing_assignment_never_replaced(case,monkeypatch,fault):
    spec,worker,job=case
    if fault=='wrong_store':worker={**worker,'workspace_root':str(spec.workspace_path.parent)}
    if fault=='wrong_run':spec=dataclasses.replace(spec,run_dir=spec.run_dir.parent/'other')
    if fault=='wrong_base':spec=dataclasses.replace(spec,expected_base_sha='b'*40)
    if fault=='write':spec=dataclasses.replace(spec,authorities=('WRITE',))
    if fault=='missing_group':
        monkeypatch.setattr(assignment.os,'getgroups',lambda:[])
        monkeypatch.setattr(assignment.os,'getegid',lambda:worker['worker_gid']+1)
    if fault=='store_writable':Path(worker['workspace_root']).chmod(0o770)
    destination=Path(worker['workspace_root'])/spec.run_id
    marker=None
    if fault=='occupied':
        destination.mkdir();marker=destination/'retained';marker.write_text('original')
    with pytest.raises(Exception):assignment.prepare_assignment(spec,worker,job)
    if marker is not None:assert marker.read_text()=='original'
    else:assert not destination.exists()
