"""Closed, provider-private Claude CLI protocol falsifier.

This module compiles exactly one foreground ``claude -p`` shape and, in PF1-F0,
observes it only through the exact committed fake executable.  A later guarded
integration must supply native managed-policy and authentication attestation
before it can lift that provider-free effect ceiling.  This module deliberately
does not define or mutate any shared lifecycle or control-plane state.

The boundary is evidence-negative by design: after a process starts, any
ambiguous stream, timeout, cancellation, exit, or cleanup result fails closed
and never authorizes a retry, resume, fallback, or success inference.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import math
import os
import pwd
import re
import selectors
import signal
import stat
import subprocess
import sys
import threading
import time
import uuid
from enum import Enum
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence


_MINIMUM_VERSION = (2, 1, 248)
_PERMISSION_PROMPTS_VERSION = (2, 1, 259)
_MODEL_PATTERN = re.compile(
    r"claude-(?:opus|sonnet|haiku)-[1-9][0-9]*(?:-[0-9]+)+(?:-[0-9]{8})?\Z"
)
_HEX_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_SAFE_FAKE_SCENARIO = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")
_TOOL_ID = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")
_MESSAGE_ID = re.compile(r"msg_[A-Za-z0-9_-]{1,128}\Z")
_REQUEST_ID = re.compile(r"req_[A-Za-z0-9_-]{1,128}\Z")
_SAFE_PROTOCOL_TOKEN = re.compile(r"[A-Za-z0-9_.:-]{1,128}\Z")
_SAFE_TIMESTAMP = re.compile(r"[0-9TZ:.,+\-]{1,64}\Z")
_MAX_BINARY_BYTES = 1_048_576
_BOUND_STATE_SCHEMA = "mmx.fake-claude-state.v2"
_FAST_MODE_STATES = frozenset({"off", "cooldown", "on"})
_FAST_MODE_DISABLED_REASONS = frozenset(
    {
        "free",
        "preference",
        "extra_usage_disabled",
        "network_error",
        "unknown",
        "not_first_party",
        "disabled_by_env",
        "model_not_allowed",
        "sdk_opt_in_required",
        "pending",
    }
)
_EFFORT_LEVELS = frozenset({"low", "medium", "high", "xhigh", "max"})
_RESULT_ELAPSED_TIMING_FIELDS = frozenset(
    {
        "ttft_ms",
        "ttft_stream_ms",
        "time_to_request_ms",
        "first_content_frame_ms",
        "first_stream_post_ms",
        "first_stream_post_ack_ms",
        "time_to_request_from_spawn_ms",
    }
)
_RESULT_WALL_TIMING_FIELDS = frozenset(
    {"request_sent_wall_ms", "first_stream_post_wall_ms", "time_origin_ms"}
)
_SAFE_ENVIRONMENT = (
    ("PATH", "/usr/bin:/bin"),
    ("LANG", "C.UTF-8"),
    ("LC_ALL", "C.UTF-8"),
    ("TZ", "UTC"),
    ("CLAUDE_CODE_MAX_RETRIES", "0"),
    ("MAX_STRUCTURED_OUTPUT_RETRIES", "0"),
    ("CLAUDE_CODE_MAX_TOOL_USE_CONCURRENCY", "1"),
    ("CLAUDE_CODE_SKIP_PROMPT_HISTORY", "1"),
    ("IS_DEMO", "1"),
)
_FAKE_CONTROL_KEYS = frozenset(
    {
        "MMX_FAKE_CLAUDE_SCENARIO",
        "MMX_FAKE_CLAUDE_STATE_FILE",
        "MMX_FAKE_CLAUDE_VERSION",
        "MMX_FAKE_CLAUDE_MAX_STARTS",
        "MMX_FAKE_CLAUDE_MANAGED_SETTINGS",
    }
)
_SENSITIVE_BYTES = (
    b"sk-ant-",
    b"ANTHROPIC_API_KEY",
    b"ANTHROPIC_AUTH_TOKEN",
    b"CLAUDE_CODE_OAUTH_TOKEN",
    b"-----BEGIN PRIVATE KEY-----",
    b"-----BEGIN OPENSSH PRIVATE KEY-----",
)
_EMAIL_BYTES = re.compile(rb"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PRIVATE_LOCATOR_BYTES = (
    b"/Users/",
    b"/home/",
    b"\\Users\\",
    b"file://",
)


class ClaudeCliObservation(str, Enum):
    """Provider-private observation states; none are Executive lifecycle state."""

    PROCESS_NOT_STARTED = "PROCESS_NOT_STARTED"
    PROCESS_STARTED_SUBMISSION_POSSIBLE = "PROCESS_STARTED_SUBMISSION_POSSIBLE"
    TERMINAL_RESULT_OBSERVED = "TERMINAL_RESULT_OBSERVED"
    TERMINAL_PROVIDER_FAILURE_OBSERVED = "TERMINAL_PROVIDER_FAILURE_OBSERVED"
    OUTCOME_UNRECONCILED = "OUTCOME_UNRECONCILED"


@dataclasses.dataclass(frozen=True, order=True)
class ClaudeCliVersion:
    major: int
    minor: int
    patch: int

    @classmethod
    def parse(cls, value: str) -> "ClaudeCliVersion":
        if not isinstance(value, str) or re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", value) is None:
            raise ClaudeCliProtocolError(
                "VERSION_INVALID",
                ClaudeCliObservation.PROCESS_NOT_STARTED,
                "Claude CLI version is invalid",
            )
        parts = value.split(".")
        parsed = cls(*(int(part) for part in parts))
        if any(part > 999_999 for part in (parsed.major, parsed.minor, parsed.patch)):
            raise ClaudeCliProtocolError(
                "VERSION_INVALID",
                ClaudeCliObservation.PROCESS_NOT_STARTED,
                "Claude CLI version is out of bounds",
            )
        return parsed

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"

    @property
    def supports_permission_prompts(self) -> bool:
        return (self.major, self.minor, self.patch) >= _PERMISSION_PROMPTS_VERSION


@dataclasses.dataclass(frozen=True)
class ClaudeCliInvocationPolicy:
    """Frozen inputs for the one reviewed provider-private invocation."""

    binary: Path
    version: ClaudeCliVersion
    model: str
    session_id: str
    prompt: str
    working_directory: Path
    isolated_home: Path
    isolated_tmp: Path
    evidence_relative_path: str
    expected_result_sha256: str
    api_timeout_ms: int
    idle_timeout_seconds: float
    absolute_timeout_seconds: float
    terminate_grace_seconds: float
    max_stdout_bytes: int
    max_stderr_bytes: int
    max_line_bytes: int
    max_events: int
    max_json_depth: int
    max_json_string_bytes: int
    max_json_collection_items: int


@dataclasses.dataclass(frozen=True)
class ClaudeCliCommand:
    """Exact argv/environment plus bounded private validation material."""

    argv: tuple[str, ...]
    environment: tuple[tuple[str, str], ...]
    working_directory: str
    model: str
    session_id: str
    version: ClaudeCliVersion
    prompt: str
    isolated_home: str
    isolated_tmp: str
    evidence_relative_path: str
    evidence_sha256: str
    expected_result_sha256: str
    api_timeout_ms: int
    idle_timeout_seconds: float
    absolute_timeout_seconds: float
    terminate_grace_seconds: float
    max_stdout_bytes: int
    max_stderr_bytes: int
    max_line_bytes: int
    max_events: int
    max_json_depth: int
    max_json_string_bytes: int
    max_json_collection_items: int
    argv_sha256: str
    environment_sha256: str
    settings_sha256: str
    binary_sha256: str
    binary_device: int
    binary_inode: int
    binary_uid: int
    binary_mode: int
    binary_size: int
    binary_mtime_ns: int
    evidence_device: int
    evidence_inode: int
    evidence_uid: int
    evidence_mode: int
    evidence_size: int
    evidence_mtime_ns: int


@dataclasses.dataclass(frozen=True)
class ClaudeCliEvent:
    index: int
    event_type: str
    subtype: str | None
    sha256: str


@dataclasses.dataclass(frozen=True)
class ClaudeCliCleanupReceipt:
    process_group_empty: bool
    marked_descendants_empty: bool
    leader_reaped: bool
    stdin_closed: bool
    stdout_closed: bool
    stderr_closed: bool
    reader_closed: bool
    scratch_empty: bool
    term_sent: bool
    kill_sent: bool
    residue_rows: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "process_group_empty": self.process_group_empty,
            "marked_descendants_empty": self.marked_descendants_empty,
            "leader_reaped": self.leader_reaped,
            "stdin_closed": self.stdin_closed,
            "stdout_closed": self.stdout_closed,
            "stderr_closed": self.stderr_closed,
            "reader_closed": self.reader_closed,
            "scratch_empty": self.scratch_empty,
            "term_sent": self.term_sent,
            "kill_sent": self.kill_sent,
            "residue_rows": list(self.residue_rows),
        }


@dataclasses.dataclass(frozen=True)
class ClaudeCliRunReceipt:
    observation: ClaudeCliObservation
    session_id: str
    model: str
    event_count: int
    read_count: int
    submission_count: int
    input_tokens: int
    output_tokens: int
    cost_microusd: int
    result_sha256: str
    stream_sha256: str
    argv_sha256: str
    environment_sha256: str
    settings_sha256: str
    binary_sha256: str
    binary_device: int
    binary_inode: int
    binary_uid: int
    binary_mode: int
    binary_size: int
    binary_mtime_ns: int
    returncode: int
    events: tuple[ClaudeCliEvent, ...]
    cleanup: ClaudeCliCleanupReceipt
    receipt_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "observation": self.observation.value,
            "session_id": self.session_id,
            "model": self.model,
            "event_count": self.event_count,
            "read_count": self.read_count,
            "submission_count": self.submission_count,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cost_microusd": self.cost_microusd,
            "result_sha256": self.result_sha256,
            "stream_sha256": self.stream_sha256,
            "argv_sha256": self.argv_sha256,
            "environment_sha256": self.environment_sha256,
            "settings_sha256": self.settings_sha256,
            "binary_sha256": self.binary_sha256,
            "binary_device": self.binary_device,
            "binary_inode": self.binary_inode,
            "binary_uid": self.binary_uid,
            "binary_mode": self.binary_mode,
            "binary_size": self.binary_size,
            "binary_mtime_ns": self.binary_mtime_ns,
            "returncode": self.returncode,
            "events": [dataclasses.asdict(event) for event in self.events],
            "cleanup": self.cleanup.to_dict(),
            "receipt_sha256": self.receipt_sha256,
        }


class ClaudeCliProtocolError(RuntimeError):
    """Bounded safe failure with the strongest provider observation available."""

    def __init__(
        self,
        code: str,
        observation: ClaudeCliObservation,
        message: str,
        *,
        cleanup: ClaudeCliCleanupReceipt | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.observation = observation
        self.cleanup = cleanup


class _DuplicateKey(ValueError):
    pass


class _StreamViolation(Exception):
    def __init__(
        self,
        code: str,
        observation: ClaudeCliObservation,
        message: str,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.observation = observation
        self.message = message


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("ascii")
    return _sha256_bytes(encoded)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


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


def _trusted_native_home() -> Path:
    try:
        value = pwd.getpwuid(os.getuid()).pw_dir
        if not value:
            raise KeyError
        return Path(value).resolve(strict=True)
    except (KeyError, OSError):
        raise _fail_before_start(
            "NATIVE_HOME_UNPROVEN",
            "native account home identity could not be proven",
        ) from None


def _fail_before_start(code: str, message: str) -> ClaudeCliProtocolError:
    return ClaudeCliProtocolError(
        code,
        ClaudeCliObservation.PROCESS_NOT_STARTED,
        message,
    )


def _resolve_real_directory(value: Any, name: str) -> Path:
    if not isinstance(value, Path) or not value.is_absolute():
        raise _fail_before_start("PATH_INVALID", f"{name} must be an absolute directory")
    try:
        info = value.lstat()
        resolved = value.resolve(strict=True)
    except OSError:
        raise _fail_before_start("PATH_INVALID", f"{name} is unavailable") from None
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise _fail_before_start("PATH_INVALID", f"{name} must be a real directory")
    return resolved


def _validate_safe_relative_path(value: Any) -> PurePosixPath:
    if not isinstance(value, str) or not value or len(value.encode("utf-8")) > 256:
        raise _fail_before_start("EVIDENCE_PATH_INVALID", "evidence path is invalid")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or "." in path.parts
        or ".." in path.parts
        or any(not part or part.startswith(".") for part in path.parts)
        or "\\" in value
        or "\x00" in value
    ):
        raise _fail_before_start("EVIDENCE_PATH_INVALID", "evidence path must remain sealed and relative")
    return path


def _validate_policy(
    policy: ClaudeCliInvocationPolicy,
) -> tuple[Path, os.stat_result, bytes, Path, Path, os.stat_result, bytes]:
    if not isinstance(policy, ClaudeCliInvocationPolicy):
        raise _fail_before_start("POLICY_INVALID", "Claude invocation policy is invalid")
    if not isinstance(policy.version, ClaudeCliVersion):
        raise _fail_before_start("VERSION_INVALID", "Claude CLI version is invalid")
    if (policy.version.major, policy.version.minor, policy.version.patch) < _MINIMUM_VERSION:
        raise _fail_before_start(
            "VERSION_UNSUPPORTED",
            "Claude CLI version is below the supported restricted-mode floor",
        )
    if not isinstance(policy.binary, Path) or not policy.binary.is_absolute():
        raise _fail_before_start("BINARY_INVALID", "Claude binary must be an absolute path")
    try:
        binary_info = policy.binary.lstat()
        binary = policy.binary.resolve(strict=True)
        binary_bytes = binary.read_bytes()
    except OSError:
        raise _fail_before_start("BINARY_INVALID", "Claude binary is unavailable") from None
    if (
        stat.S_ISLNK(binary_info.st_mode)
        or not stat.S_ISREG(binary_info.st_mode)
        or not os.access(binary, os.X_OK)
        or not binary_bytes
        or len(binary_bytes) > _MAX_BINARY_BYTES
    ):
        raise _fail_before_start("BINARY_INVALID", "Claude binary must be a real executable file")
    if not isinstance(policy.model, str) or _MODEL_PATTERN.fullmatch(policy.model) is None:
        raise _fail_before_start("MODEL_INVALID", "model must be a full Claude model identifier")
    if not isinstance(policy.session_id, str):
        raise _fail_before_start("SESSION_INVALID", "session UUID is invalid")
    try:
        parsed_session = uuid.UUID(policy.session_id)
    except (ValueError, AttributeError):
        raise _fail_before_start("SESSION_INVALID", "session UUID is invalid") from None
    if str(parsed_session) != policy.session_id:
        raise _fail_before_start("SESSION_INVALID", "session UUID must use canonical lowercase form")
    if (
        not isinstance(policy.prompt, str)
        or not policy.prompt
        or "\x00" in policy.prompt
        or len(policy.prompt.encode("utf-8")) > 8_192
        or policy.prompt.lstrip().startswith("/")
    ):
        raise _fail_before_start("PROMPT_INVALID", "prompt is invalid or out of bounds")
    relative = _validate_safe_relative_path(policy.evidence_relative_path)
    workspace = _resolve_real_directory(policy.working_directory, "working directory")
    home = _resolve_real_directory(policy.isolated_home, "isolated home")
    scratch = _resolve_real_directory(policy.isolated_tmp, "isolated temp directory")
    native_home = _trusted_native_home()
    if home == native_home:
        raise _fail_before_start("HOME_NOT_ISOLATED", "isolated home may not be the native home")
    if home == scratch or workspace in home.parents or workspace in scratch.parents:
        raise _fail_before_start("PATH_INVALID", "runtime paths must be distinct from the sealed workspace")
    evidence_path = workspace.joinpath(*relative.parts)
    try:
        evidence_info = evidence_path.lstat()
        resolved_evidence = evidence_path.resolve(strict=True)
        evidence_bytes = resolved_evidence.read_bytes()
    except OSError:
        raise _fail_before_start("EVIDENCE_INVALID", "sealed evidence file is unavailable") from None
    if (
        stat.S_ISLNK(evidence_info.st_mode)
        or not stat.S_ISREG(evidence_info.st_mode)
        or resolved_evidence != evidence_path
        or workspace not in resolved_evidence.parents
        or len(evidence_bytes) > 65_536
    ):
        raise _fail_before_start("EVIDENCE_INVALID", "sealed evidence file is invalid or out of bounds")
    if not isinstance(policy.expected_result_sha256, str) or _HEX_SHA256.fullmatch(
        policy.expected_result_sha256
    ) is None:
        raise _fail_before_start("RESULT_DIGEST_INVALID", "expected result digest is invalid")
    evidence_sha256 = _sha256_bytes(evidence_bytes)
    if policy.prompt != _derived_prompt(policy.evidence_relative_path, evidence_sha256):
        raise _fail_before_start(
            "PROMPT_BINDING_INVALID",
            "prompt was not canonically derived from sealed evidence",
        )
    if policy.expected_result_sha256 != _sha256_bytes(
        _derived_result(evidence_sha256).encode("utf-8")
    ):
        raise _fail_before_start(
            "RESULT_BINDING_INVALID",
            "expected result was not canonically derived from sealed evidence",
        )
    integer_bounds = (
        ("API timeout", policy.api_timeout_ms, 100, 600_000),
        ("stdout byte limit", policy.max_stdout_bytes, 1_024, 16_777_216),
        ("stderr byte limit", policy.max_stderr_bytes, 256, 1_048_576),
        ("line byte limit", policy.max_line_bytes, 256, 1_048_576),
        ("event limit", policy.max_events, 1, 4_096),
        ("JSON depth limit", policy.max_json_depth, 2, 64),
        ("JSON string limit", policy.max_json_string_bytes, 64, 1_048_576),
        ("JSON collection limit", policy.max_json_collection_items, 1, 16_384),
    )
    for name, value, minimum, maximum in integer_bounds:
        if type(value) is not int or not minimum <= value <= maximum:
            raise _fail_before_start("BOUND_INVALID", f"{name} is out of bounds")
    timeout_bounds = (
        ("idle timeout", policy.idle_timeout_seconds, 0.05, 3_600.0),
        ("absolute timeout", policy.absolute_timeout_seconds, 0.1, 14_400.0),
        ("termination grace", policy.terminate_grace_seconds, 0.01, 30.0),
    )
    for name, value, minimum, maximum in timeout_bounds:
        if type(value) not in {int, float} or not math.isfinite(float(value)) or not minimum <= float(value) <= maximum:
            raise _fail_before_start("BOUND_INVALID", f"{name} is out of bounds")
    if policy.absolute_timeout_seconds < policy.idle_timeout_seconds:
        raise _fail_before_start("BOUND_INVALID", "absolute timeout must not be shorter than idle timeout")
    if policy.max_line_bytes > policy.max_stdout_bytes:
        raise _fail_before_start("BOUND_INVALID", "line byte limit must not exceed stdout byte limit")
    return binary, binary_info, binary_bytes, workspace, home, evidence_info, evidence_bytes


def _build_argv(
    *,
    binary: str,
    version: ClaudeCliVersion,
    model: str,
    session_id: str,
    prompt: str,
    settings_json: str,
) -> tuple[str, ...]:
    values = [
        binary,
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
    if version.supports_permission_prompts:
        values.extend(["--permission-prompts", "none"])
    values.extend(
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
            settings_json,
            prompt,
        ]
    )
    return tuple(values)


def _environment_digest(environment: Sequence[tuple[str, str]]) -> str:
    normalized = {
        key: "<isolated-home>" if key == "HOME" else "<isolated-tmp>" if key == "TMPDIR" else value
        for key, value in environment
    }
    return _canonical_sha256(normalized)


def compile_claude_cli_command(
    policy: ClaudeCliInvocationPolicy,
    *,
    requested_flags: Sequence[str] = (),
    caller_environment: Mapping[str, str] | None = None,
) -> ClaudeCliCommand:
    """Compile only the frozen command; caller flags and environment never merge."""

    if isinstance(requested_flags, (str, bytes)) or tuple(requested_flags):
        raise _fail_before_start(
            "CALLER_FLAGS_REFUSED",
            "caller-supplied CLI flags are not accepted",
        )
    if caller_environment is not None:
        raise _fail_before_start(
            "CALLER_ENVIRONMENT_REFUSED",
            "caller environment is not accepted",
        )
    (
        binary,
        binary_info,
        binary_bytes,
        workspace,
        home,
        evidence_info,
        evidence_bytes,
    ) = _validate_policy(policy)
    scratch = policy.isolated_tmp.resolve(strict=True)
    environment = (
        ("HOME", str(home)),
        ("TMPDIR", str(scratch)),
        *_SAFE_ENVIRONMENT,
        ("API_TIMEOUT_MS", str(policy.api_timeout_ms)),
    )
    argv = _build_argv(
        binary=str(binary),
        version=policy.version,
        model=policy.model,
        session_id=policy.session_id,
        prompt=policy.prompt,
        settings_json=_closed_settings_json(policy.evidence_relative_path),
    )
    return ClaudeCliCommand(
        argv=argv,
        environment=environment,
        working_directory=str(workspace),
        model=policy.model,
        session_id=policy.session_id,
        version=policy.version,
        prompt=policy.prompt,
        isolated_home=str(home),
        isolated_tmp=str(scratch),
        evidence_relative_path=policy.evidence_relative_path,
        evidence_sha256=_sha256_bytes(evidence_bytes),
        expected_result_sha256=policy.expected_result_sha256,
        api_timeout_ms=policy.api_timeout_ms,
        idle_timeout_seconds=float(policy.idle_timeout_seconds),
        absolute_timeout_seconds=float(policy.absolute_timeout_seconds),
        terminate_grace_seconds=float(policy.terminate_grace_seconds),
        max_stdout_bytes=policy.max_stdout_bytes,
        max_stderr_bytes=policy.max_stderr_bytes,
        max_line_bytes=policy.max_line_bytes,
        max_events=policy.max_events,
        max_json_depth=policy.max_json_depth,
        max_json_string_bytes=policy.max_json_string_bytes,
        max_json_collection_items=policy.max_json_collection_items,
        argv_sha256=_canonical_sha256(list(argv)),
        environment_sha256=_environment_digest(environment),
        settings_sha256=_sha256_bytes(
            _closed_settings_json(policy.evidence_relative_path).encode("utf-8")
        ),
        binary_sha256=_sha256_bytes(binary_bytes),
        binary_device=binary_info.st_dev,
        binary_inode=binary_info.st_ino,
        binary_uid=binary_info.st_uid,
        binary_mode=binary_info.st_mode,
        binary_size=binary_info.st_size,
        binary_mtime_ns=binary_info.st_mtime_ns,
        evidence_device=evidence_info.st_dev,
        evidence_inode=evidence_info.st_ino,
        evidence_uid=evidence_info.st_uid,
        evidence_mode=evidence_info.st_mode,
        evidence_size=evidence_info.st_size,
        evidence_mtime_ns=evidence_info.st_mtime_ns,
    )


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise _DuplicateKey(key)
        value[key] = item
    return value


def _reject_json_constant(value: str) -> None:
    raise ValueError(value)


def _check_json_bounds(
    value: Any,
    *,
    depth: int,
    max_depth: int,
    max_string_bytes: int,
    max_collection_items: int,
) -> None:
    if depth > max_depth:
        raise _StreamViolation(
            "STREAM_JSON_DEPTH",
            ClaudeCliObservation.OUTCOME_UNRECONCILED,
            "stream JSON depth exceeded its bound",
        )
    if isinstance(value, str):
        if len(value.encode("utf-8")) > max_string_bytes:
            raise _StreamViolation(
                "STREAM_JSON_STRING",
                ClaudeCliObservation.OUTCOME_UNRECONCILED,
                "stream JSON string exceeded its bound",
            )
        return
    if isinstance(value, dict):
        if len(value) > max_collection_items:
            raise _StreamViolation(
                "STREAM_JSON_COLLECTION",
                ClaudeCliObservation.OUTCOME_UNRECONCILED,
                "stream JSON object exceeded its bound",
            )
        for key, item in value.items():
            _check_json_bounds(
                key,
                depth=depth + 1,
                max_depth=max_depth,
                max_string_bytes=max_string_bytes,
                max_collection_items=max_collection_items,
            )
            _check_json_bounds(
                item,
                depth=depth + 1,
                max_depth=max_depth,
                max_string_bytes=max_string_bytes,
                max_collection_items=max_collection_items,
            )
        return
    if isinstance(value, list):
        if len(value) > max_collection_items:
            raise _StreamViolation(
                "STREAM_JSON_COLLECTION",
                ClaudeCliObservation.OUTCOME_UNRECONCILED,
                "stream JSON array exceeded its bound",
            )
        for item in value:
            _check_json_bounds(
                item,
                depth=depth + 1,
                max_depth=max_depth,
                max_string_bytes=max_string_bytes,
                max_collection_items=max_collection_items,
            )
        return
    if value is not None and type(value) not in {bool, int, float}:
        raise _StreamViolation(
            "STREAM_JSON_INVALID",
            ClaudeCliObservation.OUTCOME_UNRECONCILED,
            "stream JSON contained an unsupported value",
        )


def _expect_keys(value: Mapping[str, Any], allowed: frozenset[str]) -> None:
    if not set(value).issubset(allowed):
        raise _StreamViolation(
            "EVENT_FIELDS_UNKNOWN",
            ClaudeCliObservation.OUTCOME_UNRECONCILED,
            "stream event contained unknown fields",
        )


def _expect_required_keys(
    value: Mapping[str, Any],
    required: frozenset[str],
    *,
    code: str,
    message: str,
) -> None:
    if not required.issubset(value):
        raise _StreamViolation(
            code,
            ClaudeCliObservation.OUTCOME_UNRECONCILED,
            message,
        )


def _expect_uuid(value: Any, *, code: str, message: str) -> None:
    if not isinstance(value, str):
        raise _StreamViolation(code, ClaudeCliObservation.OUTCOME_UNRECONCILED, message)
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError):
        raise _StreamViolation(code, ClaudeCliObservation.OUTCOME_UNRECONCILED, message) from None
    if str(parsed) != value:
        raise _StreamViolation(code, ClaudeCliObservation.OUTCOME_UNRECONCILED, message)


def _expect_session(value: Mapping[str, Any], session_id: str) -> None:
    if value.get("session_id") != session_id:
        raise _StreamViolation(
            "SESSION_DRIFT",
            ClaudeCliObservation.OUTCOME_UNRECONCILED,
            "stream session identity drifted",
        )


def _expect_optional_uuid_echoes(value: Mapping[str, Any], *, code: str) -> None:
    primary = value.get("user_message_uuid")
    if "user_message_uuid" in value:
        _expect_uuid(primary, code=code, message="user-message UUID was invalid")
    if "user_message_uuids" not in value:
        return
    echoes = value.get("user_message_uuids")
    if not isinstance(echoes, list) or not 1 <= len(echoes) <= 64:
        raise _StreamViolation(
            code,
            ClaudeCliObservation.OUTCOME_UNRECONCILED,
            "user-message UUID inventory was invalid",
        )
    for echo in echoes:
        _expect_uuid(echo, code=code, message="user-message UUID inventory was invalid")
    if primary is None or echoes[-1] != primary:
        raise _StreamViolation(
            code,
            ClaudeCliObservation.OUTCOME_UNRECONCILED,
            "user-message UUID inventory contradicted its primary UUID",
        )


def _expect_optional_timestamp(value: Any, *, code: str, message: str) -> None:
    if not isinstance(value, str) or _SAFE_TIMESTAMP.fullmatch(value) is None:
        raise _StreamViolation(
            code,
            ClaudeCliObservation.OUTCOME_UNRECONCILED,
            message,
        )


def _expect_fast_mode_fields(value: Mapping[str, Any], *, code: str) -> None:
    state = value.get("fast_mode_state")
    reason = value.get("fast_mode_disabled_reason")
    if state is not None and (
        not isinstance(state, str) or state not in _FAST_MODE_STATES
    ):
        raise _StreamViolation(
            code,
            ClaudeCliObservation.OUTCOME_UNRECONCILED,
            "fast-mode state was invalid",
        )
    if reason is not None and (
        not isinstance(reason, str) or reason not in _FAST_MODE_DISABLED_REASONS
    ):
        raise _StreamViolation(
            code,
            ClaudeCliObservation.OUTCOME_UNRECONCILED,
            "fast-mode disabled reason was invalid",
        )


def _bounded_token_count(value: Any) -> int:
    if type(value) is not int or not 0 <= value <= 1_000_000_000:
        raise _StreamViolation(
            "USAGE_INVALID",
            ClaudeCliObservation.OUTCOME_UNRECONCILED,
            "stream usage was invalid",
        )
    return value


_USAGE_REQUIRED_KEYS = frozenset(
    {
        "input_tokens",
        "output_tokens",
        "cache_creation_input_tokens",
        "cache_read_input_tokens",
    }
)
_USAGE_ALLOWED_KEYS = _USAGE_REQUIRED_KEYS | frozenset(
    {"cache_creation", "server_tool_use", "service_tier", "inference_geo"}
)


def _consume_usage_payload(value: Any) -> tuple[int, int, int, int]:
    if not isinstance(value, dict):
        raise _StreamViolation(
            "USAGE_INVALID",
            ClaudeCliObservation.OUTCOME_UNRECONCILED,
            "stream usage was invalid",
        )
    _expect_keys(value, _USAGE_ALLOWED_KEYS)
    _expect_required_keys(
        value,
        _USAGE_REQUIRED_KEYS,
        code="USAGE_INVALID",
        message="stream usage omitted required counters",
    )
    counters = tuple(
        _bounded_token_count(value[key])
        for key in (
            "input_tokens",
            "output_tokens",
            "cache_creation_input_tokens",
            "cache_read_input_tokens",
        )
    )
    cache_creation = value.get("cache_creation")
    if cache_creation is not None:
        if not isinstance(cache_creation, dict):
            raise _StreamViolation(
                "USAGE_INVALID",
                ClaudeCliObservation.OUTCOME_UNRECONCILED,
                "cache-creation usage was invalid",
            )
        _expect_keys(
            cache_creation,
            frozenset({"ephemeral_5m_input_tokens", "ephemeral_1h_input_tokens"}),
        )
        for count in cache_creation.values():
            _bounded_token_count(count)
    server_tool_use = value.get("server_tool_use")
    if server_tool_use is not None:
        if not isinstance(server_tool_use, dict):
            raise _StreamViolation(
                "USAGE_INVALID",
                ClaudeCliObservation.OUTCOME_UNRECONCILED,
                "server-tool usage was invalid",
            )
        _expect_keys(server_tool_use, frozenset({"web_search_requests", "web_fetch_requests"}))
        if any(_bounded_token_count(count) != 0 for count in server_tool_use.values()):
            raise _StreamViolation(
                "TOOL_UNAUTHORIZED",
                ClaudeCliObservation.OUTCOME_UNRECONCILED,
                "server-tool activity was observed",
            )
    if value.get("service_tier") not in (None, "standard", "priority", "batch"):
        raise _StreamViolation(
            "USAGE_INVALID",
            ClaudeCliObservation.OUTCOME_UNRECONCILED,
            "service-tier usage was invalid",
        )
    inference_geo = value.get("inference_geo")
    if inference_geo is not None and (
        not isinstance(inference_geo, str) or _SAFE_PROTOCOL_TOKEN.fullmatch(inference_geo) is None
    ):
        raise _StreamViolation(
            "USAGE_INVALID",
            ClaudeCliObservation.OUTCOME_UNRECONCILED,
            "inference geography was invalid",
        )
    return counters  # type: ignore[return-value]


def _numbered_read_content(content: str) -> str:
    """Pinned text rendering: one-based line number plus a single tab."""

    return "".join(
        f"{index}\t{line}"
        for index, line in enumerate(content.splitlines(keepends=True), start=1)
    )


def _expected_evidence_path(command: ClaudeCliCommand) -> str:
    relative = PurePosixPath(command.evidence_relative_path)
    return str(Path(command.working_directory).joinpath(*relative.parts))


def _public_protocol_value(value: Any, command: ClaudeCliCommand) -> Any:
    if isinstance(value, str):
        if value == command.working_directory:
            return "<sealed-workspace>"
        if value == _expected_evidence_path(command):
            return "<sealed-evidence>"
        return value
    if isinstance(value, list):
        return [_public_protocol_value(item, command) for item in value]
    if isinstance(value, dict):
        return {
            key: _public_protocol_value(item, command)
            for key, item in value.items()
        }
    return value


def _validate_model_usage(
    value: Any,
    *,
    command: ClaudeCliCommand,
    input_tokens: int,
    output_tokens: int,
    cache_creation_input_tokens: int,
    cache_read_input_tokens: int,
    total_cost_usd: float,
) -> None:
    if not isinstance(value, dict) or set(value) != {command.model}:
        raise _StreamViolation(
            "USAGE_INVALID",
            ClaudeCliObservation.OUTCOME_UNRECONCILED,
            "per-model usage identity was invalid",
        )
    model_usage = value.get(command.model)
    if not isinstance(model_usage, dict):
        raise _StreamViolation(
            "USAGE_INVALID",
            ClaudeCliObservation.OUTCOME_UNRECONCILED,
            "per-model usage was invalid",
        )
    _expect_keys(
        model_usage,
        frozenset(
            {
                "inputTokens",
                "outputTokens",
                "thinkingTokens",
                "cacheReadInputTokens",
                "cacheCreationInputTokens",
                "webSearchRequests",
                "costUSD",
                "contextWindow",
                "maxOutputTokens",
                "canonicalModel",
                "provider",
                "costBasis",
            }
        ),
    )
    _expect_required_keys(
        model_usage,
        frozenset(
            {
                "inputTokens",
                "outputTokens",
                "cacheReadInputTokens",
                "cacheCreationInputTokens",
                "webSearchRequests",
                "costUSD",
                "contextWindow",
                "maxOutputTokens",
            }
        ),
        code="USAGE_INVALID",
        message="per-model usage omitted required counters",
    )
    if (
        _bounded_token_count(model_usage.get("inputTokens")) != input_tokens
        or _bounded_token_count(model_usage.get("outputTokens")) != output_tokens
        or _bounded_token_count(model_usage.get("cacheCreationInputTokens"))
        != cache_creation_input_tokens
        or _bounded_token_count(model_usage.get("cacheReadInputTokens"))
        != cache_read_input_tokens
        or _bounded_token_count(model_usage.get("webSearchRequests")) != 0
    ):
        raise _StreamViolation(
            "USAGE_INVALID",
            ClaudeCliObservation.OUTCOME_UNRECONCILED,
            "per-model usage contradicted terminal usage",
        )
    thinking_tokens = model_usage.get("thinkingTokens")
    if thinking_tokens is not None and _bounded_token_count(thinking_tokens) > output_tokens:
        raise _StreamViolation(
            "USAGE_INVALID",
            ClaudeCliObservation.OUTCOME_UNRECONCILED,
            "thinking-token usage was invalid",
        )
    model_cost = model_usage.get("costUSD")
    if (
        type(model_cost) not in {int, float}
        or not math.isfinite(float(model_cost))
        or float(model_cost) != total_cost_usd
    ):
        raise _StreamViolation(
            "USAGE_INVALID",
            ClaudeCliObservation.OUTCOME_UNRECONCILED,
            "per-model cost contradicted terminal cost",
        )
    for key in ("contextWindow", "maxOutputTokens"):
        count = model_usage.get(key)
        if type(count) is not int or not 1 <= count <= 10_000_000:
            raise _StreamViolation(
                "USAGE_INVALID",
                ClaudeCliObservation.OUTCOME_UNRECONCILED,
                "per-model capacity was invalid",
            )
    for key in ("canonicalModel", "provider", "costBasis"):
        token = model_usage.get(key)
        if token is not None and (
            not isinstance(token, str) or _SAFE_PROTOCOL_TOKEN.fullmatch(token) is None
        ):
            raise _StreamViolation(
                "USAGE_INVALID",
                ClaudeCliObservation.OUTCOME_UNRECONCILED,
                "per-model metadata was invalid",
            )


class _StreamParser:
    def __init__(self, command: ClaudeCliCommand) -> None:
        self.command = command
        self.phase = 0
        self.event_count = 0
        self.read_count = 0
        self.submission_count = 0
        self.tool_use_id: str | None = None
        self.terminal = False
        self.result_sha256 = ""
        self.input_tokens = 0
        self.output_tokens = 0
        self.cost_microusd = 0
        self.events: list[ClaudeCliEvent] = []

    def consume(self, raw_line: bytes) -> None:
        self.event_count += 1
        if self.event_count > self.command.max_events:
            raise _StreamViolation(
                "STREAM_EVENT_LIMIT",
                ClaudeCliObservation.OUTCOME_UNRECONCILED,
                "stream event count exceeded its bound",
            )
        if not raw_line:
            raise _StreamViolation(
                "STREAM_JSON_INVALID",
                ClaudeCliObservation.OUTCOME_UNRECONCILED,
                "stream contained an empty line",
            )
        try:
            text = raw_line.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise _StreamViolation(
                "STDOUT_UTF8_INVALID",
                ClaudeCliObservation.OUTCOME_UNRECONCILED,
                "stdout was not valid UTF-8",
            ) from exc
        try:
            value = json.loads(
                text,
                object_pairs_hook=_reject_duplicate_pairs,
                parse_constant=_reject_json_constant,
            )
        except _DuplicateKey as exc:
            raise _StreamViolation(
                "STREAM_JSON_DUPLICATE_KEY",
                ClaudeCliObservation.OUTCOME_UNRECONCILED,
                "stream JSON contained a duplicate key",
            ) from exc
        except (json.JSONDecodeError, ValueError) as exc:
            raise _StreamViolation(
                "STREAM_JSON_INVALID",
                ClaudeCliObservation.OUTCOME_UNRECONCILED,
                "stream line was not strict JSON",
            ) from exc
        _check_json_bounds(
            value,
            depth=1,
            max_depth=self.command.max_json_depth,
            max_string_bytes=self.command.max_json_string_bytes,
            max_collection_items=self.command.max_json_collection_items,
        )
        if not isinstance(value, dict):
            raise _StreamViolation(
                "STREAM_JSON_INVALID",
                ClaudeCliObservation.OUTCOME_UNRECONCILED,
                "stream event must be a JSON object",
            )
        event_type = value.get("type")
        subtype = value.get("subtype")
        if not isinstance(event_type, str) or (subtype is not None and not isinstance(subtype, str)):
            raise _StreamViolation(
                "EVENT_UNKNOWN",
                ClaudeCliObservation.OUTCOME_UNRECONCILED,
                "stream event identity was invalid",
            )
        if self.terminal:
            code = "TERMINAL_RESULT_DUPLICATE" if event_type == "result" else "POST_TERMINAL_EVENT"
            message = "terminal result was duplicated" if event_type == "result" else "event followed terminal result"
            raise _StreamViolation(
                code,
                ClaudeCliObservation.OUTCOME_UNRECONCILED,
                message,
            )
        if event_type == "system" and subtype == "api_retry":
            raise _StreamViolation(
                "PROVIDER_RETRY_OBSERVED",
                ClaudeCliObservation.OUTCOME_UNRECONCILED,
                "provider retry was observed",
            )
        if event_type == "system" and subtype == "managed_policy":
            raise _StreamViolation(
                "MANAGED_POLICY_OBSERVED",
                ClaudeCliObservation.OUTCOME_UNRECONCILED,
                "managed policy changed the closed invocation surface",
            )
        if event_type == "system" and subtype == "permission_denied":
            raise _StreamViolation(
                "PERMISSION_DENIED",
                ClaudeCliObservation.OUTCOME_UNRECONCILED,
                "permission denial was observed",
            )
        if self.phase == 0 and not (event_type == "system" and subtype == "init"):
            raise _StreamViolation(
                "INIT_NOT_FIRST",
                ClaudeCliObservation.OUTCOME_UNRECONCILED,
                "system init was not the first stream event",
            )
        if event_type == "system" and subtype == "init":
            self._consume_init(value)
        elif event_type == "system" and subtype == "usage":
            self._consume_usage(value)
        elif event_type == "assistant":
            self._consume_assistant(value)
        elif event_type == "user":
            self._consume_user(value)
        elif event_type == "result":
            self._consume_result(value)
        else:
            raise _StreamViolation(
                "EVENT_UNKNOWN",
                ClaudeCliObservation.OUTCOME_UNRECONCILED,
                "stream event type or subtype was not accepted",
            )
        self.events.append(
            ClaudeCliEvent(
                index=self.event_count,
                event_type=event_type,
                subtype=subtype,
                sha256=_canonical_sha256(_public_protocol_value(value, self.command)),
            )
        )

    def _consume_init(self, value: Mapping[str, Any]) -> None:
        if self.phase != 0:
            raise _StreamViolation(
                "INIT_DUPLICATE",
                ClaudeCliObservation.OUTCOME_UNRECONCILED,
                "system init was duplicated",
            )
        _expect_keys(
            value,
            frozenset(
                {
                    "type",
                    "subtype",
                    "apiKeySource",
                    "claude_code_version",
                    "cwd",
                    "session_id",
                    "model",
                    "tools",
                    "mcp_servers",
                    "mcp_server_errors",
                    "plugins",
                    "plugin_errors",
                    "permissionMode",
                    "slash_commands",
                    "terminal_slash_commands",
                    "output_style",
                    "skills",
                    "capabilities",
                    "agents",
                    "betas",
                    "fast_mode_state",
                    "fast_mode_disabled_reason",
                    "effort",
                    "uuid",
                }
            ),
        )
        _expect_required_keys(
            value,
            frozenset(
                {
                    "type",
                    "subtype",
                    "apiKeySource",
                    "claude_code_version",
                    "cwd",
                    "tools",
                    "mcp_servers",
                    "model",
                    "permissionMode",
                    "slash_commands",
                    "output_style",
                    "skills",
                    "plugins",
                    "uuid",
                    "session_id",
                }
            ),
            code="INIT_INVALID",
            message="system init omitted required current-contract fields",
        )
        _expect_session(value, self.command.session_id)
        _expect_uuid(value.get("uuid"), code="INIT_INVALID", message="init UUID was invalid")
        if value.get("apiKeySource") != "none":
            raise _StreamViolation(
                "AUTH_SOURCE_DRIFT",
                ClaudeCliObservation.OUTCOME_UNRECONCILED,
                "init authentication source drifted",
            )
        if value.get("claude_code_version") != str(self.command.version):
            raise _StreamViolation(
                "VERSION_DRIFT",
                ClaudeCliObservation.OUTCOME_UNRECONCILED,
                "stream CLI version drifted",
            )
        if value.get("cwd") != self.command.working_directory:
            raise _StreamViolation(
                "WORKING_DIRECTORY_DRIFT",
                ClaudeCliObservation.OUTCOME_UNRECONCILED,
                "stream working directory drifted",
            )
        if value.get("model") != self.command.model:
            raise _StreamViolation(
                "MODEL_DRIFT",
                ClaudeCliObservation.OUTCOME_UNRECONCILED,
                "stream model identity drifted",
            )
        if value.get("tools") != ["Read"]:
            raise _StreamViolation(
                "TOOL_SET_DRIFT",
                ClaudeCliObservation.OUTCOME_UNRECONCILED,
                "stream tool set drifted",
            )
        if value.get("mcp_servers") != [] or value.get("mcp_server_errors") not in (None, []):
            raise _StreamViolation(
                "MCP_OBSERVED",
                ClaudeCliObservation.OUTCOME_UNRECONCILED,
                "MCP activity was observed",
            )
        if value.get("plugins") != [] or value.get("plugin_errors") not in (None, []):
            raise _StreamViolation(
                "PLUGIN_OBSERVED",
                ClaudeCliObservation.OUTCOME_UNRECONCILED,
                "plugin activity was observed",
            )
        if value.get("permissionMode") != "dontAsk":
            raise _StreamViolation(
                "PERMISSION_MODE_DRIFT",
                ClaudeCliObservation.OUTCOME_UNRECONCILED,
                "permission mode drifted",
            )
        if value.get("slash_commands") != [] or value.get("terminal_slash_commands") not in (None, []):
            raise _StreamViolation(
                "SLASH_COMMAND_OBSERVED",
                ClaudeCliObservation.OUTCOME_UNRECONCILED,
                "slash-command surface was observed",
            )
        if value.get("output_style") != "default":
            raise _StreamViolation(
                "OUTPUT_STYLE_DRIFT",
                ClaudeCliObservation.OUTCOME_UNRECONCILED,
                "output style drifted",
            )
        if value.get("skills") != [] or value.get("agents") not in (None, []):
            raise _StreamViolation(
                "EXTENSION_SURFACE_OBSERVED",
                ClaudeCliObservation.OUTCOME_UNRECONCILED,
                "skill or agent surface was observed",
            )
        if value.get("betas") not in (None, []):
            raise _StreamViolation(
                "BETA_SURFACE_OBSERVED",
                ClaudeCliObservation.OUTCOME_UNRECONCILED,
                "unreviewed beta surface was observed",
            )
        capabilities = value.get("capabilities", [])
        if not isinstance(capabilities, list) or any(
            not isinstance(item, str) or _SAFE_PROTOCOL_TOKEN.fullmatch(item) is None
            for item in capabilities
        ):
            raise _StreamViolation(
                "INIT_INVALID",
                ClaudeCliObservation.OUTCOME_UNRECONCILED,
                "init capabilities were invalid",
            )
        _expect_fast_mode_fields(value, code="INIT_INVALID")
        effort = value.get("effort")
        if effort is not None and (
            not isinstance(effort, str) or effort not in _EFFORT_LEVELS
        ):
            raise _StreamViolation(
                "INIT_INVALID",
                ClaudeCliObservation.OUTCOME_UNRECONCILED,
                "init effort was invalid",
            )
        self.phase = 1
        self.submission_count = 1

    def _consume_usage(self, value: Mapping[str, Any]) -> None:
        if self.phase == 0 or self.terminal:
            raise _StreamViolation(
                "EVENT_ORDER_INVALID",
                ClaudeCliObservation.OUTCOME_UNRECONCILED,
                "usage event was out of order",
            )
        _expect_keys(value, frozenset({"type", "subtype", "session_id", "usage", "uuid"}))
        _expect_session(value, self.command.session_id)
        input_tokens, output_tokens, _, _ = _consume_usage_payload(value.get("usage"))
        self.input_tokens = max(self.input_tokens, input_tokens)
        self.output_tokens = max(self.output_tokens, output_tokens)

    def _consume_assistant(self, value: Mapping[str, Any]) -> None:
        _expect_keys(
            value,
            frozenset(
                {
                    "type",
                    "message",
                    "parent_tool_use_id",
                    "session_id",
                    "uuid",
                    "error",
                    "request_id",
                    "user_message_uuid",
                    "user_message_uuids",
                    "resumed_from_incomplete_thinking",
                    "supersedes",
                    "aborted",
                    "subagent_type",
                    "task_description",
                    "timestamp",
                    "context_usage",
                }
            ),
        )
        _expect_required_keys(
            value,
            frozenset({"type", "message", "parent_tool_use_id", "session_id", "uuid"}),
            code="ASSISTANT_EVENT_INVALID",
            message="assistant event omitted required current-contract fields",
        )
        _expect_session(value, self.command.session_id)
        _expect_uuid(
            value.get("uuid"),
            code="ASSISTANT_EVENT_INVALID",
            message="assistant UUID was invalid",
        )
        if value.get("parent_tool_use_id") is not None:
            raise _StreamViolation(
                "SUBAGENT_OBSERVED",
                ClaudeCliObservation.OUTCOME_UNRECONCILED,
                "subagent output was observed",
            )
        if any(
            value.get(field) is not None
            for field in (
                "error",
                "subagent_type",
                "task_description",
                "aborted",
                "resumed_from_incomplete_thinking",
                "supersedes",
            )
        ):
            raise _StreamViolation(
                "ASSISTANT_EVENT_INVALID",
                ClaudeCliObservation.OUTCOME_UNRECONCILED,
                "assistant event carried an unapproved execution marker",
            )
        request_id = value.get("request_id")
        if request_id is not None and (
            not isinstance(request_id, str) or _REQUEST_ID.fullmatch(request_id) is None
        ):
            raise _StreamViolation(
                "ASSISTANT_EVENT_INVALID",
                ClaudeCliObservation.OUTCOME_UNRECONCILED,
                "assistant request identity was invalid",
            )
        _expect_optional_uuid_echoes(value, code="ASSISTANT_EVENT_INVALID")
        if "timestamp" in value:
            _expect_optional_timestamp(
                value.get("timestamp"),
                code="ASSISTANT_EVENT_INVALID",
                message="assistant timestamp was invalid",
            )
        if value.get("context_usage") is not None:
            raise _StreamViolation(
                "ASSISTANT_EVENT_INVALID",
                ClaudeCliObservation.OUTCOME_UNRECONCILED,
                "assistant context report was not accepted",
            )
        message = value.get("message")
        if not isinstance(message, dict):
            raise _StreamViolation(
                "ASSISTANT_EVENT_INVALID",
                ClaudeCliObservation.OUTCOME_UNRECONCILED,
                "assistant event was invalid",
            )
        _expect_keys(
            message,
            frozenset(
                {
                    "id",
                    "type",
                    "role",
                    "model",
                    "content",
                    "stop_reason",
                    "stop_sequence",
                    "usage",
                    "context_management",
                }
            ),
        )
        _expect_required_keys(
            message,
            frozenset(
                {
                    "id",
                    "type",
                    "role",
                    "model",
                    "content",
                    "stop_reason",
                    "stop_sequence",
                    "usage",
                }
            ),
            code="ASSISTANT_EVENT_INVALID",
            message="assistant message omitted required API fields",
        )
        message_id = message.get("id")
        if (
            message.get("type") != "message"
            or not isinstance(message_id, str)
            or _MESSAGE_ID.fullmatch(message_id) is None
            or message.get("role") != "assistant"
            or message.get("model") != self.command.model
        ):
            raise _StreamViolation(
                "MODEL_DRIFT",
                ClaudeCliObservation.OUTCOME_UNRECONCILED,
                "assistant identity drifted",
            )
        if message.get("stop_reason") is not None or message.get("stop_sequence") is not None:
            raise _StreamViolation(
                "ASSISTANT_EVENT_INVALID",
                ClaudeCliObservation.OUTCOME_UNRECONCILED,
                "streamed assistant message carried premature terminal fields",
            )
        if message.get("context_management") is not None:
            raise _StreamViolation(
                "ASSISTANT_EVENT_INVALID",
                ClaudeCliObservation.OUTCOME_UNRECONCILED,
                "assistant context-management metadata was not accepted",
            )
        _consume_usage_payload(message.get("usage"))
        content = message.get("content")
        if not isinstance(content, list) or len(content) != 1 or not isinstance(content[0], dict):
            raise _StreamViolation(
                "ASSISTANT_EVENT_INVALID",
                ClaudeCliObservation.OUTCOME_UNRECONCILED,
                "assistant content was not singular and bounded",
            )
        block = content[0]
        if block.get("type") == "tool_use":
            if self.phase != 1:
                raise _StreamViolation(
                    "READ_COUNT_INVALID",
                    ClaudeCliObservation.OUTCOME_UNRECONCILED,
                    "Read was duplicated or out of order",
                )
            _expect_keys(block, frozenset({"type", "id", "name", "input"}))
            if block.get("name") != "Read":
                raise _StreamViolation(
                    "TOOL_UNAUTHORIZED",
                    ClaudeCliObservation.OUTCOME_UNRECONCILED,
                    "an unauthorized tool was observed",
                )
            tool_id = block.get("id")
            inputs = block.get("input")
            if not isinstance(tool_id, str) or _TOOL_ID.fullmatch(tool_id) is None:
                raise _StreamViolation(
                    "TOOL_EVENT_INVALID",
                    ClaudeCliObservation.OUTCOME_UNRECONCILED,
                    "tool identity was invalid",
                )
            if not isinstance(inputs, dict) or set(inputs) != {"file_path"}:
                raise _StreamViolation(
                    "READ_SCOPE_DRIFT",
                    ClaudeCliObservation.OUTCOME_UNRECONCILED,
                    "Read input drifted from the sealed file",
                )
            if inputs.get("file_path") != _expected_evidence_path(self.command):
                raise _StreamViolation(
                    "READ_SCOPE_DRIFT",
                    ClaudeCliObservation.OUTCOME_UNRECONCILED,
                    "Read path drifted from the sealed file",
                )
            self.tool_use_id = tool_id
            self.read_count = 1
            self.phase = 2
            return
        if block.get("type") == "text":
            if self.phase != 3:
                raise _StreamViolation(
                    "EVENT_ORDER_INVALID",
                    ClaudeCliObservation.OUTCOME_UNRECONCILED,
                    "assistant text was out of order",
                )
            _expect_keys(block, frozenset({"type", "text"}))
            text = block.get("text")
            if not isinstance(text, str) or _sha256_bytes(text.encode("utf-8")) != self.command.expected_result_sha256:
                raise _StreamViolation(
                    "STRUCTURED_RESULT_MISMATCH",
                    ClaudeCliObservation.OUTCOME_UNRECONCILED,
                    "assistant result did not match the sealed expectation",
                )
            self.phase = 4
            return
        raise _StreamViolation(
            "TOOL_UNAUTHORIZED",
            ClaudeCliObservation.OUTCOME_UNRECONCILED,
            "assistant content type was not accepted",
        )

    def _consume_user(self, value: Mapping[str, Any]) -> None:
        if self.phase != 2:
            raise _StreamViolation(
                "EVENT_ORDER_INVALID",
                ClaudeCliObservation.OUTCOME_UNRECONCILED,
                "tool result was out of order",
            )
        _expect_keys(
            value,
            frozenset(
                {
                    "type",
                    "message",
                    "parent_tool_use_id",
                    "session_id",
                    "uuid",
                    "isSynthetic",
                    "tool_use_result",
                    "priority",
                    "origin",
                    "shouldQuery",
                    "timestamp",
                    "subagent_type",
                    "task_description",
                }
            ),
        )
        _expect_required_keys(
            value,
            frozenset(
                {
                    "type",
                    "message",
                    "parent_tool_use_id",
                    "session_id",
                    "uuid",
                    "tool_use_result",
                }
            ),
            code="TOOL_RESULT_INVALID",
            message="tool result omitted required current-contract fields",
        )
        _expect_session(value, self.command.session_id)
        _expect_uuid(
            value.get("uuid"),
            code="TOOL_RESULT_INVALID",
            message="tool-result UUID was invalid",
        )
        if value.get("parent_tool_use_id") is not None:
            raise _StreamViolation(
                "SUBAGENT_OBSERVED",
                ClaudeCliObservation.OUTCOME_UNRECONCILED,
                "subagent tool result was observed",
            )
        if value.get("isSynthetic") not in (None, False) or any(
            value.get(field) is not None for field in ("subagent_type", "task_description")
        ):
            raise _StreamViolation(
                "TOOL_RESULT_INVALID",
                ClaudeCliObservation.OUTCOME_UNRECONCILED,
                "tool result carried an unapproved synthetic or subagent marker",
            )
        if value.get("priority") not in (None, "now", "next", "later"):
            raise _StreamViolation(
                "TOOL_RESULT_INVALID",
                ClaudeCliObservation.OUTCOME_UNRECONCILED,
                "tool result priority was invalid",
            )
        if value.get("origin") is not None:
            raise _StreamViolation(
                "TOOL_RESULT_INVALID",
                ClaudeCliObservation.OUTCOME_UNRECONCILED,
                "tool result origin was not accepted for a closed prompt",
            )
        if value.get("shouldQuery") is not None and value.get("shouldQuery") is not True:
            raise _StreamViolation(
                "TOOL_RESULT_INVALID",
                ClaudeCliObservation.OUTCOME_UNRECONCILED,
                "tool result query marker was invalid",
            )
        if "timestamp" in value:
            _expect_optional_timestamp(
                value.get("timestamp"),
                code="TOOL_RESULT_INVALID",
                message="tool result timestamp was invalid",
            )
        message = value.get("message")
        if not isinstance(message, dict):
            raise _StreamViolation(
                "TOOL_RESULT_INVALID",
                ClaudeCliObservation.OUTCOME_UNRECONCILED,
                "tool result event was invalid",
            )
        _expect_keys(message, frozenset({"role", "content"}))
        content = message.get("content")
        if (
            message.get("role") != "user"
            or not isinstance(content, list)
            or len(content) != 1
            or not isinstance(content[0], dict)
        ):
            raise _StreamViolation(
                "TOOL_RESULT_INVALID",
                ClaudeCliObservation.OUTCOME_UNRECONCILED,
                "tool result event was invalid",
            )
        block = content[0]
        _expect_keys(block, frozenset({"type", "tool_use_id", "content", "is_error"}))
        if block.get("type") != "tool_result" or block.get("tool_use_id") != self.tool_use_id:
            raise _StreamViolation(
                "TOOL_RESULT_MISMATCH",
                ClaudeCliObservation.OUTCOME_UNRECONCILED,
                "tool result identity did not match Read",
            )
        result_content = block.get("content")
        if block.get("is_error") is not False or not isinstance(result_content, str):
            raise _StreamViolation(
                "TOOL_RESULT_INVALID",
                ClaudeCliObservation.OUTCOME_UNRECONCILED,
                "Read result reported an error",
            )
        structured = value.get("tool_use_result")
        if not isinstance(structured, dict):
            raise _StreamViolation(
                "TOOL_RESULT_INVALID",
                ClaudeCliObservation.OUTCOME_UNRECONCILED,
                "structured Read result was invalid",
            )
        _expect_keys(structured, frozenset({"type", "file", "artifactRead"}))
        file_result = structured.get("file")
        if structured.get("type") != "text" or structured.get("artifactRead") not in (None, False):
            raise _StreamViolation(
                "TOOL_RESULT_INVALID",
                ClaudeCliObservation.OUTCOME_UNRECONCILED,
                "structured Read result type was invalid",
            )
        if not isinstance(file_result, dict):
            raise _StreamViolation(
                "TOOL_RESULT_INVALID",
                ClaudeCliObservation.OUTCOME_UNRECONCILED,
                "structured Read file result was invalid",
            )
        _expect_keys(
            file_result,
            frozenset(
                {
                    "filePath",
                    "content",
                    "numLines",
                    "startLine",
                    "totalLines",
                    "truncatedByTokenCap",
                }
            ),
        )
        _expect_required_keys(
            file_result,
            frozenset({"filePath", "content", "numLines", "startLine", "totalLines"}),
            code="TOOL_RESULT_INVALID",
            message="structured Read result omitted required file fields",
        )
        evidence_content = file_result.get("content")
        expected_path = _expected_evidence_path(self.command)
        expected_lines = len(evidence_content.splitlines()) if isinstance(evidence_content, str) else -1
        if (
            file_result.get("filePath") != expected_path
            or not isinstance(evidence_content, str)
            or file_result.get("numLines") != expected_lines
            or file_result.get("startLine") != 1
            or file_result.get("totalLines") != expected_lines
            or file_result.get("truncatedByTokenCap") not in (None, False)
        ):
            raise _StreamViolation(
                "TOOL_RESULT_MISMATCH",
                ClaudeCliObservation.OUTCOME_UNRECONCILED,
                "structured Read result drifted from the sealed file",
            )
        if _sha256_bytes(evidence_content.encode("utf-8")) != self.command.evidence_sha256:
            raise _StreamViolation(
                "TOOL_RESULT_MISMATCH",
                ClaudeCliObservation.OUTCOME_UNRECONCILED,
                "Read result did not match the sealed evidence",
            )
        if result_content != _numbered_read_content(evidence_content):
            raise _StreamViolation(
                "TOOL_RESULT_INVALID",
                ClaudeCliObservation.OUTCOME_UNRECONCILED,
                "Read result did not carry the pinned line-number representation",
            )
        self.phase = 3

    def _consume_result(self, value: Mapping[str, Any]) -> None:
        if self.phase != 4:
            raise _StreamViolation(
                "EVENT_ORDER_INVALID",
                ClaudeCliObservation.OUTCOME_UNRECONCILED,
                "terminal result was out of order",
            )
        _expect_keys(
            value,
            frozenset(
                {
                    "type",
                    "subtype",
                    "is_error",
                    "duration_ms",
                    "duration_api_ms",
                    "num_turns",
                    "result",
                    "session_id",
                    "total_cost_usd",
                    "usage",
                    "modelUsage",
                    "permission_denials",
                    "uuid",
                    "structured_output",
                    "stop_reason",
                    "ttft_ms",
                    "ttft_stream_ms",
                    "time_to_request_ms",
                    "user_message_uuid",
                    "user_message_uuids",
                    "request_sent_wall_ms",
                    "first_content_frame_ms",
                    "first_stream_post_ms",
                    "first_stream_post_ack_ms",
                    "first_stream_post_wall_ms",
                    "time_to_request_from_spawn_ms",
                    "warm_spare_claimed",
                    "time_origin_ms",
                    "api_error_status",
                    "queued_turn_count",
                    "deferred_tool_use",
                    "terminal_reason",
                    "fast_mode_state",
                    "fast_mode_disabled_reason",
                    "origin",
                }
            ),
        )
        _expect_required_keys(
            value,
            frozenset(
                {
                    "type",
                    "subtype",
                    "duration_ms",
                    "duration_api_ms",
                    "is_error",
                    "num_turns",
                    "result",
                    "stop_reason",
                    "total_cost_usd",
                    "usage",
                    "modelUsage",
                    "permission_denials",
                    "uuid",
                    "session_id",
                }
            ),
            code="RESULT_INVALID",
            message="terminal result omitted required current-contract fields",
        )
        _expect_session(value, self.command.session_id)
        _expect_uuid(
            value.get("uuid"),
            code="RESULT_INVALID",
            message="terminal result UUID was invalid",
        )
        _expect_optional_uuid_echoes(value, code="RESULT_INVALID")
        for field in _RESULT_ELAPSED_TIMING_FIELDS:
            if field not in value:
                continue
            timing = value.get(field)
            if (
                type(timing) not in {int, float}
                or not math.isfinite(float(timing))
                or not 0 <= float(timing) <= 86_400_000
            ):
                raise _StreamViolation(
                    "RESULT_INVALID",
                    ClaudeCliObservation.OUTCOME_UNRECONCILED,
                    "terminal elapsed timing was invalid",
                )
        for field in _RESULT_WALL_TIMING_FIELDS:
            if field not in value:
                continue
            timing = value.get(field)
            if (
                type(timing) not in {int, float}
                or not math.isfinite(float(timing))
                or not 0 <= float(timing) <= 10_000_000_000_000
            ):
                raise _StreamViolation(
                    "RESULT_INVALID",
                    ClaudeCliObservation.OUTCOME_UNRECONCILED,
                    "terminal wall-clock timing was invalid",
                )
        warm_spare = value.get("warm_spare_claimed")
        if warm_spare is not None and warm_spare is not False:
            raise _StreamViolation(
                "RESULT_INVALID",
                ClaudeCliObservation.OUTCOME_UNRECONCILED,
                "terminal warm-spare marker was invalid",
            )
        if value.get("terminal_reason") not in (None, "completed"):
            raise _StreamViolation(
                "RESULT_INVALID",
                ClaudeCliObservation.OUTCOME_UNRECONCILED,
                "terminal reason was invalid",
            )
        _expect_fast_mode_fields(value, code="RESULT_INVALID")
        if "origin" in value:
            raise _StreamViolation(
                "RESULT_INVALID",
                ClaudeCliObservation.OUTCOME_UNRECONCILED,
                "terminal origin was not accepted for a closed prompt",
            )
        subtype = value.get("subtype")
        is_error = value.get("is_error")
        denials = value.get("permission_denials", [])
        if not isinstance(denials, list):
            raise _StreamViolation(
                "PERMISSION_DENIED",
                ClaudeCliObservation.TERMINAL_PROVIDER_FAILURE_OBSERVED,
                "terminal permission evidence was invalid",
            )
        if denials:
            raise _StreamViolation(
                "PERMISSION_DENIED",
                ClaudeCliObservation.TERMINAL_PROVIDER_FAILURE_OBSERVED,
                "terminal result reported a permission denial",
            )
        if subtype != "success" or is_error is not False:
            raise _StreamViolation(
                "PROVIDER_FAILURE",
                ClaudeCliObservation.TERMINAL_PROVIDER_FAILURE_OBSERVED,
                "terminal provider failure was observed",
            )
        if value.get("stop_reason") != "end_turn":
            raise _StreamViolation(
                "RESULT_INVALID",
                ClaudeCliObservation.OUTCOME_UNRECONCILED,
                "terminal stop reason was invalid",
            )
        for field in ("duration_ms", "duration_api_ms"):
            duration = value.get(field)
            if type(duration) is not int or not 0 <= duration <= 86_400_000:
                raise _StreamViolation(
                    "RESULT_INVALID",
                    ClaudeCliObservation.OUTCOME_UNRECONCILED,
                    "terminal duration was invalid",
                )
        if value.get("num_turns") != 1:
            raise _StreamViolation(
                "TURN_COUNT_INVALID",
                ClaudeCliObservation.OUTCOME_UNRECONCILED,
                "terminal turn count was invalid",
            )
        result = value.get("result")
        if not isinstance(result, str) or _sha256_bytes(result.encode("utf-8")) != self.command.expected_result_sha256:
            raise _StreamViolation(
                "STRUCTURED_RESULT_MISMATCH",
                ClaudeCliObservation.OUTCOME_UNRECONCILED,
                "terminal result did not match the sealed expectation",
            )
        cost = value.get("total_cost_usd")
        if type(cost) not in {int, float} or not math.isfinite(float(cost)) or not 0 <= float(cost) <= 1_000:
            raise _StreamViolation(
                "USAGE_INVALID",
                ClaudeCliObservation.OUTCOME_UNRECONCILED,
                "terminal cost estimate was invalid",
            )
        (
            self.input_tokens,
            self.output_tokens,
            cache_creation_input_tokens,
            cache_read_input_tokens,
        ) = _consume_usage_payload(value.get("usage"))
        _validate_model_usage(
            value.get("modelUsage"),
            command=self.command,
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
            cache_creation_input_tokens=cache_creation_input_tokens,
            cache_read_input_tokens=cache_read_input_tokens,
            total_cost_usd=float(cost),
        )
        if value.get("api_error_status") is not None or value.get("queued_turn_count") not in (None, 0):
            raise _StreamViolation(
                "RESULT_INVALID",
                ClaudeCliObservation.OUTCOME_UNRECONCILED,
                "terminal result carried an error or queued-turn marker",
            )
        if value.get("deferred_tool_use") is not None:
            raise _StreamViolation(
                "TOOL_UNAUTHORIZED",
                ClaudeCliObservation.OUTCOME_UNRECONCILED,
                "deferred tool use was observed",
            )
        structured_output = value.get("structured_output")
        if structured_output is not None:
            try:
                expected_structured = json.loads(result)
            except json.JSONDecodeError:  # pragma: no cover - result is compiler-derived JSON
                expected_structured = None
            if structured_output != expected_structured:
                raise _StreamViolation(
                    "STRUCTURED_RESULT_MISMATCH",
                    ClaudeCliObservation.OUTCOME_UNRECONCILED,
                    "structured output contradicted the terminal result",
                )
        self.cost_microusd = int(round(float(cost) * 1_000_000))
        self.result_sha256 = self.command.expected_result_sha256
        self.terminal = True
        self.phase = 5

    def finalize(self) -> None:
        if not self.terminal:
            raise _StreamViolation(
                "TERMINAL_RESULT_MISSING",
                ClaudeCliObservation.OUTCOME_UNRECONCILED,
                "terminal result was missing",
            )
        if self.read_count != 1 or self.submission_count != 1:
            raise _StreamViolation(
                "READ_COUNT_INVALID",
                ClaudeCliObservation.OUTCOME_UNRECONCILED,
                "one-Read one-submission invariant was not satisfied",
            )


def _contains_sensitive_bytes(
    value: bytes,
    *,
    allowed_private_locators: Sequence[bytes] = (),
) -> str | None:
    if any(marker in value for marker in _SENSITIVE_BYTES) or _EMAIL_BYTES.search(value):
        return "SENSITIVE_OUTPUT"
    locator_checked = value
    for allowed in sorted(allowed_private_locators, key=len, reverse=True):
        if allowed:
            locator_checked = locator_checked.replace(allowed, b"<sealed-private-path>")
    if any(marker in locator_checked for marker in _PRIVATE_LOCATOR_BYTES):
        return "PRIVATE_LOCATOR_OUTPUT"
    return None


def _group_status(pgid: int) -> str:
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return "EMPTY"
    except OSError:
        return "UNKNOWN"
    return "ALIVE"


def _wait_group_empty(pgid: int, timeout: float) -> bool:
    deadline = time.monotonic() + max(timeout, 0.01)
    while time.monotonic() < deadline:
        if _group_status(pgid) == "EMPTY":
            return True
        time.sleep(0.01)
    return _group_status(pgid) == "EMPTY"


def _read_fd_bytes(descriptor: int, *, maximum: int) -> bytes:
    chunks: list[bytes] = []
    offset = 0
    while offset <= maximum:
        chunk = os.pread(descriptor, min(65_536, maximum + 1 - offset), offset)
        if not chunk:
            break
        chunks.append(chunk)
        offset += len(chunk)
        if offset > maximum:
            break
    value = b"".join(chunks)
    if not value or len(value) > maximum:
        raise OSError("bounded descriptor content unavailable")
    return value


def _open_bound_evidence(command: ClaudeCliCommand) -> int:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor: int | None = None
    try:
        descriptor = os.open(_expected_evidence_path(command), flags)
        before = os.fstat(descriptor)
        evidence_bytes = os.pread(descriptor, 65_537, 0)
        after = os.fstat(descriptor)
        expected_identity = (
            command.evidence_device,
            command.evidence_inode,
            command.evidence_uid,
            command.evidence_mode,
            command.evidence_size,
            command.evidence_mtime_ns,
        )
        if (
            not stat.S_ISREG(before.st_mode)
            or (
                before.st_dev,
                before.st_ino,
                before.st_uid,
                before.st_mode,
                before.st_size,
                before.st_mtime_ns,
            )
            != expected_identity
            or (
                after.st_dev,
                after.st_ino,
                after.st_uid,
                after.st_mode,
                after.st_size,
                after.st_mtime_ns,
            )
            != expected_identity
            or len(evidence_bytes) > 65_536
            or _sha256_bytes(evidence_bytes) != command.evidence_sha256
        ):
            raise OSError("sealed evidence identity drifted")
        return descriptor
    except OSError:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
        raise _fail_before_start(
            "EVIDENCE_DRIFT",
            "sealed evidence descriptor could not be retained",
        ) from None


def _open_bound_binary(command: ClaudeCliCommand, *, scratch: Path) -> int:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor: int | None = None
    writer: int | None = None
    sealed_descriptor: int | None = None
    sealed_path = scratch / f".pf1-reviewed-fake-{uuid.uuid4().hex}"
    try:
        descriptor = os.open(command.argv[0], flags)
        info = os.fstat(descriptor)
        binary_bytes = _read_fd_bytes(descriptor, maximum=_MAX_BINARY_BYTES)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_dev != command.binary_device
            or info.st_ino != command.binary_inode
            or info.st_uid != command.binary_uid
            or info.st_mode != command.binary_mode
            or info.st_size != command.binary_size
            or info.st_mtime_ns != command.binary_mtime_ns
            or _sha256_bytes(binary_bytes) != command.binary_sha256
        ):
            raise OSError("source binary identity drifted")
        writer = os.open(
            sealed_path,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
            0o400,
        )
        offset = 0
        while offset < len(binary_bytes):
            written = os.write(writer, binary_bytes[offset:])
            if written <= 0:
                raise OSError("sealed binary write stalled")
            offset += written
        os.fsync(writer)
        sealed_descriptor = os.open(sealed_path, flags)
        sealed_info = os.fstat(sealed_descriptor)
        sealed_bytes = _read_fd_bytes(sealed_descriptor, maximum=_MAX_BINARY_BYTES)
        if (
            not stat.S_ISREG(sealed_info.st_mode)
            or sealed_info.st_uid != os.getuid()
            or stat.S_IMODE(sealed_info.st_mode) != 0o400
            or _sha256_bytes(sealed_bytes) != command.binary_sha256
        ):
            raise OSError("sealed binary identity invalid")
        sealed_path.unlink()
        os.close(writer)
        writer = None
        os.close(descriptor)
        descriptor = None
        return sealed_descriptor
    except OSError:
        for open_descriptor in (sealed_descriptor, writer, descriptor):
            if open_descriptor is not None:
                try:
                    os.close(open_descriptor)
                except OSError:
                    pass
        try:
            sealed_path.unlink()
        except OSError:
            pass
        raise _fail_before_start(
            "BINARY_DRIFT",
            "reviewed fake executable could not be sealed",
        ) from None


def _bound_fake_state(
    *, run_nonce: str, runner_pid: int, spawn_not_before_ns: int
) -> dict[str, Any]:
    return {
        "schema": _BOUND_STATE_SCHEMA,
        "run_nonce": run_nonce,
        "runner_pid": runner_pid,
        "spawn_not_before_ns": spawn_not_before_ns,
        "owner_pid": None,
        "owner_parent_pid": None,
        "owner_started_ns": None,
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


def _write_json_fd(descriptor: int, value: Mapping[str, Any]) -> None:
    encoded = (_canonical_json(dict(value)) + "\n").encode("ascii")
    os.ftruncate(descriptor, 0)
    offset = 0
    while offset < len(encoded):
        written = os.pwrite(descriptor, encoded[offset:], offset)
        if written <= 0:
            raise OSError("state descriptor write stalled")
        offset += written
    os.fsync(descriptor)


def _create_bound_fake_state(
    state_path: Path,
    *,
    run_nonce: str,
    runner_pid: int,
    spawn_not_before_ns: int,
) -> int:
    flags = (
        os.O_RDWR
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        descriptor = os.open(state_path, flags, 0o600)
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_uid != os.getuid()
        ):
            raise OSError("state descriptor identity invalid")
        _write_json_fd(
            descriptor,
            _bound_fake_state(
                run_nonce=run_nonce,
                runner_pid=runner_pid,
                spawn_not_before_ns=spawn_not_before_ns,
            ),
        )
        return descriptor
    except FileExistsError:
        raise _fail_before_start("FAKE_STATE_EXISTS", "fake control state path already exists") from None
    except OSError:
        try:
            os.close(descriptor)
        except (OSError, UnboundLocalError):
            pass
        raise _fail_before_start("FAKE_STATE_UNAVAILABLE", "exclusive fake state could not be created") from None


def _unlink_bound_state(state_path: Path, descriptor: int) -> None:
    try:
        path_info = state_path.stat()
        descriptor_info = os.fstat(descriptor)
        if (
            path_info.st_dev == descriptor_info.st_dev
            and path_info.st_ino == descriptor_info.st_ino
        ):
            state_path.unlink()
    except OSError:
        pass


def _read_bound_fake_state(descriptor: int) -> dict[str, Any] | None:
    try:
        encoded = _read_fd_bytes(descriptor, maximum=65_536)
        value = json.loads(encoded.decode("ascii", errors="strict"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


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
    start_token = parts[3]
    if observed_pid != pid or not start_token or len(start_token.encode("ascii", errors="ignore")) > 128:
        return None
    return observed_pid, parent_pid, pgid, start_token


def _tree_fingerprint(root: Path) -> str | None:
    """Return a bounded metadata fingerprint without retaining private names."""

    digest = hashlib.sha256()
    pending: list[tuple[Path, str]] = [(root, "")]
    count = 0
    try:
        while pending:
            directory, prefix = pending.pop()
            with os.scandir(directory) as iterator:
                entries = sorted(iterator, key=lambda entry: entry.name)
            for entry in entries:
                count += 1
                if count > 512:
                    return None
                relative = f"{prefix}/{entry.name}" if prefix else entry.name
                info = entry.stat(follow_symlinks=False)
                digest.update(relative.encode("utf-8", errors="surrogateescape"))
                digest.update(
                    f"\0{info.st_mode}\0{info.st_size}\0{info.st_mtime_ns}\0".encode("ascii")
                )
                if stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode):
                    pending.append((Path(entry.path), relative))
    except (OSError, UnicodeError):
        return None
    return digest.hexdigest()


def _marked_escaped_groups(
    state_descriptor: int,
    *,
    run_nonce: str,
    runner_pid: int,
    leader_pid: int,
    spawn_not_before_ns: int,
) -> tuple[tuple[int, ...], bool]:
    value = _read_bound_fake_state(state_descriptor)
    expected_keys = set(
        _bound_fake_state(
            run_nonce=run_nonce,
            runner_pid=runner_pid,
            spawn_not_before_ns=spawn_not_before_ns,
        )
    )
    if value is None or set(value) != expected_keys:
        return (), False
    children = value.get("children")
    escaped = value.get("escaped_children")
    counters = (
        value.get("mcp_calls"),
        value.get("network_attempts"),
        value.get("reads"),
        value.get("shells"),
        value.get("starts"),
        value.get("subagents"),
        value.get("submissions"),
        value.get("writes"),
    )
    if (
        value.get("schema") != _BOUND_STATE_SCHEMA
        or value.get("run_nonce") != run_nonce
        or value.get("runner_pid") != runner_pid
        or value.get("spawn_not_before_ns") != spawn_not_before_ns
        or not isinstance(children, list)
        or len(children) > 16
        or any(type(pid) is not int or pid <= 1 for pid in children)
        or not isinstance(escaped, list)
        or len(escaped) > 16
        or any(type(count) is not int or count < 0 for count in counters)
    ):
        return (), False
    owner_pid = value.get("owner_pid")
    owner_parent_pid = value.get("owner_parent_pid")
    owner_started_ns = value.get("owner_started_ns")
    if owner_pid is None and owner_parent_pid is None and owner_started_ns is None:
        return ((), True) if not escaped else ((), False)
    if (
        owner_pid != leader_pid
        or owner_parent_pid != runner_pid
        or type(owner_started_ns) is not int
        or owner_started_ns < spawn_not_before_ns
        or owner_started_ns > time.monotonic_ns()
    ):
        return (), False
    groups: list[int] = []
    for record in escaped:
        if not isinstance(record, dict) or set(record) != {
            "pid",
            "pgid",
            "parent_pid",
            "parent_started_ns",
            "spawned_at_ns",
            "start_token",
        }:
            return (), False
        pid = record.get("pid")
        pgid = record.get("pgid")
        spawned_at_ns = record.get("spawned_at_ns")
        if (
            type(pid) is not int
            or type(pgid) is not int
            or pid <= 1
            or pid != pgid
            or pid == runner_pid
            or record.get("parent_pid") != leader_pid
            or record.get("parent_started_ns") != owner_started_ns
            or type(spawned_at_ns) is not int
            or not owner_started_ns <= spawned_at_ns <= time.monotonic_ns()
            or not isinstance(record.get("start_token"), str)
        ):
            return (), False
        identity = _process_identity(pid)
        if (
            identity is None
            or identity[0] != pid
            or identity[2] != pgid
            or identity[3] != record.get("start_token")
        ):
            return (), False
        groups.append(pgid)
    return tuple(groups), True


def _signal_group(pgid: int, sig: signal.Signals) -> bool:
    if pgid <= 1 or pgid == os.getpgrp():
        return False
    try:
        os.killpg(pgid, sig)
        return True
    except ProcessLookupError:
        return False
    except OSError:
        return False


def _cleanup_process(
    process: subprocess.Popen[bytes],
    *,
    pgid: int,
    group_identity_proven: bool,
    grace_seconds: float,
    force_termination: bool,
    reader_closed: bool,
    scratch: Path,
    scratch_before: str,
    fake_state_descriptor: int,
    fake_run_nonce: str,
    runner_pid: int,
    spawn_not_before_ns: int,
) -> ClaudeCliCleanupReceipt:
    term_sent = False
    kill_sent = False
    residue: list[str] = []
    if not group_identity_proven:
        residue.append("PROCESS_GROUP_IDENTITY_UNPROVEN")
    group_status = _group_status(pgid)
    if force_termination and group_status != "EMPTY":
        term_sent = _signal_group(pgid, signal.SIGTERM) or term_sent
    if process.poll() is None:
        try:
            process.wait(timeout=grace_seconds)
        except subprocess.TimeoutExpired:
            pass
    if _group_status(pgid) != "EMPTY":
        if not term_sent:
            term_sent = _signal_group(pgid, signal.SIGTERM) or term_sent
        _wait_group_empty(pgid, grace_seconds)
    if _group_status(pgid) != "EMPTY":
        kill_sent = _signal_group(pgid, signal.SIGKILL) or kill_sent
    if process.poll() is None:
        try:
            process.wait(timeout=max(grace_seconds, 1.0))
        except subprocess.TimeoutExpired:
            try:
                process.kill()
                kill_sent = True
            except OSError:
                pass
            try:
                process.wait(timeout=max(grace_seconds, 1.0))
            except subprocess.TimeoutExpired:
                residue.append("LEADER_NOT_REAPED")
    group_empty = _wait_group_empty(pgid, max(grace_seconds, 1.0))
    if not group_empty:
        residue.append("PROCESS_GROUP_NOT_EMPTY")

    escaped_groups, marks_proven = _marked_escaped_groups(
        fake_state_descriptor,
        run_nonce=fake_run_nonce,
        runner_pid=runner_pid,
        leader_pid=process.pid,
        spawn_not_before_ns=spawn_not_before_ns,
    )
    if not marks_proven:
        residue.append("MARKED_DESCENDANTS_UNPROVEN")
    for escaped_pgid in escaped_groups:
        if _group_status(escaped_pgid) != "EMPTY":
            term_sent = _signal_group(escaped_pgid, signal.SIGTERM) or term_sent
    for escaped_pgid in escaped_groups:
        _wait_group_empty(escaped_pgid, grace_seconds)
        if _group_status(escaped_pgid) != "EMPTY":
            kill_sent = _signal_group(escaped_pgid, signal.SIGKILL) or kill_sent
    marked_empty = marks_proven and all(
        _wait_group_empty(escaped_pgid, max(grace_seconds, 1.0))
        for escaped_pgid in escaped_groups
    )
    if not marked_empty and "MARKED_DESCENDANTS_UNPROVEN" not in residue:
        residue.append("MARKED_DESCENDANTS_NOT_EMPTY")

    leader_reaped = process.poll() is not None
    for stream in (process.stdout, process.stderr):
        if stream is not None and not stream.closed:
            try:
                stream.close()
            except OSError:
                residue.append("PIPE_CLOSE_UNPROVEN")
    scratch_after = _tree_fingerprint(scratch)
    scratch_empty = scratch_after is not None and scratch_after == scratch_before
    if not scratch_empty:
        residue.append("SCRATCH_RESIDUE" if scratch_after is not None else "SCRATCH_STATE_UNPROVEN")
    if not reader_closed:
        residue.append("READER_NOT_CLOSED")
    return ClaudeCliCleanupReceipt(
        process_group_empty=group_empty,
        marked_descendants_empty=marked_empty,
        leader_reaped=leader_reaped,
        stdin_closed=True,
        stdout_closed=process.stdout is None or process.stdout.closed,
        stderr_closed=process.stderr is None or process.stderr.closed,
        reader_closed=reader_closed,
        scratch_empty=scratch_empty,
        term_sent=term_sent,
        kill_sent=kill_sent,
        residue_rows=tuple(dict.fromkeys(residue)),
    )


def _validate_command_integrity(command: ClaudeCliCommand) -> None:
    if not isinstance(command, ClaudeCliCommand):
        raise _fail_before_start("COMMAND_INVALID", "Claude command is invalid")
    relative = _validate_safe_relative_path(command.evidence_relative_path)
    settings_json = _closed_settings_json(command.evidence_relative_path)
    expected_argv = _build_argv(
        binary=command.argv[0] if command.argv else "",
        version=command.version,
        model=command.model,
        session_id=command.session_id,
        prompt=command.prompt,
        settings_json=settings_json,
    )
    expected_environment = (
        ("HOME", command.isolated_home),
        ("TMPDIR", command.isolated_tmp),
        *_SAFE_ENVIRONMENT,
        ("API_TIMEOUT_MS", str(command.api_timeout_ms)),
    )
    if (
        command.argv != expected_argv
        or command.argv_sha256 != _canonical_sha256(list(expected_argv))
        or command.settings_sha256 != _sha256_bytes(settings_json.encode("utf-8"))
    ):
        raise _fail_before_start("COMMAND_DRIFT", "compiled argv integrity check failed")
    if command.environment != expected_environment or command.environment_sha256 != _environment_digest(
        expected_environment
    ):
        raise _fail_before_start("ENVIRONMENT_DRIFT", "compiled environment integrity check failed")
    try:
        binary_path = Path(command.argv[0])
        binary_info = binary_path.lstat()
        binary = binary_path.resolve(strict=True)
        binary_bytes = binary.read_bytes()
    except OSError:
        raise _fail_before_start(
            "BINARY_DRIFT",
            "reviewed fake executable identity became unavailable",
        ) from None
    try:
        workspace = Path(command.working_directory).resolve(strict=True)
        home = Path(command.isolated_home).resolve(strict=True)
        scratch = Path(command.isolated_tmp).resolve(strict=True)
    except OSError:
        raise _fail_before_start("COMMAND_DRIFT", "compiled path identity became unavailable") from None
    evidence = workspace.joinpath(*relative.parts)
    try:
        evidence_info = evidence.lstat()
        resolved_evidence = evidence.resolve(strict=True)
        evidence_bytes = resolved_evidence.read_bytes()
    except OSError:
        raise _fail_before_start(
            "EVIDENCE_DRIFT",
            "sealed evidence identity became unavailable",
        ) from None
    if (
        stat.S_ISLNK(binary_info.st_mode)
        or not stat.S_ISREG(binary_info.st_mode)
        or not os.access(binary, os.X_OK)
        or not binary_bytes
        or len(binary_bytes) > _MAX_BINARY_BYTES
        or str(binary) != command.argv[0]
        or str(workspace) != command.working_directory
        or str(home) != command.isolated_home
        or str(scratch) != command.isolated_tmp
        or home == _trusted_native_home()
        or home == scratch
        or workspace in home.parents
        or workspace in scratch.parents
    ):
        raise _fail_before_start("COMMAND_DRIFT", "compiled path identity drifted")
    if (
        stat.S_ISLNK(evidence_info.st_mode)
        or not stat.S_ISREG(evidence_info.st_mode)
        or resolved_evidence != evidence
        or workspace not in resolved_evidence.parents
        or len(evidence_bytes) > 65_536
    ):
        raise _fail_before_start("EVIDENCE_DRIFT", "sealed evidence path identity drifted")
    if (
        _sha256_bytes(binary_bytes) != command.binary_sha256
        or binary_info.st_dev != command.binary_device
        or binary_info.st_ino != command.binary_inode
        or binary_info.st_uid != command.binary_uid
        or binary_info.st_mode != command.binary_mode
        or binary_info.st_size != command.binary_size
        or binary_info.st_mtime_ns != command.binary_mtime_ns
    ):
        raise _fail_before_start("BINARY_DRIFT", "reviewed fake executable identity drifted")
    if (
        _sha256_bytes(evidence_bytes) != command.evidence_sha256
        or evidence_info.st_dev != command.evidence_device
        or evidence_info.st_ino != command.evidence_inode
        or evidence_info.st_uid != command.evidence_uid
        or evidence_info.st_mode != command.evidence_mode
        or evidence_info.st_size != command.evidence_size
        or evidence_info.st_mtime_ns != command.evidence_mtime_ns
    ):
        raise _fail_before_start("EVIDENCE_DRIFT", "sealed evidence file drifted before process start")
    if command.prompt != _derived_prompt(command.evidence_relative_path, command.evidence_sha256):
        raise _fail_before_start("COMMAND_DRIFT", "compiled prompt binding drifted")
    if command.expected_result_sha256 != _sha256_bytes(
        _derived_result(command.evidence_sha256).encode("utf-8")
    ):
        raise _fail_before_start("COMMAND_DRIFT", "compiled result binding drifted")


def _committed_fake_path() -> Path:
    return Path(__file__).resolve().parents[1] / "scripts" / "ohf" / "fake_claude_cli.py"


def _validate_fake_controls(
    command: ClaudeCliCommand,
    fake_controls: Mapping[str, str] | None,
) -> dict[str, str]:
    if fake_controls is None:
        raise _fail_before_start(
            "FAKE_ONLY_EFFECT_CEILING",
            "PF1-F0 is a fake-only subprocess falsifier",
        )
    expected_fake = _committed_fake_path()
    try:
        binary = Path(command.argv[0]).resolve(strict=True)
        expected_fake = expected_fake.resolve(strict=True)
    except OSError:
        raise _fail_before_start(
            "FAKE_CONTROL_REFUSED",
            "fake controls require the committed fake executable",
        ) from None
    if binary != expected_fake:
        raise _fail_before_start("FAKE_CONTROL_REFUSED", "fake controls require the committed fake executable")
    if not isinstance(fake_controls, Mapping) or not fake_controls:
        raise _fail_before_start("FAKE_CONTROL_INVALID", "fake control mapping is invalid")
    values = dict(fake_controls)
    if set(values) - _FAKE_CONTROL_KEYS or any(
        not isinstance(key, str)
        or not isinstance(value, str)
        or not value
        or "\x00" in value
        or len(value.encode("utf-8")) > 1_024
        for key, value in values.items()
    ):
        raise _fail_before_start("FAKE_CONTROL_INVALID", "fake control mapping contains an unapproved value")
    scenario = values.get("MMX_FAKE_CLAUDE_SCENARIO")
    if scenario is not None and _SAFE_FAKE_SCENARIO.fullmatch(scenario) is None:
        raise _fail_before_start("FAKE_CONTROL_INVALID", "fake control scenario is invalid")
    version = values.get("MMX_FAKE_CLAUDE_VERSION")
    if version is not None and version != str(command.version):
        raise _fail_before_start("FAKE_CONTROL_INVALID", "fake control version drifted")
    maximum = values.get("MMX_FAKE_CLAUDE_MAX_STARTS")
    if maximum is not None and (not maximum.isascii() or not maximum.isdigit() or int(maximum) < 1):
        raise _fail_before_start("FAKE_CONTROL_INVALID", "fake control start bound is invalid")
    state = values.get("MMX_FAKE_CLAUDE_STATE_FILE")
    if state is None:
        raise _fail_before_start("FAKE_CONTROL_INVALID", "fake control state path is required")
    state_path = Path(state)
    workspace = Path(command.working_directory)
    try:
        parent_info = state_path.parent.lstat()
        resolved_parent = state_path.parent.resolve(strict=True)
    except OSError:
        raise _fail_before_start("FAKE_CONTROL_INVALID", "fake control state path is invalid") from None
    if (
        not state_path.is_absolute()
        or stat.S_ISLNK(parent_info.st_mode)
        or not stat.S_ISDIR(parent_info.st_mode)
        or resolved_parent != state_path.parent
        or state_path == workspace
        or workspace in state_path.parents
    ):
        raise _fail_before_start("FAKE_CONTROL_INVALID", "fake control state path is invalid")
    if state_path.exists() or state_path.is_symlink():
        raise _fail_before_start("FAKE_STATE_EXISTS", "fake control state path already exists")
    return values


class ClaudeCliRunner:
    """One-shot foreground runner; an instance can never start twice."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._started = False

    def _mark_started_once(self) -> None:
        with self._lock:
            if self._started:
                raise _fail_before_start(
                    "SECOND_INVOCATION_REFUSED",
                    "a Claude CLI runner cannot start a second invocation",
                )
            self._started = True

    def run(
        self,
        command: ClaudeCliCommand,
        *,
        cancel_event: threading.Event | None = None,
        fake_controls: Mapping[str, str] | None = None,
    ) -> ClaudeCliRunReceipt:
        self._mark_started_once()
        _validate_command_integrity(command)
        controls = _validate_fake_controls(command, fake_controls)
        if cancel_event is not None and cancel_event.is_set():
            raise _fail_before_start("CANCELLED_BEFORE_START", "invocation was cancelled before process start")

        scratch = Path(command.isolated_tmp)
        scratch_before = _tree_fingerprint(scratch)
        if scratch_before is None:
            raise _fail_before_start(
                "SCRATCH_BASELINE_UNPROVEN",
                "isolated temp directory baseline could not be proven",
            )
        fake_state_path = Path(controls["MMX_FAKE_CLAUDE_STATE_FILE"])
        runner_pid = os.getpid()
        run_nonce = str(uuid.uuid4())
        spawn_not_before_ns = time.monotonic_ns()
        evidence_descriptor = _open_bound_evidence(command)
        try:
            binary_descriptor = _open_bound_binary(command, scratch=scratch)
        except BaseException:
            os.close(evidence_descriptor)
            raise
        try:
            state_descriptor = _create_bound_fake_state(
                fake_state_path,
                run_nonce=run_nonce,
                runner_pid=runner_pid,
                spawn_not_before_ns=spawn_not_before_ns,
            )
        except BaseException:
            os.close(binary_descriptor)
            os.close(evidence_descriptor)
            raise
        environment = dict(command.environment)
        environment.update(controls)
        environment.update(
            {
                "MMX_FAKE_CLAUDE_STATE_FD": str(state_descriptor),
                "MMX_FAKE_CLAUDE_RUN_NONCE": run_nonce,
                "MMX_FAKE_CLAUDE_RUNNER_PID": str(runner_pid),
                "MMX_FAKE_CLAUDE_SPAWN_NOT_BEFORE_NS": str(spawn_not_before_ns),
                "MMX_FAKE_CLAUDE_EVIDENCE_FD": str(evidence_descriptor),
                "MMX_FAKE_CLAUDE_EVIDENCE_DEVICE": str(command.evidence_device),
                "MMX_FAKE_CLAUDE_EVIDENCE_INODE": str(command.evidence_inode),
                "MMX_FAKE_CLAUDE_EVIDENCE_UID": str(command.evidence_uid),
                "MMX_FAKE_CLAUDE_EVIDENCE_MODE": str(command.evidence_mode),
                "MMX_FAKE_CLAUDE_EVIDENCE_SIZE": str(command.evidence_size),
                "MMX_FAKE_CLAUDE_EVIDENCE_MTIME_NS": str(command.evidence_mtime_ns),
            }
        )
        try:
            process = subprocess.Popen(
                (sys.executable, f"/dev/fd/{binary_descriptor}", *command.argv[1:]),
                cwd=command.working_directory,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,
                close_fds=True,
                pass_fds=(binary_descriptor, state_descriptor, evidence_descriptor),
                bufsize=0,
            )
        except OSError:
            os.close(binary_descriptor)
            os.close(evidence_descriptor)
            _unlink_bound_state(fake_state_path, state_descriptor)
            os.close(state_descriptor)
            raise _fail_before_start(
                "PROCESS_START_FAILED",
                "Claude CLI process could not be started",
            ) from None
        except BaseException:
            os.close(binary_descriptor)
            os.close(evidence_descriptor)
            _unlink_bound_state(fake_state_path, state_descriptor)
            os.close(state_descriptor)
            raise
        os.close(binary_descriptor)
        os.close(evidence_descriptor)

        # Cleanup ownership begins immediately after Popen.  The new-session
        # candidate group is the leader pid even when getpgid cannot attest it.
        pgid = process.pid
        group_identity_proven = False
        reader_closed = True
        selector: selectors.BaseSelector | None = None
        parser = _StreamParser(command)
        stream_digest = hashlib.sha256()
        allowed_stdout_locators = (
            command.working_directory.encode("utf-8"),
            _expected_evidence_path(command).encode("utf-8"),
        )
        returncode: int | None = None
        failure: tuple[str, ClaudeCliObservation, str] | None = None
        try:
            try:
                observed_pgid = os.getpgid(process.pid)
            except OSError:
                failure = (
                    "PROCESS_GROUP_UNPROVEN",
                    ClaudeCliObservation.OUTCOME_UNRECONCILED,
                    "Claude CLI process-group identity was unavailable",
                )
            else:
                group_identity_proven = (
                    observed_pgid == process.pid and observed_pgid != os.getpgrp()
                )
                if not group_identity_proven:
                    failure = (
                        "PROCESS_GROUP_UNPROVEN",
                        ClaudeCliObservation.OUTCOME_UNRECONCILED,
                        "Claude CLI process was not isolated in its own group",
                    )

            if failure is None and (process.stdout is None or process.stderr is None):
                failure = (
                    "PIPE_START_FAILED",
                    ClaudeCliObservation.OUTCOME_UNRECONCILED,
                    "Claude CLI stream pipes were unavailable",
                )

            if failure is None:
                stdout_buffer = bytearray()
                stdout_total = 0
                stderr_total = 0
                selector = selectors.DefaultSelector()
                reader_closed = False
                try:
                    selector.register(process.stdout, selectors.EVENT_READ, "stdout")
                    selector.register(process.stderr, selectors.EVENT_READ, "stderr")
                    started_at = time.monotonic()
                    last_activity = started_at
                    while selector.get_map():
                        now = time.monotonic()
                        if cancel_event is not None and cancel_event.is_set():
                            raise _StreamViolation(
                                "CANCELLED_AFTER_START",
                                ClaudeCliObservation.OUTCOME_UNRECONCILED,
                                "invocation was cancelled after process start",
                            )
                        if now - started_at >= command.absolute_timeout_seconds:
                            raise _StreamViolation(
                                "ABSOLUTE_TIMEOUT",
                                ClaudeCliObservation.OUTCOME_UNRECONCILED,
                                "Claude CLI absolute deadline expired",
                            )
                        if now - last_activity >= command.idle_timeout_seconds:
                            raise _StreamViolation(
                                "IDLE_TIMEOUT",
                                ClaudeCliObservation.OUTCOME_UNRECONCILED,
                                "Claude CLI idle deadline expired",
                            )
                        wait_for = min(
                            0.05,
                            command.absolute_timeout_seconds - (now - started_at),
                            command.idle_timeout_seconds - (now - last_activity),
                        )
                        for key, _ in selector.select(timeout=max(wait_for, 0.001)):
                            stream = key.fileobj
                            try:
                                chunk = os.read(stream.fileno(), 65_536)
                            except BlockingIOError:  # pragma: no cover - readiness race
                                continue
                            if not chunk:
                                selector.unregister(stream)
                                continue
                            last_activity = time.monotonic()
                            sensitive_code = _contains_sensitive_bytes(
                                chunk,
                                allowed_private_locators=_PRIVATE_LOCATOR_BYTES
                                if key.data == "stdout"
                                else (),
                            )
                            if sensitive_code is not None:
                                raise _StreamViolation(
                                    sensitive_code,
                                    ClaudeCliObservation.OUTCOME_UNRECONCILED,
                                    "provider output contained sensitive material"
                                    if sensitive_code == "SENSITIVE_OUTPUT"
                                    else "provider output contained a private locator",
                                )
                            if key.data == "stderr":
                                stderr_total += len(chunk)
                                raise _StreamViolation(
                                    "STDERR_BYTE_LIMIT"
                                    if stderr_total > command.max_stderr_bytes
                                    else "STDERR_NOT_EMPTY",
                                    ClaudeCliObservation.OUTCOME_UNRECONCILED,
                                    "stderr exceeded its byte bound"
                                    if stderr_total > command.max_stderr_bytes
                                    else "stderr was not empty",
                                )
                            stdout_total += len(chunk)
                            if stdout_total > command.max_stdout_bytes:
                                raise _StreamViolation(
                                    "STDOUT_BYTE_LIMIT",
                                    ClaudeCliObservation.OUTCOME_UNRECONCILED,
                                    "stdout exceeded its byte bound",
                                )
                            stdout_buffer.extend(chunk)
                            while True:
                                newline = stdout_buffer.find(b"\n")
                                if newline < 0:
                                    break
                                raw_line = bytes(stdout_buffer[:newline])
                                del stdout_buffer[: newline + 1]
                                if len(raw_line) > command.max_line_bytes:
                                    raise _StreamViolation(
                                        "STREAM_LINE_LIMIT",
                                        ClaudeCliObservation.OUTCOME_UNRECONCILED,
                                        "stream line exceeded its byte bound",
                                    )
                                sensitive_code = _contains_sensitive_bytes(
                                    raw_line,
                                    allowed_private_locators=allowed_stdout_locators,
                                )
                                if sensitive_code is not None:
                                    raise _StreamViolation(
                                        sensitive_code,
                                        ClaudeCliObservation.OUTCOME_UNRECONCILED,
                                        "provider output contained sensitive material"
                                        if sensitive_code == "SENSITIVE_OUTPUT"
                                        else "provider output contained a private locator",
                                )
                                parser.consume(raw_line)
                                stream_digest.update(parser.events[-1].sha256.encode("ascii"))
                                stream_digest.update(b"\n")
                            if len(stdout_buffer) > command.max_line_bytes:
                                raise _StreamViolation(
                                    "STREAM_LINE_LIMIT",
                                    ClaudeCliObservation.OUTCOME_UNRECONCILED,
                                    "stream line exceeded its byte bound",
                                )
                    if stdout_buffer:
                        raise _StreamViolation(
                            "STREAM_LINE_UNTERMINATED",
                            ClaudeCliObservation.OUTCOME_UNRECONCILED,
                            "stream ended with an unterminated line",
                        )
                    parser.finalize()
                finally:
                    try:
                        selector.close()
                        reader_closed = True
                    except Exception:
                        reader_closed = False

                try:
                    returncode = process.wait(
                        timeout=max(command.terminate_grace_seconds, 1.0)
                    )
                except subprocess.TimeoutExpired:
                    raise _StreamViolation(
                        "PROCESS_EXIT_TIMEOUT",
                        ClaudeCliObservation.OUTCOME_UNRECONCILED,
                        "Claude CLI did not exit after its terminal result",
                    ) from None
                if returncode != 0:
                    raise _StreamViolation(
                        "PROCESS_EXIT_INVALID",
                        ClaudeCliObservation.OUTCOME_UNRECONCILED,
                        "Claude CLI exit status contradicted its terminal result",
                    )
        except _StreamViolation as exc:
            failure = (exc.code, exc.observation, exc.message)
        except Exception:
            failure = (
                "PROCESS_OBSERVATION_FAILED",
                ClaudeCliObservation.OUTCOME_UNRECONCILED,
                "Claude CLI process observation failed",
            )
        finally:
            if selector is not None and not reader_closed:
                try:
                    selector.close()
                    reader_closed = True
                except Exception:
                    reader_closed = False
            try:
                cleanup = _cleanup_process(
                    process,
                    pgid=pgid,
                    group_identity_proven=group_identity_proven,
                    grace_seconds=command.terminate_grace_seconds,
                    force_termination=failure is not None or process.poll() is None,
                    reader_closed=reader_closed,
                    scratch=scratch,
                    scratch_before=scratch_before,
                    fake_state_descriptor=state_descriptor,
                    fake_run_nonce=run_nonce,
                    runner_pid=runner_pid,
                    spawn_not_before_ns=spawn_not_before_ns,
                )
            except Exception:
                _signal_group(process.pid, signal.SIGKILL)
                try:
                    if process.poll() is None:
                        process.kill()
                    process.wait(timeout=max(command.terminate_grace_seconds, 1.0))
                except (OSError, subprocess.TimeoutExpired):
                    pass
                for stream in (process.stdout, process.stderr):
                    try:
                        if stream is not None and not stream.closed:
                            stream.close()
                    except OSError:
                        pass
                cleanup = ClaudeCliCleanupReceipt(
                    process_group_empty=_group_status(process.pid) == "EMPTY",
                    marked_descendants_empty=False,
                    leader_reaped=process.poll() is not None,
                    stdin_closed=True,
                    stdout_closed=process.stdout is None or process.stdout.closed,
                    stderr_closed=process.stderr is None or process.stderr.closed,
                    reader_closed=reader_closed,
                    scratch_empty=False,
                    term_sent=False,
                    kill_sent=True,
                    residue_rows=("CLEANUP_FAILED",),
                )
                failure = (
                    "PROCESS_CLEANUP_FAILED",
                    ClaudeCliObservation.OUTCOME_UNRECONCILED,
                    "Claude CLI cleanup failed",
                )
            finally:
                try:
                    os.close(state_descriptor)
                except OSError:
                    if failure is None:
                        failure = (
                            "PROCESS_CLEANUP_FAILED",
                            ClaudeCliObservation.OUTCOME_UNRECONCILED,
                            "Claude CLI cleanup failed",
                        )

        if failure is not None:
            raise ClaudeCliProtocolError(
                failure[0],
                failure[1],
                failure[2],
                cleanup=cleanup,
            ) from None
        if cleanup.term_sent or cleanup.kill_sent:
            raise ClaudeCliProtocolError(
                "PROCESS_RESIDUE_OBSERVED",
                ClaudeCliObservation.OUTCOME_UNRECONCILED,
                "Claude CLI descendants survived the terminal result",
                cleanup=cleanup,
            ) from None
        if (
            not cleanup.process_group_empty
            or not cleanup.marked_descendants_empty
            or not cleanup.leader_reaped
            or not cleanup.reader_closed
            or not cleanup.scratch_empty
            or cleanup.residue_rows
        ):
            raise ClaudeCliProtocolError(
                "PROCESS_RESIDUE_UNPROVEN",
                ClaudeCliObservation.OUTCOME_UNRECONCILED,
                "Claude CLI cleanup was not fully proven",
                cleanup=cleanup,
            ) from None
        if returncode is None:  # pragma: no cover - guarded by failure paths
            raise ClaudeCliProtocolError(
                "PROCESS_EXIT_UNPROVEN",
                ClaudeCliObservation.OUTCOME_UNRECONCILED,
                "Claude CLI exit status was unavailable",
                cleanup=cleanup,
            ) from None

        receipt_body = {
            "observation": ClaudeCliObservation.TERMINAL_RESULT_OBSERVED.value,
            "session_id": command.session_id,
            "model": command.model,
            "event_count": parser.event_count,
            "read_count": parser.read_count,
            "submission_count": parser.submission_count,
            "input_tokens": parser.input_tokens,
            "output_tokens": parser.output_tokens,
            "cost_microusd": parser.cost_microusd,
            "result_sha256": parser.result_sha256,
            "stream_sha256": stream_digest.hexdigest(),
            "argv_sha256": command.argv_sha256,
            "environment_sha256": command.environment_sha256,
            "settings_sha256": command.settings_sha256,
            "binary_sha256": command.binary_sha256,
            "binary_device": command.binary_device,
            "binary_inode": command.binary_inode,
            "binary_uid": command.binary_uid,
            "binary_mode": command.binary_mode,
            "binary_size": command.binary_size,
            "binary_mtime_ns": command.binary_mtime_ns,
            "returncode": returncode,
            "events": [dataclasses.asdict(event) for event in parser.events],
            "cleanup": cleanup.to_dict(),
        }
        return ClaudeCliRunReceipt(
            observation=ClaudeCliObservation.TERMINAL_RESULT_OBSERVED,
            session_id=command.session_id,
            model=command.model,
            event_count=parser.event_count,
            read_count=parser.read_count,
            submission_count=parser.submission_count,
            input_tokens=parser.input_tokens,
            output_tokens=parser.output_tokens,
            cost_microusd=parser.cost_microusd,
            result_sha256=parser.result_sha256,
            stream_sha256=stream_digest.hexdigest(),
            argv_sha256=command.argv_sha256,
            environment_sha256=command.environment_sha256,
            settings_sha256=command.settings_sha256,
            binary_sha256=command.binary_sha256,
            binary_device=command.binary_device,
            binary_inode=command.binary_inode,
            binary_uid=command.binary_uid,
            binary_mode=command.binary_mode,
            binary_size=command.binary_size,
            binary_mtime_ns=command.binary_mtime_ns,
            returncode=returncode,
            events=tuple(parser.events),
            cleanup=cleanup,
            receipt_sha256=_canonical_sha256(receipt_body),
        )

__all__ = [
    "ClaudeCliCleanupReceipt",
    "ClaudeCliCommand",
    "ClaudeCliEvent",
    "ClaudeCliInvocationPolicy",
    "ClaudeCliObservation",
    "ClaudeCliProtocolError",
    "ClaudeCliRunReceipt",
    "ClaudeCliRunner",
    "ClaudeCliVersion",
    "compile_claude_cli_command",
]
