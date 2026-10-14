"""Hermetic protocol tests; no service activation, host dispatch or UID sweep."""
import asyncio
import copy
import dataclasses
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from control_plane.executive_worker_broker import BROKER_REQUEST_SCHEMA_VERSION, BROKER_RESPONSE_SCHEMA_VERSION, PeerCredentials
try:
    from control_plane import executive_fabric_bridge_broker as bridge
except ImportError:
    bridge = None


def api():
    assert bridge is not None, "assigned optional Fabric broker module is not implemented"
    return bridge


def config_document():
    return dict(schema_version="mastermind.executive_fabric_bridge_config/v1", adapter_id="attended-fabric",
        bridge_uid=501, control_uid=450, launchd_socket_name="FabricBridge",
        socket_path="/var/run/mastermind/fabric-bridge.sock", workspace_root="/srv/fabric/workspaces",
        run_root="/srv/fabric/runs", max_request_bytes=65536, max_response_bytes=262144,
        request_timeout_seconds=10, validation_commands=[["/usr/bin/true"]])


def config(tmp_path, monkeypatch):
    b=api(); path=tmp_path / "config.json"; path.write_text(json.dumps(config_document()))
    # Fixture root ownership only; never chmod/chown an installed file.
    original = b.os.fstat
    def root_stat(fd):
        observed=original(fd)
        return SimpleNamespace(**{name:getattr(observed,name) for name in ('st_mode','st_dev','st_ino','st_size','st_mtime_ns')},st_uid=0)
    monkeypatch.setattr(b.os,'fstat',root_stat)
    monkeypatch.setattr(b,'_trusted_parent_chain',lambda path:None)
    return b.load_config(path)


def binding():
    return dict(root_id="original-root", job_id="job-1", attempt_id="attempt-1",
                effective_grant_digest="a"*64, commission_sha256="b"*64)


def start_payload():
    return dict(binding=binding(), physical_binding_sha256='9'*64, launch_spec=dict(run_id="attempt-1",job_id="job-1",worker_id="worker-1",
        workspace_path="/srv/fabric/workspaces/task",run_dir="/srv/fabric/runs/attempt-1",prompt="inert fixture",
        result_schema_path="/srv/fabric/runs/attempt-1/schema.json",authorities=["READ"],worker_user="fabric-worker",
        model="fixture-model",expected_base_sha="c"*40,effective_grant_digest="a"*64,
        isolation_manifest_sha256="d"*64,secret_canary_verdict={'passed':True},expected_worker_uid=1001,expected_worker_gid=1001),validation_commands=[])


def envelope(operation="start", payload=None):
    if payload is not None:
        payload = {'physical_binding_sha256':'9'*64, **payload}
    return dict(schema_version=BROKER_REQUEST_SCHEMA_VERSION,request_id="request-1",operation=operation,
                payload=start_payload() if payload is None else payload)


def command_envelope():
    """Inert authenticated-command fixture; never a production pin producer."""
    from control_plane.fabric_control_start import SCHEMA, launch_identity
    value = envelope()
    payload = value['payload']
    payload['control_start'] = dict(schema_version=SCHEMA,
        attempt_id=payload['binding']['attempt_id'], fence_generation=1, pin_version=2,
        pin_identity_sha256=launch_identity(payload), lease_expires_at='2099-01-01T00:00:00Z')
    return value


def start_result(payload):
    binary=dict(path="/usr/bin/provider",real_path="/usr/bin/provider",version="1",sha256="e"*64,
                team_identifier=None,size=123,device=1,inode=2,mode=0o755,uid=0,gid=0,mtime_ns=123)
    ref=dict(run_id="attempt-1",pid=1234,pgid=1234,session_id=1234,process_start_identity="linux:9876",
             boot_session_id="fixture-boot",launch_nonce="launch-1",provider_session_id="provider-1",
             stdout_path="/srv/fabric/runs/attempt-1/stdout",stderr_path="/srv/fabric/runs/attempt-1/stderr",
             result_path="/srv/fabric/runs/attempt-1/result",started_at="2026-10-11T10:00:00Z",binary=binary,
             base_sha="c"*40,effective_uid=1001,effective_gid=1001,real_uid=1001,real_gid=1001)
    identity=dict(pid=1234,pgid=1234,session_id=1234,start_identity="linux:9876",boot_id="fixture-boot",
                  effective_uid=1001,effective_gid=1001,real_uid=1001,real_gid=1001)
    attestation=dict(schema_version="mastermind.executive_launch_attestation/v1",created_at=ref['started_at'],
        executable_path=binary['real_path'],binary=binary,rendered_argv=[binary['real_path']],environment_keys=["PATH"],
        permission_profile_sha256="f"*64,isolation_manifest_sha256="d"*64,
        prompt_sha256=hashlib.sha256(payload['launch_spec']['prompt'].encode()).hexdigest(),expected_base_sha="c"*40,
        observed_base_sha="c"*40,workspace_identity=dict(path=payload['launch_spec']['workspace_path'],device=1,inode=2,uid=1001,gid=1001,mode=0o700,mtime_ns=1),
        worker_identity=dict(requested_user='fabric-worker',observed_user='fabric-worker',expected_uid=1001,expected_gid=1001,effective_uid=1001,effective_gid=1001,real_uid=1001,real_gid=1001),
        provider_home_identity=dict(path="/srv/fabric/provider",device=1,inode=2,uid=1001,gid=1001,mode=0o700,mtime_ns=1),secret_canary_verdict=dict(passed=True),
        launch_nonce="launch-1",process_identity=identity)
    return dict(adapter_id="attended-fabric",physical_binding_sha256='9'*64,process_ref=ref,launch_attestation=attestation,
                binding=payload['binding'],request_sha256=api().start_request_sha256(payload))


class Backend:
    def __init__(self):self.calls=[];self.retained=None;self.failure=None;self.start_state="UNSTARTED_PROVEN"
    async def start_owned(self,payload,*,authority):
        authority.require(payload)
        # Reuse the inert legacy recorder only inside this authenticated test
        # owner. Production broker must never invoke generic execute('start').
        return await self.execute('start',payload)
    async def execute(self,operation,payload):
        self.calls.append((operation,copy.deepcopy(payload)))
        if operation=='status' and 'start_request_sha256' in payload:
            if self.retained:
                return dict(adapter_id='attended-fabric',start_state='EXISTS',start_result=self.retained,
                            binding=payload['binding'],request_sha256=payload['start_request_sha256'],physical_binding_sha256='9'*64)
            return dict(adapter_id='attended-fabric',start_state=self.start_state,
                        binding=payload['binding'],request_sha256=payload['start_request_sha256'],physical_binding_sha256='9'*64)
        if self.failure:raise self.failure
        if operation=='start':
            self.retained=start_result(payload)
            return self.retained
        result=dict(adapter_id='attended-fabric',physical_binding_sha256='9'*64,binding=payload['binding'])
        ref=start_result(start_payload())['process_ref']
        if operation=='status':result['run']=dict(run_id=payload['run_id'],status='RUNNING',process_ref=ref)
        elif operation=='cancel':result['cancellation']=dict(run_id=payload['run_id'],reason=payload['reason'],signal_sent=False,
            escalated_to_sigkill=False,already_exited=True,finished_at='2026-10-11T10:01:00Z')
        elif operation=='validate':result['validation']=dict(argv=payload['argv'],exit_code=0,stdout_sha256='a'*64,
            stdout_size=0,stderr_sha256='b'*64,stderr_size=0,timed_out=False,error=None)
        elif operation=='collect':result['collection']=dict(process_ref=ref,stdout_sha256='a'*64,stderr_sha256='b'*64,
            result_sha256='c'*64,result=dict(job_id='job-1',run_id='attempt-1',worker_id='worker-1',status='SUCCEEDED',
            structured_output=None,artifact_manifest=[],git_manifest={},usage={},provider_session_id='provider-1',exit_code=0,
            started_at='2026-10-11T10:00:00Z',finished_at='2026-10-11T10:01:00Z',error=None))
        return result


def broker(tmp_path, monkeypatch, backend=None):
    return api().FabricBridgeBroker(config(tmp_path,monkeypatch),backend or Backend())


def execute(service, request, uid=450):
    return asyncio.run(service.execute(request,peer=PeerCredentials(uid=uid,gid=450)))


@pytest.mark.parametrize('uid',[0,451,501])
def test_unauthorized_peer_never_reaches_backend(tmp_path,monkeypatch,uid):
    backend=Backend();service=broker(tmp_path,monkeypatch,backend)
    with pytest.raises(api().BridgeProtocolError,match='PeerAuthorizationError'):
        execute(service,envelope(),uid)
    assert backend.calls==[]


def test_successful_start_uses_same_attempt_and_full_attestation(tmp_path,monkeypatch):
    backend=Backend();service=broker(tmp_path,monkeypatch,backend)
    response=execute(service,command_envelope())
    assert response['schema_version']==BROKER_RESPONSE_SCHEMA_VERSION and response['ok'] is True
    assert response['request_id']=='request-1' and response['operation']=='start'
    assert [op for op,p in backend.calls]==['status','start']
    assert backend.calls[1][1]['launch_spec']['run_id']=='attempt-1'
    assert response['result']['process_ref']['pid']==1234


def test_lost_ack_and_reopened_service_use_status_only_retained_attempt(tmp_path,monkeypatch):
    backend=Backend();first=broker(tmp_path,monkeypatch,backend)
    expected=execute(first,command_envelope())['result']
    reopened=api().FabricBridgeBroker(first.config,backend)
    observed=execute(reopened,envelope())['result']
    assert observed==expected
    assert [op for op,p in backend.calls].count('start')==1
    assert backend.calls[-1][0]=='status'


@pytest.mark.parametrize('mutate',[
    lambda p:p.update(host='alternate'),lambda p:p.update(account='other'),
    lambda p:p['binding'].update(extra=True),lambda p:p['binding'].update(root_id=''),
    lambda p:p['binding'].update(effective_grant_digest='x'),
    lambda p:p['binding'].update(attempt_id='attempt-2'),lambda p:p['binding'].update(job_id='job-2'),
    lambda p:p['launch_spec'].update(effective_grant_digest='e'*64),
    lambda p:p['launch_spec'].update(workspace_path='/Users/chris/.claude'),
    lambda p:p['launch_spec'].update(run_dir='/srv/fabric/runs/../escape'),
    lambda p:p.update(validation_commands=[['/bin/sh','-c','anything']]),
])
def test_malformed_or_mismatched_start_refuses_before_effect(tmp_path,monkeypatch,mutate):
    backend=Backend();service=broker(tmp_path,monkeypatch,backend);request=envelope();mutate(request['payload'])
    with pytest.raises(api().BridgeProtocolError):execute(service,request)
    assert backend.calls==[]


@pytest.mark.parametrize('state',['UNKNOWN','NOT_FOUND','EFFECT_UNKNOWN'])
def test_unproven_first_use_does_not_infer_absence_or_start(tmp_path,monkeypatch,state):
    backend=Backend();backend.start_state=state;service=broker(tmp_path,monkeypatch,backend)
    with pytest.raises(api().BridgeProtocolError,match='EFFECT_UNKNOWN'):execute(service,envelope())
    assert [op for op,p in backend.calls]==['status']


def test_backend_start_exception_is_sticky_unknown_and_never_retried(tmp_path,monkeypatch):
    backend=Backend();backend.failure=RuntimeError('private diagnostic');service=broker(tmp_path,monkeypatch,backend)
    with pytest.raises(api().BridgeProtocolError,match='EFFECT_UNKNOWN'):execute(service,command_envelope())
    assert [op for op,p in backend.calls]==['status','start']
    backend.start_state='EFFECT_UNKNOWN'
    with pytest.raises(api().BridgeProtocolError,match='EFFECT_UNKNOWN'):execute(service,envelope())
    assert [op for op,p in backend.calls].count('start')==1


@pytest.mark.parametrize('change',[
    lambda r:r.update(adapter_id='codex-cli'),
    lambda r:r['binding'].update(root_id='other-root'),
    lambda r:r.update(request_sha256='1'*64),
    lambda r:r['process_ref'].update(pid=None),
    lambda r:r['process_ref'].update(effective_uid=None),
    lambda r:r.update(launch_attestation={'schema':'mastermind.local_owned_process_launch.v1','phase':'PRE_EXEC_HANDSHAKE'}),
    lambda r:r['launch_attestation'].update(process_identity={}),
])
def test_retained_wrong_identity_or_partial_receipt_is_not_success(tmp_path,monkeypatch,change):
    backend=Backend();service=broker(tmp_path,monkeypatch,backend);backend.retained=start_result(start_payload());change(backend.retained)
    with pytest.raises(api().BridgeProtocolError,match='EFFECT_UNKNOWN'):execute(service,envelope())
    assert [op for op,p in backend.calls]==['status']


@pytest.mark.parametrize('payload',[{}, {'fresh_uid_sweep':True}, {'run_id':'attempt-2','binding':binding()},
                                    {'run_id':'attempt-1','binding':binding(),'sweep_uid':501}])
def test_status_requires_exact_attempt_and_never_sweeps_uid501(tmp_path,monkeypatch,payload):
    backend=Backend();service=broker(tmp_path,monkeypatch,backend)
    with pytest.raises(api().BridgeProtocolError):execute(service,envelope('status',payload))
    assert backend.calls==[]


@pytest.mark.parametrize('raw',[b'{"schema_version":"x","schema_version":"y"}\n', b'{"payload":NaN}\n',b'{}',b'[]\n'])
def test_duplicate_nonfinite_or_unterminated_frames_refused(raw):
    with pytest.raises(api().BridgeProtocolError):api().decode_request(raw,max_bytes=1024)


def test_oversized_frame_refuses_before_json_decode():
    with pytest.raises(api().BridgeProtocolError):api().decode_request(b' '*1025+b'\n',max_bytes=1024)


def test_config_is_closed_and_fixed_principal(tmp_path,monkeypatch):
    cfg=config(tmp_path,monkeypatch)
    with pytest.raises(dataclasses.FrozenInstanceError):cfg.bridge_uid=0
    doc=config_document();doc['bridge_uid']=0
    with pytest.raises(api().BridgeProtocolError):api().BridgeConfig.from_document(doc)
    doc=config_document();doc['backend_shell']='anything'
    with pytest.raises(api().BridgeProtocolError):api().BridgeConfig.from_document(doc)


def test_untrusted_config_refuses_actual_user_owned_file(tmp_path):
    path=tmp_path/'config.json';path.write_text(json.dumps(config_document()))
    with pytest.raises(api().BridgeProtocolError,match='ConfigTrustError'):api().load_config(path)


@pytest.mark.parametrize('change',[
    lambda r:r['process_ref']['binary'].update(size=None),
    lambda r:r['process_ref'].update(stdout_path='/Users/chris/.claude/private'),
    lambda r:r['launch_attestation'].update(secret_canary_verdict={'passed':False}),
    lambda r:r['launch_attestation'].update(workspace_identity={'path':'/srv/fabric/workspaces/task'}),
])
def test_incomplete_binary_path_or_canary_provenance_refuses(tmp_path,monkeypatch,change):
    backend=Backend();service=broker(tmp_path,monkeypatch,backend)
    backend.retained=start_result(start_payload());change(backend.retained)
    with pytest.raises(api().BridgeProtocolError,match='EFFECT_UNKNOWN'):execute(service,envelope())
    assert [op for op,p in backend.calls]==['status']


def test_backend_cannot_mutate_request_to_replace_root_binding(tmp_path,monkeypatch):
    class Mutating(Backend):
        async def execute(self,operation,payload):
            if operation=='start':payload['binding']['root_id']='other-root'
            return await super().execute(operation,payload)
    backend=Mutating();service=broker(tmp_path,monkeypatch,backend)
    with pytest.raises(api().BridgeProtocolError,match='EFFECT_UNKNOWN'):execute(service,command_envelope())


class Reader:
    def __init__(self,raw):self.raw=raw;self.reads=0
    async def readline(self):self.reads+=1;return self.raw


class Writer:
    def __init__(self):self.written=b'';self.closed=False
    def get_extra_info(self,name):assert name=='socket';return object()
    def write(self,data):self.written+=data
    async def drain(self):pass
    def close(self):self.closed=True
    async def wait_closed(self):pass


def test_socket_handler_authenticates_before_reading_request_bytes(tmp_path,monkeypatch):
    backend=Backend();service=broker(tmp_path,monkeypatch,backend)
    service.peer_resolver=lambda sock:PeerCredentials(uid=501,gid=20)
    reader=Reader(json.dumps(envelope()).encode()+b'\n');writer=Writer()
    asyncio.run(service.handle_connection(reader,writer))
    assert reader.reads==0 and backend.calls==[] and writer.closed
    assert json.loads(writer.written)['error']['code']=='PeerAuthorizationError'


def test_handler_errors_preserve_valid_request_identity_and_do_not_leak_backend_text(tmp_path,monkeypatch):
    backend=Backend();backend.failure=RuntimeError('private text never transmitted');service=broker(tmp_path,monkeypatch,backend)
    service.peer_resolver=lambda sock:PeerCredentials(uid=450,gid=450)
    reader=Reader(json.dumps(command_envelope()).encode()+b'\n');writer=Writer()
    asyncio.run(service.handle_connection(reader,writer))
    reply=json.loads(writer.written)
    assert reply['request_id']=='request-1' and reply['operation']=='start'
    assert reply['error']['code']=='EFFECT_UNKNOWN'
    assert b'private text' not in writer.written


@pytest.mark.parametrize('operation',[[],{},'uid-sweep','ohf-start'])
def test_handler_malformed_or_unallowed_operation_is_protocol_error(tmp_path,monkeypatch,operation):
    service=broker(tmp_path,monkeypatch);service.peer_resolver=lambda sock:PeerCredentials(uid=450,gid=450)
    req=envelope();req['operation']=operation;writer=Writer()
    asyncio.run(service.handle_connection(Reader(json.dumps(req).encode()+b'\n'),writer))
    assert json.loads(writer.written)['error']['code']=='BrokerProtocolError'


def test_service_identity_guard_never_sweeps_uid501(tmp_path,monkeypatch):
    service=broker(tmp_path,monkeypatch)
    monkeypatch.setattr(api().os,'geteuid',lambda:0)
    with pytest.raises(api().BridgeProtocolError,match='BridgeIdentityError'):service.require_service_identity()
    monkeypatch.setattr(api().os,'geteuid',lambda:501)
    assert service.require_service_identity() is None
    assert not hasattr(service,'sweeper')


def test_config_short_read_cannot_accept_a_valid_json_prefix(tmp_path,monkeypatch):
    b=api();path=tmp_path/'config.json';raw=json.dumps(config_document()).encode();path.write_bytes(raw+b' ')
    original=b.os.fstat
    def trusted(fd):
        info=original(fd)
        return SimpleNamespace(**{name:getattr(info,name) for name in ('st_mode','st_dev','st_ino','st_size','st_mtime_ns')},st_uid=0)
    monkeypatch.setattr(b,'_trusted_parent_chain',lambda path:None)
    monkeypatch.setattr(b.os,'fstat',trusted)
    monkeypatch.setattr(b.os,'read',lambda fd,count:raw)
    with pytest.raises(b.BridgeProtocolError,match='ConfigTrustError'):b.load_config(path)


def test_trusted_config_cannot_be_constructed_from_unverified_document():
    b=api()
    with pytest.raises(b.BridgeProtocolError,match='ConfigTrustError'):
        b.FabricBridgeBroker(b.BridgeConfig.from_document(config_document()),Backend())


def test_changed_start_hash_or_root_on_reopen_is_not_replayed(tmp_path,monkeypatch):
    backend=Backend();service=broker(tmp_path,monkeypatch,backend)
    execute(service,command_envelope())
    changed=envelope();changed['payload']['binding']['root_id']='another-root'
    with pytest.raises(api().BridgeProtocolError,match='EFFECT_UNKNOWN'):execute(service,changed)
    assert [op for op,p in backend.calls].count('start')==1
    changed=envelope();changed['payload']['launch_spec']['prompt']='different prompt'
    with pytest.raises(api().BridgeProtocolError,match='EFFECT_UNKNOWN'):execute(service,changed)
    assert [op for op,p in backend.calls].count('start')==1


def test_readonly_reopened_status_never_requires_broker_memory(tmp_path,monkeypatch):
    # Model an existing Fabric-owner durable receipt with separate backend objects.
    # The broker never creates or owns this file or any execution ledger.
    path=tmp_path/'owner-retained-receipt.json'
    class OwnerReceiptBackend(Backend):
        async def execute(self,operation,payload):
            if operation=='status' and path.exists():self.retained=json.loads(path.read_text())
            result=await super().execute(operation,payload)
            if operation=='start':path.write_text(json.dumps(result))
            return result
    first=OwnerReceiptBackend();service=broker(tmp_path,monkeypatch,first)
    expected=execute(service,command_envelope())['result']
    second=OwnerReceiptBackend();reopened=api().FabricBridgeBroker(service.config,second)
    assert execute(reopened,envelope())['result']==expected
    assert [op for op,p in second.calls]==['status']


def test_authorized_peer_with_exact_duplicate_nested_json_never_reaches_backend(tmp_path,monkeypatch):
    backend=Backend();service=broker(tmp_path,monkeypatch,backend)
    service.peer_resolver=lambda sock:PeerCredentials(uid=450,gid=450)
    raw=json.dumps(envelope()).replace('"root_id": "original-root"','"root_id": "original-root", "root_id": "other-root"').encode()+b'\n'
    writer=Writer();asyncio.run(service.handle_connection(Reader(raw),writer))
    assert json.loads(writer.written)['error']['code']=='BrokerProtocolError'
    assert backend.calls==[]


def test_cancelled_start_requires_same_backend_status_after_reopen(tmp_path,monkeypatch):
    class Interrupted(Backend):
        async def execute(self,operation,payload):
            if operation=='start':
                self.calls.append((operation,payload));self.start_state='EFFECT_UNKNOWN'
                raise asyncio.CancelledError()
            return await super().execute(operation,payload)
    backend=Interrupted();service=broker(tmp_path,monkeypatch,backend)
    with pytest.raises(asyncio.CancelledError):execute(service,command_envelope())
    reopened=api().FabricBridgeBroker(service.config,backend)
    with pytest.raises(api().BridgeProtocolError,match='EFFECT_UNKNOWN'):execute(reopened,envelope())
    assert [op for op,p in backend.calls].count('start')==1


@pytest.mark.parametrize('change',[
    lambda r:r.pop('physical_binding_sha256'),
    lambda r:r.update(physical_binding_sha256='not-a-digest'),
    lambda r:r.update(physical_binding_sha256='8'*64),
])
def test_physical_route_hash_missing_invalid_or_moved_is_not_success(tmp_path,monkeypatch,change):
    backend=Backend();service=broker(tmp_path,monkeypatch,backend)
    backend.retained=start_result(start_payload());change(backend.retained)
    with pytest.raises(api().BridgeProtocolError,match='EFFECT_UNKNOWN'):execute(service,envelope())
    assert [op for op,p in backend.calls]==['status']


def test_status_recovery_hash_uses_same_id_without_launch(tmp_path,monkeypatch):
    backend=Backend();service=broker(tmp_path,monkeypatch,backend)
    expected=execute(service,command_envelope())['result']
    result=execute(service,envelope('status',dict(binding=binding(),run_id='attempt-1',
                         start_request_sha256=api().start_request_sha256(start_payload()))))['result']
    assert result['start_result']==expected
    assert result['physical_binding_sha256']=='9'*64
    assert [op for op,p in backend.calls].count('start')==1


@pytest.mark.parametrize('operation,extra,key',[
    ('status',{},'run'),('collect',{},'collection'),('cancel',{'reason':'fixture stop'},'cancellation'),
    ('validate',{'argv':['/usr/bin/true'],'timeout_seconds':1},'validation'),
])
def test_bound_non_start_operations_return_closed_standard_receipts(tmp_path,monkeypatch,operation,extra,key):
    backend=Backend();service=broker(tmp_path,monkeypatch,backend)
    payload=dict(binding=binding(),run_id='attempt-1',**extra)
    response=execute(service,envelope(operation,payload))
    assert response['ok'] is True and key in response['result']
    assert response['result']['physical_binding_sha256']=='9'*64
    assert [op for op,p in backend.calls]==(
        ['status',operation] if operation in {'cancel','validate'} else [operation])


@pytest.mark.parametrize('operation,extra',[
    ('status',{}),('collect',{}),('cancel',{'reason':'fixture stop'}),
    ('validate',{'argv':['/usr/bin/true'],'timeout_seconds':1}),
])
def test_extra_backend_fields_are_refused_on_all_operation_receipts(tmp_path,monkeypatch,operation,extra):
    class Extra(Backend):
        async def execute(self,op,payload):
            result=await super().execute(op,payload);result['host_override']='another-host';return result
    service=broker(tmp_path,monkeypatch,Extra())
    with pytest.raises(api().BridgeProtocolError):execute(service,envelope(operation,dict(binding=binding(),run_id='attempt-1',**extra)))


def test_backend_typed_error_text_is_sanitized(tmp_path,monkeypatch):
    backend=Backend();backend.failure=api().BridgeProtocolError('CANCEL_UNAVAILABLE_USE_EXISTING_OWNER','private backend value')
    service=broker(tmp_path,monkeypatch,backend);service.peer_resolver=lambda sock:PeerCredentials(uid=450,gid=450)
    req=envelope('cancel',dict(binding=binding(),run_id='attempt-1',reason='fixture stop'));writer=Writer()
    asyncio.run(service.handle_connection(Reader(json.dumps(req).encode()+b'\n'),writer))
    assert json.loads(writer.written)['error']['code']=='CANCEL_UNAVAILABLE_USE_EXISTING_OWNER'
    assert b'private backend value' not in writer.written


def test_worker_broker_client_framing_interoperates_without_real_socket(tmp_path,monkeypatch):
    from control_plane.executive_worker_broker import WorkerBrokerClient
    service=broker(tmp_path,monkeypatch)
    class ExchangeWriter:
        def __init__(self):self.raw=b'';self.response=None
        def write(self,raw):self.raw+=raw
        async def drain(self):
            request=api().decode_request(self.raw,max_bytes=service.config.max_request_bytes)
            response=await service.execute(request,peer=PeerCredentials(uid=450,gid=450))
            self.response=json.dumps(response).encode()+b'\n'
        def close(self):pass
        async def wait_closed(self):pass
    class ExchangeReader:
        def __init__(self,writer):self.writer=writer
        async def readline(self):return self.writer.response
    async def connect(path,**kwargs):
        assert path==str(service.config.socket_path)
        writer=ExchangeWriter();return ExchangeReader(writer),writer
    monkeypatch.setattr(asyncio,'open_unix_connection',connect)
    client=WorkerBrokerClient(service.config.socket_path)
    response=asyncio.run(client.request('start',command_envelope()['payload']))
    assert response['adapter_id']=='attended-fabric'
    assert response['process_ref']['run_id']=='attempt-1'


def test_cancel_and_validation_never_select_shell_or_alternate_run(tmp_path,monkeypatch):
    backend=Backend();service=broker(tmp_path,monkeypatch,backend)
    with pytest.raises(api().BridgeProtocolError):
        execute(service,envelope('validate',dict(binding=binding(),run_id='attempt-1',argv=['/bin/sh','-c','anything'],timeout_seconds=1)))
    with pytest.raises(api().BridgeProtocolError):
        execute(service,envelope('cancel',dict(binding=binding(),run_id='other-attempt',reason='fixture')))
    assert backend.calls==[]


def test_backend_first_use_proof_with_extra_fields_cannot_authorize_start(tmp_path,monkeypatch):
    class ExtraProof(Backend):
        async def execute(self,op,payload):
            result=await super().execute(op,payload)
            if op=='status':result['authority_override']='ADMIN'
            return result
    backend=ExtraProof();service=broker(tmp_path,monkeypatch,backend)
    with pytest.raises(api().BridgeProtocolError,match='EFFECT_UNKNOWN'):execute(service,envelope())
    assert [op for op,p in backend.calls]==['status']
