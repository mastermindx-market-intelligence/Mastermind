"""Offline framing/ordering fixtures; no installed socket or Root effect."""
import array
import asyncio
import json
import os
import socket
from types import SimpleNamespace
from pathlib import Path
import pytest
from control_plane import paid_quiesce_transport as transport
from control_plane import paid_fabric_bridge_broker as broker_module


def test_actual_local_socketpair_delivers_one_readonly_descriptor(tmp_path):
    path=tmp_path/'inert-receipt';path.write_bytes(b'not an administrative receipt')
    fd=os.open(path,os.O_RDONLY)
    left,right=socket.socketpair()
    try:
        payload=b'{"fixture":true}\n'
        left.sendmsg([payload],[(socket.SOL_SOCKET,socket.SCM_RIGHTS,array.array('i',[fd]))])
        value,received=transport._recv_fd_frame(right)
        try:
            assert value=={'fixture':True}
            assert os.pread(received,100,0)==b'not an administrative receipt'
            assert not os.get_inheritable(received)
        finally:os.close(received)
    finally:left.close();right.close();os.close(fd)


@pytest.mark.parametrize('case',['multiple','missing','truncated','unknown-first','malformed','invalid-json'])
def test_ancillary_refusal_closes_every_delivered_descriptor(tmp_path,case):
    path=tmp_path/'inert';path.write_bytes(b'no authority')
    original=os.open(path,os.O_RDONLY)
    fds=[os.dup(original),os.dup(original)]
    rights=(socket.SOL_SOCKET,socket.SCM_RIGHTS,array.array('i',fds).tobytes())
    ancillary=[rights];flags=0;wire=b'{"fixture":true}\n'
    if case=='missing':ancillary=[]
    if case=='truncated':flags=socket.MSG_CTRUNC
    if case=='unknown-first':ancillary=[(999,999,b''),rights]
    if case=='malformed':ancillary=[(socket.SOL_SOCKET,socket.SCM_RIGHTS,rights[2]+b'x')]
    if case=='invalid-json':wire=b'{broken}\n'
    class InertReceiver:
        def settimeout(self,value):assert 0<value<=5
        def recvmsg(self,*args):return wire,ancillary,flags,None
    try:
        with pytest.raises(ValueError):transport._recv_fd_frame(InertReceiver())
        if case!='missing':
            for fd in fds:
                with pytest.raises(OSError):os.fstat(fd)
    finally:
        os.close(original)
        for fd in fds:
            try:os.close(fd)
            except OSError:pass


def test_control_json_cannot_call_quiesce():
    broker=object.__new__(broker_module.PaidFabricBridgeBroker)
    broker._authorize_peer=lambda peer:None  # fixture: no live peer authorization
    broker.require_service_identity=lambda:None
    broker.config=SimpleNamespace(adapter_id='canonical-paid-fabric',max_request_bytes=100000)
    broker.backend=SimpleNamespace(service_quiesce=lambda *a,**k:pytest.fail('Control reached stop'))
    request=dict(schema_version=broker_module.BROKER_REQUEST_SCHEMA_VERSION,
        request_id='test-only',operation='service-quiesce',payload={})
    with pytest.raises(broker_module.BridgeProtocolError):asyncio.run(broker.execute(request,peer=object()))


def test_root_client_refuses_without_original_broker_context_before_socket(monkeypatch):
    monkeypatch.setattr(socket,'socket',lambda *a,**k:pytest.fail('socket opened without owner'))
    from control_plane.executive_privileged_broker import BrokerTrustError
    with pytest.raises(BrokerTrustError):transport.quiesce_paid_service('acquire','a'*40,'b'*64)


def test_backend_fence_binds_origin_and_revalidates_before_release(monkeypatch):
    """Mechanical fence state only; opaque receipt qualification tested by its owner."""
    import copy,sys,threading
    from control_plane import paid_fabric_backend as module
    from control_plane.paid_model_execution_contract import digest
    definition={'profile.json':'a'*64}
    intent=dict(request_id='original-stop',request_sha256='b'*64,release_sha='c'*40,
        expected_definition_sha256=digest(definition))
    origin=dict(stop_intent=intent,broker_process={'fixture':'original broker generation'},receipt_sha256='d'*64)
    token=object();seen=[]
    def require(authority,*,stop_intent):
        if authority is not token or stop_intent!=intent:raise ValueError('fixture refusal')
        seen.append(1);return SimpleNamespace(to_dict=lambda:copy.deepcopy(origin))
    monkeypatch.setitem(sys.modules,'control_plane.paid_stop_authority',SimpleNamespace(require_stop_authority=require))
    owner=object.__new__(module.CanonicalPaidBackend)
    owner._startup=SimpleNamespace(release_root=Path('/fixture')/('c'*40))
    owner._lock=threading.RLock();owner._stop_fence=None
    owner.service_readiness=lambda:{'definition_hashes':definition,'process':{'fixture':'same shim generation'}}
    owner._idle_for_stop=lambda:None
    with pytest.raises(ValueError):owner.service_quiesce(object(),stop_intent=intent,phase='acquire')
    assert owner._stop_fence is None
    acquired=owner.service_quiesce(token,stop_intent=intent,phase='acquire')
    assert acquired['broker_process']==origin['broker_process'] and acquired['receipt_sha256']=='d'*64
    assert len(seen)==2
    with pytest.raises(module.PaidOwnerRefused):owner.service_quiesce(token,stop_intent=intent,phase='acquire')
    saved=origin['receipt_sha256'];origin['receipt_sha256']='e'*64
    with pytest.raises(module.PaidOwnerRefused):
        owner.service_quiesce(token,stop_intent=intent,phase='revalidate',fence_id=acquired['fence_id'])
    assert owner._stop_fence==acquired
    origin['receipt_sha256']=saved
    assert owner.service_quiesce(token,stop_intent=intent,phase='revalidate',fence_id=acquired['fence_id'])==acquired
    owner.service_quiesce(token,stop_intent=intent,phase='release',fence_id=acquired['fence_id'])
    assert owner._stop_fence is None


def test_http_and_metadata_entries_remain_closed_under_held_fence(tmp_path,monkeypatch):
    import threading
    from control_plane import paid_fabric_backend as module
    from control_plane import paid_fabric_bootstrap as helper
    owner=object.__new__(module.CanonicalPaidBackend)
    owner._startup=SimpleNamespace(log_dir=tmp_path)
    owner._gateway=SimpleNamespace(_signing_key=b'inert original-owner key')
    owner._lock=threading.RLock();owner._stop_fence={'fixture':'held'}
    owner._http_active=0;owner._metadata_active=0
    owner.require_gateway=lambda value:None
    owner.require_capacity_scope=lambda *a:None
    monkeypatch.setattr(helper,'bootstrap_paid_account',lambda *a,**k:pytest.fail('GET through stop fence'))
    assert owner.enter_http_request() is False and owner._http_active==0
    scope=dict(worker_id='worker',quota_class='paid-read',account_label='selected',provider='glm',
        transport_host='ubuntu2',model='glm-5.3-flash',source_sha256='a'*64,physical_sha256='b'*64)
    with pytest.raises(module.PaidOwnerRefused):owner._quota_bootstrap_owned('status-original',scope,allow_start=True)
    assert owner._metadata_active==0
    # Its durable INTENT is conservatively UNKNOWN, rather than permission to
    # repeat the status read if a future caller removes the temporary fence.
    owner._stop_fence=None
    with pytest.raises(module.PaidOwnerRefused):owner._quota_bootstrap_owned('status-original',scope,allow_start=True)
