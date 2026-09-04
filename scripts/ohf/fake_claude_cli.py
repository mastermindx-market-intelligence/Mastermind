#!/usr/bin/env python3
"""Deterministic, credential-free Claude CLI protocol fake for PF1 tests.

This executable deliberately implements only the frozen one-turn, one-Read
surface.  It never imports a Claude SDK, opens a socket, calls a model, reads a
credential store, invokes a shell, or writes inside the sealed workspace.
"""

from __future__ import annotations

import atexit
import fcntl
import hashlib
import json
import os
import re
import signal
import stat
import subprocess
import sys
import time
import uuid
from pathlib import Path, PurePosixPath
from typing import Any


_VERSIONS = {"2.1.248", "2.1.259"}
_BOUND_STATE_SCHEMA = "mmx.fake-claude-state.v2"
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
    "MMX_FAKE_CLAUDE_MANAGED_SETTINGS",
    "MMX_FAKE_CLAUDE_STATE_FD",
    "MMX_FAKE_CLAUDE_RUN_NONCE",
    "MMX_FAKE_CLAUDE_RUNNER_PID",
    "MMX_FAKE_CLAUDE_SPAWN_NOT_BEFORE_NS",
    "MMX_FAKE_CLAUDE_EVIDENCE_FD",
    "MMX_FAKE_CLAUDE_EVIDENCE_DEVICE",
    "MMX_FAKE_CLAUDE_EVIDENCE_INODE",
    "MMX_FAKE_CLAUDE_EVIDENCE_UID",
    "MMX_FAKE_CLAUDE_EVIDENCE_MODE",
    "MMX_FAKE_CLAUDE_EVIDENCE_SIZE",
    "MMX_FAKE_CLAUDE_EVIDENCE_MTIME_NS",
}
_EVIDENCE_IDENTITY_ENV = (
    "MMX_FAKE_CLAUDE_EVIDENCE_DEVICE",
    "MMX_FAKE_CLAUDE_EVIDENCE_INODE",
    "MMX_FAKE_CLAUDE_EVIDENCE_UID",
    "MMX_FAKE_CLAUDE_EVIDENCE_MODE",
    "MMX_FAKE_CLAUDE_EVIDENCE_SIZE",
    "MMX_FAKE_CLAUDE_EVIDENCE_MTIME_NS",
)
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


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _derived_result(evidence_sha256: str) -> str:
    return _canonical_json({"decision": "HOLD", "evidence_sha256": evidence_sha256})


def _derived_prompt(evidence_relative_path: str, evidence_sha256: str) -> str:
    return (
        f"Read exactly one sealed relative file: {evidence_relative_path}\n"
        f"Expected SHA-256: {evidence_sha256}\n"
        f"Return exactly: {_derived_result(evidence_sha256)}\n"
        "Do not perform any other action."
    )


def _closed_settings_json(evidence_relative_path: str) -> str:
    return _canonical_json(
        {
            "autoMemoryEnabled": False,
            "disableAgentView": True,
            "disableAllHooks": True,
            "disableAutoMode": "disable",
            "disableDeepLinkRegistration": "disable",
            "enableAllProjectMcpServers": False,
            "enabledMcpjsonServers": [],
            "includeGitInstructions": False,
            "permissions": {
                "allow": [f"Read(./{evidence_relative_path})"],
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
    )


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
    lines = prompt.splitlines()
    if (
        len(lines) != 4
        or not lines[0].startswith("Read exactly one sealed relative file: ")
        or not lines[1].startswith("Expected SHA-256: ")
        or not lines[2].startswith("Return exactly: ")
        or lines[3] != "Do not perform any other action."
        or len(prompt.encode("utf-8")) > 8_192
    ):
        _reject("invocation", 64)
    evidence_path = lines[0].removeprefix("Read exactly one sealed relative file: ")
    declared_sha256 = lines[1].removeprefix("Expected SHA-256: ")
    declared_result = lines[2].removeprefix("Return exactly: ")
    if not _safe_relative_path(evidence_path):
        _reject("invocation", 64)
    if (
        re.fullmatch(r"[0-9a-f]{64}", declared_sha256) is None
        or declared_result != _derived_result(declared_sha256)
        or prompt != _derived_prompt(evidence_path, declared_sha256)
    ):
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
            _closed_settings_json(evidence_path),
            prompt,
        ]
    )
    if args != expected:
        _reject("invocation", 64)
    return model, session_id, evidence_path, declared_sha256


def _empty_state() -> dict[str, Any]:
    return {
        "children": [],
        "escaped_children": [],
        "mcp_calls": 0,
        "network_attempts": 0,
        "reads": 0,
        "shells": 0,
        "starts": 0,
        "subagents": 0,
        "submissions": 0,
        "writes": 0,
    }


def _read_descriptor(descriptor: int) -> bytes:
    value = os.pread(descriptor, 65_537, 0)
    if not value or len(value) > 65_536:
        _reject("state", 74)
    return value


def _read_state(path: Path, descriptor: int | None = None) -> dict[str, Any]:
    if descriptor is None and not path.exists():
        return _empty_state()
    try:
        encoded = _read_descriptor(descriptor) if descriptor is not None else path.read_bytes()
        value = json.loads(encoded.decode("ascii", errors="strict"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        _reject("state", 74)
    if not isinstance(value, dict) or (descriptor is None and set(value) != set(_empty_state())):
        _reject("state", 74)
    return value


def _write_state(path: Path, state: dict[str, Any], descriptor: int | None = None) -> None:
    encoded = (json.dumps(state, sort_keys=True, separators=(",", ":")) + "\n").encode()
    if descriptor is not None:
        try:
            os.ftruncate(descriptor, 0)
            offset = 0
            while offset < len(encoded):
                written = os.pwrite(descriptor, encoded[offset:], offset)
                if written <= 0:
                    raise OSError
                offset += written
            os.fsync(descriptor)
        except OSError:
            _reject("state", 74)
        return
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(descriptor, encoded)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.replace(temporary, path)


def _acquire_state_lock(path: Path) -> tuple[int, bool]:
    inherited = os.environ.get("MMX_FAKE_CLAUDE_STATE_FD")
    if inherited is not None:
        if not inherited.isascii() or not inherited.isdigit() or int(inherited) < 3:
            _reject("environment", 65)
        descriptor = int(inherited)
        try:
            descriptor_info = os.fstat(descriptor)
            path_info = path.stat()
            if (
                not stat.S_ISREG(descriptor_info.st_mode)
                or stat.S_IMODE(descriptor_info.st_mode) != 0o600
                or descriptor_info.st_uid != os.getuid()
                or descriptor_info.st_dev != path_info.st_dev
                or descriptor_info.st_ino != path_info.st_ino
            ):
                _reject("state", 74)
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, BlockingIOError):
            _reject("state lock", 73)
        return descriptor, True
    lock_path = path.with_name(f".{path.name}.lock")
    try:
        descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (OSError, BlockingIOError):
        try:
            os.close(descriptor)
        except (OSError, UnboundLocalError):
            pass
        _reject("state lock", 73)
    return descriptor, False


def _release_state_lock(descriptor: int) -> None:
    try:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
    finally:
        os.close(descriptor)


def _validate_bound_state(state: dict[str, Any]) -> None:
    nonce = os.environ.get("MMX_FAKE_CLAUDE_RUN_NONCE", "")
    runner_pid = os.environ.get("MMX_FAKE_CLAUDE_RUNNER_PID", "")
    spawn_ns = os.environ.get("MMX_FAKE_CLAUDE_SPAWN_NOT_BEFORE_NS", "")
    expected_keys = set(_empty_state()) | {
        "schema",
        "run_nonce",
        "runner_pid",
        "spawn_not_before_ns",
        "owner_pid",
        "owner_parent_pid",
        "owner_started_ns",
    }
    try:
        parsed_nonce = uuid.UUID(nonce)
    except (ValueError, AttributeError):
        _reject("state", 74)
    if (
        str(parsed_nonce) != nonce
        or not runner_pid.isascii()
        or not runner_pid.isdigit()
        or not spawn_ns.isascii()
        or not spawn_ns.isdigit()
        or set(state) != expected_keys
        or state.get("schema") != _BOUND_STATE_SCHEMA
        or state.get("run_nonce") != nonce
        or state.get("runner_pid") != int(runner_pid)
        or state.get("spawn_not_before_ns") != int(spawn_ns)
        or state.get("owner_pid") is not None
        or state.get("owner_parent_pid") is not None
        or state.get("owner_started_ns") is not None
        or state.get("escaped_children") != []
        or state.get("children") != []
        or any(state.get(key) != 0 for key in set(_empty_state()) - {"children", "escaped_children"})
        or os.getppid() != int(runner_pid)
    ):
        _reject("state", 74)
    owner_started_ns = time.monotonic_ns()
    if owner_started_ns < int(spawn_ns):
        _reject("state", 74)
    state["owner_pid"] = os.getpid()
    state["owner_parent_pid"] = os.getppid()
    state["owner_started_ns"] = owner_started_ns


def _read_evidence(
    *,
    workspace: Path,
    evidence_relative: str,
    declared_sha256: str,
    bound_state: bool,
    state_descriptor: int | None,
) -> tuple[Path, str, str]:
    evidence_path = workspace.joinpath(*PurePosixPath(evidence_relative).parts)
    descriptor_value = os.environ.get("MMX_FAKE_CLAUDE_EVIDENCE_FD")
    identity_values = tuple(os.environ.get(name) for name in _EVIDENCE_IDENTITY_ENV)
    try:
        path_info = evidence_path.lstat()
        resolved_evidence = evidence_path.resolve(strict=True)
        if (
            stat.S_ISLNK(path_info.st_mode)
            or not stat.S_ISREG(path_info.st_mode)
            or resolved_evidence != evidence_path
            or workspace not in resolved_evidence.parents
        ):
            raise OSError("evidence path identity invalid")
        if bound_state:
            if (
                descriptor_value is None
                or not descriptor_value.isascii()
                or not descriptor_value.isdigit()
                or int(descriptor_value) < 3
                or int(descriptor_value) == state_descriptor
                or any(
                    value is None or not value.isascii() or not value.isdigit()
                    for value in identity_values
                )
            ):
                _reject("environment", 65)
            evidence_descriptor = int(descriptor_value)
            expected_identity = tuple(int(value) for value in identity_values)
            before = os.fstat(evidence_descriptor)
            if fcntl.fcntl(evidence_descriptor, fcntl.F_GETFL) & os.O_ACCMODE != os.O_RDONLY:
                raise OSError("evidence descriptor was not read-only")
            evidence_bytes = os.pread(evidence_descriptor, 65_537, 0)
            after = os.fstat(evidence_descriptor)
            path_after = evidence_path.lstat()
            resolved_after = evidence_path.resolve(strict=True)
            before_identity = (
                before.st_dev,
                before.st_ino,
                before.st_uid,
                before.st_mode,
                before.st_size,
                before.st_mtime_ns,
            )
            after_identity = (
                after.st_dev,
                after.st_ino,
                after.st_uid,
                after.st_mode,
                after.st_size,
                after.st_mtime_ns,
            )
            path_identity = (
                path_info.st_dev,
                path_info.st_ino,
                path_info.st_uid,
                path_info.st_mode,
                path_info.st_size,
                path_info.st_mtime_ns,
            )
            path_after_identity = (
                path_after.st_dev,
                path_after.st_ino,
                path_after.st_uid,
                path_after.st_mode,
                path_after.st_size,
                path_after.st_mtime_ns,
            )
            if (
                not stat.S_ISREG(before.st_mode)
                or stat.S_ISLNK(path_after.st_mode)
                or not stat.S_ISREG(path_after.st_mode)
                or resolved_after != evidence_path
                or before_identity != expected_identity
                or after_identity != expected_identity
                or path_identity != expected_identity
                or path_after_identity != expected_identity
            ):
                raise OSError("evidence identity drifted")
        else:
            if descriptor_value is not None or any(value is not None for value in identity_values):
                _reject("environment", 65)
            evidence_bytes = resolved_evidence.read_bytes()
        if len(evidence_bytes) > 65_536:
            raise OSError("evidence exceeded its byte bound")
        evidence = evidence_bytes.decode("utf-8", errors="strict")
    except (OSError, UnicodeError):
        _reject("invocation", 64)
    evidence_sha256 = _sha256_bytes(evidence_bytes)
    if evidence_sha256 != declared_sha256:
        _reject("invocation", 64)
    return resolved_evidence, evidence, evidence_sha256


def _process_identity(pid: int) -> tuple[int, int, int, str] | None:
    ps_binary = Path("/bin/ps") if Path("/bin/ps").is_file() else Path("/usr/bin/ps")
    try:
        completed = subprocess.run(
            [str(ps_binary), "-o", "pid=,ppid=,pgid=,lstart=", "-p", str(pid)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env={"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C", "TZ": "UTC"},
            check=False,
            timeout=1.0,
            text=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    parts = completed.stdout.strip().split(maxsplit=3)
    if completed.returncode != 0 or len(parts) != 4:
        return None
    try:
        observed_pid, parent_pid, pgid = (int(part) for part in parts[:3])
    except ValueError:
        return None
    if observed_pid != pid or not parts[3]:
        return None
    return observed_pid, parent_pid, pgid, parts[3]


def _numbered_read_content(content: str) -> str:
    return "".join(
        f"{index}\t{line}"
        for index, line in enumerate(content.splitlines(keepends=True), start=1)
    )


def _event(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _emit(value: dict[str, Any]) -> None:
    sys.stdout.buffer.write(_event(value))
    sys.stdout.buffer.flush()


def _canonical_events(
    *,
    version: str,
    model: str,
    session_id: str,
    working_directory: str,
    evidence_path: str,
    evidence: str,
    result: str,
) -> list[dict[str, Any]]:
    usage = {
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
        "input_tokens": 11,
        "output_tokens": 7,
    }
    model_usage = {
        model: {
            "cacheCreationInputTokens": 0,
            "cacheReadInputTokens": 0,
            "contextWindow": 200_000,
            "costUSD": 0.001,
            "inputTokens": 11,
            "maxOutputTokens": 32_000,
            "outputTokens": 7,
            "webSearchRequests": 0,
        }
    }
    line_count = len(evidence.splitlines())
    return [
        {
            "type": "system",
            "subtype": "init",
            "apiKeySource": "none",
            "claude_code_version": version,
            "cwd": working_directory,
            "session_id": session_id,
            "model": model,
            "tools": ["Read"],
            "mcp_servers": [],
            "plugins": [],
            "permissionMode": "dontAsk",
            "slash_commands": [],
            "output_style": "default",
            "skills": [],
            "capabilities": [],
            "uuid": "11111111-1111-4111-8111-111111111111",
        },
        {
            "type": "assistant",
            "session_id": session_id,
            "parent_tool_use_id": None,
            "uuid": "22222222-2222-4222-8222-222222222222",
            "message": {
                "id": "msg_fixture_read",
                "type": "message",
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
                "stop_reason": None,
                "stop_sequence": None,
                "usage": dict(usage),
            },
        },
        {
            "type": "user",
            "session_id": session_id,
            "parent_tool_use_id": None,
            "uuid": "33333333-3333-4333-8333-333333333333",
            "message": {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_fixture_read",
                        "content": _numbered_read_content(evidence),
                        "is_error": False,
                    }
                ],
            },
            "tool_use_result": {
                "type": "text",
                "file": {
                    "filePath": evidence_path,
                    "content": evidence,
                    "numLines": line_count,
                    "startLine": 1,
                    "totalLines": line_count,
                },
            },
        },
        {
            "type": "assistant",
            "session_id": session_id,
            "parent_tool_use_id": None,
            "uuid": "44444444-4444-4444-8444-444444444444",
            "message": {
                "id": "msg_fixture_result",
                "type": "message",
                "role": "assistant",
                "model": model,
                "content": [{"type": "text", "text": result}],
                "stop_reason": None,
                "stop_sequence": None,
                "usage": dict(usage),
            },
        },
        {
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "duration_ms": 25,
            "duration_api_ms": 10,
            "num_turns": 1,
            "result": result,
            "stop_reason": "end_turn",
            "session_id": session_id,
            "total_cost_usd": 0.001,
            "usage": dict(usage),
            "modelUsage": model_usage,
            "permission_denials": [],
            "uuid": "55555555-5555-4555-8555-555555555555",
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
    model, session_id, evidence_relative, declared_sha256 = _parse_invocation(version)

    lock_descriptor, bound_state = _acquire_state_lock(state_path)
    atexit.register(_release_state_lock, lock_descriptor)
    state_descriptor = lock_descriptor if bound_state else None
    state = _read_state(state_path, state_descriptor)
    if bound_state:
        _validate_bound_state(state)
    maximum_starts = os.environ.get("MMX_FAKE_CLAUDE_MAX_STARTS")
    if maximum_starts is not None:
        if not maximum_starts.isascii() or not maximum_starts.isdigit() or int(maximum_starts) < 1:
            _reject("environment", 65)
        if state["starts"] >= int(maximum_starts):
            sys.stderr.write("fake claude: second start refused\n")
            return 73
    state["starts"] += 1
    _write_state(state_path, state, state_descriptor)

    managed_settings = os.environ.get("MMX_FAKE_CLAUDE_MANAGED_SETTINGS")
    if managed_settings is not None:
        try:
            managed_value = json.loads(managed_settings)
        except (json.JSONDecodeError, UnicodeError):
            _reject("environment", 65)
        if managed_value != {}:
            _emit(
                {
                    "type": "system",
                    "subtype": "managed_policy",
                    "session_id": session_id,
                }
            )
            return 76

    workspace = Path.cwd().resolve(strict=True)
    resolved_evidence, evidence, evidence_sha256 = _read_evidence(
        workspace=workspace,
        evidence_relative=evidence_relative,
        declared_sha256=declared_sha256,
        bound_state=bound_state,
        state_descriptor=state_descriptor,
    )
    result = _derived_result(evidence_sha256)
    state["reads"] += 1
    state["submissions"] += 1
    _write_state(state_path, state, state_descriptor)

    scenario = os.environ.get("MMX_FAKE_CLAUDE_SCENARIO", "ok")
    events = _canonical_events(
        version=version,
        model=model,
        session_id=session_id,
        working_directory=str(workspace),
        evidence_path=str(resolved_evidence),
        evidence=evidence,
        result=result,
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
        _write_state(state_path, state, state_descriptor)
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
            sys.stdout.buffer.write(
                _event(
                    {
                        "type": "system",
                        "subtype": "usage",
                        "session_id": session_id,
                        "usage": {
                            "input_tokens": 1,
                            "output_tokens": 1,
                            "cache_creation_input_tokens": 0,
                            "cache_read_input_tokens": 0,
                        },
                        "padding": "x" * 256,
                    }
                )
            )
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
                    "usage": {
                        "input_tokens": 1,
                        "output_tokens": 1,
                        "cache_creation_input_tokens": 0,
                        "cache_read_input_tokens": 0,
                    },
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
    elif scenario == "init_end_conversation":
        # EndConversation is intentionally absent from non-interactive -p.
        events[0]["tools"] = ["Read", "EndConversation"]
    elif scenario == "init_mcp":
        events[0]["mcp_servers"] = [{"name": "bad", "status": "connected"}]
    elif scenario == "init_plugin":
        events[0]["plugins"] = [{"name": "bad", "path": "/private/plugin"}]
    elif scenario == "init_required_field_missing":
        del events[0]["apiKeySource"]
    elif scenario == "init_extra_field":
        events[0]["unreviewed"] = True
    elif scenario == "init_uuid_type_invalid":
        events[0]["uuid"] = 7
    elif scenario == "init_optional_type_invalid":
        events[0]["fast_mode_state"] = {"state": "on"}
    elif scenario == "init_cwd_drift":
        events[0]["cwd"] = str(workspace.parent)
    elif scenario == "init_version_drift":
        events[0]["claude_code_version"] = "2.1.258"
    elif scenario == "assistant_parent_tool":
        events[1]["parent_tool_use_id"] = "toolu_parent"
    elif scenario == "assistant_write_tool":
        events[1]["message"]["content"][0]["name"] = "Write"
    elif scenario == "read_wrong_file":
        events[1]["message"]["content"][0]["input"]["file_path"] = str(
            workspace / "sealed" / "other.txt"
        )
    elif scenario == "duplicate_tool":
        events.insert(2, json.loads(json.dumps(events[1])))
    elif scenario == "tool_result_mismatch":
        events[2]["message"]["content"][0]["tool_use_id"] = "toolu_other"
    elif scenario == "tool_result_unnumbered":
        events[2]["message"]["content"][0]["content"] = evidence
    elif scenario == "tool_result_structured_missing":
        del events[2]["tool_use_result"]
    elif scenario == "tool_result_structured_mismatch":
        events[2]["tool_use_result"]["file"]["content"] = "different evidence\n"
    elif scenario == "tool_result_truncated":
        events[2]["tool_use_result"]["file"]["truncatedByTokenCap"] = True
    elif scenario == "tool_result_private_locator_echo":
        events[2]["message"]["content"][0]["content"] = "1\t/Users/example/private\n"
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
    elif scenario == "result_stop_reason_missing":
        del events[-1]["stop_reason"]
    elif scenario == "result_usage_sparse":
        del events[-1]["usage"]["cache_creation_input_tokens"]
    elif scenario == "result_timing_type_invalid":
        events[-1]["ttft_ms"] = "fast"
    elif scenario == "secret_output":
        events[0]["capabilities"] = ["sk-" + "ant-" + "FAKE_SENTINEL_NOT_A_SECRET"]
    elif scenario == "private_path_output":
        events[0]["capabilities"] = ["/Users/example/private"]
    elif scenario == "scratch_residue":
        scratch_residue = Path(os.environ["TMPDIR"]) / "fake-residue"
        descriptor = os.open(scratch_residue, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(descriptor)
    elif scenario not in {
        "ok",
        "nonzero_after_success",
        "child_after_result",
        "escaped_child_after_result",
    }:
        _reject("scenario", 75)

    if scenario == "child_after_result":
        signal.signal(signal.SIGCHLD, signal.SIG_IGN)
        child = subprocess.Popen(
            [
                "/usr/bin/python3",
                "-c",
                "import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(60)",
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
        )
        state["children"] = [child.pid]
        _write_state(state_path, state, state_descriptor)
    if scenario == "escaped_child_after_result":
        spawned_at_ns = time.monotonic_ns()
        child = subprocess.Popen(
            [
                "/usr/bin/python3",
                "-c",
                "import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(60)",
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
        )
        if bound_state:
            identity = _process_identity(child.pid)
            if (
                identity is None
                or identity[0] != child.pid
                or identity[1] != os.getpid()
                or identity[2] != child.pid
            ):
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except OSError:
                    pass
                child.wait(timeout=2)
                _reject("child identity", 74)
            state["escaped_children"] = [
                {
                    "pid": child.pid,
                    "pgid": child.pid,
                    "parent_pid": os.getpid(),
                    "parent_started_ns": state["owner_started_ns"],
                    "spawned_at_ns": spawned_at_ns,
                    "start_token": identity[3],
                }
            ]
        else:
            state["escaped_children"] = [child.pid]
        _write_state(state_path, state, state_descriptor)
    for event in events:
        _emit(event)
    return 7 if scenario == "nonzero_after_success" else 0


if __name__ == "__main__":
    raise SystemExit(_main())
