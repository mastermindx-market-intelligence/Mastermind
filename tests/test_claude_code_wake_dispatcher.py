from __future__ import annotations

import asyncio
import dataclasses
import json
from pathlib import Path

import pytest

from control_plane.wake_dispatcher import TransportOutcome, WakeEffectUnknownError, WakeNudge
from integrations.executive_wake.claude_code import (
    CLAUDE_WAKE_DELIVERY_SENTINEL,
    CLAUDE_WAKE_INSTRUCTION,
    ClaudeCodeWakeDispatcher,
    ClaudeWakeCommandResult,
)

SESSION_ID = "550e8400-e29b-41d4-a716-446655440000"


def _wake(**overrides) -> WakeNudge:
    value = {
        "session_alias": "EXECUTIVE-COO-FABLE-A",
        "reasoning_surface": "claude",
        "wake_transport": "claude-code-session",
        "binding_id": "bind-claudewake01",
        "binding_generation": 4,
        "native_handle": SESSION_ID,
        "account_label": "must-never-enter-provider-prompt",
        "destination_digest": "d" * 16,
        "obligation_ids": ("WAKE-" + "a" * 32,),
        "attempt_command_ids": ("WAKE-" + "a" * 32 + ":delivery:1",),
        "nudge_id": "NUDGE-" + "b" * 32,
    }
    value.update(overrides)
    return WakeNudge(**value)


def _agent(**overrides):
    value = {
        "cwd": "/private/tmp/mmx-h1-canary",
        "kind": "background",
        "startedAt": 1790330000000,
        "id": "abc12345",
        "state": "stopped",
        "sessionId": SESSION_ID,
    }
    value.update(overrides)
    return value


def _discovery(rows=None, *, returncode=0):
    return ClaudeWakeCommandResult(
        returncode=returncode,
        stdout=json.dumps([_agent()] if rows is None else rows),
        stderr="",
    )


def _delivery(*, session_id=SESSION_ID, sentinel=CLAUDE_WAKE_DELIVERY_SENTINEL, returncode=0):
    payload = {
        "is_error": False,
        "session_id": session_id,
        "structured_output": {"wake_delivery": sentinel},
    }
    return ClaudeWakeCommandResult(returncode=returncode, stdout=json.dumps(payload), stderr="")


@dataclasses.dataclass
class _FakeRunner:
    results: list[object]
    calls: list[tuple[tuple[str, ...], Path, float]] = dataclasses.field(default_factory=list)

    async def run(self, *, argv, cwd, timeout_seconds):
        self.calls.append((tuple(argv), Path(cwd), timeout_seconds))
        if not self.results:
            raise AssertionError("unexpected runner call")
        value = self.results.pop(0)
        if isinstance(value, BaseException):
            raise value
        return value


def _dispatcher(runner):
    return ClaudeCodeWakeDispatcher(
        runner,
        claude_binary=Path("/opt/mastermind/bin/claude"),
        working_directory=Path("/private/tmp/mmx-h1-canary"),
    )


def _nudge(dispatcher, wake=None):
    return asyncio.run(dispatcher.nudge(wake or _wake()))


def test_exact_stopped_session_delivers_once_with_closed_cli_surface():
    runner = _FakeRunner([_discovery(), _delivery()])
    receipt = _nudge(_dispatcher(runner))

    assert receipt.outcome is TransportOutcome.DELIVERED
    assert receipt.reason_code == "delivered"
    assert dict(receipt.details) == {"nudge_id": _wake().nudge_id}
    assert len(runner.calls) == 2
    discovery_argv = runner.calls[0][0]
    delivery_argv = runner.calls[1][0]
    assert discovery_argv == ("/opt/mastermind/bin/claude", "agents", "--json", "--all")
    assert "--resume" in delivery_argv
    assert delivery_argv[delivery_argv.index("--resume") + 1] == SESSION_ID
    assert "--fork-session" not in delivery_argv
    assert "--session-id" not in delivery_argv
    assert "--restricted" in delivery_argv
    assert "--safe-mode" in delivery_argv
    assert delivery_argv[delivery_argv.index("--tools") + 1] == ""
    assert "mcp__*" in delivery_argv
    assert "--strict-mcp-config" in delivery_argv
    assert delivery_argv[delivery_argv.index("--mcp-config") + 1] == '{"mcpServers":{}}'
    prompt = delivery_argv[-1]
    assert CLAUDE_WAKE_INSTRUCTION in prompt
    assert _wake().nudge_id in prompt
    for opaque_id in _wake().obligation_ids + _wake().attempt_command_ids:
        assert opaque_id in prompt
    assert _wake().account_label not in prompt
    assert "objective" not in prompt.lower()
    assert _wake().destination_digest not in prompt
    assert _wake().binding_id not in prompt


@pytest.mark.parametrize(
    "overrides",
    [
        {"reasoning_surface": "codex"},
        {"wake_transport": "codex-app-server"},
        {"native_handle": None},
        {"native_handle": "not-a-uuid"},
        {"native_handle": SESSION_ID.upper()},
    ],
)
def test_invalid_bound_identity_refuses_before_any_runner_call(overrides):
    runner = _FakeRunner([])
    receipt = _nudge(_dispatcher(runner), _wake(**overrides))
    assert receipt.outcome is TransportOutcome.TARGET_UNAVAILABLE
    assert runner.calls == []


@pytest.mark.parametrize(
    "rows",
    [
        [],
        [_agent(sessionId="11111111-1111-4111-8111-111111111111")],
        [_agent(), _agent(id="duplicate")],
        [_agent(kind="interactive")],
        [_agent(state="working")],
        [_agent(state="blocked")],
        [_agent(pid=1234, status="idle")],
        [_agent(status="waiting")],
        [_agent(id="")],
    ],
)
def test_discovery_requires_one_exact_stopped_unattached_background_session(rows):
    runner = _FakeRunner([_discovery(rows)])
    receipt = _nudge(_dispatcher(runner))
    assert receipt.outcome is TransportOutcome.TARGET_UNAVAILABLE
    assert len(runner.calls) == 1


def test_discovery_malformed_or_failed_is_pre_submit_unavailable():
    for result in (
        ClaudeWakeCommandResult(returncode=0, stdout="not-json", stderr=""),
        ClaudeWakeCommandResult(returncode=1, stdout="[]", stderr="opaque error"),
        TimeoutError("read-only discovery timeout"),
    ):
        runner = _FakeRunner([result])
        receipt = _nudge(_dispatcher(runner))
        assert receipt.outcome is TransportOutcome.TARGET_UNAVAILABLE
        assert len(runner.calls) == 1


@pytest.mark.parametrize(
    "delivery",
    [
        TimeoutError("provider timeout"),
        _delivery(returncode=1),
        ClaudeWakeCommandResult(returncode=0, stdout="not-json", stderr=""),
        _delivery(session_id="11111111-1111-4111-8111-111111111111"),
        _delivery(sentinel="WRONG"),
    ],
)
def test_any_uncertainty_after_resume_begins_is_effect_unknown_without_retry(delivery):
    runner = _FakeRunner([_discovery(), delivery])
    with pytest.raises(WakeEffectUnknownError):
        _nudge(_dispatcher(runner))
    assert len(runner.calls) == 2


def test_delivery_receipt_never_persists_provider_session_or_raw_output():
    runner = _FakeRunner([_discovery(), _delivery()])
    receipt = _nudge(_dispatcher(runner))
    rendered = repr(receipt)
    assert SESSION_ID not in rendered
    assert "abc12345" not in rendered
    assert set(dict(receipt.details)) == {"nudge_id"}


def test_constructor_refuses_nonabsolute_binary_or_working_directory():
    runner = _FakeRunner([])
    with pytest.raises(ValueError, match="absolute"):
        ClaudeCodeWakeDispatcher(runner, claude_binary=Path("claude"), working_directory=Path("/tmp"))
    with pytest.raises(ValueError, match="absolute"):
        ClaudeCodeWakeDispatcher(runner, claude_binary=Path("/opt/claude"), working_directory=Path("relative"))
