"""Independent exact-head bridge boundary regressions; no installed effects."""
import asyncio
import inspect
import json
from pathlib import Path

import pytest

from integrations.session_bridge.gateway import SessionBridgeGateway
from integrations.session_bridge.native_backends import CanonicalReplyCoordinator, CanonicalTargetReader
from integrations.session_bridge.dialogue_reply import AgentDialogueContinueWriter
from integrations.session_bridge.schemas import BridgeError
import test_session_bridge_dialogue_reply as fx

SEND = {"target_ref": "codex:bind-001:g1", "instruction": "Continue one task.",
        "stop_condition": "Stop after one result.", "operation_key": "web-bridge-regression-001"}
CARRIER = {"reply_committed": True, "action": "POSTED", "message_key": "asd-test-reply",
           "fingerprint": "a" * 64, "thread_ts": fx.THREAD_TS}


def _gateway(reader=None, sender=None, summoner=None):
    return SessionBridgeGateway(target_reader=reader or (lambda _: []),
        reply_sender=sender or (lambda *_: dict(CARRIER)),
        summoner=summoner or (lambda _: {"accepted": True, "dispatched": False}))


@pytest.mark.parametrize("kind", [None, "codex"])
def test_async_target_projection_is_serializable_and_consumed_once(kind):
    calls = []
    async def read(name):
        calls.append(name)
        return [{"target_ref": name + ":exact"}]
    reader = CanonicalTargetReader(fabric_reader=lambda: read("fabric"),
        codex_reader=lambda: read("codex"), claude_reader=lambda: read("claude"))
    result = asyncio.run(_gateway(reader=reader).call("session_targets", {} if kind is None else {"kind": kind}))
    try:
        encoded = json.dumps(result)
        assert "exact" in encoded
        assert sorted(calls) == (["claude", "codex", "fabric"] if kind is None else ["codex"])
    finally:
        if isinstance(result.get("data"), dict):
            for value in result["data"].values():
                if inspect.iscoroutine(value):
                    value.close()


@pytest.mark.parametrize("failure", ["bridge", "reset", "timeout"])
def test_wake_failure_retains_the_already_committed_carrier(failure):
    calls = []
    def write(*_):
        calls.append("write")
        return dict(CARRIER)
    async def wake(*_):
        calls.append("wake")
        if failure == "bridge":
            raise BridgeError("arbitrary_backend_detail", "untrusted-provider-text")
        if failure == "reset":
            raise ConnectionResetError("untrusted-provider-text")
        raise TimeoutError("untrusted-provider-text")
    sender = CanonicalReplyCoordinator(reply_writer=write, attention_waker=wake)
    result = asyncio.run(_gateway(sender=sender).call("session_send", SEND))
    assert calls == ["write", "wake"]
    assert result["data"]["reply_committed"] is True
    assert result["data"]["carrier"] == CARRIER
    assert result["data"]["attention"]["state"] == "EFFECT_UNKNOWN"
    assert "untrusted-provider-text" not in json.dumps(result)


@pytest.mark.parametrize("failure", ["reset", "timeout", "malformed"])
def test_lost_carrier_reply_is_unknown_not_a_no_effect_refusal(failure):
    class LostReply(fx.Service):
        async def __call__(self, socket_path, request):
            if request["operation"] == "read_thread":
                return await super().__call__(socket_path, request)
            self.calls.append((socket_path, request))
            if failure == "reset":
                raise ConnectionResetError("after-send-private-detail")
            if failure == "timeout":
                raise TimeoutError("after-send-private-detail")
            return None
    service = LostReply()
    with pytest.raises(BridgeError) as caught:
        fx._run(service)
    assert caught.value.code == "carrier_effect_unknown"
    assert "private-detail" not in caught.value.message
    assert [r[1]["operation"] for r in service.calls] == ["read_thread", "send_message"]


@pytest.mark.parametrize("field", ["instruction", "stop_condition"])
def test_changed_payload_does_not_mint_a_new_message_identity(field):
    writer = AgentDialogueContinueWriter(fx.Resolver(), socket_path=Path("/private/tmp/not-used.sock"), service_call=fx.Service())
    kwargs = dict(request_message=fx._worker_result(), context=writer._context(fx._binding()),
        instruction=SEND["instruction"], stop_condition=SEND["stop_condition"], operation_key=SEND["operation_key"])
    first = writer._message(**kwargs)
    second = writer._message(**{**kwargs, field: "Different semantic payload."})
    assert first["message_key"] == second["message_key"]
    assert first["fingerprint"] != second["fingerprint"]


def test_different_operations_keep_distinct_message_identity():
    writer = AgentDialogueContinueWriter(fx.Resolver(), socket_path=Path("/private/tmp/not-used.sock"), service_call=fx.Service())
    kwargs = dict(request_message=fx._worker_result(), context=writer._context(fx._binding()),
        instruction=SEND["instruction"], stop_condition=SEND["stop_condition"], operation_key=SEND["operation_key"])
    assert writer._message(**kwargs)["message_key"] != writer._message(**{**kwargs, "operation_key": "other-operation-001"})["message_key"]


@pytest.mark.parametrize("tool", ["session_send", "session_summon"])
def test_uncaught_backend_failure_has_a_bounded_unknown_result(tool):
    calls = []
    async def fail(*_):
        calls.append(1)
        raise ConnectionResetError("untrusted-secret-shaped-error")
    args = SEND if tool == "session_send" else {"objective": "One useful task.",
        "execution_profile": "research_only", "operation_key": SEND["operation_key"]}
    result = asyncio.run(_gateway(sender=fail, summoner=fail).call(tool, args))
    assert calls == [1]
    assert result["ok"] is False
    assert result["error"]["code"] == "effect_unknown"
    assert "untrusted-secret" not in json.dumps(result)


def test_cancellation_is_not_swallowed_or_retried():
    calls = []
    async def cancel(*_):
        calls.append(1)
        raise asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(_gateway(sender=cancel).call("session_send", SEND))
    assert calls == [1]


@pytest.mark.parametrize("code", ["SERVICE_UNAVAILABLE", "REQUEST_INVALID", "SEND_EFFECT_UNKNOWN"])
def test_existing_typed_carrier_classification_is_preserved(code):
    from integrations.slack_agent_dialogue.service import DialogueServiceError
    class Refused(fx.Service):
        async def __call__(self, path, request):
            if request["operation"] == "read_thread":
                return await super().__call__(path, request)
            raise DialogueServiceError(code)
    with pytest.raises(BridgeError) as caught:
        fx._run(Refused())
    assert caught.value.code == ("carrier_effect_unknown" if code == "SEND_EFFECT_UNKNOWN" else "carrier_unavailable")


def test_same_operation_payload_race_uses_existing_engine_conflict_not_two_posts():
    import test_slack_agent_dialogue_engine_v2 as ef
    from integrations.slack_agent_dialogue.engine import DialogueEngineError

    class HeldClient(ef.InMemorySlackClient):
        def __init__(self):
            super().__init__(relay_bot_user_id=ef.BOT)
            self.entered = asyncio.Event()
            self.release = asyncio.Event()
            self.entered_count = 0
        async def post_reply(self, **kwargs):
            self.entered_count += 1
            self.entered.set()
            await self.release.wait()
            return await super().post_reply(**kwargs)

    async def scenario():
        client = HeldClient()
        client.add_parent(ef.parent_message())
        engine = ef.make_engine(client)
        context = ef.context(actor_ref=ef.ceo_actor())
        request = ef.v2_message("ACK", message_key="asd-worker-race-return")
        kwargs = dict(request_message=request, context=context.normalized(),
            instruction="Original bounded instruction.", stop_condition="One result.",
            operation_key="web-race-operation-001")
        first_message = AgentDialogueContinueWriter._message(**kwargs)
        changed_message = AgentDialogueContinueWriter._message(**{**kwargs, "instruction": "Changed bounded instruction."})
        first = await engine.prepare_send_message(thread_ts=ef.THREAD_TS, context=context, message=first_message)
        changed = await engine.prepare_send_message(thread_ts=ef.THREAD_TS, context=context, message=changed_message)
        first_task = asyncio.create_task(engine.commit_send_message(first, fingerprint=first.fingerprint))
        second_task = None
        try:
            await asyncio.wait_for(client.entered.wait(), 1)
            second_task = asyncio.create_task(engine.commit_send_message(changed, fingerprint=changed.fingerprint))
            await asyncio.sleep(.02)
            client.release.set()
            first_result, second_result = await asyncio.gather(first_task, second_task, return_exceptions=True)
            assert not isinstance(first_result, Exception)
            assert isinstance(second_result, DialogueEngineError)
            assert second_result.code == "MESSAGE_KEY_CONFLICT"
            assert client.post_call_count == 1
            assert client.entered_count == 1
        finally:
            client.release.set()
            await asyncio.gather(*[task for task in (first_task, second_task) if task is not None], return_exceptions=True)
    asyncio.run(scenario())


@pytest.mark.parametrize("lose_commit_reply", [False, True])
def test_real_unix_dialogue_commit_reopen_preserves_one_reply(lose_commit_reply):
    import tempfile
    import os
    import dataclasses
    import test_slack_agent_dialogue_service as sf
    import test_slack_agent_dialogue_engine_v2 as ef
    from integrations.slack_agent_dialogue.contract_v2 import render_message_v2
    from integrations.slack_agent_dialogue.service import AgentDialogueService, ServiceConfig

    class LoseOneCommitReply(AgentDialogueService):
        lost = False
        async def _send(self, writer, value):
            result = value.get("result", {})
            if lose_commit_reply and not self.lost and isinstance(result, dict) and result.get("action") == "POSTED":
                self.lost = True
                writer.close()
                await writer.wait_closed()
                return
            await super()._send(writer, value)

    async def scenario(socket_path):
        binding = dataclasses.replace(fx._binding(), thread_ts=ef.THREAD_TS)
        client = ef.InMemorySlackClient(relay_bot_user_id=ef.BOT)
        client.add_parent(ef.parent_message(author=ef.BOT, work_ref=binding.work_ref,
            commission_ref=dict(binding.commission_ref), session_ref=binding.session_ref,
            operation_key=binding.dialogue_operation_key, watch_mode=binding.watch_mode))
        client.add_reply(ef.SlackMessage(ts="1787471001.000001", author_user_id=ef.BOT,
            text=render_message_v2(fx._worker_result()), thread_ts=binding.thread_ts))
        legacy_engine, _ = sf.engine_and_client()
        service = LoseOneCommitReply(ServiceConfig(socket_path=socket_path,
            allowed_peer_uids=(os.geteuid(),), request_timeout_seconds=1),
            legacy_engine, engine_v2=ef.make_engine(client))
        wake_calls = []
        async def wake(*args):
            wake_calls.append(args)
            raise TimeoutError("untrusted-wake-error")
        def new_gateway():
            writer = AgentDialogueContinueWriter(fx.Resolver(binding), socket_path=socket_path)
            return _gateway(sender=CanonicalReplyCoordinator(reply_writer=writer, attention_waker=wake))
        await service.start()
        try:
            first = await new_gateway().call("session_send", SEND)
            assert first.get("data") is not None or first["error"]["code"] == "carrier_effect_unknown", first
            if lose_commit_reply:
                assert first["ok"] is False
                assert first["error"]["code"] == "carrier_effect_unknown"
                assert not wake_calls
            else:
                assert first["data"]["reply_committed"] is True
                assert first["data"]["carrier"]["action"] == "POSTED"
                assert first["data"]["attention"]["state"] == "EFFECT_UNKNOWN"
            assert client.post_call_count == 1
            reopened = await new_gateway().call("session_send", SEND)
            assert reopened["data"]["reply_committed"] is True
            assert reopened["data"]["carrier"]["action"] == "DUPLICATE"
            assert reopened["data"]["attention"]["state"] == "EFFECT_UNKNOWN"
            assert client.post_call_count == 1
            assert service.lost is lose_commit_reply
            changed = await new_gateway().call("session_send", {**SEND, "instruction": "Changed operation payload."})
            assert changed["ok"] is False
            assert client.post_call_count == 1
            assert "untrusted-wake-error" not in json.dumps([first, reopened, changed])
        finally:
            await service.close()
        assert not socket_path.exists()
    with tempfile.TemporaryDirectory(prefix="mmx-bridge-", dir=str(Path(tempfile.gettempdir()).resolve())) as tmp:
        asyncio.run(scenario(Path(tmp).resolve() / "dialogue.sock"))


@pytest.mark.parametrize("first_async", [True, False])
def test_mixed_projection_readers_preserve_sync_and_async_results(first_async):
    calls = []
    async def asynchronous(name):
        calls.append(name)
        return [name]
    def synchronous(name):
        calls.append(name)
        return [name]
    first = (lambda: asynchronous("fabric")) if first_async else (lambda: synchronous("fabric"))
    reader = CanonicalTargetReader(fabric_reader=first,
        codex_reader=lambda: asynchronous("codex"), claude_reader=lambda: synchronous("claude"))
    result = asyncio.run(_gateway(reader=reader).call("session_targets", {}))
    assert result["data"] == {"fabric_attempt": ["fabric"], "codex": ["codex"], "claude": ["claude"]}
    assert calls == ["fabric", "codex", "claude"]


def test_async_reader_failure_does_not_start_unconsumed_siblings():
    calls = []
    async def fail():
        calls.append("fabric")
        raise ConnectionResetError("read-backend-private-detail")
    def not_started():
        calls.append("unexpected-sibling")
        raise AssertionError("unneeded reader must not start")
    reader = CanonicalTargetReader(fabric_reader=fail, codex_reader=not_started, claude_reader=not_started)
    result = asyncio.run(_gateway(reader=reader).call("session_targets", {}))
    assert result["error"]["code"] == "backend_unavailable"
    assert "private-detail" not in json.dumps(result)
    assert calls == ["fabric"]


def test_operation_identity_does_not_change_with_newer_return_version():
    writer = AgentDialogueContinueWriter(fx.Resolver(), socket_path=Path("/private/tmp/not-used.sock"), service_call=fx.Service())
    original = fx._worker_result()
    kwargs = dict(request_message=original, context=writer._context(fx._binding()),
        instruction=SEND["instruction"], stop_condition=SEND["stop_condition"], operation_key=SEND["operation_key"])
    first = writer._message(**kwargs)
    second = writer._message(**{**kwargs, "request_message": {**original, "message_key": "asd-newer-return-version"}})
    assert first["message_key"] == second["message_key"]
    assert first["fingerprint"] != second["fingerprint"]
