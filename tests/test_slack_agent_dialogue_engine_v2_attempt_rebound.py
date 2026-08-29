from __future__ import annotations

import asyncio

from integrations.slack_agent_dialogue.contract_v2 import (
    MESSAGE_SCHEMA_V2,
    PARENT_SCHEMA_V2,
    TURN_WATCH_MODE_V1,
    build_message_v2,
    build_parent_v2,
    render_message_v2,
    render_parent_v2,
)
from integrations.slack_agent_dialogue.engine import DialoguePolicy, SlackMessage
from integrations.slack_agent_dialogue.engine_v2 import DialogueContextV2, DialogueEngineV2
from integrations.slack_agent_dialogue.fake_slack import InMemorySlackClient


REPO = "mastermindx-market-intelligence/Mastermind"
CHANNEL = "C0BRUL9F2V7"
WORKSPACE = "T0BRD2AQXQV"
BOT = "U0BST4WG996"
SOL = "U0BRETDUAS2"
THREAD_TS = "1787471000.000001"
OPERATION = "worker-presence-attempt-rebound-20260829"
WORK_REF = "WS:CHAIRMAN-CONTROL-ROOM"
SESSION_REF = "asd-session-rebound01"


class ExactAuthorityPolicy:
    def minimum_authority(self, *, request, option) -> str:
        return "WITHIN_COMMISSION"

    def allows_continuation(self, *, request, reply) -> bool:
        return True


def _commission() -> dict[str, str]:
    return {
        "repository": REPO,
        "commit": "a" * 40,
        "path": "research/commission.md",
        "content_sha256": "b" * 64,
    }


def _worker(attempt: str) -> dict[str, str]:
    return {
        "kind": "worker_attempt",
        "job_id": "job-wp1r-rebound",
        "attempt_id": f"attempt-{attempt}",
        "worker_id": f"worker-{attempt}",
    }


def _attempt(actor: dict[str, str]) -> dict[str, str]:
    return {
        "kind": "executive_attempt",
        "job_id": actor["job_id"],
        "attempt_id": actor["attempt_id"],
        "worker_id": actor["worker_id"],
    }


def _ceo() -> dict[str, str]:
    return {
        "kind": "executive_surface",
        "seat": "ceo",
        "reasoning_surface": "codex",
    }


def _parent() -> dict[str, object]:
    return build_parent_v2(
        {
            "schema": PARENT_SCHEMA_V2,
            "work_ref": WORK_REF,
            "commission_ref": _commission(),
            "session_ref": SESSION_REF,
            "operation_key": OPERATION,
            "watch_mode": TURN_WATCH_MODE_V1,
            "allowed_sol_user_ids": [SOL],
            "created_at": "2026-08-29T04:00:00Z",
        }
    )


def _message(
    message_type: str,
    *,
    message_key: str,
    actor: dict[str, str],
    applies_to: dict[str, str],
    reply_to_message_key: str | None,
    created_at: str,
) -> dict[str, object]:
    body: dict[str, object]
    if message_type == "RESULT":
        body = {
            "status": "PASS",
            "result": "The first Attempt reached its bounded return.",
        }
    elif message_type == "CONTINUE":
        body = {
            "instruction": "Continue the same commissioned child after the lawful rebound.",
            "stop_condition": "Stop if the parent operation or authority changes.",
            "scope_change": False,
        }
    else:
        body = {
            "stage": "attempt-rebound",
            "completed": "The replacement Attempt resumed the bounded child.",
            "next": "Continue only inside the existing commission.",
        }
    return build_message_v2(
        {
            "schema": MESSAGE_SCHEMA_V2,
            "message_key": message_key,
            "message_type": message_type,
            "work_ref": WORK_REF,
            "commission_ref": _commission(),
            "session_ref": SESSION_REF,
            "actor_ref": actor,
            "reply_to_message_key": reply_to_message_key,
            "applies_to": applies_to,
            "summary": "Bounded worker Attempt rebound proof.",
            "body": body,
            "evidence_refs": [],
            "requires_response": False,
            "created_at": created_at,
        }
    )


def _engine(client: InMemorySlackClient) -> DialogueEngineV2:
    return DialogueEngineV2(
        DialoguePolicy(
            workspace_id=WORKSPACE,
            channel_id=CHANNEL,
            relay_bot_user_id=BOT,
            allowed_sol_user_ids=(SOL,),
            allowed_parent_user_ids=(SOL,),
            poll_interval_seconds=0,
            max_wait_attempts=1,
        ),
        client,
        authority_policy=ExactAuthorityPolicy(),
    )


def test_v2_preserves_result_continue_then_worker_attempt_replacement() -> None:
    p1_actor = _worker("p1")
    p2_actor = _worker("p2")
    p1_applies = _attempt(p1_actor)
    p2_applies = _attempt(p2_actor)

    p1_result = _message(
        "RESULT",
        message_key="asd-result-attempt-rebound-p1",
        actor=p1_actor,
        applies_to=p1_applies,
        reply_to_message_key=None,
        created_at="2026-08-29T04:01:00Z",
    )
    sol_continue = _message(
        "CONTINUE",
        message_key="asd-continue-attempt-rebound-p1",
        actor=_ceo(),
        applies_to=p1_applies,
        reply_to_message_key=p1_result["message_key"],
        created_at="2026-08-29T04:02:00Z",
    )
    p2_progress = _message(
        "PROGRESS",
        message_key="asd-progress-attempt-rebound-p2",
        actor=p2_actor,
        applies_to=p2_applies,
        reply_to_message_key=sol_continue["message_key"],
        created_at="2026-08-29T04:03:00Z",
    )

    client = InMemorySlackClient(relay_bot_user_id=BOT)
    client.add_parent(
        SlackMessage(ts=THREAD_TS, author_user_id=SOL, text=render_parent_v2(_parent()))
    )
    for ts, author, message in (
        ("1787976100.000001", BOT, p1_result),
        ("1787976100.000002", SOL, sol_continue),
        ("1787976100.000003", BOT, p2_progress),
    ):
        client.add_reply(
            SlackMessage(
                ts=ts,
                author_user_id=author,
                text=render_message_v2(message),
                thread_ts=THREAD_TS,
            )
        )

    engine = _engine(client)
    p1_context = DialogueContextV2(
        work_ref=WORK_REF,
        commission_ref=_commission(),
        session_ref=SESSION_REF,
        operation_key=OPERATION,
        watch_mode=TURN_WATCH_MODE_V1,
        actor_ref=p1_actor,
        applies_to=p1_applies,
    )
    p2_context = DialogueContextV2(
        work_ref=WORK_REF,
        commission_ref=_commission(),
        session_ref=SESSION_REF,
        operation_key=OPERATION,
        watch_mode=TURN_WATCH_MODE_V1,
        actor_ref=p2_actor,
        applies_to=p2_applies,
    )

    continuation = asyncio.run(
        engine.wait_for_reply(
            thread_ts=THREAD_TS,
            context=p1_context,
            request_message_key=p1_result["message_key"],
            expected_types=("CONTINUE",),
            max_attempts=1,
        )
    )
    assert continuation["reply"] == sol_continue
    assert continuation["authority"] == {
        "disposition": "CONTINUE",
        "executable": True,
        "selected_option": None,
        "canonical_ref": None,
    }

    read = asyncio.run(engine.read_thread(thread_ts=THREAD_TS, context=p2_context))
    assert [item.message["message_key"] for item in read.messages] == [
        p1_result["message_key"],
        sol_continue["message_key"],
        p2_progress["message_key"],
    ]
    assert read.messages[0].message["actor_ref"] == p1_actor
    assert read.messages[0].message["applies_to"] == p1_applies
    assert read.messages[2].message["actor_ref"] == p2_actor
    assert read.messages[2].message["applies_to"] == p2_applies
