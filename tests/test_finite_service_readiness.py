"""Readiness joins and bounded protocol; never touches installed services."""
import asyncio
import copy
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
from types import SimpleNamespace

import pytest
from ops.executive_os import finite_service_lifecycle as lifecycle
from control_plane import executive_peer_identity as identity
from control_plane import darwin_process_image as images
from control_plane import executive_fabric_bridge_broker as bridge
from control_plane.executive_worker_broker import BROKER_REQUEST_SCHEMA_VERSION, PeerCredentials
from test_executive_fabric_bridge_broker import broker, Backend

SHA = 'a'*40
NONCE = 'b'*32


def request(payload=None):
    return dict(schema_version=BROKER_REQUEST_SCHEMA_VERSION, request_id='readiness-1',
                operation='service-readiness', payload={'nonce': NONCE} if payload is None else payload)


def run(service, value, uid=450):
    return asyncio.run(service.execute(value, peer=PeerCredentials(uid=uid, gid=450)))


def test_authenticated_readiness_does_not_reach_backend_or_runtime(tmp_path, monkeypatch):
    backend=Backend(); service=broker(tmp_path, monkeypatch, backend)
    monkeypatch.setattr(bridge.os, 'geteuid', lambda: service.config.bridge_uid)
    seen=[]
    def facts(config):
        assert config is service.config
        seen.append('live')
        return {'pid': 812}
    monkeypatch.setattr(lifecycle, 'bridge_readiness', facts)
    result=run(service, request())
    assert result['result']=={'pid':812, 'nonce':NONCE}
    assert backend.calls==[] and seen==['live']


@pytest.mark.parametrize('uid',[0,451,470,501])
def test_readiness_refuses_wrong_peer_before_observing_service(tmp_path,monkeypatch,uid):
    backend=Backend();service=broker(tmp_path,monkeypatch,backend)
    monkeypatch.setattr(lifecycle,'bridge_readiness',lambda config:pytest.fail('must not observe'))
    with pytest.raises(bridge.BridgeProtocolError,match='PeerAuthorizationError'):
        run(service,request(),uid)
    assert backend.calls==[]


@pytest.mark.parametrize('payload',[{}, {'nonce':None}, {'nonce':True}, {'nonce':'x'*32},
    {'nonce':NONCE+'\n'}, {'nonce':NONCE,'operation':'start'}, {'nonce':'b'*65536}, []])
def test_readiness_refuses_ambiguous_payload_before_observation(tmp_path,monkeypatch,payload):
    service=broker(tmp_path,monkeypatch)
    monkeypatch.setattr(lifecycle,'bridge_readiness',lambda config:pytest.fail('must not observe'))
    with pytest.raises(bridge.BridgeProtocolError):run(service,request(payload))
    assert service.backend.calls==[]


def test_readiness_refuses_wrong_service_principal(tmp_path,monkeypatch):
    service=broker(tmp_path,monkeypatch)
    monkeypatch.setattr(bridge.os,'geteuid',lambda:470)
    monkeypatch.setattr(lifecycle,'bridge_readiness',lambda config:pytest.fail('must not observe'))
    with pytest.raises(bridge.BridgeProtocolError,match='BridgeIdentityError'):run(service,request())
    assert service.backend.calls==[]


@pytest.mark.parametrize('ack',[NONCE.encode()+b'\n',b'c'*32+b'\n','timeout','eof'])
def test_handler_keeps_only_successful_readiness_connection_for_one_bounded_ack(tmp_path,monkeypatch,ack):
    service=broker(tmp_path,monkeypatch)
    monkeypatch.setattr(bridge.os,'geteuid',lambda:service.config.bridge_uid)
    monkeypatch.setattr(lifecycle,'bridge_readiness',lambda config:{'pid':812})
    service.peer_resolver=lambda sock:PeerCredentials(uid=450,gid=450)
    events=[]
    class Reader:
        async def readline(self):events.append('request');return json.dumps(request()).encode()+b'\n'
        async def readexactly(self,n):
            assert n==33 and events[-1]=='drain'
            events.append('ack')
            if ack=='timeout':raise asyncio.TimeoutError
            if ack=='eof':raise asyncio.IncompleteReadError(b'',33)
            return ack
    class Writer:
        def get_extra_info(self,key):assert key=='socket';return object()
        def write(self,raw):assert json.loads(raw)['ok'] is True;events.append('response')
        async def drain(self):events.append('drain')
        def close(self):events.append('close')
        async def wait_closed(self):events.append('closed')
    original=asyncio.wait_for
    async def bounded(awaitable,timeout):
        if events and events[-1]=='drain':assert timeout==5
        return await original(awaitable,timeout)
    monkeypatch.setattr(bridge.asyncio,'wait_for',bounded)
    asyncio.run(service.handle_connection(Reader(),Writer()))
    assert events==['request','response','drain','ack','close','closed']
    assert service.backend.calls==[]


@pytest.mark.parametrize('uid,pid,version,reply_pid,reply_version',[
    (501,812,22,812,22),(470,813,22,812,22),(470,812,23,812,22),
    (470,812,22,True,22),(470,812,22,812,'22')])
def test_connected_peer_join_rejects_same_uid_foreign_pid_or_exec_generation(monkeypatch,uid,pid,version,reply_pid,reply_version):
    peer=SimpleNamespace(euid=uid,pid=pid,pidversion=version)
    monkeypatch.setattr(identity,'capture_peer_identity',lambda connection:peer)
    monkeypatch.setattr(identity,'_current_capture',lambda peer:pytest.fail('mismatch must refuse first'))
    with pytest.raises(lifecycle.LifecycleError,match='connected_process_mismatch'):
        lifecycle.bind_live_peer(object(),{'pid':reply_pid,'process_instance':{'pidversion':reply_version}})


def test_connected_peer_rechecks_same_live_capture(monkeypatch):
    peer=SimpleNamespace(euid=470,pid=812,pidversion=22)
    monkeypatch.setattr(identity,'capture_peer_identity',lambda connection:peer)
    checked=[]
    monkeypatch.setattr(identity,'_current_capture',lambda actual:checked.append(actual))
    assert lifecycle.bind_live_peer(object(),{'pid':812,'process_instance':{'pidversion':22}}) is peer
    assert checked==[peer]


def test_changed_live_capture_never_yields_readiness(monkeypatch):
    peer=SimpleNamespace(euid=470,pid=812,pidversion=22)
    monkeypatch.setattr(identity,'capture_peer_identity',lambda connection:peer)
    def changed(actual):raise identity.PeerIdentityError('PEER_IDENTITY_CHANGED')
    monkeypatch.setattr(identity,'_current_capture',changed)
    with pytest.raises(identity.PeerIdentityError):
        lifecycle.bind_live_peer(object(),{'pid':812,'process_instance':{'pidversion':22}})


def fixture_observation():
    instance={'unique_id':1234,'pidversion':22,'parent_unique_id':1,'parent_pidversion':1}
    image=dict(exec_instance=instance,executable_path='/protected/python',sha256='e'*64,boot_id='boot',
               real_uid=470,effective_uid=470,real_gid=470,effective_gid=470)
    snapshot=dict(python_image='/protected/python',release_sha=SHA,manifest_sha256='c'*64,artifact_sha256={'worker.json':'d'*64})
    reply=dict(schema_version='mastermind.finite_service_readiness/v1',pid=812,process_instance=instance,
        real_uid=470,effective_uid=470,real_gid=470,effective_gid=470,supplementary_gids=[],
        kernel_peer=dict(euid=470,pid=812,pidversion=22,audit_identity_digest='f'*64),
        **{key:snapshot[key] for key in ('release_sha','manifest_sha256','artifact_sha256')})
    return image,snapshot,reply


@pytest.mark.parametrize('drift',['none','pid','peer_pid','peer_version','image_version','uid','groups','release','manifest','artifact','python','extra'])
def test_root_joins_actual_image_capture_and_protected_generation(monkeypatch,drift):
    image,snapshot,reply=fixture_observation()
    after=copy.deepcopy(image)
    if drift=='pid':reply['pid']=813
    elif drift=='peer_pid':reply['kernel_peer']['pid']=813
    elif drift=='peer_version':reply['kernel_peer']['pidversion']=23
    elif drift=='image_version':after['exec_instance']['pidversion']=23
    elif drift=='uid':reply['real_uid']=501
    elif drift=='groups':reply['supplementary_gids']=[20]
    elif drift=='release':reply['release_sha']='b'*40
    elif drift=='manifest':reply['manifest_sha256']='a'*64
    elif drift=='artifact':reply['artifact_sha256']={}
    elif drift=='python':after['executable_path']='/other/python'
    elif drift=='extra':reply['unqualified']=True
    observations=iter([image,after])
    monkeypatch.setattr(images,'inspect_owned_darwin_image',lambda pid:next(observations))
    def command(argv):
        assert argv[:5]==['/usr/bin/sudo','-u','_mastermind_exec','/usr/bin/env','-i']
        assert argv[-5:]==['--probe','--expected-sha',SHA,'--expected-manifest-sha256','c'*64]
        assert ['-I','-S','-B']==argv[argv.index(lifecycle.PYTHON)+1:argv.index(lifecycle.PYTHON)+4]
        return SimpleNamespace(stdout=json.dumps(reply).encode())
    monkeypatch.setattr(lifecycle,'checked_command',command)
    host=lifecycle.ProductionHost('c'*64);host.sha=SHA
    if drift=='none':
        assert host.readiness(snapshot,{'state':'running','pid':812})['image_sha256']=='e'*64
    else:
        with pytest.raises(lifecycle.LifecycleError,match='same_generation_readiness_mismatch'):
            host.readiness(snapshot,{'state':'running','pid':812})


@pytest.mark.skipif(sys.platform!='darwin',reason='actual Darwin audit token fixture')
def test_native_inherited_listener_after_send_identifies_child_process():
    """UID501 fixture, not launchd/service acceptance or a credential operation."""
    child_script='''import dataclasses,json,os,socket,sys
from control_plane.executive_process_identity import _observe_process_instance
listener=socket.socket(fileno=int(sys.argv[1]))
with listener.accept()[0] as connection:
    assert connection.recv(3)==b'go\\n'
    connection.sendall(json.dumps(dict(pid=os.getpid(),instance=dataclasses.asdict(_observe_process_instance(os.getpid())))).encode()+b'\\n')
    assert connection.recv(4)==b'ack\\n'
'''
    with tempfile.TemporaryDirectory(prefix='finite-peer-',dir='/private/tmp') as temp:
        path=str(Path(temp)/'socket')
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as listener:
            listener.bind(path);listener.listen(1)
            child=subprocess.Popen([sys.executable,'-c',child_script,str(listener.fileno())],
                                   pass_fds=(listener.fileno(),),stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            try:
                with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as client:
                    client.settimeout(5);client.connect(path);client.sendall(b'go\n')
                    raw=b''
                    while not raw.endswith(b'\n'):raw+=client.recv(1024)
                    reply=json.loads(raw)
                    peer=identity.capture_peer_identity(client)
                    assert peer.euid==os.geteuid() and peer.pid==child.pid==reply['pid']
                    assert peer.pid != os.getpid() and peer.pidversion==reply['instance']['pidversion']
                    identity._current_capture(peer)
                    client.sendall(b'ack\n')
                stdout,stderr=child.communicate(timeout=5)
                assert child.returncode==0,(stdout,stderr)
            finally:
                if child.poll() is None:
                    child.terminate();child.wait(timeout=5)


def test_readiness_preserves_response_ceiling(tmp_path,monkeypatch):
    service=broker(tmp_path,monkeypatch)
    monkeypatch.setattr(bridge.os,'geteuid',lambda:service.config.bridge_uid)
    monkeypatch.setattr(lifecycle,'bridge_readiness',lambda config:{'unexpectedly_large':'x'*config.max_response_bytes})
    with pytest.raises(bridge.BridgeProtocolError,match='Readiness response ceiling'):
        run(service,request())
    assert service.backend.calls==[]
