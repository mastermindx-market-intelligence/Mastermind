from __future__ import annotations

import asyncio
import io
import json
import os
import shlex
import stat
import subprocess
import time
from pathlib import Path

import pytest

import integrations.devbox_mcp.codespace_runtime as runtime_module
from integrations.devbox_mcp.codespace_runtime import (
    CodespaceBinding,
    CodespaceDevBoxRuntime,
    DevBoxRuntimeError,
)


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    )
    return completed.stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "devbox-test@example.invalid")
    _git(root, "config", "user.name", "DevBox Test")
    (root / "README.md").write_text("baseline\n", encoding="utf-8")
    _git(root, "add", "README.md")
    _git(root, "commit", "-qm", "baseline")
    return root


def _binding(repo: Path) -> CodespaceBinding:
    return CodespaceBinding(
        target_ref="target:" + "1" * 64,
        generation="generation:" + "2" * 64,
        owner_ref="owner:" + "3" * 64,
        repository="mastermindx-market-intelligence/Mastermind",
        committed_head=_git(repo, "rev-parse", "HEAD"),
    )


def _open(repo: Path, state: Path, **kwargs) -> CodespaceDevBoxRuntime:
    return CodespaceDevBoxRuntime.open(
        repo_root=repo,
        state_root=state,
        binding=_binding(repo),
        platform_name="linux",
        shell_path=Path("/bin/bash"),
        **kwargs,
    )


def _manual_started_operation(
    runtime: CodespaceDevBoxRuntime,
    state: Path,
    operation_key: str,
    *,
    pid: int = 4242,
    pgid: int = 4242,
    start_identity: str = "procfs:12345",
    boot_id: str | None = "boot-fixture",
) -> tuple[Path, str, dict]:
    digest = runtime._op_digest(operation_key)
    process_ref = "process:" + digest
    op_dir = state / "operations" / digest
    op_dir.mkdir(mode=0o700)
    record = {
        "schema": "mastermind.devbox_process_receipt.v1",
        "process_ref": process_ref,
        "request_digest": "6" * 64,
        "target_ref": runtime.binding.target_ref,
        "generation": runtime.binding.generation,
        "owner_ref": runtime.binding.owner_ref,
        "repository": runtime.binding.repository,
        "committed_head": runtime.binding.committed_head,
        "phase": "STARTED",
        "effect_state": "APPLIED",
        "terminal": False,
        "timed_out": False,
        "cancel_requested": False,
        "child_pid": pid,
        "child_pgid": pgid,
        "process_start_identity": start_identity,
        "boot_id": boot_id,
        "exit_code": None,
        "stdout": {"total_bytes": 0, "retained_bytes": 0, "dropped_bytes": 0},
        "stderr": {"total_bytes": 0, "retained_bytes": 0, "dropped_bytes": 0},
    }
    runtime_module._atomic_json(op_dir / "record.json", record)
    return op_dir, process_ref, record


async def _terminal(
    runtime: CodespaceDevBoxRuntime,
    process_ref: str,
    *,
    timeout: float = 8.0,
    stdout_cursor: int = 0,
    stderr_cursor: int = 0,
) -> dict:
    deadline = time.monotonic() + timeout
    latest = {}
    while time.monotonic() < deadline:
        latest = await runtime.read_process(
            {
                "process_ref": process_ref,
                "stdout_cursor": stdout_cursor,
                "stderr_cursor": stderr_cursor,
                "max_bytes": 65536,
            }
        )
        if latest["terminal"]:
            return latest
        await asyncio.sleep(0.05)
    raise AssertionError(f"process did not become terminal: {latest}")


def test_open_binds_exact_repo_and_private_external_state(repo: Path, tmp_path: Path) -> None:
    state = tmp_path / "state"
    runtime = _open(repo, state)

    result = asyncio.run(runtime.status({}))

    assert result["target_ref"] == "target:" + "1" * 64
    assert result["generation"] == "generation:" + "2" * 64
    assert result["owner_ref"] == "owner:" + "3" * 64
    assert result["repository"] == "mastermindx-market-intelligence/Mastermind"
    assert result["committed_head"] == _git(repo, "rev-parse", "HEAD")
    assert result["observed_head"] == result["committed_head"]
    assert result["working_tree_dirty"] is False
    assert stat.S_IMODE(state.stat().st_mode) == 0o700
    assert repo not in state.parents and state not in repo.parents


def test_default_open_refuses_dirty_source_before_effect(repo: Path, tmp_path: Path) -> None:
    (repo / "README.md").write_text("dirty before admission\n", encoding="utf-8")

    with pytest.raises(DevBoxRuntimeError) as exc_info:
        _open(repo, tmp_path / "state")

    assert exc_info.value.code == "SOURCE_DIRTY"
    assert not (tmp_path / "state" / "operations").exists()


def test_status_preserves_opening_baseline_truth_after_source_cleanup(
    repo: Path, tmp_path: Path
) -> None:
    (repo / "README.md").write_text("dirty before admission\n", encoding="utf-8")
    runtime = _open(repo, tmp_path / "state", require_clean_baseline=False)

    opening = asyncio.run(runtime.status({}))
    assert opening["baseline_working_tree_dirty"] is True
    assert opening["working_tree_dirty"] is True
    assert opening["working_tree_changed_from_baseline"] is False

    _git(repo, "checkout", "--", "README.md")
    cleaned = asyncio.run(runtime.status({}))
    assert cleaned["baseline_working_tree_dirty"] is True
    assert cleaned["working_tree_dirty"] is False
    assert cleaned["working_tree_changed_from_baseline"] is True


def test_source_must_remain_clean_until_first_effect(repo: Path, tmp_path: Path) -> None:
    async def exercise() -> None:
        state = tmp_path / "state"
        runtime = _open(repo, state)
        (repo / "external-drift.txt").write_text("unowned drift\n", encoding="utf-8")

        with pytest.raises(DevBoxRuntimeError) as exc_info:
            await runtime.start_command(
                {"operation_key": "dirty-before-first-effect", "command_text": "touch applied.txt"}
            )

        assert exc_info.value.code == "SOURCE_DIRTY"
        assert not (repo / "applied.txt").exists()
        assert list((state / "operations").iterdir()) == []

    asyncio.run(exercise())


def test_not_applied_attempt_does_not_consume_clean_baseline_gate(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def exercise() -> None:
        state = tmp_path / "state"
        runtime = _open(repo, state)

        with monkeypatch.context() as patch:
            patch.setattr(
                runtime_module.sys,
                "executable",
                str(tmp_path / "missing-supervisor-python"),
            )
            with pytest.raises(DevBoxRuntimeError) as exc_info:
                await runtime.start_command(
                    {"operation_key": "refused-first", "command_text": "touch refused.txt"}
                )
            assert exc_info.value.code == "START_REFUSED"

        (repo / "external-drift.txt").write_text("unowned drift\n", encoding="utf-8")
        with pytest.raises(DevBoxRuntimeError) as exc_info:
            await runtime.start_command(
                {"operation_key": "after-refusal", "command_text": "touch applied.txt"}
            )

        assert exc_info.value.code == "SOURCE_DIRTY"
        assert not (repo / "applied.txt").exists()

    asyncio.run(exercise())


def test_pre_effect_receipt_write_failure_cleans_empty_operation_and_allows_retry(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def exercise() -> None:
        state = tmp_path / "state"
        runtime = _open(repo, state)
        real_atomic = runtime_module._atomic_json

        def fail_prepared(path: Path, value: dict) -> None:
            if path.name == "record.json" and value.get("phase") == "PREPARED":
                raise OSError("simulated pre-effect receipt failure")
            real_atomic(path, value)

        with monkeypatch.context() as patch:
            patch.setattr(runtime_module, "_atomic_json", fail_prepared)
            with pytest.raises(DevBoxRuntimeError) as exc_info:
                await runtime.start_command(
                    {"operation_key": "receipt-write-fails", "command_text": "true"}
                )
            assert exc_info.value.code == "START_REFUSED"

        failed_dir = state / "operations" / runtime._op_digest("receipt-write-fails")
        assert not failed_dir.exists()
        started = await runtime.start_command(
            {"operation_key": "after-receipt-cleanup", "command_text": "printf recovered"}
        )
        result = await _terminal(runtime, started["process_ref"])
        assert result["exit_code"] == 0
        assert result["stdout"]["text"] == "recovered"

    asyncio.run(exercise())


def test_exact_empty_pre_effect_directory_has_typed_recovery_refusal(
    repo: Path, tmp_path: Path
) -> None:
    async def exercise() -> None:
        state = tmp_path / "state"
        runtime = _open(repo, state)
        orphan = state / "operations" / runtime._op_digest("orphan-pre-effect")
        orphan.mkdir(mode=0o700)
        orphan.chmod(0o700)

        for operation_key in ("orphan-pre-effect", "different-after-orphan"):
            with pytest.raises(DevBoxRuntimeError) as exc_info:
                await runtime.start_command(
                    {"operation_key": operation_key, "command_text": "true"}
                )
            assert exc_info.value.code == "PRE_EFFECT_RECEIPT_UNAVAILABLE"
        assert list(orphan.iterdir()) == []

    asyncio.run(exercise())


def test_later_commands_can_test_the_first_owned_edit(repo: Path, tmp_path: Path) -> None:
    async def exercise() -> None:
        runtime = _open(repo, tmp_path / "state")
        edit = await runtime.start_command(
            {
                "operation_key": "owned-edit",
                "command_text": "printf changed > owned-change.txt",
                "timeout_seconds": 5,
            }
        )
        edited = await _terminal(runtime, edit["process_ref"])
        assert edited["exit_code"] == 0

        verify = await runtime.start_command(
            {
                "operation_key": "verify-owned-edit",
                "command_text": 'test "$(cat owned-change.txt)" = changed',
                "timeout_seconds": 5,
            }
        )
        verified = await _terminal(runtime, verify["process_ref"])
        assert verified["exit_code"] == 0

    asyncio.run(exercise())


def test_reopen_after_owned_edit_preserves_clean_admission_baseline(
    repo: Path, tmp_path: Path
) -> None:
    async def exercise() -> None:
        state = tmp_path / "state"
        runtime = _open(repo, state)
        started = await runtime.start_command(
            {
                "operation_key": "edit-before-reopen",
                "command_text": "printf changed > reopened-change.txt",
                "timeout_seconds": 5,
            }
        )
        terminal = await _terminal(runtime, started["process_ref"])
        assert terminal["exit_code"] == 0

        reopened = _open(repo, state)
        status = await reopened.status({})
        assert status["baseline_working_tree_dirty"] is False
        assert status["working_tree_dirty"] is True
        assert status["working_tree_changed_from_baseline"] is True
        recovered = await reopened.read_process(
            {"process_ref": started["process_ref"], "max_bytes": 65536}
        )
        assert recovered["terminal"] is True
        assert recovered["exit_code"] == 0
        assert (state / "baseline.json").is_file()
        assert stat.S_IMODE((state / "baseline.json").stat().st_mode) == 0o600

    asyncio.run(exercise())


def test_dirty_inspection_baseline_cannot_be_cleaned_and_rearmed(
    repo: Path, tmp_path: Path
) -> None:
    state = tmp_path / "state"
    (repo / "README.md").write_text("dirty before admission\n", encoding="utf-8")
    _open(repo, state, require_clean_baseline=False)
    _git(repo, "checkout", "--", "README.md")

    with pytest.raises(DevBoxRuntimeError) as exc_info:
        _open(repo, state)

    assert exc_info.value.code == "SOURCE_DIRTY"


def test_open_refuses_wrong_platform_symlink_or_state_inside_repo(repo: Path, tmp_path: Path) -> None:
    with pytest.raises(DevBoxRuntimeError) as exc_info:
        CodespaceDevBoxRuntime.open(
            repo_root=repo,
            state_root=tmp_path / "state",
            binding=_binding(repo),
            platform_name="darwin",
            shell_path=Path("/bin/bash"),
        )
    assert exc_info.value.code == "RUNTIME_UNQUALIFIED"

    link = tmp_path / "repo-link"
    link.symlink_to(repo, target_is_directory=True)
    with pytest.raises(DevBoxRuntimeError) as exc_info:
        CodespaceDevBoxRuntime.open(
            repo_root=link,
            state_root=tmp_path / "state-2",
            binding=_binding(repo),
            platform_name="linux",
            shell_path=Path("/bin/bash"),
        )
    assert exc_info.value.code == "RUNTIME_UNQUALIFIED"

    with pytest.raises(DevBoxRuntimeError) as exc_info:
        _open(repo, repo / ".devbox-state")
    assert exc_info.value.code == "RUNTIME_UNQUALIFIED"


def test_exit_zero_and_exit_seven_preserve_separate_streams(repo: Path, tmp_path: Path) -> None:
    async def exercise() -> None:
        runtime = _open(repo, tmp_path / "state")
        first = await runtime.start_command(
            {
                "operation_key": "exit-zero",
                "command_text": "printf 'out-zero'; printf 'err-zero' >&2; exit 0",
                "timeout_seconds": 5,
                "output_limit_bytes": 65536,
            }
        )
        assert first["effect_state"] == "APPLIED"
        result = await _terminal(runtime, first["process_ref"])
        assert result["exit_code"] == 0
        assert result["stdout"]["text"] == "out-zero"
        assert result["stderr"]["text"] == "err-zero"
        assert result["stdout"]["next_cursor"] == len(b"out-zero")
        assert result["stderr"]["next_cursor"] == len(b"err-zero")

        second = await runtime.start_command(
            {
                "operation_key": "exit-seven",
                "command_text": "printf 'seven-out'; printf 'seven-err' >&2; exit 7",
                "timeout_seconds": 5,
                "output_limit_bytes": 65536,
            }
        )
        result = await _terminal(runtime, second["process_ref"])
        assert result["exit_code"] == 7
        assert result["timed_out"] is False
        assert result["stdout"]["text"] == "seven-out"
        assert result["stderr"]["text"] == "seven-err"

    asyncio.run(exercise())


def test_command_can_outlive_start_call_and_be_observed_later(repo: Path, tmp_path: Path) -> None:
    async def exercise() -> None:
        runtime = _open(repo, tmp_path / "state")
        started = await runtime.start_command(
            {
                "operation_key": "outlives-call",
                "command_text": "printf begin; sleep 0.35; printf end",
                "timeout_seconds": 5,
            }
        )
        immediate = await runtime.read_process(
            {"process_ref": started["process_ref"], "max_bytes": 65536}
        )
        assert immediate["process_ref"] == started["process_ref"]
        result = await _terminal(runtime, started["process_ref"])
        assert result["exit_code"] == 0
        assert result["stdout"]["text"] == "beginend"

    asyncio.run(exercise())


def test_supervisor_import_uses_reviewed_source_not_attended_repo(
    repo: Path, tmp_path: Path
) -> None:
    hostile = repo / "integrations" / "devbox_mcp"
    hostile.mkdir(parents=True)
    (repo / "integrations" / "__init__.py").write_text("", encoding="utf-8")
    (hostile / "__init__.py").write_text("", encoding="utf-8")
    (hostile / "codespace_runtime.py").write_text(
        "from pathlib import Path\n"
        "Path(__file__).resolve().parents[2].joinpath("
        "'HOSTILE_SUPERVISOR_IMPORTED').write_text('wrong source', encoding='utf-8')\n",
        encoding="utf-8",
    )
    _git(repo, "add", "integrations")
    _git(repo, "commit", "-qm", "hostile attended checkout module")

    async def exercise() -> None:
        runtime = _open(repo, tmp_path / "state")
        started = await runtime.start_command(
            {
                "operation_key": "reviewed-supervisor-source",
                "command_text": "printf reviewed-source",
                "timeout_seconds": 5,
            }
        )
        assert not (repo / "HOSTILE_SUPERVISOR_IMPORTED").exists()
        result = await _terminal(runtime, started["process_ref"])
        assert result["exit_code"] == 0
        assert result["stdout"]["text"] == "reviewed-source"

    asyncio.run(exercise())


def test_same_operation_reconciles_one_process_and_changed_payload_conflicts(
    repo: Path, tmp_path: Path
) -> None:
    async def exercise() -> None:
        runtime = _open(repo, tmp_path / "state")
        request = {
            "operation_key": "dedupe",
            "command_text": "printf once >> dedupe.txt; sleep 0.2",
            "timeout_seconds": 5,
        }
        first = await runtime.start_command(request)
        second = await runtime.start_command(dict(request))
        assert second["process_ref"] == first["process_ref"]
        assert second["reconciled"] is True
        await _terminal(runtime, first["process_ref"])
        assert (repo / "dedupe.txt").read_text(encoding="utf-8") == "once"

        with pytest.raises(DevBoxRuntimeError) as exc_info:
            await runtime.start_command({**request, "command_text": "printf twice >> dedupe.txt"})
        assert exc_info.value.code == "OPERATION_CONFLICT"
        assert (repo / "dedupe.txt").read_text(encoding="utf-8") == "once"

    asyncio.run(exercise())


def test_child_environment_strips_ambient_credentials_and_git_helpers(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GH_TOKEN", "secret-gh")
    monkeypatch.setenv("GITHUB_TOKEN", "secret-github")
    monkeypatch.setenv("OPENAI_API_KEY", "secret-openai")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "secret-aws")
    monkeypatch.setenv("SSH_AUTH_SOCK", "/tmp/fake-agent")

    async def exercise() -> None:
        runtime = _open(repo, tmp_path / "state")
        started = await runtime.start_command(
            {
                "operation_key": "env-scrub",
                "command_text": (
                    "printf '%s|%s|%s|%s|%s|%s|%s' "
                    '"${GH_TOKEN-unset}" "${GITHUB_TOKEN-unset}" '
                    '"${OPENAI_API_KEY-unset}" "${AWS_SECRET_ACCESS_KEY-unset}" '
                    '"${SSH_AUTH_SOCK-unset}" "${GIT_CONFIG_GLOBAL-unset}" '
                    '"${GIT_TERMINAL_PROMPT-unset}"'
                ),
                "timeout_seconds": 5,
            }
        )
        result = await _terminal(runtime, started["process_ref"])
        assert result["exit_code"] == 0
        fields = result["stdout"]["text"].split("|")
        assert fields[:5] == ["unset"] * 5
        assert fields[5] == "/dev/null"
        assert fields[6] == "0"

    asyncio.run(exercise())


def test_timeout_is_terminal_truth_not_generic_failure(repo: Path, tmp_path: Path) -> None:
    async def exercise() -> None:
        runtime = _open(repo, tmp_path / "state")
        started = await runtime.start_command(
            {
                "operation_key": "timeout",
                "command_text": "sleep 30",
                "timeout_seconds": 1,
            }
        )
        result = await _terminal(runtime, started["process_ref"], timeout=6)
        assert result["terminal"] is True
        assert result["timed_out"] is True
        assert result["exit_code"] is not None
        assert result["effect_state"] == "APPLIED"

    asyncio.run(exercise())


def test_cancel_targets_exact_owned_generation(repo: Path, tmp_path: Path) -> None:
    async def exercise() -> None:
        runtime = _open(repo, tmp_path / "state")
        started = await runtime.start_command(
            {
                "operation_key": "cancel",
                "command_text": "sleep 30",
                "timeout_seconds": 60,
            }
        )
        cancellation = await runtime.cancel_process(
            {"process_ref": started["process_ref"], "reason": "test stop"}
        )
        assert cancellation["process_ref"] == started["process_ref"]
        assert cancellation["cancel_requested"] is True
        result = await _terminal(runtime, started["process_ref"], timeout=6)
        assert result["terminal"] is True
        assert result["cancel_requested"] is True
        assert result["timed_out"] is False

    asyncio.run(exercise())


def test_live_read_projects_cancel_receipt_before_terminal(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = tmp_path / "state"
    runtime = _open(repo, state)
    _op_dir, process_ref, _record = _manual_started_operation(
        runtime, state, "live-cancel-projection"
    )
    monkeypatch.setattr(runtime_module.os, "getpgid", lambda _pid: 4242)
    monkeypatch.setattr(
        runtime_module,
        "_process_start_identity",
        lambda _pid: ("procfs:12345", "boot-fixture"),
    )
    monkeypatch.setattr(runtime_module.os, "killpg", lambda _pgid, _sig: None)

    cancellation = asyncio.run(
        runtime.cancel_process(
            {"process_ref": process_ref, "reason": "live cancellation truth"}
        )
    )
    assert cancellation["cancel_requested"] is True
    assert cancellation["terminal"] is False
    observed = asyncio.run(
        runtime.read_process({"process_ref": process_ref, "max_bytes": 65536})
    )
    assert observed["terminal"] is False
    assert observed["cancel_requested"] is True


def test_cancel_after_terminal_returns_terminal_without_signalling(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def exercise() -> None:
        runtime = _open(repo, tmp_path / "state")
        started = await runtime.start_command(
            {"operation_key": "already-terminal", "command_text": "true"}
        )
        terminal = await _terminal(runtime, started["process_ref"])
        signals: list[tuple[int, int]] = []
        monkeypatch.setattr(
            runtime_module.os, "killpg", lambda pgid, sig: signals.append((pgid, sig))
        )
        result = await runtime.cancel_process(
            {"process_ref": started["process_ref"], "reason": "late cancel"}
        )
        assert result == {
            "process_ref": started["process_ref"],
            "cancel_requested": terminal["cancel_requested"],
            "terminal": True,
        }
        assert signals == []

    asyncio.run(exercise())


def test_cancel_unknown_process_refuses(repo: Path, tmp_path: Path) -> None:
    runtime = _open(repo, tmp_path / "state")
    with pytest.raises(DevBoxRuntimeError) as exc_info:
        asyncio.run(
            runtime.cancel_process(
                {"process_ref": "process:" + "f" * 64, "reason": "unknown"}
            )
        )
    assert exc_info.value.code == "PROCESS_NOT_FOUND"


def test_cancel_refuses_identity_mismatch_before_signal(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = tmp_path / "state"
    runtime = _open(repo, state)
    _op_dir, process_ref, _record = _manual_started_operation(
        runtime, state, "identity-mismatch"
    )
    signals: list[tuple[int, int]] = []
    monkeypatch.setattr(runtime_module.os, "getpgid", lambda _pid: 9999)
    monkeypatch.setattr(
        runtime_module,
        "_process_start_identity",
        lambda _pid: ("procfs:changed", "boot-fixture"),
    )
    monkeypatch.setattr(
        runtime_module.os, "killpg", lambda pgid, sig: signals.append((pgid, sig))
    )

    with pytest.raises(DevBoxRuntimeError) as exc_info:
        asyncio.run(
            runtime.cancel_process(
                {"process_ref": process_ref, "reason": "identity mismatch"}
            )
        )
    assert exc_info.value.code == "PROCESS_IDENTITY_UNKNOWN"
    assert signals == []


def test_cancel_returns_terminal_projection_when_process_exits_before_signal(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = tmp_path / "state"
    runtime = _open(repo, state)
    op_dir, process_ref, record = _manual_started_operation(
        runtime, state, "exit-before-signal"
    )
    monkeypatch.setattr(runtime_module.os, "getpgid", lambda _pid: 4242)
    monkeypatch.setattr(
        runtime_module,
        "_process_start_identity",
        lambda _pid: ("procfs:12345", "boot-fixture"),
    )

    def exit_before_signal(_pgid: int, _sig: int) -> None:
        terminal = dict(record)
        terminal.update(
            phase="TERMINAL",
            terminal=True,
            exit_code=0,
            cancel_requested=False,
            ended_at_ns=time.time_ns(),
        )
        runtime_module._persist_effect_record(op_dir, terminal)
        raise ProcessLookupError("already exited")

    monkeypatch.setattr(runtime_module.os, "killpg", exit_before_signal)
    result = asyncio.run(
        runtime.cancel_process(
            {"process_ref": process_ref, "reason": "race with terminal"}
        )
    )
    assert result == {
        "process_ref": process_ref,
        "cancel_requested": True,
        "terminal": True,
    }


def test_cancel_signal_error_is_effect_uncertain(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = tmp_path / "state"
    runtime = _open(repo, state)
    _op_dir, process_ref, _record = _manual_started_operation(
        runtime, state, "signal-uncertain"
    )
    monkeypatch.setattr(runtime_module.os, "getpgid", lambda _pid: 4242)
    monkeypatch.setattr(
        runtime_module,
        "_process_start_identity",
        lambda _pid: ("procfs:12345", "boot-fixture"),
    )
    monkeypatch.setattr(
        runtime_module.os,
        "killpg",
        lambda _pgid, _sig: (_ for _ in ()).throw(OSError("signal uncertain")),
    )
    with pytest.raises(DevBoxRuntimeError) as exc_info:
        asyncio.run(
            runtime.cancel_process(
                {"process_ref": process_ref, "reason": "signal uncertainty"}
            )
        )
    assert exc_info.value.code == "CANCEL_UNCERTAIN"


def test_root_identity_drift_refuses_new_effect(repo: Path, tmp_path: Path) -> None:
    async def exercise() -> None:
        runtime = _open(repo, tmp_path / "state")
        original = tmp_path / "repo-original"
        repo.rename(original)
        replacement = tmp_path / "repo"
        replacement.mkdir()
        with pytest.raises(DevBoxRuntimeError) as exc_info:
            await runtime.start_command(
                {"operation_key": "drift", "command_text": "touch should-not-exist"}
            )
        assert exc_info.value.code == "BINDING_CHANGED"
        assert not (replacement / "should-not-exist").exists()
        assert not (original / "should-not-exist").exists()

    asyncio.run(exercise())


def test_live_progress_never_claims_retained_bytes_before_file_is_visible(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "stdout.bin"
    progress = tmp_path / "stdout.progress.json"
    real_volatile = runtime_module._volatile_json
    observed_progress: list[dict] = []

    def witness(path: Path, value: dict) -> None:
        if path == progress and value.get("retained_bytes", 0) > 0:
            visible = output.stat().st_size if output.exists() else 0
            assert visible >= value["retained_bytes"]
        observed_progress.append(dict(value))
        real_volatile(path, value)

    monkeypatch.setattr(runtime_module, "_volatile_json", witness)
    result: dict[str, int] = {}
    runtime_module._pump(
        io.BytesIO(b"x" * 5000),
        output,
        progress,
        2048,
        result,
        "stdout",
    )

    assert result == {"stdout": 5000, "stdout_retained": 2048}
    assert output.read_bytes() == b"x" * 2048
    assert observed_progress[-1]["total_bytes"] == 5000
    assert observed_progress[-1]["retained_bytes"] == 2048


def test_midflight_stream_accounting_reports_produced_and_dropped_bytes(
    repo: Path, tmp_path: Path
) -> None:
    async def exercise() -> None:
        runtime = _open(repo, tmp_path / "state")
        release = tmp_path / "release-midflight"
        started = await runtime.start_command(
            {
                "operation_key": "midflight-accounting",
                "command_text": (
                    "python3 -c \"import sys; "
                    "sys.stdout.write('x'*5000); sys.stdout.flush()\"; "
                    f"while [ ! -e {shlex.quote(str(release))} ]; do sleep 0.02; done"
                ),
                "timeout_seconds": 10,
                "output_limit_bytes": 2048,
            }
        )
        latest: dict = {}
        deadline = time.monotonic() + 5.0
        try:
            while time.monotonic() < deadline:
                latest = await runtime.read_process(
                    {"process_ref": started["process_ref"], "max_bytes": 65536}
                )
                if (
                    latest["stdout"]["text"]
                    and latest["stdout"]["total_bytes"] == 5000
                ):
                    break
                await asyncio.sleep(0.05)
            assert latest["terminal"] is False
            assert latest["stdout"]["accounting_complete"] is False
            assert latest["stdout"]["text"] == "x" * 2048
            assert latest["stdout"]["total_bytes"] == 5000
            assert latest["stdout"]["retained_bytes"] == 2048
            assert latest["stdout"]["dropped_bytes"] == 5000 - 2048
            assert latest["stdout"]["truncated"] is True
            assert latest["stdout"]["gap_ranges"] == [[2048, 5000]]
        finally:
            release.touch()
            await _terminal(runtime, started["process_ref"], timeout=6)

    asyncio.run(exercise())


def test_output_is_bounded_and_reports_dropped_bytes(repo: Path, tmp_path: Path) -> None:
    async def exercise() -> None:
        runtime = _open(repo, tmp_path / "state")
        started = await runtime.start_command(
            {
                "operation_key": "bounded-output",
                "command_text": "python3 -c \"import sys; sys.stdout.write('x'*5000); sys.stderr.write('y'*4000)\"",
                "timeout_seconds": 5,
                "output_limit_bytes": 2048,
            }
        )
        result = await _terminal(runtime, started["process_ref"])
        assert result["exit_code"] == 0
        assert result["stdout"]["accounting_complete"] is True
        assert result["stderr"]["accounting_complete"] is True
        assert result["stdout"]["retained_bytes"] == 2048
        assert result["stderr"]["retained_bytes"] == 2048
        assert result["stdout"]["dropped_bytes"] == 5000 - 2048
        assert result["stderr"]["dropped_bytes"] == 4000 - 2048
        assert result["stdout"]["truncated"] is True
        assert result["stderr"]["truncated"] is True

    asyncio.run(exercise())


def test_cursor_past_retained_output_rebases_to_readable_end(
    repo: Path, tmp_path: Path
) -> None:
    async def exercise() -> None:
        runtime = _open(repo, tmp_path / "state")
        started = await runtime.start_command(
            {
                "operation_key": "cursor-rebase",
                "command_text": "printf abc",
                "timeout_seconds": 5,
            }
        )
        await _terminal(runtime, started["process_ref"])
        result = await runtime.read_process(
            {
                "process_ref": started["process_ref"],
                "stdout_cursor": 999,
                "max_bytes": 65536,
            }
        )
        assert result["stdout"]["text"] == ""
        assert result["stdout"]["start_cursor"] == 3
        assert result["stdout"]["next_cursor"] == 3
        assert result["stdout"]["total_bytes"] == 3
        assert result["stdout"]["retained_bytes"] == 3

    asyncio.run(exercise())


def test_output_uncertainty_does_not_leave_nondaemon_supervisor_threads(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = tmp_path / "state"
    runtime = _open(repo, state)
    digest = runtime._op_digest("pump-uncertainty")
    process_ref = "process:" + digest
    op_dir = state / "operations" / digest
    op_dir.mkdir(mode=0o700)
    prepared = {
        "schema": "mastermind.devbox_process_receipt.v1",
        "process_ref": process_ref,
        "request_digest": "5" * 64,
        "target_ref": runtime.binding.target_ref,
        "generation": runtime.binding.generation,
        "owner_ref": runtime.binding.owner_ref,
        "repository": runtime.binding.repository,
        "committed_head": runtime.binding.committed_head,
        "phase": "PREPARED",
        "effect_state": "EFFECT_UNKNOWN",
        "terminal": False,
        "timed_out": False,
        "cancel_requested": False,
        "child_pid": None,
        "child_pgid": None,
        "process_start_identity": None,
        "boot_id": None,
        "exit_code": None,
        "stdout": {"total_bytes": 0, "retained_bytes": 0, "dropped_bytes": 0},
        "stderr": {"total_bytes": 0, "retained_bytes": 0, "dropped_bytes": 0},
    }
    runtime_module._atomic_json(op_dir / "record.json", prepared)

    class FakeStdin:
        buffer = io.BytesIO(b'{"command_text":"true"}\n')

    daemon_flags: list[bool] = []
    cancel_receipt_written = False

    class StuckThread:
        def __init__(self, *args, daemon: bool, **kwargs) -> None:
            daemon_flags.append(daemon)

        def start(self) -> None:
            nonlocal cancel_receipt_written
            if not cancel_receipt_written:
                runtime_module._atomic_json(
                    op_dir / "cancel.json",
                    {
                        "process_ref": process_ref,
                        "reason_digest": "7" * 64,
                        "requested_at_ns": time.time_ns(),
                    },
                )
                cancel_receipt_written = True

        def join(self, timeout: float | None = None) -> None:
            return None

        def is_alive(self) -> bool:
            return True

    monkeypatch.setattr(runtime_module.sys, "stdin", FakeStdin())
    monkeypatch.setattr(runtime_module.threading, "Thread", StuckThread)
    exit_code = runtime_module._supervise(
        op_dir,
        repo_root=repo,
        state_home=state / "home",
        shell=Path("/bin/bash"),
        timeout_seconds=5,
        output_limit_bytes=65536,
    )

    assert exit_code == 74
    assert daemon_flags == [True, True]
    observed = runtime_module._load_reconciled_record(op_dir)
    assert observed["phase"] == "TERMINAL_OUTPUT_UNCERTAIN"
    assert observed["effect_state"] == "EFFECT_UNKNOWN"
    assert observed["terminal"] is True
    assert observed["cancel_requested"] is True


def test_durable_record_contains_no_command_text_or_secret_values(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GH_TOKEN", "must-never-be-recorded")

    async def exercise() -> None:
        state = tmp_path / "state"
        runtime = _open(repo, state)
        started = await runtime.start_command(
            {
                "operation_key": "record-redaction",
                "command_text": "printf harmless",
                "timeout_seconds": 5,
            }
        )
        await _terminal(runtime, started["process_ref"])
        rendered = "\n".join(
            path.read_text(encoding="utf-8", errors="replace")
            for path in state.rglob("*.json")
        )
        assert "printf harmless" not in rendered
        assert "must-never-be-recorded" not in rendered
        assert started["process_ref"] in rendered

    asyncio.run(exercise())


def test_supervisor_reconciles_when_primary_effect_receipt_write_is_lost(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = tmp_path / "state"
    runtime = _open(repo, state)
    digest = runtime._op_digest("primary-receipt-loss")
    process_ref = "process:" + digest
    op_dir = state / "operations" / digest
    op_dir.mkdir(mode=0o700)
    prepared = {
        "schema": "mastermind.devbox_process_receipt.v1",
        "process_ref": process_ref,
        "request_digest": "4" * 64,
        "target_ref": runtime.binding.target_ref,
        "generation": runtime.binding.generation,
        "owner_ref": runtime.binding.owner_ref,
        "repository": runtime.binding.repository,
        "committed_head": runtime.binding.committed_head,
        "phase": "PREPARED",
        "effect_state": "EFFECT_UNKNOWN",
        "terminal": False,
        "timed_out": False,
        "cancel_requested": False,
        "child_pid": None,
        "child_pgid": None,
        "process_start_identity": None,
        "boot_id": None,
        "exit_code": None,
        "stdout": {"total_bytes": 0, "retained_bytes": 0, "dropped_bytes": 0},
        "stderr": {"total_bytes": 0, "retained_bytes": 0, "dropped_bytes": 0},
    }
    real_atomic = runtime_module._atomic_json
    real_atomic(op_dir / "record.json", prepared)

    class FakeStdin:
        buffer = io.BytesIO(b'{"command_text":"printf durable"}\n')

    monkeypatch.setattr(runtime_module.sys, "stdin", FakeStdin())

    def lose_primary_effect_write(path: Path, value: dict) -> None:
        if path.name == "record.json" and value.get("phase") in {
            "STARTED",
            "TERMINAL",
        }:
            raise OSError("simulated primary receipt loss")
        real_atomic(path, value)

    monkeypatch.setattr(runtime_module, "_atomic_json", lose_primary_effect_write)
    exit_code = runtime_module._supervise(
        op_dir,
        repo_root=repo,
        state_home=state / "home",
        shell=Path("/bin/bash"),
        timeout_seconds=5,
        output_limit_bytes=65536,
    )

    assert exit_code == 0
    observed = asyncio.run(
        runtime.read_process({"process_ref": process_ref, "max_bytes": 65536})
    )
    assert observed["effect_state"] == "APPLIED"
    assert observed["terminal"] is True
    assert observed["exit_code"] == 0
    assert observed["stdout"]["text"] == "durable"
    assert (op_dir / "started.json").is_file()
    assert (op_dir / "terminal.json").is_file()

    (op_dir / "record.json").unlink()
    missing_primary = asyncio.run(
        runtime.read_process({"process_ref": process_ref, "max_bytes": 65536})
    )
    assert missing_primary["effect_state"] == "APPLIED"
    assert missing_primary["terminal"] is True
    assert missing_primary["exit_code"] == 0
    assert missing_primary["stdout"]["text"] == "durable"

    (op_dir / "record.json").write_text("{malformed", encoding="utf-8")
    malformed_primary = asyncio.run(
        runtime.read_process({"process_ref": process_ref, "max_bytes": 65536})
    )
    assert malformed_primary["effect_state"] == "APPLIED"
    assert malformed_primary["terminal"] is True
    assert malformed_primary["exit_code"] == 0
    assert malformed_primary["stdout"]["text"] == "durable"

    terminal_path = op_dir / "terminal.json"
    valid_terminal = json.loads(terminal_path.read_text(encoding="utf-8"))
    identity_conflict = dict(valid_terminal)
    identity_conflict["owner_ref"] = "owner:" + "f" * 64
    real_atomic(terminal_path, identity_conflict)
    with pytest.raises(DevBoxRuntimeError) as exc_info:
        asyncio.run(runtime.read_process({"process_ref": process_ref, "max_bytes": 65536}))
    assert exc_info.value.code == "RECEIPT_UNAVAILABLE"

    phase_conflict = dict(valid_terminal)
    phase_conflict["phase"] = "STARTED"
    real_atomic(terminal_path, phase_conflict)
    with pytest.raises(DevBoxRuntimeError) as exc_info:
        asyncio.run(runtime.read_process({"process_ref": process_ref, "max_bytes": 65536}))
    assert exc_info.value.code == "RECEIPT_UNAVAILABLE"
    real_atomic(terminal_path, valid_terminal)
