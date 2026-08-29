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


def _applies(actor: dict[str, str]) -> dict[str, str]:
    return {
        "kind": "executive_attempt",
        "job_id": actor["job_id"],
        "attempt_id": actor["attempt_id"],
        "worker_id": actor["worker_id"],
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
    if message_type == "PROGRESS":
        body = {
            "stage": "attempt-rebound",
            "completed": "The first Attempt reached its bounded handoff.",
            "next": "Continue under the replacement Attempt.",
        }
    else:
        body = {
            "status": "PASS",
            "result": "The replacement Attempt completed the bounded continuation.",
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


def test_v2_history_accepts_worker_attempt_replacement_inside_one_parent() -> None:
    p1_actor = _worker("p1")
    p2_actor = _worker("p2")
    p1_applies = _applies(p1_actor)
    p2_applies = _applies(p2_actor)

    progress = _message(
        "PROGRESS",
        message_key="asd-progress-attempt-rebound-p1",
        actor=p1_actor,
        applies_to=p1_applies,
        reply_to_message_key=None,
        created_at="2026-08-29T04:01:00Z",
    )
    result = _message(
        "RESULT",
        message_key="asd-result-attempt-rebound-p2",
        actor=p2_actor,
        applies_to=p2_applies,
        reply_to_message_key=progress["message_key"],
        created_at="2026-08-29T04:02:00Z",
    )

    client = InMemorySlackClient(relay_bot_user_id=BOT)
    client.add_parent(
        SlackMessage(ts=THREAD_TS, author_user_id=SOL, text=render_parent_v2(_parent()))
    )
    client.add_reply(
        SlackMessage(
            ts="1787976100.000001",
            author_user_id=BOT,
            text=render_message_v2(progress),
            thread_ts=THREAD_TS,
        )
    )
    client.add_reply(
        SlackMessage(
            ts="1787976100.000002",
            author_user_id=BOT,
            text=render_message_v2(result),
            thread_ts=THREAD_TS,
        )
    )

    engine = DialogueEngineV2(
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
    context = DialogueContextV2(
        work_ref=WORK_REF,
        commission_ref=_commission(),
        session_ref=SESSION_REF,
        operation_key=OPERATION,
        watch_mode=TURN_WATCH_MODE_V1,
        actor_ref=p2_actor,
        applies_to=p2_applies,
    )

    read = asyncio.run(engine.read_thread(thread_ts=THREAD_TS, context=context))

    assert [item.message["message_key"] for item in read.messages] == [
        progress["message_key"],
        result["message_key"],
    ]
    assert read.messages[0].message["actor_ref"] == p1_actor
    assert read.messages[0].message["applies_to"] == p1_applies
    assert read.messages[1].message["actor_ref"] == p2_actor
    assert read.messages[1].message["applies_to"] == p2_applies
