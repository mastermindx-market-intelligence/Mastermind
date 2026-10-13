"""Inert bridge contract and canonical Runtime launch-fence regressions."""
import asyncio
import copy
import dataclasses
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest
from control_plane import executive_fabric_adapter as module
from control_plane.executive_worker_broker import BrokerProtocolError, BrokerStateError
from control_plane.worker_execution_contract import OrchestrationLaunchSpec
from test_executive_fabric_bridge_broker import start_payload, start_result
from test_remote_attempt_transport import _claimed_runtime


def physical():
    return module.FabricHostBinding(socket_path='/var/run/mastermind/fabric.sock',
        host_ref='host-'+'1'*64,worker_id='worker-1',worker_uid=1001,worker_gid=1001,
        provider='fixture',model='fixture-model',worker_source_config_digest='2'*64,
        execution_profile_digest='3'*64,service_source_sha256='4'*64,
        provider_home='/srv/fabric/provider',binary_sha256='e'*64,permission_profile_sha256='f'*64,
        bridge_uid=501)


def test_bridge_principal_requires_explicit_binding():
    fields=dataclasses.asdict(physical())
    fields.pop('bridge_uid')
    with pytest.raises(TypeError,match='bridge_uid'):
        module.FabricHostBinding(**fields)


@pytest.mark.parametrize('bridge_uid',[None,True,0,-1,450])
def test_bridge_principal_refuses_invalid_or_control_identity(bridge_uid):
    with pytest.raises(BrokerStateError,match='explicit non-Control principal'):
        dataclasses.replace(physical(),bridge_uid=bridge_uid)


def test_explicit_bridge_principal_participates_in_route_digest():
    pinned=physical()
    alternate=dataclasses.replace(pinned,bridge_uid=502)
    assert alternate.bridge_uid==502
    assert alternate.digest!=pinned.digest


def test_client_authenticates_exact_bound_bridge_principal(monkeypatch):
    pinned=dataclasses.replace(physical(),bridge_uid=502)
    monkeypatch.setattr(Path,'stat',lambda path:SimpleNamespace(
        st_mode=stat.S_IFDIR|0o755,st_uid=0))
    monkeypatch.setattr(Path,'lstat',lambda path:SimpleNamespace(
        st_mode=stat.S_IFSOCK|0o660,st_uid=0))
    captured={}
    def client(path,**kwargs):
        captured.update(path=path,**kwargs)
        return captured
    monkeypatch.setattr(module,'WorkerBrokerClient',client)
    assert module._fixed_client(pinned)['expected_peer_uid']==502


def test_broker_identity_uses_protected_binding_without_default_fallback(tmp_path,monkeypatch):
    import test_executive_fabric_bridge_broker as fixtures
    bridge=fixtures.api()
    document=fixtures.config_document()
    document['bridge_uid']=502
    monkeypatch.setattr(fixtures,'config_document',lambda:document)
    config=fixtures.config(tmp_path,monkeypatch)
    service=bridge.FabricBridgeBroker(config,fixtures.Backend())
    monkeypatch.setattr(bridge.os,'geteuid',lambda:501)
    with pytest.raises(bridge.BridgeProtocolError,match='BridgeIdentityError'):
        service.require_service_identity()
    monkeypatch.setattr(bridge.os,'geteuid',lambda:502)
    assert service.require_service_identity() is None
    assert service._authorize_peer(fixtures.PeerCredentials(uid=450,gid=450)) is None
    with pytest.raises(bridge.BridgeProtocolError,match='PeerAuthorizationError'):
        service._authorize_peer(fixtures.PeerCredentials(uid=502,gid=450))


@pytest.mark.parametrize('bridge_uid',[None,True,0,-1,450])
def test_broker_binding_refuses_invalid_or_control_principal(bridge_uid):
    import test_executive_fabric_bridge_broker as fixtures
    document=fixtures.config_document()
    document['bridge_uid']=bridge_uid
    with pytest.raises(fixtures.api().BridgeProtocolError,match='ConfigTrustError'):
        fixtures.api().BridgeConfig.from_document(document)


def payload():
    p=start_payload()
    p['physical_binding_sha256']=physical().digest
    p['launch_spec'].update(secret_canary_verdict={'passed':True}, expected_worker_uid=1001,expected_worker_gid=1001)
    return p


def result(p):
    r=start_result(p)
    r['physical_binding_sha256']=physical().digest
    return r


def test_full_receipt_binds_remote_worker_not_bridge_pid():
    p=payload(); r=result(p)
    ref,att=module.validate_start_result(r,payload=p,physical=physical())
    assert ref.effective_uid==1001 and ref.pid==1234
    assert att['process_identity']['effective_uid']!=physical().bridge_uid


@pytest.mark.parametrize('damage',[
    lambda r:r['binding'].update(root_id='other-parent'),
    lambda r:r['binding'].update(effective_grant_digest='9'*64),
    lambda r:r.update(request_sha256='9'*64),
    lambda r:r.update(physical_binding_sha256='9'*64),
    lambda r:r['process_ref'].update(pid=True),
    lambda r:r['process_ref'].update(real_uid=501),
    lambda r:r['process_ref'].update(process_start_identity=''),
    lambda r:r['process_ref'].update(launch_nonce=''),
    lambda r:r['process_ref']['binary'].update(sha256='0'*64),
    lambda r:r['launch_attestation'].update(phase='PRE_EXEC_HANDSHAKE'),
    lambda r:r['launch_attestation'].update(effective_grant_digest='a'*64),
    lambda r:r['launch_attestation'].update(prompt_sha256='0'*64),
    lambda r:r['launch_attestation'].update(isolation_manifest_sha256='0'*64),
    lambda r:r['launch_attestation'].update(permission_profile_sha256='0'*64),
    lambda r:r['launch_attestation']['provider_home_identity'].update(path='/other/home'),
    lambda r:r['launch_attestation']['workspace_identity'].update(path='/other/workspace'),
    lambda r:r['launch_attestation'].update(secret_canary_verdict={}),
    lambda r:r['launch_attestation'].update(rendered_argv=['/bin/sh']),
    lambda r:r['process_ref'].update(stdout_path='/srv/fabric/runs/attempt-1/../other/out'),
])
def test_wrong_parent_grant_route_process_or_isolation_never_accepted(damage):
    p=payload();r=copy.deepcopy(result(p));damage(r)
    with pytest.raises((BrokerStateError,BrokerProtocolError)):
        module.validate_start_result(r,payload=p,physical=physical())


def _fixture(tmp_path,monkeypatch,client):
    runtime,job,lease=_claimed_runtime(tmp_path)
    p=payload();p['binding'].update(attempt_id=lease.attempt.attempt_id,job_id=job.job_id)
    p['launch_spec'].update(run_id=lease.attempt.attempt_id,job_id=job.job_id,worker_id=lease.attempt.worker_id)
    spec=OrchestrationLaunchSpec(**{**p['launch_spec'],
        'workspace_path':Path(p['launch_spec']['workspace_path']),
        'run_dir':Path(p['launch_spec']['run_dir']),
        'result_schema_path':Path(p['launch_spec']['result_schema_path'])})
    adapter=module.AttendedFabricWorkerAdapter(runtime,lambda h,w:physical(),client_factory=lambda b:client,
                                                heartbeat_interval_seconds=.01)
    # Unit fixture replaces only physical/provenance resolution. Canonical
    # Runtime pin, token, versions and heartbeats remain real SQLite operations.
    monkeypatch.setattr(adapter,'_resolve',lambda s,launch:(runtime.attempts.get_attempt(s.run_id),physical(),p))
    return runtime,job,lease,adapter,spec,p


def test_lost_start_reply_cannot_launch_again_even_with_fresh_adapter(tmp_path,monkeypatch):
    class LostClient:
        calls=0
        async def request(self,op,p,**kwargs):
            self.calls+=1
            raise ConnectionResetError('inert lost acknowledgement')
    c=LostClient();rt,job,lease,a,s,p=_fixture(tmp_path,monkeypatch,c)
    with pytest.raises(ConnectionResetError):asyncio.run(a.start(s,lease=lease))
    # Reopen facade, preserving canonical Runtime state. Same id is never retried.
    b=module.AttendedFabricWorkerAdapter(rt,lambda h,w:physical(),client_factory=lambda x:c)
    monkeypatch.setattr(b,'_resolve',a._resolve)
    fresh=dataclasses.replace(lease,attempt=rt.attempts.get_attempt(s.run_id))
    with pytest.raises(Exception,match='already attempted'):
        asyncio.run(b.start(s,lease=fresh))
    assert c.calls==1
    assert rt.attempts.get_attempt(s.run_id).launch_metadata[module.REMOTE_LAUNCH_IDENTITY_KEY]


def test_launch_wait_heartbeats_and_stale_lease_reply_is_not_accepted(tmp_path,monkeypatch):
    class SlowClient:
        async def request(self,op,p,**kwargs):
            await asyncio.sleep(.04)
            return {}
    rt,job,lease,a,s,p=_fixture(tmp_path,monkeypatch,SlowClient())
    original=rt.attempts.validate_pinned_remote_launch
    observed=[]
    def validate(pinned,**kw):
        current=original(pinned,**kw);observed.append(current.version)
        if len(observed)>2:raise BrokerStateError('stale lease fixture')
        return current
    monkeypatch.setattr(rt.attempts,'validate_pinned_remote_launch',validate)
    with pytest.raises(BrokerStateError,match='stale lease'):
        asyncio.run(a.start(s,lease=lease))
    assert len(set(observed))>=2
    assert not a._refs
    assert rt.attempts.get_attempt(s.run_id).pid is None


def test_no_local_process_probe_or_shared_uid_sweep(tmp_path):
    rt,job,lease=_claimed_runtime(tmp_path)
    a=module.AttendedFabricWorkerAdapter(rt,lambda h,w:physical())
    assert not hasattr(a,'uid_sweep_receipt')
    with pytest.raises(BrokerStateError):a.inspector.identity(1234)


def test_live_claim_resolver_preserves_canonical_root_and_refuses_route_drift(tmp_path,monkeypatch):
    rt,job,lease=_claimed_runtime(tmp_path)
    real_read=module._read_claim
    j,a,q,join=real_read(rt,job_id=job.job_id,attempt_id=lease.attempt.attempt_id,
                        purpose=module.RemoteTransportPurpose.LAUNCH)
    j=dataclasses.replace(j,constraints={**j.constraints,'execution_profile_digest':'3'*64})
    a=dataclasses.replace(a,effective_grant_digest='a'*64)
    host=dataclasses.replace(physical(),host_ref=join.capacity_join.host_ref,
        worker_id=a.worker_id,provider=q.provider,
        worker_source_config_digest=join.capacity_join.worker_source_config_digest)
    spec=OrchestrationLaunchSpec(**{**payload()['launch_spec'],
        'run_id':a.attempt_id,'job_id':j.job_id,'worker_id':a.worker_id})
    monkeypatch.setattr(module,'_read_claim',lambda *args,**kwargs:(j,a,q,join))
    monkeypatch.setattr(module,'_dialogue_source_from_root_creation',lambda conn,root_job_id:
                        SimpleNamespace(commission_ref=SimpleNamespace(content_sha256='b'*64)))
    adapter=module.AttendedFabricWorkerAdapter(rt,lambda h,w:host)
    _,bound,wire=adapter._resolve(spec,launch=True)
    assert wire['binding']['root_id']==j.root_job_id
    assert wire['binding']['attempt_id']==a.attempt_id
    assert bound.worker_id==a.worker_id
    adapter.binding_source=lambda h,w:dataclasses.replace(host,host_ref='wrong-host')
    with pytest.raises(BrokerStateError,match='physical route'):
        adapter._resolve(spec,launch=True)
    adapter.binding_source=lambda h,w:host
    with pytest.raises(BrokerStateError,match='lost its Runtime grant'):
        adapter._resolve(dataclasses.replace(spec,effective_grant_digest='0'*64),launch=True)
