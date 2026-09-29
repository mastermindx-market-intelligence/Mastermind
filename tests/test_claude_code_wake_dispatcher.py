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
    authenticate_transport_receipt,
    normalize_transport_completion,
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
NUDGE_ID = "NUDGE-" + "b" * 32
FORBIDDEN_RECEIVER_FLAGS = ("--continue", "-c", "--fork-session", "--session-id", "--from-pr", "--model")


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
        "nudge_id": NUDGE_ID,
    }
    value.update(overrides)
    return WakeNudge(**value)


def _agent(**overrides):
    """Shape captured from a real `claude agents --json` row on 2026-09-29 (live interactive writer)."""

    value = {
        "pid": 40758,
        "cwd": "/private/tmp/mmx-h1-canary",
        "kind": "interactive",
        "startedAt": 1790672313279,
        "sessionId": SESSION_ID,
        "name": "mmx-h1-canary-6a",
    }
    value.update(overrides)
    return value


def _discovery(rows=None, *, returncode=0):
    return ClaudeWakeCommandResult(
        returncode=returncode,
        stdout=json.dumps([] if rows is None else rows),
        stderr="",
    )


def _delivery(*, session_id=SESSION_ID, sentinel=CLAUDE_WAKE_DELIVERY_SENTINEL, returncode=0, is_error=False):
    payload = {
        "is_error": is_error,
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
    root: Path


def _record(session_id: str = SESSION_ID, **fields):
    value = {"type": "user", "sessionId": session_id}
    value.update(fields)
    return json.dumps(value)


def _store(tmp_path: Path, *, session_id: str = SESSION_ID, lines=None, project: str = "-tmp-receiver") -> _Store:
    root = tmp_path / "receivers"
    receiver_cwd = root / "receiver-cwd"
    receiver_cwd.mkdir(parents=True, exist_ok=True)
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
    return _Store(config_dir=config_dir, transcript=transcript, receiver_cwd=receiver_cwd, root=root)


def _append(store: _Store, *lines: str) -> None:
    with store.transcript.open("a", encoding="utf-8") as handle:
        for line in lines:
            handle.write(line + "\n")


def _prompt_for(wake: WakeNudge | None = None) -> str:
    wake = wake or _wake()
    ids = (wake.nudge_id,) + tuple(wake.obligation_ids) + tuple(wake.attempt_command_ids)
    return CLAUDE_WAKE_INSTRUCTION + "\nOpaque Wake identities:\n" + "\n".join(ids)


def _prompt_record(content, **fields) -> str:
    """Shape the installed CLI (2.1.275) records for a `-p --resume` prompt: `message.content` is the prompt string."""

    value = {"cwd": "/tmp/receiver", "promptId": "prompt-1", "promptSource": "cli", "message": {"role": "user", "content": content}}
    value.update(fields)
    return _record(**value)


def _genuine(**fields) -> str:
    value = {"type": "assistant", "message": {"role": "assistant", "model": "claude-opus-5", "content": [{"type": "text", "text": "ack"}]}}
    value.update(fields)
    return _record(**value)


def _marker_turn(store: _Store, *, wake: WakeNudge | None = None, reply: bool = True) -> None:
    _append(store, _prompt_record(_prompt_for(wake), cwd=str(store.receiver_cwd)))
    if reply:
        _append(store, _genuine(cwd=str(store.receiver_cwd)))


def _synthetic_refusal(store: _Store) -> None:
    """Shape observed on the real host 2026-09-29: provider safeguards refused the resumed turn."""

    _append(
        store,
        _record(cwd=str(store.receiver_cwd), type="assistant", isApiErrorMessage=True,
                message={"role": "assistant", "model": "<synthetic>", "stop_reason": "refusal",
                         "content": [{"type": "text", "text": "API Error: safeguards flagged this message"}]}),
    )


def _append_turn(store: _Store, result=None):
    def _effect():
        _marker_turn(store)
        return _delivery() if result is None else result

    return _effect


def _dispatcher(runner, store: _Store, **overrides):
    kwargs = {
        "claude_binary": Path("/opt/mastermind/bin/claude"),
        "claude_config_dir": store.config_dir,
        "working_directory": Path("/private/tmp/mmx-h1-canary"),
        "receiver_cwd_roots": (store.root,),
        "settle_seconds": 0.0,
    }
    kwargs.update(overrides)
    return ClaudeCodeWakeDispatcher(runner, **kwargs)


def _nudge(dispatcher, wake=None):
    return asyncio.run(dispatcher.nudge(wake or _wake()))


def _refused(runner, store: _Store, wake=None, **overrides) -> str:
    seen: list[str] = []
    dispatcher = _dispatcher(runner, store, refusal_observer=seen.append, **overrides)
    receipt = _nudge(dispatcher, wake)
    assert receipt.outcome is TransportOutcome.TARGET_UNAVAILABLE
    assert receipt.reason_code == "target_unavailable"
    assert dict(receipt.details) == {"nudge_id": (wake or _wake()).nudge_id}
    assert SESSION_ID not in repr(receipt)
    assert len(seen) == 1 and seen[0] in CLAUDE_WAKE_REFUSAL_CLASSES
    return seen[0]


# --- delivery ---------------------------------------------------------------


def test_exact_stored_session_delivers_once_with_closed_cli_surface(tmp_path):
    store = _store(tmp_path)
    runner = _FakeRunner([_discovery(), _append_turn(store)])
    receipt = _nudge(_dispatcher(runner, store))

    assert receipt.outcome is TransportOutcome.DELIVERED
    assert receipt.reason_code == "delivered"
    assert dict(receipt.details) == {"nudge_id": NUDGE_ID}
    assert len(runner.calls) == 2
    discovery_argv, discovery_cwd, _ = runner.calls[0]
    delivery_argv, delivery_cwd, _ = runner.calls[1]
    assert discovery_argv == ("/opt/mastermind/bin/claude", "agents", "--json")
    assert discovery_cwd == Path("/private/tmp/mmx-h1-canary")
    assert delivery_cwd == store.receiver_cwd.resolve()
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
    assert NUDGE_ID in prompt
    for opaque_id in _wake().obligation_ids + _wake().attempt_command_ids:
        assert opaque_id in prompt
    assert _wake().account_label not in prompt
    assert _wake().destination_digest not in prompt
    assert _wake().binding_id not in prompt
    assert SESSION_ID not in prompt
    assert str(store.config_dir) not in prompt
    assert str(store.receiver_cwd) not in prompt


def test_delivery_receipt_authenticates_with_the_fabric_and_never_persists_provider_state(tmp_path):
    store = _store(tmp_path)
    runner = _FakeRunner([_discovery([_agent(sessionId=OTHER_SESSION_ID)]), _append_turn(store)])
    receipt = _nudge(_dispatcher(runner, store))
    transport, projection = normalize_transport_completion(receipt)
    assert projection is None
    authenticated = authenticate_transport_receipt(transport, expected_nudge_id=NUDGE_ID)
    assert authenticated.outcome is TransportOutcome.DELIVERED
    rendered = repr(receipt)
    assert SESSION_ID not in rendered
    assert "40758" not in rendered
    assert str(store.config_dir) not in rendered
    assert str(store.receiver_cwd) not in rendered
    assert set(dict(receipt.details)) == {"nudge_id"}


def test_resume_launches_from_the_most_recent_recorded_cwd(tmp_path):
    store = _store(tmp_path)
    later = store.root / "later-cwd"
    later.mkdir()
    _append(store, _record(cwd=str(later)), _record(cwd=str(later), type="assistant"))
    runner = _FakeRunner([_discovery(), _append_turn(store)])
    assert _nudge(_dispatcher(runner, store)).outcome is TransportOutcome.DELIVERED
    assert runner.calls[1][1] == later.resolve()


def test_resume_launches_from_the_resolved_receiver_cwd_not_the_recorded_alias(tmp_path):
    store = _store(tmp_path)
    real = store.root / "real-cwd"
    real.mkdir()
    alias = store.root / "alias-cwd"
    os.symlink(real, alias)
    _append(store, _record(cwd=str(alias)))
    runner = _FakeRunner([_discovery(), _append_turn(store)])
    assert _nudge(_dispatcher(runner, store)).outcome is TransportOutcome.DELIVERED
    assert runner.calls[1][1] == real.resolve()
    assert not runner.calls[1][1].is_symlink()


@pytest.mark.parametrize(
    "growth",
    [
        lambda store: _append(store, _record(cwd=str(store.receiver_cwd), type="progress")),
        lambda store: _append(store, _prompt_record("unrelated human prompt", cwd=str(store.receiver_cwd)), _genuine()),
        lambda store: _marker_turn(store, reply=False),
        lambda store: (_marker_turn(store, reply=False), _synthetic_refusal(store)),
        lambda store: _marker_turn(store, wake=_wake(nudge_id="NUDGE-" + "c" * 32)),
        lambda store: _append(store, _record(cwd=str(store.receiver_cwd), toolUseResult={"x": 1},
                                             message={"role": "user", "content": [{"type": "tool_result", "content": _prompt_for()}]}), _genuine()),
    ],
)
def test_claimed_delivery_whose_transcript_growth_is_not_this_markers_turn_is_effect_unknown(tmp_path, growth):
    store = _store(tmp_path)

    def _effect():
        growth(store)
        return _delivery()

    runner = _FakeRunner([_discovery(), _effect])
    with pytest.raises(WakeEffectUnknownError):
        _nudge(_dispatcher(runner, store))
    assert len(runner.calls) == 2


# --- identity: the exact handle is the only inclusion evidence ------------------


def test_non_wake_nudge_objects_are_unbound_on_both_entry_points(tmp_path):
    store = _store(tmp_path)
    seen: list[str] = []
    dispatcher = _dispatcher(_FakeRunner([]), store, refusal_observer=seen.append)
    receipt = asyncio.run(dispatcher.nudge(object()))
    assert receipt.outcome is TransportOutcome.TARGET_UNAVAILABLE
    assert seen == ["identity_unbound"]
    with pytest.raises(WakeEffectUnknownError):
        asyncio.run(dispatcher.reconcile(object()))


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
    assert _refused(runner, store, _wake(**overrides)) == "identity_unbound"
    assert runner.calls == []


# --- inclusion: transcript store resolution ---------------------------------


def test_store_root_absent_refuses_before_discovery(tmp_path):
    store = _store(tmp_path)
    runner = _FakeRunner([])
    assert _refused(runner, store, claude_config_dir=tmp_path / "no-such-home" / ".claude") == "store_root_absent"
    assert runner.calls == []


def test_symlinked_store_root_is_refused(tmp_path):
    store = _store(tmp_path)
    linked_home = tmp_path / "linked-home"
    linked_home.mkdir()
    os.symlink(store.config_dir / "projects", linked_home / "projects")
    assert _refused(_FakeRunner([]), store, claude_config_dir=linked_home) == "store_symlink"


def test_handle_absent_from_store_refuses_without_newest_or_sibling_fallback(tmp_path):
    store = _store(tmp_path, session_id=OTHER_SESSION_ID)
    runner = _FakeRunner([])
    assert _refused(runner, store) == "store_absent"
    assert runner.calls == []


def test_handle_present_in_two_project_directories_is_ambiguous(tmp_path):
    store = _store(tmp_path)
    _store(tmp_path, project="-tmp-receiver-copy")
    runner = _FakeRunner([])
    assert _refused(runner, store) == "store_ambiguous"
    assert runner.calls == []


def test_symlinked_transcript_is_refused_not_followed(tmp_path):
    store = _store(tmp_path, session_id=OTHER_SESSION_ID)
    os.symlink(store.transcript, store.transcript.parent / f"{SESSION_ID}.jsonl")
    runner = _FakeRunner([])
    assert _refused(runner, store) == "store_symlink"
    assert runner.calls == []


def test_unreadable_project_directory_is_a_typed_store_refusal(tmp_path):
    if os.geteuid() == 0:
        pytest.skip("permission bits are not enforced for root")
    store = _store(tmp_path)
    store.transcript.parent.chmod(0o000)
    try:
        assert _refused(_FakeRunner([]), store) == "store_unreadable"
    finally:
        store.transcript.parent.chmod(0o700)


def test_empty_transcript_is_refused(tmp_path):
    store = _store(tmp_path, lines=[])
    store.transcript.write_bytes(b"")
    assert _refused(_FakeRunner([]), store) == "store_empty"


def test_oversized_transcript_is_refused_before_any_read(tmp_path, monkeypatch):
    import integrations.executive_wake.claude_code as module

    store = _store(tmp_path)
    monkeypatch.setattr(module, "_STORE_FILE_MAX_BYTES", store.transcript.stat().st_size - 1)
    runner = _FakeRunner([])
    assert _refused(runner, store) == "store_oversized"
    assert runner.calls == []


def test_foreign_session_identity_anywhere_in_the_transcript_is_refused(tmp_path):
    store = _store(tmp_path)
    padding = _record(cwd=str(store.receiver_cwd), filler="x" * 4096)
    _append(store, *([padding] * 300), _record(OTHER_SESSION_ID, cwd=str(store.receiver_cwd)))
    assert store.transcript.stat().st_size > 1024 * 1024
    assert _refused(_FakeRunner([]), store) == "identity_mismatch"


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
    assert _refused(runner, store) == "cwd_unresolved"
    assert runner.calls == []


def test_receiver_cwd_outside_allowed_roots_refuses_before_discovery(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    store = _store(tmp_path, lines=[_record(cwd=str(outside))])
    runner = _FakeRunner([])
    assert _refused(runner, store) == "cwd_outside_roots"
    assert runner.calls == []


def test_receiver_cwd_escaping_roots_via_symlink_is_refused(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    store = _store(tmp_path)
    escape = store.root / "escape"
    os.symlink(outside, escape)
    _append(store, _record(cwd=str(escape)))
    assert _refused(_FakeRunner([]), store) == "cwd_outside_roots"


# --- exclusion: any listed writer, or an unrecognised listing, refuses ---------


@pytest.mark.parametrize(
    "rows",
    [
        [_agent()],
        [_agent(kind="background", pid=None, state="stopped", status=None)],
        [_agent(kind="background", state="done")],
        [_agent(sessionId=OTHER_SESSION_ID), _agent()],
    ],
)
def test_any_listed_writer_for_the_exact_handle_refuses_delivery(tmp_path, rows):
    store = _store(tmp_path)
    runner = _FakeRunner([_discovery(rows)])
    assert _refused(runner, store) == "live_writer"
    assert len(runner.calls) == 1


def test_listed_writers_for_other_sessions_do_not_block_the_exact_handle(tmp_path):
    store = _store(tmp_path)
    rows = [_agent(sessionId=OTHER_SESSION_ID), _agent(sessionId=OTHER_SESSION_ID, pid=99)]
    runner = _FakeRunner([_discovery(rows), _append_turn(store)])
    assert _nudge(_dispatcher(runner, store)).outcome is TransportOutcome.DELIVERED


@pytest.mark.parametrize(
    "result",
    [
        ClaudeWakeCommandResult(returncode=0, stdout="not-json", stderr=""),
        ClaudeWakeCommandResult(returncode=0, stdout='{"rows": []}', stderr=""),
        ClaudeWakeCommandResult(returncode=1, stdout="[]", stderr="opaque error"),
        ClaudeWakeCommandResult(returncode=0, stdout=json.dumps([{"session_id": SESSION_ID}]), stderr=""),
        ClaudeWakeCommandResult(returncode=0, stdout=json.dumps([{"id": "abc", "kind": "interactive"}]), stderr=""),
        ClaudeWakeCommandResult(returncode=0, stdout=json.dumps([_agent(sessionId=OTHER_SESSION_ID), "row"]), stderr=""),
        TimeoutError("read-only discovery timeout"),
    ],
)
def test_discovery_malformed_failed_or_unrecognised_refuses_because_absence_is_unproven(tmp_path, result):
    store = _store(tmp_path)
    runner = _FakeRunner([result])
    assert _refused(runner, store) == "discovery_unavailable"
    assert len(runner.calls) == 1


# --- deterministic fail-closed classification --------------------------------


def _contention(returncode=1):
    return ClaudeWakeCommandResult(
        returncode=returncode,
        stdout=CLAUDE_WAKE_AUTH_REFRESH_CONTENTION_TEXT
        + ": another Claude Code process is refreshing it or exited mid-refresh.",
        stderr="",
    )


def test_auth_refresh_contention_with_unchanged_store_is_typed_pre_effect_without_retry(tmp_path):
    store = _store(tmp_path)
    before = store.transcript.read_bytes()
    runner = _FakeRunner([_discovery(), _contention()])
    assert _refused(runner, store) == "auth_refresh_contention"
    assert len(runner.calls) == 2
    assert store.transcript.read_bytes() == before


@pytest.mark.parametrize(
    "failure",
    [
        _delivery(returncode=1),
        ClaudeWakeCommandResult(returncode=2, stdout="", stderr="No conversation found with session ID"),
        ClaudeWakeCommandResult(returncode=1, stdout="not-json", stderr=""),
        _delivery(returncode=1, is_error=True),
    ],
)
def test_nonzero_exit_with_unchanged_store_is_typed_pre_effect_refusal(tmp_path, failure):
    store = _store(tmp_path)
    runner = _FakeRunner([_discovery(), failure])
    assert _refused(runner, store) == "pre_effect_failure"
    assert len(runner.calls) == 2


@pytest.mark.parametrize(
    "result",
    [
        ClaudeWakeCommandResult(returncode=0, stdout="not-json", stderr=""),
        _delivery(session_id=OTHER_SESSION_ID),
        _delivery(sentinel="WRONG"),
        _delivery(is_error=True),
        _delivery(returncode=1, session_id=OTHER_SESSION_ID),
        _contention(returncode=0),
    ],
)
def test_zero_exit_or_foreign_session_envelope_is_never_pre_effect_even_when_store_unchanged(tmp_path, result):
    store = _store(tmp_path)
    runner = _FakeRunner([_discovery(), result])
    with pytest.raises(WakeEffectUnknownError):
        _nudge(_dispatcher(runner, store))
    assert len(runner.calls) == 2


@pytest.mark.parametrize(
    "failure",
    [
        _delivery(returncode=1),
        ClaudeWakeCommandResult(returncode=1, stdout="not-json", stderr=""),
        _contention(),
        _delivery(sentinel="WRONG"),
    ],
)
def test_failure_after_the_transcript_changed_is_effect_unknown_without_retry(tmp_path, failure):
    store = _store(tmp_path)
    runner = _FakeRunner([_discovery(), _append_turn(store, failure)])
    with pytest.raises(WakeEffectUnknownError):
        _nudge(_dispatcher(runner, store))
    assert len(runner.calls) == 2


@pytest.mark.parametrize("failure", [_delivery(returncode=1), _contention()])
def test_transcript_flushed_after_a_nonzero_exit_is_effect_unknown_not_pre_effect(tmp_path, failure):
    store = _store(tmp_path)

    def _late_flush():
        asyncio.get_running_loop().call_later(0.05, _marker_turn, store)
        return failure

    runner = _FakeRunner([_discovery(), _late_flush])
    seen: list[str] = []
    with pytest.raises(WakeEffectUnknownError):
        _nudge(_dispatcher(runner, store, settle_seconds=0.3, refusal_observer=seen.append))
    assert seen == []
    assert len(runner.calls) == 2


def test_pre_effect_refusal_requires_two_agreeing_observations_across_the_settle(tmp_path, monkeypatch):
    store = _store(tmp_path)
    runner = _FakeRunner([_discovery(), _delivery(returncode=1)])
    dispatcher = _dispatcher(runner, store, settle_seconds=0.01)
    observations: list[str] = []
    original = dispatcher._observe_after

    def _counting(before, native_handle, *, marker):
        observations.append(marker)
        return original(before, native_handle, marker=marker)

    monkeypatch.setattr(dispatcher, "_observe_after", _counting)
    seen: list[str] = []
    dispatcher._refusal_observer = seen.append
    assert _nudge(dispatcher).outcome is TransportOutcome.TARGET_UNAVAILABLE
    assert seen == ["pre_effect_failure"]
    assert observations == [_prompt_for(), _prompt_for()]


def test_runner_exception_during_resume_is_effect_unknown_even_if_store_unchanged(tmp_path):
    store = _store(tmp_path)
    runner = _FakeRunner([_discovery(), TimeoutError("provider timeout /private/leak")])
    with pytest.raises(WakeEffectUnknownError) as info:
        _nudge(_dispatcher(runner, store))
    assert len(runner.calls) == 2
    assert info.value.__cause__ is None
    assert "leak" not in str(info.value)


def test_claimed_delivery_without_transcript_growth_is_effect_unknown(tmp_path):
    store = _store(tmp_path)
    runner = _FakeRunner([_discovery(), _delivery()])
    with pytest.raises(WakeEffectUnknownError):
        _nudge(_dispatcher(runner, store))
    assert len(runner.calls) == 2


def test_claimed_delivery_that_created_a_sibling_transcript_is_effect_unknown(tmp_path):
    store = _store(tmp_path)

    def _fork():
        sibling = store.transcript.parent / f"{OTHER_SESSION_ID}.jsonl"
        sibling.write_text(_record(OTHER_SESSION_ID, cwd=str(store.receiver_cwd)) + "\n", encoding="utf-8")
        _marker_turn(store)
        return _delivery()

    runner = _FakeRunner([_discovery(), _fork])
    with pytest.raises(WakeEffectUnknownError):
        _nudge(_dispatcher(runner, store))
    assert len(runner.calls) == 2


def test_sibling_swap_that_keeps_the_count_is_still_effect_unknown(tmp_path):
    store = _store(tmp_path)
    unrelated = store.transcript.parent / "22222222-2222-4222-8222-222222222222.jsonl"
    unrelated.write_text("{}\n", encoding="utf-8")

    def _swap():
        unrelated.unlink()
        (store.transcript.parent / f"{OTHER_SESSION_ID}.jsonl").write_text("{}\n", encoding="utf-8")
        _marker_turn(store)
        return _delivery()

    runner = _FakeRunner([_discovery(), _swap])
    with pytest.raises(WakeEffectUnknownError):
        _nudge(_dispatcher(runner, store))


def test_resume_that_wrote_the_handle_into_another_project_dir_is_effect_unknown(tmp_path):
    store = _store(tmp_path)

    def _elsewhere():
        other_dir = store.config_dir / "projects" / "-tmp-receiver-other"
        other_dir.mkdir()
        (other_dir / f"{SESSION_ID}.jsonl").write_text(_record(cwd=str(store.receiver_cwd)) + "\n", encoding="utf-8")
        return _delivery(returncode=1)

    runner = _FakeRunner([_discovery(), _elsewhere])
    with pytest.raises(WakeEffectUnknownError):
        _nudge(_dispatcher(runner, store))
    assert len(runner.calls) == 2


def test_claimed_delivery_that_appended_a_foreign_identity_is_effect_unknown(tmp_path):
    store = _store(tmp_path)

    def _foreign():
        _marker_turn(store)
        _append(store, _record(OTHER_SESSION_ID, cwd=str(store.receiver_cwd)))
        return _delivery()

    runner = _FakeRunner([_discovery(), _foreign])
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
    assert len(runner.calls) == 2


# --- late reconciliation: read-only ------------------------------------------


def _reconcile(dispatcher, wake=None):
    return asyncio.run(dispatcher.reconcile(wake or _wake()))


def test_reconcile_closes_delivered_when_the_exact_marker_and_reply_are_recorded(tmp_path):
    store = _store(tmp_path)
    _marker_turn(store)
    runner = _FakeRunner([])
    receipt = _reconcile(_dispatcher(runner, store))
    assert receipt.outcome is TransportOutcome.DELIVERED
    assert dict(receipt.details) == {"nudge_id": NUDGE_ID}
    assert runner.calls == []


def test_reconcile_never_closes_on_another_nudges_marker(tmp_path):
    store = _store(tmp_path)
    _marker_turn(store, wake=_wake(nudge_id="NUDGE-" + "c" * 32))
    runner = _FakeRunner([_discovery()])
    receipt = _reconcile(_dispatcher(runner, store))
    assert receipt.outcome is TransportOutcome.TARGET_UNAVAILABLE
    assert len(runner.calls) == 1


def test_reconcile_with_marker_but_no_reply_stays_effect_unknown(tmp_path):
    store = _store(tmp_path)
    _marker_turn(store, reply=False)
    runner = _FakeRunner([])
    with pytest.raises(WakeEffectUnknownError):
        _reconcile(_dispatcher(runner, store))
    assert runner.calls == []


@pytest.mark.parametrize("synthetic_model", ["<synthetic>", None])
def test_reconcile_with_marker_and_only_a_provider_synthesised_record_stays_effect_unknown(tmp_path, synthetic_model):
    store = _store(tmp_path)
    _marker_turn(store, reply=False)
    if synthetic_model:
        _synthetic_refusal(store)
    else:
        _append(store, _record(cwd=str(store.receiver_cwd), type="assistant", message={"role": "assistant", "model": "<synthetic>", "content": [{"type": "text", "text": "No response requested."}]}))
    runner = _FakeRunner([])
    with pytest.raises(WakeEffectUnknownError):
        _reconcile(_dispatcher(runner, store))
    assert runner.calls == []


def test_reconcile_closes_when_a_genuine_reply_follows_a_synthesised_record(tmp_path):
    store = _store(tmp_path)
    _marker_turn(store, reply=False)
    _synthetic_refusal(store)
    _append(store, _genuine(cwd=str(store.receiver_cwd)))
    assert _reconcile(_dispatcher(_FakeRunner([]), store)).outcome is TransportOutcome.DELIVERED


def test_reconcile_without_marker_is_unavailable_only_when_no_writer_is_listed(tmp_path):
    store = _store(tmp_path)
    receipt = _reconcile(_dispatcher(_FakeRunner([_discovery()]), store))
    assert receipt.outcome is TransportOutcome.TARGET_UNAVAILABLE
    assert receipt.reason_code == "target_unavailable"
    assert dict(receipt.details) == {"nudge_id": NUDGE_ID}
    assert SESSION_ID not in repr(receipt) and str(store.config_dir) not in repr(receipt)
    with pytest.raises(WakeEffectUnknownError):
        _reconcile(_dispatcher(_FakeRunner([_discovery([_agent()])]), store))
    with pytest.raises(WakeEffectUnknownError):
        _reconcile(_dispatcher(_FakeRunner([TimeoutError("discovery")]), store))


@pytest.mark.parametrize(
    "lines",
    [
        # the exact prompt text inside a tool result (shape: toolUseResult + list content) is not a submission
        [_record(toolUseResult={"stdout": _prompt_for()}, sourceToolAssistantUUID="u1",
                 message={"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": _prompt_for()}]}), _genuine()],
        # the exact prompt text inside a CLI-inserted meta note is not a submission
        [_prompt_record(_prompt_for(), isMeta=True), _genuine()],
        # a human prompt that quotes the marker is not the adapter's submission
        [_prompt_record("please look at this ledger entry:\n" + _prompt_for()), _genuine()],
        [_prompt_record(_prompt_for() + "\n"), _genuine()],
        # list-shaped content equal to the prompt text is not the recorded `-p` shape
        [_record(message={"role": "user", "content": [{"type": "text", "text": _prompt_for()}]}), _genuine()],
        # a user record whose role is not user
        [_record(message={"role": "assistant", "content": _prompt_for()}), _genuine()],
    ],
)
def test_reconcile_recognises_only_the_adapters_own_prompt_record(tmp_path, lines):
    store = _store(tmp_path)
    _append(store, *lines)
    runner = _FakeRunner([_discovery()])
    receipt = _reconcile(_dispatcher(runner, store))
    assert receipt.outcome is TransportOutcome.TARGET_UNAVAILABLE
    assert len(runner.calls) == 1


def test_reconcile_does_not_attribute_a_reply_that_follows_an_intervening_user_turn(tmp_path):
    store = _store(tmp_path)
    _marker_turn(store, reply=False)
    _synthetic_refusal(store)
    _append(store, _prompt_record("hello, what happened here?", cwd=str(store.receiver_cwd)), _genuine())
    runner = _FakeRunner([])
    with pytest.raises(WakeEffectUnknownError):
        _reconcile(_dispatcher(runner, store))
    assert runner.calls == []


def test_reconcile_does_not_attribute_a_reply_that_follows_a_tool_result(tmp_path):
    store = _store(tmp_path)
    _marker_turn(store, reply=False)
    _append(store, _record(toolUseResult={"stdout": ""}, message={"role": "user", "content": [{"type": "tool_result", "content": ""}]}), _genuine())
    with pytest.raises(WakeEffectUnknownError):
        _reconcile(_dispatcher(_FakeRunner([]), store))


def test_reconcile_attributes_a_reply_across_cli_meta_notes_only(tmp_path):
    store = _store(tmp_path)
    _marker_turn(store, reply=False)
    _append(store, _record(type="attachment"), _record(type="system", isMeta=True),
            _prompt_record("Continue from where you left off.", isMeta=True), _genuine())
    assert _reconcile(_dispatcher(_FakeRunner([]), store)).outcome is TransportOutcome.DELIVERED


def test_reconcile_keeps_delivered_when_later_turns_follow_the_reply(tmp_path):
    store = _store(tmp_path)
    _marker_turn(store)
    _append(store, _prompt_record("later human prompt", cwd=str(store.receiver_cwd)), _genuine())
    assert _reconcile(_dispatcher(_FakeRunner([]), store)).outcome is TransportOutcome.DELIVERED


def test_reconcile_uses_the_latest_marker_record_for_attribution(tmp_path):
    store = _store(tmp_path)
    _marker_turn(store)
    _marker_turn(store, reply=False)
    _synthetic_refusal(store)
    with pytest.raises(WakeEffectUnknownError):
        _reconcile(_dispatcher(_FakeRunner([]), store))


@pytest.mark.parametrize("overrides", [{"native_handle": OTHER_SESSION_ID}, {"reasoning_surface": "codex"}])
def test_reconcile_cannot_observe_an_unbound_or_absent_receiver(tmp_path, overrides):
    store = _store(tmp_path)
    runner = _FakeRunner([])
    with pytest.raises(WakeEffectUnknownError):
        _reconcile(_dispatcher(runner, store), _wake(**overrides))
    assert runner.calls == []


def test_reconcile_never_submits_a_resume(tmp_path):
    store = _store(tmp_path)
    runner = _FakeRunner([_discovery()])
    _reconcile(_dispatcher(runner, store))
    assert all(argv[1:] == ("agents", "--json") for argv, _, _ in runner.calls)


# --- constructor ---------------------------------------------------------------


def test_constructor_refuses_nonabsolute_paths_and_empty_roots(tmp_path):
    runner = _FakeRunner([])
    base = {
        "claude_binary": Path("/opt/claude"),
        "claude_config_dir": tmp_path,
        "working_directory": Path("/tmp"),
        "receiver_cwd_roots": (tmp_path,),
    }
    for key, bad in (
        ("claude_binary", Path("claude")),
        ("claude_config_dir", Path("relative")),
        ("working_directory", Path("relative")),
        ("receiver_cwd_roots", ()),
        ("receiver_cwd_roots", (Path("relative"),)),
    ):
        with pytest.raises(ValueError, match="absolute"):
            ClaudeCodeWakeDispatcher(runner, **{**base, key: bad})


def test_constructor_refuses_a_negative_settle(tmp_path):
    with pytest.raises(ValueError, match="settle"):
        _dispatcher(_FakeRunner([]), _store(tmp_path), settle_seconds=-0.1)


def test_refusal_vocabulary_is_closed_and_never_names_a_session():
    assert CLAUDE_WAKE_PRE_SUBMIT_PREFIX.endswith(":")
    for refusal_class in CLAUDE_WAKE_REFUSAL_CLASSES:
        assert refusal_class == refusal_class.lower()
        assert "-" not in refusal_class
