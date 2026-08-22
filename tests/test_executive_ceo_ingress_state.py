from __future__ import annotations

import asyncio
import functools
import json
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from control_plane import executive_ceo_ingress as ceo_ingress
from control_plane import executive_hot_state as hot_state
from integrations.slack_executive import sol_state
from tests import test_executive_ceo_ingress as pr_a


def _sync_test(function):
    @functools.wraps(function)
    def wrapped(*args, **kwargs):
        return asyncio.run(function(*args, **kwargs))

    return wrapped


@pytest.fixture
def short_socket_root():
    value = Path(tempfile.mkdtemp(prefix="mmx-r0-", dir="/tmp"))
    try:
        yield value
    finally:
        shutil.rmtree(value, ignore_errors=True)


def _state_bytes(**extra) -> bytes:
    frame = {"schema": ceo_ingress.STATE_SCHEMA}
    frame.update(extra)
    return (json.dumps(frame) + "\n").encode("utf-8")


async def _state(path: Path, **extra):
    return await pr_a._raw_ceo_request(path, _state_bytes(**extra))


@_sync_test
async def test_exact_state_schema_and_zero_runtime_mutation(tmp_path, short_socket_root):
    grounding = pr_a._FakeGrounding()
    service = pr_a._service_with_ingress(
        tmp_path, socket_root=short_socket_root, grounding=grounding, armed=True
    )
    await service.start()
    try:
        runtime = service.runtime
        assert runtime is not None
        before = {
            "jobs": runtime.jobs.list_jobs(),
            "attempts": runtime.attempts.list_attempts(),
            "workers": runtime.workers.list_workers(),
            "events": runtime.events.list_events(),
        }
        response = await _state(service.ceo_ingress_socket_path)
        assert response["ok"] is True
        result = response["result"]
        assert result["schema"] == hot_state.HOT_STATE_SCHEMA
        assert result["service"] == {
            "service_state": "READY",
            "ceo_admission": "READY",
        }
        assert result["generic_operator_mutations"] == "AVAILABLE"
        assert result["runtime"]["projection_state"] == "OK"
        assert result["do_not_submit"] is False
        assert grounding.calls == 1
        after = {
            "jobs": runtime.jobs.list_jobs(),
            "attempts": runtime.attempts.list_attempts(),
            "workers": runtime.workers.list_workers(),
            "events": runtime.events.list_events(),
        }
        assert after == before
    finally:
        await service.close()


@_sync_test
async def test_state_extra_business_or_missing_schema_refuses(tmp_path, short_socket_root):
    service = pr_a._service_with_ingress(
        tmp_path,
        socket_root=short_socket_root,
        grounding=pr_a._FakeGrounding(),
        armed=False,
    )
    await service.start()
    try:
        extra = await _state(service.ceo_ingress_socket_path, objective="not allowed")
        assert extra["ok"] is False
        assert extra["error"]["code"] == "invalid_input"
        assert service.runtime.jobs.list_jobs() == []
        assert service.runtime.attempts.list_attempts() == []
        assert service.runtime.workers.list_workers() == []
        assert service.runtime.events.list_events() == []

        missing = await pr_a._raw_ceo_request(
            service.ceo_ingress_socket_path, b"{}\n"
        )
        assert missing["ok"] is False
        assert missing["error"]["code"] == "unsupported_ingress_schema"
    finally:
        await service.close()


@_sync_test
async def test_state_wrong_or_unavailable_peer_refuses_before_body_and_grounding(
    tmp_path, short_socket_root, monkeypatch
):
    grounding = pr_a._FakeGrounding()
    wrong_peer = pr_a._service_with_ingress(
        tmp_path,
        socket_root=short_socket_root,
        grounding=grounding,
        armed=False,
        peer_uid=pr_a.os.geteuid() + 1,
    )
    await wrong_peer.start()
    try:
        response = await _state(wrong_peer.ceo_ingress_socket_path)
        assert response["error"]["code"] == "peer_denied"
        assert grounding.calls == 0
    finally:
        await wrong_peer.close()

    unavailable = pr_a._service_with_ingress(
        tmp_path,
        socket_root=short_socket_root,
        grounding=grounding,
        armed=False,
    )
    await unavailable.start()
    try:
        monkeypatch.setattr(
            "control_plane.executive_service._peer_uid", lambda _connection: None
        )
        response = await _state(unavailable.ceo_ingress_socket_path)
        assert response["error"]["code"] == "peer_credentials_unavailable"
        assert grounding.calls == 0
    finally:
        await unavailable.close()


@_sync_test
async def test_unarmed_state_reads_but_submit_status_never_reach_business(
    tmp_path, short_socket_root, monkeypatch
):
    grounding = pr_a._FakeGrounding()
    service = pr_a._service_with_ingress(
        tmp_path,
        socket_root=short_socket_root,
        grounding=grounding,
        armed=False,
    )
    await service.start()
    try:
        state = await _state(service.ceo_ingress_socket_path)
        assert state["ok"] is True
        assert state["result"]["service"]["ceo_admission"] == "UNARMED"
        assert state["result"]["do_not_submit"] is True
        state_grounding_calls = grounding.calls

        async def forbidden(*_args, **_kwargs):
            raise AssertionError("unarmed PR-A business handler became reachable")

        monkeypatch.setattr(ceo_ingress, "_handle_submit", forbidden)
        monkeypatch.setattr(ceo_ingress, "_handle_status", forbidden)
        submit = await pr_a._submit(service.ceo_ingress_socket_path)
        status = await pr_a._status(
            service.ceo_ingress_socket_path, pr_a.LITERAL_SLACK_INTENT_ID
        )
        assert submit["error"]["code"] == "ingress_unavailable"
        assert status["error"]["code"] == "ingress_unavailable"
        assert grounding.calls == state_grounding_calls
    finally:
        await service.close()


@_sync_test
async def test_awaiting_canary_and_dynamic_unsafe_states_remain_diagnostic(
    tmp_path, short_socket_root
):
    service = pr_a._service_with_ingress(
        tmp_path,
        socket_root=short_socket_root,
        grounding=pr_a._FakeGrounding(),
        armed=True,
        service_state="AWAITING_CANARY",
    )
    await service.start()
    try:
        awaiting = await _state(service.ceo_ingress_socket_path)
        assert awaiting["ok"] is True
        assert awaiting["result"]["service"] == {
            "service_state": "AWAITING_CANARY",
            "ceo_admission": "READY",
        }
        assert (
            awaiting["result"]["generic_operator_mutations"]
            == "BLOCKED_AWAITING_CANARY"
        )

        service._service_state = "QUARANTINED"
        quarantined = await _state(service.ceo_ingress_socket_path)
        assert quarantined["ok"] is True
        assert quarantined["result"]["service"] == {
            "service_state": "QUARANTINED",
            "ceo_admission": "BLOCKED_QUARANTINED",
        }
        assert quarantined["result"]["do_not_submit"] is True
        assert service._service_state == "QUARANTINED"
        submit = await pr_a._submit(service.ceo_ingress_socket_path)
        assert submit["error"]["code"] == "ingress_unavailable"

        service._service_state = "FUTURE_UNSAFE"
        unknown = await _state(service.ceo_ingress_socket_path)
        assert unknown["ok"] is True
        assert unknown["result"]["service"] == {
            "service_state": "UNKNOWN",
            "ceo_admission": "BLOCKED_UNSAFE_STATE",
        }
        assert unknown["result"]["degraded"] == ["SERVICE_STATE_UNKNOWN"]
    finally:
        await service.close()


@_sync_test
async def test_state_racing_startup_latch_refuses_before_body_and_grounding(
    tmp_path, short_socket_root, monkeypatch
):
    grounding = pr_a._FakeGrounding()
    service = pr_a._service_with_ingress(
        tmp_path, socket_root=short_socket_root, grounding=grounding, armed=False
    )
    race_response = {}

    async def failing_start_operator():
        race_response["value"] = await _state(service.ceo_ingress_socket_path)
        raise RuntimeError("simulated Operator start_serving failure")

    monkeypatch.setattr(service, "_start_operator_serving", failing_start_operator)
    with pytest.raises(RuntimeError, match="simulated Operator start_serving failure"):
        await service.start()
    assert race_response["value"]["ok"] is False
    assert race_response["value"]["error"]["code"] == "ingress_unavailable"
    assert grounding.calls == 0


@_sync_test
async def test_state_response_oversize_uses_existing_code_never_truncates(
    tmp_path, short_socket_root, monkeypatch
):
    service = pr_a._service_with_ingress(
        tmp_path,
        socket_root=short_socket_root,
        grounding=pr_a._FakeGrounding(),
        armed=False,
    )
    await service.start()
    try:
        monkeypatch.setattr(hot_state, "MAX_STATE_BYTES", 1)
        response = await _state(service.ceo_ingress_socket_path)
        assert response == {
            "ok": False,
            "error": {
                "code": "response_too_large",
                "message": "Executive hot-state exceeds byte limit",
            },
        }
    finally:
        await service.close()


def test_state_schema_is_the_only_post_pr_a_addition():
    assert ceo_ingress.STATE_SCHEMA == "mastermind.executive_ceo_ingress_state.v1"
    assert ceo_ingress._STATE_TOP_KEYS == frozenset({"schema"})
    assert ceo_ingress.STATE_SCHEMA not in {
        ceo_ingress.SUBMIT_SCHEMA,
        ceo_ingress.STATUS_SCHEMA,
    }


@_sync_test
async def test_real_state_frame_flows_to_development_outbound_publisher(
    tmp_path, short_socket_root
):
    class _DevelopmentSlackFake:
        def __init__(self):
            self.messages = []

        async def fetch_history(self, *, channel_id: str, limit: int):
            return sol_state.HistoryPage(tuple(self.messages), complete=True)

        async def create_message(self, *, channel_id: str, text: str):
            message = sol_state.StateMessage("1", "U-B1-RELAY-FIXTURE", text)
            self.messages.append(message)
            return message

        async def update_message(self, *, channel_id: str, message_ts: str, text: str):
            message = sol_state.StateMessage(
                message_ts, "U-B1-RELAY-FIXTURE", text
            )
            self.messages[0] = message
            return message

    service = pr_a._service_with_ingress(
        tmp_path,
        socket_root=short_socket_root,
        grounding=pr_a._FakeGrounding(),
        armed=False,
    )
    await service.start()
    try:
        response = await _state(service.ceo_ingress_socket_path)
        assert response["ok"] is True
        executive = response["result"]
        checked = datetime.strptime(
            executive["generated_at"], "%Y-%m-%dT%H:%M:%SZ"
        ).replace(tzinfo=timezone.utc)
        client = _DevelopmentSlackFake()
        publisher = sol_state.SolStatePublisher(
            client,
            channel_id="C-B1-DEVELOPMENT-FIXTURE",
            bot_user_id="U-B1-RELAY-FIXTURE",
        )
        receipt = await publisher.publish(executive, relay_checked_at=checked)
        assert receipt.action == "created"
        assert receipt.state_hash == executive["snapshot_hash"]
        assert len(client.messages) == 1
        discriminator, payload = client.messages[0].text.split("\n", 1)
        assert discriminator == sol_state.DISCRIMINATOR
        document = json.loads(payload)
        assert document["executive"] == executive
        assert document["status"] == "DEGRADED"
        assert document["do_not_submit"] is True
        assert document["relay"]["command_transport"] == "NOT_INSTALLED"
    finally:
        await service.close()
