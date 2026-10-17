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


def test_worker_paging_roundtrips_through_original_control_socket(tmp_path, short_socket_root):
    from test_executive_session_recovery_paging import _fleet
    async def exercise():
        runtime, root, job, attempt = _fleet(tmp_path / "runtime", size=30)
        service, _holder = _service(tmp_path, socket_root=short_socket_root)
        await service.start()
        try:
            cursor = None
            observed = []
            for _ in range(3):
                args = {"root_job_id": root.job_id, "limit": 11}
                if cursor is not None:
                    args["after_job_id"] = cursor
                reply = await _request(service, "session-recovery", args)
                assert reply["ok"] is True, reply
                view = reply["result"]
                observed.extend(item["job_id"] for item in view["jobs"])
                cursor = view["next_after_job_id"]
            assert len(set(observed)) == len(observed) == 30
            assert cursor is None
            assert service._require_runtime().jobs.get_job(job.job_id).current_attempt_id == attempt.attempt_id
        finally:
            await service.close()
    asyncio.run(exercise())


def test_paging_keeps_exact_args_and_root_membership_guards(tmp_path, short_socket_root):
    async def exercise():
        runtime, root, job, attempt = _quota_fixture(tmp_path / "runtime")
        service, _holder = _service(tmp_path, socket_root=short_socket_root)
        await service.start()
        try:
            for extra in ({"after_job_id": "MISSING"}, {"after_job_id": root.job_id},
                          {"after_job_id": job.job_id, "dispatch": True}, {"after_job_id": None}):
                reply = await _request(service, "session-recovery", {"root_job_id": root.job_id, "limit": 30, **extra})
                assert reply["ok"] is False
        finally:
            await service.close()
    asyncio.run(exercise())


def test_existing_socket_returns_all_thirty_workers_with_route_diagnostics(tmp_path, short_socket_root):
    from test_executive_session_recovery_paging import _fleet
    async def exercise():
        runtime, root, job, attempt = _fleet(tmp_path / "runtime", size=30)
        service, _holder = _service(tmp_path, socket_root=short_socket_root)
        await service.start()
        try:
            reply = await _request(service, "session-recovery", {"root_job_id": root.job_id, "limit": 30})
            assert reply["ok"] is True, reply
            view = reply["result"]
            assert view["included_count"] == view["total_jobs"] == 30
            assert view["has_more"] is False
            original = next(item for item in view["jobs"] if item["job_id"] == job.job_id)
            assert original["current_worker_id"] == "pool-a"
            assert original["current_pool_status"] == "RATE_LIMITED"
            assert original["attempts_remaining"] == 1
            assert original["capacity_assessment"] == "NOT_EVALUATED"
            assert service._require_runtime().jobs.get_job(job.job_id).current_attempt_id == attempt.attempt_id
        finally:
            await service.close()
    asyncio.run(exercise())
