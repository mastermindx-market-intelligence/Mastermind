"""Actual Unix transport: the result adapter over the existing
ExecutiveControlService / CeoIngress path with operation-specific response
ceiling.
"""
from __future__ import annotations

import asyncio
import os

import pytest

from control_plane.executive_service import CeoIngressAppBinding, ExecutiveControlService
from integrations.mastermind_workspace_app.contract import (
    FRAME_SCHEMA_V2, MAX_RESULT_RESPONSE_BYTES, canonical, error as envelope_error,
)
from integrations.mastermind_workspace_app.installed import CeoIngressWorkspaceClient
from tests.test_executive_ceo_ingress import (
    _FakeGrounding, _FakeSupervisor, _config, short_socket_root,
)


def control(tmp_path, short_socket_root, factory, *, app_uid=None):
    return ExecutiveControlService(
        _config(tmp_path, socket_root=short_socket_root),
        supervisor_factory=lambda _runtime: _FakeSupervisor(),
        ceo_ingress_socket_path=short_socket_root / "ceo.sock",
        ceo_ingress_peer_uid=os.geteuid() + 1000,
        ceo_ingress_grounding_provider=_FakeGrounding(),
        ceo_ingress_app_binding=CeoIngressAppBinding(
            peer_uid=os.geteuid() if app_uid is None else app_uid,
            armed=False,
            grounding_provider=_FakeGrounding(),
            workspace_read_provider_factory=factory,
        ),
    )


def result_frame():
    return {
        "schema": FRAME_SCHEMA_V2, "operation": "result",
        "selection": {"work_ref": "WS:ONE", "root_job_id": "JOB-001", "job_id": "JOB-001",
                       "attempt_id": "ATT-" + "0" * 32, "result_envelope_digest": "0" * 64},
        "principal": {"policy_id": "workspace-test", "issuer_digest": "a" * 64,
                       "subject_digest": "b" * 64, "client_ref": "fixture-web",
                       "resource": "https://mcp.mastermind-x.com/workspace/read",
                       "scopes": ["mastermind.workspace.read"]},
    }


def mission_v3_frame():
    return {
        "schema": FRAME_SCHEMA_V2, "operation": "mission_v3",
        "selection": {"work_ref": "WS:ONE", "root_job_id": "JOB-001"},
        "principal": {"policy_id": "workspace-test", "issuer_digest": "a" * 64,
                       "subject_digest": "b" * 64, "client_ref": "fixture-web",
                       "resource": "https://mcp.mastermind-x.com/workspace/read",
                       "scopes": ["mastermind.workspace.read"]},
    }


def test_result_socket_succeeds_within_16384_bytes(tmp_path, short_socket_root):
    body = {"schema": "mastermind.workspace_role_result.v1",
            "selection": {"work_ref": "WS:ONE", "root_job_id": "JOB-001",
                          "job_id": "JOB-001", "attempt_id": "ATT-" + "0" * 32,
                          "result_envelope_digest": "0" * 64},
            "availability": "AVAILABLE", "reason_codes": [],
            "source_observation": None, "result": {"ok": True}}
    async def run():
        svc = control(tmp_path, short_socket_root,
                      lambda _runtime: _FakeProvider({"ok": True, "result": body}))
        await svc.start()
        try:
            client = CeoIngressWorkspaceClient(svc.ceo_ingress_socket_path)
            response = await client.request(result_frame())
            assert response["result"]["availability"] == "AVAILABLE"
            socket_bytes = len(canonical(response)) + 1
            assert socket_bytes <= MAX_RESULT_RESPONSE_BYTES
        finally:
            await svc.close()
    asyncio.run(run())


def test_result_socket_refuses_above_16384_bytes(tmp_path, short_socket_root):
    async def run():
        svc = control(tmp_path, short_socket_root, lambda _runtime: _FakeProvider({"ok": True, "result": {"huge": "x" * 16384}}))
        await svc.start()
        try:
            client = CeoIngressWorkspaceClient(svc.ceo_ingress_socket_path)
            response = await client.request(result_frame())
            # The exact socket ceiling is the result 16384; an oversized
            # response is typed as source_unavailable, never truncated.
            assert response == envelope_error("source_unavailable", 503)
        finally:
            await svc.close()
    asyncio.run(run())


def test_mission_v3_socket_uses_2_000_000_byte_ceiling(tmp_path, short_socket_root):
    body = {'transport_fixture': 'x' * 40000}
    async def run():
        svc = control(tmp_path, short_socket_root, lambda _runtime: _FakeProvider({"ok": True, "result": body}))
        await svc.start()
        try:
            client = CeoIngressWorkspaceClient(svc.ceo_ingress_socket_path)
            response = await client.request(mission_v3_frame())
            assert response['result'] == body
        finally:
            await svc.close()
    asyncio.run(run())


def test_result_socket_returns_503_for_non_app_peer(tmp_path, short_socket_root):
    async def run():
        svc = control(tmp_path, short_socket_root, lambda _runtime: _FakeProvider({"ok": True, "result": {}}),
                      app_uid=os.geteuid() + 9999)
        await svc.start()
        try:
            client = CeoIngressWorkspaceClient(svc.ceo_ingress_socket_path)
            with pytest.raises(ValueError, match="source_unavailable"):
                await client.request(result_frame())
        finally:
            await svc.close()
    asyncio.run(run())


class _FakeProvider:
    def __init__(self, envelope):
        self.envelope = envelope

    async def handle_frame(self, _frame):
        return self.envelope

@pytest.mark.parametrize('size', [16383, 16384, 16385])
@pytest.mark.parametrize('unicode', [False, True])
def test_complete_socket_envelope_including_lf_boundary(tmp_path, short_socket_root, size, unicode):
    # Transport-only fixture: no result authority is inferred from padding.
    envelope = {'ok': True, 'result': {'padding': '漢' if unicode else ''}}
    envelope['result']['padding'] += 'x' * (size - len(canonical(envelope)) - 1)
    assert len(canonical(envelope)) + 1 == size
    async def run():
        svc = control(tmp_path, short_socket_root, lambda _: _FakeProvider(envelope))
        await svc.start()
        try:
            response = await CeoIngressWorkspaceClient(svc.ceo_ingress_socket_path).request(result_frame())
            if size <= 16384: assert response == envelope
            else: assert response == envelope_error('source_unavailable', 503)
        finally: await svc.close()
    asyncio.run(run())


def test_result_client_independently_refuses_oversized_peer(short_socket_root):
    # Independent receive gate, even if an upstream peer neglects its send cap.
    async def run():
        path = short_socket_root / 'oversized.sock'
        async def handler(reader, writer):
            try:
                await reader.readline()
                writer.write(canonical({'ok': True, 'result': {'padding': 'x' * 17000}}) + b'\n')
                await writer.drain()
            finally:
                writer.close(); await writer.wait_closed()
        server = await asyncio.start_unix_server(handler, path=str(path))
        try:
            with pytest.raises(ValueError, match='source_unavailable'):
                await CeoIngressWorkspaceClient(path).request(result_frame())
        finally:
            server.close(); await server.wait_closed()
    asyncio.run(run())
