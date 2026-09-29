from __future__ import annotations

import asyncio
import dataclasses
import json
import os
from pathlib import Path

import pytest

from control_plane.wake_dispatcher import (
    TransportOutcome,
    WakeEffectUnknownError,
    WakeNudge,
    WakePreSubmitError,
)
from integrations.executive_wake.claude_code import (
    CLAUDE_WAKE_AUTH_REFRESH_CONTENTION_TEXT,
    CLAUDE_WAKE_DELIVERY_SENTINEL,
    CLAUDE_WAKE_INSTRUCTION,
    CLAUDE_WAKE_PRE_SUBMIT_PREFIX,
    CLAUDE_WAKE_REFUSAL_CLASSES,
    ClaudeCodeWakeDispatcher,
    ClaudeWakeCommandResult,
)

SESSION_ID = "550e8400-e29b-41d4-a716-446655440000"
OTHER_SESSION_ID = "11111111-1111-4111-8111-111111111111"
FORBIDDEN_RECEIVER_FLAGS = ("--continue", "-c", "--fork-session", "--session-id", "--from-pr")


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
        stdout=json.dumps([] if rows is None else rows),
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
    """Scripted host runner.  A callable result runs a side effect then returns its value."""

    results: list[object]
    calls: list[tuple[tuple[str, ...], Path, float]] = dataclasses.field(default_factory=list)

    async def run(self, *, argv, cwd, timeout_seconds):
        self.calls.append((tuple(argv), Path(cwd), timeout_seconds))
        if not self.results:
            raise AssertionError("unexpected runner call")
        value = self.results.pop(0)
        if callable(value):
            value = value()
        if isinstance(value, BaseException):
            raise value
        return value


@dataclasses.dataclass(frozen=True)
class _Store:
    config_dir: Path
    transcript: Path
    receiver_cwd: Path


def _record(session_id: str = SESSION_ID, **fields):
    value = {"type": "user", "sessionId": session_id}
    value.update(fields)
    return json.dumps(value)


def _store(tmp_path: Path, *, session_id: str = SESSION_ID, lines=None, project: str = "-tmp-receiver") -> _Store:
    receiver_cwd = tmp_path / "receiver-cwd"
    receiver_cwd.mkdir(exist_ok=True)
    config_dir = tmp_path / "provider-home" / ".claude"
    project_dir = config_dir / "projects" / project
    project_dir.mkdir(parents=True, exist_ok=True)
    transcript = project_dir / f"{session_id}.jsonl"
    if lines is None:
        lines = [
            json.dumps({"type": "bridge-session", "sessionId": session_id}),
            _record(session_id, cwd=str(receiver_cwd)),
            _record(session_id, cwd=str(receiver_cwd), type="assistant"),
        ]
    transcript.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return _Store(config_dir=config_dir, transcript=transcript, receiver_cwd=receiver_cwd)


def _append_turn(store: _Store):
    def _effect():
        with store.transcript.open("a", encoding="utf-8") as handle:
            handle.write(_record(cwd=str(store.receiver_cwd), type="assistant") + "\n")
        return _delivery()

    return _effect


def _dispatcher(runner, store: _Store):
    return ClaudeCodeWakeDispatcher(
        runner,
        claude_binary=Path("/opt/mastermind/bin/claude"),
        claude_config_dir=store.config_dir,
        working_directory=Path("/private/tmp/mmx-h1-canary"),
    )


def _nudge(dispatcher, wake=None):
    return asyncio.run(dispatcher.nudge(wake or _wake()))


def _refused(dispatcher, wake=None) -> str:
    with pytest.raises(WakePreSubmitError) as info:
        _nudge(dispatcher, wake)
    assert info.value.outcome is TransportOutcome.TARGET_UNAVAILABLE
    assert info.value.reason_code == "target_unavailable"
    message = str(info.value)
    assert message.startswith(CLAUDE_WAKE_PRE_SUBMIT_PREFIX)
    refusal_class = message[len(CLAUDE_WAKE_PRE_SUBMIT_PREFIX) :]
    assert refusal_class in CLAUDE_WAKE_REFUSAL_CLASSES
    assert SESSION_ID not in message
    return refusal_class


# --- delivery ---------------------------------------------------------------


def test_exact_stored_session_delivers_once_with_closed_cli_surface(tmp_path):
    store = _store(tmp_path)
    runner = _FakeRunner([_discovery(), _append_turn(store)])
    receipt = _nudge(_dispatcher(runner, store))

    assert receipt.outcome is TransportOutcome.DELIVERED
    assert receipt.reason_code == "delivered"
    assert dict(receipt.details) == {"nudge_id": _wake().nudge_id}
    assert len(runner.calls) == 2
    discovery_argv, discovery_cwd, _ = runner.calls[0]
    delivery_argv, delivery_cwd, _ = runner.calls[1]
    assert discovery_argv == ("/opt/mastermind/bin/claude", "agents", "--json")
    assert discovery_cwd == Path("/private/tmp/mmx-h1-canary")
    assert delivery_cwd == store.receiver_cwd
    assert delivery_argv[:3] == ("/opt/mastermind/bin/claude", "--resume", SESSION_ID)
    for flag in FORBIDDEN_RECEIVER_FLAGS:
        assert flag not in delivery_argv
    assert "--restricted" in delivery_argv
    assert "--safe-mode" in delivery_argv
    assert delivery_argv[delivery_argv.index("--max-turns") + 1] == "1"
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
    assert str(store.config_dir) not in prompt
    assert str(store.receiver_cwd) not in prompt


def test_legacy_stopped_background_discovery_row_is_not_a_live_writer(tmp_path):
    store = _store(tmp_path)
    runner = _FakeRunner([_discovery([_agent()]), _append_turn(store)])
    receipt = _nudge(_dispatcher(runner, store))
    assert receipt.outcome is TransportOutcome.DELIVERED
    assert len(runner.calls) == 2


def test_delivery_receipt_never_persists_provider_session_paths_or_raw_output(tmp_path):
    store = _store(tmp_path)
    runner = _FakeRunner([_discovery([_agent()]), _append_turn(store)])
    receipt = _nudge(_dispatcher(runner, store))
    rendered = repr(receipt)
    assert SESSION_ID not in rendered
    assert "abc12345" not in rendered
    assert str(store.config_dir) not in rendered
    assert str(store.receiver_cwd) not in rendered
    assert set(dict(receipt.details)) == {"nudge_id"}


# --- identity: the exact handle is the only inclusion evidence ------------------


@pytest.mark.parametrize(
    "overrides",
    [
        {"reasoning_surface": "codex"},
        {"wake_transport": "codex-app-server"},
        {"native_handle": None},
        {"native_handle": ""},
        {"native_handle": "not-a-uuid"},
        {"native_handle": SESSION_ID.upper()},
    ],
)
def test_invalid_bound_identity_refuses_before_any_store_or_runner_access(tmp_path, overrides):
    store = _store(tmp_path)
    runner = _FakeRunner([])
    assert _refused(_dispatcher(runner, store), _wake(**overrides)) == "identity_unbound"
    assert runner.calls == []


# --- inclusion: transcript store resolution ---------------------------------


def test_store_root_absent_refuses_before_discovery(tmp_path):
    store = _store(tmp_path)
    missing = ClaudeCodeWakeDispatcher(
        _FakeRunner([]),
        claude_binary=Path("/opt/mastermind/bin/claude"),
        claude_config_dir=tmp_path / "no-such-home" / ".claude",
        working_directory=Path("/private/tmp/mmx-h1-canary"),
    )
    assert _refused(missing) == "store_root_absent"
    assert store.transcript.exists()


def test_handle_absent_from_store_refuses_without_newest_or_sibling_fallback(tmp_path):
    store = _store(tmp_path, session_id=OTHER_SESSION_ID)
    runner = _FakeRunner([])
    assert _refused(_dispatcher(runner, store)) == "store_absent"
    assert runner.calls == []


def test_handle_present_in_two_project_directories_is_ambiguous(tmp_path):
    store = _store(tmp_path)
    _store(tmp_path, project="-tmp-receiver-copy")
    runner = _FakeRunner([])
    assert _refused(_dispatcher(runner, store)) == "store_ambiguous"
    assert runner.calls == []


def test_symlinked_transcript_is_refused_not_followed(tmp_path):
    store = _store(tmp_path, session_id=OTHER_SESSION_ID)
    link = store.transcript.parent / f"{SESSION_ID}.jsonl"
    os.symlink(store.transcript, link)
    runner = _FakeRunner([])
    assert _refused(_dispatcher(runner, store)) == "store_symlink"
    assert runner.calls == []


def test_empty_transcript_is_refused(tmp_path):
    store = _store(tmp_path, lines=[])
    store.transcript.write_bytes(b"")
    assert _refused(_dispatcher(_FakeRunner([]), store)) == "store_empty"


def test_transcript_carrying_a_foreign_session_identity_is_refused(tmp_path):
    receiver_cwd = tmp_path / "receiver-cwd"
    store = _store(
        tmp_path,
        lines=[_record(cwd=str(receiver_cwd)), _record(OTHER_SESSION_ID, cwd=str(receiver_cwd))],
    )
    assert _refused(_dispatcher(_FakeRunner([]), store)) == "identity_mismatch"


@pytest.mark.parametrize(
    "lines",
    [
        [json.dumps({"type": "bridge-session", "sessionId": SESSION_ID})],
        [_record(cwd="relative/path")],
        [_record(cwd="/definitely/not/a/real/directory/for/wake")],
        ["not json", _record(cwd="")],
    ],
)
def test_unresolvable_receiver_cwd_refuses_before_discovery(tmp_path, lines):
    store = _store(tmp_path, lines=lines)
    runner = _FakeRunner([])
    assert _refused(_dispatcher(runner, store)) == "cwd_unresolved"
    assert runner.calls == []


# --- exclusion: live writers and unreadable discovery ------------------------


@pytest.mark.parametrize(
    "rows",
    [
        [_agent(kind="interactive", pid=4242)],
        [_agent(kind="interactive", pid=4242, status="busy")],
        [_agent(kind="interactive", pid=4242, status="idle")],
        [_agent(state="working")],
        [_agent(state="blocked")],
        [_agent(pid=1234, status="idle")],
        [_agent(status="waiting")],
        [_agent(sessionId=OTHER_SESSION_ID, kind="interactive", pid=1), _agent(kind="interactive", pid=2)],
    ],
)
def test_live_writer_for_the_exact_handle_refuses_delivery(tmp_path, rows):
    store = _store(tmp_path)
    runner = _FakeRunner([_discovery(rows)])
    assert _refused(_dispatcher(runner, store)) == "live_writer"
    assert len(runner.calls) == 1


def test_live_rows_for_other_sessions_do_not_block_the_exact_handle(tmp_path):
    store = _store(tmp_path)
    rows = [_agent(sessionId=OTHER_SESSION_ID, kind="interactive", pid=1, status="busy")]
    runner = _FakeRunner([_discovery(rows), _append_turn(store)])
    assert _nudge(_dispatcher(runner, store)).outcome is TransportOutcome.DELIVERED


def test_discovery_malformed_or_failed_refuses_because_absence_is_unproven(tmp_path):
    for result in (
        ClaudeWakeCommandResult(returncode=0, stdout="not-json", stderr=""),
        ClaudeWakeCommandResult(returncode=0, stdout='{"rows": []}', stderr=""),
        ClaudeWakeCommandResult(returncode=1, stdout="[]", stderr="opaque error"),
        TimeoutError("read-only discovery timeout"),
    ):
        store = _store(tmp_path)
        runner = _FakeRunner([result])
        assert _refused(_dispatcher(runner, store)) == "discovery_unavailable"
        assert len(runner.calls) == 1


# --- deterministic fail-closed classification --------------------------------


def _unchanged(store: _Store) -> str:
    return store.transcript.read_text(encoding="utf-8")


def test_auth_refresh_contention_with_unchanged_transcript_is_typed_pre_effect_without_retry(tmp_path):
    store = _store(tmp_path)
    before = _unchanged(store)
    contention = ClaudeWakeCommandResult(
        returncode=1,
        stdout=CLAUDE_WAKE_AUTH_REFRESH_CONTENTION_TEXT
        + ": another Claude Code process is refreshing it or exited mid-refresh.",
        stderr="",
    )
    runner = _FakeRunner([_discovery(), contention])
    assert _refused(_dispatcher(runner, store)) == "auth_refresh_contention"
    assert len(runner.calls) == 2
    assert _unchanged(store) == before


def test_generic_pre_effect_failure_with_unchanged_transcript_is_typed_refusal(tmp_path):
    store = _store(tmp_path)
    for failure in (
        _delivery(returncode=1),
        ClaudeWakeCommandResult(returncode=2, stdout="", stderr="No conversation found with session ID"),
        ClaudeWakeCommandResult(returncode=0, stdout="not-json", stderr=""),
    ):
        runner = _FakeRunner([_discovery(), failure])
        assert _refused(_dispatcher(runner, store)) == "pre_effect_failure"
        assert len(runner.calls) == 2


@pytest.mark.parametrize(
    "failure",
    [
        _delivery(returncode=1),
        ClaudeWakeCommandResult(returncode=0, stdout="not-json", stderr=""),
        _delivery(session_id=OTHER_SESSION_ID),
        _delivery(sentinel="WRONG"),
    ],
)
def test_failure_after_the_transcript_changed_is_effect_unknown_without_retry(tmp_path, failure):
    store = _store(tmp_path)

    def _grow_then_fail():
        with store.transcript.open("a", encoding="utf-8") as handle:
            handle.write(_record(cwd=str(store.receiver_cwd)) + "\n")
        return failure

    runner = _FakeRunner([_discovery(), _grow_then_fail])
    with pytest.raises(WakeEffectUnknownError):
        _nudge(_dispatcher(runner, store))
    assert len(runner.calls) == 2


def test_runner_exception_during_resume_is_effect_unknown_even_if_transcript_unchanged(tmp_path):
    store = _store(tmp_path)
    runner = _FakeRunner([_discovery(), TimeoutError("provider timeout")])
    with pytest.raises(WakeEffectUnknownError):
        _nudge(_dispatcher(runner, store))
    assert len(runner.calls) == 2


def test_claimed_delivery_without_transcript_growth_is_effect_unknown(tmp_path):
    store = _store(tmp_path)
    runner = _FakeRunner([_discovery(), _delivery()])
    with pytest.raises(WakeEffectUnknownError):
        _nudge(_dispatcher(runner, store))


def test_claimed_delivery_that_created_a_sibling_transcript_is_effect_unknown(tmp_path):
    store = _store(tmp_path)

    def _fork():
        sibling = store.transcript.parent / f"{OTHER_SESSION_ID}.jsonl"
        sibling.write_text(_record(OTHER_SESSION_ID, cwd=str(store.receiver_cwd)) + "\n", encoding="utf-8")
        with store.transcript.open("a", encoding="utf-8") as handle:
            handle.write(_record(cwd=str(store.receiver_cwd)) + "\n")
        return _delivery()

    runner = _FakeRunner([_discovery(), _fork])
    with pytest.raises(WakeEffectUnknownError):
        _nudge(_dispatcher(runner, store))


def test_transcript_removed_during_resume_is_effect_unknown(tmp_path):
    store = _store(tmp_path)

    def _vanish():
        store.transcript.unlink()
        return _delivery()

    runner = _FakeRunner([_discovery(), _vanish])
    with pytest.raises(WakeEffectUnknownError):
        _nudge(_dispatcher(runner, store))


# --- constructor ---------------------------------------------------------------


def test_constructor_refuses_nonabsolute_binary_config_dir_or_working_directory(tmp_path):
    runner = _FakeRunner([])
    with pytest.raises(ValueError, match="absolute"):
        ClaudeCodeWakeDispatcher(
            runner, claude_binary=Path("claude"), claude_config_dir=tmp_path, working_directory=Path("/tmp")
        )
    with pytest.raises(ValueError, match="absolute"):
        ClaudeCodeWakeDispatcher(
            runner, claude_binary=Path("/opt/claude"), claude_config_dir=Path("relative"), working_directory=Path("/tmp")
        )
    with pytest.raises(ValueError, match="absolute"):
        ClaudeCodeWakeDispatcher(
            runner, claude_binary=Path("/opt/claude"), claude_config_dir=tmp_path, working_directory=Path("relative")
        )


def test_refusal_vocabulary_is_closed_and_never_names_a_session():
    assert CLAUDE_WAKE_PRE_SUBMIT_PREFIX.endswith(":")
    for refusal_class in CLAUDE_WAKE_REFUSAL_CLASSES:
        assert refusal_class == refusal_class.lower()
        assert "-" not in refusal_class
