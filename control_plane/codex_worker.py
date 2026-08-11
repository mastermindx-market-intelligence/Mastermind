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
from typing import Any, Mapping, Sequence
from uuid import uuid4


_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_OPENAI_TEAM_IDENTIFIER = "2DC432GLL2"
_SAFE_PATH = "/usr/bin:/bin:/usr/sbin:/sbin"
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


class CodexWorkerError(RuntimeError):
    """Base class for fail-closed adapter errors."""


class LaunchValidationError(CodexWorkerError):
    """The launch specification or workspace is unsafe."""


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
    forbidden_paths: tuple[Path, ...] = ()
    max_artifacts: int = _MAX_ARTIFACTS
    max_artifact_bytes: int = _MAX_ARTIFACT_BYTES
    max_artifact_total_bytes: int = _MAX_ARTIFACT_TOTAL_BYTES


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
    stdout_task: asyncio.Task[None] | None = None
    stderr_task: asyncio.Task[None] | None = None
    monitor_task: asyncio.Task[None] | None = None
    termination_lock: asyncio.Lock = dataclasses.field(default_factory=asyncio.Lock)
    status: WorkerRunStatus = WorkerRunStatus.STARTING
    stream_errors: list[str] = dataclasses.field(default_factory=list)
    cancel_reason: str | None = None
    timed_out: bool = False
    escalated: bool = False
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

    version_run = _run_checked([str(path), "--version"], timeout=10.0)
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
        verify = _run_checked(["/usr/bin/codesign", "--verify", "--strict", str(path)])
        if verify.returncode != 0:
            raise BinaryAttestationError(f"Codex code signature invalid: {verify.stderr[-500:]}")
        details = _run_checked(["/usr/bin/codesign", "-dv", "--verbose=4", str(path)])
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

    def identity(self, pid: int) -> tuple[str, int]:
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
            return identity, int(info.pbi_pgid)

        try:
            pgid = os.getpgid(pid)
        except ProcessLookupError as exc:
            raise ProcessIdentityError(f"process {pid} is absent") from exc
        result = _run_checked(["/bin/ps", "-o", "lstart=", "-p", str(pid)])
        if result.returncode != 0 or not result.stdout.strip():
            raise ProcessIdentityError(f"cannot resolve process start time for pid {pid}")
        return result.stdout.strip(), pgid


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


def _git_command(workspace: Path, *args: str) -> bytes:
    argv = [
        "/usr/bin/git",
        "--no-pager",
        "-c", "credential.helper=",
        "-c", "core.hooksPath=/dev/null",
        "-c", "core.fsmonitor=false",
        "-C", str(workspace),
        *args,
    ]
    result = subprocess.run(
        argv,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={
            "PATH": _SAFE_PATH,
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "HOME": "/var/empty",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_TERMINAL_PROMPT": "0",
            "GCM_INTERACTIVE": "never",
        },
        timeout=15,
        check=False,
    )
    if len(result.stdout) > 4 * 1024 * 1024 or len(result.stderr) > 1024 * 1024:
        raise LaunchValidationError("Git preflight output exceeded its limit")
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace")[-1000:]
        raise LaunchValidationError(f"Git preflight failed: {detail}")
    return result.stdout


def _validate_git_config(git_dir: Path) -> None:
    config_path = git_dir / "config"
    text = _read_limited(config_path, 256 * 1024).decode("utf-8", errors="strict")
    forbidden = (
        r"^\s*\[\s*remote\b",
        r"^\s*\[\s*include(?:if)?\b",
        r"^\s*\[\s*credential\b",
        r"^\s*(?:url|pushurl|extraheader|sshcommand|helper)\s*=",
    )
    for pattern in forbidden:
        if re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE):
            raise LaunchValidationError("workspace Git config contains remote/credential indirection")
    for name in ("credentials", "credential", "config.worktree"):
        if (git_dir / name).exists():
            raise LaunchValidationError(f"workspace Git metadata contains forbidden {name}")


def _git_snapshot(workspace: Path, *, require_clean: bool) -> _GitSnapshot:
    git_dir = workspace / ".git"
    try:
        git_info = git_dir.lstat()
    except OSError as exc:
        raise LaunchValidationError("workspace must contain its own .git directory") from exc
    if stat.S_ISLNK(git_info.st_mode) or not stat.S_ISDIR(git_info.st_mode):
        raise LaunchValidationError("linked worktrees and .git files are not accepted")
    _validate_git_config(git_dir)
    if _git_command(workspace, "remote").strip():
        raise LaunchValidationError("workspace clone must have no Git remotes")
    head = _git_command(workspace, "rev-parse", "--verify", "HEAD").decode().strip()
    if not re.fullmatch(r"[0-9a-fA-F]{40,64}", head):
        raise LaunchValidationError("workspace HEAD is not an immutable Git object id")
    status_value = _git_command(
        workspace, "status", "--porcelain=v1", "-z", "--untracked-files=all"
    )
    # `git status` intentionally respects ignore rules.  A per-job clone must
    # also be free of pre-existing ignored/untracked material, since ignored
    # runtime files are still a mutation and secret-smuggling surface.
    all_untracked = _git_command(workspace, "ls-files", "--others", "-z")
    if require_clean and (status_value or all_untracked):
        raise LaunchValidationError("workspace clone must be clean before launch")
    return _GitSnapshot(head=head.lower(), status=status_value)


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
        baseline = _git_snapshot(workspace, require_clean=True)
        if spec.expected_base_sha and baseline.head != spec.expected_base_sha.lower():
            raise LaunchValidationError("workspace HEAD does not match expected base SHA")

        run_lexical = Path(spec.run_dir)
        if not run_lexical.is_absolute():
            raise LaunchValidationError("run_dir must be absolute")
        run_dir = _ensure_private_directory(run_lexical)
        if _is_relative_to(run_dir, workspace) or _is_relative_to(workspace, run_dir):
            raise LaunchValidationError("run_dir and workspace must be disjoint")
        home = _ensure_private_directory(run_dir / "home")
        tmp = _ensure_private_directory(run_dir / "tmp")
        _ensure_private_directory(run_dir / "logs")
        _ensure_private_directory(run_dir / "output")

        codex_home = _validate_codex_home(Path(spec.codex_home))
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

    def _denied_filesystem_paths(self, spec: LaunchSpec, workspace: Path) -> list[str]:
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
            str(workspace / ".git" / "**"),
            str(workspace / ".codex" / "**"),
            str(workspace / "config.toml"),
            str(workspace / ".env"),
            str(workspace / ".env.*"),
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
        return sorted(values)

    def _permission_overrides(self, spec: LaunchSpec, workspace: Path) -> list[str]:
        write = "WRITE_BRANCH" in _authority_set(spec)
        profile_name = "mastermind_exec_write" if write else "mastermind_exec_read"
        filesystem: dict[str, str] = {
            str(workspace / "**"): "read",
        }
        if write:
            for relative in spec.allowed_artifact_paths:
                pattern = _normalise_relative_path(relative)
                filesystem[str(workspace / pattern)] = "write"
        for denied in self._denied_filesystem_paths(spec, workspace):
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
                        if not _process_group_exists(pgid):
                            raise ProcessIdentityError(
                                "validation leader disappeared with no residual group"
                            )
                    else:
                        if identity != start_identity or observed_pgid != pgid:
                            raise ProcessIdentityError(
                                "validation process identity changed before SIGKILL"
                            )
        if _process_group_exists(pgid):
            try:
                os.killpg(pgid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        await wait_task
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
        run_dir = _ensure_private_directory(run_lexical)
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
            process = await asyncio.create_subprocess_exec(
                *argv,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(workspace),
                env=self._environment(spec, home, tmp, codex_home),
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
            start_identity, pgid = self.inspector.identity(process.pid)
            boot_id = self.inspector.boot_session_id()
            if pgid != process.pid:
                raise ProcessIdentityError("new Codex process did not become its own process group")
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
                    try:
                        identity, observed_pgid = self.inspector.identity(state.ref.pid)
                    except ProcessIdentityError:
                        if not _process_group_exists(state.ref.pgid):
                            raise ProcessIdentityError(
                                "process leader disappeared with no residual group"
                            )
                    else:
                        if (
                            identity != state.ref.process_start_identity
                            or observed_pgid != state.ref.pgid
                        ):
                            raise ProcessIdentityError(
                                "process identity changed before SIGKILL escalation"
                            )
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
    "CancelReceipt",
    "CodexWorkerAdapter",
    "CodexWorkerError",
    "CollectionReceipt",
    "LaunchSpec",
    "LaunchValidationError",
    "ProcessIdentityError",
    "ProcessInspector",
    "ProcessRef",
    "ResultValidationError",
    "ValidationReceipt",
    "WorkerResult",
    "WorkerRunStatus",
    "attest_codex_binary",
    "validate_json_schema",
]
