"""The installed continuation must reach the existing Wake owner exactly once.

These are source/in-process tests, not proof of a live provider or deployment.
"""
import asyncio
from types import SimpleNamespace

import pytest

from control_plane.executive_service import DialogueWakeResult
from integrations.session_bridge.native_backends import CanonicalReplyCoordinator
from integrations.session_bridge.native_wire import AttentionReference
from integrations.session_bridge import runtime_attention


TARGET = "codex:11111111-2222-4444-8888-999999999999"
REFERENCE = AttentionReference("continue-operation-001", "asd-continue-one")
READ_REF = "session-reply-" + "a" * 64


def source():
    return SimpleNamespace(
        target_ref=TARGET, operation_key=REFERENCE.operation_key,
        message_key=REFERENCE.message_key, read_ref=READ_REF,
        request=SimpleNamespace(obligation=SimpleNamespace(obligation_id="WAKE-" + "b" * 32)),
    )


def setup(monkeypatch, *, guard=None, result=None):
    calls = []
    async def resolve(runtime, **kwargs):
        calls.append(("resolve", runtime, kwargs))
        return source()
    async def wake(runtime, request):
        calls.append(("wake", runtime, request))
        return result or DialogueWakeResult("RECORDED", "WAKE_RECORDED")
    monkeypatch.setattr(runtime_attention, "resolve_continuation_attention", resolve)
    runtime = object()
    callback = runtime_attention.RuntimeSessionAttention(
        runtime, dialogue_socket_path="/unused/relay.sock",
        wake_handler_provider=lambda: wake,
        admission_guard=guard or (lambda: True),
    )
    return callback, calls, runtime


def test_exact_committed_source_reaches_existing_wake_owner(monkeypatch):
    callback, calls, runtime = setup(monkeypatch)
    result = asyncio.run(callback(TARGET, REFERENCE, READ_REF))
    assert result == {"state": "RECORDED", "reason": "WAKE_RECORDED",
                      "obligation_id": "WAKE-" + "b" * 32}
    assert [x[0] for x in calls] == ["resolve", "wake"]
    assert calls[1][1] is runtime


@pytest.mark.parametrize("field", ["target_ref", "operation_key", "message_key", "read_ref"])
def test_foreign_or_stale_source_cannot_request_attention(monkeypatch, field):
    callback, calls, _ = setup(monkeypatch)
    async def wrong_source(*args, **kwargs):
        value = source()
        setattr(value, field, "foreign")
        return value
    monkeypatch.setattr(runtime_attention, "resolve_continuation_attention", wrong_source)
    assert asyncio.run(callback(TARGET, REFERENCE, READ_REF))["state"] == "UNAVAILABLE"
    assert calls == []


@pytest.mark.parametrize("guard_value", [False, None, 1, "yes"])
def test_missing_admission_has_no_source_read_or_wake(monkeypatch, guard_value):
    callback, calls, _ = setup(monkeypatch, guard=lambda: guard_value)
    assert asyncio.run(callback(TARGET, REFERENCE, READ_REF))["state"] == "UNAVAILABLE"
    assert calls == []


def test_admission_revoked_during_source_read_prevents_wake(monkeypatch):
    values = iter([True, False])
    callback, calls, _ = setup(monkeypatch, guard=lambda: next(values))
    assert asyncio.run(callback(TARGET, REFERENCE, READ_REF))["state"] == "UNAVAILABLE"
    assert [x[0] for x in calls] == ["resolve"]


def test_post_wake_admission_drift_retains_effect_uncertainty(monkeypatch):
    values = iter([True, True, False])
    callback, calls, _ = setup(monkeypatch, guard=lambda: next(values))
    assert asyncio.run(callback(TARGET, REFERENCE, READ_REF))["state"] == "EFFECT_UNKNOWN"
    assert [x[0] for x in calls] == ["resolve", "wake"]


@pytest.mark.parametrize("state,expected", [("MISSING", "UNAVAILABLE"),
                                           ("EFFECT_UNKNOWN", "EFFECT_UNKNOWN")])
def test_wake_refusal_is_not_delivery(monkeypatch, state, expected):
    callback, _, _ = setup(monkeypatch, result=DialogueWakeResult(state, "WAKE_TARGET_UNAVAILABLE"))
    assert asyncio.run(callback(TARGET, REFERENCE, READ_REF))["state"] == expected


def test_absent_existing_owner_does_not_create_an_owner(monkeypatch):
    callback, calls, _ = setup(monkeypatch)
    callback._wake_handler_provider = lambda: None
    assert asyncio.run(callback(TARGET, REFERENCE, READ_REF))["state"] == "UNAVAILABLE"
    assert calls == []


def test_changed_owner_during_source_read_is_not_rebound(monkeypatch):
    callback, calls, _ = setup(monkeypatch)
    original = callback._wake_handler_provider()
    alternate = lambda *args: DialogueWakeResult("RECORDED", "WAKE_RECORDED")
    providers = iter([original, alternate])
    callback._wake_handler_provider = lambda: next(providers)
    assert asyncio.run(callback(TARGET, REFERENCE, READ_REF))["state"] == "UNAVAILABLE"
    assert [x[0] for x in calls] == ["resolve"]


def test_duplicate_reconciliation_never_calls_attention(monkeypatch):
    callback, calls, _ = setup(monkeypatch)
    async def writer(*args):
        return {"reply_committed": True, "action": "DUPLICATE", "message_key": REFERENCE.message_key}
    coordinator = CanonicalReplyCoordinator(
        reply_writer=writer, attention_waker=lambda target, ref: callback(target, ref, READ_REF))
    result = asyncio.run(coordinator(TARGET, "Continue the original work.", "Return the finding.", REFERENCE.operation_key))
    assert result["reply_committed"] is True
    assert result["attention"] == {"state": "EFFECT_UNKNOWN"}
    assert calls == []


@pytest.mark.parametrize("failure", [RuntimeError("private owner diagnostic"),
                                    ValueError("malformed source")])
def test_source_failure_is_pre_effect_and_sanitized(monkeypatch, failure):
    callback, calls, _ = setup(monkeypatch)
    async def failing_source(*args, **kwargs):
        raise failure
    monkeypatch.setattr(runtime_attention, "resolve_continuation_attention", failing_source)
    assert asyncio.run(callback(TARGET, REFERENCE, READ_REF)) == {
        "state": "UNAVAILABLE", "reason": "ATTENTION_SOURCE_UNAVAILABLE"}
    assert calls == []


def test_owner_failure_retains_committed_effect_uncertainty(monkeypatch):
    callback, calls, _ = setup(monkeypatch)
    async def failing_owner(*args):
        calls.append(("wake",))
        raise RuntimeError("private owner diagnostic")
    callback._wake_handler_provider = lambda: failing_owner
    assert asyncio.run(callback(TARGET, REFERENCE, READ_REF)) == {
        "state": "EFFECT_UNKNOWN", "reason": "WAKE_OUTCOME_UNCONFIRMED"}
    assert [x[0] for x in calls] == ["resolve", "wake"]


@pytest.mark.parametrize("value", [None, {}, {"state": "RECORDED"}, True])
def test_untyped_owner_result_is_never_promoted(monkeypatch, value):
    callback, _, _ = setup(monkeypatch)
    def owner(*args):
        return value
    callback._wake_handler_provider = lambda: owner
    assert asyncio.run(callback(TARGET, REFERENCE, READ_REF))["state"] == "EFFECT_UNKNOWN"


@pytest.mark.parametrize("phase", ["source", "owner"])
def test_cancellation_is_not_reported_as_no_effect(monkeypatch, phase):
    callback, _, _ = setup(monkeypatch)
    async def cancel(*args, **kwargs):
        raise asyncio.CancelledError()
    if phase == "source":
        monkeypatch.setattr(runtime_attention, "resolve_continuation_attention", cancel)
    else:
        callback._wake_handler_provider = lambda: cancel
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(callback(TARGET, REFERENCE, READ_REF))


def test_typed_callback_rejects_async_admission_contract():
    async def guard():
        return True
    with pytest.raises(TypeError, match="synchronous"):
        runtime_attention.RuntimeSessionAttention(object(), dialogue_socket_path="/unused",
            wake_handler_provider=lambda: None, admission_guard=guard)
