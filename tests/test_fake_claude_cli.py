"""Executable contract tests for the deterministic PF1 Claude CLI fake."""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import signal
import subprocess
import time
from pathlib import Path

import pytest

from control_plane.claude_cli_protocol import (
    ClaudeCliInvocationPolicy,
    ClaudeCliVersion,
    compile_claude_cli_command,
)


ROOT = Path(__file__).resolve().parents[1]
FAKE = ROOT / "scripts" / "ohf" / "fake_claude_cli.py"
SESSION_ID = "550e8400-e29b-41d4-a716-446655440000"
EVIDENCE = "bounded evidence\n"


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _expected_result(evidence: str = EVIDENCE) -> str:
    return json.dumps(
        {"decision": "HOLD", "evidence_sha256": _sha256_text(evidence)},
        sort_keys=True,
        separators=(",", ":"),
    )


def _expected_prompt(path: str = "sealed/evidence.txt", evidence: str = EVIDENCE) -> str:
    return (
        f"Read exactly one sealed relative file: {path}\n"
        f"Expected SHA-256: {_sha256_text(evidence)}\n"
        f"Return exactly: {_expected_result(evidence)}\n"
        "Do not perform any other action."
    )


def _run(
    argv: tuple[str, ...] | list[str],
    *,
    cwd: Path,
    environment: dict[str, str],
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        argv,
        cwd=cwd,
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=3,
    )


def _command(tmp_path: Path, *, version: str = "2.1.259"):
    workspace = tmp_path / "workspace"
    home = tmp_path / "home"
    scratch = tmp_path / "tmp"
    (workspace / "sealed").mkdir(parents=True, mode=0o700)
    home.mkdir(mode=0o700)
    scratch.mkdir(mode=0o700)
    (workspace / "sealed" / "evidence.txt").write_text(EVIDENCE, encoding="utf-8")
    policy = ClaudeCliInvocationPolicy(
        binary=FAKE.resolve(),
        version=ClaudeCliVersion.parse(version),
        model="claude-opus-4-6",
        session_id=SESSION_ID,
        prompt=_expected_prompt(),
        working_directory=workspace,
        isolated_home=home,
        isolated_tmp=scratch,
        evidence_relative_path="sealed/evidence.txt",
        expected_result_sha256=_sha256_text(_expected_result()),
        api_timeout_ms=1_000,
        idle_timeout_seconds=1.0,
        absolute_timeout_seconds=2.0,
        terminate_grace_seconds=0.1,
        max_stdout_bytes=131_072,
        max_stderr_bytes=4_096,
        max_line_bytes=32_768,
        max_events=16,
        max_json_depth=8,
        max_json_string_bytes=8_192,
        max_json_collection_items=64,
    )
    return compile_claude_cli_command(policy)


def _environment(command, tmp_path: Path, **updates: str) -> dict[str, str]:
    values = dict(command.environment)
    values.update(
        {
            "MMX_FAKE_CLAUDE_SCENARIO": "ok",
            "MMX_FAKE_CLAUDE_STATE_FILE": str(tmp_path / "state.json"),
            "MMX_FAKE_CLAUDE_VERSION": "2.1.259",
        }
    )
    values.update(updates)
    return values


@pytest.mark.parametrize("version", ["2.1.248", "2.1.259"])
def test_version_probe_is_deterministic_and_side_effect_free(tmp_path: Path, version: str) -> None:
    before = {entry.name for entry in tmp_path.iterdir()}
    completed = _run(
        [str(FAKE), "--version"],
        cwd=tmp_path,
        environment={
            "PATH": "/usr/bin:/bin",
            "LANG": "C.UTF-8",
            "MMX_FAKE_CLAUDE_VERSION": version,
        },
    )
    assert completed.returncode == 0
    assert completed.stdout == f"{version} (Claude Code)\n".encode()
    assert completed.stderr == b""
    assert {entry.name for entry in tmp_path.iterdir()} == before


def test_exact_compiled_command_emits_canonical_stream_and_counters(tmp_path: Path) -> None:
    command = _command(tmp_path)
    completed = _run(
        command.argv,
        cwd=Path(command.working_directory),
        environment=_environment(command, tmp_path),
    )
    assert completed.returncode == 0, completed.stderr.decode(errors="replace")
    assert completed.stderr == b""
    events = [json.loads(line) for line in completed.stdout.splitlines()]
    assert [(event["type"], event.get("subtype")) for event in events] == [
        ("system", "init"),
        ("assistant", None),
        ("user", None),
        ("assistant", None),
        ("result", "success"),
    ]
    assert events[0]["tools"] == ["Read"]
    assert events[0]["mcp_servers"] == []
    assert events[0]["plugins"] == []
    assert "EndConversation" not in events[0]["tools"]
    assert events[-1]["session_id"] == SESSION_ID
    assert events[-1]["result"] == _expected_result()
    state = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert state == {
        "children": [],
        "escaped_children": [],
        "mcp_calls": 0,
        "network_attempts": 0,
        "reads": 1,
        "shells": 0,
        "starts": 1,
        "subagents": 0,
        "submissions": 1,
        "writes": 0,
    }


@pytest.mark.parametrize(
    "mutation",
    [
        "remove_restricted",
        "swap_safe_mode",
        "remove_print",
        "change_format",
        "remove_verbose",
        "alias_model",
        "bad_session",
        "permission_auto",
        "permission_prompts_ask",
        "tools_default",
        "allow_edit",
        "drop_mcp_deny",
        "nonempty_mcp",
        "drop_strict_mcp",
        "drop_slash_disable",
        "enable_chrome",
        "persist_session",
        "two_turns",
        "settings_file",
        "settings_drop_hook_guard",
        "settings_expand_permissions",
        "prompt_path_mismatch",
        "extra_flag",
    ],
)
def test_each_canonical_argv_guard_detects_a_mutation(tmp_path: Path, mutation: str) -> None:
    command = _command(tmp_path)
    argv = list(command.argv)

    def remove_pair(flag: str) -> None:
        index = argv.index(flag)
        del argv[index : index + 2]

    if mutation == "remove_restricted":
        argv.remove("--restricted")
    elif mutation == "swap_safe_mode":
        argv[argv.index("--safe-mode")] = "--bare"
    elif mutation == "remove_print":
        argv.remove("-p")
    elif mutation == "change_format":
        argv[argv.index("stream-json")] = "json"
    elif mutation == "remove_verbose":
        argv.remove("--verbose")
    elif mutation == "alias_model":
        argv[argv.index("claude-opus-4-6")] = "opus"
    elif mutation == "bad_session":
        argv[argv.index(SESSION_ID)] = "bad-session"
    elif mutation == "permission_auto":
        index = argv.index("--permission-mode")
        argv[index + 1] = "auto"
    elif mutation == "permission_prompts_ask":
        index = argv.index("--permission-prompts")
        argv[index + 1] = "ask"
    elif mutation == "tools_default":
        index = argv.index("--tools")
        argv[index + 1] = "default"
    elif mutation == "allow_edit":
        index = argv.index("--allowedTools")
        argv[index + 1] = "Read,Edit"
    elif mutation == "drop_mcp_deny":
        remove_pair("--disallowedTools")
    elif mutation == "nonempty_mcp":
        argv[argv.index('{"mcpServers":{}}')] = '{"mcpServers":{"bad":{}}}'
    elif mutation == "drop_strict_mcp":
        argv.remove("--strict-mcp-config")
    elif mutation == "drop_slash_disable":
        argv.remove("--disable-slash-commands")
    elif mutation == "enable_chrome":
        argv[argv.index("--no-chrome")] = "--chrome"
    elif mutation == "persist_session":
        argv.remove("--no-session-persistence")
    elif mutation == "two_turns":
        index = argv.index("--max-turns")
        argv[index + 1] = "2"
    elif mutation == "settings_file":
        index = argv.index("--settings")
        argv[index + 1] = "/tmp/settings.json"
    elif mutation == "settings_drop_hook_guard":
        index = argv.index("--settings")
        settings = json.loads(argv[index + 1])
        del settings["disableAllHooks"]
        argv[index + 1] = json.dumps(settings, sort_keys=True, separators=(",", ":"))
    elif mutation == "settings_expand_permissions":
        index = argv.index("--settings")
        settings = json.loads(argv[index + 1])
        settings["permissions"]["allow"].append("Bash")
        argv[index + 1] = json.dumps(settings, sort_keys=True, separators=(",", ":"))
    elif mutation == "prompt_path_mismatch":
        argv[-1] = _expected_prompt("sealed/other.txt")
    elif mutation == "extra_flag":
        argv.insert(-1, "--continue")
    else:  # pragma: no cover - table exhaustiveness
        raise AssertionError(mutation)

    completed = _run(
        argv,
        cwd=Path(command.working_directory),
        environment=_environment(command, tmp_path),
    )
    assert completed.returncode == 64
    assert completed.stdout == b""
    assert completed.stderr == b"fake claude: invocation rejected\n"


@pytest.mark.parametrize(
    "key,value",
    [
        ("ANTHROPIC_API_KEY", "FAKE_SENTINEL"),
        ("ANTHROPIC_AUTH_TOKEN", "FAKE_SENTINEL"),
        ("CLAUDE_CODE_OAUTH_TOKEN", "FAKE_SENTINEL"),
        ("HTTPS_PROXY", "http://127.0.0.1:9"),
        ("AWS_ACCESS_KEY_ID", "FAKE_SENTINEL"),
        ("GOOGLE_APPLICATION_CREDENTIALS", "/tmp/fake.json"),
    ],
)
def test_fake_rejects_credential_proxy_and_cloud_environment(
    tmp_path: Path, key: str, value: str
) -> None:
    command = _command(tmp_path)
    completed = _run(
        command.argv,
        cwd=Path(command.working_directory),
        environment=_environment(command, tmp_path, **{key: value}),
    )
    assert completed.returncode == 65
    assert completed.stdout == b""
    assert completed.stderr == b"fake claude: environment rejected\n"
    assert value.encode() not in completed.stderr


def test_fake_exclusive_state_refuses_a_second_start(tmp_path: Path) -> None:
    command = _command(tmp_path)
    environment = _environment(command, tmp_path, MMX_FAKE_CLAUDE_MAX_STARTS="1")
    first = _run(command.argv, cwd=Path(command.working_directory), environment=environment)
    second = _run(command.argv, cwd=Path(command.working_directory), environment=environment)
    assert first.returncode == 0
    assert second.returncode == 73
    assert second.stdout == b""
    assert second.stderr == b"fake claude: second start refused\n"
    assert json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))["starts"] == 1


def test_fake_state_lock_refuses_a_concurrent_process_without_losing_updates(tmp_path: Path) -> None:
    command = _command(tmp_path)
    first_environment = _environment(command, tmp_path, MMX_FAKE_CLAUDE_SCENARIO="hang_before_output")
    second_environment = _environment(command, tmp_path, MMX_FAKE_CLAUDE_SCENARIO="ok")
    first = subprocess.Popen(
        command.argv,
        cwd=command.working_directory,
        env=first_environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
        close_fds=True,
    )
    try:
        state_path = tmp_path / "state.json"
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline and not state_path.exists():
            time.sleep(0.01)
        assert state_path.exists()

        second = _run(
            command.argv,
            cwd=Path(command.working_directory),
            environment=second_environment,
        )

        assert second.returncode == 73
        assert second.stdout == b""
        assert second.stderr == b"fake claude: state lock rejected\n"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        assert state["starts"] == 1
        assert state["reads"] == 1
        assert state["submissions"] == 1
    finally:
        try:
            os.killpg(first.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
        if first.poll() is None:
            first.kill()
        first.wait(timeout=2)


def test_248_fake_rejects_newer_permission_prompt_flag(tmp_path: Path) -> None:
    command = _command(tmp_path, version="2.1.248")
    assert "--permission-prompts" not in command.argv
    environment = _environment(command, tmp_path, MMX_FAKE_CLAUDE_VERSION="2.1.248")
    accepted = _run(command.argv, cwd=Path(command.working_directory), environment=environment)
    assert accepted.returncode == 0

    argv = list(command.argv)
    index = argv.index("--tools")
    argv[index:index] = ["--permission-prompts", "none"]
    rejected = _run(argv, cwd=Path(command.working_directory), environment=environment)
    assert rejected.returncode == 64


def test_policy_copy_cannot_smuggle_a_native_home(tmp_path: Path) -> None:
    command = _command(tmp_path)
    policy_env = dict(command.environment)
    policy_env["HOME"] = str(Path.home())
    smuggled = dataclasses.replace(command, environment=tuple(sorted(policy_env.items())))
    completed = _run(
        smuggled.argv,
        cwd=Path(smuggled.working_directory),
        environment=_environment(smuggled, tmp_path),
    )
    assert completed.returncode == 65
    assert completed.stdout == b""
