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
    semantic_fingerprint,
)
from integrations.slack_agent_dialogue.engine import (
    DialogueContext,
    DialogueEngine,
    DialogueEngineError,
    DialoguePolicy,
    HistoryPage,
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


class ExactA1AuthorityPolicy:
    """Trusted test policy pinned to the exact bounded A1 option semantics."""

    def minimum_authority(self, *, request, option) -> str:
        semantic_option = {
            key: value for key, value in option.items() if key != "authority_effect"
        }
        if (
            request["message_type"] == "DECISION_REQUEST"
            and request["body"]["question"]
            == "Which bounded option should be selected?"
            and semantic_option
            in (
                {
                    "id": "opt-continue",
                    "summary": "Continue.",
                    "consequence": "A1 continues.",
                    "disposition": "CONTINUE",
                },
                {
                    "id": "opt-stop",
                    "summary": "Stop.",
                    "consequence": "A1 remains held.",
                    "disposition": "STOP",
                },
            )
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


def applies(head: str = "c" * 40) -> dict[str, object]:
    return {"repository": REPO, "head_sha": head, "pr": f"{REPO}#125"}


def context(head: str = "c" * 40) -> DialogueContext:
    return DialogueContext(
        "WS:CHAIRMAN-CONTROL-ROOM",
        commission(),
        "asd-session-fable0001",
        applies(head),
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


def make_engine(client: InMemorySlackClient, **policy_overrides) -> DialogueEngine:
    return DialogueEngine(
        policy(**policy_overrides),
        client,
        authority_policy=ExactA1AuthorityPolicy(),
    )


def parent_message(
    ts: str = THREAD_TS, session_ref: str = "asd-session-fable0001"
) -> SlackMessage:
    parent = build_parent(
        {
            "schema": PARENT_SCHEMA,
            "work_ref": "WS:CHAIRMAN-CONTROL-ROOM",
            "commission_ref": commission(),
            "session_ref": session_ref,
            "allowed_sol_user_ids": list(tuple(sorted((SOL1, SOL2)))),
            "created_at": "2026-08-23T08:00:00Z",
        }
    )
    return SlackMessage(ts=ts, author_user_id=SOL1, text=render_parent(parent))


def fable_message(
    kind: str = "ACK", *, key: str = "asd-ack-0001", head: str = "c" * 40
) -> dict[str, object]:
    bodies: dict[str, object] = {
        "ACK": {"acknowledged": True},
        "DECISION_REQUEST": {
            "question": "Which bounded option should be selected?",
            "outcome_impact": "The choice determines whether work continues.",
            "options": [
                {
                    "id": "opt-continue",
                    "summary": "Continue.",
                    "consequence": "A1 continues.",
                    "disposition": "CONTINUE",
                    "authority_effect": "NONE",
                },
                {
                    "id": "opt-stop",
                    "summary": "Stop.",
                    "consequence": "A1 remains held.",
                    "disposition": "STOP",
                    "authority_effect": "NONE",
                },
            ],
            "recommendation": "opt-continue",
            "work_paused": True,
        },
        "BLOCKED": {
            "blocker_code": "AUTH_REQUIRED",
            "reason": "A decision is required.",
            "needed_from": "sol",
            "work_paused": True,
        },
        "PROGRESS": {
            "stage": "build",
            "completed": "The contract is complete.",
            "next": "Run hostile tests.",
        },
        "RESULT": {"status": "PASS", "result": "The bounded wave passed."},
    }
    return build_message(
        {
            "schema": MESSAGE_SCHEMA,
            "message_key": key,
            "message_type": kind,
            "work_ref": "WS:CHAIRMAN-CONTROL-ROOM",
            "commission_ref": commission(),
            "session_ref": "asd-session-fable0001",
            "seat_ref": "fable",
            "reply_to_message_key": None,
            "applies_to": applies(head),
            "summary": "Bounded Fable message.",
            "body": bodies[kind],
            "evidence_refs": [],
            "requires_response": kind in {"DECISION_REQUEST", "BLOCKED"},
            "created_at": "2026-08-23T08:00:00Z",
        }
    )


def ruling(
    request: dict[str, object],
    *,
    key: str = "asd-ruling-0001",
    head: str = "c" * 40,
) -> dict[str, object]:
    return build_message(
        {
            "schema": MESSAGE_SCHEMA,
            "message_key": key,
            "message_type": "RULING",
            "work_ref": "WS:CHAIRMAN-CONTROL-ROOM",
            "commission_ref": commission(),
            "session_ref": "asd-session-fable0001",
            "seat_ref": "sol",
            "reply_to_message_key": request["message_key"],
            "applies_to": applies(head),
            "summary": "Bounded Sol ruling.",
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


def setup_client() -> InMemorySlackClient:
    client = InMemorySlackClient(relay_bot_user_id=BOT)
    client.add_parent(parent_message())
    return client


def add_reply(
    client: InMemorySlackClient,
    value: dict[str, object],
    *,
    author: str,
    ts: str,
    edited: bool = False,
    deleted: bool = False,
    text: str | None = None,
) -> None:
    client.add_reply(
        SlackMessage(
            ts=ts,
            author_user_id=author,
            text=render_message(value) if text is None else text,
            thread_ts=THREAD_TS,
            edited=edited,
            deleted=deleted,
        )
    )


def code(exc: pytest.ExceptionInfo[DialogueEngineError]) -> str:
    return exc.value.code


def test_exact_parent_binding_and_zero_multiple_refusal() -> None:
    engine = make_engine(setup_client())
    assert run(engine.bind_or_verify_thread(context())).thread_ts == THREAD_TS
    empty = InMemorySlackClient(relay_bot_user_id=BOT)
    with pytest.raises(DialogueEngineError) as exc:
        run(make_engine(empty).bind_or_verify_thread(context()))
    assert code(exc) == "THREAD_BINDING_AMBIGUOUS"
    duplicate = setup_client()
    duplicate.add_parent(parent_message(ts="1787471000.000002"))
    with pytest.raises(DialogueEngineError) as exc:
        run(make_engine(duplicate).bind_or_verify_thread(context()))
    assert code(exc) == "THREAD_BINDING_AMBIGUOUS"


def test_incomplete_channel_or_thread_history_refuses() -> None:
    client = setup_client()
    client.channel_history_complete = False
    with pytest.raises(DialogueEngineError) as exc:
        run(make_engine(client).bind_or_verify_thread(context()))
    assert code(exc) == "THREAD_HISTORY_INCOMPLETE"
    client.channel_history_complete = True
    client.thread_history_complete = False
    with pytest.raises(DialogueEngineError) as exc:
        run(
            make_engine(client).read_thread(
                thread_ts=THREAD_TS, context=context()
            )
        )
    assert code(exc) == "THREAD_HISTORY_INCOMPLETE"


def test_send_reconciles_duplicates_and_restart_from_history() -> None:
    client = setup_client()
    engine = make_engine(client)
    value = fable_message(key="asd-ack-restart")
    posted = run(
        engine.send_message(thread_ts=THREAD_TS, context=context(), message=value)
    )
    assert posted.action == "POSTED"
    duplicate = run(
        make_engine(client).send_message(
            thread_ts=THREAD_TS, context=context(), message=value
        )
    )
    assert duplicate.action == "DUPLICATE"
    assert duplicate.message_ts == posted.message_ts


def test_same_key_changed_fingerprint_is_conflict() -> None:
    client = setup_client()
    first = fable_message(key="asd-ack-conflict")
    changed = copy.deepcopy(first)
    changed["summary"] = "Different semantic payload."
    changed["fingerprint"] = semantic_fingerprint(changed)
    add_reply(client, first, author=BOT, ts="1787471000.000010")
    add_reply(client, changed, author=BOT, ts="1787471000.000011")
    with pytest.raises(DialogueEngineError) as exc:
        run(
            make_engine(client).read_thread(
                thread_ts=THREAD_TS, context=context()
            )
        )
    assert code(exc) == "MESSAGE_KEY_CONFLICT"


def test_committed_post_ack_loss_recovers_and_true_not_found_retries_once() -> None:
    client = setup_client()
    client.post_behaviors = ["commit_unknown"]
    receipt = run(
        make_engine(client).send_message(
            thread_ts=THREAD_TS,
            context=context(),
            message=fable_message(key="asd-ack-recovered"),
        )
    )
    assert receipt.action == "RECOVERED"
    retry = setup_client()
    retry.post_behaviors = ["unknown_no_commit", "success"]
    receipt = run(
        make_engine(retry).send_message(
            thread_ts=THREAD_TS,
            context=context(),
            message=fable_message(key="asd-ack-retry"),
        )
    )
    assert receipt.action == "POSTED"


def test_second_unknown_remains_effect_unknown() -> None:
    client = setup_client()
    client.post_behaviors = ["unknown_no_commit", "unknown_no_commit"]
    with pytest.raises(DialogueEngineError) as exc:
        run(
            make_engine(client).send_message(
                thread_ts=THREAD_TS,
                context=context(),
                message=fable_message(key="asd-ack-unknown"),
            )
        )
    assert code(exc) == "SEND_EFFECT_UNKNOWN"


@pytest.mark.parametrize("behavior", ["wrong_author", "wrong_text"])
def test_write_result_is_post_write_reconciled(behavior: str) -> None:
    client = setup_client()
    client.post_behaviors = [behavior]
    key = f"asd-ack-{behavior.replace('_', '-')}"
    with pytest.raises(DialogueEngineError) as exc:
        run(
            make_engine(client).send_message(
                thread_ts=THREAD_TS,
                context=context(),
                message=fable_message(key=key),
            )
        )
    assert code(exc) == "WRITE_RESULT_INVALID"


def test_wrong_sender_is_ineligible_but_eligible_malformed_protocol_refuses() -> None:
    client = setup_client()
    add_reply(
        client,
        fable_message(key="asd-ack-wrong-sender"),
        author="U0000000000",
        ts="1787471000.000020",
    )
    read = run(
        make_engine(client).read_thread(
            thread_ts=THREAD_TS, context=context()
        )
    )
    assert read.messages == () and read.ineligible_count == 1
    client = setup_client()
    add_reply(
        client,
        fable_message(),
        author=BOT,
        ts="1787471000.000021",
        text="MMX/AGENT_DIALOGUE_V1\nnot-json",
    )
    with pytest.raises(DialogueEngineError) as exc:
        run(
            make_engine(client).read_thread(
                thread_ts=THREAD_TS, context=context()
            )
        )
    assert code(exc) == "THREAD_MESSAGE_INVALID"


@pytest.mark.parametrize("mutation", ["edit", "delete"])
def test_edited_deleted_consumed_protocol_recovers_after_restart(
    mutation: str,
) -> None:
    client = setup_client()
    value = fable_message(key="asd-ack-edit")
    add_reply(client, value, author=BOT, ts="1787471000.000030")
    first = run(
        make_engine(client).read_thread(
            thread_ts=THREAD_TS, context=context()
        )
    )
    assert first.messages[0].message == value
    client.mutate_reply(
        thread_ts=THREAD_TS,
        message_ts="1787471000.000030",
        text="edited transport text" if mutation == "edit" else None,
        edited=mutation == "edit",
        deleted=mutation == "delete",
    )
    second = run(
        make_engine(client).read_thread(
            thread_ts=THREAD_TS, context=context()
        )
    )
    assert second.messages[0].message == value
    assert second.mutated_count == 1
    assert second.messages[0].primary_ts == first.messages[0].primary_ts


def test_missing_immutable_mutation_evidence_refuses_before_retry() -> None:
    client = setup_client()
    value = fable_message(key="asd-ack-evidence-gap")
    add_reply(client, value, author=BOT, ts="1787471000.000031")
    client.thread_mutation_evidence_complete = False
    with pytest.raises(DialogueEngineError) as exc:
        run(
            make_engine(client).send_message(
                thread_ts=THREAD_TS,
                context=context(),
                message=value,
            )
        )
    assert code(exc) == "THREAD_RECONCILIATION_INCOMPLETE"


def test_mutated_event_without_created_text_refuses_after_restart() -> None:
    client = setup_client()
    value = fable_message(key="asd-ack-created-text-gap")
    add_reply(
        client,
        value,
        author=BOT,
        ts="1787471000.000032",
        edited=True,
    )
    with pytest.raises(DialogueEngineError) as exc:
        run(
            make_engine(client).read_thread(
                thread_ts=THREAD_TS,
                context=context(),
            )
        )
    assert code(exc) == "THREAD_RECONCILIATION_INCOMPLETE"


def test_fake_decision_request_to_sol_ruling_round_trip() -> None:
    client = setup_client()
    request = fable_message("DECISION_REQUEST", key="asd-request-roundtrip")
    add_reply(client, request, author=BOT, ts="1787471000.000040")
    reply = ruling(request)
    add_reply(client, reply, author=SOL1, ts="1787471000.000041")
    result = run(
        make_engine(client).wait_for_reply(
            thread_ts=THREAD_TS,
            context=context(),
            request_message_key=request["message_key"],
            expected_types=["RULING"],
        )
    )
    assert result["authority"] == {
        "disposition": "CONTINUE",
        "executable": True,
        "selected_option": "opt-continue",
        "canonical_ref": None,
    }


def test_architecture_change_labeled_none_is_not_executable() -> None:
    client = setup_client()
    request = fable_message("DECISION_REQUEST", key="asd-request-architecture-launder")
    request["body"]["options"][0]["summary"] = "Change architecture."
    request["body"]["options"][0]["consequence"] = "Authority boundaries change."
    request["fingerprint"] = semantic_fingerprint(request)
    add_reply(client, request, author=BOT, ts="1787471000.000042")
    add_reply(
        client,
        ruling(request, key="asd-ruling-architecture-launder"),
        author=SOL1,
        ts="1787471000.000043",
    )
    with pytest.raises(DialogueEngineError) as exc:
        run(
            make_engine(client).wait_for_reply(
                thread_ts=THREAD_TS,
                context=context(),
                request_message_key=request["message_key"],
                expected_types=["RULING"],
                max_attempts=1,
            )
        )
    assert code(exc) == "THREAD_CONTEXT_MISMATCH"


def test_multiple_distinct_replies_are_ambiguous() -> None:
    client = setup_client()
    request = fable_message("DECISION_REQUEST", key="asd-request-ambiguous")
    add_reply(client, request, author=BOT, ts="1787471000.000050")
    add_reply(
        client,
        ruling(request, key="asd-ruling-a"),
        author=SOL1,
        ts="1787471000.000051",
    )
    add_reply(
        client,
        ruling(request, key="asd-ruling-b"),
        author=SOL2,
        ts="1787471000.000052",
    )
    with pytest.raises(DialogueEngineError) as exc:
        run(
            make_engine(client).wait_for_reply(
                thread_ts=THREAD_TS,
                context=context(),
                request_message_key=request["message_key"],
                expected_types=["RULING"],
            )
        )
    assert code(exc) == "REPLY_AMBIGUOUS"


def test_wait_timeout_refuses() -> None:
    client = setup_client()
    request = fable_message("DECISION_REQUEST", key="asd-request-timeout")
    add_reply(client, request, author=BOT, ts="1787471000.000060")
    with pytest.raises(DialogueEngineError) as exc:
        run(
            make_engine(client).wait_for_reply(
                thread_ts=THREAD_TS,
                context=context(),
                request_message_key=request["message_key"],
                expected_types=["RULING"],
                max_attempts=1,
            )
        )
    assert code(exc) == "WAIT_TIMEOUT"


def test_old_head_history_is_visible_but_cannot_execute_on_current_head() -> None:
    client = setup_client()
    old_request = fable_message(
        "DECISION_REQUEST", key="asd-request-old-head", head="d" * 40
    )
    old_reply = ruling(
        old_request,
        key="asd-ruling-old-head",
        head="d" * 40,
    )
    add_reply(
        client,
        old_request,
        author=BOT,
        ts="1787471000.000070",
    )
    add_reply(client, old_reply, author=SOL1, ts="1787471000.000071")
    current_request = fable_message(
        "DECISION_REQUEST", key="asd-request-new-head"
    )
    current_reply = ruling(current_request, key="asd-ruling-new-head")
    add_reply(client, current_request, author=BOT, ts="1787471000.000072")
    add_reply(client, current_reply, author=SOL1, ts="1787471000.000073")

    read = run(
        make_engine(client).read_thread(
            thread_ts=THREAD_TS, context=context()
        )
    )
    assert [item.message["message_key"] for item in read.messages] == [
        "asd-request-new-head",
        "asd-ruling-new-head",
    ]
    assert [item.message["message_key"] for item in read.historical_messages] == [
        "asd-request-old-head",
        "asd-ruling-old-head",
    ]
    result = run(
        make_engine(client).wait_for_reply(
            thread_ts=THREAD_TS,
            context=context(),
            request_message_key=current_request["message_key"],
            expected_types=["RULING"],
        )
    )
    assert result["reply"]["message_key"] == "asd-ruling-new-head"


def test_same_logical_key_across_heads_with_changed_semantics_refuses() -> None:
    client = setup_client()
    add_reply(
        client,
        fable_message(key="asd-ack-cross-head", head="d" * 40),
        author=BOT,
        ts="1787471000.000074",
    )
    add_reply(
        client,
        fable_message(key="asd-ack-cross-head"),
        author=BOT,
        ts="1787471000.000075",
    )
    with pytest.raises(DialogueEngineError) as exc:
        run(
            make_engine(client).read_thread(
                thread_ts=THREAD_TS, context=context()
            )
        )
    assert code(exc) == "MESSAGE_KEY_CONFLICT"


def test_old_head_ruling_cannot_execute_against_current_request() -> None:
    client = setup_client()
    request = fable_message(
        "DECISION_REQUEST", key="asd-request-current-with-stale-ruling"
    )
    add_reply(client, request, author=BOT, ts="1787471000.000076")
    add_reply(
        client,
        ruling(
            request,
            key="asd-ruling-stale-against-current",
            head="d" * 40,
        ),
        author=SOL1,
        ts="1787471000.000077",
    )
    with pytest.raises(DialogueEngineError) as exc:
        run(
            make_engine(client).wait_for_reply(
                thread_ts=THREAD_TS,
                context=context(),
                request_message_key=request["message_key"],
                expected_types=["RULING"],
                max_attempts=1,
            )
        )
    assert code(exc) == "WAIT_TIMEOUT"


def test_method_timeout_is_bounded_and_status_has_no_liveness_claim() -> None:
    class Slow(InMemorySlackClient):
        async def fetch_channel_history(self, *, channel_id: str, limit: int):
            await asyncio.sleep(1)
            return HistoryPage((), True, True)

    slow = Slow(relay_bot_user_id=BOT)
    with pytest.raises(DialogueEngineError) as exc:
        run(
            make_engine(slow, method_timeout_seconds=0.1).bind_or_verify_thread(
                context()
            )
        )
    assert code(exc) == "TRANSPORT_UNAVAILABLE"
    status = make_engine(setup_client()).status()
    assert status["status"] == "DEVELOPMENT_UNARMED"
    assert status["persistent_state"] is False
    assert status["production_token_installed"] is False
