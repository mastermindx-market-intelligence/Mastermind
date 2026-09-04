"""Closed, provider-private Claude CLI protocol falsifier.

This module compiles and observes exactly one foreground ``claude -p`` shape.
It deliberately does not define or mutate any shared lifecycle or control-plane
state.

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
import re
import selectors
import signal
import stat
import subprocess
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


@dataclasses.dataclass(frozen=True)
class ClaudeCliEvent:
    index: int
    event_type: str
    subtype: str | None
    sha256: str


@dataclasses.dataclass(frozen=True)
class ClaudeCliCleanupReceipt:
    process_group_empty: bool
    leader_reaped: bool
    stdin_closed: bool
    stdout_closed: bool
    stderr_closed: bool
    term_sent: bool
    kill_sent: bool
    residue_rows: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "process_group_empty": self.process_group_empty,
            "leader_reaped": self.leader_reaped,
            "stdin_closed": self.stdin_closed,
            "stdout_closed": self.stdout_closed,
            "stderr_closed": self.stderr_closed,
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
    except OSError as exc:
        raise _fail_before_start("PATH_INVALID", f"{name} is unavailable") from exc
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


def _validate_policy(policy: ClaudeCliInvocationPolicy) -> tuple[Path, Path, Path, bytes]:
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
    except OSError as exc:
        raise _fail_before_start("BINARY_INVALID", "Claude binary is unavailable") from exc
    if (
        stat.S_ISLNK(binary_info.st_mode)
        or not stat.S_ISREG(binary_info.st_mode)
        or not os.access(binary, os.X_OK)
    ):
        raise _fail_before_start("BINARY_INVALID", "Claude binary must be a real executable file")
    if not isinstance(policy.model, str) or _MODEL_PATTERN.fullmatch(policy.model) is None:
        raise _fail_before_start("MODEL_INVALID", "model must be a full Claude model identifier")
    if not isinstance(policy.session_id, str):
        raise _fail_before_start("SESSION_INVALID", "session UUID is invalid")
    try:
        parsed_session = uuid.UUID(policy.session_id)
    except (ValueError, AttributeError) as exc:
        raise _fail_before_start("SESSION_INVALID", "session UUID is invalid") from exc
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
    try:
        native_home = Path.home().resolve(strict=True)
    except OSError:
        native_home = Path.home().resolve()
    if home == native_home:
        raise _fail_before_start("HOME_NOT_ISOLATED", "isolated home may not be the native home")
    if home == scratch or workspace in home.parents or workspace in scratch.parents:
        raise _fail_before_start("PATH_INVALID", "runtime paths must be distinct from the sealed workspace")
    evidence_path = workspace.joinpath(*relative.parts)
    try:
        evidence_info = evidence_path.lstat()
        resolved_evidence = evidence_path.resolve(strict=True)
        evidence_bytes = resolved_evidence.read_bytes()
    except OSError as exc:
        raise _fail_before_start("EVIDENCE_INVALID", "sealed evidence file is unavailable") from exc
    if (
        stat.S_ISLNK(evidence_info.st_mode)
        or not stat.S_ISREG(evidence_info.st_mode)
        or workspace not in resolved_evidence.parents
        or len(evidence_bytes) > 65_536
    ):
        raise _fail_before_start("EVIDENCE_INVALID", "sealed evidence file is invalid or out of bounds")
    if not isinstance(policy.expected_result_sha256, str) or _HEX_SHA256.fullmatch(
        policy.expected_result_sha256
    ) is None:
        raise _fail_before_start("RESULT_DIGEST_INVALID", "expected result digest is invalid")
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
    return binary, workspace, home, evidence_bytes


def _build_argv(
    *,
    binary: str,
    version: ClaudeCliVersion,
    model: str,
    session_id: str,
    prompt: str,
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
            "{}",
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
    binary, workspace, home, evidence_bytes = _validate_policy(policy)
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
            ClaudeCliObservation.PROCESS_STARTED_SUBMISSION_POSSIBLE,
            "stream JSON depth exceeded its bound",
        )
    if isinstance(value, str):
        if len(value.encode("utf-8")) > max_string_bytes:
            raise _StreamViolation(
                "STREAM_JSON_STRING",
                ClaudeCliObservation.PROCESS_STARTED_SUBMISSION_POSSIBLE,
                "stream JSON string exceeded its bound",
            )
        return
    if isinstance(value, dict):
        if len(value) > max_collection_items:
            raise _StreamViolation(
                "STREAM_JSON_COLLECTION",
                ClaudeCliObservation.PROCESS_STARTED_SUBMISSION_POSSIBLE,
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
                ClaudeCliObservation.PROCESS_STARTED_SUBMISSION_POSSIBLE,
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
            ClaudeCliObservation.PROCESS_STARTED_SUBMISSION_POSSIBLE,
            "stream JSON contained an unsupported value",
        )


def _expect_keys(value: Mapping[str, Any], allowed: frozenset[str]) -> None:
    if not set(value).issubset(allowed):
        raise _StreamViolation(
            "EVENT_FIELDS_UNKNOWN",
            ClaudeCliObservation.PROCESS_STARTED_SUBMISSION_POSSIBLE,
            "stream event contained unknown fields",
        )


def _expect_session(value: Mapping[str, Any], session_id: str) -> None:
    if value.get("session_id") != session_id:
        raise _StreamViolation(
            "SESSION_DRIFT",
            ClaudeCliObservation.PROCESS_STARTED_SUBMISSION_POSSIBLE,
            "stream session identity drifted",
        )


def _bounded_token_count(value: Any) -> int:
    if type(value) is not int or not 0 <= value <= 1_000_000_000:
        raise _StreamViolation(
            "USAGE_INVALID",
            ClaudeCliObservation.PROCESS_STARTED_SUBMISSION_POSSIBLE,
            "stream usage was invalid",
        )
    return value


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
                ClaudeCliObservation.PROCESS_STARTED_SUBMISSION_POSSIBLE,
                "stream event count exceeded its bound",
            )
        if not raw_line:
            raise _StreamViolation(
                "STREAM_JSON_INVALID",
                ClaudeCliObservation.PROCESS_STARTED_SUBMISSION_POSSIBLE,
                "stream contained an empty line",
            )
        try:
            text = raw_line.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise _StreamViolation(
                "STDOUT_UTF8_INVALID",
                ClaudeCliObservation.PROCESS_STARTED_SUBMISSION_POSSIBLE,
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
                ClaudeCliObservation.PROCESS_STARTED_SUBMISSION_POSSIBLE,
                "stream JSON contained a duplicate key",
            ) from exc
        except (json.JSONDecodeError, ValueError) as exc:
            raise _StreamViolation(
                "STREAM_JSON_INVALID",
                ClaudeCliObservation.PROCESS_STARTED_SUBMISSION_POSSIBLE,
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
                ClaudeCliObservation.PROCESS_STARTED_SUBMISSION_POSSIBLE,
                "stream event must be a JSON object",
            )
        event_type = value.get("type")
        subtype = value.get("subtype")
        if not isinstance(event_type, str) or (subtype is not None and not isinstance(subtype, str)):
            raise _StreamViolation(
                "EVENT_UNKNOWN",
                ClaudeCliObservation.PROCESS_STARTED_SUBMISSION_POSSIBLE,
                "stream event identity was invalid",
            )
        if self.terminal:
            code = "TERMINAL_RESULT_DUPLICATE" if event_type == "result" else "POST_TERMINAL_EVENT"
            message = "terminal result was duplicated" if event_type == "result" else "event followed terminal result"
            raise _StreamViolation(
                code,
                ClaudeCliObservation.PROCESS_STARTED_SUBMISSION_POSSIBLE,
                message,
            )
        if event_type == "system" and subtype == "api_retry":
            raise _StreamViolation(
                "PROVIDER_RETRY_OBSERVED",
                ClaudeCliObservation.PROCESS_STARTED_SUBMISSION_POSSIBLE,
                "provider retry was observed",
            )
        if event_type == "system" and subtype == "permission_denied":
            raise _StreamViolation(
                "PERMISSION_DENIED",
                ClaudeCliObservation.PROCESS_STARTED_SUBMISSION_POSSIBLE,
                "permission denial was observed",
            )
        if self.phase == 0 and not (event_type == "system" and subtype == "init"):
            raise _StreamViolation(
                "INIT_NOT_FIRST",
                ClaudeCliObservation.PROCESS_STARTED_SUBMISSION_POSSIBLE,
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
                ClaudeCliObservation.PROCESS_STARTED_SUBMISSION_POSSIBLE,
                "stream event type or subtype was not accepted",
            )
        self.events.append(
            ClaudeCliEvent(
                index=self.event_count,
                event_type=event_type,
                subtype=subtype,
                sha256=_sha256_bytes(raw_line),
            )
        )

    def _consume_init(self, value: Mapping[str, Any]) -> None:
        if self.phase != 0:
            raise _StreamViolation(
                "INIT_DUPLICATE",
                ClaudeCliObservation.PROCESS_STARTED_SUBMISSION_POSSIBLE,
                "system init was duplicated",
            )
        _expect_keys(
            value,
            frozenset(
                {
                    "type",
                    "subtype",
                    "session_id",
                    "model",
                    "tools",
                    "mcp_servers",
                    "mcp_server_errors",
                    "plugins",
                    "plugin_errors",
                    "permissionMode",
                    "capabilities",
                    "uuid",
                }
            ),
        )
        _expect_session(value, self.command.session_id)
        if value.get("model") != self.command.model:
            raise _StreamViolation(
                "MODEL_DRIFT",
                ClaudeCliObservation.PROCESS_STARTED_SUBMISSION_POSSIBLE,
                "stream model identity drifted",
            )
        if value.get("tools") != ["Read"]:
            raise _StreamViolation(
                "TOOL_SET_DRIFT",
                ClaudeCliObservation.PROCESS_STARTED_SUBMISSION_POSSIBLE,
                "stream tool set drifted",
            )
        if value.get("mcp_servers") != [] or value.get("mcp_server_errors") not in (None, []):
            raise _StreamViolation(
                "MCP_OBSERVED",
                ClaudeCliObservation.PROCESS_STARTED_SUBMISSION_POSSIBLE,
                "MCP activity was observed",
            )
        if value.get("plugins") != [] or value.get("plugin_errors") not in (None, []):
            raise _StreamViolation(
                "PLUGIN_OBSERVED",
                ClaudeCliObservation.PROCESS_STARTED_SUBMISSION_POSSIBLE,
                "plugin activity was observed",
            )
        if value.get("permissionMode") != "dontAsk":
            raise _StreamViolation(
                "PERMISSION_MODE_DRIFT",
                ClaudeCliObservation.PROCESS_STARTED_SUBMISSION_POSSIBLE,
                "permission mode drifted",
            )
        capabilities = value.get("capabilities", [])
        if not isinstance(capabilities, list) or any(not isinstance(item, str) for item in capabilities):
            raise _StreamViolation(
                "INIT_INVALID",
                ClaudeCliObservation.PROCESS_STARTED_SUBMISSION_POSSIBLE,
                "init capabilities were invalid",
            )
        self.phase = 1
        self.submission_count = 1

    def _consume_usage(self, value: Mapping[str, Any]) -> None:
        if self.phase == 0 or self.terminal:
            raise _StreamViolation(
                "EVENT_ORDER_INVALID",
                ClaudeCliObservation.PROCESS_STARTED_SUBMISSION_POSSIBLE,
                "usage event was out of order",
            )
        _expect_keys(value, frozenset({"type", "subtype", "session_id", "usage", "uuid"}))
        _expect_session(value, self.command.session_id)
        usage = value.get("usage")
        if not isinstance(usage, dict):
            raise _StreamViolation(
                "USAGE_INVALID",
                ClaudeCliObservation.PROCESS_STARTED_SUBMISSION_POSSIBLE,
                "stream usage was invalid",
            )
        _expect_keys(usage, frozenset({"input_tokens", "output_tokens"}))
        self.input_tokens = max(self.input_tokens, _bounded_token_count(usage.get("input_tokens")))
        self.output_tokens = max(self.output_tokens, _bounded_token_count(usage.get("output_tokens")))

    def _consume_assistant(self, value: Mapping[str, Any]) -> None:
        _expect_keys(
            value,
            frozenset({"type", "message", "parent_tool_use_id", "session_id", "uuid"}),
        )
        _expect_session(value, self.command.session_id)
        if value.get("parent_tool_use_id") is not None:
            raise _StreamViolation(
                "SUBAGENT_OBSERVED",
                ClaudeCliObservation.PROCESS_STARTED_SUBMISSION_POSSIBLE,
                "subagent output was observed",
            )
        message = value.get("message")
        if not isinstance(message, dict):
            raise _StreamViolation(
                "ASSISTANT_EVENT_INVALID",
                ClaudeCliObservation.PROCESS_STARTED_SUBMISSION_POSSIBLE,
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
        if message.get("role") != "assistant" or message.get("model") != self.command.model:
            raise _StreamViolation(
                "MODEL_DRIFT",
                ClaudeCliObservation.PROCESS_STARTED_SUBMISSION_POSSIBLE,
                "assistant identity drifted",
            )
        content = message.get("content")
        if not isinstance(content, list) or len(content) != 1 or not isinstance(content[0], dict):
            raise _StreamViolation(
                "ASSISTANT_EVENT_INVALID",
                ClaudeCliObservation.PROCESS_STARTED_SUBMISSION_POSSIBLE,
                "assistant content was not singular and bounded",
            )
        block = content[0]
        if block.get("type") == "tool_use":
            if self.phase != 1:
                raise _StreamViolation(
                    "READ_COUNT_INVALID",
                    ClaudeCliObservation.PROCESS_STARTED_SUBMISSION_POSSIBLE,
                    "Read was duplicated or out of order",
                )
            _expect_keys(block, frozenset({"type", "id", "name", "input"}))
            if block.get("name") != "Read":
                raise _StreamViolation(
                    "TOOL_UNAUTHORIZED",
                    ClaudeCliObservation.PROCESS_STARTED_SUBMISSION_POSSIBLE,
                    "an unauthorized tool was observed",
                )
            tool_id = block.get("id")
            inputs = block.get("input")
            if not isinstance(tool_id, str) or _TOOL_ID.fullmatch(tool_id) is None:
                raise _StreamViolation(
                    "TOOL_EVENT_INVALID",
                    ClaudeCliObservation.PROCESS_STARTED_SUBMISSION_POSSIBLE,
                    "tool identity was invalid",
                )
            if not isinstance(inputs, dict) or set(inputs) != {"file_path"}:
                raise _StreamViolation(
                    "READ_SCOPE_DRIFT",
                    ClaudeCliObservation.PROCESS_STARTED_SUBMISSION_POSSIBLE,
                    "Read input drifted from the sealed file",
                )
            if inputs.get("file_path") != self.command.evidence_relative_path:
                raise _StreamViolation(
                    "READ_SCOPE_DRIFT",
                    ClaudeCliObservation.PROCESS_STARTED_SUBMISSION_POSSIBLE,
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
                    ClaudeCliObservation.PROCESS_STARTED_SUBMISSION_POSSIBLE,
                    "assistant text was out of order",
                )
            _expect_keys(block, frozenset({"type", "text"}))
            text = block.get("text")
            if not isinstance(text, str) or _sha256_bytes(text.encode("utf-8")) != self.command.expected_result_sha256:
                raise _StreamViolation(
                    "STRUCTURED_RESULT_MISMATCH",
                    ClaudeCliObservation.PROCESS_STARTED_SUBMISSION_POSSIBLE,
                    "assistant result did not match the sealed expectation",
                )
            self.phase = 4
            return
        raise _StreamViolation(
            "TOOL_UNAUTHORIZED",
            ClaudeCliObservation.PROCESS_STARTED_SUBMISSION_POSSIBLE,
            "assistant content type was not accepted",
        )

    def _consume_user(self, value: Mapping[str, Any]) -> None:
        if self.phase != 2:
            raise _StreamViolation(
                "EVENT_ORDER_INVALID",
                ClaudeCliObservation.PROCESS_STARTED_SUBMISSION_POSSIBLE,
                "tool result was out of order",
            )
        _expect_keys(
            value,
            frozenset({"type", "message", "parent_tool_use_id", "session_id", "uuid"}),
        )
        _expect_session(value, self.command.session_id)
        if value.get("parent_tool_use_id") is not None:
            raise _StreamViolation(
                "SUBAGENT_OBSERVED",
                ClaudeCliObservation.PROCESS_STARTED_SUBMISSION_POSSIBLE,
                "subagent tool result was observed",
            )
        message = value.get("message")
        if not isinstance(message, dict):
            raise _StreamViolation(
                "TOOL_RESULT_INVALID",
                ClaudeCliObservation.PROCESS_STARTED_SUBMISSION_POSSIBLE,
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
                ClaudeCliObservation.PROCESS_STARTED_SUBMISSION_POSSIBLE,
                "tool result event was invalid",
            )
        block = content[0]
        _expect_keys(block, frozenset({"type", "tool_use_id", "content", "is_error"}))
        if block.get("type") != "tool_result" or block.get("tool_use_id") != self.tool_use_id:
            raise _StreamViolation(
                "TOOL_RESULT_MISMATCH",
                ClaudeCliObservation.PROCESS_STARTED_SUBMISSION_POSSIBLE,
                "tool result identity did not match Read",
            )
        result_content = block.get("content")
        if block.get("is_error") is not False or not isinstance(result_content, str):
            raise _StreamViolation(
                "TOOL_RESULT_INVALID",
                ClaudeCliObservation.PROCESS_STARTED_SUBMISSION_POSSIBLE,
                "Read result reported an error",
            )
        if _sha256_bytes(result_content.encode("utf-8")) != self.command.evidence_sha256:
            raise _StreamViolation(
                "TOOL_RESULT_MISMATCH",
                ClaudeCliObservation.PROCESS_STARTED_SUBMISSION_POSSIBLE,
                "Read result did not match the sealed evidence",
            )
        self.phase = 3

    def _consume_result(self, value: Mapping[str, Any]) -> None:
        if self.phase != 4:
            raise _StreamViolation(
                "EVENT_ORDER_INVALID",
                ClaudeCliObservation.PROCESS_STARTED_SUBMISSION_POSSIBLE,
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
                }
            ),
        )
        _expect_session(value, self.command.session_id)
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
        if value.get("num_turns") != 1:
            raise _StreamViolation(
                "TURN_COUNT_INVALID",
                ClaudeCliObservation.PROCESS_STARTED_SUBMISSION_POSSIBLE,
                "terminal turn count was invalid",
            )
        result = value.get("result")
        if not isinstance(result, str) or _sha256_bytes(result.encode("utf-8")) != self.command.expected_result_sha256:
            raise _StreamViolation(
                "STRUCTURED_RESULT_MISMATCH",
                ClaudeCliObservation.PROCESS_STARTED_SUBMISSION_POSSIBLE,
                "terminal result did not match the sealed expectation",
            )
        cost = value.get("total_cost_usd")
        if type(cost) not in {int, float} or not math.isfinite(float(cost)) or not 0 <= float(cost) <= 1_000:
            raise _StreamViolation(
                "USAGE_INVALID",
                ClaudeCliObservation.PROCESS_STARTED_SUBMISSION_POSSIBLE,
                "terminal cost estimate was invalid",
            )
        usage = value.get("usage")
        if not isinstance(usage, dict):
            raise _StreamViolation(
                "USAGE_INVALID",
                ClaudeCliObservation.PROCESS_STARTED_SUBMISSION_POSSIBLE,
                "terminal usage was invalid",
            )
        _expect_keys(usage, frozenset({"input_tokens", "output_tokens"}))
        self.input_tokens = _bounded_token_count(usage.get("input_tokens"))
        self.output_tokens = _bounded_token_count(usage.get("output_tokens"))
        self.cost_microusd = int(round(float(cost) * 1_000_000))
        self.result_sha256 = self.command.expected_result_sha256
        self.terminal = True
        self.phase = 5

    def finalize(self) -> None:
        if not self.terminal:
            raise _StreamViolation(
                "TERMINAL_RESULT_MISSING",
                ClaudeCliObservation.PROCESS_STARTED_SUBMISSION_POSSIBLE,
                "terminal result was missing",
            )
        if self.read_count != 1 or self.submission_count != 1:
            raise _StreamViolation(
                "READ_COUNT_INVALID",
                ClaudeCliObservation.PROCESS_STARTED_SUBMISSION_POSSIBLE,
                "one-Read one-submission invariant was not satisfied",
            )


def _contains_sensitive_bytes(value: bytes) -> str | None:
    if any(marker in value for marker in _SENSITIVE_BYTES) or _EMAIL_BYTES.search(value):
        return "SENSITIVE_OUTPUT"
    if any(marker in value for marker in _PRIVATE_LOCATOR_BYTES):
        return "PRIVATE_LOCATOR_OUTPUT"
    return None


def _group_status(pgid: int) -> str:
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return "EMPTY"
    except PermissionError:
        return "UNKNOWN"
    return "ALIVE"


def _wait_group_empty(pgid: int, timeout: float) -> bool:
    deadline = time.monotonic() + max(timeout, 0.01)
    while time.monotonic() < deadline:
        if _group_status(pgid) == "EMPTY":
            return True
        time.sleep(0.01)
    return _group_status(pgid) == "EMPTY"


def _cleanup_process(
    process: subprocess.Popen[bytes],
    *,
    pgid: int,
    grace_seconds: float,
    force_termination: bool,
) -> ClaudeCliCleanupReceipt:
    term_sent = False
    kill_sent = False
    residue: list[str] = []
    if pgid != process.pid or pgid == os.getpgrp():
        residue.append("PROCESS_GROUP_IDENTITY_UNPROVEN")
        if process.poll() is None:
            try:
                process.kill()
                kill_sent = True
            except ProcessLookupError:
                pass
        try:
            process.wait(timeout=max(grace_seconds, 1.0))
        except subprocess.TimeoutExpired:
            residue.append("LEADER_NOT_REAPED")
    else:
        group_status = _group_status(pgid)
        if force_termination and group_status == "ALIVE":
            try:
                os.killpg(pgid, signal.SIGTERM)
                term_sent = True
            except ProcessLookupError:
                pass
        if process.poll() is None:
            try:
                process.wait(timeout=grace_seconds)
            except subprocess.TimeoutExpired:
                pass
        if _group_status(pgid) == "ALIVE":
            if not term_sent:
                try:
                    os.killpg(pgid, signal.SIGTERM)
                    term_sent = True
                except ProcessLookupError:
                    pass
                _wait_group_empty(pgid, grace_seconds)
            if _group_status(pgid) == "ALIVE":
                try:
                    os.killpg(pgid, signal.SIGKILL)
                    kill_sent = True
                except ProcessLookupError:
                    pass
        if process.poll() is None:
            try:
                process.wait(timeout=max(grace_seconds, 1.0))
            except subprocess.TimeoutExpired:
                residue.append("LEADER_NOT_REAPED")
        if not _wait_group_empty(pgid, max(grace_seconds, 1.0)):
            residue.append("PROCESS_GROUP_NOT_EMPTY")
    leader_reaped = process.poll() is not None
    for stream in (process.stdout, process.stderr):
        if stream is not None and not stream.closed:
            stream.close()
    return ClaudeCliCleanupReceipt(
        process_group_empty=_group_status(pgid) == "EMPTY",
        leader_reaped=leader_reaped,
        stdin_closed=True,
        stdout_closed=process.stdout is None or process.stdout.closed,
        stderr_closed=process.stderr is None or process.stderr.closed,
        term_sent=term_sent,
        kill_sent=kill_sent,
        residue_rows=tuple(residue),
    )


def _validate_command_integrity(command: ClaudeCliCommand) -> None:
    if not isinstance(command, ClaudeCliCommand):
        raise _fail_before_start("COMMAND_INVALID", "Claude command is invalid")
    expected_argv = _build_argv(
        binary=command.argv[0] if command.argv else "",
        version=command.version,
        model=command.model,
        session_id=command.session_id,
        prompt=command.prompt,
    )
    expected_environment = (
        ("HOME", command.isolated_home),
        ("TMPDIR", command.isolated_tmp),
        *_SAFE_ENVIRONMENT,
        ("API_TIMEOUT_MS", str(command.api_timeout_ms)),
    )
    if command.argv != expected_argv or command.argv_sha256 != _canonical_sha256(list(expected_argv)):
        raise _fail_before_start("COMMAND_DRIFT", "compiled argv integrity check failed")
    if command.environment != expected_environment or command.environment_sha256 != _environment_digest(
        expected_environment
    ):
        raise _fail_before_start("ENVIRONMENT_DRIFT", "compiled environment integrity check failed")
    if command.working_directory != str(Path(command.working_directory).resolve(strict=True)):
        raise _fail_before_start("COMMAND_DRIFT", "compiled working directory drifted")
    evidence = Path(command.working_directory).joinpath(
        *PurePosixPath(command.evidence_relative_path).parts
    )
    try:
        evidence_bytes = evidence.read_bytes()
    except OSError as exc:
        raise _fail_before_start("EVIDENCE_INVALID", "sealed evidence file became unavailable") from exc
    if _sha256_bytes(evidence_bytes) != command.evidence_sha256:
        raise _fail_before_start("EVIDENCE_DRIFT", "sealed evidence file drifted before process start")


def _validate_fake_controls(
    command: ClaudeCliCommand,
    fake_controls: Mapping[str, str] | None,
) -> dict[str, str]:
    if fake_controls is None:
        return {}
    if Path(command.argv[0]).name != "fake_claude_cli.py":
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
    if state is not None:
        state_path = Path(state)
        workspace = Path(command.working_directory)
        if (
            not state_path.is_absolute()
            or not state_path.parent.is_dir()
            or state_path == workspace
            or workspace in state_path.parents
        ):
            raise _fail_before_start("FAKE_CONTROL_INVALID", "fake control state path is invalid")
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
        environment = dict(command.environment)
        environment.update(controls)
        try:
            process = subprocess.Popen(
                command.argv,
                cwd=command.working_directory,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,
                close_fds=True,
                bufsize=0,
            )
        except OSError as exc:
            raise _fail_before_start("PROCESS_START_FAILED", "Claude CLI process could not be started") from exc
        try:
            pgid = os.getpgid(process.pid)
        except OSError as exc:
            try:
                if process.poll() is None:
                    process.kill()
            finally:
                process.wait()
            raise ClaudeCliProtocolError(
                "PROCESS_GROUP_UNPROVEN",
                ClaudeCliObservation.OUTCOME_UNRECONCILED,
                "Claude CLI process-group identity was unavailable",
            ) from exc
        if pgid != process.pid or pgid == os.getpgrp():
            cleanup = _cleanup_process(
                process,
                pgid=pgid,
                grace_seconds=command.terminate_grace_seconds,
                force_termination=True,
            )
            raise ClaudeCliProtocolError(
                "PROCESS_GROUP_UNPROVEN",
                ClaudeCliObservation.OUTCOME_UNRECONCILED,
                "Claude CLI process was not isolated in its own group",
                cleanup=cleanup,
            )
        if process.stdout is None or process.stderr is None:  # pragma: no cover - Popen invariant
            cleanup = _cleanup_process(
                process,
                pgid=pgid,
                grace_seconds=command.terminate_grace_seconds,
                force_termination=True,
            )
            raise ClaudeCliProtocolError(
                "PIPE_START_FAILED",
                ClaudeCliObservation.OUTCOME_UNRECONCILED,
                "Claude CLI stream pipes were unavailable",
                cleanup=cleanup,
            )

        parser = _StreamParser(command)
        stream_digest = hashlib.sha256()
        stdout_buffer = bytearray()
        stdout_total = 0
        stderr_total = 0
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ, "stdout")
        selector.register(process.stderr, selectors.EVENT_READ, "stderr")
        started_at = time.monotonic()
        last_activity = started_at
        violation: _StreamViolation | None = None
        try:
            while selector.get_map():
                now = time.monotonic()
                if cancel_event is not None and cancel_event.is_set():
                    violation = _StreamViolation(
                        "CANCELLED_AFTER_START",
                        ClaudeCliObservation.OUTCOME_UNRECONCILED,
                        "invocation was cancelled after process start",
                    )
                    break
                if now - started_at >= command.absolute_timeout_seconds:
                    violation = _StreamViolation(
                        "ABSOLUTE_TIMEOUT",
                        ClaudeCliObservation.OUTCOME_UNRECONCILED,
                        "Claude CLI absolute deadline expired",
                    )
                    break
                if now - last_activity >= command.idle_timeout_seconds:
                    violation = _StreamViolation(
                        "IDLE_TIMEOUT",
                        ClaudeCliObservation.OUTCOME_UNRECONCILED,
                        "Claude CLI idle deadline expired",
                    )
                    break
                wait_for = min(
                    0.05,
                    command.absolute_timeout_seconds - (now - started_at),
                    command.idle_timeout_seconds - (now - last_activity),
                )
                for key, _ in selector.select(timeout=max(wait_for, 0.001)):
                    stream = key.fileobj
                    try:
                        chunk = os.read(stream.fileno(), 65_536)
                    except BlockingIOError:  # pragma: no cover - selector readiness race
                        continue
                    if not chunk:
                        selector.unregister(stream)
                        continue
                    last_activity = time.monotonic()
                    sensitive_code = _contains_sensitive_bytes(chunk)
                    if sensitive_code is not None:
                        violation = _StreamViolation(
                            sensitive_code,
                            ClaudeCliObservation.PROCESS_STARTED_SUBMISSION_POSSIBLE,
                            "provider output contained sensitive material"
                            if sensitive_code == "SENSITIVE_OUTPUT"
                            else "provider output contained a private locator",
                        )
                        break
                    if key.data == "stderr":
                        stderr_total += len(chunk)
                        if stderr_total > command.max_stderr_bytes:
                            violation = _StreamViolation(
                                "STDERR_BYTE_LIMIT",
                                ClaudeCliObservation.PROCESS_STARTED_SUBMISSION_POSSIBLE,
                                "stderr exceeded its byte bound",
                            )
                        else:
                            violation = _StreamViolation(
                                "STDERR_NOT_EMPTY",
                                ClaudeCliObservation.PROCESS_STARTED_SUBMISSION_POSSIBLE,
                                "stderr was not empty",
                            )
                        break
                    stdout_total += len(chunk)
                    stream_digest.update(chunk)
                    if stdout_total > command.max_stdout_bytes:
                        violation = _StreamViolation(
                            "STDOUT_BYTE_LIMIT",
                            ClaudeCliObservation.PROCESS_STARTED_SUBMISSION_POSSIBLE,
                            "stdout exceeded its byte bound",
                        )
                        break
                    stdout_buffer.extend(chunk)
                    while True:
                        newline = stdout_buffer.find(b"\n")
                        if newline < 0:
                            break
                        raw_line = bytes(stdout_buffer[:newline])
                        del stdout_buffer[: newline + 1]
                        if len(raw_line) > command.max_line_bytes:
                            violation = _StreamViolation(
                                "STREAM_LINE_LIMIT",
                                ClaudeCliObservation.PROCESS_STARTED_SUBMISSION_POSSIBLE,
                                "stream line exceeded its byte bound",
                            )
                            break
                        sensitive_code = _contains_sensitive_bytes(raw_line)
                        if sensitive_code is not None:
                            violation = _StreamViolation(
                                sensitive_code,
                                ClaudeCliObservation.PROCESS_STARTED_SUBMISSION_POSSIBLE,
                                "provider output contained sensitive material"
                                if sensitive_code == "SENSITIVE_OUTPUT"
                                else "provider output contained a private locator",
                            )
                            break
                        try:
                            parser.consume(raw_line)
                        except _StreamViolation as exc:
                            violation = exc
                            break
                    if violation is not None:
                        break
                    if len(stdout_buffer) > command.max_line_bytes:
                        violation = _StreamViolation(
                            "STREAM_LINE_LIMIT",
                            ClaudeCliObservation.PROCESS_STARTED_SUBMISSION_POSSIBLE,
                            "stream line exceeded its byte bound",
                        )
                        break
                if violation is not None:
                    break
            if violation is None and stdout_buffer:
                violation = _StreamViolation(
                    "STREAM_LINE_UNTERMINATED",
                    ClaudeCliObservation.PROCESS_STARTED_SUBMISSION_POSSIBLE,
                    "stream ended with an unterminated line",
                )
            if violation is None:
                try:
                    parser.finalize()
                except _StreamViolation as exc:
                    violation = exc
        finally:
            selector.close()

        if violation is not None:
            cleanup = _cleanup_process(
                process,
                pgid=pgid,
                grace_seconds=command.terminate_grace_seconds,
                force_termination=True,
            )
            raise ClaudeCliProtocolError(
                violation.code,
                violation.observation,
                violation.message,
                cleanup=cleanup,
            )

        try:
            returncode = process.wait(timeout=max(command.terminate_grace_seconds, 1.0))
        except subprocess.TimeoutExpired:
            cleanup = _cleanup_process(
                process,
                pgid=pgid,
                grace_seconds=command.terminate_grace_seconds,
                force_termination=True,
            )
            raise ClaudeCliProtocolError(
                "PROCESS_EXIT_TIMEOUT",
                ClaudeCliObservation.OUTCOME_UNRECONCILED,
                "Claude CLI did not exit after its terminal result",
                cleanup=cleanup,
            )
        cleanup = _cleanup_process(
            process,
            pgid=pgid,
            grace_seconds=command.terminate_grace_seconds,
            force_termination=False,
        )
        if returncode != 0:
            raise ClaudeCliProtocolError(
                "PROCESS_EXIT_INVALID",
                ClaudeCliObservation.OUTCOME_UNRECONCILED,
                "Claude CLI exit status contradicted its terminal result",
                cleanup=cleanup,
            )
        if not cleanup.process_group_empty or not cleanup.leader_reaped or cleanup.residue_rows:
            raise ClaudeCliProtocolError(
                "PROCESS_RESIDUE_UNPROVEN",
                ClaudeCliObservation.OUTCOME_UNRECONCILED,
                "Claude CLI cleanup was not fully proven",
                cleanup=cleanup,
            )
        if cleanup.term_sent or cleanup.kill_sent:
            raise ClaudeCliProtocolError(
                "PROCESS_RESIDUE_OBSERVED",
                ClaudeCliObservation.OUTCOME_UNRECONCILED,
                "Claude CLI descendants survived the terminal result",
                cleanup=cleanup,
            )

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
