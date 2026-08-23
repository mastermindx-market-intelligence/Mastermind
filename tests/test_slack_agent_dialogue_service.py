from __future__ import annotations

import asyncio
import json
import os
import socket
from pathlib import Path

import pytest

import integrations.slack_agent_dialogue.service as service_module
from integrations.slack_agent_dialogue.contract import (
    MESSAGE_SCHEMA,
    PARENT_SCHEMA,
    build_message,
    build_parent,
    render_message,
    render_parent,
)
from integrations.slack_agent_dialogue.engine import (
    DialogueEngine,
    DialoguePolicy,
    SlackMessage,
)
from integrations.slack_agent_dialogue.fake_slack import InMemorySlackClient
from integrations.slack_agent_dialogue.service import (
    AgentDialogueService,
    CONTROL_VERSION,
    DialogueServiceError,
    ServiceConfig,
    call_service,
)

REPO = "mastermindx-market-intelligence/Mastermind"
BOT = "U0BST4WG996"
SOL = "U0BRETDUAS2"
THREAD_TS = "1787471000.000001"


class ExactServiceAuthorityPolicy:
    def minimum_authority(self, *, request, option) -> str:
        semantic_option = {
            key: value for key, value in option.items() if key != "authority_effect"
        }
        if (
            request["message_key"] == "asd-request-service"
            and semantic_option
            == {
                "id": "opt-continue",
                "summary": "Continue.",
                "consequence": "Work continues.",
                "disposition": "CONTINUE",
            }
        ):
            return "WITHIN_COMMISSION"
        return "CHAIRMAN_REQUIRED"


def run(coro):
    return asyncio.run(coro)


def commission() -> dict[str, str]:
    return {
        "repository": REPO,
        "commit": "a" * 40,
        "path": "research/commission.md",
        "content_sha256": "b" * 64,
    }


def applies() -> dict[str, object]:
    return {"repository": REPO, "head_sha": "c" * 40, "pr": f"{REPO}#125"}


def context_dict() -> dict[str, object]:
    return {
        "work_ref": "WS:CHAIRMAN-CONTROL-ROOM",
        "commission_ref": commission(),
        "session_ref": "asd-session-fable0001",
        "applies_to": applies(),
    }


def parent() -> SlackMessage:
    value = build_parent(
        {
            "schema": PARENT_SCHEMA,
            "work_ref": "WS:CHAIRMAN-CONTROL-ROOM",
            "commission_ref": commission(),
            "session_ref": "asd-session-fable0001",
            "allowed_sol_user_ids": [SOL],
            "created_at": "2026-08-23T08:00:00Z",
        }
    )
    return SlackMessage(ts=THREAD_TS, author_user_id=SOL, text=render_parent(value))


def request() -> dict[str, object]:
    return build_message(
        {
            "schema": MESSAGE_SCHEMA,
            "message_key": "asd-request-service",
            "message_type": "DECISION_REQUEST",
            "work_ref": "WS:CHAIRMAN-CONTROL-ROOM",
            "commission_ref": commission(),
            "session_ref": "asd-session-fable0001",
            "seat_ref": "fable",
            "reply_to_message_key": None,
            "applies_to": applies(),
            "summary": "Bounded request.",
            "body": {
                "question": "Continue?",
                "outcome_impact": "Only the bounded path changes.",
                "options": [
                    {
                        "id": "opt-continue",
                        "summary": "Continue.",
                        "consequence": "Work continues.",
                        "disposition": "CONTINUE",
                        "authority_effect": "NONE",
                    }
                ],
                "recommendation": "opt-continue",
                "work_paused": True,
            },
            "evidence_refs": [],
            "requires_response": True,
            "created_at": "2026-08-23T08:00:00Z",
        }
    )


def ruling(req: dict[str, object]) -> dict[str, object]:
    return build_message(
        {
            "schema": MESSAGE_SCHEMA,
            "message_key": "asd-ruling-service",
            "message_type": "RULING",
            "work_ref": "WS:CHAIRMAN-CONTROL-ROOM",
            "commission_ref": commission(),
            "session_ref": "asd-session-fable0001",
            "seat_ref": "sol",
            "reply_to_message_key": req["message_key"],
            "applies_to": applies(),
            "summary": "Bounded ruling.",
            "body": {
                "authority_class": "WITHIN_COMMISSION",
                "selected_option": "opt-continue",
                "decision": "Continue.",
                "rationale": "It preserves scope.",
                "canonical_ref": None,
            },
            "evidence_refs": [],
            "requires_response": False,
            "created_at": "2026-08-23T08:01:00Z",
        }
    )


def engine_and_client() -> tuple[DialogueEngine, InMemorySlackClient]:
    client = InMemorySlackClient(relay_bot_user_id=BOT)
    client.add_parent(parent())
    engine = DialogueEngine(
        DialoguePolicy(
            workspace_id="T0BRD2AQXQV",
            channel_id="C0BRUL9F2V7",
            relay_bot_user_id=BOT,
            allowed_sol_user_ids=(SOL,),
            allowed_parent_user_ids=(SOL,),
            poll_interval_seconds=0,
        ),
        client,
        authority_policy=ExactServiceAuthorityPolicy(),
    )
    return engine, client


def service(tmp_path: Path) -> tuple[AgentDialogueService, InMemorySlackClient]:
    engine, client = engine_and_client()
    return (
        AgentDialogueService(
            ServiceConfig(
                socket_path=tmp_path / "dialogue.sock",
                allowed_peer_uids=(os.geteuid(),),
                request_timeout_seconds=1,
            ),
            engine,
        ),
        client,
    )


def request_envelope(operation: str, args: dict[str, object]) -> dict[str, object]:
    return {"version": CONTROL_VERSION, "operation": operation, "args": args}


def test_real_unix_status_and_one_shot_cleanup(tmp_path: Path) -> None:
    async def scenario() -> None:
        srv, _client = service(tmp_path)
        task = asyncio.create_task(srv.serve_one())
        while not srv.config.socket_path.exists():
            await asyncio.sleep(0)
        response = await call_service(
            srv.config.socket_path, request_envelope("status", {})
        )
        assert response["ok"] is True
        assert response["result"]["status"] == "DEVELOPMENT_UNARMED"
        await task
        assert not srv.config.socket_path.exists()

    run(scenario())


def test_peer_is_checked_before_body(monkeypatch, tmp_path: Path) -> None:
    async def scenario() -> None:
        srv, _client = service(tmp_path)
        monkeypatch.setattr(service_module, "_peer_uid", lambda connection: 999999)
        await srv.start()
        try:
            reader, writer = await asyncio.open_unix_connection(
                str(srv.config.socket_path)
            )
            raw = await reader.readline()
            response = json.loads(raw)
            assert response == {"ok": False, "error": {"code": "PEER_DENIED"}}
            writer.close()
            await writer.wait_closed()
        finally:
            await srv.close()

    run(scenario())


def test_service_round_trips_fake_decision_and_ruling(tmp_path: Path) -> None:
    async def scenario() -> None:
        srv, client = service(tmp_path)
        req = request()
        client.add_reply(
            SlackMessage(
                ts="1787471000.000010",
                author_user_id=BOT,
                text=render_message(req),
                thread_ts=THREAD_TS,
            )
        )
        reply = ruling(req)
        client.add_reply(
            SlackMessage(
                ts="1787471000.000011",
                author_user_id=SOL,
                text=render_message(reply),
                thread_ts=THREAD_TS,
            )
        )
        await srv.start()
        try:
            response = await call_service(
                srv.config.socket_path,
                request_envelope(
                    "wait_for_reply",
                    {
                        "context": context_dict(),
                        "thread_ts": THREAD_TS,
                        "request_message_key": req["message_key"],
                        "expected_types": ["RULING"],
                        "max_attempts": 1,
                    },
                ),
            )
            assert response["ok"] is True
            assert response["result"]["authority"]["disposition"] == "CONTINUE"
        finally:
            await srv.close()

    run(scenario())


@pytest.mark.parametrize(
    "raw",
    [
        b'{"version":"mastermind.agent_dialogue_control.v1","operation":"status","args":{},"args":{}}\n',
        b'{"version":"mastermind.agent_dialogue_control.v1","operation":"status","args":{"x":NaN}}\n',
        b"not-json\n",
    ],
)
def test_duplicate_nonfinite_or_invalid_json_refuses(
    raw: bytes, tmp_path: Path
) -> None:
    async def scenario() -> None:
        srv, _client = service(tmp_path)
        await srv.start()
        try:
            reader, writer = await asyncio.open_unix_connection(
                str(srv.config.socket_path)
            )
            writer.write(raw)
            await writer.drain()
            response = json.loads(await reader.readline())
            assert response == {
                "ok": False,
                "error": {"code": "REQUEST_INVALID"},
            }
            writer.close()
            await writer.wait_closed()
        finally:
            await srv.close()

    run(scenario())


def test_bool_max_attempts_refuses_at_external_boundary(tmp_path: Path) -> None:
    async def scenario() -> None:
        srv, _client = service(tmp_path)
        await srv.start()
        try:
            response = await call_service(
                srv.config.socket_path,
                request_envelope(
                    "wait_for_reply",
                    {
                        "context": context_dict(),
                        "thread_ts": THREAD_TS,
                        "request_message_key": "asd-request-service",
                        "expected_types": ["RULING"],
                        "max_attempts": True,
                    },
                ),
            )
            assert response == {
                "ok": False,
                "error": {"code": "REQUEST_INVALID"},
            }
        finally:
            await srv.close()

    run(scenario())


def test_existing_nonsocket_or_running_socket_is_not_unlinked(
    tmp_path: Path,
) -> None:
    path = tmp_path / "dialogue.sock"
    path.write_text("owned file", encoding="utf-8")
    srv, _client = service(tmp_path)
    with pytest.raises(DialogueServiceError) as exc:
        run(srv.start())
    assert exc.value.code == "SERVICE_UNAVAILABLE"
    assert path.read_text(encoding="utf-8") == "owned file"

    path.unlink()
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(str(path))
    listener.listen(1)
    try:
        srv, _client = service(tmp_path)
        with pytest.raises(DialogueServiceError):
            run(srv.start())
        assert path.exists()
    finally:
        listener.close()
        path.unlink(missing_ok=True)


def test_relative_client_socket_and_oversize_request_refuse() -> None:
    with pytest.raises(DialogueServiceError) as exc:
        run(call_service("relative.sock", request_envelope("status", {})))
    assert exc.value.code == "REQUEST_INVALID"
    with pytest.raises(DialogueServiceError) as exc:
        run(call_service(Path("/tmp/unused.sock"), {"payload": "x" * 40000}))
    assert exc.value.code == "REQUEST_TOO_LARGE"
