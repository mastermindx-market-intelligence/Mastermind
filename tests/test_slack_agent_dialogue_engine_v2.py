from __future__ import annotations

import asyncio
import copy

import pytest

from integrations.slack_agent_dialogue.contract import (
    PARENT_SCHEMA,
    build_parent,
    render_parent,
)
from integrations.slack_agent_dialogue.contract_v2 import (
    PARENT_SCHEMA_V2,
    TURN_WATCH_MODE_V1,
    build_parent_v2,
    render_parent_v2,
)
from integrations.slack_agent_dialogue.engine import (
    DialogueEngineError,
    DialoguePolicy,
    SlackMessage,
)
from integrations.slack_agent_dialogue.fake_slack import InMemorySlackClient

REPO = "mastermindx-market-intelligence/Mastermind"
CHANNEL = "C0BRUL9F2V7"
WORKSPACE = "T0BRD2AQXQV"
BOT = "U0BST4WG996"
SOL1 = "U0BRETDUAS2"
SOL2 = "U0BSB73JWNL"
THREAD_TS = "1787471000.000001"
OPERATION = "worker-presence-dialogue-canary-20260827-001"


class ExactV2AuthorityPolicy:
    def minimum_authority(self, *, request, option) -> str:
        return "WITHIN_COMMISSION"

    def allows_continuation(self, *, request, reply) -> bool:
        return True


def run(coro):
    return asyncio.run(coro)


def commission() -> dict[str, str]:
    return {
        "repository": REPO,
        "commit": "a" * 40,
        "path": "research/commission.md",
        "content_sha256": "b" * 64,
    }


def applies(head: str = "c" * 40) -> dict[str, object]:
    return {
        "kind": "repository",
        "repository": REPO,
        "head_sha": head,
        "pr": f"{REPO}#178",
    }


def actor() -> dict[str, str]:
    return {
        "kind": "executive_surface",
        "seat": "coo",
        "reasoning_surface": "claude",
    }


def context(
    *,
    work_ref: str = "WS:CHAIRMAN-CONTROL-ROOM",
    commission_ref: dict[str, str] | None = None,
    session_ref: str = "asd-session-fable0001",
    operation_key: str = OPERATION,
    watch_mode: str | None = TURN_WATCH_MODE_V1,
):
    from integrations.slack_agent_dialogue.engine_v2 import DialogueContextV2

    return DialogueContextV2(
        work_ref=work_ref,
        commission_ref=commission() if commission_ref is None else commission_ref,
        session_ref=session_ref,
        operation_key=operation_key,
        watch_mode=watch_mode,
        actor_ref=actor(),
        applies_to=applies(),
    )


def policy(**overrides) -> DialoguePolicy:
    values = {
        "workspace_id": WORKSPACE,
        "channel_id": CHANNEL,
        "relay_bot_user_id": BOT,
        "allowed_sol_user_ids": tuple(sorted((SOL1, SOL2))),
        "allowed_parent_user_ids": (SOL1,),
        "poll_interval_seconds": 0,
        "max_wait_attempts": 3,
    }
    values.update(overrides)
    return DialoguePolicy(**values)


def make_engine(client: InMemorySlackClient):
    from integrations.slack_agent_dialogue.engine_v2 import DialogueEngineV2

    return DialogueEngineV2(
        policy(),
        client,
        authority_policy=ExactV2AuthorityPolicy(),
    )


def parent_value(
    *,
    work_ref: str = "WS:CHAIRMAN-CONTROL-ROOM",
    commission_ref: dict[str, str] | None = None,
    session_ref: str = "asd-session-fable0001",
    operation_key: str = OPERATION,
    watch_mode: str | None = TURN_WATCH_MODE_V1,
) -> dict[str, object]:
    return build_parent_v2(
        {
            "schema": PARENT_SCHEMA_V2,
            "work_ref": work_ref,
            "commission_ref": commission() if commission_ref is None else commission_ref,
            "session_ref": session_ref,
            "operation_key": operation_key,
            "watch_mode": watch_mode,
            "allowed_sol_user_ids": list(tuple(sorted((SOL1, SOL2)))),
            "created_at": "2026-08-27T13:00:00Z",
        }
    )


def parent_message(
    *,
    ts: str = THREAD_TS,
    author: str = SOL1,
    **overrides,
) -> SlackMessage:
    return SlackMessage(
        ts=ts,
        author_user_id=author,
        text=render_parent_v2(parent_value(**overrides)),
    )


def setup_client() -> InMemorySlackClient:
    client = InMemorySlackClient(relay_bot_user_id=BOT)
    client.add_parent(parent_message())
    return client


def code(exc: pytest.ExceptionInfo[DialogueEngineError]) -> str:
    return exc.value.code


def test_v2_binds_exactly_one_v2_parent() -> None:
    bound = run(make_engine(setup_client()).bind_or_verify_thread(context()))
    assert bound.thread_ts == THREAD_TS
    assert bound.parent_author_user_id == SOL1
    assert bound.parent_fingerprint == parent_value()["fingerprint"]


def test_v2_zero_or_multiple_matching_parents_are_ambiguous() -> None:
    empty = InMemorySlackClient(relay_bot_user_id=BOT)
    with pytest.raises(DialogueEngineError) as exc:
        run(make_engine(empty).bind_or_verify_thread(context()))
    assert code(exc) == "THREAD_BINDING_AMBIGUOUS"

    duplicate = setup_client()
    duplicate.add_parent(parent_message(ts="1787471000.000002"))
    with pytest.raises(DialogueEngineError) as exc:
        run(make_engine(duplicate).bind_or_verify_thread(context()))
    assert code(exc) == "THREAD_BINDING_AMBIGUOUS"


@pytest.mark.parametrize(
    ("field", "changed"),
    [
        ("work_ref", "WS:OTHER-WORK"),
        (
            "commission_ref",
            {
                "repository": REPO,
                "commit": "d" * 40,
                "path": "research/commission.md",
                "content_sha256": "b" * 64,
            },
        ),
        ("session_ref", "asd-session-fable0002"),
        ("operation_key", "worker-presence-dialogue-canary-20260827-002"),
        ("watch_mode", None),
    ],
)
def test_v2_parent_identity_mismatch_refuses(field: str, changed: object) -> None:
    client = setup_client()
    kwargs = {field: changed}
    with pytest.raises(DialogueEngineError) as exc:
        run(make_engine(client).bind_or_verify_thread(context(**kwargs)))
    assert code(exc) == "THREAD_CONTEXT_MISMATCH"


def test_v1_parent_never_satisfies_v2_binding() -> None:
    v1_parent = build_parent(
        {
            "schema": PARENT_SCHEMA,
            "work_ref": "WS:CHAIRMAN-CONTROL-ROOM",
            "commission_ref": commission(),
            "session_ref": "asd-session-fable0001",
            "allowed_sol_user_ids": list(tuple(sorted((SOL1, SOL2)))),
            "created_at": "2026-08-27T13:00:00Z",
        }
    )
    client = InMemorySlackClient(relay_bot_user_id=BOT)
    client.add_parent(
        SlackMessage(ts=THREAD_TS, author_user_id=SOL1, text=render_parent(v1_parent))
    )
    with pytest.raises(DialogueEngineError) as exc:
        run(make_engine(client).bind_or_verify_thread(context()))
    assert code(exc) == "THREAD_BINDING_AMBIGUOUS"


def test_v2_mutated_parent_without_creation_evidence_refuses() -> None:
    client = setup_client()
    original = client.channel_messages[0]
    client.channel_messages[0] = SlackMessage(
        ts=original.ts,
        author_user_id=original.author_user_id,
        text="edited transport text",
        edited=True,
    )
    with pytest.raises(DialogueEngineError) as exc:
        run(make_engine(client).bind_or_verify_thread(context()))
    assert code(exc) == "THREAD_RECONCILIATION_INCOMPLETE"


def test_v2_parent_transport_identity_cannot_supply_actor_ref() -> None:
    client = InMemorySlackClient(relay_bot_user_id=BOT)
    client.add_parent(parent_message(author=BOT))
    with pytest.raises(DialogueEngineError) as exc:
        run(make_engine(client).bind_or_verify_thread(context()))
    assert code(exc) == "THREAD_BINDING_AMBIGUOUS"

    forged = copy.deepcopy(actor())
    forged["seat"] = "ceo"
    asserted = context()
    assert asserted.actor_ref == actor()
    assert asserted.actor_ref != forged
