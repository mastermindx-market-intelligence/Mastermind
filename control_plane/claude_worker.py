"""Bounded native Claude Code command compiler for the common worker harness.

This native adapter owns immutable provider-private construction, binary
attestation, closed auth observation, and one bounded foreground lifecycle.
"""
from __future__ import annotations

import asyncio
import dataclasses
import enum
import hashlib
import json
import os
import platform
import pwd
import re
import selectors
import signal
import stat
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any, Mapping, Sequence

from control_plane.codex_worker import (
    CodexWorkerAdapter,
    LaunchValidationError,
    ProcessIdentityError,
    ProcessInspector as LocalProcessInspector,
    ResultValidationError,
    _canonical_sha256,
    _create_private_file,
    _ensure_private_directory,
    _ensure_run_directory,
    _git_changed_paths,
    _git_snapshot,
    _is_protected_workspace_path,
    _is_relative_to,
    _normalise_relative_path,
    _path_identity,
    _path_matches_patterns,
    _process_group_exists,
    _read_limited,
    _utc_now,
    _wait_for_process_group_exit,
    validate_json_schema,
    validate_secret_canary_verdict,
)
from control_plane.worker_execution_contract import (
    LAUNCH_ATTESTATION_SCHEMA_VERSION,
    ArtifactReceipt,
    BinaryAttestation,
    LaunchAttestation,
    CancelReceipt,
    CollectionReceipt,
    ProcessInspector,
    ValidationReceipt,
    WorkerLaunchSpec,
    WorkerProcessRef,
    WorkerResult,
    WorkerRunStatus,
)


_SAFE_PATH = "/usr/bin:/bin:/usr/sbin:/sbin"
_VERSION_RE = re.compile(r"(?P<version>\d+\.\d+\.\d+)\s+\(Claude Code\)")
_MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_MAX_BINARY_BYTES = 1 << 29
_MAX_TURNS = 64
_MOVING_MODEL_ALIASES = frozenset({"haiku", "opus", "sonnet"})
_READ_TOOLS = ("Glob", "Grep", "Read")
_WRITE_TOOLS = ("Edit", "Write")
_TEST_TOOL = "Bash"
_SAFE_PERMISSION_PATH_SEGMENT_RE = re.compile(r"^[A-Za-z0-9*?][A-Za-z0-9._*?-]*$")
_FORBIDDEN_TOOLS = (
    "Agent",
    "NotebookEdit",
    "Skill",
    "Task",
    "WebFetch",
    "WebSearch",
    "mcp__*",
)
_MAX_PROMPT_BYTES = 1 * 1024 * 1024
_MAX_SCHEMA_BYTES = 1 * 1024 * 1024
_MAX_STDOUT_BYTES = 32 * 1024 * 1024
_MAX_STDERR_BYTES = 4 * 1024 * 1024
_MAX_RESULT_BYTES = 1 * 1024 * 1024
_MAX_AUTH_JSON_BYTES = 16 * 1024
_MAX_AUTH_STRING_BYTES = 1024
_MAX_SESSION_ID_BYTES = 1 << 9
_MAX_PROCESS_CENSUS_BYTES = 64 * 1024
_MAX_PROCESS_CENSUS_MEMBERS = 256
_DARWIN_PROCESS_RUN_STATES = frozenset("IRSTUZ")
_DARWIN_PROCESS_STATE_FLAGS = frozenset("+<>AELNSsVWX")
_LAUNCH_QUARANTINE_CLEANUP_SECONDS = 0.2
_LOCAL_TASK_SETTLEMENT_SECONDS = 0.2
_DENIED_PROVIDER_ENV_KEYS = frozenset(
    {
        "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL",
        "ANTHROPIC_API_URL", "CLAUDE_CODE_OAUTH_TOKEN", "CLAUDE_SETUP_TOKEN",
        "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN",
        "GOOGLE_APPLICATION_CREDENTIALS",
    }
)
_RAW_AUTH_ALLOWED_KEYS = frozenset(
    {
        "loggedIn", "authMethod", "apiProvider", "subscriptionType", "apiKeySource",
        "email", "organization", "accountId", "organizationId",
    }
)
_SECRET_KEY_RE = re.compile(
    r"(?i)(?:\btoken\b|\bsecret\b|\bpassword\b|\bcredential\b|\bauthorization\b|api[_-]?key)"
)
_SECRET_VALUE_RE = re.compile(
    r"(?i)(?:xox[a-z]-[A-Za-z0-9-]{10,}|github_pat_[A-Za-z0-9_]{20,}|"
    r"gh[pousr]_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9_-]{20,}|Bearer\s+[A-Za-z0-9._-]{20,})"
)
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
_SHELL_NAMES = frozenset({"bash", "csh", "dash", "fish", "ksh", "sh", "tcsh", "zsh"})


class ClaudeWorkerContractError(RuntimeError):
    """The native Claude command contract could not be safely compiled."""


class ClaudeWorkerNotImplementedError(ClaudeWorkerContractError):
    """A lifecycle operation is held until its reviewed common owner exists."""


class ClaudeAuthStatusError(ClaudeWorkerContractError):
    """Native auth status was malformed, unavailable, or unsafe."""


class ClaudeLaunchError(ClaudeWorkerContractError):
    """The common launch contract refused this native Claude run."""


class ClaudeProcessIdentityError(ClaudeWorkerContractError):
    """A process reference cannot be proven to identify the spawned process."""


class ClaudeProcessSignalError(ClaudeProcessIdentityError):
    """An owned process-group signal was refused before a safe terminal state."""


class ClaudeResultValidationError(ClaudeWorkerContractError):
    """The provider result was absent, unsafe, or outside the common schema."""


class ClaudeLaunchEnvironmentUnavailableError(ClaudeWorkerContractError):
    """Task 2 has not yet established the native worker launch environment."""


@dataclasses.dataclass(frozen=True)
class ClaudeAuthObservation:
    """Closed, non-secret readiness facts for the later auth-status probe."""

    client_version: str
    authenticated: bool | None
    ready: bool
    auth_method: str
    api_provider: str
    exit_code: int | None
    observed_at: str


@dataclasses.dataclass(frozen=True, slots=True)
class ClaudeLaunchEnvironment:
    """An immutable seam, not a caller-supplied subprocess mapping."""

    def as_subprocess_environment(self) -> dict[str, str]:
        raise ClaudeLaunchEnvironmentUnavailableError(
            "Claude worker launch environment is not realized for callers"
        )


@dataclasses.dataclass(frozen=True, slots=True)
class ClaudeInvocation:
    """One complete, closed foreground invocation policy."""

    argv: tuple[str, ...]
    environment: ClaudeLaunchEnvironment


@dataclasses.dataclass(frozen=True)
class _ClaudeConfiguration:
    """Adapter-private configuration that never enters a launch request."""

    binary: BinaryAttestation
    allowed_versions: frozenset[str]
    exact_model: str
    max_turns: int


@dataclasses.dataclass
class _RunState:
    spec: WorkerLaunchSpec
    ref: WorkerProcessRef | None
    process: asyncio.subprocess.Process
    baseline: Any
    schema: Any
    stdout_evidence: _BoundEvidence
    stderr_evidence: _BoundEvidence
    result_evidence: _BoundEvidence
    violation: asyncio.Event
    process_wait_task: asyncio.Task[int]
    deadline: float
    launch_attestation: LaunchAttestation | None = None
    stdout: bytearray = dataclasses.field(default_factory=bytearray)
    stderr: bytearray = dataclasses.field(default_factory=bytearray)
    stdout_task: asyncio.Task[None] | None = None
    stderr_task: asyncio.Task[None] | None = None
    monitor_task: asyncio.Task[None] | None = None
    termination_lock: asyncio.Lock = dataclasses.field(default_factory=asyncio.Lock)
    status: WorkerRunStatus = WorkerRunStatus.RUNNING
    stream_errors: list[str] = dataclasses.field(default_factory=list)
    cancel_reason: str | None = None
    timed_out: bool = False
    escalated: bool = False
    finished_at: str | None = None
    receipt: CollectionReceipt | None = None
    collection_task: asyncio.Task[CollectionReceipt] | None = None
    residual_reconciliation_task: asyncio.Task[bool] | None = None
    signal_sent: bool = False
    terminal_cleanup_error: str | None = None
    evidence_closed: bool = False


@dataclasses.dataclass
class _BoundEvidence:
    path: Path
    fd: int
    device: int
    inode: int
    uid: int


@dataclasses.dataclass(frozen=True)
class _ProcessGroupMember:
    pid: int
    state: str


class _LaunchCleanupOutcome(enum.Enum):
    ABSENT = "absent"
    OWNED_CLEANED = "owned_cleaned"
    AMBIGUOUS = "ambiguous"


def _binary_identity(info: os.stat_result) -> tuple[int, int, int, int, int, int, int]:
    return (
        int(info.st_dev),
        int(info.st_ino),
        int(info.st_size),
        stat.S_IMODE(info.st_mode),
        int(info.st_uid),
        int(info.st_gid),
        int(info.st_mtime_ns),
    )


def _require_safe_binary_stat(info: os.stat_result) -> None:
    if not stat.S_ISREG(info.st_mode) or not info.st_mode & 0o111:
        raise ClaudeWorkerContractError("Claude binary is not an executable regular file")
    if stat.S_IMODE(info.st_mode) & 0o022:
        raise ClaudeWorkerContractError("Claude binary must not be group/other writable")
    if not 0 < info.st_size <= _MAX_BINARY_BYTES:
        raise ClaudeWorkerContractError(
            "Claude binary size is outside the attestation ceiling"
        )


def _open_direct_binary(path: Path) -> int:
    if not hasattr(os, "O_NOFOLLOW"):
        raise ClaudeWorkerContractError(
            "Claude binary attestation requires no-follow file opening"
        )
    try:
        return os.open(
            path,
            os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0),
        )
    except OSError as exc:
        raise ClaudeWorkerContractError("Claude binary is unavailable") from exc


def _direct_binary_stat(path: Path) -> os.stat_result:
    fd = _open_direct_binary(path)
    try:
        info = os.fstat(fd)
        _require_safe_binary_stat(info)
        return info
    finally:
        os.close(fd)


def _sha256_direct_binary(path: Path) -> tuple[os.stat_result, str]:
    digest = hashlib.sha256()
    size = 0
    fd = _open_direct_binary(path)
    try:
        before = os.fstat(fd)
        _require_safe_binary_stat(before)
        while chunk := os.read(fd, 1024 * 1024):
            size += len(chunk)
            if size > _MAX_BINARY_BYTES:
                raise ClaudeWorkerContractError(
                    "Claude binary exceeds attestation ceiling"
                )
            digest.update(chunk)
        after = os.fstat(fd)
        if _binary_identity(before) != _binary_identity(after):
            raise ClaudeWorkerContractError("Claude binary changed during attestation")
        return before, digest.hexdigest()
    finally:
        os.close(fd)


def _configured_direct_binary(claude_binary: Path) -> Path:
    try:
        lexical = claude_binary.lstat()
    except OSError as exc:
        raise ClaudeWorkerContractError("Claude binary is unavailable") from exc
    if stat.S_ISLNK(lexical.st_mode):
        raise ClaudeWorkerContractError("Claude binary must not be a symlink")
    try:
        real_path = claude_binary.resolve(strict=True)
    except OSError as exc:
        raise ClaudeWorkerContractError("Claude binary is unavailable") from exc
    _direct_binary_stat(real_path)
    return real_path


def _closed_probe_environment() -> dict[str, str]:
    """Return the complete environment for attestation, never an overlay."""

    return {
        "HOME": "/var/empty",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": _SAFE_PATH,
        "TZ": "UTC",
    }


def attest_claude_code_binary(
    claude_binary: Path,
    *,
    allowed_versions: frozenset[str],
) -> BinaryAttestation:
    """Attest a configured, absolute Claude Code executable without secrets."""

    if not isinstance(claude_binary, Path) or not claude_binary.is_absolute():
        raise ClaudeWorkerContractError("Claude binary path must be absolute")
    if not isinstance(allowed_versions, frozenset) or not allowed_versions or any(
        not isinstance(version, str) or not version for version in allowed_versions
    ):
        raise ClaudeWorkerContractError("Claude binary versions must be a non-empty allowlist")
    real_path = _configured_direct_binary(claude_binary)
    pre_probe, pre_probe_sha256 = _sha256_direct_binary(real_path)
    try:
        completed = subprocess.run(
            [str(real_path), "--version"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
            env=_closed_probe_environment(),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ClaudeWorkerContractError("Claude binary version probe failed") from exc
    observed = f"{completed.stdout}\n{completed.stderr}"
    match = _VERSION_RE.search(observed)
    if completed.returncode != 0 or match is None:
        raise ClaudeWorkerContractError("Claude binary version is unsupported")
    version = match.group("version")
    if version not in allowed_versions:
        raise ClaudeWorkerContractError("Claude binary version is not allowlisted")
    info, sha256 = _sha256_direct_binary(real_path)
    if (
        _binary_identity(pre_probe) != _binary_identity(info)
        or pre_probe_sha256 != sha256
    ):
        raise ClaudeWorkerContractError("Claude binary changed during version probe")
    if _configured_direct_binary(claude_binary) != real_path:
        raise ClaudeWorkerContractError("Claude binary changed during attestation")
    return BinaryAttestation(
        path=str(claude_binary),
        real_path=str(real_path),
        version=version,
        sha256=sha256,
        # Claude identity is non-secret filesystem/version evidence.  Unlike
        # Codex, this contract does not assume an OpenAI signing identity.
        team_identifier=None,
        size=int(info.st_size),
        device=int(info.st_dev),
        inode=int(info.st_ino),
        mode=stat.S_IMODE(info.st_mode),
        uid=int(info.st_uid),
        gid=int(info.st_gid),
        mtime_ns=int(info.st_mtime_ns),
    )


def _assert_claude_binary_unchanged(attestation: BinaryAttestation) -> None:
    """Refuse a launch when the exact attested executable identity drifted."""

    configured = Path(attestation.path)
    if not configured.is_absolute():
        raise ClaudeWorkerContractError("attested Claude binary changed")
    real_path = _configured_direct_binary(configured)
    if str(real_path) != attestation.real_path:
        raise ClaudeWorkerContractError("attested Claude binary changed")
    info, sha256 = _sha256_direct_binary(real_path)
    expected = (
        attestation.device,
        attestation.inode,
        attestation.size,
        attestation.mode,
        attestation.uid,
        attestation.gid,
        attestation.mtime_ns,
    )
    if _binary_identity(info) != expected or sha256 != attestation.sha256:
        raise ClaudeWorkerContractError("attested Claude binary changed")


def _validate_exact_model(exact_model: str) -> str:
    if (
        not isinstance(exact_model, str)
        or exact_model != exact_model.strip()
        or _MODEL_RE.fullmatch(exact_model) is None
        or exact_model.lower() in _MOVING_MODEL_ALIASES
    ):
        raise ClaudeWorkerContractError("Claude model must be an exact configured model id")
    return exact_model


def _requested_capabilities(spec: WorkerLaunchSpec) -> frozenset[str]:
    if not isinstance(spec.authorities, tuple):
        raise ClaudeWorkerContractError("worker authorities must be an immutable tuple")
    raw = list(spec.authorities)
    if spec.authority is not None:
        raw.append(spec.authority)
    if not raw:
        raise ClaudeWorkerContractError(
            "Claude execution requires an explicit capability grant"
        )
    if any(not isinstance(value, str) or not value.strip() for value in raw):
        raise ClaudeWorkerContractError("worker authorities must be non-empty strings")
    requested = frozenset(value.strip().upper() for value in raw)
    mapped = frozenset({"READ", "RUN_TESTS", "WRITE_BRANCH"})
    if requested - mapped:
        raise ClaudeWorkerContractError(
            "unsupported or unmapped Claude capabilities: "
            + ", ".join(sorted(requested - mapped))
        )
    return requested


def _allowed_write_paths(spec: WorkerLaunchSpec) -> tuple[str, ...]:
    paths: list[str] = []
    for candidate in spec.allowed_artifact_paths:
        if (
            not isinstance(candidate, str)
            or not candidate
            or candidate != candidate.strip()
            or "\\" in candidate
            or "//" in candidate
            or any(ord(character) < 32 or ord(character) == 127 for character in candidate)
        ):
            raise ClaudeWorkerContractError("Claude write permission path is not safe")
        parts = candidate.split("/")
        if any(
            part in {"", ".", ".."}
            or _SAFE_PERMISSION_PATH_SEGMENT_RE.fullmatch(part) is None
            for part in parts
        ):
            raise ClaudeWorkerContractError("Claude write permission path is not safe")
        if (
            parts[0] in {".git", ".codex", ".claude"}
            or candidate == "config.toml"
            or any(part == ".env" or part.startswith(".env.") for part in parts)
        ):
            raise ClaudeWorkerContractError("Claude write permission path is not safe")
        paths.append(candidate)
    if len(paths) != len(set(paths)):
        raise ClaudeWorkerContractError("duplicate Claude write permission path")
    return tuple(sorted(paths))


def _tool_policy(
    spec: WorkerLaunchSpec,
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    requested = _requested_capabilities(spec)
    tools: list[str] = []
    preapproved: list[str] = []
    forbidden = list(_FORBIDDEN_TOOLS)

    if "READ" in requested:
        tools.extend(_READ_TOOLS)
        preapproved.extend(f"{tool}(./**)" for tool in _READ_TOOLS)
    if "WRITE_BRANCH" in requested:
        paths = _allowed_write_paths(spec)
        if not paths:
            raise ClaudeWorkerContractError("unsupported or unmapped Claude capabilities")
        tools.extend(_WRITE_TOOLS)
        for path in paths:
            scoped_tools = (f"Edit(./{path})", f"Write(./{path})")
            preapproved.extend(scoped_tools)
    if "RUN_TESTS" in requested:
        tools.append(_TEST_TOOL)
        preapproved.append("Bash(python3 -m pytest *)")

    for tool in ("Bash", "Edit", "Write"):
        if tool not in tools:
            forbidden.append(tool)
    return (
        tuple(sorted(tools)),
        tuple(sorted(preapproved)),
        tuple(sorted(forbidden)),
    )


def _provider_environment_key_is_denied(key: str) -> bool:
    upper = key.upper()
    return (
        upper in _DENIED_PROVIDER_ENV_KEYS
        or upper.startswith("ANTHROPIC_")
        or upper.startswith("CLAUDE_CODE_OAUTH_TOKEN_")
        or (
            upper.startswith("CLAUDE_CODE_")
            and any(marker in upper for marker in ("API", "AUTH", "TOKEN", "GATEWAY", "HELPER"))
        )
    )


def _closed_auth_environment(source: Mapping[str, str] | None = None) -> dict[str, str]:
    incoming = os.environ if source is None else source
    if any(not isinstance(key, str) or _provider_environment_key_is_denied(key) for key in incoming):
        raise ClaudeAuthStatusError("provider credential environment is refused")
    return {
        "HOME": "/var/empty",
        "PATH": _SAFE_PATH,
        "LANG": "C",
        "LC_ALL": "C",
        "TMPDIR": "/tmp",
        "TZ": "UTC",
    }


def _closed_launch_environment(home: Path, tmp: Path, spec: WorkerLaunchSpec) -> dict[str, str]:
    return {
        "HOME": str(home),
        "TMPDIR": str(tmp),
        "PATH": _SAFE_PATH,
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "TZ": "UTC",
        "USER": spec.worker_user,
        "LOGNAME": spec.worker_user,
        "NO_COLOR": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "GCM_INTERACTIVE": "never",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_OPTIONAL_LOCKS": "0",
    }


def _redacted_launch_argv(argv: Sequence[str]) -> tuple[str, ...]:
    """Bind exact flags while replacing prompt/schema bodies with their digests."""

    rendered: list[str] = []
    index = 0
    while index < len(argv):
        value = str(argv[index])
        if value == "--json-schema":
            if index + 1 >= len(argv):
                raise ClaudeLaunchError("compiled Claude command lost its JSON schema")
            schema = str(argv[index + 1]).encode("utf-8", "strict")
            rendered.extend(
                (value, f"<json-schema-sha256:{hashlib.sha256(schema).hexdigest()}>")
            )
            index += 2
            continue
        if index == len(argv) - 1:
            prompt = value.encode("utf-8", "strict")
            rendered.append(f"<prompt-sha256:{hashlib.sha256(prompt).hexdigest()}>")
        else:
            rendered.append(value)
        index += 1
    return tuple(rendered)


def _permission_profile(spec: WorkerLaunchSpec) -> dict[str, Any]:
    tools, preapproved, forbidden = _tool_policy(spec)
    return {
        "tools": list(tools),
        "preapproved_tools": list(preapproved),
        "forbidden_tools": list(forbidden),
        "isolation_manifest_sha256": spec.isolation_manifest_sha256,
        "network_enabled": False,
        "safe_mode": True,
        "session_persistence": False,
        "mcp_servers": [],
        "shell_environment_policy": "include_only",
    }


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _reject_json_constant(_value: str) -> None:
    raise ValueError("non-finite JSON number")


def _strict_json(raw: bytes, *, maximum: int, error_type: type[ClaudeWorkerContractError]) -> dict[str, Any]:
    if not raw or len(raw) > maximum:
        raise error_type("provider JSON exceeded its bounded contract")
    try:
        value = json.loads(
            raw.decode("utf-8", "strict"),
            object_pairs_hook=_reject_duplicate_json_keys,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, ValueError, TypeError, RecursionError):
        # JSONDecodeError retains its raw document.  Leave this except block
        # before raising so no provider bytes survive in exception chaining.
        value = None
    if value is None:
        raise error_type("provider JSON is malformed") from None
    if not isinstance(value, dict):
        raise error_type("provider JSON root is not an object")
    return value


def _contains_secret_shaped(value: Any) -> bool:
    if isinstance(value, Mapping):
        return any(
            not isinstance(key, str)
            or _SECRET_KEY_RE.search(key) is not None
            or _contains_secret_shaped(item)
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple)):
        return any(_contains_secret_shaped(item) for item in value)
    return isinstance(value, str) and _SECRET_VALUE_RE.search(value) is not None


def _raw_output_is_sensitive(raw: bytes) -> bool:
    try:
        text = raw.decode("utf-8", "strict")
    except UnicodeDecodeError:
        return True
    return _SECRET_KEY_RE.search(text) is not None or _SECRET_VALUE_RE.search(text) is not None


def _validate_discard_only(value: Any, *, depth: int = 0) -> None:
    if depth > 16:
        raise ClaudeAuthStatusError("auth discard data exceeds the bounded contract")
    if isinstance(value, str):
        if (
            len(value.encode("utf-8", "strict")) > _MAX_AUTH_STRING_BYTES
            or _CONTROL_RE.search(value)
            or _SECRET_VALUE_RE.search(value)
        ):
            raise ClaudeAuthStatusError("auth discard data is unsafe")
        return
    if value is None or isinstance(value, bool) or isinstance(value, (int, float)):
        return
    if isinstance(value, Mapping):
        if len(value) > 64:
            raise ClaudeAuthStatusError("auth discard data exceeds the bounded contract")
        for key, item in value.items():
            if (
                not isinstance(key, str)
                or len(key.encode("utf-8", "strict")) > 128
                or _SECRET_KEY_RE.search(key)
            ):
                raise ClaudeAuthStatusError("auth discard data is unsafe")
            _validate_discard_only(item, depth=depth + 1)
        return
    if isinstance(value, list):
        if len(value) > 64:
            raise ClaudeAuthStatusError("auth discard data exceeds the bounded contract")
        for item in value:
            _validate_discard_only(item, depth=depth + 1)
        return
    raise ClaudeAuthStatusError("auth discard data is unsupported")


def _bind_private_evidence(path: Path) -> _BoundEvidence:
    fd = _create_private_file(path)
    try:
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1
            or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) & 0o077
        ):
            raise ClaudeResultValidationError("created evidence file is not private")
        return _BoundEvidence(path, fd, int(info.st_dev), int(info.st_ino), int(info.st_uid))
    except Exception:
        os.close(fd)
        raise


def _verify_bound_evidence(evidence: _BoundEvidence) -> None:
    if evidence.fd < 0:
        raise ClaudeResultValidationError("evidence descriptor is closed")
    try:
        opened = os.fstat(evidence.fd)
        named = evidence.path.lstat()
    except OSError as exc:
        raise ClaudeResultValidationError("evidence path is unavailable") from exc
    for info in (opened, named):
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1
            or info.st_uid != evidence.uid
            or stat.S_IMODE(info.st_mode) & 0o077
            or int(info.st_dev) != evidence.device
            or int(info.st_ino) != evidence.inode
        ):
            raise ClaudeResultValidationError("evidence identity changed")


def _write_bound_evidence(evidence: _BoundEvidence, payload: bytes) -> str:
    _verify_bound_evidence(evidence)
    os.lseek(evidence.fd, 0, os.SEEK_SET)
    os.ftruncate(evidence.fd, 0)
    offset = 0
    while offset < len(payload):
        written = os.write(evidence.fd, payload[offset:])
        if written <= 0:
            raise OSError("short evidence write")
        offset += written
    os.fsync(evidence.fd)
    _verify_bound_evidence(evidence)
    return hashlib.sha256(payload).hexdigest()


async def _pump_claude_stream(
    reader: asyncio.StreamReader,
    *,
    name: str,
    maximum: int,
    target: bytearray,
    state: _RunState,
) -> None:
    total = 0
    accepting = True
    try:
        while chunk := await reader.read(64 * 1024):
            total += len(chunk)
            if accepting and total <= maximum:
                target.extend(chunk)
            elif accepting:
                accepting = False
                state.stream_errors.append(f"{name} exceeded byte cap")
                state.violation.set()
    except Exception:
        state.stream_errors.append(f"{name} stream failure")
        state.violation.set()


def _run_bounded_auth_status(argv: Sequence[str], *, timeout: float, env: Mapping[str, str]) -> tuple[bytes, bytes, int]:
    """Collect the metadata command without granting it an unbounded output buffer."""

    try:
        process = subprocess.Popen(
            tuple(argv),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            close_fds=True,
            start_new_session=True,
            env=dict(env),
        )
    except (OSError, ValueError) as exc:
        raise ClaudeAuthStatusError("auth observation failed") from exc
    streams = {"stdout": process.stdout, "stderr": process.stderr}
    limits = {"stdout": _MAX_AUTH_JSON_BYTES, "stderr": _MAX_STDERR_BYTES}
    captured = {"stdout": bytearray(), "stderr": bytearray()}
    deadline = time.monotonic() + timeout
    selector = selectors.DefaultSelector()
    try:
        for name, stream in streams.items():
            if stream is None:
                raise ClaudeAuthStatusError("auth observation pipes are unavailable")
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, selectors.EVENT_READ, name)
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ClaudeAuthStatusError("auth observation timed out")
            ready = selector.select(remaining)
            if not ready:
                raise ClaudeAuthStatusError("auth observation timed out")
            for key, _ in ready:
                name = str(key.data)
                chunk = os.read(key.fileobj.fileno(), min(8192, limits[name] - len(captured[name]) + 1))
                if not chunk:
                    selector.unregister(key.fileobj)
                    key.fileobj.close()
                    continue
                captured[name].extend(chunk)
                if len(captured[name]) > limits[name]:
                    raise ClaudeAuthStatusError("auth observation output exceeded its bounded contract")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ClaudeAuthStatusError("auth observation timed out")
        return bytes(captured["stdout"]), bytes(captured["stderr"]), process.wait(timeout=remaining)
    except (OSError, subprocess.SubprocessError) as exc:
        raise ClaudeAuthStatusError("auth observation failed") from exc
    finally:
        selector.close()
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()


def _process_group_member_pids(pgid: int) -> tuple[_ProcessGroupMember, ...]:
    """Observe group membership through the OS, never infer it from a PGID alone."""

    exact_group_query = platform.system() == "Darwin"
    argv = (
        ("/bin/ps", "-g", str(pgid), "-o", "pid=,pgid=,state=")
        if exact_group_query
        else ("/bin/ps", "-axo", "pid=,pgid=,state=")
    )
    try:
        process = subprocess.Popen(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=_closed_probe_environment(),
        )
    except OSError:
        raise ClaudeProcessIdentityError("cannot observe Claude process group") from None
    assert process.stdout is not None
    selector = selectors.DefaultSelector()
    captured = bytearray()
    deadline = time.monotonic() + 2
    try:
        selector.register(process.stdout, selectors.EVENT_READ)
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError
            if not selector.select(remaining):
                raise TimeoutError
            chunk = os.read(process.stdout.fileno(), min(8192, _MAX_PROCESS_CENSUS_BYTES - len(captured) + 1))
            if not chunk:
                selector.unregister(process.stdout)
                continue
            captured.extend(chunk)
            if len(captured) > _MAX_PROCESS_CENSUS_BYTES:
                raise ValueError
        return_code = process.wait(
            timeout=max(0.01, deadline - time.monotonic())
        )
        if return_code == 1 and exact_group_query and not captured:
            try:
                if not _process_group_exists(pgid):
                    return ()
            except ProcessIdentityError:
                raise ValueError from None
        if return_code != 0:
            raise ValueError
        members: list[_ProcessGroupMember] = []
        for line in captured.decode("ascii", "strict").splitlines():
            fields = line.split()
            if len(fields) != 3:
                raise ValueError
            pid, observed_group, state_token = int(fields[0]), int(fields[1]), fields[2]
            if pid > 0 and observed_group == pgid:
                if (
                    not state_token
                    or state_token[0] not in _DARWIN_PROCESS_RUN_STATES
                    or any(
                        flag not in _DARWIN_PROCESS_STATE_FLAGS
                        for flag in state_token[1:]
                    )
                ):
                    raise ValueError
                members.append(_ProcessGroupMember(pid, state_token[0]))
                if len(members) > _MAX_PROCESS_CENSUS_MEMBERS:
                    raise ValueError
    except (UnicodeDecodeError, ValueError, TimeoutError, OSError, subprocess.SubprocessError):
        raise ClaudeProcessIdentityError("cannot observe Claude process group") from None
    finally:
        selector.close()
        if process.poll() is None:
            process.kill()
            process.wait()
    return tuple(sorted(members, key=lambda member: member.pid))


class ClaudeCodeWorkerAdapter:
    """One foreground native Claude process under the common worker contract."""

    adapter_id = "claude-code"
    __slots__ = ("_configuration", "inspector", "_runs", "__weakref__")

    def __init__(
        self,
        claude_binary: Path,
        *,
        allowed_versions: frozenset[str],
        exact_model: str,
        max_turns: int,
    ) -> None:
        if isinstance(max_turns, bool) or not isinstance(max_turns, int) or not (
            1 <= max_turns <= _MAX_TURNS
        ):
            raise ClaudeWorkerContractError("Claude max_turns is outside the bounded contract")
        object.__setattr__(
            self,
            "_configuration",
            _ClaudeConfiguration(
                binary=attest_claude_code_binary(
                    claude_binary, allowed_versions=allowed_versions
                ),
                allowed_versions=allowed_versions,
                exact_model=_validate_exact_model(exact_model),
                max_turns=max_turns,
            ),
        )
        self.inspector: ProcessInspector = LocalProcessInspector()
        self._runs: dict[str, _RunState] = {}

    @property
    def binary(self) -> BinaryAttestation:
        return self._configuration.binary

    @property
    def exact_model(self) -> str:
        return self._configuration.exact_model

    @property
    def max_turns(self) -> int:
        return self._configuration.max_turns

    @property
    def allowed_versions(self) -> frozenset[str]:
        return self._configuration.allowed_versions

    def compile_launch(self, spec: WorkerLaunchSpec) -> ClaudeInvocation:
        """Compile existing grants into one closed, foreground CLI command."""

        tools, preapproved, forbidden = _tool_policy(spec)
        settings = {
            "autoMemoryEnabled": False,
            "disableAllHooks": True,
            "enableAllProjectMcpServers": False,
            "enabledMcpjsonServers": [],
            "permissions": {
                "allow": list(preapproved),
                "ask": [],
                "defaultMode": "dontAsk",
                "deny": list(forbidden),
                "disableBypassPermissionsMode": "disable",
            },
            "switchModelsOnFlag": False,
        }
        argv = (
            self.binary.real_path,
            "-p",
            "--output-format",
            "json",
            "--safe-mode",
            "--no-chrome",
            "--no-session-persistence",
            "--max-turns",
            str(self.max_turns),
            "--model",
            self.exact_model,
            "--permission-mode",
            "dontAsk",
            "--tools",
            ",".join(tools),
            "--allowedTools",
            ",".join(preapproved),
            "--disallowedTools",
            ",".join(forbidden),
            "--strict-mcp-config",
            "--mcp-config",
            '{"mcpServers":{}}',
            "--disable-slash-commands",
            "--settings",
            _canonical_json(settings),
            spec.prompt,
        )
        return ClaudeInvocation(argv=argv, environment=ClaudeLaunchEnvironment())

    def observe_auth_status(self, *, timeout_seconds: float = 15.0) -> ClaudeAuthObservation:
        """Observe only the documented native auth state, never its identity data."""

        timeout = float(timeout_seconds)
        if not 0.1 <= timeout <= 60:
            raise ClaudeAuthStatusError("auth observation timeout is outside the bounded contract")
        _assert_claude_binary_unchanged(self.binary)
        stdout, _stderr, exit_code = _run_bounded_auth_status(
            (
                self.binary.real_path,
                "--safe-mode",
                "--setting-sources",
                "",
                "auth",
                "status",
            ),
            timeout=timeout,
            env=_closed_auth_environment(),
        )
        parsed = _strict_json(
            stdout, maximum=_MAX_AUTH_JSON_BYTES, error_type=ClaudeAuthStatusError
        )
        if set(parsed) - _RAW_AUTH_ALLOWED_KEYS:
            raise ClaudeAuthStatusError("auth observation contains unsupported sensitive data")
        logged_in = parsed.get("loggedIn")
        if (
            type(logged_in) is not bool
            or exit_code not in {0, 1}
            or (exit_code == 0) is not logged_in
        ):
            raise ClaudeAuthStatusError("auth observation response is unsupported")
        for key in (
            "email", "organization", "subscriptionType", "apiKeySource",
            "accountId", "organizationId",
        ):
            if key in parsed:
                _validate_discard_only(parsed[key])
        if logged_in and (
            not isinstance(parsed.get("authMethod"), str)
            or not isinstance(parsed.get("apiProvider"), str)
            or _CONTROL_RE.search(parsed["authMethod"])
            or _CONTROL_RE.search(parsed["apiProvider"])
            or _SECRET_VALUE_RE.search(parsed["authMethod"])
            or _SECRET_VALUE_RE.search(parsed["apiProvider"])
            or len(parsed["authMethod"].encode("utf-8", "strict")) > _MAX_AUTH_STRING_BYTES
            or len(parsed["apiProvider"].encode("utf-8", "strict")) > _MAX_AUTH_STRING_BYTES
        ):
            raise ClaudeAuthStatusError("auth observation response is unsupported")
        if not logged_in:
            return ClaudeAuthObservation(
                client_version=self.binary.version,
                authenticated=False,
                ready=False,
                auth_method="unknown",
                api_provider="unknown",
                exit_code=exit_code,
                observed_at=_utc_now(),
            )
        if parsed.get("authMethod") == "claude.ai" and parsed.get("apiProvider") == "firstParty":
            method, provider, ready = "claudeai", "first_party", True
        else:
            method, provider, ready = "non_native", "non_native", False
        return ClaudeAuthObservation(
            client_version=self.binary.version,
            authenticated=True,
            ready=ready,
            auth_method=method,
            api_provider=provider,
            exit_code=exit_code,
            observed_at=_utc_now(),
        )

    _validate_isolation_identity = staticmethod(CodexWorkerAdapter._validate_isolation_identity)

    def _validate_spec(
        self, spec: WorkerLaunchSpec
    ) -> tuple[Path, Path, Path, Path, Any, Any]:
        try:
            for field in ("run_id", "job_id", "worker_id"):
                value = getattr(spec, field)
                if not isinstance(value, str) or _MODEL_RE.fullmatch(value) is None:
                    raise LaunchValidationError("invalid worker identifier")
            if spec.run_id in self._runs:
                raise LaunchValidationError("run id is already known")
            self.compile_launch(spec)
            if not isinstance(spec.prompt, str) or not spec.prompt.strip() or len(spec.prompt.encode("utf-8")) > _MAX_PROMPT_BYTES:
                raise LaunchValidationError("prompt is missing or exceeds the bounded contract")
            if spec.model != self.exact_model:
                raise LaunchValidationError("launch model does not match the exact configured Claude model")
            if not 0 < float(spec.timeout_seconds) <= 24 * 60 * 60:
                raise LaunchValidationError("timeout is outside the bounded contract")
            if not 0.1 <= float(spec.cancel_grace_seconds) <= 60:
                raise LaunchValidationError("cancel grace is outside the bounded contract")
            workspace_lexical = Path(spec.workspace_path)
            if not workspace_lexical.is_absolute():
                raise LaunchValidationError("workspace path must be absolute")
            info = workspace_lexical.lstat()
            if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
                raise LaunchValidationError("workspace must be a real directory")
            workspace = workspace_lexical.resolve(strict=True)
            baseline = _git_snapshot(workspace, require_clean=True)
            if spec.expected_base_sha and baseline.head != spec.expected_base_sha.lower():
                raise LaunchValidationError("workspace base does not match expected SHA")
            run_lexical = Path(spec.run_dir)
            if not run_lexical.is_absolute():
                raise LaunchValidationError("run directory must be absolute")
            run_dir = _ensure_run_directory(
                run_lexical,
                shared_gid=(int(spec.shared_run_gid) if spec.shared_run_gid is not None else None),
            )
            if _is_relative_to(run_dir, workspace) or _is_relative_to(workspace, run_dir):
                raise LaunchValidationError("run directory and workspace must be disjoint")
            CodexWorkerAdapter._validate_isolation_manifest(
                self, spec, workspace, run_dir, verify_filesystem=True
            )
            if (spec.expected_worker_uid is None) != (spec.expected_worker_gid is None):
                raise LaunchValidationError("worker UID/GID must be configured together")
            home = _ensure_private_directory(run_dir / "home")
            tmp = _ensure_private_directory(run_dir / "tmp")
            _ensure_private_directory(run_dir / "logs")
            _ensure_private_directory(run_dir / "output")
            schema_path = Path(spec.result_schema_path)
            if not schema_path.is_absolute():
                raise LaunchValidationError("result schema path must be absolute")
            schema_path = schema_path.resolve(strict=True)
            if not _is_relative_to(schema_path, run_dir):
                raise LaunchValidationError("result schema must be inside run directory")
            schema = _strict_json(
                _read_limited(schema_path, _MAX_SCHEMA_BYTES),
                maximum=_MAX_SCHEMA_BYTES,
                error_type=ClaudeLaunchError,
            )
            if spec.expected_worker_uid is not None and (
                os.geteuid() != int(spec.expected_worker_uid)
                or os.getegid() != int(spec.expected_worker_gid)
            ):
                raise LaunchValidationError("adapter is not running as the configured worker principal")
            return workspace, run_dir, home, tmp, baseline, schema
        except (LaunchValidationError, ResultValidationError, OSError, UnicodeError) as exc:
            raise ClaudeLaunchError("common launch validation refused") from exc

    def _launch_argv(self, spec: WorkerLaunchSpec, schema: Any) -> tuple[str, ...]:
        invocation = self.compile_launch(spec)
        schema_value = _canonical_json(schema)
        if len(schema_value.encode("utf-8")) > _MAX_SCHEMA_BYTES:
            raise ClaudeLaunchError("result schema exceeds the bounded contract")
        return (*invocation.argv[:-1], "--json-schema", schema_value, invocation.argv[-1])

    def _identity_matches(self, ref: WorkerProcessRef) -> bool:
        try:
            return self._exact_leader_identity(ref) is not None
        except ClaudeProcessIdentityError:
            return False

    def _exact_leader_identity(self, ref: WorkerProcessRef) -> object | None:
        try:
            if self.inspector.boot_session_id() != ref.boot_session_id:
                raise ClaudeProcessIdentityError("Claude process boot identity changed")
            identity = self.inspector.inspect(ref.pid)
        except ProcessIdentityError:
            return None
        except ClaudeProcessIdentityError:
            raise
        except Exception:
            raise ClaudeProcessIdentityError("Claude process identity is ambiguous") from None
        if not (
            getattr(identity, "start_identity", None) == ref.process_start_identity
            and getattr(identity, "pgid", None) == ref.pgid
            and getattr(identity, "session_id", None) == ref.session_id
            and getattr(identity, "effective_uid", None) == ref.effective_uid
            and getattr(identity, "effective_gid", None) == ref.effective_gid
            and getattr(identity, "real_uid", None) == ref.real_uid
            and getattr(identity, "real_gid", None) == ref.real_gid
        ):
            raise ClaudeProcessIdentityError("Claude process identity changed")
        return identity

    def _owned_residual_members(self, ref: WorkerProcessRef) -> tuple[int, ...]:
        if self.inspector.boot_session_id() != ref.boot_session_id:
            raise ClaudeProcessIdentityError("Claude process boot identity changed")
        members = tuple(
            member for member in _process_group_member_pids(ref.pgid)
            if member.state != "Z"
        )
        if not members:
            return ()
        for member in members:
            try:
                identity = self.inspector.inspect(member.pid)
            except ProcessIdentityError:
                raise ClaudeProcessIdentityError("Claude process group membership is ambiguous") from None
            except Exception:
                raise ClaudeProcessIdentityError("Claude process group membership is ambiguous") from None
            if not (
                getattr(identity, "pgid", None) == ref.pgid
                and getattr(identity, "session_id", None) == ref.session_id
                and getattr(identity, "effective_uid", None) == ref.effective_uid
                and getattr(identity, "effective_gid", None) == ref.effective_gid
                and getattr(identity, "real_uid", None) == ref.real_uid
                and getattr(identity, "real_gid", None) == ref.real_gid
            ):
                raise ClaudeProcessIdentityError("Claude process group membership changed")
        return tuple(member.pid for member in members)

    def _signal_owned_group(self, ref: WorkerProcessRef, signum: signal.Signals) -> bool:
        """Take a final ownership sample immediately before process-group signal."""

        leader = self._exact_leader_identity(ref)
        members = () if leader is not None else self._owned_residual_members(ref)
        if leader is None and not members:
            return False
        # The first observation only decides whether a second, adjacent
        # sample is warranted.  The second sample is the signal authority.
        leader = self._exact_leader_identity(ref)
        members = () if leader is not None else self._owned_residual_members(ref)
        if leader is None and not members:
            return False
        try:
            os.killpg(ref.pgid, signum)
        except ProcessLookupError:
            raise
        except OSError as exc:
            raise ClaudeProcessSignalError(
                f"Claude process group signal failed: {type(exc).__name__}"
            ) from exc
        return True

    async def _safe_launch_failure_cleanup(
        self, process: asyncio.subprocess.Process
    ) -> _LaunchCleanupOutcome:
        """Signal an unaccepted launch only after a two-sample ownership proof."""

        if process.returncode is not None:
            return _LaunchCleanupOutcome.ABSENT
        try:
            first_boot = self.inspector.boot_session_id()
            first = self.inspector.inspect(process.pid)
            expected = tuple(
                getattr(first, field, None)
                for field in (
                    "start_identity", "pgid", "session_id", "effective_uid",
                    "effective_gid", "real_uid", "real_gid",
                )
            )
            second = self.inspector.inspect(process.pid)
            observed = tuple(
                getattr(second, field, None)
                for field in (
                    "start_identity", "pgid", "session_id", "effective_uid",
                    "effective_gid", "real_uid", "real_gid",
                )
            )
            if (
                self.inspector.boot_session_id() != first_boot
                or observed != expected
                or expected[1] != process.pid
                or expected[2] != process.pid
            ):
                return _LaunchCleanupOutcome.AMBIGUOUS
            if process.returncode is not None:
                return _LaunchCleanupOutcome.ABSENT
            os.killpg(process.pid, signal.SIGKILL)
            return _LaunchCleanupOutcome.OWNED_CLEANED
        except ProcessLookupError:
            return _LaunchCleanupOutcome.ABSENT
        except (ProcessIdentityError, OSError, AttributeError):
            return _LaunchCleanupOutcome.AMBIGUOUS

    @staticmethod
    def _retrieve_task_exception(task: asyncio.Task[Any]) -> None:
        if not task.cancelled():
            try:
                task.exception()
            except asyncio.CancelledError:
                pass

    async def _quarantine_launch_failure(
        self, state: _RunState, outcome: _LaunchCleanupOutcome
    ) -> None:
        """Spend one absolute post-refusal budget on all cleanup operations."""

        deadline = asyncio.get_running_loop().time() + _LAUNCH_QUARANTINE_CLEANUP_SECONDS
        tasks = tuple(
            task for task in (state.stdout_task, state.stderr_task) if task is not None
        )
        try:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise asyncio.TimeoutError
            await asyncio.wait_for(
                asyncio.shield(state.process_wait_task), timeout=remaining
            )
            for task in tasks:
                if not task.done():
                    task.cancel()
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise asyncio.TimeoutError
            await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True), timeout=remaining
            )
        except asyncio.TimeoutError:
            for task in tasks:
                if not task.done():
                    task.cancel()
            raise ClaudeProcessIdentityError(
                "unaccepted Claude launch could not be safely reaped"
            ) from None
        finally:
            for task in (state.process_wait_task, *tasks):
                if not task.done():
                    task.add_done_callback(self._retrieve_task_exception)
            self._close_evidence(state)
        if outcome is _LaunchCleanupOutcome.AMBIGUOUS:
            raise ClaudeProcessIdentityError(
                "unaccepted Claude launch identity is ambiguous"
            )

    async def start(self, spec: WorkerLaunchSpec) -> WorkerProcessRef:
        workspace, run_dir, home, tmp, baseline, schema = self._validate_spec(spec)
        _assert_claude_binary_unchanged(self.binary)
        canary_verdict = validate_secret_canary_verdict(
            spec.secret_canary_verdict,
            require_passed=bool(spec.require_secret_canary),
        )
        argv = self._launch_argv(spec, schema)
        environment = _closed_launch_environment(home, tmp, spec)
        stdout_path = run_dir / "logs" / "stdout.json"
        stderr_path = run_dir / "logs" / "stderr.log"
        result_path = run_dir / "output" / "result.json"
        stdout_evidence = _bind_private_evidence(stdout_path)
        try:
            stderr_evidence = _bind_private_evidence(stderr_path)
        except Exception:
            os.close(stdout_evidence.fd)
            raise
        try:
            result_evidence = _bind_private_evidence(result_path)
            process = await asyncio.create_subprocess_exec(
                *argv,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(workspace),
                env=environment,
                start_new_session=True,
                limit=128 * 1024,
            )
            deadline = asyncio.get_running_loop().time() + float(spec.timeout_seconds)
        except Exception:
            os.close(stdout_evidence.fd)
            os.close(stderr_evidence.fd)
            try:
                os.close(result_evidence.fd)
            except UnboundLocalError:
                pass
            raise
        if process.stdout is None or process.stderr is None:
            for evidence in (stdout_evidence, stderr_evidence, result_evidence):
                os.close(evidence.fd)
            outcome = await self._safe_launch_failure_cleanup(process)
            try:
                await asyncio.wait_for(
                    asyncio.shield(process.wait()),
                    timeout=_LAUNCH_QUARANTINE_CLEANUP_SECONDS,
                )
            except asyncio.TimeoutError:
                raise ClaudeProcessIdentityError(
                    "unaccepted Claude launch could not be safely reaped"
                ) from None
            if outcome is _LaunchCleanupOutcome.AMBIGUOUS:
                raise ClaudeProcessIdentityError("unaccepted Claude launch identity is ambiguous")
            raise ClaudeLaunchError("foreground process pipes are unavailable")
        state = _RunState(
            spec=spec, ref=None, process=process, baseline=baseline, schema=schema,
            stdout_evidence=stdout_evidence, stderr_evidence=stderr_evidence,
            result_evidence=result_evidence, violation=asyncio.Event(),
            process_wait_task=asyncio.create_task(process.wait()),
            deadline=deadline,
        )
        # Draining precedes synchronous identity inspection so a fast writer
        # cannot block on the pipe while process metadata is being collected.
        state.stdout_task = asyncio.create_task(
            _pump_claude_stream(
                process.stdout, name="stdout", maximum=_MAX_STDOUT_BYTES,
                target=state.stdout, state=state,
            )
        )
        state.stderr_task = asyncio.create_task(
            _pump_claude_stream(
                process.stderr, name="stderr", maximum=_MAX_STDERR_BYTES,
                target=state.stderr, state=state,
            )
        )
        try:
            identity = self.inspector.inspect(process.pid)
            boot = self.inspector.boot_session_id()
            if getattr(identity, "pgid", None) != process.pid or getattr(identity, "session_id", None) != process.pid:
                raise ClaudeProcessIdentityError("new Claude process lacks a dedicated session")
            if spec.expected_worker_uid is not None and (
                getattr(identity, "effective_uid", None) != int(spec.expected_worker_uid)
                or getattr(identity, "effective_gid", None) != int(spec.expected_worker_gid)
                or getattr(identity, "real_uid", None) != int(spec.expected_worker_uid)
                or getattr(identity, "real_gid", None) != int(spec.expected_worker_gid)
            ):
                raise ClaudeProcessIdentityError("Claude process principal does not match worker")
        except Exception as exc:
            outcome = await self._safe_launch_failure_cleanup(process)
            try:
                await self._quarantine_launch_failure(state, outcome)
            except ClaudeProcessIdentityError:
                raise
            raise ClaudeProcessIdentityError("Claude process identity is unavailable") from exc
        try:
            ref = WorkerProcessRef(
                run_id=spec.run_id, pid=process.pid, pgid=process.pid,
                process_start_identity=str(getattr(identity, "start_identity")), boot_session_id=boot,
                launch_nonce=uuid.uuid4().hex, provider_session_id=None,
                stdout_path=str(stdout_path), stderr_path=str(stderr_path), result_path=str(result_path),
                started_at=_utc_now(), binary=self.binary, base_sha=baseline.head,
                session_id=int(getattr(identity, "session_id")),
                effective_uid=int(getattr(identity, "effective_uid")), effective_gid=int(getattr(identity, "effective_gid")),
                real_uid=int(getattr(identity, "real_uid")), real_gid=int(getattr(identity, "real_gid")),
            )
        except Exception as exc:
            outcome = await self._safe_launch_failure_cleanup(process)
            try:
                await self._quarantine_launch_failure(state, outcome)
            except ClaudeProcessIdentityError:
                raise
            raise ClaudeProcessIdentityError(
                "Claude process reference is unavailable"
            ) from exc
        try:
            try:
                observed_user = pwd.getpwuid(ref.effective_uid).pw_name
            except KeyError:
                observed_user = None
            state.launch_attestation = LaunchAttestation(
                schema_version=LAUNCH_ATTESTATION_SCHEMA_VERSION,
                created_at=_utc_now(),
                executable_path=self.binary.real_path,
                binary=self.binary,
                rendered_argv=_redacted_launch_argv(argv),
                environment_keys=tuple(sorted(environment)),
                permission_profile_sha256=_canonical_sha256(_permission_profile(spec)),
                prompt_sha256=hashlib.sha256(spec.prompt.encode("utf-8", "strict")).hexdigest(),
                expected_base_sha=spec.expected_base_sha,
                observed_base_sha=baseline.head,
                workspace_identity={**_path_identity(workspace), "git_head": baseline.head},
                worker_identity={
                    "requested_user": spec.worker_user,
                    "observed_user": observed_user,
                    "expected_uid": spec.expected_worker_uid,
                    "expected_gid": spec.expected_worker_gid,
                    "effective_uid": ref.effective_uid,
                    "effective_gid": ref.effective_gid,
                    "real_uid": ref.real_uid,
                    "real_gid": ref.real_gid,
                },
                provider_home_identity=_path_identity(home),
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
        except Exception as exc:
            outcome = await self._safe_launch_failure_cleanup(process)
            try:
                await self._quarantine_launch_failure(state, outcome)
            except ClaudeProcessIdentityError:
                raise
            raise ClaudeProcessIdentityError(
                "Claude launch attestation is unavailable"
            ) from exc
        state.ref = ref
        self._runs[spec.run_id] = state
        state.monitor_task = asyncio.create_task(self._monitor(state))
        return ref

    def launch_attestation(self, ref: WorkerProcessRef) -> LaunchAttestation:
        state = self._state(ref)
        if state.launch_attestation is None:
            raise ClaudeProcessIdentityError("Claude launch attestation is unavailable")
        return state.launch_attestation

    async def status(self, ref: WorkerProcessRef) -> WorkerRunStatus:
        state = self._state(ref)
        if state.receipt is not None:
            return state.receipt.result.status
        if state.terminal_cleanup_error is not None:
            return WorkerRunStatus.FAILED
        if state.monitor_task is not None and state.monitor_task.done():
            # Collection alone validates a terminal provider result.
            return WorkerRunStatus.CANCELLING if state.cancel_reason else WorkerRunStatus.RUNNING
        return state.status

    @staticmethod
    def _latch_terminal_cleanup_error(state: _RunState, exc: BaseException) -> None:
        if state.terminal_cleanup_error is None:
            detail = str(exc).strip() or type(exc).__name__
            state.terminal_cleanup_error = f"{type(exc).__name__}: {detail}"[:500]
        if state.terminal_cleanup_error not in state.stream_errors:
            state.stream_errors.append(state.terminal_cleanup_error)

    async def _settle_or_cancel_local_tasks(
        self, state: _RunState, *, include_monitor: bool = False
    ) -> None:
        current = asyncio.current_task()
        candidates: list[asyncio.Task[Any]] = [state.process_wait_task]
        candidates.extend(
            task for task in (state.stdout_task, state.stderr_task) if task is not None
        )
        if (
            include_monitor
            and state.monitor_task is not None
            and state.monitor_task is not current
        ):
            candidates.append(state.monitor_task)
        tasks = tuple(dict.fromkeys(task for task in candidates if task is not current))
        if not tasks:
            return
        done = {task for task in tasks if task.done()}
        pending = set(tasks) - done
        if pending:
            newly_done, pending = await asyncio.wait(
                pending, timeout=_LOCAL_TASK_SETTLEMENT_SECONDS
            )
            done.update(newly_done)
        for task in pending:
            task.cancel()
        if pending:
            newly_done, pending = await asyncio.wait(
                pending, timeout=_LOCAL_TASK_SETTLEMENT_SECONDS
            )
            done.update(newly_done)
        for task in done:
            if task.cancelled():
                continue
            try:
                task.result()
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                message = f"local task failed: {type(exc).__name__}"
                if message not in state.stream_errors:
                    state.stream_errors.append(message)
        for task in pending:
            task.add_done_callback(self._retrieve_task_exception)
        if pending and "local task settlement incomplete" not in state.stream_errors:
            state.stream_errors.append("local task settlement incomplete")

    async def collect_result(self, ref: WorkerProcessRef) -> CollectionReceipt:
        state = self._state(ref)
        if state.receipt is not None:
            return state.receipt
        if state.collection_task is None:
            state.collection_task = asyncio.create_task(self._collect_once(state, ref))
            state.collection_task.add_done_callback(self._retrieve_terminal_exception)
        return await self._await_shared_collection(state.collection_task)

    @staticmethod
    async def _await_shared_collection(
        task: asyncio.Task[CollectionReceipt],
    ) -> CollectionReceipt:
        waiter: asyncio.Future[CollectionReceipt] = (
            asyncio.get_running_loop().create_future()
        )

        def deliver(completed: asyncio.Task[CollectionReceipt]) -> None:
            if waiter.cancelled():
                try:
                    completed.exception()
                except asyncio.CancelledError:
                    pass
                return
            if completed.cancelled():
                waiter.cancel()
                return
            exception = completed.exception()
            if exception is not None:
                waiter.set_exception(exception)
            else:
                waiter.set_result(completed.result())

        task.add_done_callback(deliver)
        try:
            return await waiter
        except asyncio.CancelledError:
            if task.done() and not task.cancelled():
                return task.result()
            raise

    @staticmethod
    def _retrieve_terminal_exception(task: asyncio.Task[CollectionReceipt]) -> None:
        if not task.cancelled():
            task.exception()

    async def _collect_once(
        self, state: _RunState, ref: WorkerProcessRef
    ) -> CollectionReceipt:
        try:
            if state.monitor_task is None:
                raise ClaudeProcessIdentityError("Claude run monitor is unavailable")
            await state.monitor_task
        except BaseException:
            self._close_evidence(state)
            raise
        status, output, session, usage, result_hash = WorkerRunStatus.FAILED, None, None, {}, None
        artifacts: tuple[ArtifactReceipt, ...] = ()
        error: str | None = None
        git_after = None
        changed: tuple[str, ...] = ()
        try:
            if self._exact_leader_identity(ref) is not None:
                raise ClaudeProcessIdentityError("process identity is still live after exit")
            if state.timed_out:
                status, error = WorkerRunStatus.TIMED_OUT, "worker timed out"
            elif state.cancel_reason:
                status, error = WorkerRunStatus.CANCELLED, "worker cancelled"
            elif state.stream_errors:
                raise ClaudeResultValidationError("provider stream exceeded its bounded contract")
            elif _raw_output_is_sensitive(bytes(state.stdout)) or _raw_output_is_sensitive(bytes(state.stderr)):
                raise ClaudeResultValidationError("provider stream contains sensitive data")
            elif state.process.returncode != 0:
                status, error = WorkerRunStatus.FAILED, "provider process failed"
            else:
                output, session, usage = self._parse_provider_result(
                    bytes(state.stdout), state.schema, state.spec
                )
                artifacts = CodexWorkerAdapter._artifact_receipts(self, state, output)
                workspace = Path(state.spec.workspace_path).resolve(strict=True)
                git_after = _git_snapshot(workspace, require_clean=False)
                changed = _git_changed_paths(workspace)
                if git_after.head != state.baseline.head or any(_is_protected_workspace_path(path) for path in changed):
                    raise ClaudeResultValidationError("workspace Git integrity changed")
                allowed = tuple(_normalise_relative_path(value) for value in state.spec.allowed_artifact_paths)
                if any(not _path_matches_patterns(path, allowed) for path in changed):
                    raise ClaudeResultValidationError("workspace changed unauthorized paths")
                if set(changed) != {artifact.path for artifact in artifacts}:
                    raise ClaudeResultValidationError("Git changes do not match artifact manifest")
                _write_bound_evidence(state.stdout_evidence, bytes(state.stdout))
                _write_bound_evidence(state.stderr_evidence, bytes(state.stderr))
                result_hash = _write_bound_evidence(
                    state.result_evidence,
                    self._bounded_result_bytes(output),
                )
                status = WorkerRunStatus.SUCCEEDED
        except ClaudeProcessIdentityError:
            raise
        except (ClaudeWorkerContractError, LaunchValidationError, ProcessIdentityError, ResultValidationError, OSError, UnicodeError, ValueError):
            if status not in {WorkerRunStatus.TIMED_OUT, WorkerRunStatus.CANCELLED}:
                status, error = WorkerRunStatus.INVALID_RESULT, "provider result rejected"
        worker_result = WorkerResult(
            job_id=state.spec.job_id, run_id=state.spec.run_id, worker_id=state.spec.worker_id,
            status=status, structured_output=output if status is WorkerRunStatus.SUCCEEDED else None,
            artifact_manifest=artifacts,
            git_manifest={
                "base_sha": state.baseline.head,
                "head_sha": git_after.head if git_after is not None else None,
                "changed_paths": list(changed),
            },
            usage=usage if status is WorkerRunStatus.SUCCEEDED else {},
            provider_session_id=session if status is WorkerRunStatus.SUCCEEDED else None,
            exit_code=state.process.returncode, started_at=ref.started_at,
            finished_at=state.finished_at or _utc_now(), error=error,
        )
        try:
            receipt = CollectionReceipt(
                process_ref=dataclasses.replace(ref, provider_session_id=worker_result.provider_session_id),
                result=worker_result,
                stdout_sha256=hashlib.sha256(state.stdout).hexdigest(),
                stderr_sha256=hashlib.sha256(state.stderr).hexdigest(),
                result_sha256=result_hash if status is WorkerRunStatus.SUCCEEDED else None,
            )
            state.status, state.receipt = status, receipt
            return receipt
        finally:
            self._close_evidence(state)

    async def cancel(self, ref: WorkerProcessRef, reason: str) -> CancelReceipt:
        state = self._state(ref)
        if not isinstance(reason, str) or not reason.strip() or len(reason) > 1000:
            raise ClaudeLaunchError("cancellation reason is invalid")
        try:
            sent, escalated, already = await self._terminate(state, reason.strip())
        except ClaudeProcessIdentityError as exc:
            if isinstance(exc, ClaudeProcessSignalError) or state.signal_sent:
                self._latch_terminal_cleanup_error(state, exc)
                if state.monitor_task is not None and not state.monitor_task.done():
                    state.monitor_task.cancel()
                await self._settle_or_cancel_local_tasks(state, include_monitor=True)
                if state.finished_at is None:
                    state.finished_at = _utc_now()
            raise
        if state.monitor_task is not None:
            await asyncio.shield(state.monitor_task)
        return CancelReceipt(
            ref.run_id, reason.strip(), sent, escalated, already,
            state.finished_at or _utc_now(),
        )

    def _state(self, ref: WorkerProcessRef) -> _RunState:
        state = self._runs.get(ref.run_id)
        if state is None or state.ref != ref:
            raise ClaudeProcessIdentityError("unknown or mismatched Claude process reference")
        return state

    async def _terminate(
        self, state: _RunState, reason: str | None
    ) -> tuple[bool, bool, bool]:
        if state.terminal_cleanup_error is not None:
            raise ClaudeProcessIdentityError(state.terminal_cleanup_error)
        ref = state.ref
        if ref is None:
            raise ClaudeProcessIdentityError("Claude process identity is unavailable")
        async with state.termination_lock:
            if state.terminal_cleanup_error is not None:
                raise ClaudeProcessIdentityError(state.terminal_cleanup_error)
            try:
                leader_already_exited = state.process_wait_task.done()
                sent = escalated = False
                if not leader_already_exited:
                    leader = self._exact_leader_identity(ref)
                    if leader is None:
                        # The leader exited in the race between wait sampling and
                        # inspection. Reconcile descendants before awaiting the
                        # asyncio transport, because inherited pipes can keep that
                        # wait pending after the OS leader is already gone.
                        residual = await self._reconcile_residual_process_group(state)
                        await state.process_wait_task
                        return residual, residual, not residual
                    if reason is not None:
                        state.cancel_reason = reason
                        state.status = WorkerRunStatus.CANCELLING
                    try:
                        sent = self._signal_owned_group(ref, signal.SIGTERM)
                        state.signal_sent = state.signal_sent or sent
                    except ProcessLookupError:
                        pass
                    try:
                        await asyncio.wait_for(
                            asyncio.shield(state.process_wait_task),
                            timeout=float(state.spec.cancel_grace_seconds),
                        )
                    except asyncio.TimeoutError:
                        leader = self._exact_leader_identity(ref)
                        residual_members = (
                            () if leader is not None else self._owned_residual_members(ref)
                        )
                        # The OS may report the leader and group absent one event-loop
                        # turn before asyncio publishes the wait-task completion.
                        # Absence authorizes no further signal; the shared residual
                        # reconciliation below still proves the terminal group state.
                        if leader is not None or residual_members:
                            try:
                                escalated = self._signal_owned_group(ref, signal.SIGKILL)
                                state.signal_sent = state.signal_sent or escalated
                                sent = sent or escalated
                            except ProcessLookupError:
                                pass
                            await state.process_wait_task
                residual = await self._reconcile_residual_process_group(state)
                await state.process_wait_task
                return (
                    sent or residual,
                    escalated or residual,
                    leader_already_exited and not residual,
                )
            except ClaudeProcessIdentityError as exc:
                if isinstance(exc, ClaudeProcessSignalError) or state.signal_sent:
                    self._latch_terminal_cleanup_error(state, exc)
                raise

    async def _reconcile_residual_process_group(self, state: _RunState) -> bool:
        """Run one identity-bound residual reconciliation and share its outcome."""

        if state.residual_reconciliation_task is None:
            state.residual_reconciliation_task = asyncio.create_task(
                self._kill_residual_process_group(state)
            )
            state.residual_reconciliation_task.add_done_callback(
                self._retrieve_task_exception
            )
        return await asyncio.shield(state.residual_reconciliation_task)

    async def _kill_residual_process_group(self, state: _RunState) -> bool:
        ref = state.ref
        if ref is None:
            raise ClaudeProcessIdentityError("Claude process identity is unavailable")
        try:
            if not self._signal_owned_group(ref, signal.SIGKILL):
                census = _process_group_member_pids(ref.pgid)
                if census and all(member.state == "Z" for member in census):
                    return False
                try:
                    group_exists = _process_group_exists(ref.pgid)
                except ProcessIdentityError:
                    raise ClaudeProcessIdentityError(
                        "Claude process group identity is ambiguous"
                    ) from None
                if group_exists:
                    raise ClaudeProcessIdentityError(
                        "Claude process group exists without owned members"
                    )
                return False
        except ProcessLookupError:
            return False
        state.signal_sent = True
        state.escalated = True
        try:
            if not await _wait_for_process_group_exit(ref.pgid, timeout=0.2):
                census = _process_group_member_pids(ref.pgid)
                if census and all(member.state == "Z" for member in census):
                    return True
                raise ClaudeProcessIdentityError("Claude process group survived SIGKILL")
        except ProcessIdentityError:
            # Darwin may report EPERM for an already-reaped group coordinate.
            # A fresh member census can distinguish that empty observation
            # from a still-live/foreign group without sending another signal.
            if not _process_group_member_pids(ref.pgid):
                return True
            raise ClaudeProcessIdentityError("Claude process group identity is ambiguous") from None
        return True

    @staticmethod
    async def _wait_for_process_returncode(
        process: asyncio.subprocess.Process,
    ) -> None:
        """Observe OS leader exit without waiting for inherited pipe EOF."""

        while process.returncode is None:
            await asyncio.sleep(0.01)

    async def _monitor(self, state: _RunState) -> None:
        violation_task = asyncio.create_task(state.violation.wait())
        leader_exit_task = asyncio.create_task(
            self._wait_for_process_returncode(state.process)
        )
        failed = False
        try:
            done, _pending = await asyncio.wait(
                {leader_exit_task, violation_task},
                timeout=max(0.0, state.deadline - asyncio.get_running_loop().time()),
                return_when=asyncio.FIRST_COMPLETED,
            )
            if not done:
                state.timed_out = True
                await self._terminate(state, None)
            elif violation_task in done and state.violation.is_set():
                await self._terminate(state, None)
            async with state.termination_lock:
                residual = await self._reconcile_residual_process_group(state)
            await state.process_wait_task
            if residual:
                state.stream_errors.append("provider left a residual process group")
                state.violation.set()
        except BaseException as exc:
            failed = True
            if isinstance(exc, ClaudeProcessIdentityError):
                self._latch_terminal_cleanup_error(state, exc)
            raise
        finally:
            violation_task.cancel()
            leader_exit_task.cancel()
            await asyncio.gather(
                violation_task, leader_exit_task, return_exceptions=True
            )
            if failed:
                await self._settle_or_cancel_local_tasks(state)
            else:
                tasks = tuple(
                    task for task in (state.stdout_task, state.stderr_task) if task is not None
                )
                await asyncio.gather(*tasks, return_exceptions=True)
            state.finished_at = _utc_now()

    @staticmethod
    def _close_evidence(state: _RunState) -> None:
        if state.evidence_closed:
            return
        state.evidence_closed = True
        for evidence in (
            state.stdout_evidence,
            state.stderr_evidence,
            state.result_evidence,
        ):
            if evidence.fd >= 0:
                try:
                    os.close(evidence.fd)
                except OSError:
                    pass
                evidence.fd = -1

    @staticmethod
    def _bounded_result_bytes(output: Mapping[str, Any]) -> bytes:
        payload = _canonical_json(output).encode("utf-8") + b"\n"
        if len(payload) > _MAX_RESULT_BYTES:
            raise ClaudeResultValidationError("structured result exceeded byte cap")
        return payload

    def _parse_provider_result(
        self, raw: bytes, schema: Any, spec: WorkerLaunchSpec
    ) -> tuple[dict[str, Any], str | None, Mapping[str, Any]]:
        payload = _strict_json(raw, maximum=_MAX_STDOUT_BYTES, error_type=ClaudeResultValidationError)
        allowed = {"is_error", "model", "session_id", "usage", "structured_output"}
        if set(payload) - allowed or any(
            _SECRET_VALUE_RE.search(value) is not None
            for value in payload.values()
            if isinstance(value, str)
        ):
            raise ClaudeResultValidationError("provider result contains unsupported sensitive data")
        if payload.get("is_error") is not False:
            raise ClaudeResultValidationError("provider returned refusal or error")
        if payload.get("model") != self.exact_model:
            raise ClaudeResultValidationError("provider result model does not match configuration")
        structured = payload.get("structured_output")
        if not isinstance(structured, dict):
            raise ClaudeResultValidationError("provider result lacks structured output")
        if _contains_secret_shaped(structured):
            raise ClaudeResultValidationError("structured output contains sensitive data")
        validate_json_schema(structured, schema)
        for field in ("run_id", "job_id", "worker_id"):
            expected = getattr(spec, field)
            if field in structured and structured[field] != expected:
                raise ClaudeResultValidationError("structured result identity does not match launch")
        session = payload.get("session_id")
        if session is not None and (
            not isinstance(session, str)
            or not session
            or len(session.encode("utf-8", "strict")) > _MAX_SESSION_ID_BYTES
            or _CONTROL_RE.search(session)
            or _contains_secret_shaped(session)
        ):
            raise ClaudeResultValidationError("provider session observation is invalid")
        raw_usage = payload.get("usage", {})
        if not isinstance(raw_usage, Mapping) or set(raw_usage) - {
            "input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"
        }:
            raise ClaudeResultValidationError("provider usage observation is invalid")
        usage: dict[str, int | float] = {}
        for key, value in raw_usage.items():
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 10**15:
                raise ClaudeResultValidationError("provider usage observation is invalid")
            usage[key] = value
        return dict(structured), session, usage

    async def run_validation_argv(
        self,
        spec: WorkerLaunchSpec,
        argv: Sequence[str],
        *,
        timeout_seconds: float = 300.0,
    ) -> ValidationReceipt:
        """Refuse validation until Task 3 composes the reviewed common sandbox."""

        del spec, argv, timeout_seconds
        raise ClaudeWorkerNotImplementedError(
            "Claude validation requires common broker sandbox composition"
        )


def _canonical_json(value: object) -> str:
    import json

    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


__all__ = [
    "ClaudeAuthObservation",
    "ClaudeCodeWorkerAdapter",
    "ClaudeInvocation",
    "ClaudeLaunchEnvironment",
    "ClaudeLaunchEnvironmentUnavailableError",
    "ClaudeWorkerContractError",
    "ClaudeWorkerNotImplementedError",
    "attest_claude_code_binary",
    "_assert_claude_binary_unchanged",
]
