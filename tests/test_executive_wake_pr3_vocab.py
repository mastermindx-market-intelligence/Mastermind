"""RED-first vocabulary contract for Wake PR3 native Claude continuation."""
from __future__ import annotations

from control_plane.session_targets import RuntimeBinding, SessionTarget
from control_plane.wake_transport import (
    requires_runtime_binding,
    transport_implemented,
    wake_transport_descriptor,
)


def test_claude_runtime_binding_is_a_supported_reasoning_surface():
    binding = RuntimeBinding(
        session_alias="EXECUTIVE-COO-A",
        binding_id="bind-claude1234",
        binding_generation=1,
        native_handle="opaque-provider-session",
        account_label="claude-subscription-a",
        reasoning_surface="claude",
    )

    assert binding.reasoning_surface == "claude"
    assert binding.native_handle == "opaque-provider-session"


def test_claude_code_session_is_known_binding_required_but_unimplemented():
    descriptor = wake_transport_descriptor("claude-code-session")

    assert descriptor.transport_id == "claude-code-session"
    assert requires_runtime_binding("claude-code-session") is True
    assert transport_implemented("claude-code-session") is False


def test_claude_session_target_can_be_declared_without_arming_delivery():
    target = SessionTarget(
        session_alias="EXECUTIVE-COO-A",
        target_seat="coo",
        reasoning_surface="claude",
        wake_transport="claude-code-session",
        allowed_transports=("claude-code-session",),
        workstream="executive",
        target_enabled=False,
    )

    assert target.target_seat == "coo"
    assert target.reasoning_surface == "claude"
    assert target.wake_transport == "claude-code-session"
    assert target.target_enabled is False
