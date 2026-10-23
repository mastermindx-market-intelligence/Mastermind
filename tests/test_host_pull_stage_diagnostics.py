"""Inert host-pull framing only; no host, provider, config or daemon execution."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shlex
import socket
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'ops/native_fabric/quota_continuity/candidate'
PREFIX = 'HOST_PULL_STAGE_V1 '
SECRET = 'INERT_SECRET_SENTINEL_NEVER_RETAIN'


@pytest.fixture(autouse=True)
def boundary(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError('network is forbidden in inert host-pull tests')
    monkeypatch.setattr(socket, 'create_connection', refuse)
    original = subprocess.Popen
    def inert_only(argv, *args, **kwargs):
        env = kwargs.get('env') or {}
        assert isinstance(argv, list) and argv[:4] == ['/bin/bash', '--noprofile', '--norc', '-c']
        assert set(env) == {'PATH', 'HOME'} and env['PATH'] == ''
        return original(argv, *args, **kwargs)
    monkeypatch.setattr(subprocess, 'Popen', inert_only)


@pytest.fixture
def backend():
    spec = importlib.util.spec_from_file_location('inert_host_pull_backend', SOURCE/'host_pull_backend.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def framed(physical=0, readiness=0):
    return (PREFIX+'PHYSICAL_BEGIN\n'+PREFIX+f'PHYSICAL_EXIT {physical}\n'+
            PREFIX+'READINESS_BEGIN\n'+PREFIX+f'READINESS_EXIT {readiness}\n')


def physical():
    return ('ts=1000\nload1=0.5\nload5=0.25\nncpu=8\nmem_free_gb=6\n'
            'disk_free_gb=90\nprocess_active_lanes=0\nactive_lanes=0\n'
            'active_lanes_status=known\nlease_active_lanes=0\nlease_locked_lanes=0\n'
            'lease_legacy_lanes=0\nlease_unlocked_lanes=0\ntools=claude,python3\n')


def write(backend, tmp_path, monkeypatch, output, rc):
    directory = tmp_path/'observations';directory.mkdir(mode=0o700, exist_ok=True)
    with monkeypatch.context() as m:
        m.setattr(sys,'argv',['backend',str(directory),'fixture-host',str(rc),output,'fixture-alias'])
        m.setattr(time,'time',lambda:1000)
        # No validator imports or original files; these bytes are DATA fixtures.
        m.setitem(sys.modules,'glm_host_account_source',SimpleNamespace(owned_bytes=lambda path:b'inert validator'))
        backend.write_state()
    return json.loads((directory/'fixture-host.json').read_bytes())


def test_success_retains_physical_and_account_observation(backend,tmp_path,monkeypatch):
    account={'schema':'mastermind.glm_local_account_readiness.v1','host':'fixture-host',
             'transport_alias':'fixture-alias','mode':'glm','config_scope':'launcher_glm_config.v1',
             'validator_sha256':hashlib.sha256(b'inert validator').hexdigest(),
             'observed_at':1000,'status':'known','accounts':{'fixture-account':True}}
    value=write(backend,tmp_path,monkeypatch,framed()+physical()+
                'glm_local_account_readiness='+json.dumps(account)+'\n',0)
    assert value['reachable'] is True and value['error'] is None
    assert value['load1']==0.5 and value['ncpu']==8 and value['active_lanes']==0
    assert value['glm_local_account_readiness']==account
    assert value['probe_diagnostic']['framing']=='COMPLETE'


@pytest.mark.parametrize('rc,error',[(1,'probe_exit_1'),(78,'probe_exit_78'),
                                   (128,'probe_timeout'),(255,'ssh_unreachable')])
def test_nonzero_remains_unavailable_even_with_complete_physical(backend,tmp_path,monkeypatch,rc,error):
    value=write(backend,tmp_path,monkeypatch,framed(readiness=rc)+physical(),rc)
    assert value['reachable'] is False and value['error']==error
    assert 'load1' not in value and 'tools' not in value
    assert value['probe_diagnostic']['transport']['exit_status']==rc


@pytest.mark.parametrize('suffix',[ '', PREFIX+'PHYSICAL_BEGIN\n',
    PREFIX+'PHYSICAL_BEGIN\n'+PREFIX+'PHYSICAL_EXIT 0\n',
    PREFIX+'PHYSICAL_BEGIN\n'+PREFIX+'PHYSICAL_EXIT 0\n'+PREFIX+'READINESS_BEGIN\n'])
def test_missing_partial_frames_fail_closed(backend,tmp_path,monkeypatch,suffix):
    value=write(backend,tmp_path,monkeypatch,physical()+suffix,0)
    assert value['reachable'] is False and value['error']=='probe_diagnostic_invalid'
    assert value['probe_diagnostic']['framing'] in ('MISSING','INCOMPLETE')


@pytest.mark.parametrize('frame',[
    framed()+PREFIX+'READINESS_EXIT 0\n',
    framed().replace('PHYSICAL_EXIT 0','PHYSICAL_EXIT +0'),
    framed().replace('PHYSICAL_EXIT 0','PHYSICAL_EXIT ０'),
    framed().replace('PHYSICAL_EXIT 0','PHYSICAL_EXIT 256'),
    framed().replace('PHYSICAL_EXIT 0','PHYSICAL_EXIT -1'),
    framed().replace('PHYSICAL_EXIT 0','PHYSICAL_EXIT 00'),
    framed().replace('PHYSICAL_EXIT 0','PHYSICAL_EXIT '+SECRET),
    framed().replace('PHYSICAL_BEGIN','READINESS_BEGIN'),
    framed(readiness=1),
    framed()+PREFIX+SECRET+'\n'])
def test_malformed_duplicate_inconsistent_frames_fail_closed(backend,tmp_path,monkeypatch,frame):
    value=write(backend,tmp_path,monkeypatch,physical()+frame,0)
    assert value['reachable'] is False and value['error']=='probe_diagnostic_invalid'
    assert value['probe_diagnostic']['framing']=='INVALID'
    assert SECRET not in json.dumps(value)


@pytest.mark.parametrize('rc',['-1','256','+0','０',SECRET])
def test_invalid_transport_status_is_bounded_unknown(backend,tmp_path,monkeypatch,rc):
    value=write(backend,tmp_path,monkeypatch,physical()+framed(),rc)
    assert value['reachable'] is False and value['error']=='probe_status_invalid'
    assert value['probe_diagnostic']['transport']=={'state':'UNKNOWN','exit_status':None}
    assert SECRET not in json.dumps(value)


def test_failure_diagnostic_never_copies_arbitrary_output(backend,tmp_path,monkeypatch):
    value=write(backend,tmp_path,monkeypatch,framed(readiness=1)+physical()+SECRET+'\n'+
                'stderr='+SECRET+'\n',1)
    assert SECRET not in json.dumps(value)
    assert set(value)=={'host','ts','reachable','error','probe_diagnostic'}
    diagnostic=value['probe_diagnostic']
    assert set(diagnostic)=={'schema','transport','framing','physical','optional_readiness'}
    assert diagnostic['physical']=={'state':'RETURNED_ZERO','exit_status':0}
    assert diagnostic['optional_readiness']=={'state':'RETURNED_NONZERO','exit_status':1}


@pytest.mark.parametrize('physical_status,readiness_status',[(0,0),(0,1),(1,0),(1,78)])
def test_actual_shell_wrapper_preserves_context_and_last_status(tmp_path,physical_status,readiness_status):
    source=(SOURCE/'host_pull.sh').read_text()
    start=source.index('    probe="printf')
    end=source.index('\n    OUT=$(run_probe',start)
    assignment=source[start:end]
    body=f'PRESERVED=fixture; printf "load1=0\\nncpu=8\\n"; (exit {physical_status})'
    auxiliary=f'test "$PRESERVED" = fixture || exit 99; printf "optional_fixture=true\\n"; (exit {readiness_status})'
    env={'PATH':'','HOME':str(tmp_path)}
    build='probe='+shlex.quote(body)+'\nglm_probe='+shlex.quote(auxiliary)+'\n'+assignment+'\nprintf "%s" "$probe"'
    generated=subprocess.run(['/bin/bash','--noprofile','--norc','-c',build],env=env,
                             capture_output=True,text=True,check=True).stdout
    result=subprocess.run(['/bin/bash','--noprofile','--norc','-c',generated],env=env,
                          capture_output=True,text=True)
    assert result.returncode==readiness_status
    assert 'optional_fixture=true' in result.stdout
    assert PREFIX+f'PHYSICAL_EXIT {physical_status}' in result.stdout
    assert PREFIX+f'READINESS_EXIT {readiness_status}' in result.stdout
    assert result.stderr==''


def test_own_return_retains_diagnostic_without_shared_state_reread(backend,tmp_path,monkeypatch,capsys):
    value=write(backend,tmp_path,monkeypatch,framed(readiness=1)+physical()+SECRET,1)
    response=capsys.readouterr().out.strip()
    prefix,encoded=response.split(' probe_diagnostic=',1)
    assert prefix=='reachable=false error=probe_exit_1'
    assert json.loads(encoded)==value['probe_diagnostic']
    assert SECRET not in response and len(encoded)<768
    # A later normal writer can replace state; the actual first return remains
    # bound to its invocation and never claims current Capacity or file custody.
    write(backend,tmp_path,monkeypatch,'',1)
    assert json.loads(encoded)['framing']=='COMPLETE'
