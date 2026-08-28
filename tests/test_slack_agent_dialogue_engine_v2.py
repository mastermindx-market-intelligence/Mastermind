from __future__ import annotations

import asyncio
import copy

import pytest

from integrations.slack_agent_dialogue.contract import (
    MESSAGE_SCHEMA,
    PARENT_SCHEMA,
    build_message,
    build_parent,
    render_message,
    render_parent,
)
from integrations.slack_agent_dialogue.contract_v2 import (
    MESSAGE_SCHEMA_V2,
    PARENT_SCHEMA_V2,
    TURN_WATCH_MODE_V1,
    build_message_v2,
    build_parent_v2,
    render_message_v2,
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


class ChairmanFloorPolicy:
    def minimum_authority(self, *, request, option) -> str:
        return "CHAIRMAN_REQUIRED"

    def allows_continuation(self, *, request, reply) -> bool:
        return False


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


def ceo_actor() -> dict[str, str]:
    return {
        "kind": "executive_surface",
        "seat": "ceo",
        "reasoning_surface": "codex",
    }


def context(
    *,
    work_ref: str = "WS:CHAIRMAN-CONTROL-ROOM",
    commission_ref: dict[str, str] | None = None,
    session_ref: str = "asd-session-fable0001",
    operation_key: str = OPERATION,
    watch_mode: str | None = TURN_WATCH_MODE_V1,
    actor_ref: dict[str, object] | None = None,
    applies_to: dict[str, object] | None = None,
):
    from integrations.slack_agent_dialogue.engine_v2 import DialogueContextV2

    return DialogueContextV2(
        work_ref=work_ref,
        commission_ref=commission() if commission_ref is None else commission_ref,
        session_ref=session_ref,
        operation_key=operation_key,
        watch_mode=watch_mode,
        actor_ref=copy.deepcopy(actor() if actor_ref is None else actor_ref),
        applies_to=copy.deepcopy(applies() if applies_to is None else applies_to),
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


def make_engine(
    client: InMemorySlackClient,
    *,
    authority_policy=None,
):
    from integrations.slack_agent_dialogue.engine_v2 import DialogueEngineV2

    return DialogueEngineV2(
        policy(),
        client,
        authority_policy=(
            ExactV2AuthorityPolicy() if authority_policy is None else authority_policy
        ),
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


def raw_v2_message(
    message_type: str = "ACK",
    *,
    message_key: str | None = None,
    actor_ref: dict[str, object] | None = None,
    work_ref: str = "WS:CHAIRMAN-CONTROL-ROOM",
    commission_ref: dict[str, str] | None = None,
    session_ref: str = "asd-session-fable0001",
    applies_to: dict[str, object] | None = None,
    reply_to_message_key: str | None = None,
) -> dict[str, object]:
    bodies: dict[str, dict[str, object]] = {
        "ACK": {"acknowledged": True},
        "PROGRESS": {
            "stage": "engine",
            "completed": "V2 history was read.",
            "next": "Continue the bounded engine proof.",
        },
        "DECISION_REQUEST": {
            "question": "Which bounded engine option should be selected?",
            "outcome_impact": "The choice changes only the accepted V2 engine path.",
            "options": [
                {
                    "id": "opt-continue",
                    "summary": "Continue.",
                    "consequence": "The bounded engine proof continues.",
                    "disposition": "CONTINUE",
                    "authority_effect": "NONE",
                },
                {
                    "id": "opt-stop",
                    "summary": "Stop.",
                    "consequence": "The bounded engine proof remains held.",
                    "disposition": "STOP",
                    "authority_effect": "NONE",
                },
            ],
            "recommendation": "opt-continue",
            "work_paused": True,
        },
        "RULING": {
            "authority_class": "WITHIN_COMMISSION",
            "selected_option": "opt-continue",
            "decision": "Continue the bounded engine proof.",
            "rationale": "It preserves the accepted commission.",
            "canonical_ref": None,
        },
        "CONTINUE": {
            "instruction": "Continue within the frozen WP-1 scope.",
            "stop_condition": "Stop if the commission or carrier changes.",
            "scope_change": False,
        },
        "STOP": {
            "reason": "Stop at the current bounded gate.",
            "next_authority": "sol",
        },
    }
    sol_reply = message_type in {"RULING", "CONTINUE", "STOP"}
    return {
        "schema": MESSAGE_SCHEMA_V2,
        "message_key": message_key or f"asd-{message_type.lower()}-v2-engine-0001",
        "message_type": message_type,
        "work_ref": work_ref,
        "commission_ref": commission() if commission_ref is None else commission_ref,
        "session_ref": session_ref,
        "actor_ref": copy.deepcopy(actor() if actor_ref is None else actor_ref),
        "reply_to_message_key": (
            reply_to_message_key
            if reply_to_message_key is not None
            else ("asd-request-v2-engine-0001" if sol_reply else None)
        ),
        "applies_to": copy.deepcopy(applies() if applies_to is None else applies_to),
        "summary": "Bounded V2 engine message.",
        "body": copy.deepcopy(bodies[message_type]),
        "evidence_refs": [],
        "requires_response": message_type == "DECISION_REQUEST",
        "created_at": "2026-08-27T13:05:00Z",
    }


def v2_message(message_type: str = "ACK", **kwargs) -> dict[str, object]:
    return build_message_v2(raw_v2_message(message_type, **kwargs))


def add_v2_reply(
    client: InMemorySlackClient,
    value: dict[str, object],
    *,
    author: str,
    ts: str,
    text: str | None = None,
    edited: bool = False,
    deleted: bool = False,
    created_text: str | None = None,
) -> None:
    client.add_reply(
        SlackMessage(
            ts=ts,
            author_user_id=author,
            text=render_message_v2(value) if text is None else text,
            thread_ts=THREAD_TS,
            edited=edited,
            deleted=deleted,
            created_text=created_text,
        )
    )


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


def test_v2_history_reads_only_v2_frames_and_accepts_opposite_actor() -> None:
    client = setup_client()
    contributor = v2_message("ACK", message_key="asd-ack-v2-engine-read")
    executive = v2_message(
        "STOP",
        message_key="asd-stop-v2-engine-read",
        actor_ref=ceo_actor(),
    )
    add_v2_reply(client, contributor, author=BOT, ts="1787471000.000010")
    add_v2_reply(client, executive, author=SOL1, ts="1787471000.000011")

    v1 = build_message(
        {
            "schema": MESSAGE_SCHEMA,
            "message_key": "asd-v1-ignored-engine-0001",
            "message_type": "ACK",
            "work_ref": "WS:CHAIRMAN-CONTROL-ROOM",
            "commission_ref": commission(),
            "session_ref": "asd-session-fable0001",
            "seat_ref": "fable",
            "reply_to_message_key": None,
            "applies_to": {
                "repository": REPO,
                "head_sha": "c" * 40,
                "pr": f"{REPO}#178",
            },
            "summary": "Historical V1 frame ignored by V2.",
            "body": {"acknowledged": True},
            "evidence_refs": [],
            "requires_response": False,
            "created_at": "2026-08-27T13:05:01Z",
        }
    )
    client.add_reply(
        SlackMessage(
            ts="1787471000.000012",
            author_user_id=BOT,
            text=render_message(v1),
            thread_ts=THREAD_TS,
        )
    )

    read = run(make_engine(client).read_thread(thread_ts=THREAD_TS, context=context()))
    assert [item.message["message_key"] for item in read.messages] == [
        contributor["message_key"],
        executive["message_key"],
    ]
    assert read.historical_messages == ()
    assert read.ineligible_count == 0


@pytest.mark.parametrize("mutation", ["work", "commission", "session", "applicability"])
def test_v2_history_wrong_bound_context_fails_closed(mutation: str) -> None:
    client = setup_client()
    kwargs: dict[str, object] = {}
    if mutation == "work":
        kwargs["work_ref"] = "WS:OTHER-WORK"
    elif mutation == "commission":
        kwargs["commission_ref"] = {
            "repository": REPO,
            "commit": "d" * 40,
            "path": "research/commission.md",
            "content_sha256": "b" * 64,
        }
    elif mutation == "session":
        kwargs["session_ref"] = "asd-session-fable0002"
    else:
        kwargs["applies_to"] = applies("d" * 40)

    changed = v2_message("ACK", message_key=f"asd-ack-v2-wrong-{mutation}", **kwargs)
    add_v2_reply(client, changed, author=BOT, ts="1787471000.000020")
    with pytest.raises(DialogueEngineError) as exc:
        run(make_engine(client).read_thread(thread_ts=THREAD_TS, context=context()))
    assert code(exc) == "THREAD_CONTEXT_MISMATCH"


def test_v2_history_mutation_requires_creation_evidence() -> None:
    client = setup_client()
    message = v2_message("ACK", message_key="asd-ack-v2-mutated-no-proof")
    frame = render_message_v2(message)
    add_v2_reply(
        client,
        message,
        author=BOT,
        ts="1787471000.000030",
        text="edited transport text",
        edited=True,
    )
    with pytest.raises(DialogueEngineError) as exc:
        run(make_engine(client).read_thread(thread_ts=THREAD_TS, context=context()))
    assert code(exc) == "THREAD_RECONCILIATION_INCOMPLETE"

    client = setup_client()
    add_v2_reply(
        client,
        message,
        author=BOT,
        ts="1787471000.000031",
        text="edited transport text",
        edited=True,
        created_text=frame,
    )
    read = run(make_engine(client).read_thread(thread_ts=THREAD_TS, context=context()))
    assert read.messages[0].message == message
    assert read.mutated_count == 1


def test_v2_history_unknown_sender_is_ineligible_not_actor_authority() -> None:
    client = setup_client()
    message = v2_message("ACK", message_key="asd-ack-v2-unknown-sender")
    add_v2_reply(client, message, author="U000000001", ts="1787471000.000040")
    read = run(make_engine(client).read_thread(thread_ts=THREAD_TS, context=context()))
    assert read.messages == ()
    assert read.ineligible_count == 1


def test_v2_send_duplicate_is_storeless_and_posts_zero_times() -> None:
    client = setup_client()
    message = v2_message("ACK", message_key="asd-ack-v2-send-duplicate")
    add_v2_reply(client, message, author=BOT, ts="1787471000.000050")
    receipt = run(
        make_engine(client).send_message(
            thread_ts=THREAD_TS,
            context=context(),
            message=message,
        )
    )
    assert receipt.action == "DUPLICATE"
    assert receipt.message_ts == "1787471000.000050"
    assert client.post_call_count == 0


def test_v2_send_same_key_changed_fingerprint_is_conflict() -> None:
    client = setup_client()
    first = v2_message("ACK", message_key="asd-ack-v2-send-conflict")
    add_v2_reply(client, first, author=BOT, ts="1787471000.000051")
    changed_raw = raw_v2_message("ACK", message_key="asd-ack-v2-send-conflict")
    changed_raw["summary"] = "Changed bounded V2 engine message."
    changed = build_message_v2(changed_raw)
    with pytest.raises(DialogueEngineError) as exc:
        run(
            make_engine(client).send_message(
                thread_ts=THREAD_TS,
                context=context(),
                message=changed,
            )
        )
    assert code(exc) == "MESSAGE_KEY_CONFLICT"
    assert client.post_call_count == 0


def test_v2_send_effect_unknown_reconciles_before_retry() -> None:
    committed = setup_client()
    committed.post_behaviors = ["commit_unknown"]
    message = v2_message("ACK", message_key="asd-ack-v2-send-recovered")
    receipt = run(
        make_engine(committed).send_message(
            thread_ts=THREAD_TS,
            context=context(),
            message=message,
        )
    )
    assert receipt.action == "RECOVERED"
    assert committed.post_call_count == 1

    retry = setup_client()
    retry.post_behaviors = ["unknown_no_commit", "success"]
    retry_message = v2_message("ACK", message_key="asd-ack-v2-send-retry")
    receipt = run(
        make_engine(retry).send_message(
            thread_ts=THREAD_TS,
            context=context(),
            message=retry_message,
        )
    )
    assert receipt.action == "POSTED"
    assert retry.post_call_count == 2


def test_v2_send_second_unknown_stays_effect_unknown() -> None:
    client = setup_client()
    client.post_behaviors = ["unknown_no_commit", "unknown_no_commit"]
    with pytest.raises(DialogueEngineError) as exc:
        run(
            make_engine(client).send_message(
                thread_ts=THREAD_TS,
                context=context(),
                message=v2_message("ACK", message_key="asd-ack-v2-send-unknown"),
            )
        )
    assert code(exc) == "SEND_EFFECT_UNKNOWN"
    assert client.post_call_count == 2


def test_v2_send_definitive_transport_failure_does_not_failover() -> None:
    client = setup_client()
    client.post_behaviors = ["definitive_error"]
    with pytest.raises(DialogueEngineError) as exc:
        run(
            make_engine(client).send_message(
                thread_ts=THREAD_TS,
                context=context(),
                message=v2_message("ACK", message_key="asd-ack-v2-send-definitive"),
            )
        )
    assert code(exc) == "TRANSPORT_UNAVAILABLE"
    assert client.post_call_count == 1


@pytest.mark.parametrize("behavior", ["wrong_author", "wrong_text"])
def test_v2_send_malformed_committed_receipt_recovers_from_history(behavior: str) -> None:
    client = setup_client()
    client.post_behaviors = [behavior]
    message = v2_message(
        "ACK",
        message_key=f"asd-ack-v2-send-{behavior.replace('_', '-')}",
    )
    receipt = run(
        make_engine(client).send_message(
            thread_ts=THREAD_TS,
            context=context(),
            message=message,
        )
    )
    assert receipt.action == "RECOVERED"
    assert client.post_call_count == 1


def test_v2_send_refuses_actor_or_applicability_laundering_before_post() -> None:
    client = setup_client()
    ceo_ack = v2_message(
        "ACK",
        message_key="asd-ack-v2-send-ceo-launder",
        actor_ref=ceo_actor(),
    )
    with pytest.raises(DialogueEngineError) as exc:
        run(
            make_engine(client).send_message(
                thread_ts=THREAD_TS,
                context=context(),
                message=ceo_ack,
            )
        )
    assert code(exc) == "THREAD_CONTEXT_MISMATCH"
    assert client.post_call_count == 0

    changed_scope = v2_message(
        "ACK",
        message_key="asd-ack-v2-send-scope-launder",
        applies_to=applies("d" * 40),
    )
    with pytest.raises(DialogueEngineError) as exc:
        run(
            make_engine(client).send_message(
                thread_ts=THREAD_TS,
                context=context(),
                message=changed_scope,
            )
        )
    assert code(exc) == "THREAD_CONTEXT_MISMATCH"
    assert client.post_call_count == 0


def _decision_and_ruling() -> tuple[dict[str, object], dict[str, object]]:
    request = v2_message(
        "DECISION_REQUEST",
        message_key="asd-request-v2-engine-wait",
    )
    reply = v2_message(
        "RULING",
        message_key="asd-ruling-v2-engine-wait",
        actor_ref=ceo_actor(),
        reply_to_message_key=request["message_key"],
    )
    return request, reply


def test_v2_wait_for_reply_uses_injected_authority_policy() -> None:
    client = setup_client()
    request, reply = _decision_and_ruling()
    add_v2_reply(client, request, author=BOT, ts="1787471000.000060")
    add_v2_reply(client, reply, author=SOL1, ts="1787471000.000061")
    result = run(
        make_engine(client).wait_for_reply(
            thread_ts=THREAD_TS,
            context=context(),
            request_message_key=request["message_key"],
            expected_types=("RULING",),
            max_attempts=1,
        )
    )
    assert result["reply"] == reply
    assert result["authority"] == {
        "disposition": "CONTINUE",
        "executable": True,
        "selected_option": "opt-continue",
        "canonical_ref": None,
    }


def test_v2_executive_actor_is_not_sufficient_ruling_authority() -> None:
    client = setup_client()
    request, reply = _decision_and_ruling()
    add_v2_reply(client, request, author=BOT, ts="1787471000.000062")
    add_v2_reply(client, reply, author=SOL1, ts="1787471000.000063")
    with pytest.raises(DialogueEngineError) as exc:
        run(
            make_engine(client, authority_policy=ChairmanFloorPolicy()).wait_for_reply(
                thread_ts=THREAD_TS,
                context=context(),
                request_message_key=request["message_key"],
                expected_types=("RULING",),
                max_attempts=1,
            )
        )
    assert code(exc) == "THREAD_CONTEXT_MISMATCH"


def test_v2_wait_competing_replies_are_ambiguous() -> None:
    client = setup_client()
    request, reply = _decision_and_ruling()
    second = v2_message(
        "RULING",
        message_key="asd-ruling-v2-engine-wait-second",
        actor_ref=ceo_actor(),
        reply_to_message_key=request["message_key"],
    )
    add_v2_reply(client, request, author=BOT, ts="1787471000.000064")
    add_v2_reply(client, reply, author=SOL1, ts="1787471000.000065")
    add_v2_reply(client, second, author=SOL1, ts="1787471000.000066")
    with pytest.raises(DialogueEngineError) as exc:
        run(
            make_engine(client).wait_for_reply(
                thread_ts=THREAD_TS,
                context=context(),
                request_message_key=request["message_key"],
                expected_types=("RULING",),
                max_attempts=1,
            )
        )
    assert code(exc) == "REPLY_AMBIGUOUS"


def test_v2_wait_without_reply_times_out() -> None:
    client = setup_client()
    request = v2_message(
        "DECISION_REQUEST",
        message_key="asd-request-v2-engine-timeout",
    )
    add_v2_reply(client, request, author=BOT, ts="1787471000.000067")
    with pytest.raises(DialogueEngineError) as exc:
        run(
            make_engine(client).wait_for_reply(
                thread_ts=THREAD_TS,
                context=context(),
                request_message_key=request["message_key"],
                expected_types=("RULING",),
                max_attempts=1,
            )
        )
    assert code(exc) == "WAIT_TIMEOUT"


def test_v2_status_is_explicitly_production_inert_and_not_watcher_ready() -> None:
    status = make_engine(setup_client()).status()
    assert status["schema"] == "mastermind.agent_dialogue_status.v2"
    assert status["status"] == "DEVELOPMENT_UNARMED"
    assert status["persistent_state"] is False
    assert status["production_token_installed"] is False
    assert status["production_armed"] is False
    assert "watcher_ready" not in status
    assert "wake_ready" not in status
