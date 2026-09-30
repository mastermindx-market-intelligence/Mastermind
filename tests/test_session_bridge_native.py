import asyncio

from integrations.session_bridge.native_backends import (
    CanonicalReplyCoordinator,
    CanonicalTargetReader,
    ExactTargetRouter,
    ExecutiveSummonAdapter,
)
from integrations.session_bridge.schemas import BridgeError


def test_exact_target_router_never_falls_back():
    calls = []
    router = ExactTargetRouter(
        fabric_reply=lambda *args: calls.append(("fabric", args)),
        codex_reply=lambda *args: calls.append(("codex", args)),
        claude_reply=lambda *args: calls.append(("claude", args)),
    )
    router("codex:binding-7", "Continue.", "Stop after result.", "op-001")
    assert calls == [
        (
            "codex",
            ("codex:binding-7", "Continue.", "Stop after result.", "op-001"),
        )
    ]


def test_unknown_target_kind_is_refused():
    router = ExactTargetRouter(
        fabric_reply=lambda *_: None,
        codex_reply=lambda *_: None,
        claude_reply=lambda *_: None,
    )
    try:
        router("newest-tab:any", "Continue.", "Stop.", "op-001")
    except BridgeError as exc:
        assert exc.code == "not_found"
    else:
        raise AssertionError("implicit/newest-tab routing must be refused")


def test_reply_coordinator_commits_carrier_before_wake():
    events = []

    async def writer(target_ref, instruction, stop_condition, operation_key):
        events.append(("carrier", target_ref, operation_key))
        return {
            "reply_committed": True,
            "action": "POSTED",
            "message_key": "asd-dot-001",
        }

    async def wake(target_ref, operation_key):
        events.append(("wake", target_ref, operation_key))
        return {"state": "DELIVERED"}

    coordinator = CanonicalReplyCoordinator(
        reply_writer=writer,
        attention_waker=wake,
    )
    result = asyncio.run(
        coordinator(
            "codex:binding-7",
            "Continue the bounded repair.",
            "Stop after the next result.",
            "op-001",
        )
    )
    assert events == [
        ("carrier", "codex:binding-7", "op-001"),
        ("wake", "codex:binding-7", "op-001"),
    ]
    assert result["reply_committed"] is True
    assert result["attention"] == {"state": "DELIVERED"}


def test_reply_coordinator_never_wakes_uncommitted_carrier():
    events = []

    def writer(*_args):
        events.append("carrier")
        return {"reply_committed": False, "state": "EFFECT_UNKNOWN"}

    def wake(*_args):
        events.append("wake")
        return {"state": "DELIVERED"}

    coordinator = CanonicalReplyCoordinator(
        reply_writer=writer,
        attention_waker=wake,
    )
    try:
        asyncio.run(
            coordinator(
                "codex:binding-7",
                "Continue.",
                "Stop after result.",
                "op-001",
            )
        )
    except BridgeError as exc:
        assert exc.code == "carrier_not_committed"
    else:
        raise AssertionError("uncommitted carrier must refuse")
    assert events == ["carrier"]


def test_attention_failure_does_not_resend_committed_carrier():
    events = []

    def writer(*_args):
        events.append("carrier")
        return {"reply_committed": True, "action": "POSTED"}

    def wake(*_args):
        events.append("wake")
        return {"state": "WAKE_UNAVAILABLE"}

    coordinator = CanonicalReplyCoordinator(
        reply_writer=writer,
        attention_waker=wake,
    )
    result = asyncio.run(
        coordinator(
            "claude:session-1",
            "Continue.",
            "Stop after result.",
            "op-claude-001",
        )
    )
    assert events == ["carrier", "wake"]
    assert result["carrier"]["action"] == "POSTED"
    assert result["attention"]["state"] == "WAKE_UNAVAILABLE"


def test_target_reader_keeps_provider_projections_separate():
    reader = CanonicalTargetReader(
        fabric_reader=lambda: [{"target_ref": "fabric:ATTEMPT-1"}],
        codex_reader=lambda: [{"target_ref": "codex:BIND-1"}],
        claude_reader=lambda: [{"target_ref": "claude:SESSION-1"}],
    )
    assert reader(None) == {
        "fabric_attempt": [{"target_ref": "fabric:ATTEMPT-1"}],
        "codex": [{"target_ref": "codex:BIND-1"}],
        "claude": [{"target_ref": "claude:SESSION-1"}],
    }


def test_summon_delegates_without_provider_preference():
    seen = []
    adapter = ExecutiveSummonAdapter(
        lambda args: seen.append(args) or {"accepted": True, "dispatched": False}
    )
    result = adapter(
        {
            "objective": "repair the failing test",
            "execution_profile": "bounded_code_change",
            "operation_key": "dot-summon-001",
        }
    )
    assert result == {"accepted": True, "dispatched": False}
    assert seen == [
        {
            "objective": "repair the failing test",
            "execution_profile": "bounded_code_change",
            "operation_key": "dot-summon-001",
        }
    ]
