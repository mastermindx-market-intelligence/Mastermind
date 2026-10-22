"""Hermetic exact-UID socket contract, not proof of the installed Executive listener.

The public process only knows a socket path and serialized, signed-origin
decision. The owner is the EXISTING Runtime/JobRegistry. No direct database
access in the client and no START/worker execution claim.
"""
import asyncio
import json

import pytest

from control_plane.executive_runtime import Runtime
from control_plane.github_review_socket_contract import FRAME_SCHEMA, RESPONSE_SCHEMA
from control_plane.github_review_socket_owner import (
    ExecutiveGitHubReviewSocketOwner, GitHubReviewSocketRefused,
)
from integrations.github_review_socket_client import (
    ExecutiveReviewSocketClient, ReviewAdmissionUnavailable,
)
from test_github_review_runtime_adapter import decision


def make_owner(tmp_path, *, armed=True):
    runtime = Runtime.at(tmp_path / "runtime")
    def guarded():
        if not armed:
            raise PermissionError("unarmed")
    owner = ExecutiveGitHubReviewSocketOwner(
        runtime=runtime,
        admission_guard=guarded,
        source_guard=lambda decided: None,
        repositories=frozenset({"example/repo"}),
    )
    return owner, runtime


def status_frame(command):
    return {"schema": FRAME_SCHEMA, "action": "status", "command_id": command}


def admit_frame(subject):
    return {
        "schema": FRAME_SCHEMA, "action": "admit",
        "decision": subject.to_dict(), "objective": "Read-only independent review",
    }


def test_owner_admits_once_via_existing_runtime_and_exact_command(tmp_path):
    owner, runtime = make_owner(tmp_path)
    subject = decision()
    assert owner.handle_frame(status_frame(subject.command_id)) == {
        "schema": RESPONSE_SCHEMA, "state": "ABSENT",
    }
    first = owner.handle_frame(admit_frame(subject))
    assert first["state"] == "ADMITTED" and first["job_id"].startswith("JOB-")
    assert owner.handle_frame(admit_frame(subject)) == first
    assert owner.handle_frame(status_frame(subject.command_id)) == {
        "schema": RESPONSE_SCHEMA, "state": "EXISTS", "job_id": first["job_id"],
    }
    assert len(runtime.jobs.list_jobs()) == 1
    assert runtime.jobs.list_jobs()[0].status.value == "QUEUED"
    assert runtime.jobs.list_jobs()[0].attempt_count == 0


def test_owner_refuses_unarmed_malformed_decision_and_unapproved_repository(tmp_path):
    owner, runtime = make_owner(tmp_path, armed=False)
    with pytest.raises(GitHubReviewSocketRefused, match="UNARMED"):
        owner.handle_frame(admit_frame(decision()))
    assert runtime.jobs.list_jobs() == []
    owner, runtime = make_owner(tmp_path, armed=True)
    malformed = admit_frame(decision())
    malformed["decision"]["repository"] = "another/repository"
    with pytest.raises(GitHubReviewSocketRefused):
        owner.handle_frame(malformed)
    malformed = admit_frame(decision())
    malformed["decision"]["command_id"] = "gh-review-intent:bad"
    with pytest.raises(GitHubReviewSocketRefused):
        owner.handle_frame(malformed)
    assert runtime.jobs.list_jobs() == []


def test_socket_wire_end_to_end_with_same_exact_ledger(tmp_path):
    async def exercise():
        owner, runtime = make_owner(tmp_path)
        path = str(tmp_path / "review.sock")
        async def handle(reader, writer):
            try:
                raw = await reader.readline()
                frame = json.loads(raw)
                result = owner.handle_frame(frame)
                response = {"ok": True, "result": result}
            except Exception:
                response = {"ok": False, "error": {"code": "refused"}}
            writer.write(json.dumps(response).encode() + b"\n")
            await writer.drain()
            writer.close()
            await writer.wait_closed()
        server = await asyncio.start_unix_server(handle, path=path)
        try:
            client = ExecutiveReviewSocketClient(socket_path=path)
            subject = decision()
            assert await asyncio.to_thread(client.has_admitted_command, subject.command_id) is False
            job = await asyncio.to_thread(
                client.admit_review_intent,
                decision=subject, objective="Read-only independent review",
            )
            assert job.startswith("JOB-")
            assert await asyncio.to_thread(client.has_admitted_command, subject.command_id) is True
            again = await asyncio.to_thread(
                client.admit_review_intent,
                decision=subject, objective="Read-only independent review",
            )
            assert again == job
            assert len(runtime.jobs.list_jobs()) == 1
        finally:
            server.close()
            await server.wait_closed()
    asyncio.run(exercise())


def test_missing_socket_fails_without_creating_any_runtime(tmp_path):
    client = ExecutiveReviewSocketClient(
        socket_path=str(tmp_path / "missing.sock"), timeout_seconds=1,
    )
    with pytest.raises(ReviewAdmissionUnavailable, match="UNAVAILABLE"):
        client.has_admitted_command(decision().command_id)


def test_socket_client_refuses_broad_status_enumeration_without_socket_io(tmp_path):
    client = ExecutiveReviewSocketClient(socket_path=str(tmp_path / "missing.sock"))
    with pytest.raises(ReviewAdmissionUnavailable, match="EXACT_STATUS"):
        client.admitted_command_ids()


def test_source_authority_rechecked_at_runtime_commit(tmp_path):
    runtime = Runtime.at(tmp_path / "runtime")
    checks = []
    def changing_source(subject):
        checks.append(subject.command_id)
        if len(checks) >= 3:
            raise PermissionError("head or actor authority changed at commit")
    owner = ExecutiveGitHubReviewSocketOwner(
        runtime=runtime, admission_guard=lambda: None,
        source_guard=changing_source, repositories=frozenset({"example/repo"}),
    )
    with pytest.raises(GitHubReviewSocketRefused, match="ADMISSION_REFUSED"):
        owner.handle_frame(admit_frame(decision()))
    assert len(checks) >= 3
    assert runtime.jobs.list_jobs() == []


def test_socket_sendall_partial_failure_is_unknown_not_safe_to_retry(tmp_path, monkeypatch):
    from integrations import github_review_socket_client as socket_module
    client = ExecutiveReviewSocketClient(socket_path=str(tmp_path / "existing.sock"))
    history = []
    class PartialSend:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def settimeout(self, value):
            pass
        def connect(self, path):
            history.append(("connected", path))
        def sendall(self, payload):
            history.append(("sent_some_bytes", payload[:32]))
            raise BrokenPipeError("partial transmission no ACK")
    monkeypatch.setattr(socket_module.socket, "socket", lambda *args: PartialSend())
    with pytest.raises(ReviewAdmissionUnavailable, match="EFFECT_UNKNOWN"):
        client.admit_review_intent(
            decision=decision(), objective="Read-only independent review"
        )
    assert any(item[0] == "sent_some_bytes" for item in history)


def test_oversized_socket_frame_refuses_before_guard_or_ledger(tmp_path):
    runtime = Runtime.at(tmp_path / "runtime")
    checked = []
    def auth_guard():
        checked.append("checked")
    owner = ExecutiveGitHubReviewSocketOwner(
        runtime=runtime, admission_guard=auth_guard,
        source_guard=lambda _: None,
        repositories=frozenset({"example/repo"}),
    )
    frame = status_frame(decision().command_id)
    frame["padding"] = "x" * 9000
    with pytest.raises(GitHubReviewSocketRefused, match="OVER_BOUND"):
        owner.handle_frame(frame)
    assert checked == []
    assert runtime.jobs.list_jobs() == []
