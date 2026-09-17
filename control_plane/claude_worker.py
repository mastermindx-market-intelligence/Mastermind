"""Bounded native Claude Code command compiler for the common worker harness.

This Task 1 adapter intentionally stops before provider process lifecycle,
authentication observation, or result parsing.  It owns only immutable
provider-private construction, binary attestation, and the closed invocation
policy that later lifecycle work will execute.
"""
from __future__ import annotations

import dataclasses
import hashlib
import os
import re
import stat
import subprocess
from pathlib import Path
from typing import Sequence

from control_plane.worker_execution_contract import (
    BinaryAttestation,
    CancelReceipt,
    CollectionReceipt,
    ProcessInspector,
    ValidationReceipt,
    WorkerLaunchSpec,
    WorkerProcessRef,
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


class ClaudeWorkerContractError(RuntimeError):
    """The native Claude command contract could not be safely compiled."""


class ClaudeWorkerNotImplementedError(ClaudeWorkerContractError):
    """A lifecycle operation intentionally deferred to Task 2."""


class ClaudeLaunchEnvironmentUnavailableError(ClaudeWorkerContractError):
    """Task 2 has not yet established the native worker launch environment."""


@dataclasses.dataclass(frozen=True)
class ClaudeAuthObservation:
    """Closed, non-secret readiness facts for the later auth-status probe."""

    client_version: str
    authenticated: bool | None
    exit_code: int | None


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


class ClaudeCodeWorkerAdapter:
    """Native Claude Code provider boundary with no Task 2 lifecycle behavior."""

    adapter_id = "claude-code"
    __slots__ = ("_configuration", "inspector", "__weakref__")

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
        self.inspector: ProcessInspector = _DeferredProcessInspector()

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

    async def start(self, spec: WorkerLaunchSpec) -> WorkerProcessRef:
        del spec
        raise ClaudeWorkerNotImplementedError("Claude process start is not implemented")

    async def status(self, ref: WorkerProcessRef) -> WorkerRunStatus:
        del ref
        raise ClaudeWorkerNotImplementedError("Claude process status is not implemented")

    async def collect_result(self, ref: WorkerProcessRef) -> CollectionReceipt:
        del ref
        raise ClaudeWorkerNotImplementedError("Claude result collection is not implemented")

    async def cancel(self, ref: WorkerProcessRef, reason: str) -> CancelReceipt:
        del ref, reason
        raise ClaudeWorkerNotImplementedError("Claude cancellation is not implemented")

    async def run_validation_argv(
        self,
        spec: WorkerLaunchSpec,
        argv: Sequence[str],
        *,
        timeout_seconds: float = 300.0,
    ) -> ValidationReceipt:
        del spec, argv, timeout_seconds
        raise ClaudeWorkerNotImplementedError("Claude validation execution is not implemented")


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
