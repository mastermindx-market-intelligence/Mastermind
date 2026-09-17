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
from pathlib import Path, PurePosixPath
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


@dataclasses.dataclass(frozen=True)
class ClaudeAuthObservation:
    """Closed, non-secret readiness facts for the later auth-status probe."""

    client_version: str
    authenticated: bool | None
    exit_code: int | None


@dataclasses.dataclass(frozen=True)
class ClaudeInvocation:
    """One complete, closed foreground invocation policy."""

    argv: tuple[str, ...]
    environment: dict[str, str]


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


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    size = 0
    try:
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                size += len(chunk)
                if size > _MAX_BINARY_BYTES:
                    raise ClaudeWorkerContractError(
                        "Claude binary exceeds attestation ceiling"
                    )
                digest.update(chunk)
    except OSError as exc:
        raise ClaudeWorkerContractError("Claude binary is unavailable") from exc
    return digest.hexdigest()


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
    try:
        real_path = claude_binary.resolve(strict=True)
        info = real_path.stat()
    except OSError as exc:
        raise ClaudeWorkerContractError("Claude binary is unavailable") from exc
    if not stat.S_ISREG(info.st_mode) or not os.access(real_path, os.X_OK):
        raise ClaudeWorkerContractError("Claude binary is not an executable regular file")
    if not 0 < info.st_size <= _MAX_BINARY_BYTES:
        raise ClaudeWorkerContractError(
            "Claude binary size is outside the attestation ceiling"
        )
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
    return BinaryAttestation(
        path=str(claude_binary),
        real_path=str(real_path),
        version=version,
        sha256=_sha256_path(real_path),
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
        raw.append("READ")
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
        if not isinstance(candidate, str) or not candidate or candidate != candidate.strip():
            raise ClaudeWorkerContractError("unsupported or unmapped Claude capabilities")
        path = PurePosixPath(candidate)
        if path.is_absolute() or ".." in path.parts or str(path) in {".", ""}:
            raise ClaudeWorkerContractError("unsupported or unmapped Claude capabilities")
        paths.append(str(path))
    if len(paths) != len(set(paths)):
        raise ClaudeWorkerContractError("unsupported or unmapped Claude capabilities")
    return tuple(sorted(paths))


def _tool_policy(spec: WorkerLaunchSpec) -> tuple[str, str, str, list[str]]:
    requested = _requested_capabilities(spec)
    tools: list[str] = []
    allowed: list[str] = []
    forbidden = list(_FORBIDDEN_TOOLS)
    settings_allowed: list[str] = []

    if "READ" in requested:
        tools.extend(_READ_TOOLS)
        allowed.extend(_READ_TOOLS)
        settings_allowed.extend(f"{tool}(./**)" for tool in _READ_TOOLS)
    if "WRITE_BRANCH" in requested:
        paths = _allowed_write_paths(spec)
        if not paths:
            raise ClaudeWorkerContractError("unsupported or unmapped Claude capabilities")
        tools.extend(_WRITE_TOOLS)
        allowed.extend(_WRITE_TOOLS)
        for path in paths:
            settings_allowed.extend((f"Edit(./{path})", f"Write(./{path})"))
    if "RUN_TESTS" in requested:
        tools.append(_TEST_TOOL)
        allowed.append("Bash(python3 -m pytest *)")
        settings_allowed.append("Bash(python3 -m pytest *)")

    for tool in ("Bash", "Edit", "Write"):
        if tool not in tools:
            forbidden.append(tool)
    return (
        ",".join(sorted(tools)),
        ",".join(sorted(allowed)),
        ",".join(sorted(forbidden)),
        sorted(settings_allowed),
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

        tools, allowed_tools, forbidden_tools, settings_allowed = _tool_policy(spec)
        settings = {
            "autoMemoryEnabled": False,
            "disableAllHooks": True,
            "enableAllProjectMcpServers": False,
            "enabledMcpjsonServers": [],
            "permissions": {
                "allow": settings_allowed,
                "ask": [],
                "defaultMode": "dontAsk",
                "deny": list(_FORBIDDEN_TOOLS),
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
            tools,
            "--allowedTools",
            allowed_tools,
            "--disallowedTools",
            forbidden_tools,
            "--strict-mcp-config",
            "--mcp-config",
            '{"mcpServers":{}}',
            "--disable-slash-commands",
            "--settings",
            _canonical_json(settings),
            spec.prompt,
        )
        return ClaudeInvocation(argv=argv, environment=_closed_probe_environment())

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
    "ClaudeWorkerContractError",
    "ClaudeWorkerNotImplementedError",
    "attest_claude_code_binary",
]
