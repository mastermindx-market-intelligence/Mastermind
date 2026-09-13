from __future__ import annotations

import asyncio
import json
import os
import stat
import subprocess
import time
from pathlib import Path

import pytest

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
        assert result["stdout"]["retained_bytes"] == 2048
        assert result["stderr"]["retained_bytes"] == 2048
        assert result["stdout"]["dropped_bytes"] == 5000 - 2048
        assert result["stderr"]["dropped_bytes"] == 4000 - 2048
        assert result["stdout"]["truncated"] is True
        assert result["stderr"]["truncated"] is True

    asyncio.run(exercise())


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
