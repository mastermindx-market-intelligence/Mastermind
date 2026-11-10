"""Joined existing Runtime/Control/root/exact input/private result source test.

Explicit inert premises: installed450 process/filesystem identity, protected
root source/binary enrollment, Linux SSH issuer, and disposable child/provider
process are substituted. Actual SQLite claims/pin/process/Events, Unix FD
handshake, fixed argv/body, private retained files and parser are exercised.
No actual login/source/private E0/provider/study or installed transport proof.
"""
import base64
import dataclasses
import hashlib
import json
import pwd
import os
from pathlib import Path
import socket
import stat
import threading
import time
from types import SimpleNamespace
import pytest

from common import memory_native_wire as wire
from common.memory_participant_view import selected_descriptors
from control_plane import protected_memory_execution as execution
from control_plane import protected_memory_peer as peer
from control_plane import protected_memory_profile as profile
from control_plane import memory_native_issuer as facade
from control_plane import executive_memory_issuer as root
from control_plane import paid_fabric_backend as paid
from control_plane.worker_execution_contract import BinaryAttestation
from tests.test_protected_memory_profile import configured
from tests.test_protected_memory_peer import installed
from tests.test_executive_peer_identity import owner_observation,bind_fixture
from tests.test_memory_native_wire import response,frame
from tests.test_memory_participant_view import packet
from tests.test_protected_memory_economic import economy

@pytest.fixture
def joined(configured,installed,monkeypatch,economy,request):
    runtime,job,_,config=configured
    # A composed fixture may also contain its still-active study root. Select
    # the actual configured opaque claim, never the first unrelated Attempt.
    attempt=runtime.attempts.get_attempt(__import__('control_plane.native_memory_admission',fromlist=['_ISSUED'])._ISSUED[configured[2]].lease.attempt.attempt_id)
    # The genuine opaque token remains in the source fixture claim, never
    # reconstructed from public Attempt fields or source labels.
    from control_plane import native_memory_admission as admission
    state=admission._ISSUED[configured[2]];lease=state.lease
    def qualified(capture,*,role):
        return bind_fixture(capture,dataclasses.replace(owner_observation(capture),
            service_label=installed[1]['label'],config_digest=config['owner']['configuration_sha256']))
    monkeypatch.setattr(peer,'qualify_installed_peer',qualified)
    actions=[];calls=[];done=threading.Event();errors=[];result={'bad':False,'late':False}
    native=packet()
    if getattr(request,'param',None)=='native-builder-vector':
        native=(Path(__file__).parent/'fixtures/native_memory_packet_20261106/participant-input.bin').read_bytes()
        assert hashlib.sha256(native).hexdigest()=='f4213c04dc827819ac476859803d462b27ddf4badb3d5855c52dbf701acd641f'
    result['native_packet']=native
    sha=hashlib.sha256(native).hexdigest()
    fingerprint=response({'schema':'request.v2','action':'prepare_case','operation_id':'x','intent':{}})['issuer']['broker_service_fingerprint']
    monkeypatch.setattr(root,'_enrollment',lambda _:(config['raw'],fingerprint,b'known',(1,2,3)))
    def exchange(raw):
        req=wire.decode_request(raw);actions.append(req['action'])
        if req['action']=='qualify_current_case' and result.get('qualification')=='unknown':raise root.IssuerExchangeUnknown()
        if (req['action']=='qualify_current_case' and result.get('qualification')=='refused'
                or req['action']=='prepare_case' and result.get('revoked_after_qualification')):
            return frame({'schema':'research_factory.market_memory_e0_native_issuer_response.v3','status':'REFUSED',
                'reason':'native_recipient_grant_unavailable','verification':dict(wire.FLAGS),
                'scientific_admission':False,'retry_authorized':False})
        value=response(req)
        if result.get('access_advanced'):
            value['issuer']['current_selection_sha256']='b'*64
            value['issuer']['current_access_ref']=dict(value['issuer']['current_access_ref'],object_id='continued-access',sha256='b'*64)
        if result.get('grant_changed'):
            value['issuer']['recipient_grant_ref']=dict(value['issuer']['recipient_grant_ref'],sha256='c'*64)
        if req['action']=='authorize_result_disclosure' and result.get('disclosure_refused'):
            return frame({'schema':'research_factory.market_memory_e0_native_issuer_response.v3','status':'REFUSED',
                'reason':'native_recipient_grant_unavailable','verification':dict(wire.FLAGS),
                'scientific_admission':False,'retry_authorized':False})
        loc=value.get('locator')
        if loc is not None:loc.update(input_sha256=sha,input_bytes=len(native))
        if 'input' in value:value['input'].update(body=base64.b64encode(native).decode(),sha256=sha,bytes=len(native))
        if req['action']=='authorize_result_disclosure':
            value['result_ref']=req['result_ref']
        return frame(value)
    monkeypatch.setattr(root,'_exchange',exchange)
    from control_plane import protected_memory_economic_owner as economic_root
    economic_owner,_,economic_engine,token,authorization,_,_,_,_=economy
    # Explicit inert root->501 metadata-process boundary. Actual original
    # bearer, count reservation, Broker lease, input consumption and ledger
    # run against the real disposable incumbent owners, not receipt fixtures.
    monkeypatch.setattr(root,'_read',lambda path,_maximum:config['raw'] if path==root.CONFIG else (_ for _ in ()).throw(ValueError()))
    def economic_helper(value):
        monkeypatch.setattr(peer.os,'geteuid',lambda:501)
        try:
            action=value['action'];selector=value['selector'];arguments=value['arguments']
            if action=='acquire':
                scope=dict(authorization,**selector)
                return economic_engine.acquire(selector,value['route'],controller_pid=value['controller_pid'],
                    delegation=value['delegation'],authority=economic_engine._fixture_root_authority(scope))
            economic_engine.require_route(selector,value['route'],ready=action!='settle')
            if action in ('current','heartbeat'):return getattr(economic_engine,action)(selector)
            return getattr(economic_engine,action)(selector,arguments)
        finally:monkeypatch.setattr(peer.os,'geteuid',lambda:0)
    monkeypatch.setattr(economic_root,'_call_helper',economic_helper)
    monkeypatch.setattr(economic_root,'qualify_helper_source',lambda:None)
    def send(value):
        monkeypatch.setattr(peer.os,'geteuid',lambda:0)
        try:return root.handle_memory_exchange(json.loads(wire.canonical(value)),installed[0])
        finally:monkeypatch.setattr(peer.os,'geteuid',lambda:450)
    monkeypatch.setattr(facade,'_send',send)
    monkeypatch.setattr(peer.os,'geteuid',lambda:450)
    run=runtime.store.root/'data/control_plane/runs'/attempt.attempt_id;run.mkdir(parents=True,mode=0o700);run.chmod(0o700)
    def private(path):
        assert path==run and stat.S_IMODE(path.stat().st_mode)==0o700
    monkeypatch.setattr(execution,'_private_directory',private)
    binary=Path(os.sys.executable).resolve();info=binary.stat()
    att=BinaryAttestation(str(binary),str(binary),'fixture-interpreter',hashlib.sha256(binary.read_bytes()).hexdigest(),None,
        info.st_size,info.st_dev,info.st_ino,info.st_mode,info.st_uid,info.st_gid,info.st_mtime_ns)
    monkeypatch.setattr(execution,'_source_binary',lambda:att)
    class Inspector:
        def inspect(self,pid):return SimpleNamespace(pgid=pid,start_identity='fixture-start',session_id=pid,
            effective_uid=450,effective_gid=450,real_uid=450,real_gid=450)
        def boot_session_id(self):return 'fixture-boot'
    monkeypatch.setattr(execution,'ProcessInspector',Inspector)
    class Process:
        def __init__(self,argv,**kwargs):
            calls.append((argv,kwargs['env']));self.pid=os.getpid()
            channel=socket.socket(fileno=os.dup(kwargs['pass_fds'][0]));out=os.dup(kwargs['stdout'])
            def child():
                try:
                    channel.sendall(b'READY\n');raw=bytearray()
                    while True:
                        part=channel.recv(65536)
                        if not part:break
                        raw.extend(part)
                    assert int.from_bytes(raw[:4],'big')==len(raw)-4
                    envelope=wire.parse(bytes(raw[4:]),400000)
                    actual=base64.b64decode(envelope['input_base64'])
                    assert actual==result['native_packet']
                    body=json.loads(base64.b64decode(envelope['body_base64']))
                    assert body['input'].encode()==actual and body['input'].encode().count(wire.SUFFIX)==1
                    chosen=selected_descriptors(actual)[0]
                    if result['bad']:chosen['context_id']='foreign-arm'
                    original=wire.canonical({'schema':'research_factory.market_memory_e0_participant_result.v1','answer':'Fixture untrusted answer','citations':[chosen]})
                    os.write(out,original);os.fsync(out)
                except BaseException as error:errors.append(error)
                finally:os.close(out);channel.close();done.set()
            threading.Thread(target=child,daemon=True).start()
        def poll(self):return (1 if errors else 0) if done.is_set() else None
    monkeypatch.setattr(execution.subprocess,'Popen',Process)
    # Inert filesystem UID premise only; real file bytes/modes/stability remain.
    def retained(path,limit):
        before=path.stat();raw=path.read_bytes();after=path.stat()
        assert before.st_ino==after.st_ino and before.st_mtime_ns==after.st_mtime_ns
        assert stat.S_IMODE(before.st_mode)==0o600 and 1<=len(raw)<=limit
        return raw
    monkeypatch.setattr(paid,'_private_read',retained)
    result['economic_owner']=economic_owner;result['economic_engine']=economic_engine
    from control_plane.executive_supervisor import ExecutiveSupervisor
    class Unused:
        inspector=Inspector()
        def __getattr__(self,name):raise AssertionError('ordinary adapter not used')
    supervisor=ExecutiveSupervisor(runtime,Unused(),worker_user=pwd.getpwuid(os.getuid()).pw_name)
    supervisor.retain_protected_memory_economic_delegation(lease,token,
        task_class=authorization['task_class'],task_complexity=authorization['task_complexity'])
    result['supervisor']=supervisor;result['config']=config;result['installed']=installed
    return runtime,job,lease,actions,calls,done,errors,result,run


def test_existing_runtime_fixed_owner_one_exact_input_and_current_recipient_view(joined):
    runtime,job,lease,actions,calls,done,errors,result,run=joined
    prepared=execution.prepare_memory_execution(runtime,lease)
    ref=execution.start_memory_execution(prepared)
    assert done.wait(3) and not errors
    projected=execution.disclose_memory_result(prepared)
    assert projected['answer']=='Fixture untrusted answer'
    assert projected['verification']==wire.FLAGS and projected['scientific_admission'] is False
    assert len(calls)==1 and len(runtime.jobs.list_jobs())==1
    actual=runtime.attempts.get_attempt(lease.attempt.attempt_id)
    assert actual.pid==ref.pid and actual.status.value=='RUNNING'
    assert sum(e.event_type=='MEMORY_EXECUTION_ATTEMPT' for e in runtime.events.list_events())==1
    with pytest.raises(execution.MemoryExecutionUnknown):execution.start_memory_execution(prepared)
    assert len(calls)==1
    assert not list(runtime.store.root.glob('**/*.operator-packet'))
    assert 'RESULT_SCHEMA_JSON' not in run.joinpath('memory-original-result').read_text()
    delegation=json.loads((run/'memory-original-economic-delegation').read_bytes())
    bearer=delegation['token']
    assert stat.S_IMODE((run/'memory-original-economic-delegation').stat().st_mode)==0o600
    assert bearer not in json.dumps([e.payload for e in runtime.events.list_events()])
    assert bearer not in json.dumps(calls) and bearer not in (run/'memory-original-input').read_text()


def test_current_grant_loss_withholds_retained_result_and_never_replays(joined):
    runtime,job,lease,actions,calls,done,errors,_,_=joined
    prepared=execution.prepare_memory_execution(runtime,lease);execution.start_memory_execution(prepared)
    assert done.wait(3) and not errors
    before=list(actions)
    with runtime.store.transaction() as con:con.execute("UPDATE jobs SET status='CANCELLED' WHERE job_id=?",(job.job_id,))
    with pytest.raises(ValueError):execution.disclose_memory_result(prepared)
    assert actions==before and len(calls)==1


def test_foreign_arm_citation_cannot_escape_private_original(joined):
    _,_,lease,_,calls,done,errors,result,_=joined;result['bad']=True
    runtime=joined[0];prepared=execution.prepare_memory_execution(runtime,lease);execution.start_memory_execution(prepared)
    assert done.wait(3) and not errors
    with pytest.raises(ValueError,match='memory_participant_view_refused'):execution.disclose_memory_result(prepared)
    assert len(calls)==1


def test_missing_protected_profile_refuses_before_linux_source_prepare(joined,monkeypatch):
    runtime,_,lease,actions,calls,_,_,_,_=joined
    def unavailable():raise profile.MemoryProfileRefused()
    monkeypatch.setattr(profile,'_credential_metadata',unavailable)
    with pytest.raises(profile.MemoryProfileRefused):execution.prepare_memory_execution(runtime,lease)
    assert not actions and not calls
    assert not any(e.event_type=='MEMORY_PREPARE_ATTEMPT' for e in runtime.events.list_events())


def test_actual_economic_grant_revocation_refuses_before_linux_prepare_or_process(joined):
    runtime,_,lease,actions,calls,_,_,state,_=joined
    owner=state['economic_owner']
    with owner.transaction() as con:con.execute("UPDATE leases SET state='released'")
    with pytest.raises(ValueError):execution.prepare_memory_execution(runtime,lease)
    assert actions==['qualify_current_case'] and calls==[]
    assert not any(e.event_type=='MEMORY_PREPARE_ATTEMPT' for e in runtime.events.list_events())
    with owner.transaction() as con:assert con.execute('SELECT count(*) FROM operator_child_authorizations').fetchone()[0]==0


def test_paid_permission_loss_after_source_preparation_refuses_before_provider_input_release(joined):
    runtime,_,lease,actions,calls,_,_,state,_=joined
    prepared=execution.prepare_memory_execution(runtime,lease)
    owner=state['economic_owner']
    with owner.transaction() as con:con.execute("UPDATE leases SET state='released' WHERE task_class='remote-glm'")
    with pytest.raises(ValueError):execution.start_memory_execution(prepared)
    assert actions==['qualify_current_case','prepare_case','current_input'] and calls==[]


def test_same_preinput_reservation_cannot_be_spent_by_a_second_original_prepare(joined):
    runtime,_,lease,actions,calls,_,_,_,_=joined
    execution.prepare_memory_execution(runtime,lease)
    with pytest.raises(ValueError):execution.prepare_memory_execution(runtime,lease)
    assert actions==['qualify_current_case','prepare_case','current_input'] and calls==[]


def test_actual_existing_supervisor_internal_entry_terminalizes_safe_runtime_receipt(joined):
    import asyncio
    from control_plane.executive_supervisor import ExecutiveSupervisor
    runtime,job,lease,_,calls,_,errors,_,_=joined
    # Existing generic adapter is deliberately unusable; this exact source mode
    # must not route input through the ordinary UID501 adapter/fake controller.
    class Unused:
        inspector=execution.ProcessInspector()
        def __getattr__(self,name):raise AssertionError('ordinary adapter not used')
    supervisor=ExecutiveSupervisor(runtime,Unused(),worker_user=pwd.getpwuid(os.getuid()).pw_name)
    view=asyncio.run(supervisor.run_protected_memory_case(lease))
    assert view['answer']=='Fixture untrusted answer' and len(calls)==1 and not errors
    assert runtime.jobs.get_job(job.job_id).status.value=='COMPLETED'
    result=runtime.jobs.get_job(job.job_id).result
    assert 'Fixture untrusted answer' not in json.dumps(result)
    assert 'context-0' not in json.dumps(result)
    assert sum(e.event_type=='MEMORY_RESULT_VIEW_OBSERVED' for e in runtime.events.list_events())==1


@pytest.mark.parametrize('joined',['native-builder-vector'],indirect=True)
def test_native_builder_whole_packet_through_actual_economic_runtime_and_private_result_owner(joined):
    # Genuine supplied packet; installed peer/Linux grant/child are still the
    # explicit inert premises above, NOT a full native issuer/provider claim.
    runtime,_,lease,_,calls,done,errors,_,run=joined
    prepared=execution.prepare_memory_execution(runtime,lease)
    execution.start_memory_execution(prepared)
    assert done.wait(3) and not errors
    view=execution.disclose_memory_result(prepared)
    held=(run/'memory-original-input').read_bytes()
    assert len(held)==9856 and hashlib.sha256(held).hexdigest()=='f4213c04dc827819ac476859803d462b27ddf4badb3d5855c52dbf701acd641f'
    assert view['citations']==[selected_descriptors(held)[0]] and len(calls)==1
    assert view['verification']==wire.FLAGS and view['scientific_admission'] is False


@pytest.mark.parametrize('status',['refused','unknown','malformed'])
def test_v3_nonqualification_never_reserves_original_child_count_or_paid_lease(joined,monkeypatch,status):
    runtime,_,lease,actions,calls,_,_,state,_=joined
    state['qualification']=status
    if status=='malformed':
        actual=root._exchange
        def malformed(raw):
            req=wire.decode_request(raw)
            if req['action']=='qualify_current_case':
                actions.append(req['action']);value=response(req);value['locator']={};return frame(value)
            return actual(raw)
        monkeypatch.setattr(root,'_exchange',malformed)
    with pytest.raises(ValueError):execution.prepare_memory_execution(runtime,lease)
    assert actions==['qualify_current_case'] and calls==[]
    owner=state['economic_owner']
    with owner.transaction() as con:
        assert con.execute('SELECT count(*) FROM operator_child_authorizations').fetchone()[0]==0
        assert con.execute('SELECT count(*) FROM leases').fetchone()[0]==1
    assert not any(e.event_type=='MEMORY_PREPARE_ATTEMPT' for e in runtime.events.list_events())


def test_fresh_prepare_grant_revocation_after_qualification_withholds_input_and_provider(joined):
    runtime,_,lease,actions,calls,_,_,state,run=joined
    state['revoked_after_qualification']=True
    with pytest.raises(ValueError):execution.prepare_memory_execution(runtime,lease)
    assert actions==['qualify_current_case','prepare_case'] and calls==[]
    assert not (run/'memory-original-input').exists()
    with state['economic_owner'].transaction() as con:
        assert con.execute('SELECT count(*) FROM operator_child_authorizations').fetchone()[0]==1
        assert con.execute('SELECT count(*) FROM leases').fetchone()[0]==2


def test_v3_qualified_current_access_advances_without_rebinding_original_input_or_grant(joined):
    runtime,_,lease,_,calls,done,errors,state,run=joined
    prepared=execution.prepare_memory_execution(runtime,lease)
    old=next(e.payload for e in runtime.events.list_events() if e.event_type=='MEMORY_CASE_BOUND')
    state['access_advanced']=True
    execution.start_memory_execution(prepared)
    assert done.wait(3) and not errors
    view=execution.disclose_memory_result(prepared)
    assert view['answer']=='Fixture untrusted answer' and len(calls)==1
    assert next(e.payload for e in runtime.events.list_events() if e.event_type=='MEMORY_CASE_BOUND')==old
    assert hashlib.sha256((run/'memory-original-input').read_bytes()).hexdigest()==view['input_sha256']


def test_v3_changed_original_native_grant_never_uses_current_access_exemption(joined):
    runtime,_,lease,_,calls,_,_,state,_=joined
    prepared=execution.prepare_memory_execution(runtime,lease)
    state['grant_changed']=True
    with pytest.raises(ValueError):execution.start_memory_execution(prepared)
    assert calls==[]


@pytest.fixture
def absent_control_user(monkeypatch):
    """Linux CI has no NSS user450; the inert UID premise is not enrollment."""
    real=pwd.getpwuid
    def lookup(uid):
        if uid==450:raise KeyError('explicit inert missing Control account')
        return real(uid)
    monkeypatch.setattr(pwd,'getpwuid',lookup)


def test_disposable_supervisor_does_not_require_a_real_control_account(absent_control_user,joined):
    runtime,_,_,_,_,_,_,state,_=joined
    assert state['supervisor'].worker_user==pwd.getpwuid(os.getuid()).pw_name
    assert state['supervisor'].runtime is runtime
