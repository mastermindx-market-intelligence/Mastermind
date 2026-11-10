"""Real loopback TLS + Unix transport, with an inert retained-owner responder.

The test endpoint is not installed/admitted; no Runtime or provider is invoked.
The fixture Control responder proves routing, not filesystem sealing authority.
"""
import asyncio
import dataclasses
import json
import os
import ssl
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

from control_plane.executive_worker_broker import BROKER_RESPONSE_SCHEMA_VERSION
from control_plane import executive_fabric_composition as composition
from control_plane.remote_worker_transport import TransportError
from ops.executive_os import remote_worker_gateway as gateway_module
from ops.executive_os.capacity_broker_topology import CONTROL_UID
from ops.executive_os.remote_assignment_control import AssignmentControlBinding
from ops.executive_os.remote_worker_gateway import RemoteWorkerGateway
from ops.executive_os.remote_worker_gateway_config import RemoteWorkerGatewayConfig, REMOTE_WORKER_GATEWAY_CONFIG_SCHEMA
from test_executive_fabric_composition import binding, root_stats, installed
from test_fabric_remote_composition import payload
from tests.test_remote_worker_transport import _certificate_fixture
from tests.test_remote_worker_gateway import _cert_sha256


@asynccontextmanager
async def endpoint(tmp_path, monkeypatch, *, wrong_peer=False, wrong_server=False):
    ca_key, ca, _ = _certificate_fixture(tmp_path, name='fabric-ca',
        common_name='Fabric test CA', san='DNS:ca.invalid', ca=True)
    server_key, server_cert, _ = _certificate_fixture(tmp_path, name='fabric-server',
        common_name='localhost', san='IP:127.0.0.1,DNS:localhost', issuer_key=ca_key, issuer_cert=ca)
    client_key, client_cert, _ = _certificate_fixture(tmp_path, name='fabric-control',
        common_name='control', san='DNS:control.invalid', issuer_key=ca_key, issuer_cert=ca)
    calls = []
    async def owner(reader, writer):
        try:
            raw = await reader.readline()
            if not raw:
                return
            request = json.loads(raw); calls.append(request)
            response = dict(schema_version=BROKER_RESPONSE_SCHEMA_VERSION,
                request_id=request['request_id'], operation=request['operation'],
                ok=True, result={'echoed': request['payload']})
            writer.write((json.dumps(response) + '\n').encode()); await writer.drain()
        finally:
            writer.close(); await writer.wait_closed()
    sock = Path('/tmp') / ('fabric-test-' + uuid.uuid4().hex[:12] + '.sock')
    unix = await asyncio.start_unix_server(owner, path=str(sock))
    server = None
    try:
        route = binding(); route['bridge_uid'] = os.geteuid()
        peer_uid = os.geteuid() + int(wrong_peer)
        control_binding = AssignmentControlBinding(
            worker_id=route['worker_id'], control_uid=CONTROL_UID, control_gid=CONTROL_UID,
            worker_uid=peer_uid, worker_gid=CONTROL_UID + 1,
            workspace_root=tmp_path/'assignments', run_root=tmp_path/'runs')
        seals = []
        async def fixture_control(control, request, broker_call, *, fabric_target):
            assert control is control_binding and fabric_target is True
            packet = request['broker_request']
            seals.append(packet)
            # Keep the real TLS/Unix transports; only the filesystem owner is inert.
            for operation in ('assignment-seal-prepare', 'assignment-seal-commit'):
                assert await broker_call(operation, packet) == {'echoed': packet}
            return {'fixture_control_sealed': packet}
        monkeypatch.setattr(gateway_module, 'seal_original_assignment', fixture_control)
        gateway = RemoteWorkerGateway(RemoteWorkerGatewayConfig(
            schema=REMOTE_WORKER_GATEWAY_CONFIG_SCHEMA, host_ref=route['host_ref'],
            listen_host='127.0.0.1', listen_port=0, certificate_path=server_cert,
            key_path=server_key, ca_path=ca, expected_control_fingerprint=_cert_sha256(client_cert),
            broker_socket_path=sock, allowed_worker_ids={route['worker_id']},
            allowed_operations={'start', 'status', 'assignment-seal', 'assignment-seal-finalize'},
            broker_target='attended-fabric', expected_broker_peer_uid=peer_uid,
            assignment_control=control_binding))
        server = await gateway.start_server()
        _, port = server.sockets[0].getsockname()[:2]
        physical = composition.FabricHostBinding(**route)
        remote = dict(host_ref=route['host_ref'], worker_id=route['worker_id'],
            physical_binding_sha256=physical.digest, endpoint_host='127.0.0.1', endpoint_port=port,
            ca_path=str(ca), client_cert_path=str(client_cert), client_key_path=str(client_key),
            expected_server_fingerprint=('0'*64 if wrong_server else _cert_sha256(server_cert)),
            timeout_seconds=5)
        doc = dict(schema_version='mastermind.executive_fabric_bindings/v2',
                   bindings=[route], remote_transports=[remote])
        path, digest = installed(tmp_path, json.dumps(doc).encode())
        selected = composition.FabricBindingSource.from_path(path, digest)
        request = payload(physical)
        yield selected.client_for(physical, request), request, calls, seals
    finally:
        if server is not None:
            server.close(); await server.wait_closed()
        unix.close(); await unix.wait_closed(); sock.unlink(missing_ok=True)


def test_original_command_and_assignment_cross_existing_tls_and_unix(tmp_path, root_stats, monkeypatch):
    async def run():
        async with endpoint(tmp_path, monkeypatch) as (client, p, calls, seals):
            command = {**p, 'control_start': {'original': 'validated-projection'}}
            assert await client.request('start', command) == {'echoed': command}
            assert await client.request('assignment-seal', p) == {'fixture_control_sealed': p}
            assert await client.request('assignment-seal-finalize', p) == {'echoed': p}
            assert [r['operation'] for r in calls] == [
                'start', 'assignment-seal-prepare', 'assignment-seal-commit', 'assignment-seal-finalize']
            assert seals == [p]
            assert calls[0]['payload'] == command
    asyncio.run(run())


@pytest.mark.parametrize('defect', ['wrong_peer', 'wrong_server'])
def test_mismatched_enrolled_transport_never_reaches_owner(tmp_path, root_stats, monkeypatch, defect):
    async def run():
        async with endpoint(tmp_path, monkeypatch, **{defect: True}) as (client, p, calls, seals):
            with pytest.raises(TransportError):
                await client.request('status', p)
            assert calls == []
            assert seals == []
    asyncio.run(run())
