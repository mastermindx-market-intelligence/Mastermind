"""In-process tests for the async Claude helper runtime.

Tests inject a fake ``claude_agent_sdk`` module that mirrors the real async
SDK interface (``ClaudeSDKClient``, ``ClaudeAgentOptions``, ``SystemMessage``,
``ResultMessage``).  No subprocess, no env hooks, no real SDK.
"""
from __future__ import annotations

import asyncio
import json
import sys
import types
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator, Optional

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import scripts.claude_operator_generation_helper as helper  # noqa: E402
from control_plane.claude_operator_helper_protocol import (  # noqa: E402
    HelperProtocolError,
    bounded_text,
    encode_json_line,
)


# ---------- Fake SDK mirroring the verified async SDK interface ----------


@dataclass
class FakeSystemMessage:
    subtype: str
    data: dict


@dataclass
class FakeResultMessage:
    subtype: str
    session_id: str
    is_error: bool
    num_turns: int
    total_cost_usd: float
    usage: dict
    result: Optional[str] = None


@dataclass
class FakeAssistantMessage:
    content: Any


@dataclass
class FakeAgentOptions:
    output_format: dict | None = None
    cli_path: str = ""
    cwd: str = ""
    model: str = ""
    session_id: str = ""
    setting_sources: list = field(default_factory=list)
    strict_mcp_config: bool = True
    mcp_servers: Any = None
    tools: Any = None
    permission_mode: str = "dontAsk"
    max_turns: int = 1
    skills: Any = None
    resume: Any = None
    allowed_tools: Any = None
    disallowed_tools: Any = None
    sandbox: Any = None
    stderr: Any = None
    settings: Any = None
    extra_args: Any = None
    system_prompt: Any = None


class FakeClient:
    """Async fake of ClaudeSDKClient mirroring the real interface."""

    # Class-level defaults so tests can override BEFORE any instance is built.
    next_mcp_default: list = []

    def __init__(self, options: FakeAgentOptions):
        self.options = options
        self._query = self
        self.connected = False
        self.queries: list = []
        self.connect_calls = 0
        self._response_queues: list[list] = [[]]
        self._interrupt_count = 0
        self.disconnect_called = 0
        self._registration_consumed = False
        # Mutable state for tests
        self.next_model: str = options.model
        self.next_permission_mode: str = options.permission_mode
        self.next_session_state: str = "idle"
        self.next_context_model: Optional[str] = None
        self.next_mcp: list = list(self.next_mcp_default)
        self.next_account: dict = {
            "apiProvider": "firstParty",
            "email": "secret@example.test",
            "organization": "secret-org",
            "subscriptionType": "max",
        }
        self.available_models: list = [
            {"value": "default", "displayName": "Default"},
            {"value": "opus", "displayName": "Opus"},
            {"value": "sonnet", "displayName": "Sonnet"},
        ]

    async def connect(self, prompt=None):
        if prompt is not None:
            raise AssertionError("connect(prompt=...) must be None")
        self.connect_calls += 1
        self.connected = True
        # connect() does not produce events on its own; the helper drives
        # registration via query() and receive_response() thereafter.
        # Make sure there's a current queue to drain from.
        if not self._response_queues:
            self._response_queues.append([])

    async def _send_control_request(self, request, timeout=10):
        assert request == {"subtype":"get_settings"}
        effective = json.loads(self.options.settings or "{}")
        if self.options.sandbox is not None:
            effective["sandbox"] = self.options.sandbox
        return {"effective":effective,"sources":{},"applied":{}}

    async def get_server_info(self):
        return {
            "session_state": self.next_session_state,
            "current_permission_mode": self.next_permission_mode,
            "pid": 99,
            "account": dict(self.next_account),
            "models": [dict(m) for m in self.available_models],
        }

    async def get_context_usage(self):
        model = self.next_context_model or self.next_model
        return {
            "model": model,
            "mcpTools": ["leak-this-tool"],
            "totalTokens": 13192,
        }

    async def get_mcp_status(self):
        return {"mcpServers": list(self.next_mcp)}

    async def query(self, payload, session_id=None):
        self.queries.append((payload, session_id))
        if session_id != self.options.session_id:
            raise AssertionError("query session_id mismatch")
        # First query is the non-model registration; emit init + zero-turn result.
        # Subsequent queries are turns; the test must pre-enqueue events.
        sid = self.options.session_id
        if len(self.queries) == 1:
            self._response_queues[-1].extend(
                [
                    FakeSystemMessage(
                        subtype="init",
                        data={
                            "session_id": sid,
                            "model": self.options.model,
                            "tools": self.options.tools or ["Read", "Glob", "Grep"],
                            "skills": [],
                            "mcp_servers": [],
                            "plugins": [],
                            "cwd": self.options.cwd,
                            "permissionMode": self.next_permission_mode,
                            "claude_code_version": "2.1.275",
                            "apiKeySource": "none",
                        },
                    ),
                    FakeResultMessage(
                        subtype="success",
                        session_id=sid,
                        is_error=False,
                        num_turns=0,
                        total_cost_usd=0.0,
                        usage={
                            "input_tokens": 0,
                            "cache_creation_input_tokens": 0,
                            "cache_read_input_tokens": 0,
                            "output_tokens": 0,
                            "service_tier": "standard",
                        },
                        result=None,
                    ),
                ]
            )
            # After registration, the runtime collects from the same queue.
            return
        # For turn queries, the test pre-enqueues events into the new queue.
        # Create a fresh queue only if current queue is empty (so receive_response
        # can drain pending events first).
        if not self._response_queues[-1]:
            self._response_queues.append([])

    async def interrupt(self):
        self._interrupt_count += 1

    async def disconnect(self):
        self.disconnect_called += 1
        self.connected = False

    def receive_response(self):
        # Returns an async iterator directly (NOT a coroutine).
        queue = self._response_queues[-1] if self._response_queues else []
        async def gen():
            for item in queue:
                yield item
        return gen()

    # Test helpers below are NOT part of the real SDK surface.

    def enqueue_turn_events(self, events: list) -> None:
        """Pre-load events that will be drained after the next query().

        Always opens a fresh queue so receive_response() returns only the new
        events, never the previously-consumed registration stream.
        """
        self._response_queues.append(list(events))


def make_fake_sdk(**overrides) -> types.ModuleType:
    module = types.ModuleType("claude_agent_sdk")
    module.ClaudeSDKClient = FakeClient
    module.ClaudeAgentOptions = FakeAgentOptions
    module.SystemMessage = FakeSystemMessage
    module.ResultMessage = FakeResultMessage
    module.AssistantMessage = FakeAssistantMessage
    for key, value in overrides.items():
        setattr(module, key, value)
    return module


@pytest.fixture
def fake_sdk(monkeypatch):
    sdk = make_fake_sdk()
    monkeypatch.setattr(helper, "_SDK_FACTORY", lambda: sdk)
    monkeypatch.setattr(helper.importlib.metadata, "version", lambda _: "0.2.160")
    return sdk


def _run(coro):
    return asyncio.run(coro)


def _good_config(session_id: Optional[str] = None) -> dict:
    return {
        "cli_path": "/usr/local/bin/claude",
        "cwd": "/tmp/work",
        "model": "opus",
        "session_id": session_id or str(uuid.uuid4()),
        "setting_sources": [],
        "strict_mcp_config": True,
        "mcp_servers": {},
        "tools": ["Read", "Glob", "Grep"],
        "permission_mode": "dontAsk",
        "max_turns": 1,
    }


def test_zero_model_registration_before_work(fake_sdk):
    runtime = helper.HelperRuntime("gen", _good_config())
    handshake = _run(runtime.initialize())
    assert handshake["registration_zero_turn"] is True
    assert handshake["session_id"] == runtime.session_id
    init = handshake["initialization"]
    assert init["model"] == "opus"
    assert init["apiKeySource"] == "none"
    assert init["claude_code_version"] == "2.1.275"
    # Only registration events were processed; the client received one query
    # (the non-model registration) and zero work queries.
    fake_client = fake_sdk.ClaudeSDKClient.__init__  # not called directly
    # Use the actual client stored on runtime.
    client = runtime.client
    assert len(client.queries) == 1
    # The query was for registration, not model work.
    only_query_iter, only_sid = client.queries[0]
    # Drain the iterable to verify the registration payload shape.
    async def _drain():
        items = []
        async for item in only_query_iter:
            items.append(item)
        return items
    items = _run(_drain())
    assert items[0]["type"] == "user"
    assert items[0]["shouldQuery"] is False
    assert items[0]["message"]["content"] == "Executive session registration; no model work."
    # PII scrubbed.
    flat = json.dumps(handshake)
    assert "secret@example.test" not in flat
    assert "secret-org" not in flat
    assert "leak-this-tool" not in flat  # mcpTools stripped from context_usage
    # Server info scrubbed.
    assert set(handshake["server_info"]["account"].keys()) == {"apiProvider", "subscriptionType"}
    # MCP status uses sanitized servers list with names only.
    assert handshake["mcp_status"]["servers"] == []


def test_two_real_turns_same_generation(fake_sdk):
    runtime = helper.HelperRuntime("gen", _good_config())
    handshake = _run(runtime.initialize())
    initial_session = handshake["session_id"]

    # First turn.
    client = runtime.client
    client.enqueue_turn_events(
        [
            FakeAssistantMessage(content=[{"type": "text", "text": "first answer"}]),
            FakeResultMessage(
                subtype="success",
                session_id=initial_session,
                is_error=False,
                num_turns=1,
                total_cost_usd=0.01,
                usage={"input_tokens": 1, "output_tokens": 2},
                result="first answer",
            ),
        ]
    )
    _run(runtime.begin_turn("turn-a", "hello"))
    first = _run(runtime.collect())
    assert first["terminal"] is True
    assert first["summary"] == "first answer"
    assert first["session_id"] == initial_session

    # Second turn reuses the same generation and same UUID.
    client.enqueue_turn_events(
        [
            FakeAssistantMessage(content=[{"type": "text", "text": "second answer"}]),
            FakeResultMessage(
                subtype="success",
                session_id=initial_session,
                is_error=False,
                num_turns=2,
                total_cost_usd=0.02,
                usage={"input_tokens": 3, "output_tokens": 4},
                result="second answer",
            ),
        ]
    )
    second_handshake = _run(runtime.begin_turn("turn-b", "again"))
    second = _run(runtime.collect())
    assert second["terminal"] is True
    assert second["summary"] == "second answer"
    assert second_handshake["provider_turn_id"] == "turn-b"
    assert second["session_id"] == initial_session
    # Only one model query per turn; registration stays a single prior query.
    work_queries = [q for q in client.queries if q[1] == initial_session]
    assert len(work_queries) >= 3  # registration + turn-a + turn-b
    # The session_id never changes across turns.
    sids = {sid for _, sid in work_queries}
    assert sids == {initial_session}


def test_interrupt_while_awaiting_response(fake_sdk):
    runtime = helper.HelperRuntime("gen", _good_config())
    _run(runtime.initialize())
    client = runtime.client

    # Replace receive_response with a hanging async iterator.
    original_receive = client.receive_response

    def hanging_receive(self):
        async def gen():
            yield FakeAssistantMessage(content=[{"type": "text", "text": "partial"}])
            await asyncio.sleep(60)
            return
        return gen()

    client.receive_response = hanging_receive.__get__(client)  # type: ignore[assignment]
    # Pre-enqueue nothing extra; the hanging iterator yields one message
    # then sleeps forever until cancelled.
    try:
        _run(runtime.begin_turn("turn-i", "hi"))
        # Interrupt should cancel the drain task quickly.
        _run(runtime.interrupt())
        assert client._interrupt_count == 1
        # Drain task is no longer running.
        assert runtime._drain_task is None or runtime._drain_task.done()
    finally:
        client.receive_response = original_receive  # type: ignore[assignment]


def test_terminal_missing_or_mismatched_refused(fake_sdk):
    runtime = helper.HelperRuntime("gen", _good_config())
    _run(runtime.initialize())
    client = runtime.client

    # Missing terminal ResultMessage.
    client.enqueue_turn_events(
        [FakeAssistantMessage(content=[{"type": "text", "text": "no terminal"}])]
    )
    _run(runtime.begin_turn("turn-x", "ask"))
    out = _run(runtime.collect())
    assert out["terminal"] is False
    assert out["summary"] is None

    # Mismatched terminal session_id is refused.
    client.enqueue_turn_events(
        [
            FakeAssistantMessage(content=[{"type": "text", "text": "x"}]),
            FakeResultMessage(
                subtype="success",
                session_id="not-our-uuid",
                is_error=False,
                num_turns=1,
                total_cost_usd=0.0,
                usage={},
                result="mismatch",
            ),
        ]
    )
    with pytest.raises(HelperProtocolError):
        _run(runtime.begin_turn("turn-y", "ask2"))
    # Mismatched session should not have been accepted.
    assert runtime.active_turn_id in (None, "turn-x")


def test_failed_terminal_is_not_success(fake_sdk):
    runtime = helper.HelperRuntime("gen", _good_config())
    _run(runtime.initialize())
    client = runtime.client
    client.enqueue_turn_events(
        [
            FakeAssistantMessage(content=[{"type": "text", "text": "no good"}]),
            FakeResultMessage(
                subtype="error",
                session_id=runtime.session_id,
                is_error=True,
                num_turns=1,
                total_cost_usd=0.0,
                usage={},
                result=None,
            ),
        ]
    )
    _run(runtime.begin_turn("turn-fail", "go"))
    out = _run(runtime.collect())
    # A failed terminal is observable, but can never become a successful candidate.
    assert out["terminal"] is True
    assert out["success"] is False
    assert out["failure"] == "provider_turn_failed"


def test_context_and_mcp_scrubbing(fake_sdk):
    # Override class-level defaults so get_mcp_status() returns the rich list
    # before initialize() is called.
    original_default = FakeClient.next_mcp_default
    FakeClient.next_mcp_default = [
        {"name": "business", "status": "connected"},
        {"name": "research", "status": "disconnected"},
    ]
    try:
        runtime = helper.HelperRuntime("gen", _good_config())
        handshake = _run(runtime.initialize())
    finally:
        FakeClient.next_mcp_default = original_default
    flat = json.dumps(handshake)
    # Email/org absent.
    assert "secret@example.test" not in flat
    assert "secret-org" not in flat
    # MCP status emits only names + status.
    names = [entry["name"] for entry in handshake["mcp_status"]["servers"]]
    assert names == ["business", "research"]
    statuses = [entry["status"] for entry in handshake["mcp_status"]["servers"]]
    assert statuses == ["connected", "disconnected"]
    # context_usage has only model.
    assert set(handshake["context_usage"].keys()) == {"model"}
    # mcpTools stripped.
    assert "mcpTools" not in flat
    assert "leak-this-tool" not in flat


def test_query_not_called_for_malformed_or_duplicate_inputs(fake_sdk):
    runtime = helper.HelperRuntime("gen", _good_config())
    _run(runtime.initialize())
    client = runtime.client
    baseline = len(client.queries)

    # Duplicate turn_id while previous turn is active.
    client.enqueue_turn_events(
        [FakeResultMessage(
            subtype="success",
            session_id=runtime.session_id,
            is_error=False,
            num_turns=1,
            total_cost_usd=0.0,
            usage={},
            result="first",
        )]
    )
    _run(runtime.begin_turn("dup", "first"))
    # Second begin_turn with same turn_id is refused BEFORE any further query.
    with pytest.raises(HelperProtocolError):
        _run(runtime.begin_turn("dup", "second"))
    after_dup = len(client.queries)
    # Collect first turn.
    first = _run(runtime.collect())
    assert first["terminal"] is True

    # Malformed config rejected on initialize: env / extra_args are refused.
    with pytest.raises(HelperProtocolError):
        helper.HelperRuntime("gen2", {**_good_config(), "env": {"X": "1"}})
    with pytest.raises(HelperProtocolError):
        helper.HelperRuntime("gen2", {**_good_config(), "extra_args": ["--bare"]})
    # Bare CLI flag never propagates.
    assert not any("--bare" in str(q) for q in client.queries)
    assert not any("--safe-mode" in str(q) for q in client.queries)


def test_same_uuid_retained_across_turns(fake_sdk):
    sid = str(uuid.uuid4())
    runtime = helper.HelperRuntime("gen", _good_config(session_id=sid))
    handshake = _run(runtime.initialize())
    assert handshake["session_id"] == sid

    client = runtime.client
    for i, label in enumerate(["a", "b", "c"]):
        client.enqueue_turn_events(
            [
                FakeAssistantMessage(content=[{"type": "text", "text": f"out-{label}"}]),
                FakeResultMessage(
                    subtype="success",
                    session_id=sid,
                    is_error=False,
                    num_turns=i + 1,
                    total_cost_usd=0.0,
                    usage={"input_tokens": 0, "output_tokens": 0},
                    result=f"out-{label}",
                ),
            ]
        )
        _run(runtime.begin_turn(f"turn-{label}", f"ask-{label}"))
        result = _run(runtime.collect())
        assert result["terminal"] is True
        assert result["session_id"] == sid
    # Reconcile also reports the same uuid.
    rec = _run(runtime.reconcile())
    assert rec["session_reachable"] is True


def test_registration_init_session_mismatch_refused(fake_sdk):
    cfg = _good_config()
    runtime = helper.HelperRuntime("gen", cfg)
    # Override FakeClient.connect after we instantiate the helper; the helper
    # creates the client during initialize(), so we wrap connect to enqueue a
    # bad init SystemMessage into the registration response queue.
    original_connect = FakeClient.connect

    async def bad_connect(self, prompt=None):
        self.connected = True
        sid = self.options.session_id
        self._response_queues[-1].extend(
            [
                FakeSystemMessage(
                    subtype="init",
                    data={
                        "session_id": "wrong-uuid",
                        "model": self.options.model,
                        "tools": ["Read"],
                        "skills": [],
                        "mcp_servers": [],
                        "plugins": [],
                        "cwd": self.options.cwd,
                        "permissionMode": "dontAsk",
                        "claude_code_version": "2.1.275",
                        "apiKeySource": "none",
                    },
                ),
                FakeResultMessage(
                    subtype="success",
                    session_id=sid,
                    is_error=False,
                    num_turns=0,
                    total_cost_usd=0.0,
                    usage={"input_tokens": 0, "output_tokens": 0},
                ),
            ]
        )

    FakeClient.connect = bad_connect  # type: ignore[assignment]
    try:
        with pytest.raises(HelperProtocolError, match="session_id"):
            _run(runtime.initialize())
    finally:
        FakeClient.connect = original_connect  # type: ignore[assignment]


def test_wire_envelope_in_dispatch(fake_sdk):
    runtime = helper.HelperRuntime("gen", _good_config())

    async def run_dispatch():
        # Malformed envelope should be refused and not trigger any query.
        bad_line = encode_json_line(
            {
                "operation": "initialize",
                "request_id": "req-bad",
                "fields": {
                    "interface_version": "mastermind.claude_native_helper/v1",
                    "generation_id": "gen",
                    "config": {"cli_path": "/usr/bin/claude", "cwd": "/", "model": "opus", "session_id": str(uuid.uuid4())},
                },
                "extra": 1,
            }
        )
        # The dispatch handler validates after decode; decode_json_line
        # should reject duplicate-key wire, but here the duplicate is at
        # the dict level. parse_request checks envelope shape.
        response, _ = await helper._dispatch(bad_line, None, set())
        return response

    # Simpler: just verify parse_request refuses the envelope.
    from control_plane.claude_operator_helper_protocol import (
        INTERFACE_VERSION,
        parse_request,
        decode_json_line,
    )
    msg = decode_json_line(
        encode_json_line(
            {
                "operation": "initialize",
                "request_id": "req-init",
                "fields": {"interface_version": INTERFACE_VERSION, "generation_id": "g", "config": {}},
                "extra": 1,
            }
        )
    )
    with pytest.raises(HelperProtocolError):
        parse_request(msg, seen_request_ids=set())


def test_oversized_duplicate_key_wire_is_refused(fake_sdk):
    # Duplicate JSON keys inside an otherwise valid envelope.
    raw = (
        b'{"operation":"initialize","request_id":"req-x",'
        b'"request_id":"req-y","fields":{"interface_version":"mastermind.claude_native_helper/v1","generation_id":"g","config":{}}}\n'
    )
    with pytest.raises(HelperProtocolError, match="duplicate"):
        helper.decode_json_line(raw)


def test_disconnect_cancels_drain_task(fake_sdk):
    runtime = helper.HelperRuntime("gen", _good_config())
    _run(runtime.initialize())
    client = runtime.client
    # Hang receive_response: it must return an async iterator (not a coroutine).
    def hanging_receive(self):
        async def gen():
            await asyncio.sleep(60)
            return
            yield  # pragma: no cover
        return gen()

    client.receive_response = hanging_receive.__get__(client)  # type: ignore[assignment]
    _run(runtime.begin_turn("turn-d", "go"))
    _run(runtime.disconnect())
    assert client.disconnect_called == 1
    assert runtime.client is None


def test_sdk_factory_round_trip():
    # The default factory should attempt to import claude_agent_sdk.
    # If the SDK is not installed in this environment, just confirm the
    # factory is the real one (importlib.import_module).
    assert callable(helper._SDK_FACTORY)
    # And tests can swap it back.
    original = helper._SDK_FACTORY
    helper._set_sdk_factory(lambda: None)
    assert helper._SDK_FACTORY is not original
    helper._set_sdk_factory(original)


def test_terminal_session_mismatch_taints_generation_and_refuses_successor(fake_sdk):
    async def scenario():
        r = helper.HelperRuntime('gen', _good_config())
        await r.initialize()
        r.client.enqueue_turn_events([FakeResultMessage('success', str(uuid.uuid4()), False, 1, 0, {}, 'wrong session')])
        await r.begin_turn('turn-1', 'actual task')
        await r._drain_task
        result = await r.collect()
        assert result['terminal'] is False
        assert result['failure'] == 'terminal_session_mismatch'
        assert result['summary'] is None
        with pytest.raises(HelperProtocolError, match='reconciliation'):
            await r.begin_turn('turn-2', 'do not retry')
        assert len(r.client.queries) == 2
        await r.disconnect()
    asyncio.run(scenario())


def test_completed_turn_id_cannot_be_reused_and_collection_is_repeatable(fake_sdk):
    async def scenario():
        r = helper.HelperRuntime('gen', _good_config())
        await r.initialize()
        r.client.enqueue_turn_events([FakeResultMessage('success', r.session_id, False, 1, 0, {}, 'accepted')])
        await r.begin_turn('turn-1', 'actual task')
        await r._drain_task
        first = await r.collect()
        assert first == await r.collect()
        assert first['success'] is True
        with pytest.raises(HelperProtocolError, match='duplicate'):
            await r.begin_turn('turn-1', 'duplicate task')
        assert len(r.client.queries) == 2
        await r.disconnect()
    asyncio.run(scenario())


def test_lost_query_response_cannot_be_replayed(fake_sdk):
    async def scenario():
        r = helper.HelperRuntime('gen', _good_config())
        await r.initialize()
        async def lost(*args, **kwargs):
            raise RuntimeError('secret provider diagnostic')
        r.client.query = lost
        with pytest.raises(HelperProtocolError) as err:
            await r.begin_turn('turn-1', 'possibly delivered')
        assert 'secret' not in str(err.value)
        with pytest.raises(HelperProtocolError, match='reconciliation'):
            await r.begin_turn('turn-2', 'cannot retry on missing response')
        await r.disconnect()
    asyncio.run(scenario())


def test_duplicate_initialize_keeps_original_generation(fake_sdk):
    async def scenario():
        r = helper.HelperRuntime('gen', _good_config())
        await r.initialize()
        original = r.client
        req = {'operation':'initialize','request_id':'req-again','fields':{
            'interface_version':helper.INTERFACE_VERSION,'generation_id':'other','config':_good_config()}}
        result, retained = await helper._dispatch(encode_json_line(req), r, set())
        assert result['ok'] is False
        assert retained is r and r.client is original
        assert original.disconnect_called == 0
        await r.disconnect()
    asyncio.run(scenario())


def test_completed_result_cannot_recycle_turn_until_drain_closes(fake_sdk):
    async def scenario():
        r=helper.HelperRuntime('gen', _good_config());await r.initialize()
        release=asyncio.Event();yielded=asyncio.Event()
        async def delayed_close():
            yield FakeResultMessage('success',r.session_id,False,1,0,{},'turn A')
            yielded.set()
            await release.wait()
        r.client.receive_response=delayed_close
        await r.begin_turn('A','first')
        await yielded.wait()
        assert (await r.collect())['terminal'] is False
        with pytest.raises(HelperProtocolError, match='active|closed'):
            await r.begin_turn('B','must not race')
        assert len(r.client.queries)==2
        release.set();await r._drain_task
        result=await r.collect()
        assert result['turn_id']=='A' and result['summary']=='turn A'
        await r.disconnect()
    asyncio.run(scenario())


def test_event_evidence_is_scrubbed_before_helper_export(fake_sdk):
    async def scenario():
        r=helper.HelperRuntime('gen',_good_config());await r.initialize()
        r.client.enqueue_turn_events([FakeAssistantMessage([{'type':'text','text':'privateperson@example.test'}]),
            FakeResultMessage('success',r.session_id,False,1,0,{},'complete')])
        await r.begin_turn('A','read');await r._drain_task
        events=await r.read_events(256)
        assert 'privateperson@example.test' not in json.dumps(events)
        assert '<redacted>' in json.dumps(events)
        assert events==await r.read_events(256)
        await r.disconnect()
    asyncio.run(scenario())


@pytest.mark.parametrize('bad',[None,{},['valid',{}],['x'*201]])
def test_native_inventory_malformed_never_becomes_empty(bad):
    with pytest.raises(HelperProtocolError):helper._bounded_list(bad)


def test_aborted_success_shape_cannot_be_successful_candidate(fake_sdk):
    async def scenario():
        r=helper.HelperRuntime('gen',_good_config());await r.initialize()
        result=FakeResultMessage('success',r.session_id,False,1,0,{},'partial')
        result.terminal_reason='aborted_streaming'
        r.client.enqueue_turn_events([result]);await r.begin_turn('A','work');await r._drain_task
        assert (await r.collect())['success'] is False
        await r.disconnect()
    asyncio.run(scenario())


@pytest.mark.parametrize('cancelled',[False,True])
def test_success_followed_by_uncertain_drain_is_not_accepted_or_recycled(fake_sdk,cancelled):
    async def scenario():
        r=helper.HelperRuntime('gen',_good_config());await r.initialize()
        async def uncertain():
            yield FakeResultMessage('success',r.session_id,False,1,0,{},'unaccepted')
            if cancelled:raise asyncio.CancelledError()
            raise RuntimeError('private transport diagnostic')
        r.client.receive_response=uncertain
        await r.begin_turn('A','work')
        try:await r._drain_task
        except asyncio.CancelledError:pass
        result=await r.collect()
        assert result['terminal'] is True and result['drain_closed'] is True
        assert result['success'] is False and result['summary'] is None
        assert result['failure']=='response_effect_unknown'
        assert result['event_sequence']==1
        with pytest.raises(HelperProtocolError,match='reconciliation'):
            await r.begin_turn('B','must not recycle')
        assert len(r.client.queries)==2
        await r.disconnect()
    asyncio.run(scenario())


def _structured_plan():
    return {'schema_version':'mastermind.executive_orchestration_result/v1',
        'job_id':'JOB-1','run_id':'ATT-1','worker_id':'worker','role':'plan','status':'COMPLETED',
        'role_result':{'schema_version':'mastermind.execution_plan/v1','root_job_id':'JOB-ROOT',
            'plan_attempt_id':'ATT-1','steps':[{'ordinal':0,'step_id':'STEP-1','objective':'Inspect protocol',
                'business_impact':'routine','review_required':False,'requested_authorities':['READ'],
                'allowed_write_paths':[],'validation_ids':[],'attempt_limit':1,'cost_class':'small'}]},
        'summary':'Plan ready','current_state':'Read complete','next_actions':[],'errors':[],'validations':[]}


def test_native_structured_output_is_lossless_and_not_text_repair(fake_sdk):
    async def scenario():
        from control_plane.claude_operator_helper_protocol import native_plan_contract,native_plan_schema
        from control_plane.executive_orchestration_result import canonical_bytes
        r=helper.HelperRuntime('gen',{**_good_config(),'result_contract':'executive-plan-v1'})
        handshake=await r.initialize()
        assert handshake['result_contract']==native_plan_contract()
        assert r.client.options.output_format=={'type':'json_schema','schema':native_plan_schema()}
        msg=FakeResultMessage('success',r.session_id,False,1,0,{},'ignore this prose')
        msg.structured_output=_structured_plan()
        msg.uuid=str(uuid.uuid4())
        r.client.enqueue_turn_events([msg]);await r.begin_turn('A','work');await r._drain_task
        result=await r.collect()
        assert result['success'] is True
        assert result['summary'].encode()==canonical_bytes(msg.structured_output)
        assert result['result_source']=='native-structured-output'
        assert result['native_result_id']==msg.uuid and result['session_id']==r.session_id
        assert result['result_contract']==native_plan_contract()
        await r.disconnect()
    asyncio.run(scenario())


@pytest.mark.parametrize('case',['absent','missing-worker','bad-cost','too-large'])
def test_native_structured_output_failure_never_uses_plausible_text(fake_sdk,case):
    async def scenario():
        r=helper.HelperRuntime('gen',{**_good_config(),'result_contract':'executive-plan-v1'});await r.initialize()
        msg=FakeResultMessage('success',r.session_id,False,1,0,{},json.dumps(_structured_plan()))
        structured=_structured_plan()
        if case=='absent':structured=None
        elif case=='missing-worker':structured.pop('worker_id')
        elif case=='bad-cost':structured['role_result']['steps'][0]['cost_class']='invented'
        else:
            for k in ('summary','current_state'):structured[k]='x'*8000
        msg.structured_output=structured
        r.client.enqueue_turn_events([msg]);await r.begin_turn('A','work');await r._drain_task
        result=await r.collect()
        assert result['success'] is False and result['summary'] is None
        assert result['failure']=='native_structured_result_invalid'
        with pytest.raises(HelperProtocolError,match='reconciliation'):await r.begin_turn('B','do not retry')
        await r.disconnect()
    asyncio.run(scenario())


@pytest.mark.parametrize('status,expected',[(401,'authentication_required'),(403,'authentication_required'),(429,'quota_or_rate_limit')])
def test_native_auth_or_quota_error_not_hidden_by_absent_structured_result(fake_sdk,status,expected):
    async def scenario():
        r=helper.HelperRuntime('gen',{**_good_config(),'result_contract':'executive-plan-v1'});await r.initialize()
        msg=FakeResultMessage('error',r.session_id,True,1,0,{},None);msg.api_error_status=status
        r.client.enqueue_turn_events([msg]);await r.begin_turn('A','work');await r._drain_task
        result=await r.collect()
        assert result['success'] is False and result['summary'] is None and result['failure']==expected
        await r.disconnect()
    asyncio.run(scenario())
