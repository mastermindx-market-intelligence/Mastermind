"""Real private control-socket reads; no provider calls or live Runtime changes."""
from __future__ import annotations

import asyncio
import os

import pytest

from test_executive_service import _service, _request
from test_executive_quota_rollover_runtime import _fixture as _quota_fixture


def test_original_root_triage_roundtrips_through_existing_authenticated_socket(tmp_path, short_socket_root):
    async def exercise():
        _runtime, root, job, attempt = _quota_fixture(tmp_path / "runtime")
        service, _holder = _service(tmp_path, socket_root=short_socket_root)
        await service.start()
        try:
            runtime = service._require_runtime()
            before = len(runtime.events.list_events())
            reply = await _request(service, "session-recovery", {"root_job_id": root.job_id, "limit": 100})
            assert reply["ok"] is True, reply
            view = reply["result"]
            assert view["root_job_id"] == root.job_id
            assert view["operation_performed"] is False
            assert view["authority_effect"] == "NONE"
            assert view["count_by_action"] == {"REQUEUE_WITH_EXISTING_COO": 1}
            assert view["jobs"][0]["attempt_id"] == attempt.attempt_id
            assert view["jobs"][0]["checkpoint_available"] is True
            assert runtime.jobs.get_job(job.job_id).status.value == "RATE_LIMITED"
            assert runtime.jobs.get_job(job.job_id).attempt_count == 1
            assert len(runtime.events.list_events()) == before
        finally:
            await service.close()
    asyncio.run(exercise())


@pytest.mark.parametrize("args", [
    {}, {"root_job_id": "JOB-001"},
    {"root_job_id": "JOB-001", "limit": 0},
    {"root_job_id": "JOB-001", "limit": 501},
    {"root_job_id": "JOB-001", "limit": True},
    {"root_job_id": "JOB-001", "limit": "30"},
    {"root_job_id": "JOB-001", "limit": 100, "provider": "grok"},
    {"root_job_id": "../arbitrary", "limit": 100},
])
def test_recovery_socket_refuses_malformed_or_authority_shaped_arguments(tmp_path, short_socket_root, args):
    async def exercise():
        service, _holder = _service(tmp_path, socket_root=short_socket_root)
        await service.start()
        try:
            reply = await _request(service, "session-recovery", args)
            assert reply["ok"] is False
            assert reply["error"]["code"] == "request_failed"
        finally:
            await service.close()
    asyncio.run(exercise())


def test_child_id_cannot_be_used_as_an_original_root(tmp_path, short_socket_root):
    async def exercise():
        _runtime, root, job, attempt = _quota_fixture(tmp_path / "runtime")
        service, _holder = _service(tmp_path, socket_root=short_socket_root)
        await service.start()
        try:
            reply = await _request(service, "session-recovery", {"root_job_id": job.job_id, "limit": 30})
            assert reply["ok"] is False
            assert "original root" in reply["error"]["message"]
        finally:
            await service.close()
    asyncio.run(exercise())


@pytest.mark.parametrize("unknown_peer", [False, True])
def test_triage_preserves_existing_kernel_peer_authorization(tmp_path, short_socket_root, monkeypatch, unknown_peer):
    async def exercise():
        service, _holder = _service(tmp_path, socket_root=short_socket_root)
        await service.start()
        try:
            monkeypatch.setattr("control_plane.executive_service._peer_uid",
                lambda _connection: None if unknown_peer else os.geteuid() + 123)
            reply = await _request(service, "session-recovery", {"root_job_id": "JOB-001", "limit": 30})
            assert reply["ok"] is False
            assert reply["error"]["code"] == ("peer_credentials_unavailable" if unknown_peer else "peer_denied")
        finally:
            await service.close()
    asyncio.run(exercise())


def test_triage_does_not_bypass_existing_service_readiness_gate(tmp_path, short_socket_root):
    async def exercise():
        service, _holder = _service(tmp_path, socket_root=short_socket_root)
        await service.start()
        try:
            service._service_state = "AWAITING_CANARY"
            reply = await _request(service, "session-recovery", {"root_job_id": "JOB-001", "limit": 30})
            assert reply["ok"] is False
            assert "AWAITING_CANARY" in reply["error"]["message"]
        finally:
            await service.close()
    asyncio.run(exercise())
