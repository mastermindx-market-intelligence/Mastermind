"""Bounded native Claude Code command compiler for the common worker harness.

This Task 1 adapter intentionally stops before provider process lifecycle,
authentication observation, or result parsing.  It owns only immutable
provider-private construction, binary attestation, and the closed invocation
policy that later lifecycle work will execute.
"""
from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import json
import os
import re
import selectors
import signal
import stat
import subprocess
import time
import uuid
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any, Mapping, Sequence

from control_plane.codex_worker import (
    CodexWorkerAdapter,
    LaunchValidationError,
    ProcessIdentityError,
    ProcessInspector as LocalProcessInspector,
    ResultValidationError,
    _authority_set,
    _create_private_file,
    _ensure_private_directory,
    _ensure_run_directory,
    _git_changed_paths,
    _git_snapshot,
    _is_protected_workspace_path,
    _is_relative_to,
    _normalise_relative_path,
    _path_matches_patterns,
    _read_limited,
    _sha256_path,
    _utc_now,
    validate_json_schema,
)
from control_plane.worker_execution_contract import (
    ArtifactReceipt,
    BinaryAttestation,
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
_MAX_BINARY_BYTES = 512 * 1024 * 1024
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
_MAX_VALIDATION_ARGV_BYTES = 64 * 1024
_MAX_VALIDATION_STDOUT_BYTES = 4 * 1024 * 1024
_MAX_VALIDATION_STDERR_BYTES = 1 * 1024 * 1024
_AUTH_ENV_PATH_KEYS = frozenset(
    {"HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "CLAUDE_CONFIG_DIR", "SSL_CERT_FILE", "SSL_CERT_DIR"}
)
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
    """A lifecycle operation intentionally deferred to Task 2."""


class ClaudeAuthStatusError(ClaudeWorkerContractError):
    """Native auth status was malformed, unavailable, or unsafe."""


class ClaudeLaunchError(ClaudeWorkerContractError):
    """The common launch contract refused this native Claude run."""


class ClaudeProcessIdentityError(ClaudeWorkerContractError):
    """A process reference cannot be proven to identify the spawned process."""


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
    """An explicit Task 2 boundary, not a subprocess environment mapping."""

    def as_subprocess_environment(self) -> dict[str, str]:
        raise ClaudeLaunchEnvironmentUnavailableError(
            "Claude worker launch environment is not realized until Task 2"
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
    ref: WorkerProcessRef
    process: asyncio.subprocess.Process
    baseline: Any
    schema: Any
    stdout_task: asyncio.Task[tuple[bytes, bool]]
    stderr_task: asyncio.Task[tuple[bytes, bool]]
    status: WorkerRunStatus = WorkerRunStatus.RUNNING
    cancel_reason: str | None = None
    timed_out: bool = False
    escalated: bool = False
    receipt: CollectionReceipt | None = None


class _DeferredProcessInspector:
    """Avoid implying that Task 1 has process identity/runtime support."""

    def boot_session_id(self) -> str:
        raise ClaudeWorkerNotImplementedError("Claude process inspection is not implemented")

    def identity(self, pid: int) -> tuple[str, int]:
        del pid
        raise ClaudeWorkerNotImplementedError("Claude process inspection is not implemented")

    def inspect(self, pid: int) -> object:
        del pid
        raise ClaudeWorkerNotImplementedError("Claude process inspection is not implemented")


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
    result = {"PATH": _SAFE_PATH, "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "TMPDIR": "/tmp", "TZ": "UTC"}
    for key in _AUTH_ENV_PATH_KEYS:
        value = incoming.get(key)
        if value is None:
            continue
        if (
            not isinstance(value, str)
            or not value
            or len(value.encode("utf-8", "strict")) > 4096
            or _CONTROL_RE.search(value)
            or _SECRET_VALUE_RE.search(value)
            or not Path(value).is_absolute()
        ):
            raise ClaudeAuthStatusError("provider credential environment is refused")
        result[key] = value
    return result


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
    except (UnicodeDecodeError, ValueError, TypeError, RecursionError) as exc:
        raise error_type("provider JSON is malformed") from exc
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


def _write_private_bytes(path: Path, payload: bytes) -> str:
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) & 0o077:
        raise ClaudeResultValidationError("result output path is not private")
    flags = os.O_WRONLY | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    fd = os.open(path, flags)
    try:
        offset = 0
        while offset < len(payload):
            written = os.write(fd, payload[offset:])
            if written <= 0:
                raise OSError("short result write")
            offset += written
        os.fsync(fd)
    finally:
        os.close(fd)
    return hashlib.sha256(payload).hexdigest()


async def _read_stream_limited(reader: asyncio.StreamReader, maximum: int) -> tuple[bytes, bool]:
    chunks: list[bytes] = []
    total = 0
    exceeded = False
    while chunk := await reader.read(64 * 1024):
        total += len(chunk)
        if total <= maximum:
            chunks.append(chunk)
        else:
            exceeded = True
    return b"".join(chunks), exceeded


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
        if set(parsed) - _RAW_AUTH_ALLOWED_KEYS or any(
            _contains_secret_shaped(value) for value in parsed.values()
        ):
            raise ClaudeAuthStatusError("auth observation contains unsupported sensitive data")
        logged_in = parsed.get("loggedIn")
        if (
            type(logged_in) is not bool
            or exit_code not in {0, 1}
            or (exit_code == 0) is not logged_in
        ):
            raise ClaudeAuthStatusError("auth observation response is unsupported")
        for key, value in parsed.items():
            if key == "loggedIn":
                continue
            if value is not None and (
                not isinstance(value, str)
                or len(value.encode("utf-8", "strict")) > _MAX_AUTH_STRING_BYTES
                or _CONTROL_RE.search(value)
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
            if self.inspector.boot_session_id() != ref.boot_session_id:
                return False
            identity = self.inspector.inspect(ref.pid)
            return (
                getattr(identity, "start_identity", None) == ref.process_start_identity
                and getattr(identity, "pgid", None) == ref.pgid
                and getattr(identity, "session_id", None) == ref.session_id
                and getattr(identity, "effective_uid", None) == ref.effective_uid
                and getattr(identity, "effective_gid", None) == ref.effective_gid
            )
        except Exception:
            return False

    async def start(self, spec: WorkerLaunchSpec) -> WorkerProcessRef:
        workspace, run_dir, home, tmp, baseline, schema = self._validate_spec(spec)
        _assert_claude_binary_unchanged(self.binary)
        stdout_path = run_dir / "logs" / "stdout.json"
        stderr_path = run_dir / "logs" / "stderr.log"
        result_path = run_dir / "output" / "result.json"
        stdout_fd = _create_private_file(stdout_path)
        stderr_fd: int | None = None
        try:
            stderr_fd = _create_private_file(stderr_path)
            result_fd = _create_private_file(result_path)
            os.close(result_fd)
            process = await asyncio.create_subprocess_exec(
                *self._launch_argv(spec, schema),
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(workspace),
                env=_closed_launch_environment(home, tmp, spec),
                start_new_session=True,
                limit=128 * 1024,
            )
        except Exception:
            os.close(stdout_fd)
            if stderr_fd is not None:
                os.close(stderr_fd)
            raise
        else:
            os.close(stdout_fd)
            assert stderr_fd is not None
            os.close(stderr_fd)
        if process.stdout is None or process.stderr is None:
            raise ClaudeLaunchError("foreground process pipes are unavailable")
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
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            await process.wait()
            raise ClaudeProcessIdentityError("Claude process identity is unavailable") from exc
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
        state = _RunState(
            spec, ref, process, baseline, schema,
            asyncio.create_task(_read_stream_limited(process.stdout, _MAX_STDOUT_BYTES)),
            asyncio.create_task(_read_stream_limited(process.stderr, _MAX_STDERR_BYTES)),
        )
        self._runs[spec.run_id] = state
        return ref

    async def status(self, ref: WorkerProcessRef) -> WorkerRunStatus:
        state = self._state(ref)
        if state.receipt is not None:
            return state.receipt.result.status
        if state.process.returncode is None:
            if not self._identity_matches(ref):
                raise ClaudeProcessIdentityError("Claude process identity is ambiguous")
            return WorkerRunStatus.CANCELLING if state.cancel_reason else WorkerRunStatus.RUNNING
        return WorkerRunStatus.CANCELLING if state.cancel_reason else WorkerRunStatus.RUNNING

    async def collect_result(self, ref: WorkerProcessRef) -> CollectionReceipt:
        state = self._state(ref)
        if state.receipt is not None:
            return state.receipt
        if state.process.returncode is None:
            try:
                await asyncio.wait_for(state.process.wait(), timeout=float(state.spec.timeout_seconds))
            except asyncio.TimeoutError:
                state.timed_out = True
                await self._terminate(state, f"timeout after {state.spec.timeout_seconds:g}s")
        stdout, stdout_exceeded = await state.stdout_task
        stderr, stderr_exceeded = await state.stderr_task
        status, output, session, usage, result_hash = WorkerRunStatus.FAILED, None, None, {}, None
        error: str | None = None
        git_after = None
        try:
            if self._identity_matches(ref):
                raise ClaudeProcessIdentityError("process identity is still live after exit")
            if state.timed_out:
                status, error = WorkerRunStatus.TIMED_OUT, "worker timed out"
            elif state.cancel_reason:
                status, error = WorkerRunStatus.CANCELLED, "worker cancelled"
            elif state.process.returncode != 0:
                status, error = WorkerRunStatus.FAILED, "provider process failed"
            elif stdout_exceeded or stderr_exceeded:
                raise ClaudeResultValidationError("provider output exceeded byte cap")
            else:
                output, session, usage = self._parse_provider_result(
                    stdout, state.schema, state.spec
                )
                result_hash = _write_private_bytes(
                    Path(ref.result_path),
                    _canonical_json(output).encode("utf-8") + b"\n",
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
                status = WorkerRunStatus.SUCCEEDED
        except (ClaudeWorkerContractError, LaunchValidationError, ProcessIdentityError, ResultValidationError, OSError, UnicodeError, ValueError):
            if status not in {WorkerRunStatus.TIMED_OUT, WorkerRunStatus.CANCELLED}:
                status, error = WorkerRunStatus.INVALID_RESULT, "provider result rejected"
        if not _raw_output_is_sensitive(stdout) and not _raw_output_is_sensitive(stderr):
            _write_private_bytes(Path(ref.stdout_path), stdout)
            _write_private_bytes(Path(ref.stderr_path), stderr)
        artifacts = () if status is not WorkerRunStatus.SUCCEEDED else CodexWorkerAdapter._artifact_receipts(self, state, output or {})
        worker_result = WorkerResult(
            job_id=state.spec.job_id, run_id=state.spec.run_id, worker_id=state.spec.worker_id,
            status=status, structured_output=output if status is WorkerRunStatus.SUCCEEDED else None,
            artifact_manifest=artifacts,
            git_manifest={
                "base_sha": state.baseline.head,
                "head_sha": git_after.head if git_after is not None else None,
                "changed_paths": list(_git_changed_paths(Path(state.spec.workspace_path).resolve(strict=True))) if git_after else [],
            },
            usage=usage if status is WorkerRunStatus.SUCCEEDED else {},
            provider_session_id=session if status is WorkerRunStatus.SUCCEEDED else None,
            exit_code=state.process.returncode, started_at=ref.started_at, finished_at=_utc_now(), error=error,
        )
        receipt = CollectionReceipt(
            process_ref=dataclasses.replace(ref, provider_session_id=worker_result.provider_session_id),
            result=worker_result,
            stdout_sha256=hashlib.sha256(stdout).hexdigest(),
            stderr_sha256=hashlib.sha256(stderr).hexdigest(),
            result_sha256=result_hash if status is WorkerRunStatus.SUCCEEDED else None,
        )
        state.status, state.receipt = status, receipt
        return receipt

    async def cancel(self, ref: WorkerProcessRef, reason: str) -> CancelReceipt:
        state = self._state(ref)
        if not isinstance(reason, str) or not reason.strip() or len(reason) > 1000:
            raise ClaudeLaunchError("cancellation reason is invalid")
        sent, escalated, already = await self._terminate(state, reason.strip())
        return CancelReceipt(ref.run_id, reason.strip(), sent, escalated, already, _utc_now())

    def _state(self, ref: WorkerProcessRef) -> _RunState:
        state = self._runs.get(ref.run_id)
        if state is None or state.ref != ref:
            raise ClaudeProcessIdentityError("unknown or mismatched Claude process reference")
        return state

    async def _terminate(self, state: _RunState, reason: str) -> tuple[bool, bool, bool]:
        if state.process.returncode is not None:
            return False, False, True
        if not self._identity_matches(state.ref):
            raise ClaudeProcessIdentityError("refusing to signal ambiguous Claude process identity")
        state.cancel_reason = reason
        state.status = WorkerRunStatus.CANCELLING
        try:
            os.killpg(state.ref.pgid, signal.SIGTERM)
            sent = True
        except ProcessLookupError:
            return False, False, True
        try:
            await asyncio.wait_for(
                state.process.wait(), timeout=float(state.spec.cancel_grace_seconds)
            )
            return sent, False, False
        except asyncio.TimeoutError:
            if not self._identity_matches(state.ref):
                raise ClaudeProcessIdentityError(
                    "Claude process identity changed before SIGKILL escalation"
                )
            try:
                os.killpg(state.ref.pgid, signal.SIGKILL)
            except ProcessLookupError:
                return sent, False, True
            await state.process.wait()
            state.escalated = True
            return sent, True, False

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
            or len(session.encode("utf-8", "strict")) > 512
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
        if isinstance(argv, (str, bytes)) or not isinstance(argv, Sequence):
            raise ClaudeLaunchError("validation command must be argv")
        exact = tuple(argv)
        if not exact or any(not isinstance(value, str) or not value or "\x00" in value for value in exact):
            raise ClaudeLaunchError("validation argv is invalid")
        if sum(len(value.encode("utf-8")) + 1 for value in exact) > _MAX_VALIDATION_ARGV_BYTES:
            raise ClaudeLaunchError("validation argv exceeds byte cap")
        if PurePosixPath(exact[0]).name.lower() in _SHELL_NAMES:
            raise ClaudeLaunchError("validation argv may not invoke a shell")
        timeout = float(timeout_seconds)
        if not 0.1 <= timeout <= 3600:
            raise ClaudeLaunchError("validation timeout is outside the bounded contract")
        workspace, run_dir, _home, _tmp, baseline, _schema = self._validate_spec(
            dataclasses.replace(spec, run_id=f"validation-{uuid.uuid4().hex[:16]}", model=self.exact_model)
        )
        del baseline
        home = _ensure_private_directory(run_dir / "validation-home")
        tmp = _ensure_private_directory(run_dir / "validation-tmp")
        process = await asyncio.create_subprocess_exec(
            *exact, stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE, cwd=str(workspace),
            env=_closed_launch_environment(home, tmp, spec), start_new_session=True,
        )
        if process.stdout is None or process.stderr is None:
            raise ClaudeLaunchError("validation pipes are unavailable")
        out_task = asyncio.create_task(_read_stream_limited(process.stdout, _MAX_VALIDATION_STDOUT_BYTES))
        err_task = asyncio.create_task(_read_stream_limited(process.stderr, _MAX_VALIDATION_STDERR_BYTES))
        timed_out, error = False, None
        try:
            await asyncio.wait_for(process.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            timed_out, error = True, "validation timed out"
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            await process.wait()
        stdout, stdout_exceeded = await out_task
        stderr, stderr_exceeded = await err_task
        if stdout_exceeded or stderr_exceeded:
            error = error or "validation output exceeded byte cap"
        return ValidationReceipt(
            argv=exact, exit_code=process.returncode,
            stdout_sha256=hashlib.sha256(stdout).hexdigest(), stdout_size=len(stdout),
            stderr_sha256=hashlib.sha256(stderr).hexdigest(), stderr_size=len(stderr),
            timed_out=timed_out, error=error,
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
