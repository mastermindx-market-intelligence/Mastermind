from integrations.session_bridge.native_backends import (
    CanonicalTargetReader,
    ExactTargetRouter,
    ExecutiveSummonAdapter,
)
from integrations.session_bridge.schemas import BridgeError


def test_exact_target_router_never_falls_back():
    calls = []
    router = ExactTargetRouter(
        fabric_sender=lambda *args: calls.append(("fabric", args)),
        codex_sender=lambda *args: calls.append(("codex", args)),
        claude_sender=lambda *args: calls.append(("claude", args)),
    )
    router("codex:binding-7", "continue", "op-001")
    assert calls == [("codex", ("codex:binding-7", "continue", "op-001"))]


def test_unknown_target_kind_is_refused():
    router = ExactTargetRouter(
        fabric_sender=lambda *_: None,
        codex_sender=lambda *_: None,
        claude_sender=lambda *_: None,
    )
    try:
        router("newest-tab:any", "continue", "op-001")
    except BridgeError as exc:
        assert exc.code == "not_found"
    else:
        raise AssertionError("implicit/newest-tab routing must be refused")


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


def test_summon_delegates_to_executive_owner():
    seen = []
    adapter = ExecutiveSummonAdapter(lambda args: seen.append(args) or {"accepted": True, "dispatched": False})
    result = adapter(
        {
            "objective": "repair the failing test",
            "execution_profile": "bounded_code_change",
            "operation_key": "dot-summon-001",
            "preferred_surface": "claude",
        }
    )
    assert result == {"accepted": True, "dispatched": False}
    assert seen[0]["preferred_surface"] == "claude"
