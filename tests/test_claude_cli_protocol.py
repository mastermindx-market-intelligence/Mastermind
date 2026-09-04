"""Black-box contract tests for the provider-private Claude CLI protocol.

Every execution test launches the committed deterministic fake as a real
subprocess in a new process group.  No native Claude binary, account, model,
credential store, or network service participates in this suite.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import subprocess
import threading
import time
from pathlib import Path

import pytest

from control_plane.claude_cli_protocol import (
    ClaudeCliInvocationPolicy,
    ClaudeCliObservation,
    ClaudeCliProtocolError,
    ClaudeCliRunner,
    ClaudeCliVersion,
    compile_claude_cli_command,
)


ROOT = Path(__file__).resolve().parents[1]
FAKE = ROOT / "scripts" / "ohf" / "fake_claude_cli.py"
SESSION_ID = "550e8400-e29b-41d4-a716-446655440000"
MODEL = "claude-opus-4-6"
RESULT = '{"decision":"HOLD","reason":"sealed fixture"}'


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _git(*args: str, cwd: Path) -> str:
    completed = subprocess.run(
        ["/usr/bin/git", *args],
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    return completed.stdout.strip()


def _workspace(tmp_path: Path) -> tuple[Path, str, str]:
    workspace = tmp_path / "sealed-workspace"
    workspace.mkdir(mode=0o700, parents=True)
    evidence = workspace / "sealed" / "evidence.txt"
    evidence.parent.mkdir(mode=0o700)
    evidence.write_text("observed: fixture confirmation\n", encoding="utf-8")
    (workspace / ".gitignore").write_text("*.runtime\n", encoding="utf-8")
    _git("init", "-q", cwd=workspace)
    _git("add", ".gitignore", "sealed/evidence.txt", cwd=workspace)
    _git(
        "-c",
        "user.name=PF1 Fixture",
        "-c",
        "user.email=pf1@example.invalid",
        "commit",
        "-q",
        "-m",
        "sealed fixture",
        cwd=workspace,
    )
    return workspace, _git("rev-parse", "HEAD", cwd=workspace), _git("status", "--porcelain=v1", cwd=workspace)


def _policy(
    tmp_path: Path,
    *,
    version: str = "2.1.259",
    idle_timeout_seconds: float = 1.0,
    absolute_timeout_seconds: float = 3.0,
    max_stdout_bytes: int = 131_072,
    max_line_bytes: int = 32_768,
    max_events: int = 16,
) -> tuple[ClaudeCliInvocationPolicy, Path, str, str]:
    workspace, head, status = _workspace(tmp_path)
    home = tmp_path / "empty-home"
    scratch = tmp_path / "private-tmp"
    home.mkdir(mode=0o700)
    scratch.mkdir(mode=0o700)
    policy = ClaudeCliInvocationPolicy(
        binary=FAKE.resolve(),
        version=ClaudeCliVersion.parse(version),
        model=MODEL,
        session_id=SESSION_ID,
        prompt=(
            "Read only sealed/evidence.txt. Return exactly the required bounded "
            "JSON decision and perform no other action."
        ),
        working_directory=workspace,
        isolated_home=home,
        isolated_tmp=scratch,
        evidence_relative_path="sealed/evidence.txt",
        expected_result_sha256=_sha256_text(RESULT),
        api_timeout_ms=1_000,
        idle_timeout_seconds=idle_timeout_seconds,
        absolute_timeout_seconds=absolute_timeout_seconds,
        terminate_grace_seconds=0.1,
        max_stdout_bytes=max_stdout_bytes,
        max_stderr_bytes=4_096,
        max_line_bytes=max_line_bytes,
        max_events=max_events,
        max_json_depth=8,
        max_json_string_bytes=8_192,
        max_json_collection_items=64,
    )
    return policy, workspace, head, status


def _fake_controls(tmp_path: Path, scenario: str = "ok") -> dict[str, str]:
    return {
        "MMX_FAKE_CLAUDE_SCENARIO": scenario,
        "MMX_FAKE_CLAUDE_STATE_FILE": str(tmp_path / "fake-state.json"),
        "MMX_FAKE_CLAUDE_VERSION": "2.1.259",
    }


def _assert_workspace_unchanged(workspace: Path, head: str, status: str) -> None:
    assert _git("rev-parse", "HEAD", cwd=workspace) == head
    assert _git("status", "--porcelain=v1", cwd=workspace) == status == ""


def test_compiler_emits_exact_248_command_and_closed_environment(tmp_path: Path) -> None:
    policy, workspace, _, _ = _policy(tmp_path, version="2.1.248")

    command = compile_claude_cli_command(policy)

    assert command.argv == (
        str(FAKE.resolve()),
        "--restricted",
        "--safe-mode",
        "-p",
        "--output-format",
        "stream-json",
        "--verbose",
        "--model",
        MODEL,
        "--session-id",
        SESSION_ID,
        "--permission-mode",
        "dontAsk",
        "--tools",
        "Read",
        "--allowedTools",
        "Read",
        "--disallowedTools",
        "mcp__*",
        "--strict-mcp-config",
        "--mcp-config",
        '{"mcpServers":{}}',
        "--disable-slash-commands",
        "--no-chrome",
        "--no-session-persistence",
        "--max-turns",
        "1",
        "--settings",
        "{}",
        policy.prompt,
    )
    assert dict(command.environment) == {
        "HOME": str(policy.isolated_home),
        "TMPDIR": str(policy.isolated_tmp),
        "PATH": "/usr/bin:/bin",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "TZ": "UTC",
        "CLAUDE_CODE_MAX_RETRIES": "0",
        "MAX_STRUCTURED_OUTPUT_RETRIES": "0",
        "CLAUDE_CODE_MAX_TOOL_USE_CONCURRENCY": "1",
        "API_TIMEOUT_MS": "1000",
        "CLAUDE_CODE_SKIP_PROMPT_HISTORY": "1",
        "IS_DEMO": "1",
    }
    assert command.working_directory == str(workspace)
    assert len(command.argv_sha256) == len(command.environment_sha256) == 64


def test_compiler_adds_no_prompt_host_flag_only_when_supported(tmp_path: Path) -> None:
    old_policy, _, _, _ = _policy(tmp_path / "old", version="2.1.258")
    new_policy, _, _, _ = _policy(tmp_path / "new", version="2.1.259")

    assert "--permission-prompts" not in compile_claude_cli_command(old_policy).argv
    argv = compile_claude_cli_command(new_policy).argv
    index = argv.index("--permission-prompts")
    assert argv[index : index + 2] == ("--permission-prompts", "none")
    assert argv[index - 2 : index] == ("--permission-mode", "dontAsk")
    assert argv[index + 2 : index + 4] == ("--tools", "Read")


@pytest.mark.parametrize("value", ["2.1.247", "2.0.999", "latest", "2.1", "v2.1.259", "2.1.259-beta"])
def test_version_parser_or_compiler_refuses_unfrozen_versions(tmp_path: Path, value: str) -> None:
    if value in {"2.1.247", "2.0.999"}:
        policy, _, _, _ = _policy(tmp_path, version=value)
        with pytest.raises(ClaudeCliProtocolError, match="supported restricted-mode floor") as error:
            compile_claude_cli_command(policy)
    else:
        with pytest.raises(ClaudeCliProtocolError, match="version") as error:
            ClaudeCliVersion.parse(value)
    assert error.value.observation is ClaudeCliObservation.PROCESS_NOT_STARTED


@pytest.mark.parametrize(
    "field,value,match",
    [
        ("model", "opus", "full Claude model identifier"),
        ("model", "claude-opus-latest", "full Claude model identifier"),
        ("session_id", "not-a-uuid", "session UUID"),
        ("evidence_relative_path", "../private.txt", "evidence path"),
        ("evidence_relative_path", "/private.txt", "evidence path"),
        ("expected_result_sha256", "short", "result digest"),
        ("api_timeout_ms", 0, "API timeout"),
        ("max_events", 0, "event limit"),
    ],
)
def test_compiler_rejects_aliases_broadening_and_bad_bounds(
    tmp_path: Path, field: str, value: object, match: str
) -> None:
    policy, _, _, _ = _policy(tmp_path)
    policy = dataclasses.replace(policy, **{field: value})
    with pytest.raises(ClaudeCliProtocolError, match=match) as error:
        compile_claude_cli_command(policy)
    assert error.value.observation is ClaudeCliObservation.PROCESS_NOT_STARTED


@pytest.mark.parametrize(
    "flag",
    [
        "--bare",
        "--continue",
        "--resume",
        "--fork-session",
        "--cloud",
        "--bg",
        "--agents",
        "--agent",
        "--fallback-model",
        "--plugin-dir",
        "--plugin-url",
        "--channels",
        "--chrome",
        "--dangerously-skip-permissions",
    ],
)
def test_compiler_rejects_every_caller_supplied_flag(tmp_path: Path, flag: str) -> None:
    policy, _, _, _ = _policy(tmp_path)
    with pytest.raises(ClaudeCliProtocolError, match="caller-supplied CLI flags") as error:
        compile_claude_cli_command(policy, requested_flags=(flag,))
    assert error.value.observation is ClaudeCliObservation.PROCESS_NOT_STARTED


def test_compiler_rejects_caller_environment_even_when_apparently_benign(tmp_path: Path) -> None:
    policy, _, _, _ = _policy(tmp_path)
    for caller_environment in ({}, {"NO_COLOR": "1"}, {"ANTHROPIC_API_KEY": "FAKE_SENTINEL"}):
        with pytest.raises(ClaudeCliProtocolError, match="caller environment") as error:
            compile_claude_cli_command(policy, caller_environment=caller_environment)
        assert error.value.observation is ClaudeCliObservation.PROCESS_NOT_STARTED


def test_protocol_dataclasses_are_deeply_immutable(tmp_path: Path) -> None:
    policy, _, _, _ = _policy(tmp_path)
    command = compile_claude_cli_command(policy)
    with pytest.raises(dataclasses.FrozenInstanceError):
        command.model = "claude-sonnet-4-6"  # type: ignore[misc]
    with pytest.raises(TypeError):
        command.environment[0] = ("HOME", "/tmp")  # type: ignore[index]
    assert isinstance(command.argv, tuple)
    assert isinstance(command.environment, tuple)


def test_happy_journey_is_one_read_one_submission_and_deterministic(tmp_path: Path) -> None:
    policy, workspace, head, status = _policy(tmp_path)
    command = compile_claude_cli_command(policy)
    state = tmp_path / "fake-state.json"

    receipt = ClaudeCliRunner().run(command, fake_controls=_fake_controls(tmp_path))

    assert receipt.observation is ClaudeCliObservation.TERMINAL_RESULT_OBSERVED
    assert receipt.session_id == SESSION_ID
    assert receipt.model == MODEL
    assert receipt.read_count == 1
    assert receipt.submission_count == 1
    assert receipt.result_sha256 == _sha256_text(RESULT)
    assert receipt.returncode == 0
    assert receipt.cleanup.process_group_empty is True
    assert receipt.cleanup.leader_reaped is True
    assert receipt.cleanup.residue_rows == ()
    first_digest = receipt.receipt_sha256
    state_payload = json.loads(state.read_text(encoding="utf-8"))
    assert state_payload["starts"] == 1
    assert state_payload["submissions"] == 1
    assert state_payload["reads"] == 1
    assert state_payload["network_attempts"] == 0
    assert state_payload["writes"] == 0
    assert state_payload["shells"] == 0
    assert state_payload["mcp_calls"] == 0
    assert state_payload["subagents"] == 0
    assert state_payload["children"] == []
    _assert_workspace_unchanged(workspace, head, status)

    second_policy, second_workspace, second_head, second_status = _policy(tmp_path / "again")
    second = ClaudeCliRunner().run(
        compile_claude_cli_command(second_policy),
        fake_controls=_fake_controls(tmp_path / "again"),
    )
    assert second.receipt_sha256 == first_digest
    _assert_workspace_unchanged(second_workspace, second_head, second_status)
    serialized = json.dumps(receipt.to_dict(), sort_keys=True)
    assert str(tmp_path) not in serialized
    assert "evidence.txt" not in serialized


@pytest.mark.parametrize(
    "scenario,code,observation",
    [
        ("stderr", "STDERR_NOT_EMPTY", ClaudeCliObservation.PROCESS_STARTED_SUBMISSION_POSSIBLE),
        ("invalid_utf8", "STDOUT_UTF8_INVALID", ClaudeCliObservation.PROCESS_STARTED_SUBMISSION_POSSIBLE),
        ("malformed_json", "STREAM_JSON_INVALID", ClaudeCliObservation.PROCESS_STARTED_SUBMISSION_POSSIBLE),
        ("duplicate_key", "STREAM_JSON_DUPLICATE_KEY", ClaudeCliObservation.PROCESS_STARTED_SUBMISSION_POSSIBLE),
        ("oversized_line", "STREAM_LINE_LIMIT", ClaudeCliObservation.PROCESS_STARTED_SUBMISSION_POSSIBLE),
        ("excessive_depth", "STREAM_JSON_DEPTH", ClaudeCliObservation.PROCESS_STARTED_SUBMISSION_POSSIBLE),
        ("excessive_string", "STREAM_JSON_STRING", ClaudeCliObservation.PROCESS_STARTED_SUBMISSION_POSSIBLE),
        ("excessive_collection", "STREAM_JSON_COLLECTION", ClaudeCliObservation.PROCESS_STARTED_SUBMISSION_POSSIBLE),
        ("too_many_events", "STREAM_EVENT_LIMIT", ClaudeCliObservation.PROCESS_STARTED_SUBMISSION_POSSIBLE),
        ("pre_init_hook", "INIT_NOT_FIRST", ClaudeCliObservation.PROCESS_STARTED_SUBMISSION_POSSIBLE),
        ("api_retry", "PROVIDER_RETRY_OBSERVED", ClaudeCliObservation.PROCESS_STARTED_SUBMISSION_POSSIBLE),
        ("unknown_event", "EVENT_UNKNOWN", ClaudeCliObservation.PROCESS_STARTED_SUBMISSION_POSSIBLE),
        ("init_model_drift", "MODEL_DRIFT", ClaudeCliObservation.PROCESS_STARTED_SUBMISSION_POSSIBLE),
        ("init_session_drift", "SESSION_DRIFT", ClaudeCliObservation.PROCESS_STARTED_SUBMISSION_POSSIBLE),
        ("init_tools_extra", "TOOL_SET_DRIFT", ClaudeCliObservation.PROCESS_STARTED_SUBMISSION_POSSIBLE),
        ("init_mcp", "MCP_OBSERVED", ClaudeCliObservation.PROCESS_STARTED_SUBMISSION_POSSIBLE),
        ("init_plugin", "PLUGIN_OBSERVED", ClaudeCliObservation.PROCESS_STARTED_SUBMISSION_POSSIBLE),
        ("assistant_parent_tool", "SUBAGENT_OBSERVED", ClaudeCliObservation.PROCESS_STARTED_SUBMISSION_POSSIBLE),
        ("assistant_write_tool", "TOOL_UNAUTHORIZED", ClaudeCliObservation.PROCESS_STARTED_SUBMISSION_POSSIBLE),
        ("read_wrong_file", "READ_SCOPE_DRIFT", ClaudeCliObservation.PROCESS_STARTED_SUBMISSION_POSSIBLE),
        ("duplicate_tool", "READ_COUNT_INVALID", ClaudeCliObservation.PROCESS_STARTED_SUBMISSION_POSSIBLE),
        ("tool_result_mismatch", "TOOL_RESULT_MISMATCH", ClaudeCliObservation.PROCESS_STARTED_SUBMISSION_POSSIBLE),
        ("permission_denied", "PERMISSION_DENIED", ClaudeCliObservation.PROCESS_STARTED_SUBMISSION_POSSIBLE),
        ("missing_result", "TERMINAL_RESULT_MISSING", ClaudeCliObservation.PROCESS_STARTED_SUBMISSION_POSSIBLE),
        ("duplicate_result", "TERMINAL_RESULT_DUPLICATE", ClaudeCliObservation.PROCESS_STARTED_SUBMISSION_POSSIBLE),
        ("post_result", "POST_TERMINAL_EVENT", ClaudeCliObservation.PROCESS_STARTED_SUBMISSION_POSSIBLE),
        ("result_session_drift", "SESSION_DRIFT", ClaudeCliObservation.PROCESS_STARTED_SUBMISSION_POSSIBLE),
        ("result_failure", "PROVIDER_FAILURE", ClaudeCliObservation.TERMINAL_PROVIDER_FAILURE_OBSERVED),
        ("result_permission_denial", "PERMISSION_DENIED", ClaudeCliObservation.TERMINAL_PROVIDER_FAILURE_OBSERVED),
        ("result_mismatch", "STRUCTURED_RESULT_MISMATCH", ClaudeCliObservation.PROCESS_STARTED_SUBMISSION_POSSIBLE),
        ("result_invalid_cost", "USAGE_INVALID", ClaudeCliObservation.PROCESS_STARTED_SUBMISSION_POSSIBLE),
        ("nonzero_after_success", "PROCESS_EXIT_INVALID", ClaudeCliObservation.OUTCOME_UNRECONCILED),
        ("secret_output", "SENSITIVE_OUTPUT", ClaudeCliObservation.PROCESS_STARTED_SUBMISSION_POSSIBLE),
        ("private_path_output", "PRIVATE_LOCATOR_OUTPUT", ClaudeCliObservation.PROCESS_STARTED_SUBMISSION_POSSIBLE),
    ],
)
def test_hostile_streams_fail_closed_and_leave_no_workspace_effect(
    tmp_path: Path,
    scenario: str,
    code: str,
    observation: ClaudeCliObservation,
) -> None:
    policy, workspace, head, status = _policy(tmp_path)
    runner = ClaudeCliRunner()
    with pytest.raises(ClaudeCliProtocolError) as captured:
        runner.run(
            compile_claude_cli_command(policy),
            fake_controls=_fake_controls(tmp_path, scenario),
        )
    error = captured.value
    assert error.code == code
    assert error.observation is observation
    assert error.cleanup is not None
    assert error.cleanup.process_group_empty is True
    assert error.cleanup.leader_reaped is True
    assert error.cleanup.residue_rows == ()
    assert "FAKE_SENTINEL" not in str(error)
    assert str(tmp_path) not in str(error)
    _assert_workspace_unchanged(workspace, head, status)


def test_total_stdout_cap_terminates_and_reaps_process_group(tmp_path: Path) -> None:
    policy, workspace, head, status = _policy(
        tmp_path,
        max_stdout_bytes=2_048,
        max_line_bytes=1_024,
    )
    with pytest.raises(ClaudeCliProtocolError) as captured:
        ClaudeCliRunner().run(
            compile_claude_cli_command(policy),
            fake_controls=_fake_controls(tmp_path, "oversized_total"),
        )
    assert captured.value.code == "STDOUT_BYTE_LIMIT"
    assert captured.value.cleanup is not None
    assert captured.value.cleanup.process_group_empty is True
    _assert_workspace_unchanged(workspace, head, status)


@pytest.mark.parametrize("scenario", ["hang_before_output", "hang_after_tool", "child_hang", "child_ignore_term"])
def test_timeout_contains_leader_and_marked_descendants(tmp_path: Path, scenario: str) -> None:
    policy, workspace, head, status = _policy(
        tmp_path,
        idle_timeout_seconds=1.0,
        absolute_timeout_seconds=1.5,
    )
    state = tmp_path / "fake-state.json"
    with pytest.raises(ClaudeCliProtocolError) as captured:
        ClaudeCliRunner().run(
            compile_claude_cli_command(policy),
            fake_controls=_fake_controls(tmp_path, scenario),
        )
    error = captured.value
    assert error.code in {"IDLE_TIMEOUT", "ABSOLUTE_TIMEOUT"}
    assert error.observation is ClaudeCliObservation.OUTCOME_UNRECONCILED
    assert error.cleanup is not None
    assert error.cleanup.process_group_empty is True
    assert error.cleanup.leader_reaped is True
    assert error.cleanup.residue_rows == ()
    payload = json.loads(state.read_text(encoding="utf-8"))
    for child_pid in payload["children"]:
        with pytest.raises(ProcessLookupError):
            os.kill(child_pid, 0)
    _assert_workspace_unchanged(workspace, head, status)


def test_cancellation_before_spawn_has_no_process_or_submission(tmp_path: Path) -> None:
    policy, workspace, head, status = _policy(tmp_path)
    cancelled = threading.Event()
    cancelled.set()
    runner = ClaudeCliRunner()

    with pytest.raises(ClaudeCliProtocolError) as captured:
        runner.run(
            compile_claude_cli_command(policy),
            cancel_event=cancelled,
            fake_controls=_fake_controls(tmp_path),
        )

    assert captured.value.code == "CANCELLED_BEFORE_START"
    assert captured.value.observation is ClaudeCliObservation.PROCESS_NOT_STARTED
    assert captured.value.cleanup is None
    assert not (tmp_path / "fake-state.json").exists()
    _assert_workspace_unchanged(workspace, head, status)


def test_cancellation_after_spawn_is_unreconciled_but_contained(tmp_path: Path) -> None:
    policy, workspace, head, status = _policy(
        tmp_path,
        idle_timeout_seconds=2.0,
        absolute_timeout_seconds=3.0,
    )
    controls = _fake_controls(tmp_path, "hang_after_tool")
    state = tmp_path / "fake-state.json"
    cancelled = threading.Event()

    def cancel_when_started() -> None:
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            if state.exists() and json.loads(state.read_text(encoding="utf-8"))["submissions"] == 1:
                cancelled.set()
                return
            time.sleep(0.01)
        raise AssertionError("fake never recorded its submission")

    canceller = threading.Thread(target=cancel_when_started, daemon=True)
    canceller.start()
    with pytest.raises(ClaudeCliProtocolError) as captured:
        ClaudeCliRunner().run(
            compile_claude_cli_command(policy),
            cancel_event=cancelled,
            fake_controls=controls,
        )
    canceller.join(timeout=2)
    assert captured.value.code == "CANCELLED_AFTER_START"
    assert captured.value.observation is ClaudeCliObservation.OUTCOME_UNRECONCILED
    assert captured.value.cleanup is not None
    assert captured.value.cleanup.process_group_empty is True
    _assert_workspace_unchanged(workspace, head, status)


def test_runner_is_an_exactly_once_invocation_guard(tmp_path: Path) -> None:
    first_policy, _, _, _ = _policy(tmp_path / "first")
    second_policy, _, _, _ = _policy(tmp_path / "second")
    runner = ClaudeCliRunner()
    runner.run(
        compile_claude_cli_command(first_policy),
        fake_controls=_fake_controls(tmp_path / "first"),
    )
    with pytest.raises(ClaudeCliProtocolError) as captured:
        runner.run(
            compile_claude_cli_command(second_policy),
            fake_controls=_fake_controls(tmp_path / "second"),
        )
    assert captured.value.code == "SECOND_INVOCATION_REFUSED"
    assert captured.value.observation is ClaudeCliObservation.PROCESS_NOT_STARTED
    assert not (tmp_path / "second" / "fake-state.json").exists()


def test_fake_controls_are_closed_and_fake_only(tmp_path: Path) -> None:
    policy, _, _, _ = _policy(tmp_path)
    command = compile_claude_cli_command(policy)
    with pytest.raises(ClaudeCliProtocolError, match="fake control") as captured:
        ClaudeCliRunner().run(command, fake_controls={"ANTHROPIC_API_KEY": "FAKE_SENTINEL"})
    assert captured.value.observation is ClaudeCliObservation.PROCESS_NOT_STARTED

    real_named_binary = tmp_path / "claude"
    real_named_binary.write_bytes(FAKE.read_bytes())
    real_named_binary.chmod(0o700)
    real_policy = dataclasses.replace(policy, binary=real_named_binary)
    with pytest.raises(ClaudeCliProtocolError, match="fake controls require") as captured:
        ClaudeCliRunner().run(
            compile_claude_cli_command(real_policy),
            fake_controls=_fake_controls(tmp_path),
        )
    assert captured.value.observation is ClaudeCliObservation.PROCESS_NOT_STARTED
