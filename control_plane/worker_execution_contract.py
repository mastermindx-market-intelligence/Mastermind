"""Provider-neutral execution values shared by Executive OS worker adapters.

This module contains only immutable request, process, result, and receipt
shapes.  Provider configuration and credentials belong to concrete adapters;
they must never enter :class:`WorkerLaunchSpec`.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import re
import stat
from collections.abc import Iterator, Mapping
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Any, Protocol, runtime_checkable


WORKER_EXECUTION_CONTRACT_VERSION = "mastermind.worker_execution_contract/v1"
LAUNCH_ATTESTATION_SCHEMA_VERSION = "mastermind.executive_launch_attestation/v1"
WORKER_RECOVERY_BINDING_VERSION = "mastermind.worker_recovery_binding/v1"
DURABLE_COLLECTION_CONTRACT_VERSION = "mastermind.worker_durable_collection/v1"
_MAX_RECOVERY_PROMPT_BYTES = 1024 * 1024
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SUBSCRIPTION_CANARY_CLAIM_FIELDS = frozenset({
    "schema", "execution_mode", "run_id", "job_id", "worker_id", "quota_class",
    "fence_generation", "capacity_generation", "capacity_state", "held_attempt_id",
    "current_attempt_id", "binding_id", "profile_id", "adapter_id", "model",
    "realm_config_sha256", "realm_generation", "catalog_digest", "issued_at_ms",
    "expires_at_ms", "observation_digest",
})
_SUBSCRIPTION_CANARY_TOKEN_FIELDS = frozenset({
    "run_id", "job_id", "worker_id", "quota_class", "held_attempt_id",
    "current_attempt_id", "binding_id", "profile_id", "adapter_id", "model",
})
_SUBSCRIPTION_CANARY_DIGEST_FIELDS = frozenset({
    "realm_config_sha256", "catalog_digest", "observation_digest",
})
_SUBSCRIPTION_CANARY_INTEGER_FIELDS = frozenset({
    "fence_generation", "capacity_generation", "realm_generation",
    "issued_at_ms", "expires_at_ms",
})
_SUBSCRIPTION_CANARY_SECRET_NAME_RE = re.compile(
    r"(?:^|_)(?:api[-_]?key|authorization|credential|secret|token)(?:$|_)",
    re.IGNORECASE,
)
_SUBSCRIPTION_CANARY_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")

MAX_ARTIFACTS = 32
MAX_ARTIFACT_BYTES = 8 * 1024 * 1024
MAX_ARTIFACT_TOTAL_BYTES = 32 * 1024 * 1024


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


def _jsonable(value: Any) -> Any:
    if dataclasses.is_dataclass(value):
        return {
            field.name: _jsonable(getattr(value, field.name))
            for field in dataclasses.fields(value)
        }
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def validate_subscription_canary_claim(value: Any) -> Mapping[str, Any]:
    """Validate and freeze the exact public owner observation.

    The durable launch field is evidence only; the process-local admission
    travels through a separate adapter seam and is never persisted.
    """

    if value is None or (isinstance(value, Mapping) and not value):
        return _FrozenMapping(())
    if not isinstance(value, Mapping) or set(value) != _SUBSCRIPTION_CANARY_CLAIM_FIELDS:
        raise WorkerRecoveryContractError("subscription canary claim fields are invalid")
    for field_name in _SUBSCRIPTION_CANARY_TOKEN_FIELDS:
        token = value[field_name]
        if not isinstance(token, str) or _SUBSCRIPTION_CANARY_TOKEN_RE.fullmatch(token) is None:
            raise WorkerRecoveryContractError(
                f"subscription canary claim {field_name} is invalid"
            )
    for field_name in _SUBSCRIPTION_CANARY_DIGEST_FIELDS:
        digest = value[field_name]
        if not isinstance(digest, str) or _SHA256_RE.fullmatch(digest) is None:
            raise WorkerRecoveryContractError(
                f"subscription canary claim {field_name} is invalid"
            )
    for field_name in _SUBSCRIPTION_CANARY_INTEGER_FIELDS:
        number = value[field_name]
        if type(number) is not int or not 0 < number < 2**63:
            raise WorkerRecoveryContractError(
                f"subscription canary claim {field_name} is invalid"
            )
    if (
        value["schema"] != "mastermind.subscription_canary_claim/v1"
        or value["execution_mode"] != "interactive_canary"
        or value["capacity_state"] != "BUSY"
        or value["capacity_generation"] != value["fence_generation"]
        or value["held_attempt_id"] != value["run_id"]
        or value["current_attempt_id"] != value["run_id"]
        or not value["issued_at_ms"] <= value["expires_at_ms"]
    ):
        raise WorkerRecoveryContractError("subscription canary claim is malformed")
    frozen = _freeze(dict(value))
    for key, item in frozen.items():
        if isinstance(key, str) and _SUBSCRIPTION_CANARY_SECRET_NAME_RE.search(key):
            raise WorkerRecoveryContractError(
                "subscription canary claim contains a secret-like field"
            )
        if isinstance(item, str) and _SUBSCRIPTION_CANARY_SECRET_NAME_RE.fullmatch(item):
            raise WorkerRecoveryContractError(
                "subscription canary claim contains a raw secret label"
            )
    return frozen


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
    subscription_canary_observation_digest: str | None = None
    subscription_canary_binding_id: str | None = None
    subscription_canary_model: str | None = None
    isolation_manifest_sha256: str | None = None

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
            "workspace_identity": _jsonable(self.workspace_identity),
            "worker_identity": _jsonable(self.worker_identity),
            "provider_home_identity": _jsonable(self.provider_home_identity),
            "secret_canary_verdict": _jsonable(self.secret_canary_verdict),
            "launch_nonce": self.launch_nonce,
            "process_identity": dict(self.process_identity),
            **(
                {"isolation_manifest_sha256": self.isolation_manifest_sha256}
                if self.isolation_manifest_sha256 is not None
                else {}
            ),
            **(
                {
                    "subscription_canary_observation_digest": (
                        self.subscription_canary_observation_digest
                    ),
                    "subscription_canary_binding_id": self.subscription_canary_binding_id,
                    "subscription_canary_model": self.subscription_canary_model,
                }
                if self.subscription_canary_observation_digest is not None
                else {}
            ),
        }


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
    max_artifacts: int = MAX_ARTIFACTS
    max_artifact_bytes: int = MAX_ARTIFACT_BYTES
    max_artifact_total_bytes: int = MAX_ARTIFACT_TOTAL_BYTES
    expected_worker_uid: int | None = None
    expected_worker_gid: int | None = None
    shared_run_gid: int | None = None
    secret_canary_verdict: Mapping[str, Any] = dataclasses.field(default_factory=dict)
    require_secret_canary: bool = False
    subscription_canary_claim: Mapping[str, Any] = dataclasses.field(default_factory=dict)

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
        object.__setattr__(
            self,
            "subscription_canary_claim",
            validate_subscription_canary_claim(self.subscription_canary_claim),
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


class WorkerRecoveryContractError(ValueError):
    """Durable worker recovery evidence is malformed or has drifted."""


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        _jsonable(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _launch_spec_material(spec: WorkerLaunchSpec) -> dict[str, Any]:
    material = {
        field.name: _jsonable(getattr(spec, field.name))
        for field in dataclasses.fields(spec)
        if field.name != "prompt"
    }
    material["prompt_sha256"] = hashlib.sha256(
        spec.prompt.encode("utf-8")
    ).hexdigest()
    return material


def worker_launch_spec_sha256(spec: WorkerLaunchSpec) -> str:
    """Hash the exact provider-neutral launch contract without storing prompt bytes."""

    if not isinstance(spec, WorkerLaunchSpec):
        raise WorkerRecoveryContractError(
            "recovery binding requires WorkerLaunchSpec"
        )
    return _canonical_sha256(_launch_spec_material(spec))


def _recovery_prompt_bytes(path: Path) -> bytes:
    try:
        info = path.lstat()
    except OSError as exc:
        raise WorkerRecoveryContractError(
            "recovery prompt is unavailable"
        ) from exc
    if (
        stat.S_ISLNK(info.st_mode)
        or not stat.S_ISREG(info.st_mode)
        or info.st_nlink != 1
        or info.st_uid != os.geteuid()
        or stat.S_IMODE(info.st_mode) & 0o077
        or info.st_size <= 0
        or info.st_size > _MAX_RECOVERY_PROMPT_BYTES
    ):
        raise WorkerRecoveryContractError(
            "recovery prompt is not a private bounded control-owned file"
        )
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise WorkerRecoveryContractError(
            "recovery prompt is unavailable"
        ) from exc
    if len(payload) != info.st_size:
        raise WorkerRecoveryContractError(
            "recovery prompt changed while reading"
        )
    try:
        payload.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise WorkerRecoveryContractError(
            "recovery prompt is not strict UTF-8"
        ) from exc
    return payload


def _process_ref_from_recovery(value: Any) -> WorkerProcessRef:
    if not isinstance(value, Mapping):
        raise WorkerRecoveryContractError(
            "recovery process_ref must be an object"
        )
    raw = dict(value)
    binary = raw.get("binary")
    if not isinstance(binary, Mapping):
        raise WorkerRecoveryContractError(
            "recovery process_ref binary is invalid"
        )
    try:
        raw["binary"] = BinaryAttestation(**dict(binary))
        return WorkerProcessRef(**raw)
    except (TypeError, ValueError) as exc:
        raise WorkerRecoveryContractError(
            "recovery process_ref is invalid"
        ) from exc


@dataclasses.dataclass(frozen=True)
class WorkerRecoveryBinding:
    """Provider-neutral durable coordinates for one already-started execution."""

    schema_version: str
    adapter_id: str
    collection_contract_version: str
    launch_spec_sha256: str
    launch_spec: Mapping[str, Any] = dataclasses.field(repr=False)
    process_ref: WorkerProcessRef

    def __post_init__(self) -> None:
        object.__setattr__(self, "launch_spec", _freeze(self.launch_spec))
        if self.schema_version != WORKER_RECOVERY_BINDING_VERSION:
            raise WorkerRecoveryContractError(
                "recovery binding schema is unsupported"
            )
        if (
            self.collection_contract_version
            != DURABLE_COLLECTION_CONTRACT_VERSION
        ):
            raise WorkerRecoveryContractError(
                "recovery collection contract is unsupported"
            )
        if not isinstance(self.adapter_id, str) or not self.adapter_id.strip():
            raise WorkerRecoveryContractError(
                "recovery adapter identity is invalid"
            )
        if (
            not isinstance(self.launch_spec_sha256, str)
            or _SHA256_RE.fullmatch(self.launch_spec_sha256) is None
        ):
            raise WorkerRecoveryContractError(
                "recovery launch digest is invalid"
            )
        fields = self.launch_spec.get("fields")
        if (
            set(self.launch_spec)
            != {"fields", "prompt_path", "prompt_sha256"}
            or not isinstance(fields, Mapping)
            or fields.get("run_id") != self.process_ref.run_id
        ):
            raise WorkerRecoveryContractError(
                "recovery run identity is inconsistent"
            )
        prompt_digest = self.launch_spec.get("prompt_sha256")
        if (
            not isinstance(prompt_digest, str)
            or _SHA256_RE.fullmatch(prompt_digest) is None
        ):
            raise WorkerRecoveryContractError(
                "recovery prompt digest is invalid"
            )

    @classmethod
    def bind(
        cls,
        *,
        adapter_id: str,
        spec: WorkerLaunchSpec,
        process_ref: WorkerProcessRef,
        prompt_path: str | Path,
    ) -> "WorkerRecoveryBinding":
        if process_ref.run_id != spec.run_id:
            raise WorkerRecoveryContractError(
                "recovery run identity is inconsistent"
            )
        path = Path(prompt_path)
        if not path.is_absolute():
            raise WorkerRecoveryContractError(
                "recovery prompt path must be absolute"
            )
        try:
            resolved = path.resolve(strict=True)
            input_root = (Path(spec.run_dir) / "input").resolve(strict=True)
            resolved.relative_to(input_root)
        except (OSError, ValueError) as exc:
            raise WorkerRecoveryContractError(
                "recovery prompt path escapes the run input directory"
            ) from exc
        payload = _recovery_prompt_bytes(resolved)
        if payload != spec.prompt.encode("utf-8"):
            raise WorkerRecoveryContractError(
                "recovery prompt bytes differ from the launch specification"
            )
        fields = {
            field.name: _jsonable(getattr(spec, field.name))
            for field in dataclasses.fields(spec)
            if field.name != "prompt"
        }
        return cls(
            schema_version=WORKER_RECOVERY_BINDING_VERSION,
            adapter_id=str(adapter_id),
            collection_contract_version=DURABLE_COLLECTION_CONTRACT_VERSION,
            launch_spec_sha256=worker_launch_spec_sha256(spec),
            launch_spec={
                "fields": fields,
                "prompt_path": str(resolved),
                "prompt_sha256": hashlib.sha256(payload).hexdigest(),
            },
            process_ref=process_ref,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "adapter_id": self.adapter_id,
            "collection_contract_version": self.collection_contract_version,
            "launch_spec_sha256": self.launch_spec_sha256,
            "launch_spec": _jsonable(self.launch_spec),
            "process_ref": _jsonable(self.process_ref),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "WorkerRecoveryBinding":
        if not isinstance(value, Mapping) or set(value) != {
            "schema_version",
            "adapter_id",
            "collection_contract_version",
            "launch_spec_sha256",
            "launch_spec",
            "process_ref",
        }:
            raise WorkerRecoveryContractError(
                "recovery binding fields are invalid"
            )
        launch_spec = value.get("launch_spec")
        if not isinstance(launch_spec, Mapping):
            raise WorkerRecoveryContractError(
                "recovery launch material is invalid"
            )
        return cls(
            schema_version=value.get("schema_version"),
            adapter_id=value.get("adapter_id"),
            collection_contract_version=value.get(
                "collection_contract_version"
            ),
            launch_spec_sha256=value.get("launch_spec_sha256"),
            launch_spec=dict(launch_spec),
            process_ref=_process_ref_from_recovery(value.get("process_ref")),
        )

    def recover_launch_spec(
        self,
        spec_type: type[WorkerLaunchSpec] = WorkerLaunchSpec,
    ) -> WorkerLaunchSpec:
        if not isinstance(spec_type, type) or not issubclass(
            spec_type, WorkerLaunchSpec
        ):
            raise WorkerRecoveryContractError(
                "recovery launch type is invalid"
            )
        fields = self.launch_spec["fields"]
        if not isinstance(fields, Mapping):
            raise WorkerRecoveryContractError(
                "recovery launch fields are invalid"
            )
        raw = dict(_jsonable(fields))
        prompt_path = Path(str(self.launch_spec["prompt_path"]))
        run_dir = Path(str(raw.get("run_dir", "")))
        try:
            prompt_path.resolve(strict=True).relative_to(
                (run_dir / "input").resolve(strict=True)
            )
        except (OSError, ValueError) as exc:
            raise WorkerRecoveryContractError(
                "recovery prompt path escapes the run input directory"
            ) from exc
        payload = _recovery_prompt_bytes(prompt_path)
        digest = hashlib.sha256(payload).hexdigest()
        if digest != self.launch_spec["prompt_sha256"]:
            raise WorkerRecoveryContractError(
                "recovery prompt digest has drifted"
            )
        try:
            prompt = payload.decode("utf-8", errors="strict")
            for name in (
                "workspace_path",
                "run_dir",
                "result_schema_path",
            ):
                raw[name] = Path(raw[name])
            for name in (
                "isolation_roots",
                "isolation_denied_paths",
                "forbidden_paths",
            ):
                raw[name] = tuple(Path(item) for item in raw[name])
            for name in ("authorities", "allowed_artifact_paths"):
                raw[name] = tuple(raw[name])
            spec = spec_type(prompt=prompt, **raw)
        except (KeyError, TypeError, ValueError) as exc:
            raise WorkerRecoveryContractError(
                "recovery launch specification is invalid"
            ) from exc
        if (
            spec.run_id != self.process_ref.run_id
            or worker_launch_spec_sha256(spec) != self.launch_spec_sha256
        ):
            raise WorkerRecoveryContractError(
                "recovery launch specification digest or run identity has drifted"
            )
        return spec


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
    "LAUNCH_ATTESTATION_SCHEMA_VERSION",
    "WORKER_RECOVERY_BINDING_VERSION",
    "DURABLE_COLLECTION_CONTRACT_VERSION",
    "validate_subscription_canary_claim",
    "MAX_ARTIFACTS",
    "MAX_ARTIFACT_BYTES",
    "MAX_ARTIFACT_TOTAL_BYTES",
    "ArtifactReceipt",
    "BinaryAttestation",
    "CancelReceipt",
    "CollectionReceipt",
    "LaunchAttestation",
    "ProcessInspector",
    "ValidationReceipt",
    "WorkerLaunchSpec",
    "WorkerRecoveryBinding",
    "WorkerRecoveryContractError",
    "worker_launch_spec_sha256",
    "WorkerProcessRef",
    "WorkerResult",
    "WorkerRunStatus",
]
