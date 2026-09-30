"""Conditional #992 + #999 composition, entirely provider/network-free.

The real Runtime, resolver, fleet, facades and framed remote client execute.
Only connection I/O is replaced by an in-memory broker wire. No credentials,
provider process, installed service or production database is used.
"""
from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import json
from pathlib import Path
import pytest

from control_plane import remote_attempt_transport as rt
from control_plane import executive_worker_broker as broker
from control_plane.executive_runtime import Runtime
from control_plane.remote_worker_broker_client import RemoteWorkerBrokerClient
from control_plane.remote_worker_transport import REMOTE_BROKER_RESPONSE_SCHEMA, TransportError, TransportEffect, encode_frame
from control_plane.worker_execution_contract import WorkerRecoveryBinding, WorkerRunStatus
from control_plane.worker_adapter import adapter_descriptor
import test_remote_attempt_transport as fx
from test_native_claude_remote_fleet import _BrokerWire

CERT = b'composition-fixture-certificate'
WORKER = fx.WORKER  # Deliberately keep a Codex-looking name for the Claude proof.
PAIRS = [('codex', 'codex-cli'), ('anthropic', 'claude-code')]


class Wire:
    def __init__(self, adapter_id):
        self.start_wire = _BrokerWire(adapter_id)
        self.adapter_id = adapter_id
        self.calls = []
        self.opens = []
        self.process = None
        self.start_receipt = None
        self.lose_start = False
        self.lose_status = False
        self.observed_adapter_id = adapter_id
        self.result_identity_override = {}

    async def reply(self, client, request):
        self.calls.append((dict(client.identity), request))
        op, payload = request['broker_operation'], request['broker_request']
        if op == 'start':
            result = await self.start_wire.request(op, payload)
            self.start_receipt = result
            self.process = result['process_ref']
            if self.lose_start:
                raise OSError('fixture response lost after start write')
        elif op == 'status':
            if self.lose_status:
                raise OSError('fixture status response lost')
            result = {'adapter_id': self.observed_adapter_id, 'run': {'status':'RUNNING', 'process_ref': self.process}}
        elif op == 'collect':
            ref = self.process
            spec = self.start_wire.calls[0][1]['launch_spec']
            result = {'collection': {
                'process_ref': ref,
                'result': {'job_id': spec['job_id'], 'run_id': spec['run_id'], 'worker_id': spec['worker_id'],
                    'status':'SUCCEEDED', 'structured_output': {'summary':'fixture-result'}, 'artifact_manifest':[],
                    'git_manifest': {}, 'usage':{}, 'provider_session_id':ref['provider_session_id'], 'exit_code':0,
                    'started_at':ref['started_at'], 'finished_at':ref['started_at'], 'error':None},
                'stdout_sha256':'a'*64, 'stderr_sha256':'b'*64, 'result_sha256':'c'*64},
                'uid_sweep': self.start_receipt['startup_sweep']}
            result['collection']['result'].update(self.result_identity_override)
        else:
            raise AssertionError(op)
        response = {k:request[k] for k in ('host_ref','job_id','attempt_id','worker_id','operation_id','broker_operation','request_sha256')}
        response.update(schema=REMOTE_BROKER_RESPONSE_SCHEMA, outcome='ok', broker_response=result, observed_at_ms=1)
        return encode_frame(json.dumps(response,sort_keys=True,separators=(',',':')).encode())

    def install(self, monkeypatch):
        wire = self
        async def open_memory_connection(client):
            channel = Channel(client, wire)
            wire.opens.append(client)
            return channel, channel
        monkeypatch.setattr(RemoteWorkerBrokerClient, '_open_connection', open_memory_connection)


class Channel:
    def __init__(self, client, wire):
        self.client, self.wire = client, wire
        self.data = b''
        self.closed = False
    def get_extra_info(self, name):
        return self if name == 'ssl_object' else None
    def getpeercert(self, binary_form=False):
        return CERT if binary_form else {}
    def write(self, frame):
        assert len(frame) == 4 + int.from_bytes(frame[:4],'big')
        self.request = json.loads(frame[4:])
    async def drain(self):
        self.data = await self.wire.reply(self.client, self.request)
    async def readexactly(self, count):
        if len(self.data) < count:
            raise asyncio.IncompleteReadError(self.data,count)
        result, self.data = self.data[:count], self.data[count:]
        return result
    def close(self): self.closed = True
    async def wait_closed(self): pass


def claimed(tmp_path, provider):
    runtime = Runtime.at(tmp_path/'runtime')
    runtime.workers.register_worker(WORKER, provider=provider, account_label='fixture', worker_type='fixture',
        capabilities=['research'], quota_classes={fx.QUOTA:{'capabilities':['research'],'metadata':{'capacity_join':fx._join()}}})
    job=runtime.jobs.create_job('conditional remote composition', requested_authorities=['READ'],constraints={'eligible_quota_classes':[fx.QUOTA]},attempt_limit=1)
    lease=runtime.attempts.claim_job(job.job_id,worker_id=WORKER,quota_class=fx.QUOTA,lease_owner='composition-test')
    assert lease is not None
    return runtime,job,lease


def binding(tmp_path, adapter_id):
    original=fx._host_binding(tmp_path)
    return dataclasses.replace(original, adapter_id=adapter_id,
        transport=dataclasses.replace(original.transport, expected_server_fingerprint=hashlib.sha256(CERT).hexdigest()))


def setup(tmp_path, monkeypatch, provider, adapter_id):
    runtime,job,lease=claimed(tmp_path,provider)
    bound=binding(tmp_path,adapter_id)
    lookup=[]
    def source(host,worker):
        lookup.append((host,worker)); return bound
    wire=Wire(adapter_id);wire.install(monkeypatch)
    adapter=rt.AttemptBoundRemoteWorkerAdapter(runtime,source)
    spec=fx._spec(tmp_path,run_id=lease.attempt.attempt_id,job_id=job.job_id)
    return runtime,job,lease,bound,source,lookup,wire,adapter,spec


@pytest.mark.parametrize('provider,adapter_id',PAIRS)
def test_claim_to_real_client_launch_status_collect_keeps_parent_and_target(tmp_path,monkeypatch,provider,adapter_id):
    runtime,job,lease,bound,source,lookup,wire,adapter,spec=setup(tmp_path,monkeypatch,provider,adapter_id)
    async def exercise():
        ref=await adapter.start(spec)
        assert ref.binary.path == ('/fixtures/claude' if provider=='anthropic' else '/fixtures/codex')
        assert await adapter.status(ref) is WorkerRunStatus.RUNNING
        result=await adapter.collect_result(ref)
        assert result.result.job_id==job.job_id
        assert result.result.run_id==lease.attempt.attempt_id
        assert result.result.worker_id==WORKER
        assert result.result.structured_output['summary']=='fixture-result'
        return ref
    ref=asyncio.run(exercise())
    assert lookup==[(fx.HOST_A,WORKER)]
    assert [req['broker_operation'] for _,req in wire.calls]==['start','status','collect']
    for identity,req in wire.calls:
        assert identity==dict(host_ref=fx.HOST_A,job_id=job.job_id,attempt_id=ref.run_id,worker_id=WORKER,operation_id=ref.run_id)
        assert 'adapter_id' not in req['broker_request']  # no request-time provider selection
    assert runtime.jobs.get_job(job.job_id).current_attempt_id==ref.run_id
    assert adapter_descriptor('claude-code').implemented is False


@pytest.mark.parametrize('provider,adapter_id',[('anthropic','codex-cli'),('codex','claude-code'),('other','codex-cli')])
def test_mismatched_claim_provider_refuses_before_client_creation(tmp_path,monkeypatch,provider,adapter_id):
    runtime,job,lease=claimed(tmp_path,provider);bound=binding(tmp_path,adapter_id)
    calls=[]
    def no_client(*args,**kwargs):
        calls.append('constructed');raise AssertionError('client must not be built')
    monkeypatch.setattr(rt,'RemoteWorkerBrokerClient',no_client)
    with pytest.raises(rt.RemoteAttemptTransportError) as error:
        rt.resolve_remote_attempt_transport(runtime,job_id=job.job_id,attempt_id=lease.attempt.attempt_id,binding_source=lambda *_:bound)
    assert error.value.code=='PROVIDER_UNSUPPORTED'
    assert calls==[]


@pytest.mark.parametrize('bad',[None,True,'','claude','Claude-Code',' claude-code','claude-code ','unknown',[]])
def test_host_binding_adapter_is_closed_and_noncanonical_values_refuse(tmp_path,bad):
    with pytest.raises(rt.RemoteAttemptTransportError):
        binding(tmp_path,bad)


def test_trusted_adapter_binding_is_frozen(tmp_path):
    bound=binding(tmp_path,'claude-code')
    with pytest.raises(dataclasses.FrozenInstanceError): bound.adapter_id='codex-cli'


@pytest.mark.parametrize('provider,adapter_id',PAIRS)
def test_loss_after_start_keeps_original_carrier_and_no_second_start(tmp_path,monkeypatch,provider,adapter_id):
    runtime,job,lease,bound,source,lookup,wire,adapter,spec=setup(tmp_path,monkeypatch,provider,adapter_id)
    wire.lose_start=True
    with pytest.raises(TransportError) as error: asyncio.run(adapter.start(spec))
    assert error.value.classification is TransportEffect.EFFECT_UNKNOWN
    with pytest.raises(broker.BrokerStateError): asyncio.run(adapter.start(spec))
    assert len(wire.calls)==1 and len(lookup)==1


@pytest.mark.parametrize('provider,adapter_id',PAIRS)
def test_new_controller_recovers_same_process_and_has_no_start_permission(tmp_path,monkeypatch,provider,adapter_id):
    runtime,job,lease,bound,source,lookup,wire,old,spec=setup(tmp_path,monkeypatch,provider,adapter_id)
    ref=asyncio.run(old.start(spec))
    prompt=spec.run_dir/'input'/'worker-prompt.txt';prompt.parent.mkdir(parents=True);prompt.write_text(spec.prompt);prompt.chmod(0o600)
    recovery=WorkerRecoveryBinding.bind(adapter_id=old.adapter_id,spec=spec,process_ref=ref,prompt_path=prompt)
    fresh=rt.AttemptBoundRemoteWorkerAdapter(runtime,source)
    assert fresh.reattach(spec,recovery)==ref
    assert asyncio.run(fresh.status(ref)) is WorkerRunStatus.RUNNING
    with pytest.raises(broker.BrokerStateError): asyncio.run(fresh.start(spec))
    assert [req['broker_operation'] for _,req in wire.calls]==['start','status','status']
    recovered_client=wire.opens[-1]
    assert 'start' not in recovered_client.allowed_operations
    with pytest.raises(TransportError) as error: asyncio.run(recovered_client.request('start',{}))
    assert error.value.classification is TransportEffect.NO_EFFECT
    assert len(wire.calls)==3


@pytest.mark.parametrize('observed',['codex-cli',None,'claude-code '])
def test_native_wrong_status_adapter_refuses_without_restarting(tmp_path,monkeypatch,observed):
    _,_,_,_,_,lookup,wire,adapter,spec=setup(tmp_path,monkeypatch,'anthropic','claude-code')
    ref=asyncio.run(adapter.start(spec));wire.observed_adapter_id=observed
    with pytest.raises(broker.BrokerProtocolError): asyncio.run(adapter.status(ref))
    with pytest.raises(broker.BrokerStateError): asyncio.run(adapter.start(spec))
    assert len(wire.calls)==2 and len(lookup)==1


def test_native_payload_cannot_retarget_claimed_worker(tmp_path,monkeypatch):
    runtime,job,lease,bound,source,lookup,wire,_,spec=setup(tmp_path,monkeypatch,'anthropic','claude-code')
    resolution=rt.resolve_remote_attempt_transport(runtime,job_id=job.job_id,attempt_id=spec.run_id,binding_source=source)
    with pytest.raises(TransportError) as error:
        asyncio.run(resolution.client.request('start',{'launch_spec':{'run_id':spec.run_id,'job_id':job.job_id,'worker_id':'other'}}))
    assert error.value.classification is TransportEffect.NO_EFFECT
    assert not wire.opens and not wire.calls


def test_native_claim_movement_during_binding_resolution_refuses_before_io(tmp_path,monkeypatch):
    runtime,job,lease,bound,_,_,wire,_,spec=setup(tmp_path,monkeypatch,'anthropic','claude-code')
    def moving_source(*_):
        runtime.attempts.heartbeat_attempt(lease.attempt.attempt_id,fence_generation=lease.attempt.fence_generation,lease_token=lease.lease_token)
        return bound
    with pytest.raises(rt.RemoteAttemptTransportError) as error:
        rt.resolve_remote_attempt_transport(runtime,job_id=job.job_id,attempt_id=spec.run_id,binding_source=moving_source)
    assert error.value.code=='STATE_MOVED'
    assert not wire.opens and not wire.calls


@pytest.mark.parametrize('failure',['lost_response','wrong_process','wrong_adapter'])
def test_native_failed_recovery_cannot_issue_another_start(tmp_path,monkeypatch,failure):
    runtime,job,lease,bound,source,lookup,wire,old,spec=setup(tmp_path,monkeypatch,'anthropic','claude-code')
    ref=asyncio.run(old.start(spec))
    prompt=spec.run_dir/'input'/'worker-prompt.txt';prompt.parent.mkdir(parents=True);prompt.write_text(spec.prompt);prompt.chmod(0o600)
    recovery=WorkerRecoveryBinding.bind(adapter_id=old.adapter_id,spec=spec,process_ref=ref,prompt_path=prompt)
    if failure=='lost_response': wire.lose_status=True
    elif failure=='wrong_process': wire.process=dict(wire.process,launch_nonce='foreign-generation')
    else: wire.observed_adapter_id='codex-cli'
    fresh=rt.AttemptBoundRemoteWorkerAdapter(runtime,source)
    with pytest.raises((TransportError,broker.BrokerProtocolError)):
        fresh.reattach(spec,recovery)
    with pytest.raises(broker.BrokerStateError): asyncio.run(fresh.start(spec))
    assert [req['broker_operation'] for _,req in wire.calls]==['start','status']
    assert 'start' not in wire.opens[-1].allowed_operations


def test_relabelled_resolution_cannot_override_endpoint_facade(tmp_path,monkeypatch):
    runtime,job,lease,bound,source,lookup,wire,_,spec=setup(tmp_path,monkeypatch,'anthropic','claude-code')
    resolution=rt.resolve_remote_attempt_transport(runtime,job_id=job.job_id,attempt_id=spec.run_id,binding_source=source)
    with pytest.raises(rt.RemoteAttemptTransportError) as error:
        rt.build_attempt_bound_worker_fleet(dataclasses.replace(resolution,provider='codex'))
    assert error.value.code=='PROVIDER_UNSUPPORTED'
    assert not wire.opens


@pytest.mark.parametrize('provider,adapter_id',PAIRS)
@pytest.mark.parametrize('field',['job_id','run_id','worker_id'])
def test_correct_transport_envelope_cannot_hide_foreign_result_identity(tmp_path,monkeypatch,provider,adapter_id,field):
    runtime,job,lease,bound,source,lookup,wire,adapter,spec=setup(tmp_path,monkeypatch,provider,adapter_id)
    ref=asyncio.run(adapter.start(spec));wire.result_identity_override={field:'foreign-identity'}
    with pytest.raises(broker.BrokerProtocolError,match='result identity'):
        asyncio.run(adapter.collect_result(ref))
    assert [req['broker_operation'] for _,req in wire.calls]==['start','collect']
    with pytest.raises(broker.BrokerStateError): asyncio.run(adapter.start(spec))
