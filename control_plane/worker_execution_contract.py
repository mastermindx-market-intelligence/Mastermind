"""Provider-neutral execution values shared by Executive OS worker adapters.

This module contains only immutable request, process, result, and receipt
shapes.  Provider configuration and credentials belong to concrete adapters;
they must never enter :class:`WorkerLaunchSpec`.
"""
from __future__ import annotations

import dataclasses
from collections.abc import Iterator, Mapping
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Any, Protocol, runtime_checkable


WORKER_EXECUTION_CONTRACT_VERSION = "mastermind.worker_execution_contract/v1"

_MAX_ARTIFACTS = 32
_MAX_ARTIFACT_BYTES = 8 * 1024 * 1024
_MAX_ARTIFACT_TOTAL_BYTES = 32 * 1024 * 1024


class _FrozenMapping(Mapping[Any, Any]):
    """Read-only mapping snapshot with no mutable ``dict`` base to bypass."""

    __slots__ = ("__values",)

    def __init__(self, items: Any) -> None:
        object.__setattr__(self, "_FrozenMapping__values", MappingProxyType(dict(items)))

    def __getitem__(self, key: Any) -> Any:
        return self.__values[key]

    def __iter__(self) -> Iterator[Any]:
        return iter(self.__values)

    def __len__(self) -> int:
        return len(self.__values)

    def __repr__(self) -> str:
        return repr(dict(self.__values))

    def __setattr__(self, _name: str, _value: object) -> None:
        raise TypeError("worker execution mappings are immutable")

    def __copy__(self) -> _FrozenMapping:
        return self

    def __deepcopy__(self, _memo: dict[int, object]) -> _FrozenMapping:
        return self


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return _FrozenMapping((key, _freeze(item)) for key, item in value.items())
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(_freeze(item) for item in value)
    return value


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
class WorkerLaunchSpec:
    """Immutable provider-neutral inputs for one authorized worker turn."""

    run_id: str
    job_id: str
    worker_id: str
    workspace_path: Path
    run_dir: Path
    prompt: str
    result_schema_path: Path
    # Executable grants are an exact set, not an ordinal. ``authority`` is a
    # temporary scalar compatibility seam for callers predating Phase 1B.
    authorities: tuple[str, ...] = ()
    authority: str | None = None
    model: str = "gpt-5.6-sol"
    reasoning_effort: str = "xhigh"
    timeout_seconds: float = 1800.0
    cancel_grace_seconds: float = 10.0
    worker_user: str = "mastermind-worker"
    expected_base_sha: str | None = None
    allowed_artifact_paths: tuple[str, ...] = ()
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

    def __post_init__(self) -> None:
        for field_name in (
            "authorities",
            "allowed_artifact_paths",
            "isolation_roots",
            "isolation_denied_paths",
            "forbidden_paths",
        ):
            object.__setattr__(self, field_name, tuple(getattr(self, field_name)))
        object.__setattr__(self, "isolation_manifest", _freeze(self.isolation_manifest))
        object.__setattr__(
            self,
            "secret_canary_verdict",
            _freeze(self.secret_canary_verdict),
        )


@dataclasses.dataclass(frozen=True)
class WorkerProcessRef:
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

    def __post_init__(self) -> None:
        object.__setattr__(self, "artifact_manifest", tuple(self.artifact_manifest))
        if self.structured_output is not None:
            object.__setattr__(self, "structured_output", _freeze(self.structured_output))
        object.__setattr__(self, "git_manifest", _freeze(self.git_manifest))
        object.__setattr__(self, "usage", _freeze(self.usage))


@dataclasses.dataclass(frozen=True)
class CollectionReceipt:
    process_ref: WorkerProcessRef
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

    def __post_init__(self) -> None:
        object.__setattr__(self, "argv", tuple(self.argv))


@runtime_checkable
class ProcessInspector(Protocol):
    """Provider-neutral process identity observations used by supervisors."""

    def boot_session_id(self) -> str: ...

    def identity(self, pid: int) -> tuple[str, int]: ...

    def inspect(self, pid: int) -> object: ...


__all__ = [
    "WORKER_EXECUTION_CONTRACT_VERSION",
    "ArtifactReceipt",
    "BinaryAttestation",
    "CancelReceipt",
    "CollectionReceipt",
    "ProcessInspector",
    "ValidationReceipt",
    "WorkerLaunchSpec",
    "WorkerProcessRef",
    "WorkerResult",
    "WorkerRunStatus",
]
