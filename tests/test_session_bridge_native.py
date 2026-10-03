import asyncio

import pytest

from integrations.session_bridge.native_backends import (
    CanonicalReplyCoordinator,
    CanonicalTargetReader,
    ExactTargetRouter,
    ExecutiveSummonAdapter,
    ExecutiveSummonBinding,
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
    from integrations.session_bridge.native_wire import AttentionReference
    assert events == [
        ("carrier", "codex:binding-7", "op-001"),
        (
            "wake",
            "codex:binding-7",
            AttentionReference(operation_key="op-001", message_key="asd-dot-001"),
        ),
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
        return {
            "reply_committed": True,
            "action": "POSTED",
            "message_key": "asd-claude-attention-001",
        }

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


class _SummonResolver:
    def __init__(self, binding):
        self.binding = binding
        self.calls = []

    def resolve(self, *, operation_key, execution_profile):
        self.calls.append((operation_key, execution_profile))
        return self.binding


def test_summon_uses_trusted_host_binding_without_provider_preference():
    seen = []
    resolver = _SummonResolver(ExecutiveSummonBinding(
        department="executive-infrastructure",
        priority=7,
        workstream="WS:DOT-SESSION-BRIDGE",
        allowed_write_paths=("integrations/session_bridge", "tests"),
        validation={"pytest_targets": ["tests/test_session_bridge_native.py"], "git_diff_check": True},
        attempt_limit=2,
    ))
    adapter = ExecutiveSummonAdapter(
        lambda args: seen.append(args) or {"accepted": True, "dispatched": False},
        binding_resolver=resolver,
    )
    result = adapter({
        "objective": "repair the failing test",
        "execution_profile": "bounded_code_change",
        "operation_key": "dot-summon-001",
    })
    assert result == {"accepted": True, "dispatched": False}
    assert resolver.calls == [("dot-summon-001", "bounded_code_change")]
    assert seen == [{
        "operation_key": "dot-summon-001",
        "objective": "repair the failing test",
        "department": "executive-infrastructure",
        "priority": 7,
        "execution_profile": "bounded_code_change",
        "attempt_limit": 2,
        "workstream": "WS:DOT-SESSION-BRIDGE",
        "allowed_write_paths": ["integrations/session_bridge", "tests"],
        "validation": {"pytest_targets": ["tests/test_session_bridge_native.py"], "git_diff_check": True},
    }]


def test_research_summon_refuses_host_write_scope():
    resolver = _SummonResolver(ExecutiveSummonBinding(
        department="research",
        allowed_write_paths=("integrations/session_bridge",),
    ))
    adapter = ExecutiveSummonAdapter(lambda _args: None, binding_resolver=resolver)
    try:
        adapter({"objective": "inspect", "execution_profile": "research_only", "operation_key": "dot-summon-002"})
    except BridgeError as exc:
        assert exc.code == "binding_unavailable"
    else:
        raise AssertionError("research summon must refuse trusted write scope")


def test_reply_coordinator_wake_uses_exact_committed_message_reference():
    from integrations.session_bridge.native_wire import AttentionReference

    seen = []

    def writer(*_args):
        return {
            "reply_committed": True,
            "action": "POSTED",
            "message_key": "asd-canonical-message-001",
        }

    async def wake(target_ref, reference):
        seen.append((target_ref, reference))
        return {"state": "ATTENTION_ACCEPTED"}

    sender = CanonicalReplyCoordinator(reply_writer=writer, attention_waker=wake)
    result = asyncio.run(sender(
        "claude:target-001",
        "Continue.",
        "Stop after result.",
        "canonical-ref-op-001",
    ))
    assert seen == [(
        "claude:target-001",
        AttentionReference(
            operation_key="canonical-ref-op-001",
            message_key="asd-canonical-message-001",
        ),
    )]
    assert result["reply_committed"] is True


def test_reply_coordinator_missing_committed_message_key_is_effect_unknown_without_wake():
    calls = []

    def writer(*_args):
        calls.append("write")
        return {"reply_committed": True, "action": "POSTED"}

    def wake(*_args):
        calls.append("wake")
        return {"state": "ATTENTION_ACCEPTED"}

    sender = CanonicalReplyCoordinator(reply_writer=writer, attention_waker=wake)
    with pytest.raises(BridgeError) as caught:
        asyncio.run(sender(
            "claude:target-001",
            "Continue.",
            "Stop after result.",
            "missing-reference-op-001",
        ))
    assert caught.value.code == "effect_unknown"
    assert calls == ["write"]


def test_duplicate_carrier_reconciles_attention_without_rewaking_native_target():
    events = []

    def writer(*_args):
        events.append("carrier")
        return {
            "reply_committed": True,
            "action": "DUPLICATE",
            "message_key": "asd-canonical-message-duplicate-001",
        }

    async def wake(target_ref, reference):
        events.append(("wake", target_ref, reference))
        return {"state": "ATTENTION_ACCEPTED"}

    async def reconcile(target_ref, reference):
        events.append(("reconcile", target_ref, reference))
        return {"state": "ATTENTION_ACCEPTED", "reconciled": True}

    sender = CanonicalReplyCoordinator(
        reply_writer=writer,
        attention_waker=wake,
        attention_reconciler=reconcile,
    )
    result = asyncio.run(
        sender(
            "claude:target-001",
            "Continue.",
            "Stop after result.",
            "duplicate-attention-op-001",
        )
    )

    from integrations.session_bridge.native_wire import AttentionReference

    expected = AttentionReference(
        operation_key="duplicate-attention-op-001",
        message_key="asd-canonical-message-duplicate-001",
    )
    assert events == ["carrier", ("reconcile", "claude:target-001", expected)]
    assert result["carrier"]["action"] == "DUPLICATE"
    assert result["attention"] == {"state": "ATTENTION_ACCEPTED", "reconciled": True}


def test_exact_target_router_accepts_public_fabric_attempt_prefix():
    calls = []
    router = ExactTargetRouter(
        fabric_reply=lambda *args: calls.append(("fabric", args)),
        codex_reply=lambda *_: None,
        claude_reply=lambda *_: None,
    )
    router(
        "fabric_attempt:exact-1",
        "Continue.",
        "Stop after result.",
        "fabric-route-001",
    )
    assert calls == [(
        "fabric",
        (
            "fabric_attempt:exact-1",
            "Continue.",
            "Stop after result.",
            "fabric-route-001",
        ),
    )]
