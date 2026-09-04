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
import pwd
import subprocess
import threading
import time
import traceback
from pathlib import Path

import pytest

import control_plane.claude_cli_protocol as protocol
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
EVIDENCE = "observed: fixture confirmation\n"


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _expected_result(evidence: str = EVIDENCE) -> str:
    return json.dumps(
        {"decision": "HOLD", "evidence_sha256": _sha256_text(evidence)},
        sort_keys=True,
        separators=(",", ":"),
    )


def _expected_prompt(path: str = "sealed/evidence.txt", evidence: str = EVIDENCE) -> str:
    result = _expected_result(evidence)
    return (
        f"Read exactly one sealed relative file: {path}\n"
        f"Expected SHA-256: {_sha256_text(evidence)}\n"
        f"Return exactly: {result}\n"
        "Do not perform any other action."
    )


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
    evidence.write_text(EVIDENCE, encoding="utf-8")
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
    idle_timeout_seconds: float = 3.0,
    absolute_timeout_seconds: float = 5.0,
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
        prompt=_expected_prompt(),
        working_directory=workspace,
        isolated_home=home,
        isolated_tmp=scratch,
        evidence_relative_path="sealed/evidence.txt",
        expected_result_sha256=_sha256_text(_expected_result()),
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

    settings = {
        "autoMemoryEnabled": False,
        "disableAgentView": True,
        "disableAllHooks": True,
        "disableAutoMode": "disable",
        "disableDeepLinkRegistration": "disable",
        "enableAllProjectMcpServers": False,
        "enabledMcpjsonServers": [],
        "includeGitInstructions": False,
        "permissions": {
            "allow": ["Read(./sealed/evidence.txt)"],
            "ask": [],
            "defaultMode": "dontAsk",
            "deny": [
                "Agent",
                "Bash",
                "Edit",
                "Glob",
                "Grep",
                "NotebookEdit",
                "Skill",
                "Task",
                "WebFetch",
                "WebSearch",
                "Write",
                "mcp__*",
            ],
            "disableBypassPermissionsMode": "disable",
        },
    }
    settings_json = json.dumps(settings, sort_keys=True, separators=(",", ":"))
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
        settings_json,
        policy.prompt,
    )
    assert command.settings_sha256 == _sha256_text(settings_json)
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


def test_compiler_binds_the_reviewed_fake_bytes_and_filesystem_identity(tmp_path: Path) -> None:
    policy, _, _, _ = _policy(tmp_path)

    command = compile_claude_cli_command(policy)
    binary_info = FAKE.stat()

    assert command.binary_sha256 == hashlib.sha256(FAKE.read_bytes()).hexdigest()
    assert command.binary_device == binary_info.st_dev
    assert command.binary_inode == binary_info.st_ino
    assert command.binary_size == binary_info.st_size
    assert command.binary_mtime_ns == binary_info.st_mtime_ns


def test_compiler_refuses_the_native_home_even_with_an_isolated_temp(tmp_path: Path) -> None:
    policy, _, _, _ = _policy(tmp_path)
    with pytest.raises(ClaudeCliProtocolError) as captured:
        compile_claude_cli_command(dataclasses.replace(policy, isolated_home=Path.home()))
    assert captured.value.code == "HOME_NOT_ISOLATED"
    assert captured.value.observation is ClaudeCliObservation.PROCESS_NOT_STARTED


def test_native_home_identity_comes_from_the_os_account_not_home_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    policy, _, _, _ = _policy(tmp_path / "fixture")
    trusted_home = Path(pwd.getpwuid(os.getuid()).pw_dir).resolve(strict=True)
    monkeypatch.setenv("HOME", str(tmp_path / "fixture" / "empty-home"))

    with pytest.raises(ClaudeCliProtocolError) as captured:
        compile_claude_cli_command(dataclasses.replace(policy, isolated_home=trusted_home))

    assert captured.value.code == "HOME_NOT_ISOLATED"


@pytest.mark.parametrize(
    "field,value,code",
    [
        ("prompt", "Read exactly one sealed relative file: sealed/other.txt", "PROMPT_BINDING_INVALID"),
        ("expected_result_sha256", "0" * 64, "RESULT_BINDING_INVALID"),
    ],
)
def test_compiler_rejects_prompt_or_result_not_derived_from_sealed_evidence(
    tmp_path: Path, field: str, value: str, code: str
) -> None:
    policy, _, _, _ = _policy(tmp_path)

    with pytest.raises(ClaudeCliProtocolError) as captured:
        compile_claude_cli_command(dataclasses.replace(policy, **{field: value}))

    assert captured.value.code == code
    assert captured.value.observation is ClaudeCliObservation.PROCESS_NOT_STARTED


def test_prestart_error_trace_suppresses_private_locator_context(tmp_path: Path) -> None:
    policy, _, _, _ = _policy(tmp_path)
    missing = dataclasses.replace(policy, evidence_relative_path="sealed/missing.txt")

    with pytest.raises(ClaudeCliProtocolError) as captured:
        compile_claude_cli_command(missing)

    rendered = "".join(traceback.format_exception(captured.value))
    assert str(tmp_path) not in rendered
    assert captured.value.__cause__ is None
    assert captured.value.__suppress_context__ is True


def test_spawn_boundary_revalidates_evidence_prompt_and_result_as_one_identity(tmp_path: Path) -> None:
    policy, workspace, _, _ = _policy(tmp_path)
    command = compile_claude_cli_command(policy)
    (workspace / "sealed" / "evidence.txt").write_text("drifted after compile\n", encoding="utf-8")

    with pytest.raises(ClaudeCliProtocolError) as captured:
        ClaudeCliRunner().run(command, fake_controls=_fake_controls(tmp_path))

    assert captured.value.code == "EVIDENCE_DRIFT"
    assert captured.value.observation is ClaudeCliObservation.PROCESS_NOT_STARTED
    assert captured.value.cleanup is None
    assert not (tmp_path / "fake-state.json").exists()


def test_runner_executes_sealed_reviewed_bytes_after_same_path_in_place_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    policy, workspace, head, status = _policy(tmp_path)
    copied_fake = tmp_path / "bound-fake.py"
    copied_fake.write_bytes(FAKE.read_bytes())
    copied_fake.chmod(0o700)
    command = compile_claude_cli_command(dataclasses.replace(policy, binary=copied_fake))
    monkeypatch.setattr(protocol, "_committed_fake_path", lambda: copied_fake.resolve(), raising=False)
    real_popen = subprocess.Popen
    replaced = False

    def mutate_path_then_spawn(*args: object, **kwargs: object):
        nonlocal replaced
        if not replaced:
            copied_fake.write_text(
                "#!/usr/bin/env python3\nraise SystemExit(97)\n",
                encoding="utf-8",
            )
            copied_fake.chmod(0o700)
            replaced = True
        return real_popen(*args, **kwargs)

    monkeypatch.setattr(protocol.subprocess, "Popen", mutate_path_then_spawn)

    receipt = ClaudeCliRunner().run(command, fake_controls=_fake_controls(tmp_path))

    assert replaced is True
    assert receipt.observation is ClaudeCliObservation.TERMINAL_RESULT_OBSERVED
    assert receipt.binary_sha256 == command.binary_sha256
    _assert_workspace_unchanged(workspace, head, status)


def test_preexisting_fake_state_is_refused_before_spawn_without_signalling_a_pgid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    policy, workspace, head, status = _policy(tmp_path)
    state_path = tmp_path / "fake-state.json"
    state_path.write_text(
        json.dumps(
            {
                "children": [],
                "escaped_children": [os.getpgrp()],
                "mcp_calls": 0,
                "network_attempts": 0,
                "reads": 0,
                "shells": 0,
                "starts": 0,
                "subagents": 0,
                "submissions": 0,
                "writes": 0,
            }
        ),
        encoding="utf-8",
    )
    signalled: list[tuple[int, signal.Signals]] = []

    def record_signal(pgid: int, sent_signal: signal.Signals) -> bool:
        signalled.append((pgid, sent_signal))
        return False

    monkeypatch.setattr(protocol, "_signal_group", record_signal)

    with pytest.raises(ClaudeCliProtocolError) as captured:
        ClaudeCliRunner().run(
            compile_claude_cli_command(policy),
            fake_controls=_fake_controls(tmp_path),
        )

    assert captured.value.code == "FAKE_STATE_EXISTS"
    assert captured.value.observation is ClaudeCliObservation.PROCESS_NOT_STARTED
    assert captured.value.cleanup is None
    assert signalled == []
    _assert_workspace_unchanged(workspace, head, status)


def test_escaped_group_mark_requires_exact_parent_chronology_and_live_start_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner_pid = os.getpid()
    leader_pid = runner_pid + 10_000
    escaped_pid = leader_pid + 1
    spawn_not_before_ns = time.monotonic_ns() - 10_000
    owner_started_ns = spawn_not_before_ns + 1
    run_nonce = SESSION_ID
    state = protocol._bound_fake_state(
        run_nonce=run_nonce,
        runner_pid=runner_pid,
        spawn_not_before_ns=spawn_not_before_ns,
    )
    state.update(
        {
            "owner_pid": leader_pid,
            "owner_parent_pid": runner_pid,
            "owner_started_ns": owner_started_ns,
            "escaped_children": [
                {
                    "pid": escaped_pid,
                    "pgid": escaped_pid,
                    "parent_pid": leader_pid,
                    "parent_started_ns": owner_started_ns,
                    "spawned_at_ns": owner_started_ns + 1,
                    "start_token": "stale-start-token",
                }
            ],
        }
    )
    state_path = tmp_path / "bound-state.json"
    state_path.write_text(json.dumps(state), encoding="ascii")
    descriptor = os.open(state_path, os.O_RDONLY)
    monkeypatch.setattr(
        protocol,
        "_process_identity",
        lambda pid: (pid, 1, pid, "different-live-start-token"),
    )
    try:
        groups, proven = protocol._marked_escaped_groups(
            descriptor,
            run_nonce=run_nonce,
            runner_pid=runner_pid,
            leader_pid=leader_pid,
            spawn_not_before_ns=spawn_not_before_ns,
        )
    finally:
        os.close(descriptor)

    assert groups == ()
    assert proven is False


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
    assert receipt.result_sha256 == _sha256_text(_expected_result())
    assert receipt.settings_sha256 == command.settings_sha256
    assert receipt.returncode == 0
    assert receipt.cleanup.process_group_empty is True
    assert receipt.cleanup.leader_reaped is True
    assert receipt.cleanup.marked_descendants_empty is True
    assert receipt.cleanup.reader_closed is True
    assert receipt.cleanup.scratch_empty is True
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
        ("stderr", "STDERR_NOT_EMPTY", ClaudeCliObservation.OUTCOME_UNRECONCILED),
        ("invalid_utf8", "STDOUT_UTF8_INVALID", ClaudeCliObservation.OUTCOME_UNRECONCILED),
        ("malformed_json", "STREAM_JSON_INVALID", ClaudeCliObservation.OUTCOME_UNRECONCILED),
        ("duplicate_key", "STREAM_JSON_DUPLICATE_KEY", ClaudeCliObservation.OUTCOME_UNRECONCILED),
        ("oversized_line", "STREAM_LINE_LIMIT", ClaudeCliObservation.OUTCOME_UNRECONCILED),
        ("excessive_depth", "STREAM_JSON_DEPTH", ClaudeCliObservation.OUTCOME_UNRECONCILED),
        ("excessive_string", "STREAM_JSON_STRING", ClaudeCliObservation.OUTCOME_UNRECONCILED),
        ("excessive_collection", "STREAM_JSON_COLLECTION", ClaudeCliObservation.OUTCOME_UNRECONCILED),
        ("too_many_events", "STREAM_EVENT_LIMIT", ClaudeCliObservation.OUTCOME_UNRECONCILED),
        ("pre_init_hook", "INIT_NOT_FIRST", ClaudeCliObservation.OUTCOME_UNRECONCILED),
        ("api_retry", "PROVIDER_RETRY_OBSERVED", ClaudeCliObservation.OUTCOME_UNRECONCILED),
        ("unknown_event", "EVENT_UNKNOWN", ClaudeCliObservation.OUTCOME_UNRECONCILED),
        ("init_model_drift", "MODEL_DRIFT", ClaudeCliObservation.OUTCOME_UNRECONCILED),
        ("init_session_drift", "SESSION_DRIFT", ClaudeCliObservation.OUTCOME_UNRECONCILED),
        ("init_tools_extra", "TOOL_SET_DRIFT", ClaudeCliObservation.OUTCOME_UNRECONCILED),
        ("init_end_conversation", "TOOL_SET_DRIFT", ClaudeCliObservation.OUTCOME_UNRECONCILED),
        ("init_mcp", "MCP_OBSERVED", ClaudeCliObservation.OUTCOME_UNRECONCILED),
        ("init_plugin", "PLUGIN_OBSERVED", ClaudeCliObservation.OUTCOME_UNRECONCILED),
        ("init_required_field_missing", "INIT_INVALID", ClaudeCliObservation.OUTCOME_UNRECONCILED),
        ("init_cwd_drift", "WORKING_DIRECTORY_DRIFT", ClaudeCliObservation.OUTCOME_UNRECONCILED),
        ("init_version_drift", "VERSION_DRIFT", ClaudeCliObservation.OUTCOME_UNRECONCILED),
        ("assistant_parent_tool", "SUBAGENT_OBSERVED", ClaudeCliObservation.OUTCOME_UNRECONCILED),
        ("assistant_write_tool", "TOOL_UNAUTHORIZED", ClaudeCliObservation.OUTCOME_UNRECONCILED),
        ("read_wrong_file", "READ_SCOPE_DRIFT", ClaudeCliObservation.OUTCOME_UNRECONCILED),
        ("duplicate_tool", "READ_COUNT_INVALID", ClaudeCliObservation.OUTCOME_UNRECONCILED),
        ("tool_result_mismatch", "TOOL_RESULT_MISMATCH", ClaudeCliObservation.OUTCOME_UNRECONCILED),
        ("tool_result_unnumbered", "TOOL_RESULT_INVALID", ClaudeCliObservation.OUTCOME_UNRECONCILED),
        ("tool_result_structured_missing", "TOOL_RESULT_INVALID", ClaudeCliObservation.OUTCOME_UNRECONCILED),
        ("tool_result_structured_mismatch", "TOOL_RESULT_MISMATCH", ClaudeCliObservation.OUTCOME_UNRECONCILED),
        ("permission_denied", "PERMISSION_DENIED", ClaudeCliObservation.OUTCOME_UNRECONCILED),
        ("missing_result", "TERMINAL_RESULT_MISSING", ClaudeCliObservation.OUTCOME_UNRECONCILED),
        ("duplicate_result", "TERMINAL_RESULT_DUPLICATE", ClaudeCliObservation.OUTCOME_UNRECONCILED),
        ("post_result", "POST_TERMINAL_EVENT", ClaudeCliObservation.OUTCOME_UNRECONCILED),
        ("result_session_drift", "SESSION_DRIFT", ClaudeCliObservation.OUTCOME_UNRECONCILED),
        ("result_failure", "PROVIDER_FAILURE", ClaudeCliObservation.TERMINAL_PROVIDER_FAILURE_OBSERVED),
        ("result_permission_denial", "PERMISSION_DENIED", ClaudeCliObservation.TERMINAL_PROVIDER_FAILURE_OBSERVED),
        ("result_mismatch", "STRUCTURED_RESULT_MISMATCH", ClaudeCliObservation.OUTCOME_UNRECONCILED),
        ("result_invalid_cost", "USAGE_INVALID", ClaudeCliObservation.OUTCOME_UNRECONCILED),
        ("result_stop_reason_missing", "RESULT_INVALID", ClaudeCliObservation.OUTCOME_UNRECONCILED),
        ("result_usage_sparse", "USAGE_INVALID", ClaudeCliObservation.OUTCOME_UNRECONCILED),
        ("nonzero_after_success", "PROCESS_EXIT_INVALID", ClaudeCliObservation.OUTCOME_UNRECONCILED),
        ("secret_output", "SENSITIVE_OUTPUT", ClaudeCliObservation.OUTCOME_UNRECONCILED),
        ("private_path_output", "PRIVATE_LOCATOR_OUTPUT", ClaudeCliObservation.OUTCOME_UNRECONCILED),
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
    assert error.cleanup.marked_descendants_empty is True
    assert error.cleanup.reader_closed is True
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
        idle_timeout_seconds=4.0,
        absolute_timeout_seconds=5.0,
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


def test_descendant_after_terminal_result_prevents_success(tmp_path: Path) -> None:
    policy, workspace, head, status = _policy(
        tmp_path,
        idle_timeout_seconds=2.0,
        absolute_timeout_seconds=3.0,
    )
    state = tmp_path / "fake-state.json"
    with pytest.raises(ClaudeCliProtocolError) as captured:
        ClaudeCliRunner().run(
            compile_claude_cli_command(policy),
            fake_controls=_fake_controls(tmp_path, "child_after_result"),
        )
    error = captured.value
    assert error.code == "PROCESS_RESIDUE_OBSERVED"
    assert error.observation is ClaudeCliObservation.OUTCOME_UNRECONCILED
    assert error.cleanup is not None
    assert error.cleanup.process_group_empty is True
    assert error.cleanup.leader_reaped is True
    assert error.cleanup.term_sent or error.cleanup.kill_sent
    assert error.cleanup.residue_rows == ()
    payload = json.loads(state.read_text(encoding="utf-8"))
    for child_pid in payload["children"]:
        with pytest.raises(ProcessLookupError):
            os.kill(child_pid, 0)
    _assert_workspace_unchanged(workspace, head, status)


def test_escaped_descendant_after_terminal_result_is_killed_and_never_accepted(
    tmp_path: Path,
) -> None:
    policy, workspace, head, status = _policy(tmp_path)
    state = tmp_path / "fake-state.json"

    with pytest.raises(ClaudeCliProtocolError) as captured:
        ClaudeCliRunner().run(
            compile_claude_cli_command(policy),
            fake_controls=_fake_controls(tmp_path, "escaped_child_after_result"),
        )

    error = captured.value
    assert error.code == "PROCESS_RESIDUE_OBSERVED"
    assert error.observation is ClaudeCliObservation.OUTCOME_UNRECONCILED
    assert error.cleanup is not None
    assert error.cleanup.marked_descendants_empty is True
    payload = json.loads(state.read_text(encoding="utf-8"))
    for child_record in payload["escaped_children"]:
        child_pid = child_record["pid"]
        assert child_record["pgid"] == child_pid
        assert child_record["parent_pid"] == payload["owner_pid"]
        assert child_record["parent_started_ns"] == payload["owner_started_ns"]
        assert child_record["spawned_at_ns"] >= payload["owner_started_ns"]
        assert child_record["start_token"]
        with pytest.raises(ProcessLookupError):
            os.kill(child_pid, 0)
    _assert_workspace_unchanged(workspace, head, status)


def test_getpgid_failure_still_terminates_the_candidate_group_and_reaps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    policy, workspace, head, status = _policy(tmp_path, absolute_timeout_seconds=3.0)
    state = tmp_path / "fake-state.json"

    def fail_after_child_started(pid: int) -> int:
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            if state.exists() and json.loads(state.read_text(encoding="utf-8"))["children"]:
                raise OSError("private locator must not escape")
            time.sleep(0.01)
        raise OSError("bounded group lookup failure")

    monkeypatch.setattr(protocol.os, "getpgid", fail_after_child_started)
    with pytest.raises(ClaudeCliProtocolError) as captured:
        ClaudeCliRunner().run(
            compile_claude_cli_command(policy),
            fake_controls=_fake_controls(tmp_path, "child_hang"),
        )

    error = captured.value
    assert error.code == "PROCESS_GROUP_UNPROVEN"
    assert error.observation is ClaudeCliObservation.OUTCOME_UNRECONCILED
    assert error.cleanup is not None
    assert error.cleanup.process_group_empty is True
    assert error.cleanup.leader_reaped is True
    assert "private locator" not in "".join(traceback.format_exception(error))
    for child_pid in json.loads(state.read_text(encoding="utf-8"))["children"]:
        with pytest.raises(ProcessLookupError):
            os.kill(child_pid, 0)
    _assert_workspace_unchanged(workspace, head, status)


def test_unexpected_post_spawn_exception_is_contained_and_redacted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    policy, workspace, head, status = _policy(tmp_path)

    def explode(_self: object, _line: bytes) -> None:
        raise RuntimeError(f"private={tmp_path}")

    monkeypatch.setattr(protocol._StreamParser, "consume", explode)
    with pytest.raises(ClaudeCliProtocolError) as captured:
        ClaudeCliRunner().run(
            compile_claude_cli_command(policy),
            fake_controls=_fake_controls(tmp_path),
        )

    error = captured.value
    assert error.code == "PROCESS_OBSERVATION_FAILED"
    assert error.observation is ClaudeCliObservation.OUTCOME_UNRECONCILED
    assert error.cleanup is not None
    assert error.cleanup.process_group_empty is True
    assert error.cleanup.leader_reaped is True
    assert str(tmp_path) not in "".join(traceback.format_exception(error))
    _assert_workspace_unchanged(workspace, head, status)


def test_scratch_residue_prevents_success_and_is_reported_without_a_locator(tmp_path: Path) -> None:
    policy, workspace, head, status = _policy(tmp_path)

    with pytest.raises(ClaudeCliProtocolError) as captured:
        ClaudeCliRunner().run(
            compile_claude_cli_command(policy),
            fake_controls=_fake_controls(tmp_path, "scratch_residue"),
        )

    error = captured.value
    assert error.code == "PROCESS_RESIDUE_UNPROVEN"
    assert error.cleanup is not None
    assert error.cleanup.scratch_empty is False
    assert error.cleanup.residue_rows == ("SCRATCH_RESIDUE",)
    assert str(tmp_path) not in json.dumps(error.cleanup.to_dict(), sort_keys=True)
    _assert_workspace_unchanged(workspace, head, status)


def test_managed_policy_override_can_never_reach_result_acceptance(tmp_path: Path) -> None:
    policy, workspace, head, status = _policy(tmp_path)
    controls = _fake_controls(tmp_path)
    controls["MMX_FAKE_CLAUDE_MANAGED_SETTINGS"] = '{"hooks":{"PreToolUse":[{"command":"bad"}]}}'

    with pytest.raises(ClaudeCliProtocolError) as captured:
        ClaudeCliRunner().run(compile_claude_cli_command(policy), fake_controls=controls)

    assert captured.value.code == "MANAGED_POLICY_OBSERVED"
    assert captured.value.observation is ClaudeCliObservation.OUTCOME_UNRECONCILED
    state = json.loads((tmp_path / "fake-state.json").read_text(encoding="utf-8"))
    assert state["starts"] == 1
    assert state["reads"] == 0
    assert state["submissions"] == 0
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
    with pytest.raises(ClaudeCliProtocolError, match="fake-only") as captured:
        ClaudeCliRunner().run(command)
    assert captured.value.code == "FAKE_ONLY_EFFECT_CEILING"
    assert captured.value.observation is ClaudeCliObservation.PROCESS_NOT_STARTED

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
