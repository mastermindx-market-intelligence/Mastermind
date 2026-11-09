"""Actual Control/Runtime/Event + root branch join with declared Linux fixture.

Only kernel/installed-service qualification, SSH enrollment/exchange and Linux
issuer response are inert source fixtures. The prior source-issuer component
also assumes current paid admission; test_protected_memory_execution exercises
the new join with real temporary OperatorOwner/Broker/ledger instead. No fixture authenticates deployed
source, provider identity, actual service enrollment, scientific rights or study.
"""
import copy
import hashlib
import json
import pytest

from common import memory_native_wire as wire
from control_plane import memory_native_issuer as facade
from control_plane import executive_memory_issuer as root
from control_plane import protected_memory_peer as peer
from tests.test_native_memory_admission import claimed
from tests.test_protected_memory_peer import installed, prepare
from tests.test_memory_native_wire import response, frame, rawpacket


@pytest.fixture
def joined(claimed,installed,monkeypatch):
    runtime,job,lease=claimed
    intent,_=prepare(runtime,lease,installed[0],monkeypatch)
    from control_plane import protected_memory_economic_owner as economic
    def paid_component_premise(value,request):
        peer.require_protected_memory_intent(value)
        assert request=={'action':'current','arguments':{}}
        return {'phase':'RESERVED'}
    monkeypatch.setattr(economic,'execute',paid_component_premise)
    count={'source':0,'actions':[],'pending':False,'absent':False,'unknown':False,'withdraw':False}
    projection=peer._CONTROL_ISSUED[intent].original
    fingerprint=response({'schema':'research_factory.market_memory_e0_native_issuer_request.v2','action':'prepare_case',
        'operation_id':'x','intent':{}})['issuer']['broker_service_fingerprint']
    transport=wire.canonical({'memory_native_issuer':{'schema':'mastermind.fixed_memory_issuer_transport.v1',
        'protocol':'memory.e0.native_issuer.v2','service_key_fingerprint':fingerprint,'known_hosts_sha256':'a'*64}})
    monkeypatch.setattr(root,'_enrollment',lambda observed:(transport,fingerprint,b'known',('root-owned-key-metadata',)))
    def exchange(raw):
        request=wire.decode_request(raw);count['actions'].append(request['action'])
        # Real Events are inspected BEFORE the fixed transport seam.
        assert any(e.event_type=='MEMORY_PREPARE_ATTEMPT' for e in runtime.events.list_events())
        if request['action']=='prepare_case':count['source']+=1
        if count['unknown'] and request['action']=='prepare_case':raise root.IssuerExchangeUnknown()
        value=response(request,'ABSENT' if count['absent'] else 'PENDING' if count['pending'] else 'COMPLETE')
        if count['withdraw']:
            with runtime.store.transaction() as con:
                con.execute("UPDATE jobs SET status='CANCELLED' WHERE job_id=?",(job.job_id,))
        return frame(value)
    monkeypatch.setattr(root,'_exchange',exchange)
    def send(value):
        monkeypatch.setattr(peer.os,'geteuid',lambda:0)
        try:return root.handle_memory_exchange(json.loads(wire.canonical(value)),installed[0])
        finally:monkeypatch.setattr(peer.os,'geteuid',lambda:450)
    monkeypatch.setattr(facade,'_send',send)
    monkeypatch.setattr(peer.os,'geteuid',lambda:450)
    return runtime,job,lease,intent,count


def test_actual_root_branch_and_original_events_current_input_and_result_join(joined):
    runtime,job,lease,intent,c=joined
    cap=facade.prepare_case(intent)
    assert facade.current_input(cap,intent)==rawpacket()
    assert c['source']==1
    auth=facade.authorize_result_disclosure(cap,intent,lease.attempt.attempt_id,
        hashlib.sha256(rawpacket()).hexdigest(),{'sha256':'b'*64,'bytes':12})
    assert auth['purpose']=='disclose_exact_original_untrusted_child_result'
    assert c['actions']==['prepare_case','current_input','authorize_result_disclosure']
    assert len(runtime.jobs.list_jobs())==1
    assert sum(e.event_type=='MEMORY_PREPARE_ATTEMPT' for e in runtime.events.list_events())==1
    assert not list(runtime.store.root.glob('**/*.operator-packet'))


def test_lost_prepare_uses_read_original_and_never_new_prepare(joined):
    _,_,_,intent,c=joined;c['unknown']=True
    with pytest.raises(facade.NativeCaseUnknown):facade.prepare_case(intent)
    c['unknown']=False
    state,cap=facade.read_original_case(intent)
    assert state=='COMPLETE' and cap is not None
    with pytest.raises(facade.NativeCaseUnknown):facade.prepare_case(intent)
    assert c['actions']==['prepare_case','read_original_case'] and c['source']==1


def test_pending_recovery_is_body_free_no_source_reload_or_refund(joined):
    _,_,_,intent,c=joined;c['unknown']=True
    with pytest.raises(facade.NativeCaseUnknown):facade.prepare_case(intent)
    c['unknown']=False;c['pending']=True
    assert facade.read_original_case(intent)==('PENDING',None)
    with pytest.raises(facade.NativeCaseUnknown):facade.prepare_case(intent)
    assert c['actions']==['prepare_case','read_original_case'] and c['source']==1


def test_late_current_runtime_withdrawal_hides_received_source(joined):
    _,_,_,intent,c=joined;c['withdraw']=True
    with pytest.raises(peer.ProtectedMemoryRefused):facade.prepare_case(intent)
    assert c['source']==1


@pytest.mark.parametrize('damage',['wrong_intent','clone','subclass','wrong_input','foreign_result'])
def test_result_or_capability_substitution_never_reaches_transport(joined,damage):
    _,_,lease,intent,c=joined;cap=facade.prepare_case(intent);before=list(c['actions'])
    chosen=cap;given=intent;digest=hashlib.sha256(rawpacket()).hexdigest();result={'sha256':'b'*64,'bytes':12}
    if damage=='wrong_intent':given=object.__new__(peer.ControlMemoryIntent)
    elif damage=='clone':chosen=object.__new__(facade.NativeCaseCapability)
    elif damage=='subclass':
        class Foreign(facade.NativeCaseCapability):pass
        chosen=object.__new__(Foreign)
    elif damage=='wrong_input':digest='c'*64
    else:result['path']='/private/foreign'
    with pytest.raises(ValueError):facade.authorize_result_disclosure(chosen,given,lease.attempt.attempt_id,digest,result)
    assert c['actions']==before


def test_root_rejects_unqualified_projection_before_enrollment_or_ssh(claimed,installed,monkeypatch):
    _,_,_=claimed
    monkeypatch.setattr(root,'_enrollment',lambda _:pytest.fail('no enrollment read'))
    monkeypatch.setattr(root,'_exchange',lambda _:pytest.fail('no SSH'))
    monkeypatch.setattr(peer.os,'geteuid',lambda:501)
    assert root.handle_memory_exchange({'schema':root.SCHEMA,'operation':'exchange','projection':{},'request':{}},installed[0])=={
        'schema':root.SCHEMA,'state':'REFUSED'}


def test_existing_privileged_broker_registered_branch_uses_actual_accepted_socket(monkeypatch):
    import socket
    import threading
    from types import SimpleNamespace
    from control_plane import executive_privileged_broker as broker
    from control_plane import executive_peer_identity as native_peer
    from tests.test_executive_peer_identity import owner_observation,bind_fixture
    left,right=socket.socketpair(socket.AF_UNIX,socket.SOCK_STREAM)
    def observation(connection):
        return native_peer._KernelObservation(b'K'*32,450,1234,5678,native_peer._descriptor_identity(connection))
    monkeypatch.setattr(native_peer,'_observe_socket',observation)
    monkeypatch.setattr(peer,'qualify_installed_peer',lambda capture,role:bind_fixture(capture,owner_observation(capture)))
    monkeypatch.setattr(peer.os,'geteuid',lambda:0)
    service=SimpleNamespace(config=SimpleNamespace(allowed_peer_uids=(450,)))
    errors=[]
    def serve():
        try:broker.serve_connection(service,left,peer_resolver=lambda sock:450)
        except BaseException as error:errors.append(error)
        finally:left.close()
    thread=threading.Thread(target=serve);thread.start()
    try:
        right.sendall(wire.canonical({'schema':root.SCHEMA,'operation':'describe'})+b'\n')
        raw=bytearray()
        while True:
            part=right.recv(65536)
            if not part:break
            raw.extend(part)
        result=json.loads(raw)
        assert result['schema']==root.SCHEMA and result['state']=='OWNER_CURRENT'
        assert result['owner']['service_label']=='com.mastermind.executive.control'
        assert result['owner']['mode']==peer.MODE
    finally:right.close();thread.join(3)
    assert not thread.is_alive() and not errors


def test_absent_original_lookup_never_creates_an_input_or_new_attempt(joined):
    runtime,_,_,intent,c=joined;c['unknown']=True
    with pytest.raises(facade.NativeCaseUnknown):facade.prepare_case(intent)
    c['unknown']=False;c['absent']=True
    assert facade.read_original_case(intent)==('ABSENT',None)
    with pytest.raises(facade.NativeCaseUnknown):facade.prepare_case(intent)
    assert c['source']==1 and c['actions']==['prepare_case','read_original_case']
    assert sum(e.event_type=='MEMORY_PREPARE_ATTEMPT' for e in runtime.events.list_events())==1
