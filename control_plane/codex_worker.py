"""Isolated, one-shot Codex CLI process adapter for the Executive OS.

The adapter owns provider-process mechanics only.  It does not claim jobs,
decide authority, create workspaces, commit Git changes, retry work, or promote
an output to an Executive result.  A caller must hand it an already-authorized
``LaunchSpec`` whose workspace is a clean, credential-free, per-job clone.

Security properties are intentionally local and inspectable:

* an absolute, attested native Codex binary (never ambient ``PATH`` lookup);
* a process environment constructed from an empty mapping;
* one non-interactive, ephemeral ``codex exec --json`` turn;
* Codex permission-profile fences with model-tool networking off;
* a new POSIX session/process group and PID-reuse-resistant macOS identity;
* bounded, owner-only streamed logs;
* strict JSONL lifecycle, final JSON Schema, Git, and artifact validation; and
* identity-checked process-group cancellation and timeout escalation.

No credential value is persisted by this module.  The provider client receives
only the path to its dedicated ``CODEX_HOME``; model-spawned tools receive
neither that variable nor access to the auth file through the Codex permission
profile.
"""
from __future__ import annotations

import asyncio
import contextlib
import ctypes
import dataclasses
import fnmatch
import hashlib
import json
import math
import os
import platform
import pwd
import re
import signal
import stat
import subprocess
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path, PurePosixPath
from typing import Any, Iterator, Mapping, Sequence
from uuid import uuid4

from control_plane.executive_workspace import (
    LAUNCH_CLEAN_STATUS_ARGS,
    LAUNCH_CLEAN_UNTRACKED_ARGS,
    git_observation_env,
    observe_launch_cleanliness,
)


_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_OPENAI_TEAM_IDENTIFIER = "2DC432GLL2"
_SAFE_PATH = "/usr/bin:/bin:/usr/sbin:/sbin"
_CODE_SIGNATURE_TIMEOUT_SECONDS = 60.0
_MAX_PROMPT_BYTES = 1 * 1024 * 1024
_MAX_SCHEMA_BYTES = 1 * 1024 * 1024
_MAX_RESULT_BYTES = 1 * 1024 * 1024
_MAX_STDOUT_BYTES = 32 * 1024 * 1024
_MAX_STDERR_BYTES = 4 * 1024 * 1024
_MAX_JSONL_LINE_BYTES = 1 * 1024 * 1024
_MAX_ARTIFACTS = 32
_MAX_ARTIFACT_BYTES = 8 * 1024 * 1024
_MAX_ARTIFACT_TOTAL_BYTES = 32 * 1024 * 1024
_MAX_VALIDATION_STDOUT_BYTES = 4 * 1024 * 1024
_MAX_VALIDATION_STDERR_BYTES = 1 * 1024 * 1024
_MAX_VALIDATION_ARGV_BYTES = 64 * 1024
_MAX_PROJECT_CONFIG_BYTES = 64 * 1024
_AUDITED_PROJECT_CONFIG_SHA256 = "d7e836eb5a6cbd4cb4e97de41f8182add663cb2a152dc4e381f82553f571bb7f"
_ALLOWED_AUTHORITIES = frozenset({"READ", "RESEARCH", "WRITE_BRANCH", "RUN_TESTS"})
_GIT_COMMAND_TIMEOUT_SECONDS = 15.0
_SAFE_GIT_OPERATION_IDENTITIES = {
    ("remote",): "remote",
    ("rev-parse", "--verify", "HEAD"): "rev-parse --verify HEAD",
    LAUNCH_CLEAN_STATUS_ARGS: "status --porcelain=v1 -z --untracked-files=all",
    LAUNCH_CLEAN_UNTRACKED_ARGS: "ls-files --others -z",
    ("diff", "--name-only", "-z", "HEAD", "--"): "diff --name-only -z HEAD --",
}
_SAFE_GIT_OPERATION_NAMES = frozenset(
    {*_SAFE_GIT_OPERATION_IDENTITIES.values(), "unknown"}
)
_SAFE_LAUNCH_VALIDATION_STAGES = frozenset(
    {
        "spec_contract",
        "workspace_identity",
        "project_configuration",
        "git_metadata",
        "git_remote_policy",
        "git_head_policy",
        "git_cleanliness",
        "expected_base",
        "run_directory",
        "isolation_manifest",
    }
)
_SHELL_EXECUTABLE_NAMES = frozenset({"bash", "csh", "dash", "fish", "ksh", "sh", "tcsh", "zsh"})
_DISABLED_FEATURES = (
    "hooks",
    "apps",
    "plugins",
    "plugin_sharing",
    "browser_use",
    "computer_use",
    "image_generation",
    "memories",
    "multi_agent",
    "remote_plugin",
)
_JSONL_EVENT_TYPES = frozenset({
    "thread.started",
    "turn.started",
    "turn.completed",
    "turn.failed",
    "item.started",
    "item.updated",
    "item.completed",
    "error",
})
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
LAUNCH_ATTESTATION_SCHEMA_VERSION = "mastermind.executive_launch_attestation/v1"
SECRET_CANARY_SCHEMA_VERSION = "mastermind.executive_secret_canary/v1"
ISOLATION_MANIFEST_SCHEMA_VERSION = "mastermind.executive_isolation_manifest/v1"
_SECRET_CANARY_CHECKS = frozenset(
    {
        "control_service_environment",
        "administrative_checkout",
        "executive_database",
        "other_worker_home",
        "forbidden_production_path",
    }
)


class CodexWorkerError(RuntimeError):
    """Base class for fail-closed adapter errors."""


class LaunchValidationError(CodexWorkerError):
    """The launch specification or workspace is unsafe."""


class LaunchValidationStageError(LaunchValidationError):
    """A launch refusal attributed only to one audited validation boundary."""

    code = "launch_validation_stage"

    def __init__(self, *, stage: str) -> None:
        if stage not in _SAFE_LAUNCH_VALIDATION_STAGES:
            raise ValueError("launch validation stage is not allowlisted")
        self.stage = stage
        super().__init__(f"Launch validation failed at stage: {self.stage}")


def _validate_safe_git_operation(operation: str) -> str:
    value = str(operation)
    if value not in _SAFE_GIT_OPERATION_NAMES:
        raise ValueError("Git preflight operation is not allowlisted")
    return value


class GitPreflightTimeout(LaunchValidationError):
    """A bounded Git validation operation did not finish in time."""

    code = "git_preflight_timeout"

    def __init__(self, *, operation: str, timeout_seconds: float) -> None:
        self.operation = _validate_safe_git_operation(operation)
        self.timeout_seconds = float(timeout_seconds)
        if self.timeout_seconds != _GIT_COMMAND_TIMEOUT_SECONDS:
            raise ValueError("Git preflight timeout differs from the fixed contract")
        rendered_timeout = f"{self.timeout_seconds:g}"
        super().__init__(
            f"Git preflight timed out after {rendered_timeout}s: {self.operation}"
        )


class GitPreflightFailed(LaunchValidationError):
    """An allowlisted Git validation operation returned a bounded nonzero code."""

    code = "git_preflight_failed"

    def __init__(self, *, operation: str, exit_code: int) -> None:
        self.operation = _validate_safe_git_operation(operation)
        if (
            isinstance(exit_code, bool)
            or not isinstance(exit_code, int)
            or not -255 <= exit_code <= 255
            or exit_code == 0
        ):
            raise ValueError("Git preflight exit code is outside the safe contract")
        self.exit_code = exit_code
        super().__init__(
            f"Git preflight failed: {self.operation} (exit {self.exit_code})"
        )


@contextlib.contextmanager
def _launch_validation_stage(stage: str) -> Iterator[None]:
    """Replace private validation prose with a stable allowlisted stage."""

    if stage not in _SAFE_LAUNCH_VALIDATION_STAGES:
        raise ValueError("launch validation stage is not allowlisted")
    try:
        yield
    except (LaunchValidationStageError, GitPreflightTimeout, GitPreflightFailed):
        raise
    except LaunchValidationError as exc:
        raise LaunchValidationStageError(stage=stage) from exc


class BinaryAttestationError(CodexWorkerError):
    """The configured Codex executable failed attestation."""


class ProcessIdentityError(CodexWorkerError):
    """A process no longer matches its persisted identity."""


class ResultValidationError(CodexWorkerError):
    """Provider output did not satisfy the local result contract."""


class WorkerRunStatus(str, Enum):
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    CANCELLING = "CANCELLING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    INVALID_RESULT = "INVALID_RESULT"
    CANCELLED = "CANCELLED"
    TIMED_OUT = "TIMED_OUT"


@dataclasses.dataclass(frozen=True)
class BinaryAttestation:
    path: str
    real_path: str
    version: str
    sha256: str
    team_identifier: str | None
    size: int
    device: int
    inode: int
    mode: int
    uid: int
    gid: int
    mtime_ns: int


@dataclasses.dataclass(frozen=True)
class ProcessIdentity:
    """Boot-scoped process identity including the OS-principal boundary."""

    start_identity: str
    pgid: int
    session_id: int
    effective_uid: int
    effective_gid: int
    real_uid: int
    real_gid: int


@dataclasses.dataclass(frozen=True)
class LaunchAttestation:
    """Complete, secret-free launch receipt persisted before RUNNING."""

    schema_version: str
    created_at: str
    executable_path: str
    binary: BinaryAttestation
    rendered_argv: tuple[str, ...]
    environment_keys: tuple[str, ...]
    permission_profile_sha256: str
    prompt_sha256: str
    expected_base_sha: str | None
    observed_base_sha: str
    workspace_identity: Mapping[str, Any]
    worker_identity: Mapping[str, Any]
    provider_home_identity: Mapping[str, Any]
    secret_canary_verdict: Mapping[str, Any]
    launch_nonce: str
    process_identity: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "created_at": self.created_at,
            "executable_path": self.executable_path,
            "binary": dataclasses.asdict(self.binary),
            "rendered_argv": list(self.rendered_argv),
            "environment_keys": list(self.environment_keys),
            "permission_profile_sha256": self.permission_profile_sha256,
            "prompt_sha256": self.prompt_sha256,
            "expected_base_sha": self.expected_base_sha,
            "observed_base_sha": self.observed_base_sha,
            "workspace_identity": dict(self.workspace_identity),
            "worker_identity": dict(self.worker_identity),
            "provider_home_identity": dict(self.provider_home_identity),
            "secret_canary_verdict": dict(self.secret_canary_verdict),
            "launch_nonce": self.launch_nonce,
            "process_identity": dict(self.process_identity),
        }


@dataclasses.dataclass(frozen=True)
class LaunchSpec:
    """Immutable inputs for one authorized, non-interactive Codex turn."""

    run_id: str
    job_id: str
    worker_id: str
    workspace_path: Path
    run_dir: Path
    prompt: str
    result_schema_path: Path
    codex_home: Path
    # Executable grants are an exact set, not an ordinal.  ``authority`` is a
    # temporary scalar compatibility seam for callers predating Phase 1B;
    # callers that need WRITE_BRANCH + RUN_TESTS should use ``authorities``.
    authorities: tuple[str, ...] = ()
    authority: str | None = None
    model: str = "gpt-5.6-sol"
    reasoning_effort: str = "xhigh"
    timeout_seconds: float = 1800.0
    cancel_grace_seconds: float = 10.0
    worker_user: str = "mastermind-worker"
    expected_base_sha: str | None = None
    allowed_artifact_paths: tuple[str, ...] = ()
    # The control principal freezes every existing sibling assignment before
    # launch.  The worker cannot enumerate the control-owned 0710 roots.
    isolation_roots: tuple[Path, ...] = ()
    isolation_denied_paths: tuple[Path, ...] = ()
    isolation_manifest: Mapping[str, Any] = dataclasses.field(default_factory=dict)
    isolation_manifest_sha256: str | None = None
    forbidden_paths: tuple[Path, ...] = ()
    max_artifacts: int = _MAX_ARTIFACTS
    max_artifact_bytes: int = _MAX_ARTIFACT_BYTES
    max_artifact_total_bytes: int = _MAX_ARTIFACT_TOTAL_BYTES
    expected_worker_uid: int | None = None
    expected_worker_gid: int | None = None
    shared_run_gid: int | None = None
    secret_canary_verdict: Mapping[str, Any] = dataclasses.field(default_factory=dict)
    require_secret_canary: bool = False


@dataclasses.dataclass(frozen=True)
class ProcessRef:
    run_id: str
    pid: int
    pgid: int
    process_start_identity: str
    boot_session_id: str
    launch_nonce: str
    provider_session_id: str | None
    stdout_path: str
    stderr_path: str
    result_path: str
    started_at: str
    binary: BinaryAttestation
    base_sha: str
    session_id: int | None = None
    effective_uid: int | None = None
    effective_gid: int | None = None
    real_uid: int | None = None
    real_gid: int | None = None


@dataclasses.dataclass(frozen=True)
class ArtifactReceipt:
    path: str
    sha256: str
    size: int


@dataclasses.dataclass(frozen=True)
class WorkerResult:
    job_id: str
    run_id: str
    worker_id: str
    status: WorkerRunStatus
    structured_output: Mapping[str, Any] | None
    artifact_manifest: tuple[ArtifactReceipt, ...]
    git_manifest: Mapping[str, Any]
    usage: Mapping[str, Any]
    provider_session_id: str | None
    exit_code: int | None
    started_at: str
    finished_at: str
    error: str | None


@dataclasses.dataclass(frozen=True)
class CollectionReceipt:
    process_ref: ProcessRef
    result: WorkerResult
    stdout_sha256: str
    stderr_sha256: str
    result_sha256: str | None


@dataclasses.dataclass(frozen=True)
class CancelReceipt:
    run_id: str
    reason: str
    signal_sent: bool
    escalated_to_sigkill: bool
    already_exited: bool
    finished_at: str


@dataclasses.dataclass(frozen=True)
class ValidationReceipt:
    argv: tuple[str, ...]
    exit_code: int | None
    stdout_sha256: str
    stdout_size: int
    stderr_sha256: str
    stderr_size: int
    timed_out: bool
    error: str | None


@dataclasses.dataclass(frozen=True)
class _GitSnapshot:
    head: str
    status: bytes


@dataclasses.dataclass
class _JSONLState:
    thread_started: int = 0
    turn_started: int = 0
    turn_completed: int = 0
    provider_session_id: str | None = None
    final_agent_message: str | None = None
    usage: dict[str, Any] = dataclasses.field(default_factory=dict)
    failures: list[str] = dataclasses.field(default_factory=list)
    parse_errors: list[str] = dataclasses.field(default_factory=list)
    terminal_seen: bool = False

    def consume(self, raw_line: bytes) -> None:
        if not raw_line:
            self.parse_errors.append("empty JSONL line")
            return
        try:
            line = raw_line.decode("utf-8", errors="strict")
            event = json.loads(line)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            self.parse_errors.append(f"malformed JSONL: {type(exc).__name__}")
            return
        if not isinstance(event, dict):
            self.parse_errors.append("JSONL event is not an object")
            return
        event_type = event.get("type")
        if event_type not in _JSONL_EVENT_TYPES:
            self.parse_errors.append(f"unknown JSONL event type {event_type!r}")
            return
        if self.terminal_seen and event_type not in {"turn.completed", "turn.failed", "error"}:
            self.parse_errors.append(f"event {event_type!r} arrived after terminal event")
        if event_type == "thread.started":
            self.thread_started += 1
            thread_id = event.get("thread_id")
            if not isinstance(thread_id, str) or not thread_id:
                self.parse_errors.append("thread.started lacks thread_id")
            elif self.provider_session_id not in {None, thread_id}:
                self.parse_errors.append("multiple provider thread ids")
            else:
                self.provider_session_id = thread_id
        elif event_type == "turn.started":
            self.turn_started += 1
        elif event_type == "turn.completed":
            self.turn_completed += 1
            self.terminal_seen = True
            usage = event.get("usage", {})
            if not isinstance(usage, dict):
                self.parse_errors.append("turn.completed usage is not an object")
            else:
                self.usage = usage
        elif event_type in {"turn.failed", "error"}:
            self.terminal_seen = True
            value = event.get("error") or event.get("message") or event_type
            if isinstance(value, dict):
                value = value.get("message") or json.dumps(value, sort_keys=True)
            self.failures.append(str(value)[:1000])
        elif event_type.startswith("item."):
            item = event.get("item")
            if not isinstance(item, dict) or not isinstance(item.get("type"), str):
                self.parse_errors.append(f"{event_type} lacks typed item")
            elif event_type == "item.completed" and item.get("type") == "agent_message":
                text = item.get("text")
                if not isinstance(text, str) or not text:
                    self.parse_errors.append("completed agent_message lacks text")
                else:
                    self.final_agent_message = text

    def validate(self) -> None:
        errors = list(self.parse_errors)
        if self.thread_started != 1:
            errors.append(f"expected one thread.started, got {self.thread_started}")
        if self.turn_started != 1:
            errors.append(f"expected one turn.started, got {self.turn_started}")
        if self.turn_completed != 1:
            errors.append(f"expected one turn.completed, got {self.turn_completed}")
        if self.failures:
            errors.append("provider failure event: " + "; ".join(self.failures))
        if not self.final_agent_message:
            errors.append("missing final agent_message")
        if errors:
            raise ResultValidationError("; ".join(errors)[:3000])
        _validate_usage(self.usage)


@dataclasses.dataclass
class _RunState:
    spec: LaunchSpec
    ref: ProcessRef
    process: asyncio.subprocess.Process
    parser: _JSONLState
    baseline: _GitSnapshot
    stdout_fd: int
    stderr_fd: int
    violation: asyncio.Event
    process_wait_task: asyncio.Task[int]
    launch_attestation: LaunchAttestation
    stdout_task: asyncio.Task[None] | None = None
    stderr_task: asyncio.Task[None] | None = None
    monitor_task: asyncio.Task[None] | None = None
    termination_lock: asyncio.Lock = dataclasses.field(default_factory=asyncio.Lock)
    status: WorkerRunStatus = WorkerRunStatus.STARTING
    stream_errors: list[str] = dataclasses.field(default_factory=list)
    cancel_reason: str | None = None
    timed_out: bool = False
    escalated: bool = False
    # Set once the verified original process group has been *proven* absent.
    # A group cannot come back, so this latches: no later sweep may re-probe or
    # signal that PGID, which the host may already have recycled to a stranger.
    group_proven_absent: bool = False
    finished_at: str | None = None
    receipt: CollectionReceipt | None = None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _sha256_path(path: Path, *, max_bytes: int | None = None) -> str:
    digest = hashlib.sha256()
    total = 0
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if max_bytes is not None and total > max_bytes:
                raise ResultValidationError(f"file exceeds {max_bytes} byte limit: {path}")
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _path_identity(path: Path) -> dict[str, Any]:
    resolved = path.resolve(strict=True)
    info = resolved.lstat()
    return {
        "path": str(resolved),
        "device": int(info.st_dev),
        "inode": int(info.st_ino),
        "mode": stat.S_IMODE(info.st_mode),
        "uid": int(info.st_uid),
        "gid": int(info.st_gid),
        "mtime_ns": int(info.st_mtime_ns),
    }


_SENSITIVE_ARG_RE = re.compile(
    r"(?i)(authorization|credential|lease[_-]?token|password|secret|token)"
)


def _redact_argv(argv: Sequence[str]) -> tuple[str, ...]:
    """Return an audit-safe argv without ever serializing credential values."""

    redacted: list[str] = []
    hide_next = False
    for raw in argv:
        value = str(raw)
        if hide_next:
            redacted.append("<redacted>")
            hide_next = False
            continue
        if _SENSITIVE_ARG_RE.search(value):
            if "=" in value:
                redacted.append(value.split("=", 1)[0] + "=<redacted>")
            else:
                redacted.append(value)
                hide_next = True
            continue
        redacted.append(value)
    return tuple(redacted)


def validate_secret_canary_verdict(
    value: Mapping[str, Any] | None,
    *,
    require_passed: bool,
) -> dict[str, Any]:
    """Validate a hash/status-only canary receipt; raw sentinel values are forbidden."""

    if not value:
        if require_passed:
            raise LaunchValidationError("a passing distinct-principal secret canary is required")
        return {
            "schema_version": SECRET_CANARY_SCHEMA_VERSION,
            "passed": False,
            "status": "NOT_PROVIDED",
            "checks": {},
        }
    try:
        document = json.loads(
            json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)
        )
    except (TypeError, ValueError) as exc:
        raise LaunchValidationError(f"secret canary verdict is not JSON data: {exc}") from exc
    if not isinstance(document, dict):
        raise LaunchValidationError("secret canary verdict must be a mapping")
    allowed_top = {
        "schema_version",
        "passed",
        "checks",
        "receipt_sha256",
        "control_environment_probe_sha256",
        "observed_at",
        "worker_auth_exception",
    }
    if set(document) != allowed_top:
        raise LaunchValidationError("secret canary verdict fields are incomplete or unknown")
    if document.get("schema_version") != SECRET_CANARY_SCHEMA_VERSION:
        raise LaunchValidationError("secret canary verdict schema is unsupported")
    checks = document.get("checks")
    if not isinstance(checks, dict) or set(checks) != _SECRET_CANARY_CHECKS:
        raise LaunchValidationError("secret canary verdict is missing required checks")
    if any(result != "DENIED" for result in checks.values()):
        raise LaunchValidationError("every unrelated secret canary check must be DENIED")
    digest = document.get("receipt_sha256")
    if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
        raise LaunchValidationError("secret canary verdict requires a receipt SHA-256")
    probe_digest = document.get("control_environment_probe_sha256")
    if (
        not isinstance(probe_digest, str)
        or re.fullmatch(r"[0-9a-f]{64}", probe_digest) is None
    ):
        raise LaunchValidationError(
            "secret canary verdict requires a control-environment probe SHA-256"
        )
    if document.get("worker_auth_exception") != "DEDICATED_CODEX_HOME_ONLY":
        raise LaunchValidationError("worker authentication exception is not explicit")
    if document.get("passed") is not True:
        raise LaunchValidationError("secret canary verdict did not pass")
    observed_at = document.get("observed_at")
    if not isinstance(observed_at, str) or not observed_at:
        raise LaunchValidationError("secret canary verdict requires an observation time")
    return document


def _read_limited(path: Path, maximum: int) -> bytes:
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise LaunchValidationError(f"expected regular non-symlink file: {path}")
    if info.st_size > maximum:
        raise LaunchValidationError(f"file exceeds {maximum} byte limit: {path}")
    with path.open("rb") as handle:
        value = handle.read(maximum + 1)
    if len(value) > maximum:
        raise LaunchValidationError(f"file exceeds {maximum} byte limit: {path}")
    return value


def _run_checked(argv: Sequence[str], *, timeout: float = 10.0) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        list(argv),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        errors="replace",
        timeout=timeout,
        env={
            "PATH": _SAFE_PATH,
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "HOME": "/var/empty",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0",
            "GCM_INTERACTIVE": "never",
        },
        check=False,
    )
    if len(result.stdout) > 1024 * 1024 or len(result.stderr) > 1024 * 1024:
        raise LaunchValidationError(f"preflight command produced excessive output: {argv[0]}")
    return result


def _run_binary_attestation_command(
    argv: Sequence[str], *, timeout: float
) -> subprocess.CompletedProcess[str]:
    try:
        return _run_checked(argv, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        executable = Path(argv[0]).name if argv else "unknown"
        raise BinaryAttestationError(
            f"Codex binary attestation command {executable!r} timed out "
            f"after {timeout:.0f} seconds"
        ) from exc


def attest_codex_binary(
    binary_path: str | os.PathLike[str],
    *,
    allowed_versions: frozenset[str] | None = None,
    required_team_identifier: str | None = _OPENAI_TEAM_IDENTIFIER,
) -> BinaryAttestation:
    """Attest one absolute, direct native Codex executable without invoking a model."""

    path = Path(binary_path)
    if not path.is_absolute():
        raise BinaryAttestationError("Codex binary path must be absolute")
    try:
        info = path.lstat()
    except OSError as exc:
        raise BinaryAttestationError(f"Codex binary unavailable: {exc}") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise BinaryAttestationError("Codex binary must be a direct regular file, not a symlink")
    if not os.access(path, os.X_OK):
        raise BinaryAttestationError("Codex binary is not executable")
    if info.st_mode & 0o022:
        raise BinaryAttestationError("Codex binary must not be group/other writable")
    try:
        with path.open("rb") as handle:
            magic = handle.read(4)
    except OSError as exc:
        raise BinaryAttestationError(f"cannot read Codex binary: {exc}") from exc
    # Thin and universal Mach-O magic values, in both byte orders.
    if platform.system() == "Darwin" and magic not in {
        b"\xcf\xfa\xed\xfe", b"\xfe\xed\xfa\xcf", b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca",
    }:
        raise BinaryAttestationError("Codex executable is not a native Mach-O binary")

    version_run = _run_binary_attestation_command(
        [str(path), "--version"], timeout=10.0
    )
    if version_run.returncode != 0:
        raise BinaryAttestationError(
            f"Codex version probe failed: {(version_run.stderr or version_run.stdout)[-500:]}"
        )
    match = re.fullmatch(r"codex-cli\s+([^\s]+)\s*", version_run.stdout)
    if match is None:
        raise BinaryAttestationError(f"unexpected Codex version output: {version_run.stdout[:200]!r}")
    version = match.group(1)
    if allowed_versions is not None and version not in allowed_versions:
        raise BinaryAttestationError(f"Codex version {version!r} is not allowlisted")

    team_identifier: str | None = None
    if platform.system() == "Darwin":
        verify = _run_binary_attestation_command(
            ["/usr/bin/codesign", "--verify", "--strict", str(path)],
            timeout=_CODE_SIGNATURE_TIMEOUT_SECONDS,
        )
        if verify.returncode != 0:
            raise BinaryAttestationError(f"Codex code signature invalid: {verify.stderr[-500:]}")
        details = _run_binary_attestation_command(
            ["/usr/bin/codesign", "-dv", "--verbose=4", str(path)],
            timeout=_CODE_SIGNATURE_TIMEOUT_SECONDS,
        )
        code_text = details.stdout + "\n" + details.stderr
        team_match = re.search(r"^TeamIdentifier=(.+)$", code_text, re.MULTILINE)
        team_identifier = team_match.group(1).strip() if team_match else None
        if required_team_identifier and team_identifier != required_team_identifier:
            raise BinaryAttestationError(
                f"Codex signer team {team_identifier!r} does not match required team"
            )

    return BinaryAttestation(
        path=str(path),
        real_path=str(path.resolve(strict=True)),
        version=version,
        sha256=_sha256_path(path),
        team_identifier=team_identifier,
        size=info.st_size,
        device=info.st_dev,
        inode=info.st_ino,
        mode=stat.S_IMODE(info.st_mode),
        uid=info.st_uid,
        gid=info.st_gid,
        mtime_ns=info.st_mtime_ns,
    )


def _assert_binary_unchanged(attestation: BinaryAttestation) -> None:
    path = Path(attestation.real_path)
    try:
        info = path.lstat()
    except OSError as exc:
        raise BinaryAttestationError(f"attested Codex binary disappeared: {exc}") from exc
    actual = (
        info.st_dev,
        info.st_ino,
        info.st_size,
        stat.S_IMODE(info.st_mode),
        info.st_uid,
        info.st_gid,
        info.st_mtime_ns,
    )
    expected = (
        attestation.device,
        attestation.inode,
        attestation.size,
        attestation.mode,
        attestation.uid,
        attestation.gid,
        attestation.mtime_ns,
    )
    if actual != expected or _sha256_path(path) != attestation.sha256:
        raise BinaryAttestationError("attested Codex binary changed before launch")


# ---------------------------------------------------------------------------
# Install-time Codex attestation receipt
# ---------------------------------------------------------------------------
# ``ops/executive_os/install.sh`` runs as root, warm, at normal process
# priority.  It pays the real cost of attestation exactly once -- a
# ``codesign --verify --strict`` on the ~220 MB Codex binary plus a
# ``--version`` probe -- and records the verdict plus the binary's cheap
# filesystem identity in a root-owned receipt.  ``CodexWorkerAdapter``, run
# from the *worker* daemon under ``ProcessType=Background`` (CPU scheduling
# politeness only).  launchd's ``LowPriorityIO=true`` disk I/O throttling
# -- once also inherited here -- was removed from both Executive plists;
# see tests/test_executive_launchd_config.py::
# test_executive_daemons_do_not_throttle_disk_io.  The worker no longer
# has to repeat the attestation cost, and therefore no longer has a
# codesign/--version call on its startup path that a cold trust-service
# cache or host load can push past a timeout -- true regardless of I/O
# policy: install-time attestation was never only a throttling
# workaround, since repeated subprocess calls on every worker start are
# real, avoidable cost on their own terms.
CODEX_ATTESTATION_RECEIPT_SCHEMA_VERSION = "mastermind.executive_codex_attestation/v1"

# The fields pinned in the receipt and re-checked against a fresh
# ``os.fstat`` at every worker startup.  ``ctime_ns`` is the load-bearing
# tamper signal: unlike ``mtime_ns`` (which any writer can backdate with
# ``utimes``), nothing can set ``st_ctime_ns`` directly -- the kernel stamps
# it on every metadata or content change.  A same-size, same-content,
# same-mtime replacement written to a *new* inode still changes both
# ``inode`` and ``ctime_ns``.  This does NOT catch an attacker who is
# already root and willing to fabricate ctime at the filesystem level (e.g.
# raw device manipulation) -- that attacker already owns the machine and
# every other control on it, including this one.
_CODEX_RECEIPT_IDENTITY_FIELDS: tuple[str, ...] = (
    "device",
    "inode",
    "size",
    "mode",
    "uid",
    "gid",
    "mtime_ns",
    "ctime_ns",
)
_CODEX_RECEIPT_FIELDS = frozenset(
    {
        "schema_version",
        "path",
        "version",
        "team_identifier",
        "sha256",
        "recorded_at",
        "identity",
    }
)
_MAX_CODEX_RECEIPT_BYTES = 64 * 1024
# Thin and universal Mach-O magic values, in both byte orders -- the same
# set attest_codex_binary checks.  Costs one 4-byte read on an already-open
# descriptor; dropping it would save nothing measurable.
_MACHO_MAGIC = frozenset(
    {b"\xcf\xfa\xed\xfe", b"\xfe\xed\xfa\xcf", b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca"}
)


class CodexAttestationReceiptError(BinaryAttestationError):
    """The install-time Codex attestation receipt is missing, unsafe, or stale."""


def _open_regular_nofollow(path: Path) -> int:
    """Open ``path`` for reading without following a trailing symlink.

    Callers ``fstat`` the returned descriptor rather than checking with
    ``lstat`` and opening afterward, so there is no window between the
    safety check and the read it protects.  ``O_NOFOLLOW`` is required, not
    best-effort: a platform without it would silently follow a symlink
    instead of refusing, which is exactly the TOCTOU this function exists
    to close.
    """

    if not hasattr(os, "O_NOFOLLOW"):
        raise CodexAttestationReceiptError(
            "this platform has no O_NOFOLLOW; refusing to open without symlink protection"
        )
    flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    return os.open(path, flags)


def _fstat_identity(fd: int) -> dict[str, int]:
    info = os.fstat(fd)
    return {
        "device": info.st_dev,
        "inode": info.st_ino,
        "size": info.st_size,
        "mode": stat.S_IMODE(info.st_mode),
        "uid": info.st_uid,
        "gid": info.st_gid,
        "mtime_ns": info.st_mtime_ns,
        "ctime_ns": info.st_ctime_ns,
    }


def _verify_codex_binary_identity(binary_path: Path, identity: Mapping[str, Any]) -> None:
    """Refuse to start if the Codex binary's cheap filesystem identity drifted.

    Opens ``binary_path`` exactly once and calls ``fstat`` on that single
    descriptor -- never stat-then-open, which would leave a TOCTOU race
    between the check and the open.  Every pinned field is compared; a
    mismatch names the specific field that moved so the operator does not
    have to guess from a bare "attestation failed".

    This intentionally never recomputes the binary's SHA-256 here: reading
    the full ~220 MB binary on every worker startup is exactly the cost this
    mechanism exists to remove.  The SHA-256 recorded in the receipt is for
    install-time audit and provenance only.
    """

    try:
        fd = _open_regular_nofollow(binary_path)
    except OSError as exc:
        raise CodexAttestationReceiptError(
            f"codex binary named by the attestation receipt is missing or unreadable: "
            f"{binary_path}"
        ) from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise CodexAttestationReceiptError(
                "codex binary named by the attestation receipt is not a regular file"
            )
        if platform.system() == "Darwin":
            magic = os.read(fd, 4)
            if magic not in _MACHO_MAGIC:
                raise CodexAttestationReceiptError(
                    "codex binary named by the attestation receipt is not a native "
                    "Mach-O binary"
                )
        observed = _fstat_identity(fd)
    finally:
        os.close(fd)
    for field in _CODEX_RECEIPT_IDENTITY_FIELDS:
        expected_value = identity[field]
        observed_value = observed[field]
        if observed_value != expected_value:
            raise CodexAttestationReceiptError(
                "codex binary identity mismatch at startup: "
                f"{field} changed since install-time attestation "
                f"(receipt={expected_value!r}, observed={observed_value!r}); "
                "remedy: re-run install.sh for this release, which always "
                "re-attests the current binary and rewrites the receipt"
            )


def load_codex_attestation_receipt(
    receipt_path: str | os.PathLike[str],
    *,
    expected_binary_path: str | os.PathLike[str],
    expected_owner_gid: int,
    expected_owner_uid: int = 0,
) -> BinaryAttestation:
    """Build a ``BinaryAttestation`` from an install-time receipt, fail-closed.

    This is the fast path ``CodexWorkerAdapter.__init__`` takes at every
    worker startup: one ``open``+``fstat`` of the receipt and one
    ``open``+``fstat`` of the Codex binary -- no ``codesign`` invocation, no
    ``--version`` subprocess, no re-read of the binary's bytes.  Those were
    already paid for once, warm, at normal process priority, by
    ``ops/executive_os/install.sh`` running as root; see that script for the
    write side that produces this receipt.

    The receipt file itself must be root-owned, mode 0440, a direct regular
    file with exactly one hard link, and not a symlink.  Mode 0440 (rather
    than the 0400 this repo's ``PYTHON_RUNTIME_RECEIPT`` uses for its
    root-to-root-only provenance file) is deliberate: this receipt's reader
    is the non-root worker process, so its own primary group -- passed in as
    ``expected_owner_gid`` -- needs read access; only root can ever write or
    replace it.  There is no path through this function that falls back to
    re-attesting the binary from scratch on a missing or unsafe receipt --
    that would silently reintroduce the exact slow cold-start path (a
    ``codesign`` call that can block on a cold trust-service cache under
    throttling and load) this mechanism exists to remove. Every failure is a
    refusal to start, naming the specific check that failed.
    """

    path = Path(receipt_path)
    if not path.is_absolute():
        raise CodexAttestationReceiptError("codex attestation receipt path must be absolute")
    try:
        fd = _open_regular_nofollow(path)
    except OSError as exc:
        raise CodexAttestationReceiptError(
            f"codex attestation receipt is missing or unreadable: {path}"
        ) from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise CodexAttestationReceiptError(
                "codex attestation receipt must be a direct regular file"
            )
        if info.st_nlink != 1:
            raise CodexAttestationReceiptError(
                "codex attestation receipt must have exactly one hard link"
            )
        if info.st_uid != int(expected_owner_uid):
            raise CodexAttestationReceiptError("codex attestation receipt is not root-owned")
        if info.st_gid != int(expected_owner_gid):
            raise CodexAttestationReceiptError(
                "codex attestation receipt has an unexpected group owner"
            )
        if stat.S_IMODE(info.st_mode) != 0o440:
            raise CodexAttestationReceiptError("codex attestation receipt has an unsafe mode")
        if info.st_size > _MAX_CODEX_RECEIPT_BYTES:
            raise CodexAttestationReceiptError(
                "codex attestation receipt exceeds its size limit"
            )
        raw = os.read(fd, _MAX_CODEX_RECEIPT_BYTES + 1)
    finally:
        os.close(fd)
    if len(raw) > _MAX_CODEX_RECEIPT_BYTES:
        raise CodexAttestationReceiptError("codex attestation receipt exceeds its size limit")
    try:
        document = json.loads(raw.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CodexAttestationReceiptError(
            "codex attestation receipt is not valid UTF-8 JSON"
        ) from exc
    if not isinstance(document, dict) or set(document) != _CODEX_RECEIPT_FIELDS:
        raise CodexAttestationReceiptError(
            "codex attestation receipt fields do not match the schema"
        )
    if document.get("schema_version") != CODEX_ATTESTATION_RECEIPT_SCHEMA_VERSION:
        raise CodexAttestationReceiptError(
            "codex attestation receipt schema version is unsupported"
        )
    for field in ("path", "version", "sha256", "recorded_at"):
        if not isinstance(document.get(field), str) or not document[field]:
            raise CodexAttestationReceiptError(
                f"codex attestation receipt field {field!r} is invalid"
            )
    if re.fullmatch(r"[0-9a-f]{64}", document["sha256"]) is None:
        raise CodexAttestationReceiptError("codex attestation receipt sha256 is malformed")
    team_identifier = document.get("team_identifier")
    if team_identifier is not None and not isinstance(team_identifier, str):
        raise CodexAttestationReceiptError(
            "codex attestation receipt team_identifier is invalid"
        )
    expected_binary = Path(expected_binary_path)
    if document["path"] != str(expected_binary):
        raise CodexAttestationReceiptError(
            "codex attestation receipt binary path does not match the configured codex_binary"
        )
    identity = document.get("identity")
    if not isinstance(identity, dict) or set(identity) != set(_CODEX_RECEIPT_IDENTITY_FIELDS):
        raise CodexAttestationReceiptError(
            "codex attestation receipt identity fields do not match the schema"
        )
    for field in _CODEX_RECEIPT_IDENTITY_FIELDS:
        if type(identity[field]) is not int:
            raise CodexAttestationReceiptError(
                f"codex attestation receipt identity field {field!r} is not an integer"
            )

    # Compare the recorded identity against a fresh fstat of the real binary
    # BEFORE asserting the two static invariants below.  A field-specific
    # mismatch (a swap, an edit) is a more specific and more actionable
    # diagnosis than a generic "not root-owned" -- and checking the dynamic
    # comparison first means a receipt that is internally self-consistent
    # (recorded and observed AGREE) but still describes an invalid binary
    # -- not root-owned, or group/other-writable -- is what reaches the
    # static checks below.
    _verify_codex_binary_identity(expected_binary, identity)

    # attest_codex_binary asserted these two on every cold start (a fresh
    # os.access(X_OK)/mode check plus never trusting a group/other-writable
    # or non-root-owned executable); the receipt now carries the binary's
    # mode and uid instead of re-probing them, so the same invariants are
    # asserted against the RECORDED values here -- which, by this point,
    # are also known to match the binary's real, current filesystem state.
    if identity["uid"] != 0:
        raise CodexAttestationReceiptError(
            "codex attestation receipt records a non-root-owned binary"
        )
    if identity["mode"] & 0o022:
        raise CodexAttestationReceiptError(
            "codex attestation receipt records a group/other-writable binary"
        )

    try:
        real_path = str(expected_binary.resolve(strict=True))
    except OSError as exc:
        raise CodexAttestationReceiptError(
            f"codex binary named by the attestation receipt could not be resolved: "
            f"{expected_binary}"
        ) from exc

    return BinaryAttestation(
        path=str(expected_binary),
        real_path=real_path,
        version=document["version"],
        sha256=document["sha256"],
        team_identifier=team_identifier,
        size=identity["size"],
        device=identity["device"],
        inode=identity["inode"],
        mode=identity["mode"],
        uid=identity["uid"],
        gid=identity["gid"],
        mtime_ns=identity["mtime_ns"],
    )


class _ProcBSDInfo(ctypes.Structure):
    # sys/proc_info.h, PROC_PIDTBSDINFO, macOS 26.  Native alignment is intentional.
    _fields_ = [
        ("pbi_flags", ctypes.c_uint32),
        ("pbi_status", ctypes.c_uint32),
        ("pbi_xstatus", ctypes.c_uint32),
        ("pbi_pid", ctypes.c_uint32),
        ("pbi_ppid", ctypes.c_uint32),
        ("pbi_uid", ctypes.c_uint32),
        ("pbi_gid", ctypes.c_uint32),
        ("pbi_ruid", ctypes.c_uint32),
        ("pbi_rgid", ctypes.c_uint32),
        ("pbi_svuid", ctypes.c_uint32),
        ("pbi_svgid", ctypes.c_uint32),
        ("rfu_1", ctypes.c_uint32),
        ("pbi_comm", ctypes.c_char * 16),
        ("pbi_name", ctypes.c_char * 32),
        ("pbi_nfiles", ctypes.c_uint32),
        ("pbi_pgid", ctypes.c_uint32),
        ("pbi_pjobc", ctypes.c_uint32),
        ("e_tdev", ctypes.c_uint32),
        ("e_tpgid", ctypes.c_uint32),
        ("pbi_nice", ctypes.c_int32),
        ("pbi_start_tvsec", ctypes.c_uint64),
        ("pbi_start_tvusec", ctypes.c_uint64),
    ]


class ProcessInspector:
    """OS process identity source, injectable in model-free tests."""

    def boot_session_id(self) -> str:
        if platform.system() == "Darwin":
            result = _run_checked(["/usr/sbin/sysctl", "-n", "kern.bootsessionuuid"])
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        # The fallback remains boot-scoped for one adapter process.  It is not used
        # as a cross-restart recovery identity on non-macOS hosts.
        return f"adapter-{os.getpid()}"

    def inspect(self, pid: int) -> ProcessIdentity:
        if platform.system() == "Darwin":
            libproc = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
            proc_pidinfo = libproc.proc_pidinfo
            proc_pidinfo.argtypes = [
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_uint64,
                ctypes.c_void_p,
                ctypes.c_int,
            ]
            proc_pidinfo.restype = ctypes.c_int
            info = _ProcBSDInfo()
            size = ctypes.sizeof(info)
            returned = proc_pidinfo(pid, 3, 0, ctypes.byref(info), size)
            if returned != size or int(info.pbi_pid) != pid:
                raise ProcessIdentityError(f"cannot resolve macOS process identity for pid {pid}")
            identity = f"{info.pbi_start_tvsec}.{info.pbi_start_tvusec:06d}"
            try:
                session_id = os.getsid(pid)
            except OSError as exc:
                raise ProcessIdentityError(
                    f"cannot resolve macOS process session for pid {pid}"
                ) from exc
            return ProcessIdentity(
                start_identity=identity,
                pgid=int(info.pbi_pgid),
                session_id=int(session_id),
                effective_uid=int(info.pbi_uid),
                effective_gid=int(info.pbi_gid),
                real_uid=int(info.pbi_ruid),
                real_gid=int(info.pbi_rgid),
            )

        try:
            pgid = os.getpgid(pid)
            session_id = os.getsid(pid)
        except ProcessLookupError as exc:
            raise ProcessIdentityError(f"process {pid} is absent") from exc
        result = _run_checked(
            ["/bin/ps", "-o", "lstart=,uid=,gid=", "-p", str(pid)]
        )
        if result.returncode != 0 or not result.stdout.strip():
            raise ProcessIdentityError(f"cannot resolve process start time for pid {pid}")
        fields = result.stdout.strip().rsplit(maxsplit=2)
        if len(fields) != 3:
            raise ProcessIdentityError(f"cannot parse process principal for pid {pid}")
        start_identity, uid_text, gid_text = fields
        try:
            uid = int(uid_text)
            gid = int(gid_text)
        except ValueError as exc:
            raise ProcessIdentityError(f"cannot parse process principal for pid {pid}") from exc
        return ProcessIdentity(
            start_identity=start_identity,
            pgid=int(pgid),
            session_id=int(session_id),
            effective_uid=uid,
            effective_gid=gid,
            real_uid=uid,
            real_gid=gid,
        )

    def identity(self, pid: int) -> tuple[str, int]:
        """Compatibility projection used by the Phase 1B cancellation path."""

        identity = self.inspect(pid)
        return identity.start_identity, identity.pgid


def _normalise_relative_path(value: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise LaunchValidationError(f"invalid artifact path {value!r}")
    parsed = PurePosixPath(value)
    if parsed.is_absolute() or any(part in {"", ".", ".."} for part in parsed.parts):
        raise LaunchValidationError(f"artifact path must be canonical and relative: {value!r}")
    return parsed.as_posix()


def _normalise_declared_artifact_path(value: str) -> str:
    normalised = _normalise_relative_path(value)
    if any(character in normalised for character in "*?["):
        raise ResultValidationError(f"declared artifact path cannot be a glob: {value!r}")
    return normalised


def _is_protected_workspace_path(value: str) -> bool:
    parts = PurePosixPath(value).parts
    return bool(parts) and (
        parts[0] in {".git", ".codex"}
        or value == "config.toml"
        or any(part == ".env" or part.startswith(".env.") for part in parts)
    )


def _path_matches_patterns(value: str, patterns: Sequence[str]) -> bool:
    value_parts = value.split("/")

    def _matches(pattern: str) -> bool:
        pattern_parts = pattern.split("/")

        def _walk(pattern_index: int, value_index: int) -> bool:
            if pattern_index == len(pattern_parts):
                return value_index == len(value_parts)
            part = pattern_parts[pattern_index]
            if part == "**":
                return any(
                    _walk(pattern_index + 1, candidate)
                    for candidate in range(value_index, len(value_parts) + 1)
                )
            return (
                value_index < len(value_parts)
                and fnmatch.fnmatchcase(value_parts[value_index], part)
                and _walk(pattern_index + 1, value_index + 1)
            )

        return _walk(0, 0)

    return any(_matches(pattern) for pattern in patterns)


def _authority_set(spec: LaunchSpec) -> frozenset[str]:
    if not isinstance(spec.authorities, tuple):
        raise LaunchValidationError("authorities must be an immutable tuple")
    raw: list[str] = list(spec.authorities)
    if spec.authority is not None:
        raw.append(spec.authority)
    if not raw:
        raw.append("READ")
    if any(not isinstance(value, str) or not value.strip() for value in raw):
        raise LaunchValidationError("authority values must be non-empty strings")
    values = frozenset(value.strip().upper() for value in raw)
    unknown = values - _ALLOWED_AUTHORITIES
    if unknown:
        raise LaunchValidationError(f"unsupported worker authorities: {sorted(unknown)}")
    return values


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _ensure_private_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise LaunchValidationError(f"private path is not a real directory: {path}")
    if stat.S_IMODE(info.st_mode) & 0o077:
        raise LaunchValidationError(f"private directory is accessible to group/other: {path}")
    return path.resolve(strict=True)


def _ensure_run_directory(path: Path, *, shared_gid: int | None) -> Path:
    """Accept either worker-private 0700 or one explicit control/worker group root."""

    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise LaunchValidationError(f"run path is not a real directory: {path}")
    mode = stat.S_IMODE(info.st_mode)
    if mode & 0o007:
        raise LaunchValidationError(f"run directory is accessible to other users: {path}")
    if mode & 0o070:
        if shared_gid is None or info.st_gid != int(shared_gid) or mode & 0o070 != 0o070:
            raise LaunchValidationError(
                f"run directory group boundary does not match the configured worker group: {path}"
            )
    return path.resolve(strict=True)


def _create_private_file(path: Path) -> int:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_CLOEXEC", 0)
    try:
        return os.open(path, flags, 0o600)
    except FileExistsError as exc:
        raise LaunchValidationError(f"run output already exists: {path}") from exc


def _validate_codex_home(path: Path) -> Path:
    resolved = path.resolve(strict=True)
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise LaunchValidationError("CODEX_HOME must be a real directory")
    if stat.S_IMODE(info.st_mode) & 0o077:
        raise LaunchValidationError("CODEX_HOME must be mode 0700 or narrower")
    auth = resolved / "auth.json"
    try:
        auth_info = auth.lstat()
    except OSError as exc:
        raise LaunchValidationError("dedicated CODEX_HOME/auth.json is required") from exc
    if stat.S_ISLNK(auth_info.st_mode) or not stat.S_ISREG(auth_info.st_mode):
        raise LaunchValidationError("CODEX_HOME/auth.json must be a regular non-symlink file")
    if stat.S_IMODE(auth_info.st_mode) & 0o077:
        raise LaunchValidationError("CODEX_HOME/auth.json must be mode 0600 or narrower")
    return resolved


def _safe_git_operation_identity(args: Sequence[str]) -> str:
    """Name only audited Git argv, never workspace or future caller data."""

    return _SAFE_GIT_OPERATION_IDENTITIES.get(tuple(args), "unknown")


def _command_scoped_git_trust_args(workspace: Path) -> tuple[str, str]:
    """Trust one already-canonical workspace for one Git process only.

    ``safe.directory`` is honored only from Git's protected configuration.
    The command scope supplied by ``-c`` is protected but is not persisted.
    Refusing aliases and glob syntax keeps this grant bound to the canonical
    workspace accepted by launch validation rather than to request text, a
    parent directory, or a family of repositories.
    """

    lexical = Path(workspace)
    if not lexical.is_absolute():
        raise LaunchValidationError("Git workspace trust path must be absolute")
    try:
        info = lexical.lstat()
        canonical = lexical.resolve(strict=True)
    except OSError as exc:
        raise LaunchValidationError("Git workspace trust path is unavailable") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise LaunchValidationError("Git workspace trust path must be a real directory")
    if lexical != canonical:
        raise LaunchValidationError("Git workspace trust path must already be canonical")
    rendered = os.fspath(canonical)
    if any(character in rendered for character in ("\x00", "\n", "\r", "*", "?", "[")):
        raise LaunchValidationError("Git workspace trust path contains unsafe syntax")
    return ("-c", f"safe.directory={rendered}")


def _git_command(workspace: Path, *args: str) -> bytes:
    trust_args = _command_scoped_git_trust_args(workspace)
    argv = [
        "/usr/bin/git",
        "--no-pager",
        "-c", "credential.helper=",
        "-c", "core.hooksPath=/dev/null",
        "-c", "core.fsmonitor=false",
        *trust_args,
        "-C", str(workspace),
        *args,
    ]
    try:
        result = subprocess.run(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=git_observation_env(
                {
                    "PATH": _SAFE_PATH,
                    "LANG": "C.UTF-8",
                    "LC_ALL": "C.UTF-8",
                    "HOME": "/var/empty",
                    "GIT_CONFIG_GLOBAL": "/dev/null",
                    "GIT_CONFIG_NOSYSTEM": "1",
                    "GIT_TERMINAL_PROMPT": "0",
                    "GCM_INTERACTIVE": "never",
                }
            ),
            timeout=_GIT_COMMAND_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise GitPreflightTimeout(
            operation=_safe_git_operation_identity(args),
            timeout_seconds=_GIT_COMMAND_TIMEOUT_SECONDS,
        ) from exc
    if len(result.stdout) > 4 * 1024 * 1024 or len(result.stderr) > 1024 * 1024:
        raise LaunchValidationError("Git preflight output exceeded its limit")
    if result.returncode != 0:
        raise GitPreflightFailed(
            operation=_safe_git_operation_identity(args),
            exit_code=result.returncode,
        )
    return result.stdout


def _validate_git_config(git_dir: Path) -> None:
    config_path = git_dir / "config"
    text = _read_limited(config_path, 256 * 1024).decode("utf-8", errors="strict")
    forbidden = (
        r"^\s*\[\s*remote\b",
        r"^\s*\[\s*include(?:if)?\b",
        r"^\s*\[\s*credential\b",
        r"^\s*\[\s*url\b",
        r"^\s*(?:url|pushurl|extraheader|sshcommand|helper)\s*=",
    )
    for pattern in forbidden:
        if re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE):
            raise LaunchValidationError("workspace Git config contains remote/credential indirection")
    for name in ("credentials", "credential", "config.worktree"):
        if (git_dir / name).exists():
            raise LaunchValidationError(f"workspace Git metadata contains forbidden {name}")


def _git_snapshot(workspace: Path, *, require_clean: bool) -> _GitSnapshot:
    with _launch_validation_stage("git_metadata"):
        git_dir = workspace / ".git"
        try:
            git_info = git_dir.lstat()
        except OSError as exc:
            raise LaunchValidationError("workspace must contain its own .git directory") from exc
        if stat.S_ISLNK(git_info.st_mode) or not stat.S_ISDIR(git_info.st_mode):
            raise LaunchValidationError("linked worktrees and .git files are not accepted")
        _validate_git_config(git_dir)
    with _launch_validation_stage("git_remote_policy"):
        remote = _git_command(workspace, "remote")
        if remote.strip():
            raise LaunchValidationError("workspace clone must have no Git remotes")
    with _launch_validation_stage("git_head_policy"):
        try:
            head = _git_command(
                workspace, "rev-parse", "--verify", "HEAD"
            ).decode("ascii", errors="strict").strip()
        except UnicodeDecodeError as exc:
            raise LaunchValidationError("workspace HEAD is not ASCII") from exc
        if not re.fullmatch(r"[0-9a-fA-F]{40,64}", head):
            raise LaunchValidationError("workspace HEAD is not an immutable Git object id")
    with _launch_validation_stage("git_cleanliness"):
        cleanliness = observe_launch_cleanliness(
            lambda arguments: _git_command(workspace, *arguments)
        )
        # `git status` intentionally respects ignore rules. A per-job clone
        # must also be free of pre-existing ignored/untracked material, since
        # ignored runtime files are still a mutation and secret-smuggling
        # surface.
        if require_clean and cleanliness.dirty:
            raise LaunchValidationError("workspace clone must be clean before launch")
    return _GitSnapshot(head=head.lower(), status=cleanliness.status)


def _validate_project_configuration(workspace: Path) -> None:
    """Fail closed on every Codex project-config layer visible from the clone."""

    root_config = workspace / "config.toml"
    if os.path.lexists(root_config):
        raise LaunchValidationError("workspace root config.toml is not allowed")

    dot_codex = workspace / ".codex"
    try:
        dot_info = dot_codex.lstat()
    except OSError as exc:
        raise LaunchValidationError("workspace must contain audited .codex config") from exc
    if stat.S_ISLNK(dot_info.st_mode) or not stat.S_ISDIR(dot_info.st_mode):
        raise LaunchValidationError("workspace .codex must be a real directory")
    config_path = dot_codex / "config.toml"
    try:
        config_info = config_path.lstat()
    except OSError as exc:
        raise LaunchValidationError(
            "workspace must contain audited .codex/config.toml"
        ) from exc
    if stat.S_ISLNK(config_info.st_mode) or not stat.S_ISREG(config_info.st_mode):
        raise LaunchValidationError(
            "workspace .codex/config.toml must be a regular non-symlink file"
        )
    if config_info.st_nlink != 1 or config_info.st_mode & 0o022:
        raise LaunchValidationError("workspace .codex/config.toml is not immutable enough")
    raw = _read_limited(config_path, _MAX_PROJECT_CONFIG_BYTES)
    actual_hash = hashlib.sha256(raw).hexdigest()
    if actual_hash != _AUDITED_PROJECT_CONFIG_SHA256:
        raise LaunchValidationError(
            "workspace .codex/config.toml does not match the audited worker-safe hash"
        )

    # Codex also searches ancestor `.codex/config.toml` layers.  The isolated
    # clone's exact file is the only project layer this adapter permits, even
    # though the session additionally marks the project untrusted.
    parent = workspace.parent
    while True:
        candidate = parent / ".codex" / "config.toml"
        if os.path.lexists(candidate):
            raise LaunchValidationError(
                f"unexpected ancestor Codex project config: {candidate}"
            )
        if parent.parent == parent:
            break
        parent = parent.parent


def _git_changed_paths(workspace: Path) -> tuple[str, ...]:
    values = _git_command(workspace, "diff", "--name-only", "-z", "HEAD", "--")
    values += _git_command(workspace, "ls-files", "--others", "-z")
    paths: set[str] = set()
    for raw in values.split(b"\0"):
        if not raw:
            continue
        try:
            decoded = raw.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise ResultValidationError("changed Git path is not valid UTF-8") from exc
        try:
            paths.add(_normalise_relative_path(decoded))
        except LaunchValidationError as exc:
            raise ResultValidationError(f"unsafe changed Git path: {decoded!r}") from exc
    return tuple(sorted(paths))


def _validate_usage(usage: Mapping[str, Any]) -> None:
    for key, value in usage.items():
        if not isinstance(key, str):
            raise ResultValidationError("usage keys must be strings")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ResultValidationError(f"usage field {key!r} is not numeric")
        if not math.isfinite(float(value)) or value < 0 or value > 10**15:
            raise ResultValidationError(f"usage field {key!r} is out of bounds")


def _json_type_matches(value: Any, expected: str) -> bool:
    return {
        "null": value is None,
        "boolean": isinstance(value, bool),
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "string": isinstance(value, str),
    }.get(expected, False)


_SCHEMA_KEYS = frozenset({
    "$schema", "$id", "$ref", "$defs", "definitions", "title", "description", "default",
    "examples", "deprecated", "readOnly", "writeOnly", "type", "enum", "const", "allOf",
    "anyOf", "oneOf", "not", "required", "properties", "patternProperties",
    "additionalProperties", "minProperties", "maxProperties", "items", "prefixItems",
    "minItems", "maxItems", "uniqueItems", "contains", "minContains", "maxContains",
    "minLength", "maxLength", "pattern", "format", "minimum", "maximum",
    "exclusiveMinimum", "exclusiveMaximum", "multipleOf",
})


def _resolve_local_ref(root: Any, ref: str) -> Any:
    if not ref.startswith("#"):
        raise ResultValidationError("only local JSON Schema references are supported")
    value = root
    if ref == "#":
        return value
    if not ref.startswith("#/"):
        raise ResultValidationError(f"invalid local JSON Schema reference {ref!r}")
    for raw in ref[2:].split("/"):
        key = raw.replace("~1", "/").replace("~0", "~")
        if not isinstance(value, dict) or key not in value:
            raise ResultValidationError(f"unresolved JSON Schema reference {ref!r}")
        value = value[key]
    return value


def _validate_schema_value(
    value: Any,
    schema: Any,
    *,
    root: Any,
    location: str,
    depth: int = 0,
) -> None:
    if depth > 64:
        raise ResultValidationError("JSON Schema recursion limit exceeded")
    if isinstance(schema, bool):
        if not schema:
            raise ResultValidationError(f"{location}: rejected by false schema")
        return
    if not isinstance(schema, dict):
        raise ResultValidationError(f"{location}: schema node is not an object or boolean")
    unknown = set(schema) - _SCHEMA_KEYS
    if unknown:
        raise ResultValidationError(f"unsupported JSON Schema keyword(s): {sorted(unknown)}")
    if "$ref" in schema:
        _validate_schema_value(
            value,
            _resolve_local_ref(root, schema["$ref"]),
            root=root,
            location=location,
            depth=depth + 1,
        )
    if "const" in schema and value != schema["const"]:
        raise ResultValidationError(f"{location}: value does not match const")
    if "enum" in schema:
        enum = schema["enum"]
        if not isinstance(enum, list) or value not in enum:
            raise ResultValidationError(f"{location}: value is outside enum")
    if "type" in schema:
        expected = schema["type"]
        expected_types = [expected] if isinstance(expected, str) else expected
        if (
            not isinstance(expected_types, list)
            or not expected_types
            or not all(isinstance(item, str) for item in expected_types)
            or not any(_json_type_matches(value, item) for item in expected_types)
        ):
            raise ResultValidationError(f"{location}: value has the wrong JSON type")
    for key in ("allOf", "anyOf", "oneOf"):
        if key not in schema:
            continue
        branches = schema[key]
        if not isinstance(branches, list) or not branches:
            raise ResultValidationError(f"{location}: {key} must be a non-empty list")
        passed = 0
        for branch in branches:
            try:
                _validate_schema_value(
                    value, branch, root=root, location=location, depth=depth + 1
                )
                passed += 1
            except ResultValidationError:
                pass
        if key == "allOf" and passed != len(branches):
            raise ResultValidationError(f"{location}: allOf failed")
        if key == "anyOf" and passed == 0:
            raise ResultValidationError(f"{location}: anyOf failed")
        if key == "oneOf" and passed != 1:
            raise ResultValidationError(f"{location}: oneOf matched {passed} branches")
    if "not" in schema:
        try:
            _validate_schema_value(
                value, schema["not"], root=root, location=location, depth=depth + 1
            )
        except ResultValidationError:
            pass
        else:
            raise ResultValidationError(f"{location}: not schema matched")

    if isinstance(value, dict):
        required = schema.get("required", [])
        if not isinstance(required, list) or not all(isinstance(item, str) for item in required):
            raise ResultValidationError(f"{location}: required must contain strings")
        missing = [key for key in required if key not in value]
        if missing:
            raise ResultValidationError(f"{location}: missing required keys {missing}")
        if "minProperties" in schema and len(value) < int(schema["minProperties"]):
            raise ResultValidationError(f"{location}: too few properties")
        if "maxProperties" in schema and len(value) > int(schema["maxProperties"]):
            raise ResultValidationError(f"{location}: too many properties")
        properties = schema.get("properties", {})
        patterns = schema.get("patternProperties", {})
        if not isinstance(properties, dict) or not isinstance(patterns, dict):
            raise ResultValidationError(f"{location}: properties must be objects")
        matched: set[str] = set()
        for key, child_schema in properties.items():
            if key in value:
                matched.add(key)
                _validate_schema_value(
                    value[key], child_schema, root=root,
                    location=f"{location}.{key}", depth=depth + 1,
                )
        for pattern_text, child_schema in patterns.items():
            try:
                pattern = re.compile(pattern_text)
            except re.error as exc:
                raise ResultValidationError(f"invalid patternProperties regex: {exc}") from exc
            for key, child in value.items():
                if pattern.search(key):
                    matched.add(key)
                    _validate_schema_value(
                        child, child_schema, root=root,
                        location=f"{location}.{key}", depth=depth + 1,
                    )
        additional = schema.get("additionalProperties", True)
        for key, child in value.items():
            if key in matched:
                continue
            if additional is False:
                raise ResultValidationError(f"{location}: additional property {key!r}")
            if isinstance(additional, (dict, bool)):
                _validate_schema_value(
                    child, additional, root=root,
                    location=f"{location}.{key}", depth=depth + 1,
                )
            else:
                raise ResultValidationError(f"{location}: invalid additionalProperties")

    if isinstance(value, list):
        if "minItems" in schema and len(value) < int(schema["minItems"]):
            raise ResultValidationError(f"{location}: too few items")
        if "maxItems" in schema and len(value) > int(schema["maxItems"]):
            raise ResultValidationError(f"{location}: too many items")
        if schema.get("uniqueItems"):
            rendered = [json.dumps(item, sort_keys=True, separators=(",", ":")) for item in value]
            if len(rendered) != len(set(rendered)):
                raise ResultValidationError(f"{location}: duplicate array items")
        prefix = schema.get("prefixItems", [])
        if not isinstance(prefix, list):
            raise ResultValidationError(f"{location}: prefixItems must be a list")
        for index, child_schema in enumerate(prefix[:len(value)]):
            _validate_schema_value(
                value[index], child_schema, root=root,
                location=f"{location}[{index}]", depth=depth + 1,
            )
        if "items" in schema:
            start = len(prefix)
            for index in range(start, len(value)):
                _validate_schema_value(
                    value[index], schema["items"], root=root,
                    location=f"{location}[{index}]", depth=depth + 1,
                )
        if "contains" in schema:
            matches = 0
            for index, child in enumerate(value):
                try:
                    _validate_schema_value(
                        child, schema["contains"], root=root,
                        location=f"{location}[{index}]", depth=depth + 1,
                    )
                    matches += 1
                except ResultValidationError:
                    pass
            minimum = int(schema.get("minContains", 1))
            maximum = int(schema.get("maxContains", len(value)))
            if not minimum <= matches <= maximum:
                raise ResultValidationError(f"{location}: contains count {matches} out of bounds")

    if isinstance(value, str):
        if "minLength" in schema and len(value) < int(schema["minLength"]):
            raise ResultValidationError(f"{location}: string too short")
        if "maxLength" in schema and len(value) > int(schema["maxLength"]):
            raise ResultValidationError(f"{location}: string too long")
        if "pattern" in schema:
            try:
                if re.search(str(schema["pattern"]), value) is None:
                    raise ResultValidationError(f"{location}: string pattern mismatch")
            except re.error as exc:
                raise ResultValidationError(f"invalid schema regex: {exc}") from exc

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        number = float(value)
        if not math.isfinite(number):
            raise ResultValidationError(f"{location}: number is not finite")
        if "minimum" in schema and number < float(schema["minimum"]):
            raise ResultValidationError(f"{location}: number below minimum")
        if "maximum" in schema and number > float(schema["maximum"]):
            raise ResultValidationError(f"{location}: number above maximum")
        if "exclusiveMinimum" in schema and number <= float(schema["exclusiveMinimum"]):
            raise ResultValidationError(f"{location}: number below exclusiveMinimum")
        if "exclusiveMaximum" in schema and number >= float(schema["exclusiveMaximum"]):
            raise ResultValidationError(f"{location}: number above exclusiveMaximum")
        if "multipleOf" in schema:
            divisor = float(schema["multipleOf"])
            if divisor <= 0 or not math.isclose(number / divisor, round(number / divisor)):
                raise ResultValidationError(f"{location}: number is not a multipleOf")


def validate_json_schema(value: Any, schema: Any) -> None:
    """Validate against the bounded Draft 2020-12 subset used by worker results.

    Unsupported validation keywords fail closed instead of being silently ignored.
    Annotation keywords and local ``$ref``/``$defs`` are accepted.
    """

    _validate_schema_value(value, schema, root=schema, location="$", depth=0)


def _write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        written = os.write(fd, view)
        if written <= 0:
            raise OSError("short write to worker log")
        view = view[written:]


async def _pump_stream(
    reader: asyncio.StreamReader,
    *,
    fd: int,
    name: str,
    maximum: int,
    line_maximum: int | None,
    parser: _JSONLState | None,
    state: _RunState,
) -> None:
    total = 0
    line_buffer = bytearray()
    accepting = True
    try:
        while True:
            chunk = await reader.read(64 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if accepting and total <= maximum:
                _write_all(fd, chunk)
            elif accepting:
                accepting = False
                state.stream_errors.append(f"{name} exceeded {maximum} bytes")
                state.violation.set()
            if parser is None or not accepting:
                continue
            line_buffer.extend(chunk)
            while True:
                newline = line_buffer.find(b"\n")
                if newline < 0:
                    break
                line = bytes(line_buffer[:newline])
                del line_buffer[:newline + 1]
                if line_maximum is not None and len(line) > line_maximum:
                    state.stream_errors.append(f"{name} JSONL line exceeded {line_maximum} bytes")
                    state.violation.set()
                else:
                    parser.consume(line)
            if line_maximum is not None and len(line_buffer) > line_maximum:
                state.stream_errors.append(f"{name} JSONL line exceeded {line_maximum} bytes")
                state.violation.set()
                accepting = False
        if parser is not None and accepting and line_buffer:
            if line_maximum is not None and len(line_buffer) > line_maximum:
                state.stream_errors.append(f"{name} JSONL line exceeded {line_maximum} bytes")
                state.violation.set()
            else:
                parser.consume(bytes(line_buffer))
    except Exception as exc:  # noqa: BLE001 - converted into an invalid-result receipt
        state.stream_errors.append(f"{name} stream failure: {type(exc).__name__}: {exc}")
        state.violation.set()
    finally:
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def _process_group_exists(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except PermissionError as exc:
        raise ProcessIdentityError(f"cannot inspect process group {pgid}") from exc
    return True


async def _wait_for_process_group_exit(pgid: int, *, timeout: float = 2.0) -> bool:
    deadline = asyncio.get_running_loop().time() + timeout
    while _process_group_exists(pgid):
        if asyncio.get_running_loop().time() >= deadline:
            return False
        await asyncio.sleep(0.02)
    return True


async def _hash_validation_stream(
    reader: asyncio.StreamReader,
    *,
    maximum: int,
    exceeded: asyncio.Event,
) -> tuple[str, int]:
    digest = hashlib.sha256()
    total = 0
    while True:
        chunk = await reader.read(64 * 1024)
        if not chunk:
            break
        total += len(chunk)
        digest.update(chunk)
        if total > maximum:
            exceeded.set()
    return digest.hexdigest(), total


class CodexWorkerAdapter:
    """One-host, one-shot Codex process adapter with no queue/runtime authority."""

    def __init__(
        self,
        binary_path: str | os.PathLike[str],
        *,
        binary_attestation: BinaryAttestation | None = None,
        allowed_versions: frozenset[str] | None = None,
        required_team_identifier: str | None = _OPENAI_TEAM_IDENTIFIER,
        inspector: ProcessInspector | None = None,
    ) -> None:
        path = Path(binary_path)
        if not path.is_absolute():
            raise BinaryAttestationError("Codex binary path must be absolute")
        self.binary = binary_attestation or attest_codex_binary(
            path,
            allowed_versions=allowed_versions,
            required_team_identifier=required_team_identifier,
        )
        if Path(self.binary.real_path) != path.resolve(strict=True):
            raise BinaryAttestationError("attestation does not match configured binary")
        if allowed_versions is not None and self.binary.version not in allowed_versions:
            raise BinaryAttestationError("injected Codex version is not allowlisted")
        if (
            required_team_identifier is not None
            and self.binary.team_identifier != required_team_identifier
        ):
            raise BinaryAttestationError("injected Codex signer is not allowlisted")
        self.inspector = inspector or ProcessInspector()
        self._runs: dict[str, _RunState] = {}

    def _validate_spec(self, spec: LaunchSpec) -> tuple[Path, Path, Path, Path, _GitSnapshot, Any]:
        with _launch_validation_stage("spec_contract"):
            for field_name in ("run_id", "job_id", "worker_id"):
                value = getattr(spec, field_name)
                if not isinstance(value, str) or _ID_RE.fullmatch(value) is None:
                    raise LaunchValidationError(f"invalid {field_name}")
            if spec.run_id in self._runs:
                raise LaunchValidationError(f"run {spec.run_id!r} is already known")
            _authority_set(spec)
            if not isinstance(spec.prompt, str) or not spec.prompt.strip():
                raise LaunchValidationError("prompt is required")
            if len(spec.prompt.encode("utf-8")) > _MAX_PROMPT_BYTES:
                raise LaunchValidationError("prompt exceeds one MiB")
            if not (0 < float(spec.timeout_seconds) <= 24 * 60 * 60):
                raise LaunchValidationError("timeout_seconds is out of bounds")
            if not (0.1 <= float(spec.cancel_grace_seconds) <= 60):
                raise LaunchValidationError("cancel_grace_seconds is out of bounds")

        with _launch_validation_stage("workspace_identity"):
            workspace_lexical = Path(spec.workspace_path)
            if not workspace_lexical.is_absolute():
                raise LaunchValidationError("workspace path must be absolute")
            workspace_info = workspace_lexical.lstat()
            if stat.S_ISLNK(workspace_info.st_mode) or not stat.S_ISDIR(workspace_info.st_mode):
                raise LaunchValidationError("workspace must be a real directory")
            workspace = workspace_lexical.resolve(strict=True)
            if workspace == _PROJECT_ROOT:
                raise LaunchValidationError("production checkout cannot be used as a worker workspace")
        with _launch_validation_stage("project_configuration"):
            _validate_project_configuration(workspace)
        baseline = _git_snapshot(workspace, require_clean=True)
        with _launch_validation_stage("expected_base"):
            if spec.expected_base_sha and baseline.head != spec.expected_base_sha.lower():
                raise LaunchValidationError("workspace HEAD does not match expected base SHA")

        with _launch_validation_stage("run_directory"):
            run_lexical = Path(spec.run_dir)
            if not run_lexical.is_absolute():
                raise LaunchValidationError("run_dir must be absolute")
            run_dir = _ensure_run_directory(
                run_lexical,
                shared_gid=(int(spec.shared_run_gid) if spec.shared_run_gid is not None else None),
            )
            if _is_relative_to(run_dir, workspace) or _is_relative_to(workspace, run_dir):
                raise LaunchValidationError("run_dir and workspace must be disjoint")
        with _launch_validation_stage("isolation_manifest"):
            self._validate_isolation_manifest(
                spec, workspace, run_dir, verify_filesystem=True
            )
        home = _ensure_private_directory(run_dir / "home")
        tmp = _ensure_private_directory(run_dir / "tmp")
        _ensure_private_directory(run_dir / "logs")
        _ensure_private_directory(run_dir / "output")

        codex_home = _validate_codex_home(Path(spec.codex_home))
        if (spec.expected_worker_uid is None) != (spec.expected_worker_gid is None):
            raise LaunchValidationError("expected worker UID and GID must be configured together")
        if spec.require_secret_canary and spec.expected_worker_uid is None:
            raise LaunchValidationError(
                "a complete canary launch requires an expected OS worker principal"
            )
        if spec.expected_worker_uid is not None:
            expected_uid = int(spec.expected_worker_uid)
            expected_gid = int(spec.expected_worker_gid)
            if os.geteuid() != expected_uid or os.getegid() != expected_gid:
                raise LaunchValidationError(
                    "Codex adapter is not running as the configured worker principal"
                )
            try:
                worker_account = pwd.getpwnam(spec.worker_user)
            except KeyError as exc:
                raise LaunchValidationError("configured worker account does not exist") from exc
            if worker_account.pw_uid != expected_uid or worker_account.pw_gid != expected_gid:
                raise LaunchValidationError("configured worker account UID/GID does not match")
            for label, protected_path in (
                ("provider home", codex_home),
                ("provider auth", codex_home / "auth.json"),
            ):
                if protected_path.lstat().st_uid != expected_uid:
                    raise LaunchValidationError(
                        f"{label} is not owned by the configured worker principal"
                    )
            workspace_info = workspace.lstat()
            shared_workspace = (
                spec.shared_run_gid is not None
                and workspace_info.st_gid == int(spec.shared_run_gid)
                and stat.S_IMODE(workspace_info.st_mode) & 0o050 == 0o050
                and stat.S_IMODE(workspace_info.st_mode) & 0o007 == 0
            )
            if workspace_info.st_uid != expected_uid and not shared_workspace:
                raise LaunchValidationError(
                    "workspace is neither worker-owned nor inside the configured shared group boundary"
                )
        schema_path = Path(spec.result_schema_path)
        if not schema_path.is_absolute():
            raise LaunchValidationError("result schema path must be absolute")
        schema_resolved = schema_path.resolve(strict=True)
        if not _is_relative_to(schema_resolved, run_dir):
            raise LaunchValidationError("result schema must be contained by run_dir")
        schema_raw = _read_limited(schema_resolved, _MAX_SCHEMA_BYTES)
        try:
            schema = json.loads(schema_raw.decode("utf-8", errors="strict"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise LaunchValidationError(f"result schema is invalid JSON: {exc}") from exc
        if not isinstance(schema, (dict, bool)):
            raise LaunchValidationError("result schema root must be an object or boolean")

        allowed = tuple(_normalise_relative_path(value) for value in spec.allowed_artifact_paths)
        if len(allowed) != len(set(allowed)):
            raise LaunchValidationError("allowed artifact paths contain duplicates")
        for pattern in allowed:
            if _is_protected_workspace_path(pattern):
                raise LaunchValidationError(
                    f"write path targets protected Git/credential metadata: {pattern!r}"
                )
        if len(allowed) > _MAX_ARTIFACTS:
            raise LaunchValidationError("allowed artifact path patterns exceed adapter ceiling")
        if "WRITE_BRANCH" in _authority_set(spec) and not allowed:
            raise LaunchValidationError("WRITE_BRANCH requires at least one allowed write path")
        if not 0 <= int(spec.max_artifacts) <= _MAX_ARTIFACTS:
            raise LaunchValidationError("max_artifacts exceeds adapter ceiling")
        if not 0 < int(spec.max_artifact_bytes) <= _MAX_ARTIFACT_BYTES:
            raise LaunchValidationError("max_artifact_bytes exceeds adapter ceiling")
        if not 0 < int(spec.max_artifact_total_bytes) <= _MAX_ARTIFACT_TOTAL_BYTES:
            raise LaunchValidationError("max_artifact_total_bytes exceeds adapter ceiling")
        return workspace, run_dir, home, tmp, baseline, schema

    @staticmethod
    def _deny_tree(values: set[str], path: Path) -> None:
        resolved = str(path.resolve(strict=False))
        values.add(resolved)
        values.add(resolved + "/**")

    @staticmethod
    def _protected_workspace_paths(workspace: Path) -> set[str]:
        values: set[str] = set()
        for path in (
            workspace / ".git",
            workspace / ".codex",
        ):
            CodexWorkerAdapter._deny_tree(values, path)
        values.update(
            {
                str(workspace / "config.toml"),
                str(workspace / ".env"),
                str(workspace / ".env.*"),
            }
        )
        return values

    @staticmethod
    def _user_home_denials(
        spec: LaunchSpec, workspace: Path, run_dir: Path
    ) -> set[str]:
        users_root = Path("/Users")
        if any(_is_relative_to(path, users_root) for path in (workspace, run_dir)):
            if spec.isolation_roots:
                raise LaunchValidationError(
                    "secure worker assignments must not be placed beneath /Users"
                )
            # Compatibility for the local Phase 1B seam.  Complete Phase 1C
            # launches always configure control-owned roots outside /Users.
            return set()
        return {"/Users", "/Users/**"}

    @staticmethod
    def _validate_isolation_identity(value: Any, *, label: str) -> dict[str, Any]:
        if not isinstance(value, dict) or set(value) != {
            "path",
            "device",
            "inode",
            "mode",
            "uid",
            "gid",
            "mtime_ns",
        }:
            raise LaunchValidationError(f"{label} has an invalid identity shape")
        path = value.get("path")
        if not isinstance(path, str) or not Path(path).is_absolute():
            raise LaunchValidationError(f"{label} path must be absolute")
        if any(
            not isinstance(value.get(field), int) or isinstance(value.get(field), bool)
            for field in ("device", "inode", "mode", "uid", "gid", "mtime_ns")
        ):
            raise LaunchValidationError(f"{label} identity fields must be integers")
        return value

    def _validate_isolation_manifest(
        self,
        spec: LaunchSpec,
        workspace: Path,
        run_dir: Path,
        *,
        verify_filesystem: bool,
    ) -> None:
        if not spec.isolation_roots:
            if (
                spec.isolation_denied_paths
                or spec.isolation_manifest
                or spec.isolation_manifest_sha256 is not None
            ):
                raise LaunchValidationError(
                    "isolation manifest fields require configured isolation roots"
                )
            return
        manifest = spec.isolation_manifest
        if not isinstance(manifest, Mapping) or set(manifest) != {
            "schema_version",
            "roots",
            "entries",
            "workspace_path",
            "run_dir",
        }:
            raise LaunchValidationError("isolation manifest shape is invalid")
        if manifest.get("schema_version") != ISOLATION_MANIFEST_SCHEMA_VERSION:
            raise LaunchValidationError("isolation manifest schema is unsupported")
        digest = spec.isolation_manifest_sha256
        if (
            not isinstance(digest, str)
            or re.fullmatch(r"[0-9a-f]{64}", digest) is None
            or _canonical_sha256(manifest) != digest
        ):
            raise LaunchValidationError("isolation sibling manifest digest does not match")
        if manifest.get("workspace_path") != str(workspace) or manifest.get(
            "run_dir"
        ) != str(run_dir):
            raise LaunchValidationError("isolation manifest assignment identity drifted")
        root_values = manifest.get("roots")
        entry_values = manifest.get("entries")
        if (
            not isinstance(root_values, list)
            or not root_values
            or len(root_values) > 8
            or not isinstance(entry_values, list)
            or len(entry_values) > 256
        ):
            raise LaunchValidationError("isolation manifest lists are outside safe bounds")
        roots = [
            self._validate_isolation_identity(value, label="isolation root")
            for value in root_values
        ]
        root_paths = [str(value["path"]) for value in roots]
        configured_roots = sorted(
            str(Path(value).resolve(strict=False)) for value in spec.isolation_roots
        )
        if root_paths != sorted(root_paths) or root_paths != configured_roots:
            raise LaunchValidationError("isolation manifest roots are incomplete or unordered")
        entries: list[tuple[str, str, str, dict[str, Any]]] = []
        for raw in entry_values:
            if not isinstance(raw, dict) or set(raw) != {
                "root_path",
                "disposition",
                "identity",
            }:
                raise LaunchValidationError("isolation manifest entry shape is invalid")
            root_path = raw.get("root_path")
            disposition = raw.get("disposition")
            if root_path not in root_paths or disposition not in {
                "CURRENT_WORKSPACE",
                "CURRENT_RUN",
                "DENY",
            }:
                raise LaunchValidationError("isolation manifest entry policy is invalid")
            identity = self._validate_isolation_identity(
                raw.get("identity"), label="isolation entry"
            )
            entry_path = str(identity["path"])
            if Path(entry_path).parent != Path(str(root_path)):
                raise LaunchValidationError(
                    "isolation manifest entry is not a direct root child"
                )
            entries.append((entry_path, str(root_path), str(disposition), identity))
        if [item[0] for item in entries] != sorted(item[0] for item in entries):
            raise LaunchValidationError("isolation manifest entries are not ordered")
        if len({item[0] for item in entries}) != len(entries):
            raise LaunchValidationError("isolation manifest entries contain duplicates")
        dispositions = {item[0]: item[2] for item in entries}
        expected_denied = sorted(
            str(Path(value).resolve(strict=False))
            for value in spec.isolation_denied_paths
        )
        observed_denied = sorted(
            path for path, _root, disposition, _identity in entries if disposition == "DENY"
        )
        if observed_denied != expected_denied:
            raise LaunchValidationError("isolation denial list is incomplete")
        if dispositions.get(str(workspace)) != "CURRENT_WORKSPACE" or dispositions.get(
            str(run_dir)
        ) != "CURRENT_RUN":
            raise LaunchValidationError("isolation manifest omits a current assignment")
        if verify_filesystem:
            for identity in [*roots, *(item[3] for item in entries)]:
                if _path_identity(Path(str(identity["path"]))) != identity:
                    raise LaunchValidationError(
                        "isolation manifest filesystem identity changed before launch"
                    )

    def _isolation_denied_filesystem_paths(
        self, spec: LaunchSpec, workspace: Path, run_dir: Path
    ) -> set[str]:
        # The worker is intentionally blind to every macOS user home except the
        # exact assigned paths re-opened by ``_permission_overrides``.  This is
        # important even when a host root was omitted from configuration: a
        # read-only base profile must not make an administrative checkout or
        # another user's secrets ambiently readable.
        self._validate_isolation_manifest(
            spec, workspace, run_dir, verify_filesystem=False
        )
        values = self._user_home_denials(spec, workspace, run_dir)
        for path in spec.isolation_roots:
            if not Path(path).is_absolute():
                raise LaunchValidationError("isolation roots must be absolute")
        for path in spec.isolation_denied_paths:
            lexical = Path(path)
            if not lexical.is_absolute():
                raise LaunchValidationError("isolation denied paths must be absolute")
            self._deny_tree(values, lexical)
        return values

    def _sensitive_denied_filesystem_paths(
        self, spec: LaunchSpec, workspace: Path
    ) -> set[str]:
        try:
            real_home = Path(pwd.getpwuid(os.geteuid()).pw_dir).resolve()
        except (KeyError, OSError):
            real_home = Path.home().resolve()
        codex_home = Path(spec.codex_home).resolve()
        values = {
            str(real_home / ".ssh" / "**"),
            str(real_home / ".config" / "gh" / "**"),
            str(real_home / "Library" / "Keychains" / "**"),
            str(real_home / ".aws" / "**"),
            str(real_home / ".codex" / "auth.json"),
            str(codex_home / "**"),
            str(_PROJECT_ROOT / ".git" / "**"),
            str(_PROJECT_ROOT / "data" / "**"),
            str(_PROJECT_ROOT / ".env"),
            str(_PROJECT_ROOT / ".env.*"),
            "/etc/macro-api.env",
            "/etc/macro.env",
            "/etc/macro*.env",
            "/etc/mastermind.env",
            "/etc/mastermind*.env",
            "/root/**",
        }
        values.update(self._protected_workspace_paths(workspace))
        for path in spec.forbidden_paths:
            lexical = Path(path)
            if not lexical.is_absolute():
                raise LaunchValidationError("forbidden paths must be absolute")
            resolved = str(lexical.resolve(strict=False))
            values.add(resolved)
            values.add(resolved + "/**")
            # SQLite journals are siblings, not children of the main database
            # path.  A controller-DB deny must cover every common sidecar so a
            # worker cannot recover lease tokens or state from WAL bytes.
            values.add(resolved + "-wal")
            values.add(resolved + "-shm")
            values.add(resolved + "-journal")
            values.add(resolved + "-*")
        return values

    def _denied_filesystem_paths(self, spec: LaunchSpec, workspace: Path) -> list[str]:
        return sorted(
            self._isolation_denied_filesystem_paths(
                spec, workspace, Path(spec.run_dir).resolve(strict=False)
            )
            | self._sensitive_denied_filesystem_paths(spec, workspace)
        )

    def _permission_overrides(self, spec: LaunchSpec, workspace: Path) -> list[str]:
        write = "WRITE_BRANCH" in _authority_set(spec)
        profile_name = "mastermind_exec_write" if write else "mastermind_exec_read"
        run_dir = Path(spec.run_dir).resolve(strict=False)
        # Insertion order is deliberate.  Broad user/shared-root denials land
        # first; the exact assigned workspace and run are then re-opened; and
        # sensitive paths inside those assignments are denied last.  Codex's
        # filesystem map also resolves the exact child entries more narrowly
        # than their shared-root parent, so this remains safe independent of
        # whether the renderer uses last-match or most-specific precedence.
        filesystem: dict[str, str] = {
            denied: "deny"
            for denied in sorted(
                self._isolation_denied_filesystem_paths(spec, workspace, run_dir)
            )
        }
        filesystem[str(workspace)] = "read"
        filesystem[str(workspace / "**")] = "read"
        filesystem[str(run_dir)] = "read"
        filesystem[str(run_dir / "**")] = "read"
        for writable_run_path in (
            run_dir / "home",
            run_dir / "tmp",
            run_dir / "validation-home",
            run_dir / "validation-tmp",
            run_dir / "output",
        ):
            filesystem[str(writable_run_path)] = "write"
            filesystem[str(writable_run_path / "**")] = "write"
        if write:
            for relative in spec.allowed_artifact_paths:
                pattern = _normalise_relative_path(relative)
                filesystem[str(workspace / pattern)] = "write"
        for denied in sorted(self._sensitive_denied_filesystem_paths(spec, workspace)):
            filesystem[denied] = "deny"
        rendered = ",".join(
            f"{json.dumps(key)}={json.dumps(value)}" for key, value in filesystem.items()
        )
        return [
            "-c", f"default_permissions={json.dumps(profile_name)}",
            "-c", f"permissions.{profile_name}.description={json.dumps('Executive worker boundary')}",
            "-c", f"permissions.{profile_name}.extends={json.dumps(':read-only')}",
            "-c", f"permissions.{profile_name}.filesystem={{{rendered}}}",
            "-c", f"permissions.{profile_name}.network.enabled=false",
        ]

    def _argv(
        self,
        spec: LaunchSpec,
        workspace: Path,
        schema_path: Path,
        result_path: Path,
        home: Path,
        tmp: Path,
    ) -> list[str]:
        shell_set = {
            "HOME": str(home),
            "USER": spec.worker_user,
            "LOGNAME": spec.worker_user,
            "SHELL": "/bin/zsh",
            "PATH": _SAFE_PATH,
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "TZ": "UTC",
            "TMPDIR": str(tmp) + "/",
            "NO_COLOR": "1",
            "GIT_TERMINAL_PROMPT": "0",
            "GCM_INTERACTIVE": "never",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_NOSYSTEM": "1",
        }
        shell_values = ",".join(
            f"{key}={json.dumps(value)}" for key, value in shell_set.items()
        )
        shell_allowlist = ",".join(json.dumps(key) for key in shell_set)
        shell_policy = (
            '{inherit="none",ignore_default_excludes=false,'
            f"include_only=[{shell_allowlist}],set={{{shell_values}}}}}"
        )
        argv = [
            self.binary.real_path,
            "exec",
            "--json",
            "--ephemeral",
            "--ignore-user-config",
            "--ignore-rules",
            "--strict-config",
            "--model", spec.model,
            "--color", "never",
            "-C", str(workspace),
            "--output-schema", str(schema_path),
            "--output-last-message", str(result_path),
            "-c", f"model_reasoning_effort={json.dumps(spec.reasoning_effort)}",
            "-c", 'approval_policy="never"',
            "-c", "agents.enabled=false",
            "-c", 'web_search="disabled"',
            "-c", (
                "projects={"
                f"{json.dumps(str(workspace))}={{trust_level=\"untrusted\"}}"
                "}"
            ),
            "-c", "project_doc_max_bytes=0",
            "-c", "project_doc_fallback_filenames=[]",
            "-c", "mcp_servers={}",
            "-c", f"shell_environment_policy={shell_policy}",
        ]
        argv.extend(self._permission_overrides(spec, workspace))
        for feature in _DISABLED_FEATURES:
            argv.extend(["--disable", feature])
        argv.append("-")
        return argv

    @staticmethod
    def _environment(spec: LaunchSpec, home: Path, tmp: Path, codex_home: Path) -> dict[str, str]:
        return {
            "HOME": str(home),
            "USER": spec.worker_user,
            "LOGNAME": spec.worker_user,
            "SHELL": "/bin/zsh",
            "PATH": _SAFE_PATH,
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "TZ": "UTC",
            "TMPDIR": str(tmp) + "/",
            "CODEX_HOME": str(codex_home),
            "NO_COLOR": "1",
            "GIT_TERMINAL_PROMPT": "0",
            "GCM_INTERACTIVE": "never",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_OPTIONAL_LOCKS": "0",
        }

    @staticmethod
    def _validation_environment(spec: LaunchSpec, home: Path, tmp: Path) -> dict[str, str]:
        # Deliberately omit CODEX_HOME: `codex sandbox` needs no provider auth
        # and resolves any local state beneath this isolated, empty HOME.
        return {
            "HOME": str(home),
            "USER": spec.worker_user,
            "LOGNAME": spec.worker_user,
            "SHELL": "/bin/zsh",
            "PATH": _SAFE_PATH,
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "TZ": "UTC",
            "TMPDIR": str(tmp) + "/",
            "NO_COLOR": "1",
            "GIT_TERMINAL_PROMPT": "0",
            "GCM_INTERACTIVE": "never",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_OPTIONAL_LOCKS": "0",
        }

    async def _terminate_validation_process(
        self,
        process: asyncio.subprocess.Process,
        wait_task: asyncio.Task[int],
        *,
        pid: int,
        pgid: int,
        start_identity: str,
        boot_id: str,
        grace_seconds: float,
    ) -> None:
        group_vanished = False
        if not wait_task.done():
            if self.inspector.boot_session_id() != boot_id:
                raise ProcessIdentityError("validation process boot identity changed")
            identity, observed_pgid = self.inspector.identity(pid)
            if identity != start_identity or observed_pgid != pgid:
                raise ProcessIdentityError("validation process identity changed")
            try:
                os.killpg(pgid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                await asyncio.wait_for(asyncio.shield(wait_task), timeout=grace_seconds)
            except asyncio.TimeoutError:
                if not wait_task.done():
                    if self.inspector.boot_session_id() != boot_id:
                        raise ProcessIdentityError(
                            "validation process boot identity changed before SIGKILL"
                        )
                    try:
                        identity, observed_pgid = self.inspector.identity(pid)
                    except ProcessIdentityError:
                        # Symmetric with _terminate: a *proven* absent group means
                        # the verified original leader and every remaining member
                        # already exited, so the SIGTERM above reached the
                        # terminated postcondition and there is nothing to
                        # escalate against.  Absence is proof, not inference --
                        # _process_group_exists raises when the observation itself
                        # is unavailable, so an unreadable group stays fail-closed.
                        # The result is carried forward rather than re-probed: a
                        # second probe could observe a PGID the host has already
                        # recycled to a foreign group, and an absent leader must
                        # never authorise signalling a reused group.
                        group_vanished = not _process_group_exists(pgid)
                    else:
                        if identity != start_identity or observed_pgid != pgid:
                            raise ProcessIdentityError(
                                "validation process identity changed before SIGKILL"
                            )
        if not group_vanished and _process_group_exists(pgid):
            try:
                os.killpg(pgid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        await wait_task
        if group_vanished:
            # Nothing was signalled and the group was already proven absent, so
            # there is no exit to wait for and no SIGKILL that could have been
            # survived.  Re-probing here would reopen the same reused-PGID
            # window the branch above exists to close.
            return
        if not await _wait_for_process_group_exit(pgid):
            raise ProcessIdentityError("validation process group survived SIGKILL")

    async def run_validation_argv(
        self,
        spec: LaunchSpec,
        argv: Sequence[str],
        *,
        timeout_seconds: float = 300.0,
    ) -> ValidationReceipt:
        """Run one declared argv directly in the same deny boundary, without auth.

        The native Codex binary is used only as a local Seatbelt launcher.  No
        model or provider session is started, no shell is interposed, and raw
        validation output is never persisted.
        """

        if isinstance(argv, (str, bytes)) or not isinstance(argv, Sequence):
            raise LaunchValidationError("validation command must be an argv sequence")
        exact_argv = tuple(argv)
        if not exact_argv or any(
            not isinstance(value, str) or not value or "\x00" in value
            for value in exact_argv
        ):
            raise LaunchValidationError(
                "validation argv must contain non-empty strings without NUL bytes"
            )
        if sum(len(value.encode("utf-8")) + 1 for value in exact_argv) > _MAX_VALIDATION_ARGV_BYTES:
            raise LaunchValidationError("validation argv exceeds 64 KiB")
        executable_name = PurePosixPath(exact_argv[0]).name.lower()
        if executable_name in _SHELL_EXECUTABLE_NAMES:
            raise LaunchValidationError("validation argv may not invoke a shell")
        timeout = float(timeout_seconds)
        if not 0.1 <= timeout <= 3600:
            raise LaunchValidationError("validation timeout is out of bounds")

        _authority_set(spec)
        workspace_lexical = Path(spec.workspace_path)
        if not workspace_lexical.is_absolute():
            raise LaunchValidationError("workspace path must be absolute")
        workspace_info = workspace_lexical.lstat()
        if stat.S_ISLNK(workspace_info.st_mode) or not stat.S_ISDIR(workspace_info.st_mode):
            raise LaunchValidationError("workspace must be a real directory")
        workspace = workspace_lexical.resolve(strict=True)
        if workspace == _PROJECT_ROOT:
            raise LaunchValidationError("production checkout cannot be used as a worker workspace")
        _validate_project_configuration(workspace)
        snapshot = _git_snapshot(workspace, require_clean=False)
        if spec.expected_base_sha and snapshot.head != spec.expected_base_sha.lower():
            raise LaunchValidationError("workspace HEAD does not match expected base SHA")

        run_lexical = Path(spec.run_dir)
        if not run_lexical.is_absolute():
            raise LaunchValidationError("run_dir must be absolute")
        run_dir = _ensure_run_directory(
            run_lexical,
            shared_gid=(int(spec.shared_run_gid) if spec.shared_run_gid is not None else None),
        )
        if _is_relative_to(run_dir, workspace) or _is_relative_to(workspace, run_dir):
            raise LaunchValidationError("run_dir and workspace must be disjoint")
        validation_home = _ensure_private_directory(run_dir / "validation-home")
        validation_tmp = _ensure_private_directory(run_dir / "validation-tmp")
        _validate_codex_home(Path(spec.codex_home))
        _assert_binary_unchanged(self.binary)

        read_spec = dataclasses.replace(
            spec,
            authorities=("READ", "RUN_TESTS"),
            authority=None,
            allowed_artifact_paths=(),
        )
        profile_name = "mastermind_exec_read"
        sandbox_argv = [
            self.binary.real_path,
            "sandbox",
            "-P",
            profile_name,
            "-C",
            str(workspace),
            *self._permission_overrides(read_spec, workspace),
            "--",
            *exact_argv,
        ]
        process = await asyncio.create_subprocess_exec(
            *sandbox_argv,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(workspace),
            env=self._validation_environment(spec, validation_home, validation_tmp),
            start_new_session=True,
            limit=128 * 1024,
        )
        if process.stdout is None or process.stderr is None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            await process.wait()
            raise CodexWorkerError("validation process pipes were not created")
        try:
            start_identity, pgid = self.inspector.identity(process.pid)
            boot_id = self.inspector.boot_session_id()
            if pgid != process.pid:
                raise ProcessIdentityError(
                    "validation process did not become its own process group"
                )
        except Exception:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            await process.wait()
            raise

        output_exceeded = asyncio.Event()
        wait_task = asyncio.create_task(process.wait())
        stdout_task = asyncio.create_task(
            _hash_validation_stream(
                process.stdout,
                maximum=_MAX_VALIDATION_STDOUT_BYTES,
                exceeded=output_exceeded,
            )
        )
        stderr_task = asyncio.create_task(
            _hash_validation_stream(
                process.stderr,
                maximum=_MAX_VALIDATION_STDERR_BYTES,
                exceeded=output_exceeded,
            )
        )
        exceeded_task = asyncio.create_task(output_exceeded.wait())
        timed_out = False
        error: str | None = None
        try:
            done, _ = await asyncio.wait(
                {wait_task, exceeded_task},
                timeout=timeout,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if not done:
                timed_out = True
                error = f"validation timed out after {timeout:g}s"
                await self._terminate_validation_process(
                    process,
                    wait_task,
                    pid=process.pid,
                    pgid=pgid,
                    start_identity=start_identity,
                    boot_id=boot_id,
                    grace_seconds=min(float(spec.cancel_grace_seconds), 5.0),
                )
            elif exceeded_task in done and output_exceeded.is_set() and not wait_task.done():
                error = "validation output exceeded its byte cap"
                await self._terminate_validation_process(
                    process,
                    wait_task,
                    pid=process.pid,
                    pgid=pgid,
                    start_identity=start_identity,
                    boot_id=boot_id,
                    grace_seconds=min(float(spec.cancel_grace_seconds), 5.0),
                )
            await wait_task
            if _process_group_exists(pgid):
                os.killpg(pgid, signal.SIGKILL)
                if not await _wait_for_process_group_exit(pgid):
                    raise ProcessIdentityError(
                        "validation left a live descendant process group"
                    )
                error = error or "validation left live descendants"
        except asyncio.CancelledError:
            await asyncio.shield(
                self._terminate_validation_process(
                    process,
                    wait_task,
                    pid=process.pid,
                    pgid=pgid,
                    start_identity=start_identity,
                    boot_id=boot_id,
                    grace_seconds=min(float(spec.cancel_grace_seconds), 5.0),
                )
            )
            await asyncio.shield(
                asyncio.gather(stdout_task, stderr_task, return_exceptions=True)
            )
            raise
        finally:
            exceeded_task.cancel()
            await asyncio.gather(exceeded_task, return_exceptions=True)

        stdout_hash, stdout_size = await stdout_task
        stderr_hash, stderr_size = await stderr_task
        if stdout_size > _MAX_VALIDATION_STDOUT_BYTES:
            error = error or "validation stdout exceeded its byte cap"
        if stderr_size > _MAX_VALIDATION_STDERR_BYTES:
            error = error or "validation stderr exceeded its byte cap"
        return ValidationReceipt(
            argv=exact_argv,
            exit_code=process.returncode,
            stdout_sha256=stdout_hash,
            stdout_size=stdout_size,
            stderr_sha256=stderr_hash,
            stderr_size=stderr_size,
            timed_out=timed_out,
            error=error,
        )

    async def start(self, spec: LaunchSpec) -> ProcessRef:
        workspace, run_dir, home, tmp, baseline, _schema = self._validate_spec(spec)
        _assert_binary_unchanged(self.binary)
        codex_home = _validate_codex_home(Path(spec.codex_home))
        canary_verdict = validate_secret_canary_verdict(
            spec.secret_canary_verdict,
            require_passed=bool(spec.require_secret_canary),
        )
        schema_path = Path(spec.result_schema_path).resolve(strict=True)
        stdout_path = run_dir / "logs" / "stdout.jsonl"
        stderr_path = run_dir / "logs" / "stderr.log"
        result_path = run_dir / "output" / "result.json"
        stdout_fd = _create_private_file(stdout_path)
        try:
            stderr_fd = _create_private_file(stderr_path)
        except Exception:
            os.close(stdout_fd)
            raise
        try:
            result_fd = _create_private_file(result_path)
            os.close(result_fd)
            argv = self._argv(spec, workspace, schema_path, result_path, home, tmp)
            environment = self._environment(spec, home, tmp, codex_home)
            process = await asyncio.create_subprocess_exec(
                *argv,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(workspace),
                env=environment,
                start_new_session=True,
                limit=128 * 1024,
            )
        except Exception:
            os.close(stdout_fd)
            os.close(stderr_fd)
            raise
        if process.stdin is None or process.stdout is None or process.stderr is None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            await process.wait()
            os.close(stdout_fd)
            os.close(stderr_fd)
            raise CodexWorkerError("Codex process pipes were not created")
        try:
            observed_identity = self.inspector.inspect(process.pid)
            start_identity = observed_identity.start_identity
            pgid = observed_identity.pgid
            boot_id = self.inspector.boot_session_id()
            if pgid != process.pid:
                raise ProcessIdentityError("new Codex process did not become its own process group")
            if observed_identity.session_id != process.pid:
                raise ProcessIdentityError("new Codex process did not become its own session")
            if (
                spec.expected_worker_uid is not None
                and observed_identity.effective_uid != int(spec.expected_worker_uid)
            ):
                raise ProcessIdentityError("Codex process effective UID does not match worker")
            if (
                spec.expected_worker_gid is not None
                and observed_identity.effective_gid != int(spec.expected_worker_gid)
            ):
                raise ProcessIdentityError("Codex process effective GID does not match worker")
        except Exception:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            await process.wait()
            os.close(stdout_fd)
            os.close(stderr_fd)
            raise
        ref = ProcessRef(
            run_id=spec.run_id,
            pid=process.pid,
            pgid=pgid,
            process_start_identity=start_identity,
            boot_session_id=boot_id,
            launch_nonce=uuid4().hex,
            provider_session_id=None,
            stdout_path=str(stdout_path),
            stderr_path=str(stderr_path),
            result_path=str(result_path),
            started_at=_utc_now(),
            binary=self.binary,
            base_sha=baseline.head,
            session_id=observed_identity.session_id,
            effective_uid=observed_identity.effective_uid,
            effective_gid=observed_identity.effective_gid,
            real_uid=observed_identity.real_uid,
            real_gid=observed_identity.real_gid,
        )
        try:
            observed_user = pwd.getpwuid(observed_identity.effective_uid).pw_name
        except KeyError:
            observed_user = None
        permission_profile = {
            "permission_overrides": self._permission_overrides(spec, workspace),
            "isolation_manifest_sha256": spec.isolation_manifest_sha256,
            "network_enabled": False,
            "disabled_features": list(_DISABLED_FEATURES),
            "shell_environment_policy": "include_only",
        }
        launch_attestation = LaunchAttestation(
            schema_version=LAUNCH_ATTESTATION_SCHEMA_VERSION,
            created_at=_utc_now(),
            executable_path=self.binary.real_path,
            binary=self.binary,
            rendered_argv=_redact_argv(argv),
            environment_keys=tuple(sorted(environment)),
            permission_profile_sha256=_canonical_sha256(permission_profile),
            prompt_sha256=hashlib.sha256(spec.prompt.encode("utf-8")).hexdigest(),
            expected_base_sha=spec.expected_base_sha,
            observed_base_sha=baseline.head,
            workspace_identity={**_path_identity(workspace), "git_head": baseline.head},
            worker_identity={
                "requested_user": spec.worker_user,
                "observed_user": observed_user,
                "expected_uid": spec.expected_worker_uid,
                "expected_gid": spec.expected_worker_gid,
                "effective_uid": observed_identity.effective_uid,
                "effective_gid": observed_identity.effective_gid,
                "real_uid": observed_identity.real_uid,
                "real_gid": observed_identity.real_gid,
            },
            provider_home_identity=_path_identity(codex_home),
            secret_canary_verdict=canary_verdict,
            launch_nonce=ref.launch_nonce,
            process_identity={
                "pid": ref.pid,
                "pgid": ref.pgid,
                "session_id": ref.session_id,
                "start_identity": ref.process_start_identity,
                "boot_id": ref.boot_session_id,
                "effective_uid": ref.effective_uid,
                "effective_gid": ref.effective_gid,
                "real_uid": ref.real_uid,
                "real_gid": ref.real_gid,
            },
        )
        parser = _JSONLState()
        state = _RunState(
            spec=spec,
            ref=ref,
            process=process,
            parser=parser,
            baseline=baseline,
            stdout_fd=stdout_fd,
            stderr_fd=stderr_fd,
            violation=asyncio.Event(),
            process_wait_task=asyncio.create_task(process.wait()),
            launch_attestation=launch_attestation,
            status=WorkerRunStatus.RUNNING,
        )
        self._runs[spec.run_id] = state
        state.stdout_task = asyncio.create_task(_pump_stream(
            process.stdout,
            fd=stdout_fd,
            name="stdout",
            maximum=_MAX_STDOUT_BYTES,
            line_maximum=_MAX_JSONL_LINE_BYTES,
            parser=parser,
            state=state,
        ))
        state.stderr_task = asyncio.create_task(_pump_stream(
            process.stderr,
            fd=stderr_fd,
            name="stderr",
            maximum=_MAX_STDERR_BYTES,
            line_maximum=None,
            parser=None,
            state=state,
        ))
        try:
            process.stdin.write(spec.prompt.encode("utf-8"))
            await process.stdin.drain()
        except (BrokenPipeError, ConnectionResetError) as exc:
            state.stream_errors.append(f"stdin delivery failed: {type(exc).__name__}")
            state.violation.set()
        finally:
            process.stdin.close()
        state.monitor_task = asyncio.create_task(self._monitor(state))
        return ref

    def launch_attestation(self, ref: ProcessRef) -> LaunchAttestation:
        """Return the immutable complete launch receipt for a known invocation."""

        return self._state_for(ref).launch_attestation

    def _state_for(self, ref: ProcessRef) -> _RunState:
        state = self._runs.get(ref.run_id)
        if state is None or state.ref != ref:
            raise ProcessIdentityError("unknown or altered ProcessRef")
        return state

    def _identity_matches(self, ref: ProcessRef) -> bool:
        if self.inspector.boot_session_id() != ref.boot_session_id:
            return False
        try:
            identity, pgid = self.inspector.identity(ref.pid)
        except ProcessIdentityError:
            return False
        return identity == ref.process_start_identity and pgid == ref.pgid

    async def _kill_residual_process_group(self, state: _RunState) -> bool:
        """Kill descendants that outlive the already-reaped group leader."""

        if state.group_proven_absent:
            # Termination already proved this exact group absent.  Every member
            # including the leader had exited, so there is no descendant to
            # reap; probing again could only observe a PGID the host has since
            # recycled to a foreign group, and an absent leader must never
            # authorise signalling a reused group.
            return False
        if not _process_group_exists(state.ref.pgid):
            return False
        try:
            os.killpg(state.ref.pgid, signal.SIGKILL)
        except ProcessLookupError:
            return False
        state.escalated = True
        if not await _wait_for_process_group_exit(state.ref.pgid):
            raise ProcessIdentityError(
                f"process group {state.ref.pgid} survived SIGKILL"
            )
        return True

    async def _terminate(self, state: _RunState) -> tuple[bool, bool, bool]:
        async with state.termination_lock:
            leader_already_exited = state.process_wait_task.done()
            sent = False
            escalated = False
            if not leader_already_exited:
                if not self._identity_matches(state.ref):
                    raise ProcessIdentityError(
                        "refusing to signal a process whose identity changed"
                    )
                try:
                    os.killpg(state.ref.pgid, signal.SIGTERM)
                    sent = True
                except ProcessLookupError:
                    pass
                try:
                    await asyncio.wait_for(
                        asyncio.shield(state.process_wait_task),
                        timeout=float(state.spec.cancel_grace_seconds),
                    )
                except asyncio.TimeoutError:
                    # A descendant can keep the transport pipes open after the
                    # group leader has obeyed SIGTERM.  In that case the
                    # asyncio wait task is still pending even though proc_pidinfo
                    # can no longer resolve the leader.  A nonempty group keeps
                    # its PGID allocated, so killing that residual group is safe;
                    # a *live* leader must still match the persisted identity.
                    if self.inspector.boot_session_id() != state.ref.boot_session_id:
                        raise ProcessIdentityError(
                            "process boot identity changed before SIGKILL escalation"
                        )
                    group_vanished = False
                    try:
                        identity, observed_pgid = self.inspector.identity(state.ref.pid)
                    except ProcessIdentityError:
                        # The leader can no longer be resolved.  A *proven* absent
                        # group means the verified original group leader and every
                        # remaining member have already exited, so the SIGTERM above
                        # reached the terminated postcondition and there is nothing
                        # left to escalate against; signalling that PGID now could
                        # only ever reach a reused group.  This is proof rather than
                        # inference: _process_group_exists reports absence only for
                        # ProcessLookupError and raises when the observation itself
                        # is unavailable, so an unreadable group still fails closed.
                        group_vanished = not _process_group_exists(state.ref.pgid)
                        state.group_proven_absent = group_vanished
                    else:
                        if (
                            identity != state.ref.process_start_identity
                            or observed_pgid != state.ref.pgid
                        ):
                            raise ProcessIdentityError(
                                "process identity changed before SIGKILL escalation"
                            )
                    if not group_vanished:
                        try:
                            os.killpg(state.ref.pgid, signal.SIGKILL)
                            sent = True
                        except ProcessLookupError:
                            pass
                        escalated = True
                        state.escalated = True
                    await state.process_wait_task

            await state.process_wait_task
            residual_killed = await self._kill_residual_process_group(state)
            if residual_killed:
                sent = True
                escalated = True
            return sent, escalated, leader_already_exited and not residual_killed

    async def _monitor(self, state: _RunState) -> None:
        violation_task = asyncio.create_task(state.violation.wait())
        try:
            done, _pending = await asyncio.wait(
                {state.process_wait_task, violation_task},
                timeout=float(state.spec.timeout_seconds),
                return_when=asyncio.FIRST_COMPLETED,
            )
            if not done:
                state.timed_out = True
                try:
                    await self._terminate(state)
                except ProcessIdentityError as exc:
                    state.stream_errors.append(str(exc))
            elif violation_task in done and state.violation.is_set() and not state.process_wait_task.done():
                try:
                    await self._terminate(state)
                except ProcessIdentityError as exc:
                    state.stream_errors.append(str(exc))
            await state.process_wait_task
            async with state.termination_lock:
                residual_killed = await self._kill_residual_process_group(state)
            if residual_killed:
                state.stream_errors.append(
                    "provider process left live descendants after its leader exited"
                )
                state.violation.set()
        finally:
            violation_task.cancel()
            await asyncio.gather(violation_task, return_exceptions=True)
            tasks = [task for task in (state.stdout_task, state.stderr_task) if task is not None]
            await asyncio.gather(*tasks, return_exceptions=True)
            state.finished_at = _utc_now()

    async def status(self, ref: ProcessRef) -> WorkerRunStatus:
        state = self._state_for(ref)
        if state.receipt is not None:
            return state.receipt.result.status
        if state.monitor_task is not None and state.monitor_task.done():
            # Collection performs the terminal validation; until then a clean
            # process exit is not allowed to masquerade as success.
            return WorkerRunStatus.CANCELLING if state.cancel_reason else WorkerRunStatus.RUNNING
        return state.status

    async def cancel(self, ref: ProcessRef, reason: str) -> CancelReceipt:
        state = self._state_for(ref)
        reason = str(reason).strip()
        if not reason:
            raise LaunchValidationError("cancellation reason is required")
        state.cancel_reason = reason[:1000]
        state.status = WorkerRunStatus.CANCELLING
        sent, escalated, already_exited = await self._terminate(state)
        if state.monitor_task is not None:
            await state.monitor_task
        return CancelReceipt(
            run_id=ref.run_id,
            reason=state.cancel_reason,
            signal_sent=sent,
            escalated_to_sigkill=escalated,
            already_exited=already_exited,
            finished_at=state.finished_at or _utc_now(),
        )

    def _validate_process_ref_after_exit(self, state: _RunState) -> None:
        # Once reaped, proc_pidinfo should no longer resolve the exact identity.
        # A matching live identity indicates a leaked/reused process and cannot be
        # accepted as terminal evidence.
        if self._identity_matches(state.ref):
            raise ProcessIdentityError("process identity is still live after reported exit")

    def _load_result(self, state: _RunState, schema: Any) -> tuple[dict[str, Any], str]:
        result_path = Path(state.ref.result_path)
        info = result_path.lstat()
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ResultValidationError("result.json is not a single-link regular file")
        if stat.S_IMODE(info.st_mode) & 0o077:
            raise ResultValidationError("result.json is accessible to group/other")
        if info.st_size <= 0 or info.st_size > _MAX_RESULT_BYTES:
            raise ResultValidationError("result.json is empty or exceeds one MiB")
        raw = result_path.read_bytes()
        try:
            output = json.loads(raw.decode("utf-8", errors="strict"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ResultValidationError(f"result.json is not strict UTF-8 JSON: {exc}") from exc
        if not isinstance(output, dict):
            raise ResultValidationError("result.json root must be an object")
        validate_json_schema(output, schema)
        final_text = state.parser.final_agent_message
        try:
            streamed = json.loads(final_text or "")
        except json.JSONDecodeError as exc:
            raise ResultValidationError("final agent_message is not JSON") from exc
        if streamed != output:
            raise ResultValidationError("result.json differs from final agent_message")
        for field, expected in (
            ("run_id", state.spec.run_id),
            ("job_id", state.spec.job_id),
            ("worker_id", state.spec.worker_id),
        ):
            if field in output and output[field] != expected:
                raise ResultValidationError(f"result identity field {field!r} does not match launch")
        return output, hashlib.sha256(raw).hexdigest()

    def _artifact_receipts(self, state: _RunState, output: Mapping[str, Any]) -> tuple[ArtifactReceipt, ...]:
        raw_artifacts = output.get("artifacts", [])
        if raw_artifacts is None:
            raw_artifacts = []
        if not isinstance(raw_artifacts, list):
            raise ResultValidationError("result artifacts must be a list")
        allowed = tuple(
            _normalise_relative_path(value) for value in state.spec.allowed_artifact_paths
        )
        if len(raw_artifacts) > state.spec.max_artifacts:
            raise ResultValidationError("result declares too many artifacts")
        requested: list[str] = []
        for item in raw_artifacts:
            value = item.get("path") if isinstance(item, dict) else item
            if not isinstance(value, str):
                raise ResultValidationError("artifact entry must be a path string or object")
            try:
                normalised = _normalise_declared_artifact_path(value)
            except LaunchValidationError as exc:
                raise ResultValidationError(str(exc)) from exc
            if _is_protected_workspace_path(normalised):
                raise ResultValidationError(
                    f"artifact targets protected workspace metadata: {normalised}"
                )
            if not _path_matches_patterns(normalised, allowed):
                raise ResultValidationError(f"artifact path was not authorized: {normalised}")
            requested.append(normalised)
        if len(requested) != len(set(requested)):
            raise ResultValidationError("result declares duplicate artifacts")

        root = Path(state.spec.workspace_path).resolve(strict=True)
        root_fd = os.open(root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        receipts: list[ArtifactReceipt] = []
        total = 0
        try:
            for relative in requested:
                parts = PurePosixPath(relative).parts
                directory_fd = os.dup(root_fd)
                try:
                    for component in parts[:-1]:
                        next_fd = os.open(
                            component,
                            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
                            dir_fd=directory_fd,
                        )
                        os.close(directory_fd)
                        directory_fd = next_fd
                    file_fd = os.open(
                        parts[-1],
                        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
                        dir_fd=directory_fd,
                    )
                    try:
                        file_info = os.fstat(file_fd)
                        if not stat.S_ISREG(file_info.st_mode) or file_info.st_nlink != 1:
                            raise ResultValidationError(
                                f"artifact is not a single-link regular file: {relative}"
                            )
                        if file_info.st_size > state.spec.max_artifact_bytes:
                            raise ResultValidationError(f"artifact exceeds size cap: {relative}")
                        total += file_info.st_size
                        if total > state.spec.max_artifact_total_bytes:
                            raise ResultValidationError("artifact manifest exceeds total byte cap")
                        digest = hashlib.sha256()
                        read_total = 0
                        while True:
                            chunk = os.read(file_fd, 1024 * 1024)
                            if not chunk:
                                break
                            read_total += len(chunk)
                            digest.update(chunk)
                        if read_total != file_info.st_size:
                            raise ResultValidationError(f"artifact changed while hashing: {relative}")
                        after = os.fstat(file_fd)
                        if (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) != (
                            file_info.st_dev, file_info.st_ino, file_info.st_size, file_info.st_mtime_ns
                        ):
                            raise ResultValidationError(f"artifact changed while hashing: {relative}")
                        receipts.append(ArtifactReceipt(
                            path=relative,
                            sha256=digest.hexdigest(),
                            size=file_info.st_size,
                        ))
                    finally:
                        os.close(file_fd)
                except OSError as exc:
                    raise ResultValidationError(f"unsafe or missing artifact {relative}: {exc}") from exc
                finally:
                    os.close(directory_fd)
        finally:
            os.close(root_fd)
        return tuple(receipts)

    async def collect_result(self, ref: ProcessRef) -> CollectionReceipt:
        state = self._state_for(ref)
        if state.receipt is not None:
            return state.receipt
        if state.monitor_task is None:
            raise CodexWorkerError("run monitor was not started")
        await state.monitor_task
        finished_at = state.finished_at or _utc_now()
        exit_code = state.process.returncode
        status_value = WorkerRunStatus.FAILED
        output: dict[str, Any] | None = None
        artifacts: tuple[ArtifactReceipt, ...] = ()
        usage: Mapping[str, Any] = {}
        result_hash: str | None = None
        error: str | None = None
        git_after: _GitSnapshot | None = None
        try:
            self._validate_process_ref_after_exit(state)
            if state.cancel_reason:
                status_value = WorkerRunStatus.CANCELLED
                error = f"cancelled: {state.cancel_reason}"
            elif state.timed_out:
                status_value = WorkerRunStatus.TIMED_OUT
                error = f"timed out after {state.spec.timeout_seconds:g}s"
            elif state.stream_errors:
                status_value = WorkerRunStatus.INVALID_RESULT
                error = "; ".join(state.stream_errors)[:3000]
            elif exit_code != 0:
                status_value = WorkerRunStatus.FAILED
                error = f"Codex exited with status {exit_code}"
            else:
                state.parser.validate()
                schema_raw = _read_limited(Path(state.spec.result_schema_path), _MAX_SCHEMA_BYTES)
                schema = json.loads(schema_raw.decode("utf-8", errors="strict"))
                output, result_hash = self._load_result(state, schema)
                artifacts = self._artifact_receipts(state, output)
                usage = dict(state.parser.usage)
                git_after = _git_snapshot(
                    Path(state.spec.workspace_path).resolve(strict=True), require_clean=False
                )
                if git_after.head != state.baseline.head:
                    raise ResultValidationError("worker changed Git HEAD")
                changed_paths = _git_changed_paths(
                    Path(state.spec.workspace_path).resolve(strict=True)
                )
                protected_changes = [
                    path for path in changed_paths
                    if _is_protected_workspace_path(path)
                ]
                if protected_changes:
                    raise ResultValidationError(
                        "worker changed protected workspace path(s): "
                        + ", ".join(protected_changes[:20])
                    )
                allowed_patterns = tuple(
                    _normalise_relative_path(value)
                    for value in state.spec.allowed_artifact_paths
                )
                unauthorized_changes = [
                    path for path in changed_paths
                    if not _path_matches_patterns(path, allowed_patterns)
                ]
                if unauthorized_changes:
                    raise ResultValidationError(
                        "worker changed unauthorized path(s): "
                        + ", ".join(unauthorized_changes[:20])
                    )
                changed_set = set(changed_paths)
                artifact_set = {artifact.path for artifact in artifacts}
                if changed_set != artifact_set:
                    missing = sorted(changed_set - artifact_set)
                    unchanged = sorted(artifact_set - changed_set)
                    details: list[str] = []
                    if missing:
                        details.append("unhashed changed paths: " + ", ".join(missing[:20]))
                    if unchanged:
                        details.append(
                            "declared artifacts without Git changes: "
                            + ", ".join(unchanged[:20])
                        )
                    raise ResultValidationError(
                        "Git changes and safely hashed artifacts differ: "
                        + "; ".join(details)
                    )
                if "WRITE_BRANCH" not in _authority_set(state.spec) and (
                    git_after.status != state.baseline.status
                ):
                    raise ResultValidationError("read-only worker changed the workspace")
                status_value = WorkerRunStatus.SUCCEEDED
        except (CodexWorkerError, OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            if status_value not in {WorkerRunStatus.CANCELLED, WorkerRunStatus.TIMED_OUT}:
                status_value = WorkerRunStatus.INVALID_RESULT
                error = f"{type(exc).__name__}: {exc}"[:3000]

        state.status = status_value
        stdout_path = Path(ref.stdout_path)
        stderr_path = Path(ref.stderr_path)
        stdout_hash = _sha256_path(stdout_path, max_bytes=_MAX_STDOUT_BYTES)
        stderr_hash = _sha256_path(stderr_path, max_bytes=_MAX_STDERR_BYTES)
        git_manifest = {
            "base_sha": state.baseline.head,
            "head_sha": git_after.head if git_after else None,
            "status_sha256": (
                hashlib.sha256(git_after.status).hexdigest() if git_after is not None else None
            ),
            "changed_paths": (
                list(_git_changed_paths(Path(state.spec.workspace_path).resolve(strict=True)))
                if git_after is not None else []
            ),
        }
        worker_result = WorkerResult(
            job_id=state.spec.job_id,
            run_id=state.spec.run_id,
            worker_id=state.spec.worker_id,
            status=status_value,
            structured_output=output,
            artifact_manifest=artifacts,
            git_manifest=git_manifest,
            usage=usage,
            provider_session_id=state.parser.provider_session_id,
            exit_code=exit_code,
            started_at=ref.started_at,
            finished_at=finished_at,
            error=error,
        )
        receipt = CollectionReceipt(
            process_ref=dataclasses.replace(
                ref, provider_session_id=state.parser.provider_session_id
            ),
            result=worker_result,
            stdout_sha256=stdout_hash,
            stderr_sha256=stderr_hash,
            result_sha256=result_hash,
        )
        state.receipt = receipt
        return receipt


__all__ = [
    "ArtifactReceipt",
    "BinaryAttestation",
    "BinaryAttestationError",
    "CODEX_ATTESTATION_RECEIPT_SCHEMA_VERSION",
    "CancelReceipt",
    "CodexAttestationReceiptError",
    "CodexWorkerAdapter",
    "CodexWorkerError",
    "CollectionReceipt",
    "GitPreflightFailed",
    "GitPreflightTimeout",
    "LAUNCH_ATTESTATION_SCHEMA_VERSION",
    "LaunchAttestation",
    "LaunchSpec",
    "LaunchValidationError",
    "LaunchValidationStageError",
    "ProcessIdentityError",
    "ProcessIdentity",
    "ProcessInspector",
    "ProcessRef",
    "ResultValidationError",
    "SECRET_CANARY_SCHEMA_VERSION",
    "ValidationReceipt",
    "WorkerResult",
    "WorkerRunStatus",
    "attest_codex_binary",
    "load_codex_attestation_receipt",
    "validate_secret_canary_verdict",
    "validate_json_schema",
]
