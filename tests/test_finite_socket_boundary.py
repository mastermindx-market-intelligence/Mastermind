import json
import stat
from types import SimpleNamespace
import pytest
from control_plane import executive_peer_identity as identity
from control_plane.executive_worker_broker import BROKER_RESPONSE_SCHEMA_VERSION

from ops.executive_os import finite_service_lifecycle as l


def fixture(monkeypatch, change='none'):
    uid=451 if change=='uid' else 450
    for name in ('getuid','geteuid','getgid','getegid'):monkeypatch.setattr(l.os,name,lambda:uid)
    initial=SimpleNamespace(st_dev=1,st_ino=2,st_mode=stat.S_IFSOCK|0o660,st_uid=0,st_gid=450,
            st_nlink=1,st_size=0,st_mtime_ns=3,st_ctime_ns=4)
    if change=='type':initial.st_mode=stat.S_IFLNK|0o660
    if change=='owner':initial.st_uid=450
    if change=='group':initial.st_gid=0
    if change=='mode':initial.st_mode=stat.S_IFSOCK|0o666
    if change=='links':initial.st_nlink=2
    late=SimpleNamespace(**vars(initial))
    if change=='inode':late.st_ino+=1
    observations=iter([initial,late])
    path=SimpleNamespace(lstat=lambda:next(observations));monkeypatch.setattr(l,'Path',lambda _:path)
    stages=[]
    def acl(path,info):
        stages.append('acl')
        if (change=='acl_early' and stages.count('acl')==1) or (change=='acl_late' and stages.count('acl')==2):
            raise l.LifecycleError('socket_allocated_acl')
    monkeypatch.setattr(l,'socket_acl_absent',acl)
    peer=SimpleNamespace(euid=470,pid=812,pidversion=22,audit_identity_digest='a'*64)
    monkeypatch.setattr(l,'bind_live_peer',lambda *a:peer)
    monkeypatch.setattr(identity,'_current_capture',lambda p:stages.append('peer'))
    class Connection:
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def settimeout(self,n):assert n==5
        def connect(self,p):stages.append('connect')
        def sendall(self,raw):
            if raw.startswith(b'{'):self.request=json.loads(raw);stages.append('request')
            else:stages.append('ack')
        def recv(self,n):
            return json.dumps(dict(schema_version=BROKER_RESPONSE_SCHEMA_VERSION,
                request_id=self.request['request_id'],operation='service-readiness',ok=True,
                result=dict(nonce=self.request['payload']['nonce'],pid=812))).encode()+b'\n'
    import socket
    monkeypatch.setattr(socket,'socket',lambda *a:Connection())
    return stages


def test_actual_probe_calls_socket_observer_before_connect_and_before_ack(monkeypatch):
    stages=fixture(monkeypatch)
    out=l.probe_socket()
    assert out['kernel_peer']['euid']==470
    assert stages==['acl','connect','request','acl','peer','ack']


@pytest.mark.parametrize('change',['uid','type','owner','group','mode','links','acl_early'])
def test_unsafe_initial_socket_never_connects(monkeypatch,change):
    stages=fixture(monkeypatch,change)
    with pytest.raises(l.LifecycleError):l.probe_socket()
    assert 'connect' not in stages


@pytest.mark.parametrize('change',['inode','acl_late'])
def test_late_socket_change_never_acknowledges_readiness(monkeypatch,change):
    stages=fixture(monkeypatch,change)
    with pytest.raises(l.LifecycleError):l.probe_socket()
    assert 'connect' in stages and 'ack' not in stages
