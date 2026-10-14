"""Read-only Relay principal source adapter tests over the real local service.

The positive paths run the actual ``AgentDialogueService``/``DialogueEngineV2``
stack over a real AF_UNIX socket with the in-memory Slack seam; the fault paths
tamper one field of a real wire response, the established carrier-fault
pattern.  Nothing here deploys, posts, or reaches a live service.
"""
from __future__ import annotations

import ast
import asyncio
import dataclasses
import inspect
import os
from pathlib import Path
from types import MappingProxyType
from typing import Any

import pytest

from control_plane.dialogue_source_resolution import (
    DialogueSourceObservation,
    PhysicalDialogueSourceIdentity,
    attention_source_ref,
    correlated_source_ref,
)
from control_plane.wake_events import mint_obligation_id
from integrations.slack_agent_dialogue.contract_v2 import (
    build_message_v2,
    build_parent_v2,
    render_message_v2,
    render_parent_v2,
)
from integrations.slack_agent_dialogue.engine import (
    DialogueEngine,
    DialoguePolicy,
    SlackMessage,
    ThreadRead,
)
from integrations.slack_agent_dialogue.engine_v2 import DialogueContextV2, DialogueEngineV2
from integrations.slack_agent_dialogue.fake_slack import InMemorySlackClient
from integrations.slack_agent_dialogue.principal_source_reader import (
    PRINCIPAL_SOURCE_ERROR_CODE,
    PrincipalSourceError,
    PrincipalSourceRead,
    read_principal_source,
)
from integrations.slack_agent_dialogue.service import (
    CONTROL_VERSION_V2,
    AgentDialogueService,
    ServiceConfig,
    call_service,
)

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = "T0BRD2AQXQV"
OTHER_WORKSPACE = "T0BRD2AQXQW"
CHANNEL = "C0BSBM78V1N"
OTHER_CHANNEL = "C0BSBM78V1P"
BOT = "U0RELAY001"
SOL = "U0BRETDUAS2"
THREAD = "1788000000.123456"
FOREIGN_THREAD = "1788000042.654321"
PREDECESSOR_TS = "1788000001.123456"
DUPLICATE_TS = "1788000001.654321"
LATER_TS = "1788000002.123456"
CANDIDATE = {
    "mode": "ACTIVE_CURRENT_WORKER",
    "root_job_id": "JOB-100",
    "job_id": "JOB-200",
    "attempt_id": "ATT-" + "2" * 32,
    "worker_id": "codex-worker-01",
    "evidence_digest": "b" * 64,
}


def _commission() -> dict[str, str]:
    return {
        "repository": "mastermindx-market-intelligence/Mastermind",
        "commit": "c" * 40,
        "path": "research/operator-commission.md",
        "content_sha256": "d" * 64,
    }


def _parent() -> dict[str, Any]:
    return build_parent_v2(
        {
            "schema": "mastermind.agent_dialogue_parent.v2",
            "work_ref": "WS:CHAIRMAN-CONTROL-ROOM",
            "commission_ref": _commission(),
            "session_ref": "asd-session-exec-job-200",
            "operation_key": "runtime-continuity-r2",
            "watch_mode": None,
            "allowed_sol_user_ids": [SOL],
            "created_at": "2026-09-03T01:00:00Z",
        }
    )


def _actor() -> dict[str, str]:
    return {
        "kind": "worker_attempt",
        "job_id": CANDIDATE["job_id"],
        "attempt_id": CANDIDATE["attempt_id"],
        "worker_id": CANDIDATE["worker_id"],
    }


def _applies() -> dict[str, str]:
    return {
        "kind": "executive_attempt",
        "job_id": CANDIDATE["job_id"],
        "attempt_id": CANDIDATE["attempt_id"],
        "worker_id": CANDIDATE["worker_id"],
    }


def _context() -> DialogueContextV2:
    parent = _parent()
    return DialogueContextV2(
        work_ref=parent["work_ref"],
        commission_ref=parent["commission_ref"],
        session_ref=parent["session_ref"],
        operation_key=parent["operation_key"],
        watch_mode=parent["watch_mode"],
        actor_ref=_actor(),
        applies_to=_applies(),
    )


def _message(
    message_key: str, message_type: str, body: dict[str, Any], *, created_at: str
) -> dict[str, Any]:
    parent = _parent()
    return build_message_v2(
        {
            "schema": "mastermind.agent_dialogue.v2",
            "message_key": message_key,
            "message_type": message_type,
            "work_ref": parent["work_ref"],
            "commission_ref": parent["commission_ref"],
            "session_ref": parent["session_ref"],
            "actor_ref": _actor(),
            "reply_to_message_key": None,
            "applies_to": _applies(),
            "summary": "Bounded continuation evidence.",
            "body": body,
            "evidence_refs": [],
            "requires_response": False,
            "created_at": created_at,
        }
    )


PREDECESSOR = _message(
    "asd-progress-0001",
    "PROGRESS",
    {
        "stage": "source",
        "completed": "Prior work recorded.",
        "next": "Await continuation.",
    },
    created_at="2026-09-03T01:00:01Z",
)
LATER = _message(
    "asd-result-0002",
    "RESULT",
    {"status": "PASS", "result": "Bounded finding confirmed."},
    created_at="2026-09-03T01:00:02Z",
)


def _physical(
    parent: dict[str, Any] | None = None,
    *,
    thread_ts: str = THREAD,
    workspace_id: str = WORKSPACE,
    channel_id: str = CHANNEL,
    message_key: str | None = None,
    fingerprint: str | None = None,
    operation_key: str | None = None,
) -> PhysicalDialogueSourceIdentity:
    parent = parent if parent is not None else _parent()
    observation = DialogueSourceObservation(
        workspace_id=workspace_id,
        channel_id=channel_id,
        thread_ts=thread_ts,
        predecessor_message_key=message_key or PREDECESSOR["message_key"],
        predecessor_message_fingerprint=fingerprint or PREDECESSOR["fingerprint"],
    )
    operation = operation_key or parent["operation_key"]
    logical = correlated_source_ref(
        attention_source_ref=attention_source_ref(
            parent_fingerprint=parent["fingerprint"],
            message_key=observation.predecessor_message_key,
            target_seat="coo",
        ),
        parent_fingerprint=parent["fingerprint"],
        operation_key=operation,
        candidate=CANDIDATE,
    )
    return PhysicalDialogueSourceIdentity.create(
        logical_source_ref=logical,
        obligation_id=mint_obligation_id(
            source_kind="agent_dialogue_attention",
            source_ref=logical,
            wake_kind="dialogue_turn_pending",
        ),
        observation=observation,
        parent_fingerprint=parent["fingerprint"],
        operation_key=operation,
        target_seat="coo",
        candidate=CANDIDATE,
    )


class _ExactAuthorityPolicy:
    def minimum_authority(self, *, request, option) -> str:
        return "CHAIRMAN_REQUIRED"

    def allows_continuation(self, *, request, reply) -> bool:
        return False


def _policy() -> DialoguePolicy:
    return DialoguePolicy(
        workspace_id=WORKSPACE,
        channel_id=CHANNEL,
        relay_bot_user_id=BOT,
        allowed_sol_user_ids=(SOL,),
        allowed_parent_user_ids=(BOT,),
        poll_interval_seconds=0,
        method_timeout_seconds=1,
    )


def _seed(
    client: InMemorySlackClient,
    *,
    duplicate_predecessor: bool = False,
    conflicting_predecessor: bool = False,
) -> None:
    parent = _parent()
    client.add_parent(
        SlackMessage(ts=THREAD, author_user_id=BOT, text=render_parent_v2(parent))
    )
    client.add_reply(
        SlackMessage(
            ts=PREDECESSOR_TS,
            author_user_id=BOT,
            text=render_message_v2(PREDECESSOR),
            thread_ts=THREAD,
        )
    )
    if duplicate_predecessor:
        client.add_reply(
            SlackMessage(
                ts=DUPLICATE_TS,
                author_user_id=BOT,
                text=render_message_v2(PREDECESSOR),
                thread_ts=THREAD,
            )
        )
    if conflicting_predecessor:
        conflicted = dict(PREDECESSOR)
        conflicted.pop("fingerprint")
        conflicted["summary"] = "A forged conflicting continuation."
        client.add_reply(
            SlackMessage(
                ts=DUPLICATE_TS,
                author_user_id=BOT,
                text=render_message_v2(build_message_v2(conflicted)),
                thread_ts=THREAD,
            )
        )
    client.add_reply(
        SlackMessage(
            ts=LATER_TS,
            author_user_id=BOT,
            text=render_message_v2(LATER),
            thread_ts=THREAD,
        )
    )


async def _start_relay(
    socket_path: Path, client: InMemorySlackClient
) -> AgentDialogueService:
    policy = _policy()
    relay = AgentDialogueService(
        ServiceConfig(socket_path=socket_path, allowed_peer_uids=(os.geteuid(),)),
        DialogueEngine(policy, client, authority_policy=_ExactAuthorityPolicy()),
        engine_v2=DialogueEngineV2(
            policy, client, authority_policy=_ExactAuthorityPolicy()
        ),
    )
    await relay.start()
    return relay


def _mutating(mutate):
    async def service_call(socket_path, request):
        response = await call_service(socket_path, request)
        if isinstance(response, dict) and response.get("ok") is True:
            mutate(request, response)
        return response

    return service_call


def _on(operation: str, mutate_result):
    def mutate(request, response):
        if request.get("operation") == operation:
            mutate_result(response["result"])

    return mutate


def _attempt(
    tmp_path: Path,
    *,
    seed_options: dict[str, bool] | None = None,
    service_call=call_service,
    context: DialogueContextV2 | None = None,
    physical: PhysicalDialogueSourceIdentity | None = None,
) -> tuple[InMemorySlackClient, Any]:
    async def run():
        client = InMemorySlackClient(relay_bot_user_id=BOT)
        _seed(client, **(seed_options or {}))
        socket_path = tmp_path / "relay" / "principal.sock"
        relay = await _start_relay(socket_path, client)
        try:
            try:
                outcome = await read_principal_source(
                    socket_path=socket_path,
                    context=context if context is not None else _context(),
                    physical_source=physical if physical is not None else _physical(),
                    service_call=service_call,
                )
            except PrincipalSourceError as error:
                outcome = error
        finally:
            await relay.close()
        return client, outcome

    return asyncio.run(run())


def _assert_refused(outcome: Any) -> None:
    assert isinstance(outcome, PrincipalSourceError)
    assert outcome.code == PRINCIPAL_SOURCE_ERROR_CODE
    assert str(outcome) == PRINCIPAL_SOURCE_ERROR_CODE


def test_reader_signature_is_keyword_only_and_defaults_to_canonical_client() -> None:
    signature = inspect.signature(read_principal_source)
    assert list(signature.parameters) == [
        "socket_path",
        "context",
        "physical_source",
        "service_call",
    ]
    assert all(
        parameter.kind is inspect.Parameter.KEYWORD_ONLY
        for parameter in signature.parameters.values()
    )
    assert signature.parameters["service_call"].default is call_service


def test_positive_read_returns_canonical_parent_thread_and_exact_predecessor(
    tmp_path: Path,
) -> None:
    operations: list[Any] = []
    requests: list[Any] = []

    def recording(service_call):
        async def wrapped(socket_path, request):
            operations.append(request.get("operation"))
            requests.append(request)
            return await service_call(socket_path, request)

        return wrapped

    client, outcome = _attempt(tmp_path, service_call=recording(call_service))
    assert isinstance(outcome, PrincipalSourceRead)
    assert operations == ["status", "read_bound_parent", "read_thread"]
    assert requests[0] == {
        "version": CONTROL_VERSION_V2,
        "operation": "status",
        "args": {},
    }
    expected_args = {"context": _context().normalized(), "thread_ts": THREAD}
    assert requests[1]["args"] == expected_args
    assert requests[2]["args"] == expected_args

    assert dict(outcome.parent) == {**_parent(), "allowed_sol_user_ids": (SOL,)}
    assert isinstance(outcome.parent, MappingProxyType)
    assert outcome.thread_ts == THREAD
    assert isinstance(outcome.thread, ThreadRead)
    assert outcome.thread.historical_messages == ()
    assert outcome.thread.ineligible_count == 0
    assert outcome.thread.mutated_count == 0
    # The exact physical predecessor is selected, never the newest message.
    assert [item.message["message_key"] for item in outcome.thread.messages] == [
        PREDECESSOR["message_key"],
        LATER["message_key"],
    ]
    assert outcome.predecessor.message["fingerprint"] == PREDECESSOR["fingerprint"]
    assert outcome.predecessor.primary_ts == PREDECESSOR_TS
    assert outcome.predecessor.duplicate_timestamps == ()
    # Exactly one attempt per operation; the read introduced no send effect.
    assert client.channel_history_call_count == 2
    assert client.thread_history_call_count == 1
    assert client.post_call_count == 0
    assert client.parent_post_call_count == 0


def test_duplicate_physical_timestamps_survive_only_for_same_semantic_message(
    tmp_path: Path,
) -> None:
    client, outcome = _attempt(tmp_path, seed_options={"duplicate_predecessor": True})
    assert isinstance(outcome, PrincipalSourceRead)
    assert outcome.predecessor.primary_ts == PREDECESSOR_TS
    assert outcome.predecessor.duplicate_timestamps == (DUPLICATE_TS,)
    assert [item.message["message_key"] for item in outcome.thread.messages] == [
        PREDECESSOR["message_key"],
        LATER["message_key"],
    ]
    assert client.post_call_count == 0 and client.parent_post_call_count == 0


def test_same_key_conflicting_semantics_refuse(tmp_path: Path) -> None:
    client, outcome = _attempt(
        tmp_path, seed_options={"conflicting_predecessor": True}
    )
    _assert_refused(outcome)
    assert client.post_call_count == 0 and client.parent_post_call_count == 0


def test_result_is_frozen_and_deeply_read_only(tmp_path: Path) -> None:
    _client, outcome = _attempt(tmp_path)
    assert isinstance(outcome, PrincipalSourceRead)
    with pytest.raises(dataclasses.FrozenInstanceError):
        outcome.thread_ts = FOREIGN_THREAD  # type: ignore[misc]
    with pytest.raises(TypeError):
        outcome.parent["work_ref"] = "WS:FORGED-ROOM"  # type: ignore[index]
    entry = outcome.thread.messages[0]
    assert isinstance(entry.message, MappingProxyType)
    with pytest.raises(TypeError):
        entry.message["summary"] = "forged"  # type: ignore[index]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("workspace_id", OTHER_WORKSPACE),
        ("channel_id", OTHER_CHANNEL),
        ("schema", "mastermind.agent_dialogue_status.v1"),
    ],
)
def test_service_status_gate_refuses_before_any_thread_read(
    tmp_path: Path, field: str, value: str
) -> None:
    client, outcome = _attempt(
        tmp_path,
        service_call=_mutating(_on("status", lambda result: result.__setitem__(field, value))),
    )
    _assert_refused(outcome)
    assert client.channel_history_call_count == 0
    assert client.thread_history_call_count == 0
    assert client.post_call_count == 0 and client.parent_post_call_count == 0


@pytest.mark.parametrize(
    "overrides",
    [
        {"workspace_id": OTHER_WORKSPACE},
        {"channel_id": OTHER_CHANNEL},
    ],
)
def test_physical_workspace_and_channel_must_match_the_service(
    tmp_path: Path, overrides: dict[str, str]
) -> None:
    client, outcome = _attempt(tmp_path, physical=_physical(**overrides))
    _assert_refused(outcome)
    assert client.channel_history_call_count == 0
    assert client.thread_history_call_count == 0
    assert client.post_call_count == 0 and client.parent_post_call_count == 0


@pytest.mark.parametrize(
    "mutate_result",
    [
        lambda result: result.pop("attestation"),
        lambda result: result.__setitem__(
            "attestation", "mastermind.agent_dialogue.relay_parent/v2"
        ),
        lambda result: result.__setitem__("extra", 1),
    ],
)
def test_parent_binding_attestation_is_closed_and_required(
    tmp_path: Path, mutate_result
) -> None:
    client, outcome = _attempt(
        tmp_path,
        service_call=_mutating(_on("read_bound_parent", mutate_result)),
    )
    _assert_refused(outcome)
    assert client.post_call_count == 0 and client.parent_post_call_count == 0


def _rebuilt_parent(changes: dict[str, Any]) -> dict[str, Any]:
    changed = dict(_parent())
    changed.pop("fingerprint")
    changed.update(changes)
    return build_parent_v2(changed)


@pytest.mark.parametrize(
    "mutate_result",
    [
        lambda result: result.pop("thread_ts"),
        lambda result: result.__setitem__("thread_ts", FOREIGN_THREAD),
        lambda result: result.__setitem__("parent", {}),
        lambda result: result["parent"].__setitem__("fingerprint", "e" * 64),
        lambda result: result.__setitem__(
            "parent", _rebuilt_parent({"allowed_sol_user_ids": ["U0OTHER001"]})
        ),
        lambda result: result.__setitem__(
            "parent", _rebuilt_parent({"operation_key": "runtime-continuity-r3"})
        ),
        lambda result: result.__setitem__(
            "parent", _rebuilt_parent({"session_ref": "asd-session-exec-job-201"})
        ),
    ],
)
def test_changed_or_malformed_parent_binding_refuses(
    tmp_path: Path, mutate_result
) -> None:
    client, outcome = _attempt(
        tmp_path,
        service_call=_mutating(_on("read_bound_parent", mutate_result)),
    )
    _assert_refused(outcome)
    assert client.post_call_count == 0 and client.parent_post_call_count == 0


@pytest.mark.parametrize(
    "mutate_result",
    [
        lambda result: result.pop("messages"),
        lambda result: result.__setitem__("messages", {}),
        lambda result: result.__setitem__("historical_messages", [{"message": {}}]),
        lambda result: result.__setitem__("ineligible_count", "3"),
        lambda result: result.__setitem__("mutated_count", -1),
        lambda result: result.__setitem__("thread_ts", FOREIGN_THREAD),
        lambda result: result["messages"][0].__setitem__("primary_ts", "1788000001"),
        lambda result: result["messages"][0].__setitem__("extra", 1),
        lambda result: result["messages"][0].pop("duplicate_timestamps"),
        lambda result: result["messages"][0].__setitem__(
            "duplicate_timestamps",
            ["1788000001.123456", "1788000001.123456"],
        ),
        lambda result: result["messages"][0].__setitem__(
            "duplicate_timestamps", ["1788000001"]
        ),
        lambda result: result["messages"][0].__setitem__("message", {}),
        lambda result: result["messages"][0]["message"].__setitem__(
            "summary", "A forged summary."
        ),
    ],
)
def test_malformed_thread_wire_refuses(tmp_path: Path, mutate_result) -> None:
    client, outcome = _attempt(
        tmp_path,
        service_call=_mutating(_on("read_thread", mutate_result)),
    )
    _assert_refused(outcome)
    assert client.post_call_count == 0 and client.parent_post_call_count == 0


def test_missing_predecessor_refuses(tmp_path: Path) -> None:
    client, outcome = _attempt(
        tmp_path,
        physical=_physical(message_key="asd-progress-9999", fingerprint="f" * 64),
    )
    _assert_refused(outcome)
    assert client.post_call_count == 0 and client.parent_post_call_count == 0


def test_predecessor_fingerprint_drift_refuses(tmp_path: Path) -> None:
    client, outcome = _attempt(tmp_path, physical=_physical(fingerprint="f" * 64))
    _assert_refused(outcome)
    assert client.post_call_count == 0 and client.parent_post_call_count == 0


def test_foreign_thread_in_physical_source_refuses(tmp_path: Path) -> None:
    client, outcome = _attempt(tmp_path, physical=_physical(thread_ts=FOREIGN_THREAD))
    _assert_refused(outcome)
    assert client.post_call_count == 0 and client.parent_post_call_count == 0


def test_operation_key_mismatch_refuses_before_contacting_any_socket(
    tmp_path: Path,
) -> None:
    socket_path = tmp_path / "relay" / "unused.sock"
    operations = []

    async def forbidden_service_call(_path, request):
        operations.append(request["operation"])
        raise AssertionError("foreign operation must refuse before source I/O")

    with pytest.raises(PrincipalSourceError) as caught:
        asyncio.run(
            read_principal_source(
                socket_path=socket_path,
                context=_context(),
                physical_source=_physical(operation_key="runtime-continuity-r3"),
                service_call=forbidden_service_call,
            )
        )
    assert caught.value.code == PRINCIPAL_SOURCE_ERROR_CODE
    assert operations == []


@pytest.mark.parametrize(
    "overrides",
    [
        {"socket_path": Path("relative/principal.sock")},
        {"socket_path": None},
        {"context": None},
        {"context": {"work_ref": "WS:CHAIRMAN-CONTROL-ROOM"}},
        {"physical_source": object()},
        {"service_call": None},
    ],
)
def test_invalid_arguments_refuse_without_any_effect(
    tmp_path: Path, overrides: dict[str, Any]
) -> None:
    arguments: dict[str, Any] = {
        "socket_path": tmp_path / "relay" / "principal.sock",
        "context": _context(),
        "physical_source": _physical(),
        "service_call": call_service,
    }
    arguments.update(overrides)
    with pytest.raises(PrincipalSourceError) as caught:
        asyncio.run(read_principal_source(**arguments))
    assert caught.value.code == PRINCIPAL_SOURCE_ERROR_CODE


def test_foreign_engine_error_is_not_forwarded(tmp_path: Path) -> None:
    def mutate(request, response):
        if request.get("operation") == "read_bound_parent":
            response.clear()
            response.update({"ok": False, "error": {"code": "THREAD_CONTEXT_MISMATCH"}})

    client, outcome = _attempt(tmp_path, service_call=_mutating(mutate))
    _assert_refused(outcome)
    assert "THREAD_CONTEXT_MISMATCH" not in str(outcome)
    assert client.post_call_count == 0 and client.parent_post_call_count == 0


def test_private_service_exception_is_replaced_by_the_fixed_code(
    tmp_path: Path,
) -> None:
    class _Exploding:
        async def __call__(self, socket_path, request):
            raise RuntimeError("provider-session-private-1 leaked xoxb-secret-value")

    with pytest.raises(PrincipalSourceError) as caught:
        asyncio.run(
            read_principal_source(
                socket_path=tmp_path / "relay" / "principal.sock",
                context=_context(),
                physical_source=_physical(),
                service_call=_Exploding(),
            )
        )
    assert str(caught.value) == PRINCIPAL_SOURCE_ERROR_CODE
    assert "xoxb" not in str(caught.value)
    assert caught.value.__cause__ is None


def test_module_is_read_only_single_attempt_and_statically_inert() -> None:
    path = ROOT / "integrations" / "slack_agent_dialogue" / "principal_source_reader.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imports |= {
        (node.module or "").split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }
    assert imports.isdisjoint(
        {
            "sqlite3",
            "socket",
            "subprocess",
            "requests",
            "httpx",
            "mcp",
            "slack_sdk",
            "os",
            "json",
            "asyncio",
        }
    )
    source = path.read_text(encoding="utf-8").lower()
    for forbidden in (
        "ensure_thread",
        "send_message",
        "send_consultation_packet",
        "post_parent",
        "post_reply",
        "wait_for_reply",
        "read_consultation_packet",
        "bind_or_verify",
        "mint_obligation",
        "physicaldialoguesourceidentity.create",
        "retry",
        "fallback",
        "open(",
        "write_text(",
    ):
        assert forbidden not in source
    constants = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    assert {"status", "read_bound_parent", "read_thread"} <= constants
    assert constants.isdisjoint(
        {
            "send_message",
            "ensure_thread",
            "send_consultation_packet",
            "wait_for_reply",
            "read_consultation_packet",
            "bind_or_verify_thread",
            "bind_or_verify_relay_parent_thread",
        }
    )


@pytest.mark.parametrize('mutation', ['edited', 'deleted'])
@pytest.mark.parametrize('message_ts', [PREDECESSOR_TS, LATER_TS])
def test_mutated_created_history_refuses_before_principal_composition(
    tmp_path, monkeypatch, mutation, message_ts,
):
    original_seed = _seed

    def seed_with_mutation(client, **options):
        original_seed(client, **options)
        client.mutate_reply(thread_ts=THREAD, message_ts=message_ts,
                            **{mutation: True})

    monkeypatch.setattr(__import__(__name__, fromlist=['_seed']), '_seed', seed_with_mutation)
    client, outcome = _attempt(tmp_path)
    _assert_refused(outcome)
    assert client.post_call_count == client.parent_post_call_count == 0
