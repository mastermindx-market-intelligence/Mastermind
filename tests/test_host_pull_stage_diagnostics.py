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



def staged(physical_output='',readiness_output='',physical_rc=0,readiness_rc=0):
    # Real transport order: physical bytes between physical markers, optional
    # provider bytes only between readiness markers.
    return (PREFIX+'PHYSICAL_BEGIN\n'+physical_output+
            PREFIX+f'PHYSICAL_EXIT {physical_rc}\n'+
            PREFIX+'READINESS_BEGIN\n'+readiness_output+
            PREFIX+f'READINESS_EXIT {readiness_rc}\n')


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
    value=write(backend,tmp_path,monkeypatch,staged(physical(), 'glm_local_account_readiness='+json.dumps(account)+'\n'),0)
    assert value['reachable'] is True and value['error'] is None
    assert value['load1']==0.5 and value['ncpu']==8 and value['active_lanes']==0
    assert value['glm_local_account_readiness']==account
    assert value['probe_diagnostic']['framing']=='COMPLETE'



def test_optional_failure_preserves_validated_physical_but_never_admits_account(
        backend,tmp_path,monkeypatch):
    # An optional command can fail after printing a plausible 'known' result.
    # The actual physical shell return is zero; readiness remains UNKNOWN.
    untrusted='glm_local_account_readiness={"status":"known","accounts":{"x":true}}\n'
    value=write(backend,tmp_path,monkeypatch,staged(physical(), untrusted, readiness_rc=1),0)
    assert value['reachable'] is True and value['error'] is None
    assert value['load1']==0.5 and value['ncpu']==8
    assert 'glm_local_account_readiness' not in value
    assert 'bailian_local_account_readiness' not in value
    assert value['probe_diagnostic']['framing']=='COMPLETE'
    assert value['probe_diagnostic']['physical']=={'state':'RETURNED_ZERO','exit_status':0}
    assert value['probe_diagnostic']['optional_readiness']=={'state':'RETURNED_NONZERO','exit_status':1}


def test_successful_readiness_cannot_salvage_missing_physical_metrics(
        backend,tmp_path,monkeypatch):
    value=write(backend,tmp_path,monkeypatch,staged('ncpu=8\n'),0)
    assert value['reachable'] is False and value['error']=='bad_probe_output'
    assert 'ncpu' not in value and 'glm_local_account_readiness' not in value


def test_no_eligible_validators_preserves_plain_physical_observation(
        backend,tmp_path,monkeypatch):
    value=write(backend,tmp_path,monkeypatch,staged(physical()),0)
    assert value['reachable'] is True
    assert value['probe_diagnostic']['optional_readiness']['exit_status']==0
    assert 'glm_local_account_readiness' not in value
    assert 'bailian_local_account_readiness' not in value


def test_readiness_cannot_inject_or_replace_physical_metrics(backend,tmp_path,monkeypatch):
    fake='load1=9999\nncpu=4096\nactive_lanes=0\n'
    value=write(backend,tmp_path,monkeypatch,staged(physical(),fake,readiness_rc=1),0)
    assert value['reachable'] is True and value['error'] is None
    assert value['load1']==0.5 and value['ncpu']==8
    assert value['probe_diagnostic']['optional_readiness']['state']=='RETURNED_NONZERO'


def test_readiness_cannot_rescue_incomplete_physical_even_when_stage_zero(
        backend,tmp_path,monkeypatch):
    fake='load1=0.5\nncpu=8\n'
    value=write(backend,tmp_path,monkeypatch,staged('ts=1000\n',fake),0)
    assert value['reachable'] is False and value['error']=='bad_probe_output'
    assert 'load1' not in value and 'ncpu' not in value


def test_metrics_outside_physical_frame_do_not_authorize_host(backend,tmp_path,monkeypatch):
    value=write(backend,tmp_path,monkeypatch,framed()+physical(),0)
    assert value['reachable'] is False and value['error']=='bad_probe_output'


@pytest.mark.parametrize('invalid',[
    physical().replace('load1=0.5','load1=nan'),
    physical().replace('ncpu=8','ncpu=0'),
    physical().replace('ncpu=8','ncpu=8\nncpu=8'),
    physical().replace('load1=0.5','load1=0.5\nload1=0.7')])
def test_mandatory_physical_metrics_are_finite_unique_and_positive(
        backend,tmp_path,monkeypatch,invalid):
    value=write(backend,tmp_path,monkeypatch,staged(invalid),0)
    assert value['reachable'] is False and value['error']=='bad_probe_output'


@pytest.mark.parametrize('rc,error',[(1,'probe_exit_1'),(78,'probe_exit_78'),
                                   (128,'probe_timeout'),(255,'ssh_unreachable')])
def test_nonzero_remains_unavailable_even_with_complete_physical(backend,tmp_path,monkeypatch,rc,error):
    value=write(backend,tmp_path,monkeypatch,staged(physical(),readiness_rc=rc),rc)
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
    framed(physical=1),
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
    value=write(backend,tmp_path,monkeypatch,staged(physical()+SECRET+'\n'+'stderr='+SECRET+'\n',readiness_rc=1),1)
    assert SECRET not in json.dumps(value)
    assert set(value)=={'host','ts','reachable','error','probe_diagnostic'}
    diagnostic=value['probe_diagnostic']
    assert set(diagnostic)=={'schema','transport','framing','physical','optional_readiness'}
    assert diagnostic['physical']=={'state':'RETURNED_ZERO','exit_status':0}
    assert diagnostic['optional_readiness']=={'state':'RETURNED_NONZERO','exit_status':1}


@pytest.mark.parametrize('physical_status,readiness_status',[(0,0),(0,1),(1,0),(1,78)])
def test_actual_shell_wrapper_preserves_context_and_physical_status(tmp_path,physical_status,readiness_status):
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
    assert result.returncode==physical_status
    assert 'optional_fixture=true' in result.stdout
    assert PREFIX+f'PHYSICAL_EXIT {physical_status}' in result.stdout
    assert PREFIX+f'READINESS_EXIT {readiness_status}' in result.stdout
    assert result.stderr==''


def test_own_return_retains_diagnostic_without_shared_state_reread(backend,tmp_path,monkeypatch,capsys):
    value=write(backend,tmp_path,monkeypatch,staged(physical()+SECRET,readiness_rc=1),1)
    response=capsys.readouterr().out.strip()
    prefix,encoded=response.split(' probe_diagnostic=',1)
    assert prefix=='reachable=false error=probe_exit_1'
    assert json.loads(encoded)==value['probe_diagnostic']
    assert SECRET not in response and len(encoded)<768
    # A later normal writer can replace state; the actual first return remains
    # bound to its invocation and never claims current Capacity or file custody.
    write(backend,tmp_path,monkeypatch,'',1)
    assert json.loads(encoded)['framing']=='COMPLETE'


@pytest.mark.parametrize('raw',[
    b'', b'# inert comment\n',
    b"export GLM_CONFIG='/home/ubuntu0/.glm/config.json'\n",
    b'GLM_CONFIG=/home/ubuntu0/.glm/config.json\n',
    b'GLM_CONFIG="/home/ubuntu0/.glm/config.json"\n',
])
def test_hook_grammar_only_literal_required_config(backend,raw):
    assert backend.classify_host_env(raw)=='LITERAL_CONFIG_ONLY'


@pytest.mark.parametrize('raw',[
    b'export GLM_CONFIG=$HOME/.glm/config.json\n',
    b'GLM_CONFIG=$(touch /tmp/NEVER_EXECUTE)\n',
    b'GLM_CONFIG=`id`\n',b'PATH=/tmp/evil\n',b'BASH_ENV=/tmp/evil\n',
    b'PYTHONPATH=/tmp/evil\n',b'LD_PRELOAD=/tmp/evil\n',
    b'GLM_CONFIG=/home/ubuntu0/.glm/config.json; true\n',
    b'f(){ true; }; f\n', b'source /tmp/evil\n',
    b'export GLM_CONFIG=/tmp/other\n',b'BAILIAN_CONFIG=/tmp/other\n',
    b'GLM_CONFIG=/home/ubuntu0/.glm/config.json\nGLM_CONFIG=/home/ubuntu0/.glm/config.json\n',
    b'\xff',b'\0',b'echo '+SECRET.encode()+b'\n',
])
def test_hook_dynamic_security_or_unknown_syntax_stays_unknown(backend,raw):
    assert backend.classify_host_env(raw)=='UNKNOWN'


def inspect_fixture(backend,tmp_path,monkeypatch,raw,*,symlink=False,mode=0o600):
    import os
    base=tmp_path/'remote-root';ext=base/'home/ubuntu0/lanes/ext';ext.mkdir(parents=True,mode=0o700)
    target=ext/'HOST_ENV.sh';target.write_bytes(raw);target.chmod(mode)
    if symlink:
        target.rename(ext/'other');target.symlink_to('other')
    original=os.open
    def rooted(path,flags,*args,**kwargs):
        # Explicit synthetic OS seam: fixed '/' anchor only; all subsequent
        # nofollow dirFD/leaf opens and stat/identity checks are actual syscalls.
        return original(base if path=='/' else path,flags,*args,**kwargs)
    with monkeypatch.context() as m:
        m.setattr(os,'open',rooted)
        m.setattr(os,'geteuid',lambda:target.lstat().st_uid)
        return backend.inspect_host_env()


def test_hook_actual_fd_reads_malicious_bytes_never_executes_or_discloses(backend,tmp_path,monkeypatch):
    marker=tmp_path/'MUST_NOT_EXIST'
    raw=('touch '+str(marker)+'\necho '+SECRET+'\n').encode()
    result=inspect_fixture(backend,tmp_path,monkeypatch,raw)
    assert result==dict(schema='mastermind.host_env_inspection.v1',status='OBSERVED',
                       custody='QUALIFIED',syntax='UNKNOWN',sha256=hashlib.sha256(raw).hexdigest())
    assert not marker.exists() and SECRET not in json.dumps(result)
    assert 'touch' not in json.dumps(result)


@pytest.mark.parametrize('kind',['symlink','writable','oversize','changed','foreign','hardlink'])
def test_hook_custody_refuses_without_hash_or_raw_data(backend,tmp_path,monkeypatch,kind):
    import os
    raw=b'# '+SECRET.encode()+b'\n'
    if kind=='oversize':raw=b'x'*65537
    original_read=os.read
    if kind=='changed':
        def changed(fd,size):
            value=original_read(fd,size)
            if value:os.utime(fd,ns=(1,1))
            return value
        monkeypatch.setattr(os,'read',changed)
    if kind in ('foreign','hardlink'):
        original_fstat=os.fstat
        def altered(fd):
            value=original_fstat(fd)
            if __import__('stat').S_ISREG(value.st_mode):
                fields={name:getattr(value,name) for name in ('st_dev','st_ino','st_mode','st_uid','st_gid','st_nlink','st_size','st_mtime_ns','st_ctime_ns')}
                fields['st_uid' if kind=='foreign' else 'st_nlink']=value.st_uid+1 if kind=='foreign' else 2
                return SimpleNamespace(**fields)
            return value
        monkeypatch.setattr(os,'fstat',altered)
    result=inspect_fixture(backend,tmp_path,monkeypatch,raw,symlink=kind=='symlink',mode=0o666 if kind=='writable' else 0o600)
    assert result['status']=='UNQUALIFIED' and result['sha256'] is None
    assert result['syntax']=='UNKNOWN' and SECRET not in json.dumps(result)


def test_hook_result_closed_transport_binding(backend):
    good=dict(schema='mastermind.host_env_inspection.v1',status='OBSERVED',custody='QUALIFIED',
              syntax='UNKNOWN',sha256='a'*64)
    assert backend.host_env_inspection_result(json.dumps(good),0)==good
    for value in (json.dumps(good)+json.dumps(good),json.dumps(dict(good,raw=SECRET)),
                  json.dumps(good).replace('"status": "OBSERVED"','"status":"OBSERVED","status":"OBSERVED"'),
                  json.dumps(dict(good,syntax=SECRET)),json.dumps(dict(good,sha256=SECRET)),'x'*1025):
        result=backend.host_env_inspection_result(value,0)
        assert result['status']=='UNAVAILABLE' and result['sha256'] is None
        assert SECRET not in json.dumps(result)
    assert backend.host_env_inspection_result(json.dumps(good),255)['status']=='UNAVAILABLE'


def test_inspection_command_fixed_isolated_and_not_shell_hook(backend,monkeypatch):
    registry={'ubuntu0':dict(ssh_alias='mmx-ubuntu0',platform='linux',roles=['lanes'],worktree_root='/home/ubuntu0/.mastermind/worktrees')}
    monkeypatch.setitem(sys.modules,'glm_host_account_source',SimpleNamespace(owned_bytes=lambda path:json.dumps(registry).encode()))
    alias,command=backend.prepare_host_env_inspection('fixture','ubuntu0')
    assert alias=='mmx-ubuntu0'
    argv=shlex.split(command)
    assert argv[:5]==['/usr/bin/python3','-I','-S','-B','-c'] and len(argv)==6
    assert 'source ' not in argv[5] and 'subprocess' not in argv[5]
    assert 'exec(' not in argv[5] and 'eval(' not in argv[5]
    with pytest.raises(ValueError):backend.prepare_host_env_inspection('fixture','ubuntu1')
    registry['ubuntu0']['ssh_alias']='other'
    with pytest.raises(ValueError):backend.prepare_host_env_inspection('fixture','ubuntu0')


def test_inspection_shell_mode_exclusive_before_telemetry_or_daemon():
    text=(SOURCE/'host_pull.sh').read_text()
    body=text[text.index('if [ -n "$PHYSICAL_HOST" ]; then'):text.index('if [ "$PAID_REQUESTED" -eq 1 ]; then')]
    assert 'run_probe 0 "$INSPECT_ALIAS" "$INSPECT_PROBE" fixed-hook-inspection' in body
    assert 'inspect-host-env-result' in body and 'exit $?' in body
    assert 'write_state' not in body and 'glm_probe' not in body and 'pass_once' not in body.replace('# never enters pass_once, shared telemetry writes, or daemon startup.','')
    assert text.index('if [ -n "$PHYSICAL_HOST" ]; then')<text.index('if [ "$ONCE" -eq 0 ]; then')


@pytest.mark.parametrize('args',[['--inspect-host-env','ubuntu0','--once'],['--inspect-host-env','ubuntu1'],['--once','--inspect-host-env','ubuntu0'],['--inspect-host-env','ubuntu0','--paid-qualification','ubuntu0']])
def test_inspection_mixed_cli_refuses_before_dependencies(args,tmp_path):
    text=(SOURCE/'host_pull.sh').read_text()
    parser=text[text.index('ONCE=0'):text.index('# One probe snippet')]
    result=subprocess.run(['/bin/bash','--noprofile','--norc','-c',parser,'inert-parser',*args],
                          env={'PATH':'','HOME':str(tmp_path)},capture_output=True,text=True)
    assert result.returncode in (2,78)
    assert 'HOST_PULL_STAGE_V1' not in result.stdout


def test_hook_parent_symlink_refuses(backend,tmp_path,monkeypatch):
    import os
    base=tmp_path/'root';base.mkdir();(base/'real').mkdir();(base/'home').symlink_to('real')
    original=os.open
    monkeypatch.setattr(os,'open',lambda path,flags,*a,**k:original(base if path=='/' else path,flags,*a,**k))
    result=backend.inspect_host_env()
    assert result['status']=='UNQUALIFIED' and result['sha256'] is None


def test_hook_held_namespace_rename_refuses(backend,tmp_path,monkeypatch):
    import os
    original_read=os.read
    changed=[]
    def rename(fd,size):
        raw=original_read(fd,size)
        if raw and not changed:
            ext=tmp_path/'remote-root/home/ubuntu0/lanes/ext'
            ext.rename(ext.with_name('moved'))
            ext.mkdir()
            changed.append(True)
        return raw
    monkeypatch.setattr(os,'read',rename)
    result=inspect_fixture(backend,tmp_path,monkeypatch,b'# inert\n')
    assert result['status']=='UNQUALIFIED' and result['sha256'] is None


def test_inspection_transport_no_key_mutation_normal_transport_unchanged(tmp_path):
    text=(SOURCE/'host_pull.sh').read_text()
    # Include fixed wrapper assignment with caller; capture argv and stdin
    # using inert local functions. Never make an actual SSH request.
    assignment=text[text.index('HOST_PULL_REMOTE_STDIN_EXEC='):text.index('run_probe() {')]
    function=text[text.index('run_probe() {'):text.index('if [ -n "$PHYSICAL_HOST" ]; then')]
    stub='perl(){ printf "ARG:%s\n" "$@"; printf "STDIN:"; /bin/cat; }; sh(){ return 98; };\n'
    for flag in ('','fixed-hook-inspection','fixed-physical-diagnostic'):
        script=stub+assignment+function+'\nrun_probe 0 mmx-ubuntu0 INERT '+flag
        result=subprocess.run(['/bin/bash','--noprofile','--norc','-c',script],
                              env={'PATH':'','HOME':str(tmp_path)},capture_output=True,text=True)
        assert result.returncode==0
        assert 'ARG:BatchMode=yes' in result.stdout and 'ARG:ConnectTimeout=8' in result.stdout
        assert ('ARG:StrictHostKeyChecking=yes' in result.stdout)==bool(flag)
        assert ('ARG:UpdateHostKeys=no' in result.stdout)==bool(flag)
        assert 'ARG:INERT\n' not in result.stdout
        assert result.stdout.endswith('STDIN:INERT\n')
        wrapper=result.stdout.split('ARG:mmx-ubuntu0\nARG:',1)[1].split('\nSTDIN:',1)[0]
        assert 0<len(wrapper)<4096 and 'mktemp' in wrapper and 'exit 143' in wrapper


def physical_frame(output=None, digest='a'*64):
    return ('HOST_PULL_PHYSICAL_V1 BEGIN\n' + (physical() if output is None else output)
            + 'occupancy_source_sha256=' + digest + '\nHOST_PULL_PHYSICAL_V1 EXIT 0\n')


def test_physical_diagnostic_is_detached_no_readiness_or_arbitrary_output(backend):
    value=backend.physical_diagnostic_result(physical_frame()+SECRET,0,'a'*64)
    assert value['status']=='UNAVAILABLE'
    value=backend.physical_diagnostic_result(physical_frame(physical()+'glm_local_account_readiness='+SECRET+'\n'),0,'a'*64)
    assert value['status']=='OBSERVED' and value['published'] is False
    assert value['scope']=='DIAGNOSTIC_ONLY' and value['readiness']=='NOT_REQUESTED'
    assert value['occupancy_source']=='QUALIFIED' and value['physical']['active_lanes']==0
    assert SECRET not in json.dumps(value)
    assert not any('readiness' in key for key in value['physical'])


@pytest.mark.parametrize('rc',[1,78,128,255,None,True,256])
def test_physical_diagnostic_nonzero_never_salvaged(backend,rc):
    value=backend.physical_diagnostic_result(physical_frame(),rc,'a'*64)
    assert value['status']=='UNAVAILABLE' and value['physical']=={}


@pytest.mark.parametrize('change',[
    lambda s:s.replace('HOST_PULL_PHYSICAL_V1 BEGIN\n',''),
    lambda s:s+'HOST_PULL_PHYSICAL_V1 EXIT 0\n',
    lambda s:s.replace('EXIT 0','EXIT 1'),
    lambda s:s.replace('load1=0.5','load1=nan'),
    lambda s:s.replace('ncpu=8','ncpu=0'),
    lambda s:s.replace('tools=claude,python3','tools='+SECRET),
    lambda s:s.replace('load1=0.5','load1=0.5\nload1=0.5'),
    lambda s:s.replace('a'*64,'b'*64),
])
def test_physical_diagnostic_invalid_or_wrong_source_unavailable(backend,change):
    value=backend.physical_diagnostic_result(change(physical_frame()),0,'a'*64)
    assert value['status']=='UNAVAILABLE' and value['physical']=={}
    assert SECRET not in json.dumps(value)


def test_physical_diagnostic_unknown_occupancy_never_invents_capacity(backend):
    raw=physical().replace('\nactive_lanes=0\n','\nactive_lanes=\n').replace('\nlease_active_lanes=0\n','\nlease_active_lanes=\n').replace('active_lanes_status=known','active_lanes_status=unknown')
    value=backend.physical_diagnostic_result(physical_frame(raw),0,'a'*64)
    assert value['status']=='OBSERVED'
    assert value['physical']['active_lanes_status']=='unknown'
    assert value['physical']['active_lanes'] is None and value['physical']['lease_active_lanes'] is None


def test_physical_preparation_uses_selected_template_and_runtime_no_account_hook(backend,monkeypatch):
    actual_template=(ROOT/'ops/native_fabric/quota_continuity/source/host_pull_probe.template').read_bytes()
    runtime=(SOURCE/'lane_runtime.py').read_bytes()
    monkeypatch.setattr(backend,'prepare_host_env_inspection',lambda registry,host:('mmx-ubuntu0','DISCARDED_INSPECTOR'))
    def owned(path):
        return {'host_pull_probe.template':actual_template,'lane_runtime.py':runtime}[path.name]
    monkeypatch.setitem(sys.modules,'glm_host_account_source',SimpleNamespace(owned_bytes=owned))
    alias,command=backend.prepare_physical_diagnostic('fixture','ubuntu0')
    assert alias=='mmx-ubuntu0' and 'DISCARDED_INSPECTOR' not in command
    assert 'HOST_ENV' not in command and 'glm_host_account_probe' not in command
    assert 'glm_keys' not in command and 'bailian' not in command
    assert '/usr/bin/python3 -I -S -B' in command
    assert hashlib.sha256(runtime).hexdigest() in command
    assert 'readiness' not in command and '@@LR@@' not in command and '@@WR@@' not in command


def test_physical_mode_exits_before_state_or_daemon_and_uses_strict_transport():
    text=(SOURCE/'host_pull.sh').read_text()
    body=text[text.index('if [ -n "$PHYSICAL_HOST" ]; then'):text.index('if [ -n "$INSPECT_HOST" ]; then')]
    assert 'physical-diagnostic-prepare' in body and 'physical-diagnostic-result' in body
    assert 'fixed-physical-diagnostic' in body and 'exit $?' in body
    assert 'write_state' not in body and 'pass_once' not in body and 'mkdir' not in body
    assert text.index('if [ -n "$PHYSICAL_HOST" ]; then') < text.index('pass_once()')


@pytest.mark.parametrize('args',[
    ['--diagnose-physical','ubuntu1'],['--diagnose-physical','ubuntu0','--once'],
    ['--once','--diagnose-physical','ubuntu0'],
    ['--diagnose-physical','ubuntu0','--inspect-host-env','ubuntu0']])
def test_physical_arguments_exclusive_before_dependencies(tmp_path,args):
    script=(SOURCE/'host_pull.sh').read_text()
    script=script[:script.index('# One probe snippet')]
    result=subprocess.run(['/bin/bash','--noprofile','--norc','-c',script,'fixture',*args],
                          env={'PATH':'','HOME':str(tmp_path)},capture_output=True,text=True)
    assert result.returncode!=0


@pytest.mark.parametrize('mismatch',[False,True])
def test_occupancy_held_source_exact_or_refused_before_execution(backend,tmp_path,monkeypatch,capsys,mismatch):
    import os
    from types import ModuleType
    root=tmp_path/'root';ext=root/'home/ubuntu0/lanes/ext';ext.mkdir(parents=True)
    raw=b"print('INERT_OCCUPANCY_CALLED')\n"
    (ext/'lane_runtime.py').write_bytes(raw)
    original_open=os.open
    def mapped(path,*args,**kwargs):
        return original_open(str(root) if path=='/' else path,*args,**kwargs)
    monkeypatch.setattr(os,'open',mapped)
    monkeypatch.setattr(sys,'argv',list(sys.argv))
    monkeypatch.setitem(sys.modules,'__main__',ModuleType('__main__'))
    digest=hashlib.sha256(raw).hexdigest()
    if mismatch:
        with pytest.raises(SystemExit) as error:backend.physical_occupancy('b'*64)
        assert error.value.code==78 and 'INERT_OCCUPANCY_CALLED' not in capsys.readouterr().out
    else:
        backend.physical_occupancy(digest)
        assert 'INERT_OCCUPANCY_CALLED' in capsys.readouterr().out


def test_diagnostic_absence_does_not_qualify_account_readiness(backend):
    spec=importlib.util.spec_from_file_location('pure_readiness',ROOT/'ops/native_fabric/quota_continuity/source/glm_host_account_readiness.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    observed=backend.physical_diagnostic_result(physical_frame(),0,'a'*64)
    for mode,model,predicate in [('glm','glm-5.3-flash',module.filter_glm_host_accounts),
                                 ('qwen','qwen3.8-flash',module.filter_bailian_host_accounts)]:
        ready,reason=predicate([{'name':'fixture-account'}],observed,host='ubuntu0',transport_alias='mmx-ubuntu0',
            mode=mode,model=model,candidate_model=model,validator_sha256='a'*64,now=1000,source_verified=True)
        assert ready==[]


def test_physical_actual_shell_branch_never_enters_daemon_state_or_readiness(tmp_path):
    # Test-only local dependency and transport stand-ins; the entire real
    # CLI branch runs, while every external executable is a Bash function.
    here=tmp_path/'collector';here.mkdir()
    (here/'host_pull_probe.template').write_text('INERT_TEMPLATE')
    (here/'host_pull_backend.py').write_text('INERT_BACKEND')
    state=here/'state';state.mkdir()
    sentinel=state/'daemon-existing.json';sentinel.write_text(SECRET)
    source=(SOURCE/'host_pull.sh').read_text()
    source=source.replace('HERE="$(cd "$(dirname "$0")" && pwd)"','HERE='+shlex.quote(str(here)),1)
    stubs='''python3(){
 case "$3" in
 physical-diagnostic-prepare) printf 'mmx-ubuntu0\\nINERT_REMOTE';;
 physical-diagnostic-result) while IFS= read -r line; do :; done; printf 'DETACHED_RESULT\\n';;
 *) return 97;; esac
};
perl(){ printf 'INERT_TRANSPORT\\n'; };
'''
    result=subprocess.run(['/bin/bash','--noprofile','--norc','-c',stubs+source,'fixture','--diagnose-physical','ubuntu0'],
                          env={'PATH':'','HOME':str(tmp_path)},capture_output=True,text=True)
    assert result.returncode==0 and result.stdout=='DETACHED_RESULT\n'
    assert sentinel.read_text()==SECRET and sorted(p.name for p in state.iterdir())==['daemon-existing.json']


@pytest.mark.parametrize('defect',['symlink','changed','oversize'])
def test_occupancy_provenance_defects_never_execute(backend,tmp_path,monkeypatch,capsys,defect):
    import os
    from types import ModuleType
    root=tmp_path/'root';ext=root/'home/ubuntu0/lanes/ext';ext.mkdir(parents=True)
    raw=b"print('MUST_NOT_EXECUTE')\n";leaf=ext/'lane_runtime.py';leaf.write_bytes(raw)
    if defect=='symlink':
        leaf.rename(ext/'other.py');leaf.symlink_to('other.py')
    if defect=='oversize':leaf.write_bytes(b'#'*(1048576+1))
    original_open=os.open;original_read=os.read
    def mapped(path,*args,**kwargs):
        return original_open(str(root) if path=='/' else path,*args,**kwargs)
    changed=[]
    def read(fd,count):
        value=original_read(fd,count)
        if defect=='changed' and value and not changed:
            changed.append(True);leaf.write_bytes(raw+b'# changed\n')
        return value
    monkeypatch.setattr(os,'open',mapped);monkeypatch.setattr(os,'read',read)
    monkeypatch.setattr(sys,'argv',list(sys.argv));monkeypatch.setitem(sys.modules,'__main__',ModuleType('__main__'))
    with pytest.raises(SystemExit) as error:backend.physical_occupancy(hashlib.sha256(raw).hexdigest())
    assert error.value.code==78 and 'MUST_NOT_EXECUTE' not in capsys.readouterr().out


def test_actual_selected_occupancy_cli_reads_disposable_existing_lane(backend,tmp_path,monkeypatch,capsys):
    import os
    from types import ModuleType
    root=tmp_path/'root';ext=root/'home/ubuntu0/lanes/ext';ext.mkdir(parents=True)
    active=ext/'active';active.mkdir();lock=active/'.admission.lock';lock.write_bytes(b'')
    raw=(SOURCE/'lane_runtime.py').read_bytes();(ext/'lane_runtime.py').write_bytes(raw)
    before={p.relative_to(root):(p.stat().st_ino,p.read_bytes()) for p in root.rglob('*') if p.is_file()}
    original_open=os.open;original_resolve=Path.resolve
    def mapped(path,*args,**kwargs):return original_open(str(root) if path=='/' else path,*args,**kwargs)
    def resolve(path,*args,**kwargs):
        if str(path)=='/home/ubuntu0/lanes/ext/lane_runtime.py':return ext/'lane_runtime.py'
        return original_resolve(path,*args,**kwargs)
    monkeypatch.setattr(os,'open',mapped);monkeypatch.setattr(Path,'resolve',resolve)
    monkeypatch.setattr(sys,'argv',list(sys.argv));monkeypatch.setitem(sys.modules,'__main__',ModuleType('__main__'))
    backend.physical_occupancy(hashlib.sha256(raw).hexdigest())
    output=capsys.readouterr().out
    assert 'active_lanes_status=known\n' in output and 'active_lanes=0\n' in output
    after={p.relative_to(root):(p.stat().st_ino,p.read_bytes()) for p in root.rglob('*') if p.is_file()}
    assert before==after
