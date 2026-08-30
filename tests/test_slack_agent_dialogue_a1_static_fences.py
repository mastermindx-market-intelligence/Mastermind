from __future__ import annotations

import ast
import asyncio
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "integrations" / "slack_agent_dialogue"
A1_FILES = (
    PACKAGE / "contract.py",
    PACKAGE / "contract_v2.py",
    PACKAGE / "engine.py",
    PACKAGE / "engine_v2.py",
    PACKAGE / "fake_slack.py",
    PACKAGE / "service.py",
    ROOT / "scripts" / "agent_dialogue_client.py",
)

REPO = "mastermindx-market-intelligence/Mastermind"
BOT = "U0BST4WG996"
SOL1 = "U0BRETDUAS2"
SOL2 = "U0BSB73JWNL"
THREAD_TS = "1787471000.000001"
OPERATION = "worker-presence-dialogue-final-repair-20260828-001"


def combined_text() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in A1_FILES)


def test_a1_has_no_lifecycle_store_or_executive_crossover() -> None:
    lowered = combined_text().lower()
    forbidden = (
        "sqlite",
        "create table",
        "control_plane",
        "ceo_ingress",
        "sol_state",
        "executive_runtime",
        "apscheduler",
        "launchd",
        "redis",
        "postgres",
        "sqlalchemy",
        "shelve",
        "pickle",
    )
    assert all(fragment not in lowered for fragment in forbidden)


def test_a1_has_no_real_slack_sdk_or_generic_http_client() -> None:
    lowered = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            PACKAGE / "contract.py",
            PACKAGE / "contract_v2.py",
            PACKAGE / "engine.py",
            PACKAGE / "engine_v2.py",
            PACKAGE / "fake_slack.py",
            PACKAGE / "service.py",
        )
    ).lower()
    forbidden = (
        "slack_sdk",
        "urllib.request",
        "requests.",
        "httpx.",
        "aiohttp",
        "websocket",
        "socket mode",
        "conversations.history",
        "conversations.replies",
        "chat.postmessage",
    )
    assert all(fragment not in lowered for fragment in forbidden)


def test_v2_modules_do_not_import_wake_persistence_or_second_transport() -> None:
    forbidden_roots = {
        "sqlite3",
        "apscheduler",
        "redis",
        "sqlalchemy",
        "slack_sdk",
        "requests",
        "httpx",
        "aiohttp",
        "websockets",
    }
    forbidden_prefixes = (
        "control_plane.wake",
        "integrations.slack_agent_dialogue.turn_watcher",
    )
    for path in (PACKAGE / "contract_v2.py", PACKAGE / "engine_v2.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        assert not any(name.split(".", 1)[0] in forbidden_roots for name in imported)
        assert not any(
            name.startswith(prefix) for name in imported for prefix in forbidden_prefixes
        )


def test_injected_slack_seam_is_exactly_four_methods() -> None:
    tree = ast.parse((PACKAGE / "engine.py").read_text(encoding="utf-8"))
    protocol = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "SlackDialogueClient"
    )
    methods = {
        node.name
        for node in protocol.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert methods == {
        "fetch_channel_history",
        "fetch_thread",
        "post_parent",
        "post_reply",
    }


def test_local_service_exposes_only_six_operations() -> None:
    text = (PACKAGE / "service.py").read_text(encoding="utf-8")
    operations = {
        "status",
        "bind_or_verify_thread",
        "ensure_thread",
        "send_message",
        "read_thread",
        "wait_for_reply",
    }
    for operation in operations:
        assert f'operation == "{operation}"' in text
    forbidden = (
        "arbitrary_channel",
        "file_upload",
        "workspace_search",
        "user_admin",
        "execute_command",
        "dispatch_job",
        "merge_pull",
        "deploy",
    )
    lowered = text.lower()
    assert all(fragment not in lowered for fragment in forbidden)


def test_model_side_client_contains_no_token_or_credential_path() -> None:
    text = (ROOT / "scripts" / "agent_dialogue_client.py").read_text(
        encoding="utf-8"
    ).lower()
    assert "token" not in text
    assert "credential" not in text
    assert "environment" not in text
    assert "--channel" not in text
    assert "--workspace" not in text


def test_only_service_socket_path_is_written_or_unlinked() -> None:
    tree = ast.parse((PACKAGE / "service.py").read_text(encoding="utf-8"))
    attribute_calls = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            attribute_calls.append(node.func.attr)
    assert "write_text" not in attribute_calls
    assert "write_bytes" not in attribute_calls
    assert "open" not in attribute_calls
    # unlink is present only for the owner-checked AF_UNIX socket path.
    assert "unlink" in attribute_calls


def _commission() -> dict[str, str]:
    return {
        "repository": REPO,
        "commit": "a" * 40,
        "path": "research/commission.md",
        "content_sha256": "b" * 64,
    }


def _applies() -> dict[str, object]:
    return {
        "kind": "repository",
        "repository": REPO,
        "head_sha": "c" * 40,
        "pr": f"{REPO}#178",
    }


def _ceo_actor(reasoning_surface: str = "codex") -> dict[str, str]:
    return {
        "kind": "executive_surface",
        "seat": "ceo",
        "reasoning_surface": reasoning_surface,
    }


def _coo_actor() -> dict[str, str]:
    return {
        "kind": "executive_surface",
        "seat": "coo",
        "reasoning_surface": "claude",
    }


def _chairman_actor() -> dict[str, str]:
    return {
        "kind": "executive_surface",
        "seat": "chairman",
        "reasoning_surface": "chatgpt",
    }


def _worker_actor(worker_id: str = "worker-01") -> dict[str, str]:
    return {
        "kind": "worker_attempt",
        "job_id": "JOB-001",
        "attempt_id": "ATTEMPT-001",
        "worker_id": worker_id,
    }


def _worker_applies(worker_id: str = "worker-01") -> dict[str, str]:
    return {
        "kind": "executive_attempt",
        "job_id": "JOB-001",
        "attempt_id": "ATTEMPT-001",
        "worker_id": worker_id,
    }


def _decision_request(actor_ref: dict[str, str]) -> dict[str, object]:
    from integrations.slack_agent_dialogue.contract_v2 import (
        MESSAGE_SCHEMA_V2,
        build_message_v2,
    )

    return build_message_v2(
        {
            "schema": MESSAGE_SCHEMA_V2,
            "message_key": "asd-final-repair-request-0001",
            "message_type": "DECISION_REQUEST",
            "work_ref": "WS:CHAIRMAN-CONTROL-ROOM",
            "commission_ref": _commission(),
            "session_ref": "asd-session-fable0001",
            "actor_ref": actor_ref,
            "reply_to_message_key": None,
            "applies_to": _applies(),
            "summary": "Choose one bounded repair disposition.",
            "body": {
                "question": "Continue the bounded repair?",
                "outcome_impact": "Only the accepted WP-1 repair path changes.",
                "options": [
                    {
                        "id": "opt-continue",
                        "summary": "Continue.",
                        "consequence": "The bounded repair continues.",
                        "disposition": "CONTINUE",
                        "authority_effect": "NONE",
                    },
                    {
                        "id": "opt-stop",
                        "summary": "Stop.",
                        "consequence": "The bounded repair stops.",
                        "disposition": "STOP",
                        "authority_effect": "NONE",
                    },
                ],
                "recommendation": "opt-continue",
                "work_paused": True,
            },
            "evidence_refs": [],
            "requires_response": True,
            "created_at": "2026-08-28T04:05:00Z",
        }
    )


def _ruling(actor_ref: dict[str, str], request_key: str) -> dict[str, object]:
    from integrations.slack_agent_dialogue.contract_v2 import (
        MESSAGE_SCHEMA_V2,
        build_message_v2,
    )

    return build_message_v2(
        {
            "schema": MESSAGE_SCHEMA_V2,
            "message_key": "asd-final-repair-ruling-0001",
            "message_type": "RULING",
            "work_ref": "WS:CHAIRMAN-CONTROL-ROOM",
            "commission_ref": _commission(),
            "session_ref": "asd-session-fable0001",
            "actor_ref": actor_ref,
            "reply_to_message_key": request_key,
            "applies_to": _applies(),
            "summary": "Continue the bounded repair.",
            "body": {
                "authority_class": "WITHIN_COMMISSION",
                "selected_option": "opt-continue",
                "decision": "Continue.",
                "rationale": "The repair remains inside frozen scope.",
                "canonical_ref": None,
            },
            "evidence_refs": [],
            "requires_response": False,
            "created_at": "2026-08-28T04:06:00Z",
        }
    )


class _AllowAuthority:
    def minimum_authority(self, *, request, option) -> str:
        return "WITHIN_COMMISSION"

    def allows_continuation(self, *, request, reply) -> bool:
        return True


def _engine_for(actor_ref: dict[str, str]):
    from integrations.slack_agent_dialogue.contract_v2 import (
        PARENT_SCHEMA_V2,
        build_parent_v2,
        render_parent_v2,
    )
    from integrations.slack_agent_dialogue.engine import DialoguePolicy, SlackMessage
    from integrations.slack_agent_dialogue.engine_v2 import DialogueContextV2, DialogueEngineV2
    from integrations.slack_agent_dialogue.fake_slack import InMemorySlackClient

    client = InMemorySlackClient(relay_bot_user_id=BOT)
    parent = build_parent_v2(
        {
            "schema": PARENT_SCHEMA_V2,
            "work_ref": "WS:CHAIRMAN-CONTROL-ROOM",
            "commission_ref": _commission(),
            "session_ref": "asd-session-fable0001",
            "operation_key": OPERATION,
            "watch_mode": "turn_watch_v1",
            "allowed_sol_user_ids": [SOL1],
            "created_at": "2026-08-28T04:00:00Z",
        }
    )
    client.add_parent(
        SlackMessage(ts=THREAD_TS, author_user_id=SOL1, text=render_parent_v2(parent))
    )
    policy = DialoguePolicy(
        workspace_id="T0BRD2AQXQV",
        channel_id="C0BRUL9F2V7",
        relay_bot_user_id=BOT,
        allowed_sol_user_ids=(SOL1,),
        allowed_parent_user_ids=(SOL1,),
        poll_interval_seconds=0,
        max_wait_attempts=1,
    )
    context = DialogueContextV2(
        work_ref="WS:CHAIRMAN-CONTROL-ROOM",
        commission_ref=_commission(),
        session_ref="asd-session-fable0001",
        operation_key=OPERATION,
        watch_mode="turn_watch_v1",
        actor_ref=actor_ref,
        applies_to=_applies(),
    )
    return DialogueEngineV2(policy, client, authority_policy=_AllowAuthority()), client, context


def _add_reply(client, value: dict[str, object], *, ts: str) -> None:
    from integrations.slack_agent_dialogue.contract_v2 import render_message_v2
    from integrations.slack_agent_dialogue.engine import SlackMessage

    client.add_reply(
        SlackMessage(
            ts=ts,
            author_user_id=BOT,
            text=render_message_v2(value),
            thread_ts=THREAD_TS,
        )
    )


def test_v2_ceo_cannot_self_adjudicate_executable_ruling() -> None:
    from integrations.slack_agent_dialogue.engine import DialogueEngineError

    actor = _ceo_actor()
    engine, client, context = _engine_for(actor)
    request = _decision_request(actor)
    reply = _ruling(actor, str(request["message_key"]))
    _add_reply(client, request, ts="1787471000.000010")
    _add_reply(client, reply, ts="1787471000.000011")

    with pytest.raises(DialogueEngineError) as exc:
        asyncio.run(
            engine.wait_for_reply(
                thread_ts=THREAD_TS,
                context=context,
                request_message_key=str(request["message_key"]),
                expected_types=["RULING"],
                max_attempts=1,
            )
        )
    assert exc.value.code == "THREAD_CONTEXT_MISMATCH"


def test_v2_reasoning_surface_cannot_widen_same_ceo_seat() -> None:
    from integrations.slack_agent_dialogue.engine import DialogueEngineError

    request_actor = _ceo_actor("codex")
    engine, client, context = _engine_for(request_actor)
    request = _decision_request(request_actor)
    reply = _ruling(_ceo_actor("chatgpt"), str(request["message_key"]))
    _add_reply(client, request, ts="1787471000.000010")
    _add_reply(client, reply, ts="1787471000.000011")

    with pytest.raises(DialogueEngineError) as exc:
        asyncio.run(
            engine.wait_for_reply(
                thread_ts=THREAD_TS,
                context=context,
                request_message_key=str(request["message_key"]),
                expected_types=["RULING"],
                max_attempts=1,
            )
        )
    assert exc.value.code == "THREAD_CONTEXT_MISMATCH"


def test_relay_projection_does_not_require_bot_in_personal_sol_allowlist() -> None:
    request_actor = _coo_actor()
    engine, client, context = _engine_for(request_actor)
    request = _decision_request(request_actor)
    reply = _ruling(_ceo_actor(), str(request["message_key"]))
    _add_reply(client, request, ts="1787471000.000010")
    _add_reply(client, reply, ts="1787471000.000011")

    result = asyncio.run(
        engine.wait_for_reply(
            thread_ts=THREAD_TS,
            context=context,
            request_message_key=str(request["message_key"]),
            expected_types=["RULING"],
            max_attempts=1,
        )
    )
    assert BOT not in {SOL1, SOL2}
    assert result["authority"]["executable"] is True
    assert result["authority"]["disposition"] == "CONTINUE"


def test_v2_worker_frame_refuses_chatgpt_provenance_trailer() -> None:
    from integrations.slack_agent_dialogue.contract import (
        A0_PROVEN_CHATGPT_TRAILER,
        DialogueContractError,
    )
    from integrations.slack_agent_dialogue.contract_v2 import (
        MESSAGE_SCHEMA_V2,
        build_message_v2,
        parse_message_frame_v2,
        render_message_v2,
    )

    actor = _worker_actor()
    value = build_message_v2(
        {
            "schema": MESSAGE_SCHEMA_V2,
            "message_key": "asd-worker-trailer-refusal-0001",
            "message_type": "ACK",
            "work_ref": "WS:CHAIRMAN-CONTROL-ROOM",
            "commission_ref": _commission(),
            "session_ref": "asd-session-fable0001",
            "actor_ref": actor,
            "reply_to_message_key": None,
            "applies_to": _worker_applies(),
            "summary": "Worker acknowledgement.",
            "body": {"acknowledged": True},
            "evidence_refs": [],
            "requires_response": False,
            "created_at": "2026-08-28T04:07:00Z",
        }
    )
    with pytest.raises(DialogueContractError) as exc:
        parse_message_frame_v2(render_message_v2(value) + "\n" + A0_PROVEN_CHATGPT_TRAILER)
    assert exc.value.code == "TRAILER_REFUSED"


@pytest.mark.parametrize("separator", ["\u2028", "\u2029"])
def test_v2_identity_refuses_unicode_line_separator(separator: str) -> None:
    from integrations.slack_agent_dialogue.contract import DialogueContractError
    from integrations.slack_agent_dialogue.contract_v2 import MESSAGE_SCHEMA_V2, build_message_v2

    bad_worker = f"worker{separator}forged"
    with pytest.raises(DialogueContractError) as exc:
        build_message_v2(
            {
                "schema": MESSAGE_SCHEMA_V2,
                "message_key": "asd-unicode-line-refusal-0001",
                "message_type": "ACK",
                "work_ref": "WS:CHAIRMAN-CONTROL-ROOM",
                "commission_ref": _commission(),
                "session_ref": "asd-session-fable0001",
                "actor_ref": _worker_actor(bad_worker),
                "reply_to_message_key": None,
                "applies_to": _worker_applies(bad_worker),
                "summary": "Worker acknowledgement.",
                "body": {"acknowledged": True},
                "evidence_refs": [],
                "requires_response": False,
                "created_at": "2026-08-28T04:08:00Z",
            }
        )
    assert exc.value.code == "MESSAGE_INVALID"


def test_v2_text_refuses_slack_mention_shaped_value() -> None:
    from integrations.slack_agent_dialogue.contract import DialogueContractError
    from integrations.slack_agent_dialogue.contract_v2 import MESSAGE_SCHEMA_V2, build_message_v2

    with pytest.raises(DialogueContractError) as exc:
        build_message_v2(
            {
                "schema": MESSAGE_SCHEMA_V2,
                "message_key": "asd-mention-shape-refusal-0001",
                "message_type": "ACK",
                "work_ref": "WS:CHAIRMAN-CONTROL-ROOM",
                "commission_ref": _commission(),
                "session_ref": "asd-session-fable0001",
                "actor_ref": _coo_actor(),
                "reply_to_message_key": None,
                "applies_to": _applies(),
                "summary": "<@U0BRETDUAS2|Sol> projected identity must not be trusted.",
                "body": {"acknowledged": True},
                "evidence_refs": [],
                "requires_response": False,
                "created_at": "2026-08-28T04:09:00Z",
            }
        )
    assert exc.value.code == "MESSAGE_INVALID"


def test_v2_parent_and_message_invalid_trailers_stay_closed() -> None:
    from integrations.slack_agent_dialogue.contract import DialogueContractError
    from integrations.slack_agent_dialogue.contract_v2 import (
        PARENT_SCHEMA_V2,
        build_parent_v2,
        parse_message_frame_v2,
        parse_parent_frame_v2,
        render_message_v2,
        render_parent_v2,
    )

    parent = build_parent_v2(
        {
            "schema": PARENT_SCHEMA_V2,
            "work_ref": "WS:CHAIRMAN-CONTROL-ROOM",
            "commission_ref": _commission(),
            "session_ref": "asd-session-fable0001",
            "operation_key": OPERATION,
            "watch_mode": "turn_watch_v1",
            "allowed_sol_user_ids": [SOL1],
            "created_at": "2026-08-28T04:00:00Z",
        }
    )
    with pytest.raises(DialogueContractError) as parent_exc:
        parse_parent_frame_v2(render_parent_v2(parent) + "\nSent using Claude")
    assert parent_exc.value.code == "TRAILER_REFUSED"

    message = _decision_request(_coo_actor())
    with pytest.raises(DialogueContractError) as message_exc:
        parse_message_frame_v2(render_message_v2(message) + "\nSent using Claude")
    assert message_exc.value.code == "TRAILER_REFUSED"


def test_worker_requires_executive_attempt_applicability_kind() -> None:
    from integrations.slack_agent_dialogue.contract import DialogueContractError
    from integrations.slack_agent_dialogue.contract_v2 import MESSAGE_SCHEMA_V2, build_message_v2

    with pytest.raises(DialogueContractError) as exc:
        build_message_v2(
            {
                "schema": MESSAGE_SCHEMA_V2,
                "message_key": "asd-worker-kind-refusal-0001",
                "message_type": "ACK",
                "work_ref": "WS:CHAIRMAN-CONTROL-ROOM",
                "commission_ref": _commission(),
                "session_ref": "asd-session-fable0001",
                "actor_ref": _worker_actor(),
                "reply_to_message_key": None,
                "applies_to": _applies(),
                "summary": "Worker acknowledgement.",
                "body": {"acknowledged": True},
                "evidence_refs": [],
                "requires_response": False,
                "created_at": "2026-08-28T04:10:00Z",
            }
        )
    assert exc.value.code == "MESSAGE_INVALID"


def test_chairman_actor_cannot_emit_contributor_family() -> None:
    from integrations.slack_agent_dialogue.contract import DialogueContractError
    from integrations.slack_agent_dialogue.contract_v2 import MESSAGE_SCHEMA_V2, build_message_v2

    with pytest.raises(DialogueContractError) as exc:
        build_message_v2(
            {
                "schema": MESSAGE_SCHEMA_V2,
                "message_key": "asd-chairman-contributor-refusal-0001",
                "message_type": "ACK",
                "work_ref": "WS:CHAIRMAN-CONTROL-ROOM",
                "commission_ref": _commission(),
                "session_ref": "asd-session-fable0001",
                "actor_ref": _chairman_actor(),
                "reply_to_message_key": None,
                "applies_to": _applies(),
                "summary": "Contributor acknowledgement.",
                "body": {"acknowledged": True},
                "evidence_refs": [],
                "requires_response": False,
                "created_at": "2026-08-28T04:11:00Z",
            }
        )
    assert exc.value.code == "MESSAGE_INVALID"


def test_v2_parent_sol_allowlist_is_bound_but_relay_projection_is_not_personal_sol() -> None:
    from integrations.slack_agent_dialogue.contract_v2 import (
        PARENT_SCHEMA_V2,
        build_parent_v2,
        render_parent_v2,
    )
    from integrations.slack_agent_dialogue.engine import (
        DialogueEngineError,
        DialoguePolicy,
        SlackMessage,
    )
    from integrations.slack_agent_dialogue.engine_v2 import DialogueContextV2, DialogueEngineV2
    from integrations.slack_agent_dialogue.fake_slack import InMemorySlackClient

    client = InMemorySlackClient(relay_bot_user_id=BOT)
    parent = build_parent_v2(
        {
            "schema": PARENT_SCHEMA_V2,
            "work_ref": "WS:CHAIRMAN-CONTROL-ROOM",
            "commission_ref": _commission(),
            "session_ref": "asd-session-fable0001",
            "operation_key": OPERATION,
            "watch_mode": "turn_watch_v1",
            "allowed_sol_user_ids": [SOL2],
            "created_at": "2026-08-28T04:00:00Z",
        }
    )
    client.add_parent(
        SlackMessage(ts=THREAD_TS, author_user_id=SOL1, text=render_parent_v2(parent))
    )
    engine = DialogueEngineV2(
        DialoguePolicy(
            workspace_id="T0BRD2AQXQV",
            channel_id="C0BRUL9F2V7",
            relay_bot_user_id=BOT,
            allowed_sol_user_ids=(SOL1,),
            allowed_parent_user_ids=(SOL1,),
            poll_interval_seconds=0,
        ),
        client,
        authority_policy=_AllowAuthority(),
    )
    context = DialogueContextV2(
        work_ref="WS:CHAIRMAN-CONTROL-ROOM",
        commission_ref=_commission(),
        session_ref="asd-session-fable0001",
        operation_key=OPERATION,
        watch_mode="turn_watch_v1",
        actor_ref=_coo_actor(),
        applies_to=_applies(),
    )
    with pytest.raises(DialogueEngineError) as exc:
        asyncio.run(engine.bind_or_verify_thread(context))
    assert exc.value.code == "THREAD_CONTEXT_MISMATCH"
