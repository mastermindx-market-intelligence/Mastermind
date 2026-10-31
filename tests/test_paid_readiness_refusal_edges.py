"""Actual finite writer/transport refusal discriminators; no host or provider."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import fcntl
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import threading
from types import SimpleNamespace

import pytest
from tests.test_paid_host_readiness import context, state, envelope, SOURCE, ROOT, OwnerMetadataFixture


def backend():
    spec=importlib.util.spec_from_file_location('edge_physical_writer',SOURCE/'host_pull_backend.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    return m


def physical(ctx):
    code=hashlib.sha256((SOURCE/'lane_runtime.py').read_bytes()).hexdigest()
    return ('HOST_PULL_PHYSICAL_V1 BEGIN\nts=1000\nload1=0\nload5=0\nncpu=32\nmem_free_gb=10\ndisk_free_gb=100\n'
        'process_active_lanes=0\nactive_lanes=0\nactive_lanes_status=known\nlease_active_lanes=0\nlease_locked_lanes=0\n'
        'lease_legacy_lanes=0\nlease_unlocked_lanes=0\ntools=python3,codex\noccupancy_source_sha256='+code+
        '\nboot_id='+ctx.binding['boot_id']+'\nHOST_PULL_PHYSICAL_V1 EXIT 0\n')


def test_real_physical_read_modify_publish_cannot_erase_interleaved_refusal(state,monkeypatch):
    m,ctx,directory,doc=state
    monkeypatch.syspath_prepend(str(ROOT/'ops/native_fabric/quota_continuity/source'))
    monkeypatch.syspath_prepend(str(SOURCE))
    import glm_host_account_source as source
    b=backend();path=directory/'ubuntu0.json'
    ready=envelope();ready['context']=ctx.binding;ready['validator_sha256']=ctx.binding['validator_sha256']
    doc['glm_local_account_readiness']=ready;path.write_bytes(m.canonical(doc))
    read_prior=threading.Event();allow_physical=threading.Event()
    read=source.owned_bytes
    def paused_read(p,**kw):
        raw=read(p,**kw)
        if Path(p)==path and threading.current_thread().name.startswith('physical'):
            read_prior.set();assert allow_physical.wait(5)
        return raw
    monkeypatch.setattr(source,'owned_bytes',paused_read)
    monkeypatch.setattr(sys,'argv',['backend',str(directory),'ubuntu0','0',physical(ctx),'mmx-ubuntu0'])
    refusal=m._refusal(ctx,now=1000)
    with ThreadPoolExecutor(max_workers=1,thread_name_prefix='physical') as physical_pool, ThreadPoolExecutor(max_workers=1,thread_name_prefix='refusal') as refusal_pool:
        physical_done=physical_pool.submit(b.write_state,physical_only=True)
        assert read_prior.wait(5)
        fd=os.open(directory,os.O_RDONLY|os.O_DIRECTORY)
        try:
            try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:locked=True
            else:
                locked=False;fcntl.flock(fd,fcntl.LOCK_UN)
        finally:os.close(fd)
        refusal_done=refusal_pool.submit(m._publish,directory,ctx,refusal)
        try:
            # Force the permitted adverse order on the preimage. Under the
            # repair the physical owner already holds the SAME kernel lock,
            # so refusal publication follows it and cannot be overwritten.
            if not locked:refusal_done.result(timeout=5)
        finally:allow_physical.set()
        physical_done.result(timeout=5);refusal_done.result(timeout=5)
    assert json.loads(path.read_bytes())['glm_local_account_readiness']==refusal
    @contextmanager
    def installed():yield ctx
    monkeypatch.setattr(m,'open_installed_context',installed)
    read_state=m._state_read;monkeypatch.setattr(m,'_state_read',lambda _:read_state(directory))
    monkeypatch.setattr(m,'_observe',lambda _:pytest.fail('erased refusal permitted another dispatch'))
    with pytest.raises(ValueError):m.refresh()


@pytest.mark.parametrize('code,error,expected',[
    (255,b'Host key verification failed.\n','REFUSED'),
    (255,b'operator@inert: Permission denied (publickey).\n','REFUSED'),
    (255,b'WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED!\n','REFUSED'),
    (1,b'INERT_SECRET_KEY_SENTINEL /private/path authentication failed\n','REFUSED'),
    (255,b'','REFUSED'),
    (137,b'','REFUSED'),
    (0,b'inert-unexpected-diagnostic\n','REFUSED'),
    (255,b'ssh: connect to host 192.0.2.1 port 22: Connection timed out\n','UNAVAILABLE'),
    (255,b'ssh: connect to host 192.0.2.1 port 22: No route to host\n','UNAVAILABLE'),
])
def test_real_bounded_transport_classifies_refusal_without_echo(context,monkeypatch,tmp_path,code,error,expected):
    m,ctx,_=context
    real_popen=subprocess.Popen
    principal=dict(uid=501,gid=os.getgid(),user='inert',home=str(tmp_path))
    monkeypatch.setattr(m,'_qualifier',lambda _:SimpleNamespace(_transport_principal=lambda:principal))
    monkeypatch.setattr(m,'os',OwnerMetadataFixture(os))
    monkeypatch.setattr(m,'sys',SimpleNamespace(platform='darwin',executable=sys.executable))
    def inert(command,**kwargs):
        assert command[0]=='/bin/bash' and command[-2:]==['--qualified-readiness-transport','ubuntu0']
        # Genuine child/pipe/selector/EOF/lifetime, explicit local transport seam.
        body='import sys\nsys.stdin.buffer.read()\nsys.stderr.buffer.write('+repr(error)+')\nsys.stdout.buffer.write('+repr(b'{}' if code==0 else b'')+')\nsys.exit('+str(code)+')'
        return real_popen([sys.executable,'-I','-S','-B','-c',body],**kwargs)
    monkeypatch.setattr(subprocess,'Popen',inert)
    exception=m.ObservationUnavailable if expected=='UNAVAILABLE' else m.ReadinessRefused
    with pytest.raises(exception) as found:m._transport(ctx,{'inert':'public request'})
    assert 'SENTINEL' not in str(found.value) and '/private/path' not in str(found.value)


@pytest.mark.parametrize('code,out,error',[
    (255,b'partial',b'ssh: connect to host 192.0.2.1 port 22: Connection timed out\n'),
    (1,b'',b'ssh: connect to host 192.0.2.1 port 22: Connection timed out\n'),
    (255,b'',b'ssh: connect to host 192.0.2.1 port 22: Connection timed out\nextra\n'),
    (255,b'',b'ssh: connect to host 192.0.2.1 port 22: Connection reset by peer\n'),
    (255,b'',b'ssh: connect to host 192.0.2.1 port 22: Connection closed\n'),
    (255,b'',b'\xff'),
    (0,b'',b''),
    (0,b'{}',b'x'*4097),
])
def test_ambiguous_or_partial_transport_is_never_retryable(context,code,out,error):
    m,_,_=context
    assert m._transport_outcome(code,out,error)=='REFUSED'


def test_real_transport_refusal_is_durable_before_restart_dispatch(state,monkeypatch):
    m,ctx,directory,doc=state
    @contextmanager
    def installed():yield ctx
    monkeypatch.setattr(m,'open_installed_context',installed)
    read=m._state_read;monkeypatch.setattr(m,'_state_read',lambda _:read(directory))
    publish=m._publish;monkeypatch.setattr(m,'_publish',lambda _,*a,**kw:publish(directory,*a,**kw))
    def refused(_):
        assert m._transport_outcome(255,b'',b'Permission denied (publickey).\n')=='REFUSED'
        m._refuse()
    monkeypatch.setattr(m,'_observe',refused)
    with pytest.raises(m.ReadinessRefused):m.refresh()
    prior=json.loads((directory/'ubuntu0.json').read_bytes())['glm_local_account_readiness']
    assert prior['status']=='refused'
    monkeypatch.setattr(m,'_observe',lambda _:pytest.fail('restart dispatched through retained refusal'))
    with pytest.raises(m.ReadinessRefused):m.refresh()
    assert json.loads((directory/'ubuntu0.json').read_bytes())['glm_local_account_readiness']==prior


def test_transport_success_and_shell_stderr_not_discarded(context):
    m,_,_=context
    assert m._transport_outcome(0,b'{}',b'')=='RETURNED'
    source=(SOURCE/'host_pull.sh').read_text()
    line=next(line for line in source.splitlines() if 'alarm 35; exec @ARGV' in line)
    assert '2>/dev/null' not in line


@pytest.mark.parametrize('failure',['constructor','timeout','stderr_limit'])
def test_transport_ambiguous_local_failure_is_held_and_child_reaped(context,monkeypatch,tmp_path,failure):
    m,ctx,_=context
    principal=dict(uid=501,gid=os.getgid(),user='inert',home=str(tmp_path))
    monkeypatch.setattr(m,'_qualifier',lambda _:SimpleNamespace(_transport_principal=lambda:principal))
    monkeypatch.setattr(m,'os',OwnerMetadataFixture(os))
    monkeypatch.setattr(m,'sys',SimpleNamespace(platform='darwin',executable=sys.executable))
    real=subprocess.Popen;children=[]
    def inert(command,**kw):
        if failure=='constructor':raise OSError('INERT_SECRET_SENTINEL /private/path')
        body=('import sys,time\nsys.stdin.buffer.read()\n'+
              ('time.sleep(20)' if failure=='timeout' else "sys.stderr.buffer.write(b'X'*8192);sys.stderr.flush()"))
        child=real([sys.executable,'-I','-S','-B','-c',body],**kw);children.append(child);return child
    monkeypatch.setattr(subprocess,'Popen',inert)
    if failure=='timeout':
        clock=iter([0,41]);monkeypatch.setattr(m,'time',SimpleNamespace(monotonic=lambda:next(clock)))
    with pytest.raises(m.ReadinessRefused) as found:m._transport(ctx,{'inert':'public'})
    assert 'SENTINEL' not in str(found.value) and '/private/path' not in str(found.value)
    for child in children:
        assert child.poll() is not None
        assert all(stream.closed for stream in (child.stdin,child.stdout,child.stderr))
