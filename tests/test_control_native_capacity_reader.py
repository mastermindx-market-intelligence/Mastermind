"""Fixed Control reader -> actual async client -> worker Bridge -> source owner.

OS peer/custody boundaries and Control startup definition are fixture-owned;
wire framing, nonce, source/realm/boot joins and the actual worker producer run.
No service, provider, credential or Runtime effect is performed.
"""
import asyncio
import copy
import dataclasses
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace

import pytest

from control_plane import executive_fabric_adapter as adapter
from control_plane import executive_worker_broker as broker
from control_plane.fabric_attended_canary import AttendedControlProbeSource
from ops.executive_os.capacity_source_contract import CapacitySourceContractError
from tests.test_native_capacity_identity_producer import native, bound, enrolled


@pytest.fixture
def reader(native, monkeypatch):
    raw = {'fabric_attended_probe': {'worker_config_path': str(native.bound.f.path)}}
    attestation = {'config_sha256': 'a'*64}
    probe = AttendedControlProbeSource(Path('/fixture/control.json'), 'a'*64, 'b'*64, 'c'*64)
    physical = native.backend._resources.physical
    calls = []
    def configuration(self, selected):
        assert self is probe and selected is physical
        calls.append('configuration')
        return copy.deepcopy(raw), copy.deepcopy(native.bound.f.config), copy.deepcopy(attestation)
    monkeypatch.setattr(AttendedControlProbeSource, 'configuration', configuration)
    holder = SimpleNamespace(native=native, probe=probe, physical=physical, raw=raw,
                             calls=calls, requests=[], fault=None)

    class FixedClient:
        async def request(self, operation, payload):
            assert operation == 'native-capacity-observation'
            assert set(payload) == {'nonce'}
            holder.requests.append(copy.deepcopy(payload))
            request = dict(native.request, payload=payload)
            response = await native.service.execute(request,
                peer=broker.PeerCredentials(uid=450, gid=450))
            result = copy.deepcopy(response['result'])
            if holder.fault == 'nonce': result['nonce'] = 'f'*32
            if holder.fault == 'extra': result['path'] = '/caller/path'
            if holder.fault in ('host_ref', 'boot_ref', 'source_receipt_digest', 'enrollment_receipt_digest'):
                k = holder.fault
                result['observation'][k] = ('host-' if k=='host_ref' else 'boot-' if k=='boot_ref' else '')+'9'*64
            if holder.fault in ('capability_generation', 'realm_generation'):
                result['observation'][holder.fault] += 1
            if holder.fault == 'stale':
                result['observation']['observed_at'] = (datetime.now(UTC)-timedelta(minutes=1)).isoformat(timespec='milliseconds').replace('+00:00','Z')
            if holder.fault == 'future':
                result['observation']['observed_at'] = (datetime.now(UTC)+timedelta(minutes=1)).isoformat(timespec='milliseconds').replace('+00:00','Z')
            if holder.fault == 'source-change': native.bound.f.path.write_text('{}')
            return result

    def fixed(selected):
        assert selected is physical
        return FixedClient()
    monkeypatch.setattr(adapter, '_fixed_client', fixed)
    return holder


def query(reader):
    return asyncio.run(reader.probe.native_observation(reader.physical))


@pytest.fixture
def short_socket():
    # Darwin AF_UNIX excludes long pytest node paths. Only this disposable
    # socket fixture is short; no repository/project source is placed here.
    with tempfile.TemporaryDirectory(prefix='ncr-', dir='/tmp') as directory:
        yield Path(directory)/'s'


def test_current_control_owner_acquires_exact_worker_source_and_boot(reader):
    value = query(reader)
    assert value['host_ref'] == reader.physical.host_ref
    assert value['capability_generation'] == 3 and value['realm_generation'] == 2
    assert value['realm_auth']['state'] == value['provider_health']['state'] == 'unknown'
    assert len(reader.requests) == 1
    assert reader.native.backend._backend is None and reader.native.backend._attempted is False


@pytest.mark.parametrize('fault', ['nonce', 'extra', 'host_ref', 'boot_ref',
    'source_receipt_digest', 'enrollment_receipt_digest', 'capability_generation',
    'realm_generation', 'stale', 'future', 'source-change'])
def test_noncurrent_or_substituted_result_refuses_without_retry(reader, fault):
    reader.fault = fault
    with pytest.raises((ValueError, broker.BrokerStateError)): query(reader)
    assert len(reader.requests) == 1 and reader.native.backend._attempted is False


def test_without_enrollment_no_query_is_sent(reader):
    del reader.native.bound.f.config['native_capacity_enrollment']
    with pytest.raises(broker.BrokerStateError): query(reader)
    assert reader.requests == []


@pytest.mark.parametrize('fault', ['elapsed', 'wall-jump', 'expired-revalidation'])
def test_entire_read_and_revalidation_interval_is_bounded(reader, monkeypatch, fault):
    base = time.time_ns()
    wall = iter((base, base + (5_000_000_000 if fault=='wall-jump' else 0), base))
    mono = iter((0, 20_000_000_000 if fault=='elapsed' else 0,
                 20_000_000_000 if fault=='expired-revalidation' else 0))
    monkeypatch.setattr(time, 'time_ns', lambda: next(wall))
    monkeypatch.setattr(time, 'monotonic_ns', lambda: next(mono))
    with pytest.raises(broker.BrokerStateError): query(reader)
    assert len(reader.requests) == 1 and reader.native.backend._attempted is False


def test_no_forged_control_source_can_read_registration(reader):
    from ops.executive_os.capacity_source_contract import acquire_control_native_registration
    with pytest.raises(CapacitySourceContractError, match='OWNER_REQUIRED'):
        acquire_control_native_registration(SimpleNamespace(), reader.physical)


def test_real_async_client_frames_and_authenticates_the_query(reader, monkeypatch, short_socket):
    path = short_socket
    captured = []
    monkeypatch.setattr(broker, 'get_peer_credentials',
        lambda _socket: broker.PeerCredentials(uid=470, gid=470))

    async def run():
        async def handler(stream, writer):
            try:
                request = json.loads(await stream.readline())
                captured.append(request)
                response = await reader.native.service.execute(request,
                    peer=broker.PeerCredentials(uid=450, gid=450))
                writer.write(json.dumps(response).encode()+b'\n')
                await writer.drain()
            finally:
                writer.close(); await writer.wait_closed()
        service = await asyncio.start_unix_server(handler, path=str(path))
        client = broker.WorkerBrokerClient(path, expected_peer_uid=470)
        monkeypatch.setattr(adapter, '_fixed_client', lambda _physical: client)
        try:
            return await reader.probe.native_observation(reader.physical)
        finally:
            service.close(); await service.wait_closed()
    value = asyncio.run(run())
    assert value['capability_generation'] == 3
    assert len(captured) == 1 and captured[0]['operation'] == 'native-capacity-observation'
    assert set(captured[0]['payload']) == {'nonce'}


def test_wrong_real_client_peer_stops_before_query_write(reader, monkeypatch, short_socket):
    path = short_socket; written=[]
    monkeypatch.setattr(broker, 'get_peer_credentials',
        lambda _socket: broker.PeerCredentials(uid=471, gid=471))
    async def run():
        async def handler(stream, writer):
            try: written.append(await stream.readline())
            finally: writer.close(); await writer.wait_closed()
        service=await asyncio.start_unix_server(handler,path=str(path))
        monkeypatch.setattr(adapter,'_fixed_client',lambda _p:broker.WorkerBrokerClient(path,expected_peer_uid=470))
        try:
            with pytest.raises(broker.PeerAuthorizationError):
                await reader.probe.native_observation(reader.physical)
            await asyncio.sleep(0)
        finally: service.close(); await service.wait_closed()
    asyncio.run(run())
    assert not any(written)
