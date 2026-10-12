"""Real codec/preparer with local inert filesystem fixtures; no providers."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat

import pytest
from control_plane.executive_fabric_bridge_broker import start_request_sha256
from control_plane.executive_worker_broker import BrokerPolicy
from integrations.session_bridge.bound_launch_capture.fabric_reserved_attended_launch import prepare_reserved_attended_launch, ReservedLaunchRefused

ROOT = Path(__import__('control_plane').__file__).resolve().parents[1]
fixture_spec = importlib.util.spec_from_file_location('attended_fixture', ROOT / 'tests/test_fabric_attended_claude.py')
fixtures = importlib.util.module_from_spec(fixture_spec)
fixture_spec.loader.exec_module(fixtures)


def fixture(tmp_path):
    paths = [tmp_path / n for n in ('workspaces', 'runs', 'provider')]
    for path in paths:
        path.mkdir(mode=0o700)
    workspace, run = paths[0] / 'job-1', paths[1] / 'run-1'
    workspace.mkdir(mode=0o700); run.mkdir(mode=0o700)
    schema = run / 'input' / 'result.schema.json'
    schema.parent.mkdir(mode=0o700); schema.write_text('{}')
    policy = BrokerPolicy(control_uid=os.geteuid()+1000,
        worker_uid=os.geteuid(), worker_gid=os.getegid(), worker_user='fixture',
        worker_id='worker-1', workspace_root=paths[0], run_root=paths[1],
        provider_home=paths[2])
    def identity(path):
        st=path.lstat()
        return dict(path=str(path), device=st.st_dev, inode=st.st_ino,
                    mode=stat.S_IMODE(st.st_mode), uid=st.st_uid, gid=st.st_gid,
                    mtime_ns=st.st_mtime_ns)
    manifest=dict(schema_version='mastermind.executive_isolation_manifest/v1',
        roots=sorted([identity(paths[0]),identity(paths[1])],key=lambda x:x["path"]),
        entries=[dict(root_path=str(paths[0]),disposition='CURRENT_WORKSPACE',identity=identity(workspace)),
                 dict(root_path=str(paths[1]),disposition='CURRENT_RUN',identity=identity(run))],
        workspace_path=str(workspace), run_dir=str(run))
    spec=dict(run_id='run-1',job_id='job-1',worker_id='worker-1',workspace_path=str(workspace),
        run_dir=str(run),prompt=fixtures.PROMPT,result_schema_path=str(schema),authorities=['READ'],
        worker_user='fixture',model='glm-5.3',expected_base_sha='a'*40,
        isolation_roots=[str(paths[0]),str(paths[1])],isolation_denied_paths=[],
        isolation_manifest=manifest,isolation_manifest_sha256=hashlib.sha256(json.dumps(manifest,
            sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest(),
        effective_grant_digest='b'*64,timeout_seconds=60,cancel_grace_seconds=2)
    payload=dict(binding=dict(root_id='root-1',job_id='job-1',attempt_id='run-1',
        commission_sha256='c'*64,effective_grant_digest='b'*64),
        physical_binding_sha256='d'*64,launch_spec=spec,validation_commands=[])
    correlation=dict(schema_version='mastermind.fabric_launch_correlation/v2',
        routing_root_id='native-parent',routing_parent_run_id='native-parent',
        runtime_binding=dict(root_id='root-1',job_id='job-1',attempt_id='run-1',
          effective_grant_sha256='b'*64,commission_sha256='c'*64,
          physical_binding_sha256='d'*64,start_request_sha256=start_request_sha256(payload)))
    kw=dict(correlation=correlation,run_id='run-1',routing_root_id='native-parent',
        routing_parent_run_id='native-parent',policy=policy,binary=fixtures._binary(),
        binding=fixtures._binding(),profile=fixtures._profile(),model_class='routine',
        max_turns=3,result_schema={'type':'object'})
    return payload,kw


def test_original_request_compiles_real_closed_invocation(tmp_path, monkeypatch):
    payload,kw=fixture(tmp_path)
    monkeypatch.setenv('HOSTILE_INHERITED_VARIABLE','do-not-copy')
    prepared=prepare_reserved_attended_launch(payload,**kw)
    args=prepared.lane_runtime_arguments()
    assert args['input_text']==fixtures.PROMPT
    assert fixtures.PROMPT not in args['command']
    assert args['command'][0]=='/usr/local/bin/claude'
    assert '--safe-mode' in args['command']
    assert args['shell'] is False
    assert args['timeout']==60 and args['terminate_grace']==2
    assert args['env']['ANTHROPIC_MODEL']=='glm-5.3'
    assert 'HOSTILE_INHERITED_VARIABLE' not in args['env']
    assert 'ANTHROPIC_API_KEY' not in args['env']
    assert prepared.descriptor.preparation_only is True
    assert prepared.descriptor.start_authorized is False
    # A caller mutating one invocation must not change subsequent invocations.
    args['env']['ANTHROPIC_MODEL']='changed'
    assert prepared.lane_runtime_arguments()['env']['ANTHROPIC_MODEL']=='glm-5.3'


@pytest.mark.parametrize('field,value',[('prompt','replacement'),('model','different'),
    ('workspace_path','/elsewhere'),('authorities',['READ','RUN_TESTS']),
    ('effective_grant_digest','e'*64),('run_id','successor')])
def test_changed_request_cannot_keep_original_reservation(tmp_path,field,value):
    payload,kw=fixture(tmp_path)
    payload['launch_spec'][field]=value
    with pytest.raises(ReservedLaunchRefused,match='reserved_request_changed'):
        prepare_reserved_attended_launch(payload,**kw)


@pytest.mark.parametrize('field', ['root_id','job_id','attempt_id','commission_sha256','effective_grant_digest'])
def test_wrong_original_binding_refuses(tmp_path,field):
    payload,kw=fixture(tmp_path)
    payload['binding'][field]='wrong'
    with pytest.raises(ReservedLaunchRefused):
        prepare_reserved_attended_launch(payload,**kw)


def test_wrong_native_parent_refuses(tmp_path):
    payload,kw=fixture(tmp_path);kw['routing_parent_run_id']='another-parent'
    with pytest.raises(ReservedLaunchRefused):prepare_reserved_attended_launch(payload,**kw)


def test_correlation_without_launch_spec_is_never_an_invocation(tmp_path):
    payload,kw=fixture(tmp_path);del payload['launch_spec']
    with pytest.raises(ReservedLaunchRefused):prepare_reserved_attended_launch(payload,**kw)


@pytest.mark.parametrize('field,value',[('command',['sh','-c','bad']),('provider_home','/foreign'),
    ('worker_id','other-worker'),('model','different'),('cancel_grace_seconds',-0.5),
    ('timeout_seconds',False)])
def test_real_codec_and_preparer_enforce_even_hash_matched_input(tmp_path,field,value):
    payload,kw=fixture(tmp_path);payload['launch_spec'][field]=value
    kw['correlation']['runtime_binding']['start_request_sha256']=start_request_sha256(payload)
    with pytest.raises(ReservedLaunchRefused):prepare_reserved_attended_launch(payload,**kw)


def test_advisory_digest_may_not_replace_original_digest(tmp_path):
    payload,kw=fixture(tmp_path);payload['start_request_sha256']='0'*64
    with pytest.raises(ReservedLaunchRefused):prepare_reserved_attended_launch(payload,**kw)
