"""Credentialless pure/OS primitive tests. Linux execution is CI-only here."""
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import venv

import pytest
from ops.native_fabric.quota_continuity.candidate import paid_initializer as m


def commitment():
    return dict(schema_version=m.SCHEMA,host_ref='ubuntu2',transport_alias='ubuntu2',
        lane_root='/home/worker/lanes',account=dict(uid=1000,gid=1000,user='worker',home='/home/worker'),
        bootstrap_python=dict(path='/usr/bin/python3',real_path='/usr/bin/python3.12',sha256='a'*64),
        launch_python=dict(path='/usr/bin/python3',real_path='/usr/bin/python3.12',sha256='a'*64),
        host_env=dict(path='/home/worker/lanes/ext/HOST_ENV.sh',sha256='b'*64,size=64,uid=1000,gid=1000,mode=0o600),
        initialized_context=dict(home='/home/worker',glm_config='/home/worker/lanes/ext/glm.json'),
        initialization_contract=m.CONTRACT,purpose=m.PURPOSE,
        startup=dict(profile='cpython-3.12-linux-root-prefix.v1',prefix='/usr',exec_prefix='/usr',base_prefix='/usr',base_exec_prefix='/usr'))


def selectors():return dict(host_ref='ubuntu2',transport_alias='ubuntu2',python_path='/usr/bin/python3',capture_root='/home/worker/lanes/ext/lanes')


def test_closed_commitment_is_detached_expected_input():
    value=commitment();raw=m.canonical(value);proved=m.decode_commitment(raw,hashlib.sha256(raw).hexdigest(),**selectors())
    assert proved==value and proved is not value
    value['account']['user']='mutated';assert proved['account']['user']=='worker'


@pytest.mark.parametrize('field,value',[(k,v) for k in ('host_ref','transport_alias') for v in ('-option','üser',None,True)]+[
    ('purpose','worker-start'),('initialization_contract','source-path'),('lane_root','/x/../lanes'),
    ('lane_root','//home/worker/lanes'),('startup',{}),('unknown','value')])
def test_bad_closed_input_refuses(field,value):
    c=commitment();c[field]=value
    with pytest.raises(m.InitializerCommitmentRefused):m.validate_commitment(c,**selectors())


@pytest.mark.parametrize('section,key,value',[
    ('account','uid',True),('account','gid',-1),('host_env','mode',0o622),('host_env','size',65537),
    ('host_env','sha256','newly-observed'),('bootstrap_python','path','python3'),
    ('launch_python','path','/home/worker/python3'),('initialized_context','home','/other'),
    ('initialized_context','glm_config','/a/../secret'),('startup','profile','mutable-venv'),
    ('startup','prefix','relative')])
def test_context_and_identity_mutation_refuses(section,key,value):
    c=commitment();c[section][key]=value
    with pytest.raises(m.InitializerCommitmentRefused):m.validate_commitment(c,**selectors())


@pytest.mark.parametrize('raw',[b'{}',b'{"a":1,"a":2}',b'{"a":NaN}',b'[]',b'x'*16385])
def test_raw_commitment_refuses(raw):
    with pytest.raises(m.InitializerCommitmentRefused):m.decode_commitment(raw,hashlib.sha256(raw).hexdigest(),**selectors())


def test_different_input_digest_is_not_approval():
    with pytest.raises(m.InitializerCommitmentRefused):m.decode_commitment(m.canonical(commitment()),'f'*64,**selectors())


@pytest.mark.skipif(sys.platform!='linux',reason='requires actual Linux memfd sealing')
def test_hook_snapshot_cannot_change_after_approval_even_when_original_changes(tmp_path):
    original=tmp_path/'HOST_ENV.sh';raw=b'export MM_INERT_APPROVED=exact\n';original.write_bytes(raw)
    fd=m.sealed_snapshot(original.read_bytes())
    try:
        original.write_bytes(b'echo wrong\n')
        for operation in (lambda:os.write(fd,b'x'),lambda:os.ftruncate(fd,0)):
            with pytest.raises(OSError):operation()
        result=subprocess.run(['/bin/bash','--noprofile','--norc','-c',f'source /proc/self/fd/{fd}; printf %s "$MM_INERT_APPROVED"'],
            pass_fds=(fd,),capture_output=True,check=True)
        assert result.stdout==b'exact'
    finally:os.close(fd)


@pytest.mark.skipif(sys.platform!='linux' or sys.version_info[:2]!=(3,12),reason='requires actual Linux CPython3.12 fd-exec/getpath')
def test_actual_pinned_image_exec_matches_normal_isolated_venv_startup(tmp_path):
    """Kernel image, argv0 and venv configuration are separate observations."""
    root=tmp_path/'venv';venv.EnvBuilder(with_pip=False).create(root)
    logical=root/'bin/python3';real=logical.resolve(strict=True)
    code='import json,os,sys;print(json.dumps(dict(executable=sys.executable,prefix=sys.prefix,exec_prefix=sys.exec_prefix,base_prefix=sys.base_prefix,base_exec_prefix=sys.base_exec_prefix,kernel=os.path.realpath("/proc/self/exe"),flags=[sys.flags.isolated,sys.flags.no_site,sys.dont_write_bytecode])))'
    normal=subprocess.check_output([str(logical),'-I','-S','-B','-c',code])
    fd=os.open(real,os.O_RDONLY|os.O_NOFOLLOW)
    try:
        by_fd=subprocess.check_output([str(logical),'-I','-S','-B','-c',code],executable=f'/proc/self/fd/{fd}',pass_fds=(fd,))
        assert json.loads(by_fd)==json.loads(normal)
        assert json.loads(by_fd)['kernel']==str(real)
        # argv0 may label startup DATA, but cannot alter the held kernel image.
        foreign=tmp_path/'foreign-python3'
        foreign.symlink_to(real)
        changed=subprocess.check_output([str(foreign),'-I','-S','-B','-c',code],executable=f'/proc/self/fd/{fd}',pass_fds=(fd,))
        assert json.loads(changed)['kernel']==str(real)
        assert json.loads(changed)['executable']!=str(logical)
    finally:os.close(fd)


@pytest.mark.skipif(sys.platform!='linux' or sys.version_info[:2]!=(3,12),reason='requires actual Linux CPython3.12 initializer/getpath')
def test_actual_linux_initializer_exec_and_selector_drift_before_hook(tmp_path,monkeypatch):
    """Real FD/snapshot/Bash/getpath; Root distribution ownership is simulated.

    No remote/system mutation, credential read or provider is used. This does
    not qualify the current host's package ownership/trust or a live hook.
    """
    import pwd
    import tempfile
    from tests import test_paid_host_qualification as qualifier
    if os.getuid()==0:pytest.skip('production qualifier requires a non-Root transport account')
    account=pwd.getpwuid(os.getuid())
    logical=Path(sys.executable).with_name('python3')
    assert logical.exists()
    real=logical.resolve()
    observed=json.loads(subprocess.check_output([str(logical),'-I','-S','-B','-c',
        'import json,sys;print(json.dumps({k:getattr(sys,k) for k in ("prefix","exec_prefix","base_prefix","base_exec_prefix")}))']))
    rawstat=os.stat;rawfstat=os.fstat;rawlstat=os.lstat
    protected=[str(real),str(logical.parent),*set(observed.values())]
    def distribution(name):
        return any(str(name)==p or str(name).startswith(p+'/') for p in protected)
    def root_view(info):
        fields=list(info);fields[4]=0
        return os.stat_result(fields)
    def owned_fstat(fd):
        info=rawfstat(fd)
        try:name=os.path.realpath('/proc/self/fd/'+str(fd))
        except OSError:return info
        return root_view(info) if distribution(name) else info
    def owned_stat(name,*args,**kwargs):
        info=rawstat(name,*args,**kwargs)
        if kwargs.get('dir_fd') is not None:
            name=os.path.join(os.readlink('/proc/self/fd/'+str(kwargs['dir_fd'])),str(name))
        return root_view(info) if distribution(name) else info
    def owned_lstat(name,*args,**kwargs):
        info=rawlstat(name,*args,**kwargs)
        return root_view(info) if distribution(name) else info
    with tempfile.TemporaryDirectory(prefix='.mmx-inert-init-',dir=account.pw_dir) as scratch:
        lane=Path(scratch)/'lanes';(lane/'ext/lanes').mkdir(parents=True,mode=0o700)
        hook=lane/'ext/HOST_ENV.sh';config=Path(scratch)/'not-read.json'
        hook.write_text('export GLM_CONFIG='+str(config)+'\n');hook.chmod(0o600)
        c=commitment();c.update(lane_root=str(lane),account=dict(uid=os.getuid(),gid=os.getgid(),user=account.pw_name,home=account.pw_dir),
            bootstrap_python=dict(path=str(logical),real_path=str(real),sha256=hashlib.sha256(real.read_bytes()).hexdigest()),
            launch_python=dict(path=str(logical),real_path=str(real),sha256=hashlib.sha256(real.read_bytes()).hexdigest()),
            startup=dict(profile='cpython-3.12-linux-root-prefix.v1',**observed),
            host_env=dict(path=str(hook),sha256=hashlib.sha256(hook.read_bytes()).hexdigest(),size=hook.stat().st_size,uid=os.getuid(),gid=os.getgid(),mode=0o600),
            initialized_context=dict(home=account.pw_dir,glm_config=str(config)))
        req=qualifier.request();req.update(python_path=str(logical),capture_root=str(lane/'ext/lanes'),initializer_commitment=c,
            initializer_commitment_sha256=hashlib.sha256(m.canonical(c)).hexdigest())
        # Explicit metadata-only Root distribution seam; actual child/process/
        # image/getpath/Bash/immutable FD and protocol validators stay real.
        monkeypatch.setattr(os,'fstat',owned_fstat);monkeypatch.setattr(os,'stat',owned_stat);monkeypatch.setattr(os,'lstat',owned_lstat)
        monkeypatch.setenv('HOME',account.pw_dir)
        result=json.loads(m.run_bootstrap(req,qualifier.m._REMOTE_PROBE))
        assert result['binary']['real_path']==str(real)
        assert result['pre_execution']['snapshot_sealed'] is True
        assert result['context_identity']['host_env_sha256']==c['host_env']['sha256']
        assert not config.exists()  # Selector was compared, never opened/read.
        # Unsupported startup projection refuses before the approved hook body.
        marker=Path(scratch)/'must-not-exist'
        hook.write_text('echo effect > '+str(marker)+'\nexport GLM_CONFIG='+str(config)+'\n')
        c['host_env'].update(sha256=hashlib.sha256(hook.read_bytes()).hexdigest(),size=hook.stat().st_size)
        c['startup']['prefix']='/not-the-observed-prefix'
        req['initializer_commitment_sha256']=hashlib.sha256(m.canonical(c)).hexdigest()
        with pytest.raises(m.InitializerCommitmentRefused):m.run_bootstrap(req,qualifier.m._REMOTE_PROBE)
        assert not marker.exists()
