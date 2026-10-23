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

def parent_frame(subject, job_id, *, ts="1792699000.000001",
                 bot="U0BT71H4FQE", channel="C0CAUK8P8S3"):
    return {
        "schema": FRAME_SCHEMA, "action": "record_parent",
        "decision": subject.to_dict(), "job_id": job_id,
        "channel_id": channel, "thread_ts": ts, "author_user_id": bot,
    }


def test_socket_parent_requires_enrolled_relay_and_original_job(tmp_path):
    from integrations.github_review_slack_thread import ExecutiveSlackReviewThreads

    subject = decision()
    owner, runtime = make_owner(tmp_path)
    job_id = owner.handle_frame(admit_frame(subject))["job_id"]
    with pytest.raises(GitHubReviewSocketRefused, match="PROVENANCE_UNBOUND"):
        owner.handle_frame(parent_frame(subject, job_id))
    assert ExecutiveSlackReviewThreads(runtime=runtime).parent_thread(
        decision=subject, job_id=job_id,
    ) is None

    from integrations.github_review_slack_thread import review_parent_body
    from integrations.slack_agent_dialogue.engine import SlackMessage
    def trusted_parent_reader(subject, job, ts):
        return SlackMessage(
            ts=ts, author_user_id="U0BT71H4FQE",
            text=review_parent_body(decision=subject, job_id=job),
        )
    authorized = ExecutiveGitHubReviewSocketOwner(
        runtime=runtime, admission_guard=lambda: None,
        source_guard=lambda _: None,
        repositories=frozenset({"example/repo"}),
        relay_bot_user_id="U0BT71H4FQE",
        parent_message_reader=trusted_parent_reader,
        parent_recorder=ExecutiveSlackReviewThreads(runtime=runtime).record_parent,
    )
    bad = [
        parent_frame(subject, "JOB-999"),
        parent_frame(subject, job_id, bot="U0ATTACKER"),
        parent_frame(subject, job_id, channel="C0WRONGCHN"),
        parent_frame(subject, job_id, ts="1234"),
    ]
    for frame in bad:
        with pytest.raises(GitHubReviewSocketRefused):
            authorized.handle_frame(frame)
    assert ExecutiveSlackReviewThreads(runtime=runtime).parent_thread(
        decision=subject, job_id=job_id,
    ) is None

    frame = parent_frame(subject, job_id)
    receipt = authorized.handle_frame(frame)
    assert receipt == {
        "schema": RESPONSE_SCHEMA, "state": "PARENT_RECORDED",
        "job_id": job_id,
    }
    assert authorized.handle_frame(frame) == receipt
    assert ExecutiveSlackReviewThreads(runtime=runtime).parent_thread(
        decision=subject, job_id=job_id,
    ) == "1792699000.000001"
    events = runtime.store.list_events(command_id_prefix="gh-review-slack-parent:")
    assert len(events) == 1

    with pytest.raises(GitHubReviewSocketRefused, match="CONFLICT"):
        authorized.handle_frame(parent_frame(
            subject, job_id, ts="1792699000.000002"
        ))
    assert len(runtime.store.list_events(
        command_id_prefix="gh-review-slack-parent:"
    )) == 1


def test_partial_socket_parent_capture_is_unknown_no_automatic_repost(
    tmp_path, monkeypatch,
):
    from integrations import github_review_socket_client as socket_module
    from integrations.slack_agent_dialogue.engine import SlackMessage

    class PartialSend:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return None
        def settimeout(self, value):
            return None
        def connect(self, path):
            return None
        def sendall(self, raw):
            assert b"record_parent" in raw
            raise BrokenPipeError("partially transmitted parent receipt")

    monkeypatch.setattr(socket_module.socket, "socket", lambda *args: PartialSend())
    client = ExecutiveReviewSocketClient(socket_path=str(tmp_path / "held.sock"))
    with pytest.raises(ReviewAdmissionUnavailable, match="PARENT_EFFECT_UNKNOWN"):
        client.record_parent(
            decision=decision(), job_id="JOB-001",
            message=SlackMessage(
                ts="1792699000.000001", author_user_id="U0BT71H4FQE",
                text="Recorded trusted original Slack parent",
            ),
        )

@pytest.mark.parametrize("invalid", [
    {"eligible_quota_classes": []},
    {"eligible_quota_classes": ["codex-native", "codex-native"]},
    {"eligible_quota_classes": ["../../untrusted"]},
    {"provider": "codex"},
    {"eligible_quota_classes": ["codex-native"], "model": "override"},
])
def test_review_worker_eligibility_is_a_closed_host_only_binding(tmp_path, invalid):
    runtime = Runtime.at(tmp_path / "runtime")
    with pytest.raises(ValueError, match="worker"):
        ExecutiveGitHubReviewSocketOwner(
            runtime=runtime,
            admission_guard=lambda: None,
            source_guard=lambda _: None,
            repositories=frozenset({"example/repo"}),
            worker_constraints=invalid,
        )
    assert runtime.jobs.list_jobs() == []


def test_owner_selected_existing_worker_quota_class_survives_socket_admission(tmp_path):
    runtime = Runtime.at(tmp_path / "runtime")
    owner = ExecutiveGitHubReviewSocketOwner(
        runtime=runtime, admission_guard=lambda: None,
        source_guard=lambda _: None, repositories=frozenset({"example/repo"}),
        worker_constraints={"eligible_quota_classes": ["codex-native"]},
    )
    job_id = owner.handle_frame(admit_frame(decision()))["job_id"]
    admitted = runtime.jobs.get_job(job_id)
    assert admitted.constraints["eligible_quota_classes"] == ["codex-native"]
    assert admitted.requested_authorities == ["READ"]
    assert admitted.allowed_write_paths == []
    assert admitted.attempt_count == 0

@pytest.mark.parametrize("bad", [
    "unverified", "no_receipt", "wrong_timestamp", "wrong_bot",
    "wrong_text", "edited", "deleted", "thread_reply",
])
def test_socket_parent_requires_real_host_authenticated_message_readback(
    tmp_path, bad,
):
    from integrations.github_review_slack_thread import (
        ExecutiveSlackReviewThreads, review_parent_body,
    )
    from integrations.slack_agent_dialogue.engine import SlackMessage

    subject = decision()
    runtime = Runtime.at(tmp_path / "runtime")
    create = ExecutiveGitHubReviewSocketOwner(
        runtime=runtime, admission_guard=lambda: None,
        source_guard=lambda _: None, repositories=frozenset({"example/repo"}),
    )
    job_id = create.handle_frame(admit_frame(subject))["job_id"]
    looked_up = []
    def host_message_reader(chosen, job, ts):
        looked_up.append((chosen.command_id, job, ts))
        if bad == "unverified":
            raise OSError("trusted Relay Slack GET unavailable")
        if bad == "no_receipt":
            return None
        body = review_parent_body(decision=chosen, job_id=job)
        return SlackMessage(
            ts="1792699000.000002" if bad == "wrong_timestamp" else ts,
            author_user_id="U0WRONGBOT" if bad == "wrong_bot" else "U0BT71H4FQE",
            text="unrelated Slack parent body" if bad == "wrong_text" else body,
            edited=bad == "edited",
            deleted=bad == "deleted",
            thread_ts=ts if bad == "thread_reply" else None,
        )
    owner = ExecutiveGitHubReviewSocketOwner(
        runtime=runtime, admission_guard=lambda: None,
        source_guard=lambda _: None, repositories=frozenset({"example/repo"}),
        relay_bot_user_id="U0BT71H4FQE",
        parent_message_reader=host_message_reader,
        parent_recorder=ExecutiveSlackReviewThreads(runtime=runtime).record_parent,
    )
    with pytest.raises(GitHubReviewSocketRefused, match="SOURCE_UNVERIFIED"):
        owner.handle_frame(parent_frame(subject, job_id))
    assert len(looked_up) == 1
    assert ExecutiveSlackReviewThreads(runtime=runtime).parent_thread(
        decision=subject, job_id=job_id,
    ) is None
    assert runtime.store.list_events(command_id_prefix="gh-review-slack-parent:") == []


def test_socket_parent_rechecks_revoked_github_source_before_slack_read(tmp_path):
    from integrations.github_review_slack_thread import ExecutiveSlackReviewThreads
    runtime = Runtime.at(tmp_path / "runtime")
    chosen = decision()
    create = ExecutiveGitHubReviewSocketOwner(
        runtime=runtime, admission_guard=lambda: None,
        source_guard=lambda _: None, repositories=frozenset({"example/repo"}),
    )
    job = create.handle_frame(admit_frame(chosen))["job_id"]
    reads = []
    def revoked(_chosen):
        raise PermissionError("actor revoked after admission")
    def no_slack_read(*args):
        reads.append(args)
        raise AssertionError("Slack lookup must not occur after revocation")
    owner = ExecutiveGitHubReviewSocketOwner(
        runtime=runtime, admission_guard=lambda: None, source_guard=revoked,
        repositories=frozenset({"example/repo"}),
        relay_bot_user_id="U0BT71H4FQE",
        parent_message_reader=no_slack_read,
        parent_recorder=ExecutiveSlackReviewThreads(runtime=runtime).record_parent,
    )
    with pytest.raises(GitHubReviewSocketRefused, match="SOURCE_UNVERIFIED"):
        owner.handle_frame(parent_frame(chosen, job))
    assert reads == []

def test_socket_parent_cannot_write_without_host_owned_recorder(tmp_path):
    """A trusted Slack GET alone cannot create a second canonical event writer."""
    from integrations.github_review_slack_thread import (
        ExecutiveSlackReviewThreads, review_parent_body,
    )
    from integrations.slack_agent_dialogue.engine import SlackMessage

    subject = decision()
    runtime = Runtime.at(tmp_path / "runtime")
    admitted = ExecutiveGitHubReviewSocketOwner(
        runtime=runtime, admission_guard=lambda: None,
        source_guard=lambda _: None, repositories=frozenset({"example/repo"}),
    )
    job_id = admitted.handle_frame(admit_frame(subject))["job_id"]
    reader_calls = []
    def reader(chosen, job, ts):
        reader_calls.append(ts)
        return SlackMessage(
            ts=ts, author_user_id="U0BT71H4FQE",
            text=review_parent_body(decision=chosen, job_id=job),
        )
    no_recorder = ExecutiveGitHubReviewSocketOwner(
        runtime=runtime, admission_guard=lambda: None,
        source_guard=lambda _: None,
        repositories=frozenset({"example/repo"}),
        relay_bot_user_id="U0BT71H4FQE",
        parent_message_reader=reader,
    )
    with pytest.raises(GitHubReviewSocketRefused, match="PROVENANCE_UNBOUND"):
        no_recorder.handle_frame(parent_frame(subject, job_id))
    assert reader_calls == []
    assert ExecutiveSlackReviewThreads(runtime=runtime).parent_thread(
        decision=subject, job_id=job_id,
    ) is None
