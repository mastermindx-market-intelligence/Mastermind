"""Control projection checks; no host/provider effects or invented admission.

Wire cases use inert source records. Producer case uses a real fresh foreground
scope and Runtime pin, with the remote Capacity boundary explicitly substituted.
"""
import asyncio
import copy
import dataclasses
from types import SimpleNamespace

import pytest

from control_plane import fabric_control_start as command
from control_plane import foreground_operation as foreground
from control_plane import remote_attempt_transport as transport
from control_plane.executive_capacity_join import CapacityJoin, RegisteredCapacityJoin
from control_plane.executive_fabric_bridge_broker import start_request_sha256
from control_plane.executive_worker_broker import PeerCredentials
from tests import test_foreground_operation as live
from test_fabric_control_start import request
from test_executive_fabric_adapter import _fixture, physical


def projected_request():
    payload = request()['payload']
    payload['control_start']['foreground_expires_at'] = 4070908800
    from control_plane.executive_capacity_join import PROVIDER_CAPACITY_SCHEMA
    payload['control_start']['owner_projection'] = {
        'attendance': {**payload['binding'],
            'physical_binding_sha256': payload['physical_binding_sha256'],
            'start_request_sha256': start_request_sha256(payload),
            'principal_identity': ['policy', 'issuer-digest', 'resource', 'subject', 'client'],
            'operation_key': 'original-foreground', 'arguments_sha256': '9' * 64},
        'capacity': {
            'registered_join': RegisteredCapacityJoin(payload['launch_spec']['worker_id'],
                'paid', 'anthropic', CapacityJoin(physical().host_ref, 'provider-slot',
                    PROVIDER_CAPACITY_SCHEMA, '8' * 64)).to_dict(),
            'active_job_id': payload['binding']['job_id'],
            'active_attempt_id': payload['binding']['attempt_id'],
            'fence_generation': payload['control_start']['fence_generation'], 'status': 'BUSY'}}
    return payload


def test_foreground_deadline_bounds_command_without_rewriting_runtime_lease():
    payload = projected_request()
    payload['control_start']['foreground_expires_at'] = 123
    lease = payload['control_start']['lease_expires_at']
    authority = command.authorize_control_command(payload, peer=PeerCredentials(uid=450,gid=450), now=122)
    assert authority.expires_at == 123 and payload['control_start']['lease_expires_at'] == lease
    with pytest.raises(command.ControlStartRefused): authority.require(payload, now=123)


def test_legacy_command_remains_unchanged_but_is_not_attended_evidence():
    payload = request()['payload']
    authority = command.authorize_control_command(payload, peer=PeerCredentials(uid=450, gid=450))
    authority.require(payload)
    with pytest.raises(command.ControlStartRefused, match='foreground_owner_projection_required'):
        authority.owner_projection(payload)


def test_authenticated_projection_is_copied_and_survives_existing_forwarding():
    payload = projected_request()
    expected = copy.deepcopy(payload['control_start']['owner_projection'])
    authority = command.authorize_control_command(payload, peer=PeerCredentials(uid=450, gid=450))
    payload['control_start']['owner_projection']['attendance']['root_id'] = 'changed'
    forwarded = {k: v for k, v in payload.items() if k != 'control_start'}
    forwarded['start_request_sha256'] = start_request_sha256(payload)
    assert authority.owner_projection(forwarded) == expected
    with pytest.raises(command.ControlStartRefused):
        dataclasses.replace(authority, _peer_verified=None).owner_projection(forwarded)


@pytest.mark.parametrize('field,value', [
    ('root_id', 'other'), ('attempt_id', 'other'),
    ('physical_binding_sha256', '0' * 64), ('start_request_sha256', '0' * 64),
    ('principal_identity', []), ('arguments_sha256', 'z' * 64),
])
def test_wrong_attendance_binding_is_refused(field, value):
    payload = projected_request()
    payload['control_start']['owner_projection']['attendance'][field] = value
    with pytest.raises(command.ControlStartRefused, match='control_owner_projection_mismatch'):
        command.authorize_control_command(payload, peer=PeerCredentials(uid=450, gid=450))


@pytest.mark.parametrize('field,value', [
    ('active_job_id', 'other'), ('active_attempt_id', 'other'),
    ('fence_generation', True), ('fence_generation', 2), ('status', 'AVAILABLE'),
])
def test_wrong_capacity_claim_is_refused(field, value):
    payload = projected_request()
    payload['control_start']['owner_projection']['capacity'][field] = value
    with pytest.raises(command.ControlStartRefused, match='control_owner_projection_mismatch'):
        command.authorize_control_command(payload, peer=PeerCredentials(uid=450, gid=450))


@pytest.mark.parametrize('fault', ['none', 'closed', 'capacity_moved', 'json_receipt', 'unix_closed', 'remote_closed', 'unix_json', 'remote_json', 'unix_missing', 'remote_missing', 'unix_drift', 'remote_drift', 'unix_live', 'remote_live'])
def test_actual_foreground_receipt_is_required_at_production_projection(tmp_path, monkeypatch, fault):
    class Capture:
        async def request(self, *args, **kwargs):
            raise AssertionError('this producer test must not transmit')
    runtime, job, lease, adapter, spec, payload = _fixture(tmp_path/'pin', monkeypatch, Capture())
    source_runtime = live.Runtime.at(tmp_path/'source')
    frame = live.frame('actual-projection-source')

    async def scenario():
        async with foreground._session_bridge_foreground_dispatch(source_runtime, frame, lambda: None) as operation:
            root = (await live.admit(source_runtime, tmp_path/'source-files', operation, frame))['job_id']
            with source_runtime.store.read() as connection:
                source = foreground._dialogue_source_from_root_creation(connection, root_job_id=root)
            payload['binding'].update(root_id=root, commission_sha256=source.commission_ref.content_sha256)
            pinned = runtime.attempts.pin_remote_launch_identity(spec.run_id,
                fence_generation=lease.attempt.fence_generation, lease_token=lease.lease_token,
                expected_version=lease.attempt.version, identity_digest=command.launch_identity(payload))
            attempt = runtime.attempts.validate_pinned_remote_launch(pinned, lease_token=lease.lease_token)
            # Actual remote Capacity/physical registration is not this local fixture.
            # The SQLite pin fixture is a non-orchestration Job. Substitute only
            # its remote grant projection, not a public or runtime admission.
            attempt = dataclasses.replace(attempt,
                effective_grant_digest=payload['binding']['effective_grant_digest'])
            projected_job = dataclasses.replace(job, root_job_id=root)
            current = [attempt]
            quota = runtime.workers.get_quota_class(attempt.worker_id, attempt.quota_class)
            from control_plane.executive_capacity_join import PROVIDER_CAPACITY_SCHEMA
            join = RegisteredCapacityJoin(attempt.worker_id, attempt.quota_class, quota.provider,
                CapacityJoin(physical().host_ref, 'slot', PROVIDER_CAPACITY_SCHEMA, '8'*64))
            def claim(*args, **kwargs): return projected_job, current[0], quota, join
            monkeypatch.setattr(foreground, '_read_claim', claim)
            monkeypatch.setattr(transport, '_read_claim', claim)
            receipt = operation.start_receipt(payload['binding'], physical().digest, start_request_sha256(payload))
            if fault.startswith(('unix_', 'remote_')):
                from control_plane.executive_worker_broker import WorkerBrokerClient
                from control_plane.remote_worker_broker_client import RemoteWorkerBrokerClient
                from control_plane.remote_worker_transport import TransportError, TransportEffect
                from test_remote_worker_broker_client import _binding, _Paths, _Reader, _Writer
                import json
                value = command.command_from_validated_pin(attempt, payload, runtime=runtime, foreground_receipt=receipt)
                assert value['foreground_expires_at'] == frame['principal']['expires_at']
                transmitted = {**payload, 'control_start':value}
                opened, release = asyncio.Event(), asyncio.Event()
                writer = _Writer()
                class EmptyReader(_Reader):
                    async def readline(self): return b''
                async def connect(*args, **kwargs):
                    opened.set(); await release.wait()
                    return EmptyReader(b''), writer
                if fault.startswith('unix_'):
                    client = WorkerBrokerClient(tmp_path/'inert.sock')
                    monkeypatch.setattr(asyncio, 'open_unix_connection', connect)
                else:
                    identity = dict(host_ref=physical().host_ref, worker_id=attempt.worker_id,
                        job_id=attempt.job_id, attempt_id=attempt.attempt_id, operation_id='original-prewrite')
                    for name in ('ca','cert','key'): (tmp_path/name).write_bytes(b'inert')
                    client = RemoteWorkerBrokerClient(_binding(_Paths(tmp_path/'ca',tmp_path/'cert',tmp_path/'key')),
                        identity, allowed_operations={'start'})
                    client._open_connection = connect
                supplied = receipt
                if fault.endswith('_json'): supplied = receipt.as_dict()
                if fault.endswith('_missing'): supplied = None
                if fault.endswith('_drift'):
                    transmitted['control_start']['owner_projection']['attendance']['operation_key'] = 'foreign'
                task = asyncio.create_task(client.request('start', transmitted, foreground_start_receipt=supplied))
                await opened.wait()
                if fault.endswith('_closed'): operation._mark_source_closed()
                # Mutation after encoding must never alter the captured frame.
                transmitted['control_start']['owner_projection']['attendance'] = receipt.as_dict()
                release.set()
                if fault.endswith('_live'):
                    # A live typed source permits the one transmission. The inert
                    # peer then returns EOF; this is not a worker execution proof.
                    with pytest.raises((TransportError, RuntimeError, ValueError)): await task
                    assert writer.written and writer.closed
                else:
                    with pytest.raises(TransportError) as refused: await task
                    assert refused.value.classification is TransportEffect.NO_EFFECT
                    assert writer.written == b'' and writer.closed
                assert runtime.attempts.get_attempt(attempt.attempt_id).launch_metadata == pinned.launch_metadata
                return
            if fault == 'closed': operation._mark_source_closed()
            if fault == 'capacity_moved': current[0] = dataclasses.replace(attempt, version=attempt.version + 1)
            if fault == 'json_receipt': receipt = receipt.as_dict()
            if fault != 'none':
                with pytest.raises((foreground.ForegroundOperationRefusal, command.ControlStartRefused)):
                    command.command_from_validated_pin(attempt, payload, runtime=runtime, foreground_receipt=receipt)
            else:
                value = command.command_from_validated_pin(attempt, payload, runtime=runtime, foreground_receipt=receipt)
                assert value['owner_projection']['attendance']['root_id'] == root
                assert value['owner_projection']['capacity']['active_attempt_id'] == spec.run_id
                assert lease.lease_token not in str(value)
    asyncio.run(scenario())


def test_present_closed_foreground_refuses_adapter_before_transmission(tmp_path, monkeypatch):
    class Capture:
        calls = 0
        async def request(self, *args, **kwargs): self.calls += 1
    client = Capture()
    runtime, job, lease, adapter, spec, payload = _fixture(tmp_path, monkeypatch, client)
    def closed(): raise foreground.ForegroundOperationClosed()
    monkeypatch.setattr(foreground, '_current_foreground_operation_or_none', closed)
    with pytest.raises(foreground.ForegroundOperationClosed):
        asyncio.run(adapter.start(spec, lease=lease))
    assert client.calls == 0
