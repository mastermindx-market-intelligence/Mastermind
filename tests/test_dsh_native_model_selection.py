"""Original native startup selection through the real ACP SDK; no provider effects."""
import asyncio
from contextlib import asynccontextmanager
from dataclasses import replace
import json
import socket
from types import SimpleNamespace

import pytest

from control_plane.executive_worker_broker import BrokerStateError
from control_plane.operator_harness_contract import OperationId
from integrations.acp_worker.turn import AcpProfile
from integrations.deepseek_harness.native_connection import (
    NativeAcpProcess, NativeClient, NativeProtocolError, NativeTransport, NativeWriteGuard,
)
from integrations.deepseek_harness.native_protocol import EXTENSION_V2, document, native_extension
from integrations.deepseek_harness.operator_adapter import NativeOperatorAdapter, NativeOperatorError
from scripts.ohf.acp_probe_boundary import StrictFrameReader

PROFILE = AcpProfile("deepseek-harness-acp", "0.0.1", model_option_provider="deepseek-account")
MODEL = "fixture-model"
TARGET = PROFILE.model_option_value(MODEL)
OTHER = '["deepseek-official","fixture-model"]'
SESSION = "original-native-model-session"


def options(current=OTHER, *, available=True):
    choices = [{"value": OTHER, "name": "API-key fixture"}]
    if available:
        choices.append({"value": TARGET, "name": "Account fixture"})
    return [{"id": "model", "name": "Model", "category": "model", "type": "select",
             "currentValue": current, "options": choices}]


def client():
    value = NativeClient()
    value.bind_session(SESSION)
    value.advertised = True
    return value


def setter_frame(**updates):
    params = {"sessionId": SESSION, "configId": "model", "value": TARGET}
    params.update(updates)
    return {"jsonrpc": "2.0", "id": 19, "method": "session/set_config_option", "params": params}


@pytest.mark.parametrize("changed", [
    {"sessionId": "foreign"}, {"configId": "approval"}, {"value": OTHER}, {"extra": "field"},
])
def test_setter_cannot_borrow_another_session_option_or_value(changed):
    c = client()
    c.reserve_model_selection("model", TARGET)
    with pytest.raises(NativeProtocolError):
        c.bind_outgoing(setter_frame(**changed))
    assert c.selection.request_id is None and c.current is None and c.turns == 0


def test_setter_binding_is_one_use_before_transport_can_yield():
    c = client()
    selected = c.reserve_model_selection("model", TARGET)
    c.bind_outgoing(setter_frame())
    assert selected.request_id == 19 and c.current is None and c.turns == 0
    with pytest.raises(NativeProtocolError):
        c.bind_outgoing(setter_frame())
    assert selected.request_id == 19
    with pytest.raises(NativeProtocolError):
        c.reserve_model_selection("model", TARGET)


@asynccontextmanager
async def sdk_peer(*, already_selected=False, available=True, wrong_reply=False,
                   wrong_update=False, delayed=False):
    import acp
    from acp._transport import NdjsonTransport
    from acp.task import MessageSender, TaskSupervisor
    state = SimpleNamespace(sets=[], prompts=0, news=0, progress=[],
                            entered=asyncio.Event(), release=asyncio.Event())
    if not delayed:
        state.release.set()
    class Peer:
        def on_connect(self, connection):
            self.client = connection
        async def initialize(self, **kwargs):
            return {"protocolVersion": acp.PROTOCOL_VERSION,
                    "agentInfo": {"name": PROFILE.agent_name, "version": PROFILE.agent_version},
                    "_meta": {"mastermindNative": EXTENSION_V2}}
        async def new_session(self, **kwargs):
            state.news += 1
            return {"sessionId": SESSION,
                    "configOptions": options(TARGET if already_selected else OTHER, available=available)}
        async def set_config_option(self, config_id, session_id, value, **kwargs):
            state.sets.append((session_id, config_id, value))
            state.entered.set()
            await state.release.wait()
            await self.client.session_update(session_id=session_id, update={
                "sessionUpdate": "config_option_update",
                "configOptions": options(OTHER if wrong_update else TARGET)})
            return {"configOptions": options(OTHER if wrong_reply else TARGET)}
        async def prompt(self, **kwargs):
            state.prompts += 1
            raise AssertionError("startup must not prompt")
    left, right = socket.socketpair()
    left.setblocking(False)
    right.setblocking(False)
    reader, writer = await asyncio.open_connection(sock=left, limit=65536)
    peer_reader, peer_writer = await asyncio.open_connection(sock=right, limit=65536)
    peer_task = asyncio.create_task(acp.run_agent(Peer(), peer_writer, peer_reader))
    c = NativeClient(state.progress.append)
    native = NativeAcpProcess(c)
    # Only the process principal is inert here. Protocol/framing/SDK are real.
    native.resource = object()
    tasks = TaskSupervisor(source="native-model-selection-fixture")
    native.connection = acp.connect_to_agent(c, NativeTransport(NdjsonTransport(
        StrictFrameReader(reader, c, extension_policy=c), MessageSender(writer, tasks),
        receive_timeout=None), c), observers=[c.observe_wire])
    try:
        initialized = document(await native.connection.initialize(protocol_version=acp.PROTOCOL_VERSION))
        native.initialization = initialized
        native.native_extension = native_extension(initialized["_meta"]["mastermindNative"])
        c.advertised = True
        selected = document(await native.connection.new_session(cwd="/inert-model-fixture", mcp_servers=[]))
        native.provider_session_id = selected["sessionId"]
        c.bind_session(native.provider_session_id)
        yield native, selected, state
    finally:
        state.release.set()
        await native.connection.close()
        await tasks.shutdown()
        writer.close()
        peer_writer.close()
        await asyncio.gather(writer.wait_closed(), peer_writer.wait_closed(), return_exceptions=True)
        if not peer_task.done():
            peer_task.cancel()
        await asyncio.gather(peer_task, return_exceptions=True)
        for task in tuple(native._tasks):
            if not task.done():
                task.cancel()
        if native._tasks:
            await asyncio.gather(*tuple(native._tasks), return_exceptions=True)


@pytest.mark.parametrize("already", [False, True])
def test_real_sdk_selects_only_the_advertised_account_model_without_a_prompt(already):
    async def exercise():
        async with sdk_peer(already_selected=already) as (native, selected, seen):
            await native._select_model(selected, protocol_profile=PROFILE, model=MODEL)
            assert seen.news == 1 and seen.prompts == 0 and seen.progress == []
            assert seen.sets == ([] if already else [(SESSION, "model", TARGET)])
            assert native.session_options["configOptions"][0]["currentValue"] == TARGET
            assert native.client.current is None and native.client.turns == 0
            if not already:
                selection = native.client.selection
                assert selection.task.done() and selection.request_id is not None
                assert selection.result is not None and selection.updates == 1
            with pytest.raises(NativeProtocolError, match="OWNER_CHANGED"):
                await native._select_model(selected, protocol_profile=PROFILE, model=MODEL)
    asyncio.run(exercise())


def test_unadvertised_account_option_refuses_before_set():
    async def exercise():
        async with sdk_peer(available=False) as (native, selected, seen):
            with pytest.raises(NativeProtocolError, match="UNAVAILABLE"):
                await native._select_model(selected, protocol_profile=PROFILE, model=MODEL)
            assert seen.sets == [] and seen.prompts == 0 and native.client.selection is None
    asyncio.run(exercise())


@pytest.mark.parametrize("fault", ["wrong_reply", "wrong_update"])
def test_real_selection_reply_and_notification_must_report_the_exact_target(fault):
    async def exercise():
        async with sdk_peer(**{fault: True}) as (native, selected, seen):
            with pytest.raises((NativeProtocolError, ConnectionError)):
                await native._select_model(selected, protocol_profile=PROFILE, model=MODEL)
            if fault == "wrong_update":
                assert native.client.violation == "NATIVE_MODEL_SELECTION_UPDATE_REFUSED"
            assert seen.sets == [(SESSION, "model", TARGET)] and seen.prompts == 0
            assert native.session_options is None
    asyncio.run(exercise())


def test_real_sdk_waiter_timeout_keeps_exact_original_selection_task():
    async def exercise():
        async with sdk_peer(delayed=True) as (native, selected, seen):
            original = asyncio.create_task(native._select_model(selected, protocol_profile=PROFILE, model=MODEL))
            await asyncio.wait_for(seen.entered.wait(), 2)
            selection = native.client.selection
            task = selection.task
            with pytest.raises(asyncio.TimeoutError):
                await asyncio.wait_for(asyncio.shield(original), 0.01)
            assert not original.done() and not task.done() and task in native._tasks
            assert native._closing is None and seen.sets == [(SESSION, "model", TARGET)]
            seen.release.set()
            await asyncio.wait_for(original, 2)
            assert native.client.selection is selection and selection.task is task
            assert selection.result is not None and task.done()
            assert seen.news == 1 and seen.prompts == 0 and len(seen.sets) == 1
    asyncio.run(exercise())


@pytest.mark.parametrize("fault", ["foreign-session", "post-start", "during-prompt", "wrong-target", "budget"])
def test_control_notifications_cannot_open_or_bypass_the_prompt_callback_window(fault):
    async def exercise():
        c = client()
        selection = c.reserve_model_selection("model", TARGET)
        c.bind_outgoing(setter_frame())
        session = SESSION
        current = TARGET
        if fault == "foreign-session":
            session = "foreign"
        elif fault == "post-start":
            selection.result = {"configOptions": options(TARGET)}
        elif fault == "during-prompt":
            selection.result = {"configOptions": options(TARGET)}
            c.begin_native_prompt("original-prompt")
        elif fault == "wrong-target":
            current = OTHER
        else:
            selection.updates = 4
        await c.session_update(session, {"sessionUpdate": "config_option_update",
                                        "configOptions": options(current)})
        assert c.violation == "NATIVE_MODEL_SELECTION_UPDATE_REFUSED"
        assert c._updates == 0
    asyncio.run(exercise())


def test_text_and_permissions_remain_denied_during_startup_selection():
    async def exercise():
        c = client()
        c.reserve_model_selection("model", TARGET)
        c.bind_outgoing(setter_frame())
        await c.session_update(SESSION, {"sessionUpdate": "agent_message_chunk",
                                        "content": {"type": "text", "text": "unowned input"}})
        assert c.violation == "CALLBACK_OUTSIDE_PROMPT" and c._updates == 0
        assert await c.request_permission(SESSION, {}, []) == {"outcome": {"outcome": "cancelled"}}
    asyncio.run(exercise())


@pytest.mark.parametrize("fault", ["authority", "protocol"])
def test_actual_queued_sdk_setter_rechecks_selection_authority_at_physical_write(fault):
    async def exercise():
        from acp.task import MessageSender, TaskSupervisor
        first_written, release = asyncio.Event(), asyncio.Event()
        allowed, writes, checked = [True], [], []
        c = client()
        adapter = object.__new__(NativeOperatorAdapter)
        adapter.epoch = adapter.generation = object()
        adapter.current = None
        adapter.launch_method = "session/new"
        adapter.launch_operation = OperationId("ohf-op:model-materialization")
        adapter.native = SimpleNamespace(provider_session_id=SESSION, client=c)
        def require(operation, epoch, generation, method, session):
            checked.append(method)
            if method == "session/set_config_option" and not allowed[0]:
                raise NativeProtocolError("selection authority withdrawn")
        adapter.binding = SimpleNamespace(verify_source=lambda: None, require_current_effect=require)
        c.before_send = adapter._before_send
        class Writer:
            def write(self, data):
                writes.append(data)
                first_written.set()
            async def drain(self):
                await release.wait()
        tasks = TaskSupervisor(source="native-setter-write-fixture")
        sender = MessageSender(NativeWriteGuard(Writer(), adapter._before_write), tasks)
        first = asyncio.create_task(sender.send({"method": "initialize"}))
        await first_written.wait()
        c.reserve_model_selection("model", TARGET)
        transport = NativeTransport(SimpleNamespace(send=sender.send), c)
        setter = asyncio.create_task(transport.send(setter_frame()))
        await asyncio.sleep(0)
        assert sender._queue.qsize() == 1
        if fault == "authority":
            allowed[0] = False
        else:
            c.poison("fixture protocol invalidated while queued")
        release.set()
        await first
        with pytest.raises((NativeProtocolError, NativeOperatorError)):
            await setter
        if fault == "authority":
            assert checked.count("session/set_config_option") >= 2
        else:
            assert c.violation == "fixture protocol invalidated while queued"
        assert len(writes) == 1 and b"session/set_config_option" not in writes[0]
        await tasks.shutdown()
    asyncio.run(exercise())


@pytest.mark.parametrize("waiter", ["timeout", "cancelled"])
def test_original_broker_materialization_retains_one_selection_and_late_receipt(tmp_path, monkeypatch, waiter):
    from test_dsh_native_broker import configured, request, launch_payload, close
    from test_dsh_native_operator import FixtureNative
    async def exercise():
        f = await configured(tmp_path, monkeypatch)
        original_open = FixtureNative.open
        entered, release = asyncio.Event(), asyncio.Event()
        effects = []
        async def open_with_selection(self, **kwargs):
            await original_open(self, **kwargs)
            self.client.bind_session(self.provider_session_id)
            self.client.advertised = True
            selection = self.client.reserve_model_selection("model", TARGET)
            frame = setter_frame(sessionId=self.provider_session_id)
            self.client.bind_outgoing(frame)
            self.client.before_send("session/set_config_option")
            self.client.before_write()
            effects.append(frame)
            entered.set()
            await release.wait()
            self.client.before_send("session/set_config_option")
            selection.result = {"configOptions": options(TARGET)}
        monkeypatch.setattr(FixtureNative, "open", open_with_selection)
        original_call = f.adapter._call
        if waiter == "timeout":
            monkeypatch.setattr(f.adapter, "_call",
                lambda coroutine, **kwargs: original_call(coroutine, timeout=0.02, **kwargs))
        payload = launch_payload(f)
        waiting = asyncio.create_task(request(f, "ohf-start", payload))
        await asyncio.wait_for(entered.wait(), 2)
        state = f.broker._operator_run
        future = f.adapter.materialization_call[1]
        selection = f.adapter.native.client.selection
        if waiter == "cancelled":
            waiting.cancel()
            with pytest.raises(asyncio.CancelledError):
                await waiting
        else:
            with pytest.raises(BrokerStateError, match="unknown"):
                await waiting
        assert not future.done() and state.materialization_receipt is None and len(effects) == 1
        assert (await request(f, "ohf-materialization-status", payload))["status"] == "CONFLICT"
        release.set()
        await asyncio.wait_for(asyncio.wrap_future(future), 2)
        monkeypatch.setattr(f.adapter, "_call", original_call)
        # A cancelled socket's original broker transaction may still be completing.
        if waiter == "cancelled":
            await asyncio.shield(state.materialization_task)
        status = await request(f, "ohf-materialization-status", payload)
        assert status["status"] == "RECEIPT_CURRENT_IN_LIVE_BROKER"
        assert f.adapter.native.client.selection is selection
        assert f.adapter.native.open_calls == 1 and len(effects) == 1 and len(f.factories) == 1
        assert (await request(f, "ohf-materialization-status", payload))["receipt"] == status["receipt"]
        with pytest.raises(BrokerStateError, match="model-selection"):
            f.broker.require_native_operator_effect(f.adapter, state.materialization_operation,
                f.epoch, f.generation, "session/set_config_option", f.adapter.native.provider_session_id)
        await close(f)
    asyncio.run(exercise())


@pytest.mark.parametrize("policy", [False, True])
def test_setup_notification_requires_original_explicit_frame_policy(policy):
    async def exercise():
        c = client()
        c.reserve_model_selection("model", TARGET)
        c.bind_outgoing(setter_frame())
        raw = {"jsonrpc": "2.0", "method": "session/update", "params": {
            "sessionId": SESSION, "update": {"sessionUpdate": "config_option_update",
                                           "configOptions": options(TARGET)}}}
        line = (json.dumps(raw) + "\n").encode()
        reader = asyncio.StreamReader(limit=c.limits.frame_bytes)
        reader.feed_data(line)
        guard = StrictFrameReader(reader, c, extension_policy=c if policy else None)
        if not policy:
            from scripts.ohf.acp_probe_boundary import BoundaryViolation
            with pytest.raises(BoundaryViolation, match="CALLBACK_OUTSIDE_PROMPT"):
                await guard.readuntil()
            assert c.selection.wire_updates == 0
        else:
            assert await guard.readuntil() == line
            assert c.selection.wire_updates == 1 and c.selection.updates == 0
            await c.session_update(SESSION, raw["params"]["update"])
            assert c.selection.updates == 1
            assert c.violation is None and not c._active and c.turns == 0
    asyncio.run(exercise())


def test_wire_budget_refuses_before_delayed_sdk_callbacks_can_exceed_it():
    async def exercise():
        from scripts.ohf.acp_probe_boundary import BoundaryViolation
        c = client()
        c.reserve_model_selection("model", TARGET)
        c.bind_outgoing(setter_frame())
        line = (json.dumps({"jsonrpc": "2.0", "method": "session/update", "params": {
            "sessionId": SESSION, "update": {"sessionUpdate": "config_option_update",
                                           "configOptions": options(TARGET)}}}) + "\n").encode()
        reader = asyncio.StreamReader(limit=c.limits.frame_bytes)
        reader.feed_data(line * 5)
        guard = StrictFrameReader(reader, c, extension_policy=c)
        for _ in range(4):
            assert await guard.readuntil() == line
        with pytest.raises(BoundaryViolation, match="MODEL_SELECTION_UPDATE_REFUSED"):
            await guard.readuntil()
        assert c.selection.wire_updates == 4 and c.selection.updates == 0
        assert not c._active and c.current is None
    asyncio.run(exercise())
