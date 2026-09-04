#!/usr/bin/env python3
"""Deterministic, credential-free Claude CLI protocol fake for PF1 tests.

This executable deliberately implements only the frozen one-turn, one-Read
surface.  It never imports a Claude SDK, opens a socket, calls a model, reads a
credential store, invokes a shell, or writes inside the sealed workspace.
"""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path, PurePosixPath
from typing import Any


_RESULT = '{"decision":"HOLD","reason":"sealed fixture"}'
_VERSIONS = {"2.1.248", "2.1.259"}
_MODEL = re.compile(r"claude-(?:opus|sonnet|haiku)-[1-9][0-9]*(?:-[0-9]+)+(?:-[0-9]{8})?\Z")
_BASE_ENV = {
    "HOME",
    "TMPDIR",
    "PATH",
    "LANG",
    "LC_ALL",
    "TZ",
    "CLAUDE_CODE_MAX_RETRIES",
    "MAX_STRUCTURED_OUTPUT_RETRIES",
    "CLAUDE_CODE_MAX_TOOL_USE_CONCURRENCY",
    "API_TIMEOUT_MS",
    "CLAUDE_CODE_SKIP_PROMPT_HISTORY",
    "IS_DEMO",
}
_FAKE_ENV = {
    "MMX_FAKE_CLAUDE_SCENARIO",
    "MMX_FAKE_CLAUDE_STATE_FILE",
    "MMX_FAKE_CLAUDE_VERSION",
    "MMX_FAKE_CLAUDE_MAX_STARTS",
}
_FORBIDDEN_ENV_PREFIXES = (
    "ANTHROPIC_",
    "AWS_",
    "AZURE_",
    "GOOGLE_",
    "GCP_",
    "CLAUDE_CONFIG_",
    "CLAUDE_REMOTE_",
)
_FORBIDDEN_ENV_NAMES = {
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "NO_PROXY",
    "CLOUDSDK_CONFIG",
    "KUBECONFIG",
}
_DARWIN_PYTHON_LAUNCHER_ENV = frozenset(
    {
        "__CF_USER_TEXT_ENCODING",
        "SDKROOT",
        "CPATH",
        "LIBRARY_PATH",
        "MANPATH",
    }
)


def _reject(kind: str, code: int) -> None:
    sys.stderr.write(f"fake claude: {kind} rejected\n")
    raise SystemExit(code)


def _version() -> str:
    value = os.environ.get("MMX_FAKE_CLAUDE_VERSION", "2.1.259")
    if value not in _VERSIONS:
        _reject("environment", 65)
    return value


def _validate_environment(state_path: Path) -> None:
    # Apple's /usr/bin/python3 developer-tool shim injects this fixed compiler
    # environment after exec.  It is not inherited from the caller and the
    # fake consumes none of it; remove it before asserting the reviewed child
    # environment.  Real Claude launches do not pass through this Python shim.
    if sys.platform == "darwin":
        for name in _DARWIN_PYTHON_LAUNCHER_ENV:
            os.environ.pop(name, None)
    names = set(os.environ)
    if names - _BASE_ENV - _FAKE_ENV:
        _reject("environment", 65)
    if any(
        name in _FORBIDDEN_ENV_NAMES
        or any(name.startswith(prefix) for prefix in _FORBIDDEN_ENV_PREFIXES)
        for name in names
    ):
        _reject("environment", 65)
    required = {
        "PATH": "/usr/bin:/bin",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "TZ": "UTC",
        "CLAUDE_CODE_MAX_RETRIES": "0",
        "MAX_STRUCTURED_OUTPUT_RETRIES": "0",
        "CLAUDE_CODE_MAX_TOOL_USE_CONCURRENCY": "1",
        "CLAUDE_CODE_SKIP_PROMPT_HISTORY": "1",
        "IS_DEMO": "1",
    }
    if any(os.environ.get(key) != value for key, value in required.items()):
        _reject("environment", 65)
    api_timeout = os.environ.get("API_TIMEOUT_MS", "")
    if not api_timeout.isascii() or not api_timeout.isdigit() or not 100 <= int(api_timeout) <= 600_000:
        _reject("environment", 65)
    try:
        home = Path(os.environ["HOME"]).resolve(strict=True)
        scratch = Path(os.environ["TMPDIR"]).resolve(strict=True)
        state_parent = state_path.parent.resolve(strict=True)
    except (KeyError, OSError):
        _reject("environment", 65)
    if (
        not home.is_dir()
        or not scratch.is_dir()
        or home.parent != state_parent
        or scratch.parent != state_parent
        or home == scratch
        or str(home).startswith(("/Users/", "/home/")) and home.parent != state_parent
    ):
        _reject("environment", 65)


def _safe_relative_path(value: str) -> bool:
    path = PurePosixPath(value)
    return (
        bool(value)
        and not path.is_absolute()
        and ".." not in path.parts
        and "." not in path.parts
        and len(value.encode("utf-8")) <= 256
        and all(part and not part.startswith(".") for part in path.parts)
    )


def _parse_invocation(version: str) -> tuple[str, str, str, str]:
    args = sys.argv[1:]
    if len(args) < 2:
        _reject("invocation", 64)
    prompt = args[-1]
    match = re.fullmatch(
        r"Read only ([A-Za-z0-9][A-Za-z0-9._/-]*).+",
        prompt,
        flags=re.DOTALL,
    )
    if not match or len(prompt.encode("utf-8")) > 8_192:
        _reject("invocation", 64)
    evidence_path = match.group(1).rstrip(".,;:")
    if not _safe_relative_path(evidence_path):
        _reject("invocation", 64)
    try:
        model = args[args.index("--model") + 1]
        session_id = args[args.index("--session-id") + 1]
        uuid.UUID(session_id)
    except (ValueError, IndexError):
        _reject("invocation", 64)
    if not _MODEL.fullmatch(model):
        _reject("invocation", 64)
    expected = [
        "--restricted",
        "--safe-mode",
        "-p",
        "--output-format",
        "stream-json",
        "--verbose",
        "--model",
        model,
        "--session-id",
        session_id,
        "--permission-mode",
        "dontAsk",
    ]
    if version >= "2.1.259":
        expected.extend(["--permission-prompts", "none"])
    expected.extend(
        [
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
            prompt,
        ]
    )
    if args != expected:
        _reject("invocation", 64)
    return model, session_id, evidence_path, prompt


def _empty_state() -> dict[str, Any]:
    return {
        "children": [],
        "mcp_calls": 0,
        "network_attempts": 0,
        "reads": 0,
        "shells": 0,
        "starts": 0,
        "subagents": 0,
        "submissions": 0,
        "writes": 0,
    }


def _read_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return _empty_state()
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        _reject("state", 74)
    if not isinstance(value, dict) or set(value) != set(_empty_state()):
        _reject("state", 74)
    return value


def _write_state(path: Path, state: dict[str, Any]) -> None:
    encoded = (json.dumps(state, sort_keys=True, separators=(",", ":")) + "\n").encode()
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(descriptor, encoded)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.replace(temporary, path)


def _event(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _emit(value: dict[str, Any]) -> None:
    sys.stdout.buffer.write(_event(value))
    sys.stdout.buffer.flush()


def _canonical_events(
    *, model: str, session_id: str, evidence_path: str, evidence: str
) -> list[dict[str, Any]]:
    return [
        {
            "type": "system",
            "subtype": "init",
            "session_id": session_id,
            "model": model,
            "tools": ["Read"],
            "mcp_servers": [],
            "plugins": [],
            "permissionMode": "dontAsk",
            "capabilities": [],
        },
        {
            "type": "assistant",
            "session_id": session_id,
            "parent_tool_use_id": None,
            "message": {
                "role": "assistant",
                "model": model,
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_fixture_read",
                        "name": "Read",
                        "input": {"file_path": evidence_path},
                    }
                ],
            },
        },
        {
            "type": "user",
            "session_id": session_id,
            "parent_tool_use_id": None,
            "message": {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_fixture_read",
                        "content": evidence,
                        "is_error": False,
                    }
                ],
            },
        },
        {
            "type": "assistant",
            "session_id": session_id,
            "parent_tool_use_id": None,
            "message": {
                "role": "assistant",
                "model": model,
                "content": [{"type": "text", "text": _RESULT}],
            },
        },
        {
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "duration_ms": 25,
            "duration_api_ms": 10,
            "num_turns": 1,
            "result": _RESULT,
            "session_id": session_id,
            "total_cost_usd": 0.001,
            "usage": {"input_tokens": 11, "output_tokens": 7},
            "permission_denials": [],
        },
    ]


def _hang() -> None:
    while True:
        time.sleep(60)


def _main() -> int:
    version = _version()
    if sys.argv[1:] == ["--version"]:
        sys.stdout.write(f"{version} (Claude Code)\n")
        return 0

    state_value = os.environ.get("MMX_FAKE_CLAUDE_STATE_FILE", "")
    if not state_value or "\x00" in state_value:
        _reject("environment", 65)
    state_path = Path(state_value)
    if not state_path.is_absolute() or not state_path.parent.is_dir():
        _reject("environment", 65)
    _validate_environment(state_path)
    model, session_id, evidence_relative, _ = _parse_invocation(version)

    state = _read_state(state_path)
    state["starts"] += 1
    _write_state(state_path, state)
    maximum_starts = os.environ.get("MMX_FAKE_CLAUDE_MAX_STARTS")
    if maximum_starts is not None:
        if not maximum_starts.isascii() or not maximum_starts.isdigit() or int(maximum_starts) < 1:
            _reject("environment", 65)
        if state["starts"] > int(maximum_starts):
            sys.stderr.write("fake claude: second start refused\n")
            return 73

    scenario = os.environ.get("MMX_FAKE_CLAUDE_SCENARIO", "ok")
    workspace = Path.cwd().resolve(strict=True)
    evidence_path = workspace.joinpath(*PurePosixPath(evidence_relative).parts)
    try:
        resolved_evidence = evidence_path.resolve(strict=True)
        if workspace not in resolved_evidence.parents or evidence_path.is_symlink():
            _reject("invocation", 64)
        evidence = resolved_evidence.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        _reject("invocation", 64)
    if len(evidence.encode("utf-8")) > 65_536:
        _reject("invocation", 64)
    state["reads"] += 1
    state["submissions"] += 1
    _write_state(state_path, state)

    events = _canonical_events(
        model=model,
        session_id=session_id,
        evidence_path=evidence_relative,
        evidence=evidence,
    )

    if scenario == "hang_before_output":
        _hang()
    if scenario in {"child_hang", "child_ignore_term"}:
        signal.signal(signal.SIGCHLD, signal.SIG_IGN)
        child_code = "import time; time.sleep(60)"
        if scenario == "child_ignore_term":
            child_code = (
                "import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); "
                "time.sleep(60)"
            )
        child = subprocess.Popen(
            ["/usr/bin/python3", "-c", child_code],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
        )
        state["children"] = [child.pid]
        _write_state(state_path, state)
        for event in events[:3]:
            _emit(event)
        _hang()
    if scenario == "hang_after_tool":
        for event in events[:3]:
            _emit(event)
        _hang()
    if scenario == "stderr":
        sys.stderr.write("bounded fake diagnostic\n")
        sys.stderr.flush()
    elif scenario == "invalid_utf8":
        sys.stdout.buffer.write(b"\xff\xfe\n")
        sys.stdout.buffer.flush()
        return 0
    elif scenario == "malformed_json":
        sys.stdout.write("{not-json}\n")
        sys.stdout.flush()
        return 0
    elif scenario == "duplicate_key":
        sys.stdout.write(
            '{"type":"system","type":"system","subtype":"init","session_id":"x"}\n'
        )
        sys.stdout.flush()
        return 0
    elif scenario == "oversized_line":
        sys.stdout.write(json.dumps({"type": "system", "subtype": "init", "padding": "x" * 40_000}) + "\n")
        sys.stdout.flush()
        return 0
    elif scenario == "oversized_total":
        for _ in range(256):
            sys.stdout.buffer.write(_event({"type": "system", "subtype": "usage", "session_id": session_id, "usage": {"input_tokens": 1, "output_tokens": 1}, "padding": "x" * 256}))
        sys.stdout.buffer.flush()
        _hang()
    elif scenario == "excessive_depth":
        value: Any = "leaf"
        for _ in range(12):
            value = {"nested": value}
        event = dict(events[0])
        event["nested"] = value
        _emit(event)
        return 0
    elif scenario == "excessive_string":
        event = dict(events[0])
        event["padding"] = "x" * 9_000
        _emit(event)
        return 0
    elif scenario == "excessive_collection":
        event = dict(events[0])
        event["capabilities"] = [f"cap-{index}" for index in range(65)]
        _emit(event)
        return 0
    elif scenario == "too_many_events":
        _emit(events[0])
        for _ in range(17):
            _emit(
                {
                    "type": "system",
                    "subtype": "usage",
                    "session_id": session_id,
                    "usage": {"input_tokens": 1, "output_tokens": 1},
                }
            )
        return 0
    elif scenario == "pre_init_hook":
        _emit({"type": "system", "subtype": "hook_started", "session_id": session_id})
        return 0
    elif scenario == "api_retry":
        _emit(events[0])
        _emit(
            {
                "type": "system",
                "subtype": "api_retry",
                "attempt": 1,
                "max_retries": 1,
                "session_id": session_id,
            }
        )
        return 0
    elif scenario == "unknown_event":
        _emit(events[0])
        _emit({"type": "mystery", "session_id": session_id})
        return 0
    elif scenario == "init_model_drift":
        events[0]["model"] = "claude-sonnet-4-6"
    elif scenario == "init_session_drift":
        events[0]["session_id"] = "00000000-0000-4000-8000-000000000000"
    elif scenario == "init_tools_extra":
        events[0]["tools"] = ["Read", "Bash"]
    elif scenario == "init_mcp":
        events[0]["mcp_servers"] = [{"name": "bad", "status": "connected"}]
    elif scenario == "init_plugin":
        events[0]["plugins"] = [{"name": "bad", "path": "/private/plugin"}]
    elif scenario == "assistant_parent_tool":
        events[1]["parent_tool_use_id"] = "toolu_parent"
    elif scenario == "assistant_write_tool":
        events[1]["message"]["content"][0]["name"] = "Write"
    elif scenario == "read_wrong_file":
        events[1]["message"]["content"][0]["input"]["file_path"] = "sealed/other.txt"
    elif scenario == "duplicate_tool":
        events.insert(2, json.loads(json.dumps(events[1])))
    elif scenario == "tool_result_mismatch":
        events[2]["message"]["content"][0]["tool_use_id"] = "toolu_other"
    elif scenario == "permission_denied":
        events.insert(
            3,
            {
                "type": "system",
                "subtype": "permission_denied",
                "session_id": session_id,
                "tool_name": "Read",
            },
        )
    elif scenario == "missing_result":
        events = events[:-1]
    elif scenario == "duplicate_result":
        events.append(json.loads(json.dumps(events[-1])))
    elif scenario == "post_result":
        events.append({"type": "system", "subtype": "usage", "session_id": session_id, "usage": {"input_tokens": 1, "output_tokens": 1}})
    elif scenario == "result_session_drift":
        events[-1]["session_id"] = "00000000-0000-4000-8000-000000000000"
    elif scenario == "result_failure":
        events[-1].update(
            {
                "subtype": "error_during_execution",
                "is_error": True,
                "result": "bounded provider failure",
            }
        )
    elif scenario == "result_permission_denial":
        events[-1].update(
            {
                "subtype": "error_during_execution",
                "is_error": True,
                "permission_denials": [{"tool_name": "Read"}],
            }
        )
    elif scenario == "result_mismatch":
        events[3]["message"]["content"][0]["text"] = '{"decision":"BUY"}'
        events[-1]["result"] = '{"decision":"BUY"}'
    elif scenario == "result_invalid_cost":
        events[-1]["total_cost_usd"] = -1
    elif scenario == "secret_output":
        events[0]["capabilities"] = ["sk-ant-FAKE_SENTINEL_NOT_A_SECRET"]
    elif scenario == "private_path_output":
        events[0]["capabilities"] = ["/Users/example/private"]
    elif scenario not in {"ok", "nonzero_after_success"}:
        _reject("scenario", 75)

    for event in events:
        _emit(event)
    return 7 if scenario == "nonzero_after_success" else 0


if __name__ == "__main__":
    raise SystemExit(_main())
