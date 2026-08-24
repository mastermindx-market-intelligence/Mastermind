"""Private, local control service for the Executive OS supervisor.

The service is deliberately smaller than a scheduler or remote API.  It opens
the durable :mod:`control_plane.executive_runtime` state, reconciles attempts at
startup, and accepts one bounded JSON request per local Unix-domain connection.
There is no TCP listener and no generic command-execution request.

Provider execution remains owned by an injected ``ExecutiveSupervisor``.  The
injection seam keeps service tests model-free and lets the dedicated macOS host
compose the reviewed worker-principal boundary without importing the financial
application or APScheduler.
"""
from __future__ import annotations

import asyncio
import ctypes
import dataclasses
import errno
import fcntl
import hashlib
import json
import os
import re
import signal
import socket
import stat
import struct
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Mapping, Protocol
from uuid import uuid4

from common.redaction import sanitize_external_text
from control_plane import ceo_intent
from control_plane import executive_ceo_ingress as ceo_ingress
from control_plane.executive_agent_capabilities import CapabilityPolicyError
from control_plane.executive_coo_cycle import CooCycle, CooCycleOutcome
from control_plane.executive_runtime import (
    AttemptStatus,
    Job,
    JobStatus,
    OrchestrationDispatchOutcome,
    Runtime,
    RuntimeProofError,
    SCHEMA_VERSION,
    StateConflict,
    V2_HOST_EXECUTION_BINDING_KEYS,
)
from control_plane.model_router import ModelRouter, RoutingPolicyError
from control_plane.executive_workspace import (
    GitHandoffError,
    LAUNCH_CLEAN_STATUS_ARGS,
    LAUNCH_CLEAN_UNTRACKED_ARGS,
    WorkspaceError,
    git_observation_env,
    observe_launch_cleanliness,
    prepare_credentialless_clone,
    validate_shared_git_handoff,
)


CONTROL_PROTOCOL_VERSION = "mastermind.executive_control/v1"
DEFAULT_MAX_REQUEST_BYTES = 64 * 1024
DEFAULT_MAX_RESPONSE_BYTES = 1024 * 1024
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_BACKUP_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}\.sqlite3$")
_PROOF_WORKSPACE_RE = re.compile(r"^proof-([0-9a-f]{32})$")
_COO_ROOT_SCAN_LIMIT = 64
_COO_ACTIVE_ATTEMPT_STATUSES = frozenset(
    {
        AttemptStatus.CLAIMED,
        AttemptStatus.RUNNING,
        AttemptStatus.CHECKPOINTED,
        AttemptStatus.CANCEL_REQUESTED,
    }
)
_WORKSPACE_ROTATION_SCHEMA = "mastermind.executive_workspace_rotation/v1"
_PROOF_ARTIFACT = "research/executive_os_phase1c_worker_proof/receipt.md"
_SERVICE_GIT_OBSERVATION_ALLOWLIST = frozenset(
    {
        ("rev-parse", "--verify", "HEAD^{commit}"),
        ("rev-parse", "--abbrev-ref", "HEAD"),
        LAUNCH_CLEAN_STATUS_ARGS,
        LAUNCH_CLEAN_UNTRACKED_ARGS,
        ("remote",),
    }
)
_PROOF_OBJECTIVE = (
    "Create the bounded Executive OS Phase 1C-A proof receipt at "
    f"{_PROOF_ARTIFACT}. Record only the assigned Job, Attempt, exact base SHA, "
    "and a short harmless completion statement. Do not access credentials, "
    "network resources, financial state, Git remotes, or any undeclared path."
)
_PROOF_VALIDATION = (
    "/usr/bin/python3",
    "-c",
    (
        "from pathlib import Path; "
        f"p=Path({_PROOF_ARTIFACT!r}); "
        "t=p.read_text(encoding='utf-8'); "
        "assert t.startswith('# Phase 1C-A Worker Proof'); "
        "assert 'Job:' in t and 'Attempt:' in t and 'Base SHA:' in t"
    ),
)
# A local peer that goes away mid-reply is a normal condition, not a service
# fault: the reply (very often an error envelope) simply has nowhere to land.
_CLIENT_GONE = (BrokenPipeError, ConnectionResetError, ConnectionAbortedError)


class ServiceError(RuntimeProofError):
    """A private control-service request could not be completed safely."""


class SupervisorProtocol(Protocol):
    async def start_job(self, job_id: str) -> Any: ...

    async def start_cycle_job(
        self, job_id: str, *, command_id: str
    ) -> Any: ...

    async def finish_job(self, active: Any) -> Any: ...

    def reconcile_restart(self, *, requeue_lost: bool = False) -> list[Any]: ...


class OperatorSupervisorProtocol(Protocol):
    async def start_cycle_job(
        self, job_id: str, *, command_id: str
    ) -> OrchestrationDispatchOutcome: ...

    def reconcile_restart(self, *, requeue_lost: bool = False) -> list[Any]: ...


class BackupBackendProtocol(Protocol):
    def create_online_backup(self, store: Any, destination_dir: Path) -> Any: ...

    def verify_backup(
        self, database_path: Path, manifest_path: Path | None = None
    ) -> Any: ...


@dataclasses.dataclass(frozen=True)
class ServiceConfig:
    """Reviewed host configuration; requests cannot override these values."""

    runtime_root: Path
    socket_path: Path
    proof_source_repository: Path
    proof_workspace_root: Path
    proof_base_sha: str
    proof_branch: str = "codex/phase1c-a-proof"
    proof_shared_gid: int | None = None
    backup_root: Path | None = None
    worker_id: str = "codex-01"
    worker_account_label: str = "dedicated-codex-home"
    worker_type: str = "codex-cli"
    provider: str = "codex"
    quota_class: str = "codex-native"
    model: str = "gpt-5.6-sol"
    effort: str = "xhigh"
    cost_class: str = "standard"
    coo_autonomy_armed: bool = False
    coo_operator_harness_armed: bool = False
    coo_tick_interval_seconds: float = 15.0
    coo_model_alias: str = "coo.sealed"
    coo_quota_class: str = "codex-coo"
    coo_default_quota_class: str = "codex-coo-default"
    coo_operator_model_alias: str = "coo.operator.readonly"
    coo_operator_quota_class: str = "codex-coo-operator"
    operator_harness_binary_digest: str = "0" * 64
    operator_harness_version: str = "unproven"
    allowed_peer_uids: tuple[int, ...] = ()
    max_request_bytes: int = DEFAULT_MAX_REQUEST_BYTES
    max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES
    shutdown_grace_seconds: float = 10.0

    def __post_init__(self) -> None:
        for field_name in (
            "runtime_root",
            "socket_path",
            "proof_source_repository",
            "proof_workspace_root",
        ):
            value = Path(getattr(self, field_name))
            if not value.is_absolute():
                raise ValueError(f"{field_name} must be absolute")
            object.__setattr__(self, field_name, value.resolve(strict=False))
        source = self.proof_source_repository
        workspace_root = self.proof_workspace_root
        if source == workspace_root or source in workspace_root.parents or workspace_root in source.parents:
            raise ValueError("proof source repository and workspace root must not overlap")
        if self.backup_root is not None:
            backup_root = Path(self.backup_root)
            if not backup_root.is_absolute():
                raise ValueError("backup_root must be absolute")
            object.__setattr__(self, "backup_root", backup_root.resolve(strict=False))
        base_sha = str(self.proof_base_sha).strip().lower()
        if re.fullmatch(r"[0-9a-f]{40,64}", base_sha) is None:
            raise ValueError("proof_base_sha must be a full hexadecimal Git object id")
        object.__setattr__(self, "proof_base_sha", base_sha)
        for field_name in (
            "worker_id",
            "quota_class",
            "coo_quota_class",
            "coo_default_quota_class",
            "coo_operator_quota_class",
        ):
            if _ID_RE.fullmatch(str(getattr(self, field_name))) is None:
                raise ValueError(f"invalid {field_name}")
        if not isinstance(self.coo_autonomy_armed, bool):
            raise ValueError("coo_autonomy_armed must be boolean")
        if not isinstance(self.coo_operator_harness_armed, bool):
            raise ValueError("coo_operator_harness_armed must be boolean")
        if self.coo_operator_harness_armed and not self.coo_autonomy_armed:
            raise ValueError(
                "the COO Operator Harness cannot be armed while COO autonomy is off"
            )
        for field_name in ("coo_model_alias", "coo_operator_model_alias"):
            alias = str(getattr(self, field_name)).strip().lower()
            if _ID_RE.fullmatch(alias) is None:
                raise ValueError(f"invalid {field_name}")
            object.__setattr__(self, field_name, alias)
        quota_names = {
            self.quota_class,
            self.coo_quota_class,
            self.coo_default_quota_class,
            self.coo_operator_quota_class,
        }
        if len(quota_names) != 4:
            raise ValueError("proof and COO quota classes must be distinct")
        digest = str(self.operator_harness_binary_digest).strip().lower()
        if re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise ValueError("operator_harness_binary_digest must be SHA-256")
        object.__setattr__(self, "operator_harness_binary_digest", digest)
        version = str(self.operator_harness_version).strip()
        if not version or len(version) > 64:
            raise ValueError("operator_harness_version is invalid")
        object.__setattr__(self, "operator_harness_version", version)
        if not 1.0 <= float(self.coo_tick_interval_seconds) <= 3600.0:
            raise ValueError("coo_tick_interval_seconds must be between 1 and 3600")
        if not str(self.proof_branch).startswith("codex/"):
            raise ValueError("proof_branch must remain under codex/")
        if self.proof_shared_gid is not None and int(self.proof_shared_gid) < 0:
            raise ValueError("proof_shared_gid must be a non-negative integer")
        if not 1024 <= int(self.max_request_bytes) <= 1024 * 1024:
            raise ValueError("max_request_bytes must be between 1 KiB and 1 MiB")
        if not 4096 <= int(self.max_response_bytes) <= 16 * 1024 * 1024:
            raise ValueError("max_response_bytes must be between 4 KiB and 16 MiB")
        if not 0.1 <= float(self.shutdown_grace_seconds) <= 60:
            raise ValueError("shutdown_grace_seconds must be between 0.1 and 60 seconds")


def _jsonable(value: Any) -> Any:
    if hasattr(value, "to_dict"):
        return _jsonable(value.to_dict())
    if dataclasses.is_dataclass(value):
        return _jsonable(dataclasses.asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "value") and isinstance(getattr(value, "value"), str):
        return value.value
    return value


def _canonical_json(value: Any) -> bytes:
    return (
        json.dumps(
            _jsonable(value),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )


def _peer_uid(connection: socket.socket) -> int | None:
    """Return the local peer uid where the platform exposes it."""

    getpeereid = getattr(connection, "getpeereid", None)
    if callable(getpeereid):
        uid, _gid = getpeereid()
        return int(uid)
    if sys.platform == "darwin":
        libc = ctypes.CDLL(None, use_errno=True)
        function = libc.getpeereid
        function.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_uint32), ctypes.POINTER(ctypes.c_uint32)]
        function.restype = ctypes.c_int
        uid = ctypes.c_uint32()
        gid = ctypes.c_uint32()
        if function(connection.fileno(), ctypes.byref(uid), ctypes.byref(gid)) != 0:
            error = ctypes.get_errno()
            raise OSError(error, os.strerror(error))
        return int(uid.value)
    if hasattr(socket, "SO_PEERCRED"):
        size = struct.calcsize("3i")
        raw = connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, size)
        _pid, uid, _gid = struct.unpack("3i", raw)
        return int(uid)
    return None


def _require_listening_if_queryable(listener: socket.socket) -> None:
    """Check SO_ACCEPTCONN where AF_UNIX exposes it (Darwin may not)."""

    try:
        accepting = listener.getsockopt(socket.SOL_SOCKET, socket.SO_ACCEPTCONN)
    except OSError as exc:
        unsupported = {
            errno.EINVAL,
            getattr(errno, "ENOPROTOOPT", -1),
            getattr(errno, "EOPNOTSUPP", -1),
        }
        if exc.errno not in unsupported:
            raise
        return
    if accepting != 1:
        raise ServiceError("activated control socket is not listening")


def activate_launchd_socket(name: str) -> socket.socket:
    """Claim exactly one named launchd listener without trusting an fd env var."""

    if sys.platform != "darwin":
        raise ServiceError("launchd socket activation is available only on macOS")
    if not isinstance(name, str) or _ID_RE.fullmatch(name) is None:
        raise ServiceError("invalid launchd socket name")
    libc = ctypes.CDLL(None, use_errno=True)
    function = libc.launch_activate_socket
    function.argtypes = [
        ctypes.c_char_p,
        ctypes.POINTER(ctypes.POINTER(ctypes.c_int)),
        ctypes.POINTER(ctypes.c_size_t),
    ]
    function.restype = ctypes.c_int
    values = ctypes.POINTER(ctypes.c_int)()
    count = ctypes.c_size_t()
    result = function(name.encode("utf-8"), ctypes.byref(values), ctypes.byref(count))
    if result != 0:
        raise ServiceError(f"launchd did not activate socket {name!r}: error {result}")
    try:
        if count.value != 1:
            for index in range(count.value):
                os.close(int(values[index]))
            raise ServiceError(
                f"launchd socket {name!r} returned {count.value} descriptors; expected one"
            )
        listener = socket.socket(fileno=int(values[0]))
    finally:
        libc.free(values)
    try:
        if listener.family != socket.AF_UNIX or listener.type & socket.SOCK_STREAM == 0:
            raise ServiceError("launchd control listener is not AF_UNIX/SOCK_STREAM")
        _require_listening_if_queryable(listener)
        listener.setblocking(False)
        return listener
    except Exception:
        listener.close()
        raise


class _ModuleBackupBackend:
    """Lazy adapter so the service can land independently of backup helpers."""

    @staticmethod
    def _module() -> Any:
        try:
            from control_plane import executive_backup
        except ImportError as exc:  # pragma: no cover - exercised before sibling lands
            raise ServiceError("Executive backup support is not installed") from exc
        return executive_backup

    def create_online_backup(self, store: Any, destination_dir: Path) -> Any:
        function = getattr(self._module(), "create_online_backup", None)
        if not callable(function):
            raise ServiceError("Executive backup module has no create_online_backup()")
        return function(store, destination_dir)

    def verify_backup(
        self, database_path: Path, manifest_path: Path | None = None
    ) -> Any:
        function = getattr(self._module(), "verify_backup", None)
        if not callable(function):
            raise ServiceError("Executive backup module has no verify_backup()")
        return function(database_path, manifest_path)


class ExecutiveControlService:
    """One private AF_UNIX service around one durable Executive runtime."""

    def __init__(
        self,
        config: ServiceConfig,
        *,
        runtime_factory: Callable[[Path], Runtime] = Runtime.at,
        supervisor_factory: Callable[[Runtime], SupervisorProtocol] | None = None,
        operator_supervisor_factory: (
            Callable[[Runtime, SupervisorProtocol], OperatorSupervisorProtocol]
            | None
        ) = None,
        operator_identity_verifier: Callable[[], Awaitable[None]] | None = None,
        backup_backend: BackupBackendProtocol | None = None,
        activated_socket: socket.socket | None = None,
        service_state: str = "READY",
        canary_loader: Callable[[], Mapping[str, Any]] | None = None,
        ceo_ingress_socket_path: Path | str | None = None,
        ceo_ingress_peer_uid: int | None = None,
        ceo_ingress_grounding_provider: "ceo_ingress.GroundingProvider | None" = None,
        ceo_ingress_armed: bool = False,
        ceo_ingress_activated_socket: socket.socket | None = None,
    ) -> None:
        self.config = config
        self._runtime_factory = runtime_factory
        self._supervisor_factory = supervisor_factory
        self._operator_supervisor_factory = operator_supervisor_factory
        self._operator_identity_verifier = operator_identity_verifier
        self._backup_backend = backup_backend or _ModuleBackupBackend()
        if activated_socket is not None and activated_socket.family != socket.AF_UNIX:
            raise ValueError("activated_socket must use AF_UNIX")
        if activated_socket is not None:
            bound = activated_socket.getsockname()
            if isinstance(bound, bytes):
                bound = os.fsdecode(bound)
            if (
                not isinstance(bound, str)
                or not bound
                or bound.startswith("\0")
                or Path(bound).resolve(strict=False) != config.socket_path
            ):
                raise ValueError("activated_socket path does not match ServiceConfig")
            try:
                _require_listening_if_queryable(activated_socket)
            except ServiceError as exc:
                raise ValueError("activated_socket must already be listening") from exc
        self._activated_socket = activated_socket
        self._launchd_activated = activated_socket is not None
        self.runtime: Runtime | None = None
        self.supervisor: SupervisorProtocol | None = None
        self.operator_supervisor: OperatorSupervisorProtocol | None = None
        self._server: asyncio.AbstractServer | None = None
        self._lock_fd: int | None = None
        self._dispatch_lock = asyncio.Lock()
        self._workspace_lock = asyncio.Lock()
        self._coo_cycle_lock = asyncio.Lock()
        self._dispatch_tasks: dict[str, asyncio.Task[Any]] = {}
        self._dispatch_errors: dict[str, str] = {}
        self._coo_execution_binding = self._load_coo_execution_binding()
        self._coo_tick_task: asyncio.Task[Any] | None = None
        self._coo_shutdown_event: asyncio.Event | None = None
        self._coo_action_tasks: set[asyncio.Task[Any]] = set()
        self._coo_last_outcome: dict[str, Any] | None = None
        self._coo_last_error: str | None = None
        self._coo_last_tick_at: str | None = None
        self._closing = False
        self._startup_reconciliation: list[Any] = []
        self._started_at: str | None = None
        if service_state not in {"READY", "AWAITING_CANARY"}:
            raise ValueError("service_state must be READY or AWAITING_CANARY")
        self._service_state = service_state
        self._canary_loader = canary_loader
        self.instance_id = f"executive-service-{uuid4().hex}"

        # --- MAS-75 PR-A: optional dedicated CeoIngress composition --------
        #
        # Absent (the default) => byte-compatible-unchanged current behavior
        # (adjudication §8.2, R2 §3): no second listener, no startup latch, no
        # ingress handler drain set is ever populated.  One process / one
        # Runtime / one service lock still governs both listeners when
        # present (§8.1) — CeoIngress never opens its own Runtime or lock.
        if ceo_ingress_socket_path is None:
            if ceo_ingress_activated_socket is not None:
                raise ValueError(
                    "ceo_ingress_activated_socket requires ceo_ingress_socket_path"
                )
            if ceo_ingress_peer_uid is not None or ceo_ingress_grounding_provider is not None:
                raise ValueError(
                    "ceo_ingress_peer_uid/ceo_ingress_grounding_provider require "
                    "ceo_ingress_socket_path"
                )
            self._ceo_ingress_socket_path: Path | None = None
        else:
            resolved_ceo_ingress_path = Path(ceo_ingress_socket_path)
            if not resolved_ceo_ingress_path.is_absolute():
                raise ValueError("ceo_ingress_socket_path must be absolute")
            resolved_ceo_ingress_path = resolved_ceo_ingress_path.resolve(strict=False)
            # §17.1: ingress path same as Operator path -> constructor/
            # composition refusal.  The two sockets are transport separation,
            # never one path serving both surfaces.
            if resolved_ceo_ingress_path == config.socket_path:
                raise ValueError(
                    "ceo_ingress_socket_path must differ from the Operator socket_path"
                )
            if ceo_ingress_peer_uid is None:
                raise ValueError(
                    "ceo_ingress_peer_uid is required when ceo_ingress_socket_path is set"
                )
            if ceo_ingress_grounding_provider is None:
                raise ValueError(
                    "ceo_ingress_grounding_provider is required when "
                    "ceo_ingress_socket_path is set"
                )
            if ceo_ingress_activated_socket is not None:
                if ceo_ingress_activated_socket.family != socket.AF_UNIX:
                    raise ValueError("ceo_ingress_activated_socket must use AF_UNIX")
                bound = ceo_ingress_activated_socket.getsockname()
                if isinstance(bound, bytes):
                    bound = os.fsdecode(bound)
                if (
                    not isinstance(bound, str)
                    or not bound
                    or bound.startswith("\0")
                    or Path(bound).resolve(strict=False) != resolved_ceo_ingress_path
                ):
                    raise ValueError(
                        "ceo_ingress_activated_socket path does not match "
                        "ceo_ingress_socket_path"
                    )
                try:
                    _require_listening_if_queryable(ceo_ingress_activated_socket)
                except ServiceError as exc:
                    raise ValueError(
                        "ceo_ingress_activated_socket must already be listening"
                    ) from exc
            self._ceo_ingress_socket_path = resolved_ceo_ingress_path
        self._ceo_ingress_peer_uid = ceo_ingress_peer_uid
        self._ceo_ingress_grounding_provider = ceo_ingress_grounding_provider
        # §9: host-owned/injected policy, default false.  Never set by a
        # request; PR-A models it as constructor/test policy only.
        self._ceo_ingress_armed = bool(ceo_ingress_armed)
        self._ceo_ingress_activated_socket = ceo_ingress_activated_socket
        self._ceo_ingress_launchd_activated = ceo_ingress_activated_socket is not None
        self._ceo_ingress_server: asyncio.AbstractServer | None = None
        # R1 §2.1 in-memory, non-durable startup/readiness latch.  Process
        # lifecycle only; grants no durable authority and is never set by a
        # request.
        self._ceo_ingress_ready = False
        # §14.1 in-memory handler drain set.  No durable request registry,
        # lease, or table backs this.
        self._ceo_ingress_tasks: set[asyncio.Task[Any]] = set()

    def _load_coo_execution_binding(self) -> dict[str, Any]:
        """Resolve one reviewed sealed-COO alias into host-owned Job identity."""

        try:
            router = ModelRouter.load()
            alias = router.model_aliases[self.config.coo_model_alias]
            profile = router.capability_registry.resolve(alias.execution_profile_id)
            operator_alias = router.model_aliases[
                self.config.coo_operator_model_alias
            ]
            operator_profile = router.capability_registry.resolve(
                operator_alias.execution_profile_id
            )
        except (KeyError, RoutingPolicyError, CapabilityPolicyError) as exc:
            raise ValueError(f"configured COO execution alias is invalid: {exc}") from exc
        if (
            not alias.worker_eligible
            or alias.adapter_id != "codex-cli"
            or profile.execution_surface != "codex-exec"
            or not profile.write_capable
            or profile.auth_realm != "dedicated-worker-account"
            or profile.approval_policy != "never"
            or profile.network_policy != "disabled"
            or profile.native_helper_policy.value != "DISABLED"
            or profile.skills
            or profile.mcp_servers
            or profile.plugins
        ):
            raise ValueError(
                "configured COO alias must be a sealed, extension-free, write-capable Codex worker"
            )
        if (
            not operator_alias.worker_eligible
            or operator_alias.adapter_id != "codex-cli"
            or operator_profile.execution_surface != "codex-app-server"
            or operator_profile.write_capable
            or operator_profile.auth_realm != "dedicated-worker-account"
            or operator_profile.sandbox_policy != "read-only"
            or operator_profile.approval_policy != "never"
            or operator_profile.network_policy != "disabled"
            or operator_profile.native_helper_policy.value
            != "PARENT_READ_ONLY_CEILING"
            or operator_profile.native_helper is None
            or operator_profile.skills
            or operator_profile.profile_id
            != "operator.appserver.readonly.docs-mcp.native-helper.v1"
            or operator_profile.mcp_servers != ("openai-developer-docs-v1",)
            or operator_profile.plugins
        ):
            raise ValueError(
                "configured COO operator alias must be read-only and use the "
                "reviewed depth-one docs-MCP native-helper App Server profile"
            )
        binding = {
            "eligible_quota_classes": sorted(
                {
                    self.config.coo_quota_class,
                    self.config.coo_default_quota_class,
                }
            ),
            "provider": alias.provider_alias,
            "model": alias.model,
            "effort": alias.effort,
            "cost_class": alias.cost_class,
            "base_sha": self.config.proof_base_sha,
            "routing_policy_version": router.policy_version,
            "execution_profile_id": alias.execution_profile_id,
            "execution_profile_digest": alias.execution_profile_digest,
            "capability_policy_version": alias.capability_policy_version,
            "capability_policy_digest": alias.capability_policy_digest,
            "operator_eligible_quota_classes": [
                self.config.coo_operator_quota_class
            ],
            "operator_provider": operator_alias.provider_alias,
            "operator_model": operator_alias.model,
            "operator_effort": operator_alias.effort,
            "operator_cost_class": operator_alias.cost_class,
            "operator_routing_policy_version": router.policy_version,
            "operator_execution_profile_id": operator_alias.execution_profile_id,
            "operator_execution_profile_digest": (
                operator_alias.execution_profile_digest
            ),
            "operator_capability_policy_version": (
                operator_alias.capability_policy_version
            ),
            "operator_capability_policy_digest": (
                operator_alias.capability_policy_digest
            ),
            "operator_harness_binary_digest": (
                self.config.operator_harness_binary_digest
            ),
            "operator_harness_version": self.config.operator_harness_version,
            "operator_harness_armed": self.config.coo_operator_harness_armed,
        }
        if set(binding) != set(V2_HOST_EXECUTION_BINDING_KEYS):
            raise ValueError("configured COO host binding fields drifted")
        return binding

    def _require_current_coo_binding(self) -> dict[str, Any]:
        current = self._load_coo_execution_binding()
        if current != self._coo_execution_binding:
            raise ServiceError("installed COO routing/capability policy drifted")
        return dict(current)

    @property
    def ceo_ingress_socket_path(self) -> Path | None:
        return self._ceo_ingress_socket_path

    @property
    def ceo_ingress_armed(self) -> bool:
        return self._ceo_ingress_armed

    @property
    def ceo_ingress_ready(self) -> bool:
        """The R1/R2 in-memory startup latch — true only after BOTH listeners
        have started serving in dual-listener mode."""

        return self._ceo_ingress_ready

    @property
    def socket_path(self) -> Path:
        return self.config.socket_path

    @property
    def runtime_state_dir(self) -> Path:
        return self.config.runtime_root / "data" / "control_plane"

    @property
    def service_lock_path(self) -> Path:
        return self.runtime_state_dir / "executive-service.lock"

    @property
    def running_marker_path(self) -> Path:
        return self.runtime_state_dir / "executive-service.running"

    def _require_runtime(self) -> Runtime:
        if self.runtime is None:
            raise ServiceError("Executive control service is not started")
        return self.runtime

    def _require_supervisor(self) -> SupervisorProtocol:
        if self.supervisor is None:
            raise ServiceError("Executive supervisor is not configured")
        return self.supervisor

    def _require_operator_supervisor(self) -> OperatorSupervisorProtocol:
        if self.operator_supervisor is None:
            raise ServiceError("Executive Operator Harness supervisor is not configured")
        return self.operator_supervisor

    async def activate_canary(self, verdict: Mapping[str, Any]) -> None:
        """Leave bootstrap quarantine without changing the live launchd PID."""

        if self._service_state != "AWAITING_CANARY":
            raise ServiceError("Executive control service is not awaiting a canary")
        from control_plane.codex_worker import validate_secret_canary_verdict

        validated = validate_secret_canary_verdict(verdict, require_passed=True)
        supervisor = self._require_supervisor()
        if not hasattr(supervisor, "secret_canary_verdict") or not hasattr(
            supervisor, "require_complete_launch_attestation"
        ):
            raise ServiceError("Executive supervisor cannot activate a complete canary")
        supervisor.secret_canary_verdict = validated
        supervisor.require_complete_launch_attestation = True
        self._startup_reconciliation = await asyncio.to_thread(
            supervisor.reconcile_restart,
            requeue_lost=False,
        )
        self._service_state = "READY"

    def _acquire_service_lock(self) -> None:
        self.runtime_state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        directory_info = self.runtime_state_dir.lstat()
        if (
            not stat.S_ISDIR(directory_info.st_mode)
            or stat.S_ISLNK(directory_info.st_mode)
            or directory_info.st_uid != os.geteuid()
        ):
            raise ServiceError("Executive runtime state directory is not owner-only")
        self.runtime_state_dir.chmod(0o700)
        if stat.S_IMODE(self.runtime_state_dir.lstat().st_mode) != 0o700:
            raise ServiceError("Executive runtime state directory is not owner-only")
        lock_path = self.service_lock_path
        flags = os.O_CREAT | os.O_RDWR
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(lock_path, flags, 0o600)
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1
            or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) & 0o077
        ):
            os.close(fd)
            raise ServiceError("Executive service lock is not an owner-only regular file")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            os.close(fd)
            raise ServiceError("another Executive control service holds the socket lock") from exc
        self._lock_fd = fd
        marker_flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        if hasattr(os, "O_NOFOLLOW"):
            marker_flags |= os.O_NOFOLLOW
        temporary = self.runtime_state_dir / (
            f".{self.running_marker_path.name}.{os.getpid()}.{uuid4().hex}.tmp"
        )
        marker_fd = os.open(temporary, marker_flags, 0o600)
        try:
            payload = _canonical_json(
                {"instance_id": self.instance_id, "pid": os.getpid()}
            )
            view = memoryview(payload)
            while view:
                written = os.write(marker_fd, view)
                if written <= 0:  # pragma: no cover - defensive filesystem failure
                    raise OSError("short write while persisting service marker")
                view = view[written:]
            os.fsync(marker_fd)
        finally:
            os.close(marker_fd)
        os.replace(temporary, self.running_marker_path)
        directory = os.open(
            self.runtime_state_dir,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
        )
        try:
            os.fsync(directory)
        finally:
            os.close(directory)

    def _release_service_lock(self) -> None:
        try:
            marker = json.loads(self.running_marker_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, ValueError, TypeError):
            marker = None
        if isinstance(marker, dict) and marker.get("instance_id") == self.instance_id:
            self.running_marker_path.unlink(missing_ok=True)
        if self._lock_fd is not None:
            try:
                fcntl.flock(self._lock_fd, fcntl.LOCK_UN)
            finally:
                os.close(self._lock_fd)
                self._lock_fd = None

    def _prepare_socket(self) -> None:
        self._acquire_service_lock()
        if self._launchd_activated:
            return
        parent = self.socket_path.parent
        parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        parent_info = parent.lstat()
        if (
            not stat.S_ISDIR(parent_info.st_mode)
            or stat.S_ISLNK(parent_info.st_mode)
            or parent_info.st_uid != os.geteuid()
        ):
            self._release_service_lock()
            raise ServiceError("control socket directory is not owned by the service uid")
        parent.chmod(0o700)
        try:
            info = self.socket_path.lstat()
        except FileNotFoundError:
            return
        if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.geteuid():
            self._release_service_lock()
            raise ServiceError("refusing to replace an unowned or non-socket control path")
        self.socket_path.unlink()

    def _database_health(self) -> dict[str, Any]:
        runtime = self._require_runtime()
        with runtime.store.read() as connection:
            quick_check = [str(row[0]) for row in connection.execute("PRAGMA quick_check")]
            foreign_keys = [list(row) for row in connection.execute("PRAGMA foreign_key_check")]
            journal_mode = str(connection.execute("PRAGMA journal_mode").fetchone()[0])
            migrations = [
                {
                    "version": int(row[0]),
                    "name": str(row[1]),
                    "checksum": str(row[2]),
                }
                for row in connection.execute(
                    "SELECT version,name,checksum FROM schema_migrations ORDER BY version"
                )
            ]
        healthy = quick_check == ["ok"] and not foreign_keys and journal_mode.lower() == "wal"
        return {
            "ok": healthy,
            "schema_version": SCHEMA_VERSION,
            "journal_mode": journal_mode,
            "quick_check": quick_check,
            "foreign_key_violations": len(foreign_keys),
            "migrations": migrations,
        }

    def _prepare_ceo_ingress_socket_path(self) -> None:
        """Directory/stale-node preparation for the dedicated CeoIngress path.

        Deliberately does NOT acquire/release the service lock: §8.1 is one
        process / one Runtime / one lock for BOTH listeners, and the single
        lock is already held by ``_prepare_socket()`` earlier in ``start()``.
        A failure here is handled uniformly by ``start()``'s outer
        ``except Exception: await self.close(); raise``.
        """

        assert self._ceo_ingress_socket_path is not None
        parent = self._ceo_ingress_socket_path.parent
        parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        parent_info = parent.lstat()
        if (
            not stat.S_ISDIR(parent_info.st_mode)
            or stat.S_ISLNK(parent_info.st_mode)
            or parent_info.st_uid != os.geteuid()
        ):
            raise ServiceError(
                "CeoIngress control socket directory is not owned by the service uid"
            )
        parent.chmod(0o700)
        try:
            info = self._ceo_ingress_socket_path.lstat()
        except FileNotFoundError:
            return
        if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.geteuid():
            raise ServiceError(
                "refusing to replace an unowned or non-socket CeoIngress control path"
            )
        self._ceo_ingress_socket_path.unlink()

    async def _bind_operator_server(self, *, start_serving: bool) -> None:
        """Construct (bind) the generic Operator listener.

        ``self._server`` is assigned IMMEDIATELY once ``start_unix_server``
        returns — before the activated-socket mode/world-accessible check
        below — so a failure in that check still leaves a real server object
        reachable from ``close()`` rather than leaking an unclosed socket.
        Passing ``start_serving=True`` (the legacy single-listener path)
        reproduces the previous unparameterized call byte-for-byte, since
        that was already asyncio's own default.
        """

        if self._activated_socket is None:
            self._server = await asyncio.start_unix_server(
                self._handle_connection,
                path=str(self.socket_path),
                limit=self.config.max_request_bytes + 1,
                start_serving=start_serving,
            )
            self.socket_path.chmod(0o600)
        else:
            activated, self._activated_socket = self._activated_socket, None
            activated_options: dict[str, Any] = {}
            if sys.version_info >= (3, 13):
                # Python 3.13 added cleanup_socket and otherwise removes the
                # launchd-owned pathname when the asyncio Server closes.
                activated_options["cleanup_socket"] = False
            self._server = await asyncio.start_unix_server(
                self._handle_connection,
                sock=activated,
                limit=self.config.max_request_bytes + 1,
                start_serving=start_serving,
                **activated_options,
            )
            mode = stat.S_IMODE(self.socket_path.stat().st_mode)
            if mode & 0o007:
                raise ServiceError("launchd control socket must not be world-accessible")

    async def _bind_ceo_ingress_server(self, *, start_serving: bool) -> None:
        """Construct (bind) the dedicated CeoIngress listener; see ``_bind_operator_server``."""

        assert self._ceo_ingress_socket_path is not None
        if self._ceo_ingress_activated_socket is None:
            self._prepare_ceo_ingress_socket_path()
            self._ceo_ingress_server = await asyncio.start_unix_server(
                self._handle_ceo_ingress_connection,
                path=str(self._ceo_ingress_socket_path),
                limit=ceo_ingress.MAX_REQUEST_BYTES + 1,
                start_serving=start_serving,
            )
            self._ceo_ingress_socket_path.chmod(0o600)
        else:
            activated, self._ceo_ingress_activated_socket = (
                self._ceo_ingress_activated_socket,
                None,
            )
            activated_options: dict[str, Any] = {}
            if sys.version_info >= (3, 13):
                activated_options["cleanup_socket"] = False
            self._ceo_ingress_server = await asyncio.start_unix_server(
                self._handle_ceo_ingress_connection,
                sock=activated,
                limit=ceo_ingress.MAX_REQUEST_BYTES + 1,
                start_serving=start_serving,
                **activated_options,
            )

    async def _start_ceo_ingress_serving(self) -> None:
        assert self._ceo_ingress_server is not None
        await self._ceo_ingress_server.start_serving()

    async def _start_operator_serving(self) -> None:
        assert self._server is not None
        await self._server.start_serving()

    async def start(self) -> None:
        if self._server is not None:
            raise ServiceError("Executive control service is already started")
        self._closing = False
        self._prepare_socket()
        try:
            self.runtime = self._runtime_factory(self.config.runtime_root)
            health = self._database_health()
            if not health["ok"]:
                raise ServiceError(f"Executive database health check failed: {health!r}")
            if self._supervisor_factory is None:
                raise ServiceError("supervisor_factory is required for startup reconciliation")
            self.supervisor = self._supervisor_factory(self.runtime)
            if self.config.coo_operator_harness_armed:
                if self._operator_supervisor_factory is None:
                    raise ServiceError(
                        "armed COO Operator Harness has no supervisor composition"
                    )
                if self._operator_identity_verifier is None:
                    raise ServiceError(
                        "armed COO Operator Harness has no worker identity verifier"
                    )
                await self._operator_identity_verifier()
                self.operator_supervisor = self._operator_supervisor_factory(
                    self.runtime, self.supervisor
                )
            # Startup reconciliation must never auto-requeue.  LOST work returns
            # to QUEUED only through the explicit requeue command.
            if self._service_state == "READY":
                self._startup_reconciliation = await asyncio.to_thread(
                    self.supervisor.reconcile_restart, requeue_lost=False
                )
                if self.operator_supervisor is not None:
                    self._startup_reconciliation.extend(
                        await asyncio.to_thread(
                            self.operator_supervisor.reconcile_restart,
                            requeue_lost=False,
                        )
                    )
            if self._ceo_ingress_socket_path is not None:
                # R1 §2.1 / R2 §3 atomic dual-listener startup.  Construct/bind
                # BOTH listeners with no-accept first; only then start serving,
                # CeoIngress FIRST while its own startup latch is still false
                # (so a request racing this narrow window gets only
                # ``ingress_unavailable`` and never reaches business
                # parsing/mutation), Operator SECOND.  The startup latch flips
                # true only after BOTH ``start_serving()`` calls succeed.  Any
                # failure anywhere in this block is handled uniformly by the
                # outer ``except Exception: await self.close(); raise`` below,
                # which tears down whichever listener(s) were constructed.
                await self._bind_ceo_ingress_server(start_serving=False)
                await self._bind_operator_server(start_serving=False)
                await self._start_ceo_ingress_serving()
                await self._start_operator_serving()
                self._ceo_ingress_ready = True
            else:
                # Byte-compatible-unchanged: identical to the previous
                # unconditional call (start_serving defaults to True).
                await self._bind_operator_server(start_serving=True)
            # R2 §3: set/update _started_at exactly where the service records
            # successful startup — after BOTH listeners in dual-listener mode
            # (Operator starts second, so this line already runs after both),
            # unchanged single-listener timing otherwise.
            self._started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
            if self.config.coo_autonomy_armed:
                self._coo_shutdown_event = asyncio.Event()
                self._coo_tick_task = asyncio.create_task(
                    self._coo_tick_loop(),
                    name="executive-coo-bounded-tick",
                )
        except Exception:
            await self.close()
            raise

    async def close(self) -> None:
        # R1/R2: the startup latch is process lifecycle only; reset it before
        # anything else so a mid-startup failure or a fresh restart never
        # observes a stale true value.
        self._ceo_ingress_ready = False
        self._closing = True
        if self._coo_shutdown_event is not None:
            self._coo_shutdown_event.set()

        # §14.2 step 1 — stop BOTH listeners first, preventing new
        # connections, before awaiting either one's ``wait_closed()``.  Calling
        # ``.close()`` on both up front (rather than close+await, close+await)
        # is what actually "stops both listeners first": ``.close()`` alone
        # already stops the server from accepting new connections, so doing it
        # for both before either await removes the narrow window in which the
        # second listener could still accept a connection while this coroutine
        # is suspended awaiting the first listener's ``wait_closed()``.
        server, self._server = self._server, None
        ceo_ingress_server, self._ceo_ingress_server = self._ceo_ingress_server, None
        if server is not None:
            server.close()
        if ceo_ingress_server is not None:
            ceo_ingress_server.close()
        if server is not None:
            await server.wait_closed()
        if ceo_ingress_server is not None:
            await ceo_ingress_server.wait_closed()

        coo_tick, self._coo_tick_task = self._coo_tick_task, None
        if coo_tick is not None:
            # A CooCycle action can cross a durable mutation/claim boundary in
            # its worker thread.  Cancellation would not stop that thread, so
            # shutdown drains the one bounded action to a real return point.
            await asyncio.gather(coo_tick, return_exceptions=True)
        self._coo_shutdown_event = None
        current_task = asyncio.current_task()
        coo_actions = [
            task
            for task in self._coo_action_tasks
            if task is not current_task and not task.done()
        ]
        if coo_actions:
            await asyncio.gather(*coo_actions, return_exceptions=True)
        self._coo_action_tasks.clear()

        tasks = [task for task in self._dispatch_tasks.values() if not task.done()]
        runtime = self.runtime
        if runtime is not None:
            for job_id, task in list(self._dispatch_tasks.items()):
                if task.done():
                    continue
                try:
                    job = runtime.jobs.get_job(job_id)
                    if job is not None and job.status in {
                        JobStatus.QUEUED,
                        JobStatus.RUNNING,
                        JobStatus.CHECKPOINTED,
                    }:
                        runtime.jobs.cancel_job(job_id)
                except RuntimeProofError:
                    # Restart reconciliation remains the fail-closed cleanup
                    # path if the shutdown request races a terminal transition.
                    pass
        if tasks:
            _done, pending = await asyncio.wait(
                tasks, timeout=self.config.shutdown_grace_seconds
            )
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
        self._dispatch_tasks.clear()

        # §14.2 — CeoIngress handler tasks are NEVER cancelled here, unlike the
        # dispatch tasks above.  A handler whose sync ``submit_intent`` thread
        # has already started cannot be safely cancelled (cancelling the
        # awaiting coroutine does not cancel the underlying thread/
        # transaction), so ``close()`` waits every already-started handler to
        # a REAL terminal outcome with no grace-period timeout.  The service
        # lock/marker below is not released until this drains.
        ceo_ingress_tasks = [task for task in self._ceo_ingress_tasks if not task.done()]
        if ceo_ingress_tasks:
            await asyncio.gather(*ceo_ingress_tasks, return_exceptions=True)
        self._ceo_ingress_tasks.clear()

        if not self._launchd_activated:
            try:
                info = self.socket_path.lstat()
            except FileNotFoundError:
                pass
            else:
                if stat.S_ISSOCK(info.st_mode):
                    self.socket_path.unlink()
        if self._ceo_ingress_socket_path is not None and not self._ceo_ingress_launchd_activated:
            try:
                info = self._ceo_ingress_socket_path.lstat()
            except FileNotFoundError:
                pass
            else:
                if stat.S_ISSOCK(info.st_mode):
                    self._ceo_ingress_socket_path.unlink()
        self._release_service_lock()

    async def serve_until_stopped(self) -> None:
        await self.start()
        stopped = asyncio.Event()
        loop = asyncio.get_running_loop()
        installed: list[signal.Signals] = []
        for value in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(value, stopped.set)
                installed.append(value)
            except (NotImplementedError, RuntimeError):  # pragma: no cover - non-main loop
                continue
        try:
            await stopped.wait()
        finally:
            for value in installed:
                loop.remove_signal_handler(value)
            await self.close()

    def _allowed_peer_uids(self) -> set[int]:
        configured = {int(value) for value in self.config.allowed_peer_uids}
        return configured or {os.geteuid()}

    async def _handle_connection(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        try:
            connection = writer.get_extra_info("socket")
            if connection is None:
                raise ServiceError("control connection has no local socket identity")
            try:
                peer = _peer_uid(connection)
            except OSError:
                await self._send_error(
                    writer,
                    "peer_credentials_unavailable",
                    "kernel peer credentials could not be read",
                )
                return
            if peer is None:
                await self._send_error(
                    writer,
                    "peer_credentials_unavailable",
                    "platform exposes no trusted local peer uid",
                )
                return
            if peer not in self._allowed_peer_uids():
                await self._send_error(writer, "peer_denied", "peer uid is not authorized")
                return
            try:
                raw = await reader.readuntil(b"\n")
            except asyncio.LimitOverrunError:
                await self._send_error(writer, "request_too_large", "request exceeds byte limit")
                return
            except asyncio.IncompleteReadError as exc:
                raw = exc.partial
            if not raw or len(raw) > self.config.max_request_bytes:
                await self._send_error(writer, "request_too_large", "request exceeds byte limit")
                return
            try:
                request = json.loads(raw.decode("utf-8", errors="strict"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                await self._send_error(writer, "invalid_json", "request is not valid UTF-8 JSON")
                return
            try:
                result = await self._dispatch_request(request)
            except (RuntimeProofError, ValueError) as exc:
                await self._send_error(writer, "request_failed", str(exc)[:1000])
                return
            except WorkspaceError as exc:
                # WorkspaceError is a bare RuntimeError (see
                # control_plane/executive_workspace.py) so it is not a
                # RuntimeProofError/ValueError and does not match the branch
                # above; it is also not a subclass of RuntimeProofError or
                # ValueError, so that branch is not a subclass of this one
                # either. The two clauses are mutually exclusive by type, so
                # their relative order cannot change which one a given
                # exception hits -- only "before the generic `except
                # Exception` below" is load-bearing. Reuse the existing
                # `request_failed` code (no new wire contract) but sanitize
                # the reason first: workspace text originates outside this
                # process (paths, git/codex command output) and must not
                # cross the socket unredacted or unbounded.
                reason = sanitize_external_text(str(exc), limit=1000)
                await self._send_error(
                    writer,
                    "request_failed",
                    reason or "workspace preparation failed",
                )
                return
            except Exception as exc:  # fail closed without a traceback or local paths
                await self._send_error(
                    writer,
                    "internal_error",
                    f"{type(exc).__name__}: Executive request failed",
                )
                return
            await self._send(writer, {"ok": True, "result": result})
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except _CLIENT_GONE:
                pass

    async def _send_error(self, writer: asyncio.StreamWriter, code: str, message: str) -> None:
        await self._send(writer, {"ok": False, "error": {"code": code, "message": message}})

    async def _send(self, writer: asyncio.StreamWriter, payload: Mapping[str, Any]) -> None:
        raw = _canonical_json(payload)
        if len(raw) > self.config.max_response_bytes:
            raw = _canonical_json(
                {
                    "ok": False,
                    "error": {
                        "code": "response_too_large",
                        "message": "response exceeds byte limit",
                    },
                }
            )
        try:
            writer.write(raw)
            await writer.drain()
        except _CLIENT_GONE:
            # Delivery path only: the peer disconnected while this reply was in
            # flight.  Nothing the service decided changes, and the caller's
            # `finally` still tears the connection down.
            return

    # -----------------------------------------------------------------
    # MAS-75 PR-A: dedicated CeoIngress connection handling
    # -----------------------------------------------------------------

    def _ceo_ingress_ready_for_admission(self) -> bool:
        """R2 §5 final readiness predicate (minus the always-true "this
        service instance/lock is valid" clause, which holds trivially while
        the service itself is running): the startup latch, the host-owned
        arming decision, and the current service-state allowlist.  Every
        other/future/dynamic state (including ``QUARANTINED``) refuses.
        Arming this predicate never changes ``_service_state``, clears
        quarantine, or touches any worker/provider/broker.
        """

        return (
            self._ceo_ingress_ready
            and self._ceo_ingress_armed
            and self._service_state in {"READY", "AWAITING_CANARY"}
        )

    async def _send_ceo_ingress_response(
        self, writer: asyncio.StreamWriter, payload: Mapping[str, Any]
    ) -> None:
        """Dedicated bounded sender (§7.4) — the 32 KiB ingress ceiling, never
        the generic ``_send()``'s ``ServiceConfig.max_response_bytes``.  A
        successful canonical receipt above the ingress bound is a protocol/
        backend defect and refuses; it is never truncated."""

        raw = _canonical_json(payload)
        if len(raw) > ceo_ingress.MAX_RESPONSE_BYTES:
            raw = _canonical_json(
                {
                    "ok": False,
                    "error": {
                        "code": "response_too_large",
                        "message": "response exceeds byte limit",
                    },
                }
            )
        try:
            writer.write(raw)
            await writer.drain()
        except _CLIENT_GONE:
            return

    async def _send_ceo_ingress_error(
        self, writer: asyncio.StreamWriter, code: str, message: str
    ) -> None:
        await self._send_ceo_ingress_response(
            writer, {"ok": False, "error": {"code": code, "message": message}}
        )

    async def _handle_ceo_ingress_connection(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        """The dedicated CeoIngress protocol handler (§7, §8, R1 §2).

        Peer identity is authenticated against the ONE exact configured
        ingress peer uid — separate from the generic Operator
        ``allowed_peer_uids`` set — before any body read/parsing.  There is no
        generic dispatcher on this path: everything past peer authentication
        and the startup-readiness gate is delegated to
        ``executive_ceo_ingress.handle_frame``, which owns the three closed
        submit/status/state frame validators and typed error law.  Exactly one
        frame is read and one response is written per connection (§7.3).
        """

        task = asyncio.current_task()
        if task is not None:
            # §14.1: register on entry.  Removed in ``finally`` only once this
            # handler's admission/readback and response cleanup reaches the
            # real terminal point — a client disconnect does not remove it
            # while a canonical mutation is running.
            self._ceo_ingress_tasks.add(task)
        try:
            connection = writer.get_extra_info("socket")
            if connection is None:
                await self._send_ceo_ingress_error(
                    writer,
                    "peer_credentials_unavailable",
                    "control connection has no local socket identity",
                )
                return
            try:
                peer = _peer_uid(connection)
            except OSError:
                await self._send_ceo_ingress_error(
                    writer,
                    "peer_credentials_unavailable",
                    "kernel peer credentials could not be read",
                )
                return
            if peer is None:
                await self._send_ceo_ingress_error(
                    writer,
                    "peer_credentials_unavailable",
                    "platform exposes no trusted local peer uid",
                )
                return
            if peer != self._ceo_ingress_peer_uid:
                await self._send_ceo_ingress_error(
                    writer, "peer_denied", "peer uid is not authorized"
                )
                return
            # R1 §2.1 + R0 §4.2: startup remains refusal-only before ANY body
            # read.  Once both listeners are ready, exact-peer callers may
            # supply one bounded frame so R0 can identify the diagnostic state
            # schema.  PR-A submit/status still receive the unchanged full
            # admission predicate after schema discrimination and before any
            # grounding/business/ceo_intent call.
            if not self._ceo_ingress_ready:
                await self._send_ceo_ingress_error(
                    writer,
                    "ingress_unavailable",
                    "Executive CEO ingress is not currently admitting requests",
                )
                return
            try:
                raw = await reader.readuntil(b"\n")
            except asyncio.LimitOverrunError:
                await self._send_ceo_ingress_error(
                    writer, "request_too_large", "request exceeds byte limit"
                )
                return
            except asyncio.IncompleteReadError:
                # §7.3: EOF before newline is an incomplete/refused frame even
                # if the partial bytes would parse as valid JSON.
                await self._send_ceo_ingress_error(
                    writer, "invalid_json", "request frame is incomplete"
                )
                return
            # NIT 15b: unlike the generic Operator path (which falls through to
            # here with ``raw = exc.partial`` on ``IncompleteReadError`` and so
            # can reach this point with an empty ``raw``), BOTH exception
            # branches above ``return`` early; the only way to reach this line
            # is ``readuntil(b"\n")`` returning normally, which always yields
            # at least the separator byte.  ``not raw`` is therefore
            # unreachable here and is intentionally omitted (verified by
            # grepping both except clauses above: neither falls through).
            if len(raw) > ceo_ingress.MAX_REQUEST_BYTES:
                await self._send_ceo_ingress_error(
                    writer, "request_too_large", "request exceeds byte limit"
                )
                return
            try:
                text = raw.decode("utf-8", errors="strict")
            except UnicodeDecodeError:
                await self._send_ceo_ingress_error(
                    writer, "invalid_json", "request is not valid UTF-8"
                )
                return
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                await self._send_ceo_ingress_error(
                    writer, "invalid_json", "request is not valid JSON"
                )
                return
            if (
                isinstance(parsed, Mapping)
                and parsed.get("schema")
                in {ceo_ingress.SUBMIT_SCHEMA, ceo_ingress.STATUS_SCHEMA}
                and not self._ceo_ingress_ready_for_admission()
            ):
                await self._send_ceo_ingress_error(
                    writer,
                    "ingress_unavailable",
                    "Executive CEO ingress is not currently admitting requests",
                )
                return
            try:
                result = await ceo_ingress.handle_frame(
                    parsed,
                    runtime=self._require_runtime(),
                    grounding_provider=self._ceo_ingress_grounding_provider,
                    workspace_root=self.config.proof_workspace_root,
                    service_state=self._service_state,
                    ceo_ingress_armed=self._ceo_ingress_armed,
                )
            except ceo_ingress.CeoIngressError as exc:
                await self._send_ceo_ingress_error(writer, exc.code, exc.message)
                return
            except Exception:  # fail closed without a traceback or local paths
                await self._send_ceo_ingress_error(
                    writer, "internal_error", "Executive CEO ingress failed"
                )
                return
            await self._send_ceo_ingress_response(writer, {"ok": True, "result": result})
        finally:
            # §14.1 — remove the task from the drain set only AFTER its
            # admission/readback and response cleanup (writer close/drain)
            # reaches the real terminal point, so ``close()``'s drain-set wait
            # cannot observe this handler as "done" while its writer is still
            # being torn down.
            writer.close()
            try:
                await writer.wait_closed()
            except _CLIENT_GONE:
                pass
            if task is not None:
                self._ceo_ingress_tasks.discard(task)

    @staticmethod
    def _request(request: Any) -> tuple[str, dict[str, Any]]:
        if not isinstance(request, dict) or set(request) != {"version", "command", "args"}:
            raise ValueError("request must contain exactly version, command, and args")
        if request["version"] != CONTROL_PROTOCOL_VERSION:
            raise ValueError("unsupported control protocol version")
        command = request["command"]
        args = request["args"]
        if not isinstance(command, str) or not command:
            raise ValueError("command must be a non-empty string")
        if not isinstance(args, dict):
            raise ValueError("args must be an object")
        return command, args

    @staticmethod
    def _exact_args(args: Mapping[str, Any], expected: set[str]) -> None:
        if set(args) != expected:
            rendered = ", ".join(sorted(expected)) or "none"
            raise ValueError(f"command requires exactly these arguments: {rendered}")

    @staticmethod
    def _id(value: Any, name: str) -> str:
        if not isinstance(value, str) or _ID_RE.fullmatch(value) is None:
            raise ValueError(f"invalid {name}")
        return value

    def _proof_contract(self, *, workspace: Path, branch: str) -> dict[str, Any]:
        return {
            "objective": _PROOF_OBJECTIVE,
            "department": "executive-infrastructure",
            "priority": 0,
            "authority_level": "A0",
            "branch": branch,
            "worktree": str(workspace),
            "constraints": {
                "provider": self.config.provider,
                "model": self.config.model,
                "effort": self.config.effort,
                "cost_class": self.config.cost_class,
                "base_sha": self.config.proof_base_sha,
                "required_capabilities": ["code", "research", "tests"],
                "eligible_quota_classes": [self.config.quota_class],
            },
            "attempt_limit": 3,
            "requested_authorities": ["READ", "RESEARCH", "RUN_TESTS", "WRITE_BRANCH"],
            "allowed_write_paths": [_PROOF_ARTIFACT],
            "validation_commands": [list(_PROOF_VALIDATION)],
        }

    def _is_fixed_proof_job(self, job: Job) -> bool:
        if job.worktree is None or job.branch is None:
            return False
        workspace = Path(job.worktree)
        if not workspace.is_absolute() or workspace.parent != self.config.proof_workspace_root:
            return False
        match = _PROOF_WORKSPACE_RE.fullmatch(workspace.name)
        if match is None:
            return False
        nonce = match.group(1)
        if job.branch != f"{self.config.proof_branch}-{nonce}":
            return False
        expected = self._proof_contract(workspace=workspace, branch=job.branch)
        return (
            job.objective == expected["objective"]
            and job.department == expected["department"]
            and job.priority == expected["priority"]
            and job.authority_level == expected["authority_level"]
            and job.branch == expected["branch"]
            and job.worktree == expected["worktree"]
            and job.constraints == expected["constraints"]
            and job.attempt_limit == expected["attempt_limit"]
            and job.requested_authorities == expected["requested_authorities"]
            and job.allowed_write_paths == expected["allowed_write_paths"]
            and job.validation_commands == expected["validation_commands"]
        )

    def _register_worker(self) -> Any:
        runtime = self._require_runtime()
        binding = self._require_current_coo_binding()
        router = ModelRouter.load()
        alias = router.model_aliases[self.config.coo_model_alias]
        operator_alias = router.model_aliases[self.config.coo_operator_model_alias]
        coo_capabilities = list(alias.capabilities)
        operator_capabilities = list(operator_alias.capabilities)
        coo_metadata = {
            "service_managed": True,
            "purpose": "executive-coo-cycle",
            "model_alias": self.config.coo_model_alias,
            "routing_policy_version": binding["routing_policy_version"],
            "execution_profile_id": binding["execution_profile_id"],
            "execution_profile_digest": binding["execution_profile_digest"],
            "capability_policy_version": binding["capability_policy_version"],
            "capability_policy_digest": binding["capability_policy_digest"],
        }
        coo_default_metadata = dict(coo_metadata)
        coo_default_metadata.pop("model_alias", None)
        coo_default_metadata["capacity_variant"] = "default"
        operator_metadata = {
            "service_managed": True,
            "purpose": "executive-coo-operator-planner",
            "model_alias": self.config.coo_operator_model_alias,
            "routing_policy_version": binding[
                "operator_routing_policy_version"
            ],
            "execution_profile_id": binding[
                "operator_execution_profile_id"
            ],
            "execution_profile_digest": binding[
                "operator_execution_profile_digest"
            ],
            "capability_policy_version": binding[
                "operator_capability_policy_version"
            ],
            "capability_policy_digest": binding[
                "operator_capability_policy_digest"
            ],
            "harness_binary_digest": binding["operator_harness_binary_digest"],
            "harness_version": binding["operator_harness_version"],
        }
        proof_capabilities = ["code", "research", "tests"]
        existing = runtime.workers.get_worker(self.config.worker_id)
        if existing is not None:
            quota = runtime.workers.get_quota_class(
                self.config.worker_id, self.config.quota_class
            )
            if (
                existing.provider != self.config.provider
                or existing.account_label != self.config.worker_account_label
                or existing.worker_type != self.config.worker_type
                or quota is None
                or quota.provider != self.config.provider
                or quota.model != self.config.model
                or quota.effort != self.config.effort
                or quota.cost_class != self.config.cost_class
                or quota.capabilities != proof_capabilities
            ):
                raise StateConflict("configured worker identity already exists with different policy")
            runtime.workers.register_quota_class(
                self.config.worker_id,
                self.config.coo_quota_class,
                provider=str(binding["provider"]),
                model=str(binding["model"]),
                effort=str(binding["effort"]),
                cost_class=str(binding["cost_class"]),
                capabilities=coo_capabilities,
                metadata=coo_metadata,
            )
            runtime.workers.register_quota_class(
                self.config.worker_id,
                self.config.coo_default_quota_class,
                provider=str(binding["provider"]),
                model=str(binding["model"]),
                effort=str(binding["effort"]),
                cost_class="default",
                capabilities=coo_capabilities,
                metadata=coo_default_metadata,
            )
            if self.config.coo_operator_harness_armed:
                runtime.workers.register_quota_class(
                    self.config.worker_id,
                    self.config.coo_operator_quota_class,
                    provider=str(binding["operator_provider"]),
                    model=str(binding["operator_model"]),
                    effort=str(binding["operator_effort"]),
                    cost_class=str(binding["operator_cost_class"]),
                    capabilities=operator_capabilities,
                    metadata=operator_metadata,
                )
            refreshed = runtime.workers.get_worker(self.config.worker_id)
            assert refreshed is not None
            return refreshed
        return runtime.workers.register_worker(
            self.config.worker_id,
            provider=self.config.provider,
            account_label=self.config.worker_account_label,
            worker_type=self.config.worker_type,
            capabilities=sorted(
                set(proof_capabilities)
                | set(coo_capabilities)
                | (
                    set(operator_capabilities)
                    if self.config.coo_operator_harness_armed
                    else set()
                )
            ),
            quota_classes={
                self.config.quota_class: {
                    "provider": self.config.provider,
                    "model": self.config.model,
                    "effort": self.config.effort,
                    "cost_class": self.config.cost_class,
                    "capabilities": proof_capabilities,
                },
                self.config.coo_quota_class: {
                    "provider": binding["provider"],
                    "model": binding["model"],
                    "effort": binding["effort"],
                    "cost_class": binding["cost_class"],
                    "capabilities": coo_capabilities,
                    "metadata": coo_metadata,
                },
                self.config.coo_default_quota_class: {
                    "provider": binding["provider"],
                    "model": binding["model"],
                    "effort": binding["effort"],
                    "cost_class": "default",
                    "capabilities": coo_capabilities,
                    "metadata": coo_default_metadata,
                },
                **(
                    {
                        self.config.coo_operator_quota_class: {
                            "provider": binding["operator_provider"],
                            "model": binding["operator_model"],
                            "effort": binding["operator_effort"],
                            "cost_class": binding["operator_cost_class"],
                            "capabilities": operator_capabilities,
                            "metadata": operator_metadata,
                        }
                    }
                    if self.config.coo_operator_harness_armed
                    else {}
                ),
            },
            metadata={"service_managed": True},
        )

    async def _create_proof_job(self) -> Job:
        """Create one fresh exact-SHA, no-remote workspace for one proof Job."""

        runtime = self._require_runtime()
        async with self._workspace_lock:
            if any(not task.done() for task in self._dispatch_tasks.values()):
                raise StateConflict(
                    "cannot create a sibling proof workspace while a worker dispatch is active"
                )
            if runtime.workers.get_worker(self.config.worker_id) is None:
                raise StateConflict(
                    "register the configured Codex worker before creating proof work"
                )
            nonce = uuid4().hex
            workspace_name = f"proof-{nonce}"
            branch = f"{self.config.proof_branch}-{nonce}"
            receipt = await asyncio.to_thread(
                prepare_credentialless_clone,
                self.config.proof_source_repository,
                self.config.proof_workspace_root,
                job_id=workspace_name,
                base_sha=self.config.proof_base_sha,
                branch=branch,
                shared_gid=self.config.proof_shared_gid,
                shared_write_paths=(
                    (_PROOF_ARTIFACT,) if self.config.proof_shared_gid is not None else ()
                ),
            )
            workspace = Path(receipt.workspace_path)
            if (
                workspace.parent != self.config.proof_workspace_root
                or workspace.name != workspace_name
                or receipt.base_sha != self.config.proof_base_sha
                or receipt.branch != branch
                or receipt.remote_count != 0
            ):
                raise ServiceError("prepared proof workspace receipt drifted from policy")
            # The registry allocates the durable Job id.  The unguessable
            # service-created workspace/branch pair is persisted with that Job
            # and is the fixed proof identity checked again at dispatch.
            return runtime.jobs.create_job(
                **self._proof_contract(workspace=workspace, branch=branch)
            )

    @staticmethod
    def _path_exists(path: Path) -> bool:
        try:
            path.lstat()
        except FileNotFoundError:
            return False
        return True

    @staticmethod
    def _fsync_directory(path: Path) -> None:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    @staticmethod
    def _ensure_private_directory(path: Path) -> None:
        try:
            path.mkdir(mode=0o700)
        except FileExistsError:
            pass
        info = path.lstat()
        if (
            not stat.S_ISDIR(info.st_mode)
            or stat.S_ISLNK(info.st_mode)
            or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) & 0o077
        ):
            raise ServiceError(
                "workspace rotation receipt directory must be control-owned and owner-only"
            )

    def _observe_git(self, workspace: Path, arguments: list[str]) -> bytes:
        """Post-handoff observation-only Git. Mutation argv is refused here."""

        requested = tuple(arguments)
        if requested not in _SERVICE_GIT_OBSERVATION_ALLOWLIST:
            raise ServiceError(
                "proof workspace Git observer refuses mutating or unaudited operations"
            )
        home = self.config.proof_workspace_root / ".supervisor-home"
        environment = git_observation_env(
            {
                "PATH": "/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin:/opt/homebrew/bin",
                "HOME": str(home),
                "LANG": "C.UTF-8",
                "LC_ALL": "C.UTF-8",
                "TZ": "UTC",
                "GIT_CONFIG_GLOBAL": "/dev/null",
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_TERMINAL_PROMPT": "0",
                "GCM_INTERACTIVE": "never",
            }
        )
        try:
            completed = subprocess.run(
                ["git", "-C", str(workspace), *arguments],
                env=environment,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise ServiceError(f"proof workspace Git observation failed: {exc}") from exc
        if completed.returncode != 0:
            detail = completed.stderr.decode("utf-8", errors="replace").strip()[-500:]
            raise ServiceError(
                f"proof workspace Git observation failed ({completed.returncode}): {detail}"
            )
        return completed.stdout

    def _require_shared_git_handoff(self, workspace: Path) -> None:
        if self.config.proof_shared_gid is None:
            return
        try:
            validate_shared_git_handoff(
                workspace,
                control_uid=os.geteuid(),
                shared_gid=int(self.config.proof_shared_gid),
            )
        except GitHandoffError as exc:
            raise ServiceError(str(exc)) from exc

    def _workspace_observation(
        self,
        workspace: Path,
        *,
        require_fresh: bool,
        expected_branch: str,
    ) -> dict[str, Any]:
        info = workspace.lstat()
        if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
            raise ServiceError("proof workspace must be a real directory")
        head = self._observe_git(
            workspace, ["rev-parse", "--verify", "HEAD^{commit}"]
        ).decode("ascii", errors="strict").strip()
        branch = self._observe_git(
            workspace, ["rev-parse", "--abbrev-ref", "HEAD"]
        ).decode("utf-8", errors="strict").strip()
        cleanliness = observe_launch_cleanliness(
            lambda arguments: self._observe_git(workspace, list(arguments))
        )
        remotes = tuple(
            value
            for value in self._observe_git(workspace, ["remote"])
            .decode("utf-8", errors="strict")
            .splitlines()
            if value
        )
        if require_fresh and (
            head != self.config.proof_base_sha
            or branch != expected_branch
            or cleanliness.dirty
            or remotes
        ):
            raise ServiceError(
                "replacement proof workspace is not clean, exact-SHA, branch-bound, and no-remote"
            )
        if require_fresh:
            self._require_shared_git_handoff(workspace)
        return {
            "path": str(workspace),
            "device": int(info.st_dev),
            "inode": int(info.st_ino),
            "uid": int(info.st_uid),
            "gid": int(info.st_gid),
            "mode": stat.S_IMODE(info.st_mode),
            "head": head,
            "branch": branch,
            "status_sha256": hashlib.sha256(cleanliness.status).hexdigest(),
            "status_dirty": bool(cleanliness.status),
            "all_untracked_sha256": hashlib.sha256(
                cleanliness.all_untracked
            ).hexdigest(),
            "all_untracked_dirty": bool(cleanliness.all_untracked),
            "launch_clean": not cleanliness.dirty,
            "remote_count": len(remotes),
        }

    def _persist_rotation_receipt(
        self, receipt_path: Path, payload: Mapping[str, Any]
    ) -> tuple[dict[str, Any], str]:
        raw = _canonical_json(payload)
        temporary = receipt_path.with_name(
            f".{receipt_path.name}.{os.getpid()}.{uuid4().hex}.tmp"
        )
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(temporary, flags, 0o600)
        try:
            view = memoryview(raw)
            while view:
                written = os.write(descriptor, view)
                if written <= 0:  # pragma: no cover - defensive filesystem failure
                    raise OSError("short write while persisting workspace rotation receipt")
                view = view[written:]
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        try:
            # The receipt directory is private to the control UID.  A hard-link
            # publishes the fully fsynced bytes atomically and refuses overwrite.
            os.link(temporary, receipt_path, follow_symlinks=False)
        finally:
            temporary.unlink(missing_ok=True)
        self._fsync_directory(receipt_path.parent)
        return dict(payload), hashlib.sha256(raw).hexdigest()

    def _read_rotation_receipt(
        self,
        receipt_path: Path,
        *,
        job: Job,
        attempt_id: str,
        workspace: Path,
        archive_path: Path,
    ) -> tuple[dict[str, Any], str]:
        info = receipt_path.lstat()
        if (
            not stat.S_ISREG(info.st_mode)
            or stat.S_ISLNK(info.st_mode)
            or info.st_nlink != 1
            or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) & 0o077
        ):
            raise ServiceError("workspace rotation receipt is not an owner-only regular file")
        raw = receipt_path.read_bytes()
        try:
            payload = json.loads(raw.decode("utf-8", errors="strict"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ServiceError("workspace rotation receipt is invalid JSON") from exc
        if not isinstance(payload, dict) or (
            payload.get("schema_version") != _WORKSPACE_ROTATION_SCHEMA
            or payload.get("job_id") != job.job_id
            or payload.get("attempt_id") != attempt_id
            or payload.get("previous_status") != job.status.value
            or payload.get("workspace_path") != str(workspace)
            or payload.get("archive_path") != str(archive_path)
        ):
            raise ServiceError("workspace rotation receipt identity drifted")
        return payload, hashlib.sha256(raw).hexdigest()

    @staticmethod
    def _observation_matches_receipt(
        observed: Mapping[str, Any], recorded: Any
    ) -> bool:
        if not isinstance(recorded, dict):
            return False
        return all(recorded.get(key) == value for key, value in observed.items())

    def _rotate_proof_workspace(self, job: Job) -> dict[str, Any]:
        """Archive an interrupted attempt and recreate its exact persisted path."""

        runtime = self._require_runtime()
        if job.status not in {JobStatus.LOST, JobStatus.FAILED, JobStatus.RATE_LIMITED}:
            raise StateConflict(f"job {job.job_id} cannot requeue from {job.status.value}")
        attempt_id = job.current_attempt_id
        if attempt_id is None or _ID_RE.fullmatch(attempt_id) is None:
            raise StateConflict("proof requeue requires one terminal current attempt")
        attempt = runtime.attempts.get_attempt(attempt_id)
        if attempt is None or attempt.job_id != job.job_id:
            raise StateConflict("proof requeue lost its terminal attempt identity")
        if job.worktree is None or job.branch is None:
            raise StateConflict("proof requeue lost its workspace identity")
        workspace = Path(job.worktree)
        root = self.config.proof_workspace_root
        if workspace.parent != root or _PROOF_WORKSPACE_RE.fullmatch(workspace.name) is None:
            raise StateConflict("proof requeue workspace escaped its configured root")
        workspace_info = workspace.lstat()
        if (
            not stat.S_ISDIR(workspace_info.st_mode)
            or stat.S_ISLNK(workspace_info.st_mode)
            or workspace_info.st_uid != os.geteuid()
            or stat.S_IMODE(workspace_info.st_mode) != 0o700
        ):
            raise ServiceError(
                "proof requeue requires a control-owned sealed prior workspace"
            )
        root_info = root.lstat()
        if (
            not stat.S_ISDIR(root_info.st_mode)
            or stat.S_ISLNK(root_info.st_mode)
            or root_info.st_uid != os.geteuid()
            or stat.S_IMODE(root_info.st_mode) & 0o007
            or stat.S_IMODE(root_info.st_mode) & 0o020
        ):
            raise ServiceError("proof workspace root is not control-owned and protected")

        rotation_root = root / ".lost-attempts"
        self._ensure_private_directory(rotation_root)
        job_archive_root = rotation_root / job.job_id
        self._ensure_private_directory(job_archive_root)
        archive_path = job_archive_root / attempt_id
        receipt_path = job_archive_root / f"{attempt_id}.rotation.json"
        archive_exists = self._path_exists(archive_path)
        receipt_exists = self._path_exists(receipt_path)
        workspace_exists = self._path_exists(workspace)

        if receipt_exists:
            if not archive_exists or not workspace_exists:
                raise ServiceError("completed workspace rotation lost archived or replacement data")
            payload, receipt_sha256 = self._read_rotation_receipt(
                receipt_path,
                job=job,
                attempt_id=attempt_id,
                workspace=workspace,
                archive_path=archive_path,
            )
            old_observed = self._workspace_observation(
                archive_path, require_fresh=False, expected_branch=job.branch
            )
            old_observed["path"] = str(workspace)
            new_observed = self._workspace_observation(
                workspace, require_fresh=True, expected_branch=job.branch
            )
            if not self._observation_matches_receipt(
                old_observed, payload.get("old_workspace")
            ) or not self._observation_matches_receipt(
                new_observed, payload.get("new_workspace")
            ):
                raise ServiceError("workspace rotation evidence no longer matches its receipt")
        else:
            if archive_exists:
                old_observed = self._workspace_observation(
                    archive_path, require_fresh=False, expected_branch=job.branch
                )
                old_observed["path"] = str(workspace)
            else:
                if not workspace_exists:
                    raise ServiceError("proof workspace and interrupted evidence are both missing")
                old_observed = self._workspace_observation(
                    workspace, require_fresh=False, expected_branch=job.branch
                )
                os.rename(workspace, archive_path)
                self._fsync_directory(root)
                self._fsync_directory(job_archive_root)

            if not self._path_exists(workspace):
                clone = prepare_credentialless_clone(
                    self.config.proof_source_repository,
                    root,
                    job_id=workspace.name,
                    base_sha=self.config.proof_base_sha,
                    branch=job.branch,
                    shared_gid=self.config.proof_shared_gid,
                    shared_write_paths=(
                        (_PROOF_ARTIFACT,)
                        if self.config.proof_shared_gid is not None
                        else ()
                    ),
                )
                if Path(clone.workspace_path) != workspace:
                    raise ServiceError("replacement workspace path drifted from the durable Job")
            new_observed = self._workspace_observation(
                workspace, require_fresh=True, expected_branch=job.branch
            )
            payload = {
                "schema_version": _WORKSPACE_ROTATION_SCHEMA,
                "job_id": job.job_id,
                "attempt_id": attempt_id,
                "previous_status": job.status.value,
                "rotated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "workspace_path": str(workspace),
                "archive_path": str(archive_path),
                "old_workspace": old_observed,
                "new_workspace": new_observed,
            }
            payload, receipt_sha256 = self._persist_rotation_receipt(
                receipt_path, payload
            )

        event_payload = {
            "schema_version": _WORKSPACE_ROTATION_SCHEMA,
            "receipt_path": str(receipt_path),
            "receipt_sha256": receipt_sha256,
            "archive_path": str(archive_path),
            "workspace_path": str(workspace),
            "old_status_sha256": payload["old_workspace"]["status_sha256"],
            "new_head": payload["new_workspace"]["head"],
        }
        command_id = f"workspace-rotation-{receipt_sha256}"
        with runtime.store.transaction() as connection:
            exists = connection.execute(
                "SELECT 1 FROM events WHERE command_id=?", (command_id,)
            ).fetchone()
            if exists is None:
                runtime.store.append_event(
                    connection,
                    aggregate_type="job",
                    aggregate_id=job.job_id,
                    event_type="PROOF_WORKSPACE_ROTATED",
                    actor="executive-control-service",
                    job_id=job.job_id,
                    attempt_id=attempt_id,
                    payload=event_payload,
                    command_id=command_id,
                )
        return event_payload

    async def _requeue_proof_job(self, job_id: str) -> dict[str, Any]:
        runtime = self._require_runtime()
        async with self._workspace_lock:
            if any(not task.done() for task in self._dispatch_tasks.values()):
                raise StateConflict(
                    "cannot rotate a proof workspace while a worker dispatch is active"
                )
            job = runtime.jobs.get_job(job_id)
            if job is None or not self._is_fixed_proof_job(job):
                raise StateConflict("service requeue accepts only its fixed harmless proof job")
            rotation = await asyncio.to_thread(self._rotate_proof_workspace, job)
            requeued = await asyncio.to_thread(runtime.jobs.requeue_job, job_id)
            result = requeued.to_dict()
            result["workspace_rotation"] = rotation
            return result

    def _submit_service_intent(self, payload: Any) -> dict[str, Any]:
        """Submit through the existing sink with v2 host composition attached."""

        normalized = ceo_intent.validate_intent(payload)
        binding: dict[str, Any] | None = None
        if normalized.get("schema") == ceo_intent.INTENT_SCHEMA_V2:
            if normalized["grounding"].get("mastermind_sha") != self.config.proof_base_sha:
                raise ceo_intent.CeoIntentError(
                    "v2 intent grounding.mastermind_sha differs from the installed reviewed release"
                )
            binding = self._require_current_coo_binding()
        receipt = ceo_intent.submit_intent(
            self._require_runtime(),
            normalized,
            workspace_root=self.config.proof_workspace_root,
            execution_binding=binding,
        )
        if binding is not None:
            job = self._require_runtime().jobs.get_job(str(receipt.get("job_id") or ""))
            if job is None or not self._is_bound_coo_root(job):
                raise ceo_intent.CeoIntentError(
                    "accepted v2 intent is not bound to the current reviewed host profile"
                )
        return receipt

    def _is_bound_coo_root(self, root: Job) -> bool:
        binding = self._require_current_coo_binding()
        provenance = root.orchestration_provenance
        return bool(
            root.parent_job_id is None
            and root.root_job_id == root.job_id
            and root.depth == 0
            and root.orchestration_role == "aggregation"
            and isinstance(provenance, dict)
            and provenance.get("schema_version")
            == "mastermind.executive_orchestration_provenance/v1"
            and provenance.get("creator") == "ceo_intent"
            and provenance.get("job_id") == root.job_id
            and provenance.get("root_job_id") == root.job_id
            and provenance.get("parent_job_id") is None
            and root.worktree is not None
            and root.branch is not None
            and all(root.constraints.get(key) == value for key, value in binding.items())
        )

    def _require_bound_coo_job(self, job: Job) -> Job:
        runtime = self._require_runtime()
        root = runtime.jobs.get_job(job.root_job_id)
        if root is None or not self._is_bound_coo_root(root):
            raise StateConflict("COO dispatch root is not bound to the current host profile")
        if job.job_id != root.job_id and (
            job.parent_job_id != root.job_id
            or job.root_job_id != root.job_id
            or job.depth != 1
            or job.orchestration_role not in {"plan", "work", "review", "repair"}
        ):
            raise StateConflict("COO dispatch target is outside the direct strict-v2 subtree")
        binding = self._require_current_coo_binding()
        if (
            job.orchestration_role == "plan"
            and binding["operator_harness_armed"] is True
        ):
            expected = {
                "eligible_quota_classes": binding[
                    "operator_eligible_quota_classes"
                ],
                "provider": binding["operator_provider"],
                "model": binding["operator_model"],
                "effort": binding["operator_effort"],
                "cost_class": binding["operator_cost_class"],
                "base_sha": binding["base_sha"],
                "routing_policy_version": binding[
                    "operator_routing_policy_version"
                ],
                "execution_profile_id": binding[
                    "operator_execution_profile_id"
                ],
                "execution_profile_digest": binding[
                    "operator_execution_profile_digest"
                ],
                "capability_policy_version": binding[
                    "operator_capability_policy_version"
                ],
                "capability_policy_digest": binding[
                    "operator_capability_policy_digest"
                ],
                "harness_binary_digest": binding[
                    "operator_harness_binary_digest"
                ],
                "harness_version": binding["operator_harness_version"],
            }
        else:
            expected = {
                key: binding[key]
                for key in (
                    "eligible_quota_classes",
                    "provider",
                    "model",
                    "effort",
                    "base_sha",
                    "routing_policy_version",
                    "execution_profile_id",
                    "execution_profile_digest",
                    "capability_policy_version",
                    "capability_policy_digest",
                )
            }
            if job.constraints.get("cost_class") not in {"small", "default"}:
                raise StateConflict(
                    "COO Job cost class has no reviewed serialized capacity"
                )
        for key, value in expected.items():
            if job.constraints.get(key) != value:
                raise StateConflict(f"COO Job host binding drifted at {key}")
        if job.worktree != root.worktree or job.branch != root.branch:
            raise StateConflict("COO Job workspace/branch differs from its strict-v2 root")
        return root

    def _require_coo_workspace(self, job: Job) -> dict[str, Any]:
        root = self._require_bound_coo_job(job)
        assert root.worktree is not None and root.branch is not None
        workspace = Path(root.worktree).resolve(strict=False)
        if workspace.parent != self.config.proof_workspace_root:
            raise StateConflict("COO workspace is not a direct reviewed-root assignment")
        observation = self._workspace_observation(
            workspace,
            require_fresh=False,
            expected_branch=root.branch,
        )
        if observation["branch"] != root.branch or observation["remote_count"] != 0:
            raise ServiceError("COO workspace must remain branch-bound and credentialless")
        if (
            job.orchestration_role == "plan"
            and job.attempt_count == 0
            and (
                observation["head"] != self.config.proof_base_sha
                or observation["launch_clean"] is not True
            )
        ):
            raise ServiceError(
                "initial COO planner requires the clean exact reviewed-base workspace"
            )
        self._require_shared_git_handoff(workspace)
        return observation

    def _require_coo_worker_composed(self) -> None:
        runtime = self._require_runtime()
        binding = self._require_current_coo_binding()
        worker = runtime.workers.get_worker(self.config.worker_id)
        if (
            worker is None
            or worker.provider != binding["provider"]
            or worker.account_label != self.config.worker_account_label
            or worker.worker_type != self.config.worker_type
        ):
            raise StateConflict("reviewed COO worker identity is not registered")
        for quota_name, cost_class in (
            (self.config.coo_quota_class, "small"),
            (self.config.coo_default_quota_class, "default"),
        ):
            quota = runtime.workers.get_quota_class(self.config.worker_id, quota_name)
            if (
                quota is None
                or quota.provider != binding["provider"]
                or quota.model != binding["model"]
                or quota.effort != binding["effort"]
                or quota.cost_class != cost_class
                or any(
                    quota.metadata.get(key) != binding[key]
                    for key in (
                        "routing_policy_version",
                        "execution_profile_id",
                        "execution_profile_digest",
                        "capability_policy_version",
                        "capability_policy_digest",
                    )
                )
                or not set(ModelRouter.load().model_aliases[
                    self.config.coo_model_alias
                ].capabilities).issubset(set(quota.capabilities))
            ):
                raise StateConflict("reviewed COO worker quota identity is unavailable or drifted")
        if self.config.coo_operator_harness_armed:
            operator_quota = runtime.workers.get_quota_class(
                self.config.worker_id, self.config.coo_operator_quota_class
            )
            operator_alias = ModelRouter.load().model_aliases[
                self.config.coo_operator_model_alias
            ]
            if (
                operator_quota is None
                or operator_quota.provider != binding["operator_provider"]
                or operator_quota.model != binding["operator_model"]
                or operator_quota.effort != binding["operator_effort"]
                or operator_quota.cost_class != binding["operator_cost_class"]
                or any(
                    operator_quota.metadata.get(key) != binding[f"operator_{key}"]
                    for key in (
                        "routing_policy_version",
                        "execution_profile_id",
                        "execution_profile_digest",
                        "capability_policy_version",
                        "capability_policy_digest",
                    )
                )
                or operator_quota.metadata.get("harness_binary_digest")
                != binding["operator_harness_binary_digest"]
                or operator_quota.metadata.get("harness_version")
                != binding["operator_harness_version"]
                or not set(operator_alias.capabilities).issubset(
                    set(operator_quota.capabilities)
                )
            ):
                raise StateConflict(
                    "reviewed COO operator quota identity is unavailable or drifted"
                )

    async def _reconcile_unowned_cycle_attempts(self) -> None:
        if any(not task.done() for task in self._dispatch_tasks.values()):
            return
        runtime = self._require_runtime()
        active = [
            attempt
            for attempt in runtime.attempts.list_attempts()
            if attempt.status in _COO_ACTIVE_ATTEMPT_STATUSES
        ]
        if not active:
            return
        receipts = await asyncio.to_thread(
            self._require_supervisor().reconcile_restart,
            requeue_lost=False,
        )
        if self.operator_supervisor is not None:
            receipts.extend(
                await asyncio.to_thread(
                    self.operator_supervisor.reconcile_restart,
                    requeue_lost=False,
                )
            )
        self._startup_reconciliation.extend(receipts)
        ambiguous = [
            receipt
            for receipt in receipts
            if str(getattr(getattr(receipt, "status", None), "value", ""))
            == "IDENTITY_AMBIGUOUS"
        ]
        remaining = [
            attempt
            for attempt in runtime.attempts.list_attempts()
            if attempt.status in _COO_ACTIVE_ATTEMPT_STATUSES
        ]
        if ambiguous or remaining:
            self._service_state = "QUARANTINED"
            raise StateConflict(
                "unowned active Attempt identity could not be reconciled before COO claim"
            )

    async def _dispatch_cycle_job_exact(
        self, job_id: str, command_id: str
    ) -> OrchestrationDispatchOutcome:
        runtime = self._require_runtime()
        async with self._dispatch_lock:
            async with self._workspace_lock:
                live = {
                    value
                    for value, task in self._dispatch_tasks.items()
                    if not task.done()
                }
                if live and live != {job_id}:
                    raise StateConflict("the serialized worker already has another active dispatch")
                job = runtime.jobs.get_job(job_id)
                if job is None:
                    raise StateConflict(f"job {job_id!r} does not exist")
                self._require_bound_coo_job(job)
                if job.status not in {
                    JobStatus.QUEUED,
                    JobStatus.RUNNING,
                    JobStatus.CHECKPOINTED,
                }:
                    raise StateConflict(
                        f"job {job_id} cannot cycle-dispatch from {job.status.value}"
                    )
                if job.status is JobStatus.QUEUED:
                    self._require_coo_workspace(job)
                supervisor: Any = (
                    self._require_operator_supervisor()
                    if (
                        job.orchestration_role == "plan"
                        and self.config.coo_operator_harness_armed
                    )
                    else self._require_supervisor()
                )
                try:
                    started = await supervisor.start_cycle_job(
                        job_id, command_id=command_id
                    )
                except Exception as exc:
                    current = runtime.jobs.get_job(job_id)
                    if current is not None and current.status in {
                        JobStatus.RUNNING,
                        JobStatus.CHECKPOINTED,
                        JobStatus.CANCEL_REQUESTED,
                    }:
                        self._dispatch_errors[job_id] = (
                            f"{type(exc).__name__}: ambiguous cycle worker start; "
                            "restart reconciliation required"
                        )
                        self._service_state = "QUARANTINED"
                    raise
                if isinstance(started, OrchestrationDispatchOutcome):
                    return started
                lease = getattr(started, "lease", None)
                attempt = getattr(lease, "attempt", None)
                token = getattr(lease, "lease_token", None)
                if attempt is None or not token:
                    raise ServiceError("cycle supervisor returned no active leased Attempt")
                task = asyncio.create_task(
                    self._finish_dispatched(job_id, started),
                    name=f"executive-cycle-finish-{job_id}",
                )
                self._dispatch_tasks[job_id] = task
                return OrchestrationDispatchOutcome(
                    command_id=command_id,
                    job_id=job_id,
                    attempt=attempt,
                    outcome="ACTIVE",
                    lease_token=token,
                )

    async def _run_coo_cycle_once(self, root_job_id: str) -> CooCycleOutcome:
        if self._closing:
            raise StateConflict("Executive control service is closing")
        if not self.config.coo_autonomy_armed:
            raise StateConflict("COO autonomy is not armed in reviewed host configuration")
        if self._service_state != "READY":
            raise StateConflict(f"Executive control service is {self._service_state}")
        root_id = self._id(root_job_id, "root_job_id")
        async with self._coo_cycle_lock:
            self._require_coo_worker_composed()
            root = self._require_runtime().jobs.get_job(root_id)
            if root is None or not self._is_bound_coo_root(root):
                raise StateConflict("COO cycle accepts only an exact host-bound strict-v2 root")
            children = [
                job
                for job in self._require_runtime().jobs.list_jobs()
                if job.parent_job_id == root_id
            ]
            if not children:
                observation = self._require_coo_workspace(root)
                if (
                    observation["head"] != self.config.proof_base_sha
                    or observation["launch_clean"] is not True
                ):
                    raise ServiceError(
                        "new COO root requires the clean exact reviewed-base workspace"
                    )
            live = {
                value
                for value, task in self._dispatch_tasks.items()
                if not task.done()
            }
            live_jobs = [self._require_runtime().jobs.get_job(value) for value in live]
            if live and (
                any(value is None for value in live_jobs)
                or any(value.root_job_id != root_id for value in live_jobs if value is not None)
            ):
                raise StateConflict("another COO root owns the serialized worker")
            await self._reconcile_unowned_cycle_attempts()
            loop = asyncio.get_running_loop()

            def dispatch(job_id: str, command_id: str) -> OrchestrationDispatchOutcome:
                future = asyncio.run_coroutine_threadsafe(
                    self._dispatch_cycle_job_exact(job_id, command_id), loop
                )
                return future.result()

            outcome = await asyncio.to_thread(
                CooCycle(self._require_runtime(), dispatcher=dispatch).run_once,
                root_id,
            )
            self._coo_last_tick_at = datetime.now(timezone.utc).isoformat(
                timespec="seconds"
            )
            self._coo_last_outcome = outcome.to_dict()
            self._coo_last_error = None
            return outcome

    async def _run_coo_cycle(self, root_job_id: str) -> CooCycleOutcome:
        task = asyncio.current_task()
        if task is None:  # pragma: no cover - asyncio always owns service calls
            return await self._run_coo_cycle_once(root_job_id)
        self._coo_action_tasks.add(task)
        try:
            return await self._run_coo_cycle_once(root_job_id)
        finally:
            self._coo_action_tasks.discard(task)

    def _next_bound_coo_root(self) -> str | None:
        runtime = self._require_runtime()
        with runtime.store.read() as connection:
            rows = connection.execute(
                """
                SELECT job_id FROM jobs
                WHERE parent_job_id IS NULL AND root_job_id=job_id
                  AND orchestration_role='aggregation'
                  AND status IN ('QUEUED','RUNNING','CHECKPOINTED','RATE_LIMITED','FAILED','LOST')
                ORDER BY priority DESC,created_at_ms,job_id
                LIMIT ?
                """,
                (_COO_ROOT_SCAN_LIMIT + 1,),
            ).fetchall()
        if len(rows) > _COO_ROOT_SCAN_LIMIT:
            raise ServiceError("bounded COO root scan limit was exceeded")
        for row in rows:
            root = runtime.jobs.get_job(str(row["job_id"]))
            if root is None or not self._is_bound_coo_root(root):
                continue
            blocked = any(
                event.event_type == "COO_CYCLE_BLOCKED"
                for event in runtime.events.list_events(job_id=root.job_id)
            )
            if not blocked:
                return root.job_id
        return None

    def _record_coo_tick_refusal(self, root_job_id: str, exc: Exception) -> None:
        """Persist one idempotent, secret-free autonomous refusal receipt."""

        runtime = self._require_runtime()
        payload = {
            "schema_version": "mastermind.executive_coo_tick_refusal/v1",
            "root_job_id": root_job_id,
            "error_type": type(exc).__name__,
            "reason_code": "bounded_cycle_action_refused",
            "routing_policy_version": self._coo_execution_binding[
                "routing_policy_version"
            ],
            "capability_policy_digest": self._coo_execution_binding[
                "capability_policy_digest"
            ],
        }
        digest = hashlib.sha256(_canonical_json(payload)).hexdigest()
        command_id = f"coo-service-refusal:{digest}"
        with runtime.store.transaction() as connection:
            if connection.execute(
                "SELECT 1 FROM events WHERE command_id=?", (command_id,)
            ).fetchone() is None:
                runtime.store.append_event(
                    connection,
                    aggregate_type="job",
                    aggregate_id=root_job_id,
                    event_type="COO_SERVICE_TICK_REFUSED",
                    actor="executive-control-service",
                    job_id=root_job_id,
                    payload=payload,
                    command_id=command_id,
                )

    async def _coo_tick_loop(self) -> None:
        assert self._coo_shutdown_event is not None
        while not self._coo_shutdown_event.is_set():
            try:
                await asyncio.wait_for(
                    self._coo_shutdown_event.wait(),
                    timeout=float(self.config.coo_tick_interval_seconds),
                )
            except asyncio.TimeoutError:
                pass
            if self._coo_shutdown_event.is_set():
                return
            if self._service_state != "READY" or any(
                not task.done() for task in self._dispatch_tasks.values()
            ):
                continue
            root_id: str | None = None
            try:
                root_id = self._next_bound_coo_root()
                if root_id is not None:
                    await self._run_coo_cycle(root_id)
            except Exception as exc:
                self._coo_last_tick_at = datetime.now(timezone.utc).isoformat(
                    timespec="seconds"
                )
                self._coo_last_error = f"{type(exc).__name__}: {str(exc)[:500]}"
                if root_id is not None:
                    try:
                        self._record_coo_tick_refusal(root_id, exc)
                    except Exception:
                        # The original refusal remains the status truth.  A
                        # receipt-write defect must not trigger a second action
                        # or turn the same tick into an unbounded retry loop.
                        pass

    async def _finish_dispatched(self, job_id: str, active: Any) -> None:
        try:
            await self._require_supervisor().finish_job(active)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._dispatch_errors[job_id] = f"{type(exc).__name__}: {str(exc)[:500]}"
            # A finish/seal failure cannot be treated as an ordinary completed
            # dispatch.  Quarantine all mutating requests until an operator
            # restarts and identity-safely reconciles the still-active attempt.
            self._service_state = "QUARANTINED"
        finally:
            current = asyncio.current_task()
            if self._dispatch_tasks.get(job_id) is current:
                self._dispatch_tasks.pop(job_id, None)

    async def _dispatch_job(self, job_id: str) -> dict[str, Any]:
        runtime = self._require_runtime()
        supervisor = self._require_supervisor()
        async with self._dispatch_lock:
            # The same lock guards every operation that can add, replace, or
            # rotate a direct child of either isolation root.  Hold it across
            # supervisor.start_job(): that call freezes the sibling manifest,
            # sends it to the worker broker, and returns only after the worker
            # process has spawned.  Register the active task before releasing
            # the lock so a concurrent creator cannot enter the snapshot/start
            # gap or slip through an unrecorded-active window.
            async with self._workspace_lock:
                if any(not task.done() for task in self._dispatch_tasks.values()):
                    raise StateConflict("the serialized worker already has an active dispatch")
                job = runtime.jobs.get_job(job_id)
                if job is None:
                    raise StateConflict(f"job {job_id!r} does not exist")
                if not self._is_fixed_proof_job(job):
                    raise StateConflict(
                        "service dispatch accepts only its fixed harmless proof job"
                    )
                if job.status is not JobStatus.QUEUED:
                    raise StateConflict(f"job {job_id} cannot dispatch from {job.status.value}")
                self._require_shared_git_handoff(Path(job.worktree))
                try:
                    active = await supervisor.start_job(job_id)
                except Exception as exc:
                    current = runtime.jobs.get_job(job_id)
                    if current is not None and current.status in {
                        JobStatus.RUNNING,
                        JobStatus.CHECKPOINTED,
                        JobStatus.CANCEL_REQUESTED,
                    }:
                        self._dispatch_errors[job_id] = (
                            f"{type(exc).__name__}: ambiguous worker start; "
                            "restart reconciliation required"
                        )
                        self._service_state = "QUARANTINED"
                    raise
                task = asyncio.create_task(
                    self._finish_dispatched(job_id, active),
                    name=f"executive-finish-{job_id}",
                )
                self._dispatch_tasks[job_id] = task
                attempt = getattr(getattr(active, "lease", None), "attempt", None)
                return {
                    "job_id": job_id,
                    "attempt": _jsonable(attempt) if attempt is not None else None,
                    "accepted": True,
                }

    def _backup_path(self, name: Any) -> Path:
        if self.config.backup_root is None:
            raise ServiceError("backup_root is not configured")
        if not isinstance(name, str) or _BACKUP_NAME_RE.fullmatch(name) is None:
            raise ValueError("backup name must be a simple .sqlite3 file name")
        root = self.config.backup_root.resolve(strict=False)
        path = (root / name).resolve(strict=False)
        if path.parent != root:
            raise ValueError("backup path escapes configured backup root")
        return path

    async def _dispatch_request(self, raw_request: Any) -> Any:
        command, args = self._request(raw_request)
        runtime = self._require_runtime()

        if command == "status":
            self._exact_args(args, set())
            active = sorted(
                job_id for job_id, task in self._dispatch_tasks.items() if not task.done()
            )
            return {
                "protocol": CONTROL_PROTOCOL_VERSION,
                "service_state": self._service_state,
                "instance_id": self.instance_id,
                "pid": os.getpid(),
                "started_at": self._started_at,
                "socket": str(self.socket_path),
                "active_dispatches": active,
                "dispatch_errors": dict(sorted(self._dispatch_errors.items())),
                "startup_reconciliation": _jsonable(self._startup_reconciliation),
                "coo_autonomy": {
                    "armed": self.config.coo_autonomy_armed,
                    "tick_interval_seconds": self.config.coo_tick_interval_seconds,
                    "model_alias": self.config.coo_model_alias,
                    "quota_classes": list(
                        self._coo_execution_binding["eligible_quota_classes"]
                    ),
                    "last_tick_at": self._coo_last_tick_at,
                    "last_outcome": self._coo_last_outcome,
                    "last_error": self._coo_last_error,
                },
            }
        if command == "health":
            self._exact_args(args, set())
            return self._database_health()
        if command == "activate-canary":
            self._exact_args(args, set())
            if self._service_state != "AWAITING_CANARY":
                raise StateConflict("Executive control service is not awaiting a canary")
            if self._canary_loader is None:
                raise ServiceError("Executive control service has no canary loader")
            verdict = await asyncio.to_thread(self._canary_loader)
            await self.activate_canary(verdict)
            return {"service_state": self._service_state}
        if self._service_state != "READY":
            raise StateConflict(
                f"Executive control service is {self._service_state}; "
                "only status, health, and canary activation are available"
            )
        if command == "workers":
            self._exact_args(args, set())
            return _jsonable(runtime.workers.list_workers())
        if command == "jobs":
            self._exact_args(args, set())
            return _jsonable(runtime.jobs.list_jobs())
        if command == "job":
            self._exact_args(args, {"job_id"})
            job_id = self._id(args["job_id"], "job_id")
            job = runtime.jobs.get_job(job_id)
            if job is None:
                raise StateConflict(f"job {job_id!r} does not exist")
            return _jsonable(job)
        if command == "attempt":
            self._exact_args(args, {"attempt_id"})
            attempt_id = self._id(args["attempt_id"], "attempt_id")
            attempt = runtime.attempts.get_attempt(attempt_id)
            if attempt is None:
                raise StateConflict(f"attempt {attempt_id!r} does not exist")
            return _jsonable(attempt)
        if command == "register-worker":
            self._exact_args(args, set())
            return _jsonable(self._register_worker())
        if command == "create-proof-job":
            self._exact_args(args, set())
            return _jsonable(await self._create_proof_job())
        if command == "dispatch":
            self._exact_args(args, {"job_id"})
            return await self._dispatch_job(self._id(args["job_id"], "job_id"))
        if command == "run-coo-cycle":
            self._exact_args(args, {"root_job_id"})
            return _jsonable(
                await self._run_coo_cycle(
                    self._id(args["root_job_id"], "root_job_id")
                )
            )
        if command == "submit-ceo-intent":
            # The bounded CEO write bridge (Phase 1E-A).  It validates one typed
            # envelope, lets the existing authority policy adjudicate it inside
            # create_job, and returns a receipt naming the resulting QUEUED Job.
            # Submission remains distinct from execution. V1 is structurally
            # undispatchable by this service. Strict v2 receives only the
            # reviewed host-owned G1 execution binding; a later, separately
            # armed run-coo-cycle action may advance that exact root.
            # ``CeoIntentError`` subclasses ValueError precisely so a refusal
            # lands on the existing `request_failed` code above rather than the
            # opaque `internal_error` path.
            self._exact_args(args, {"intent"})
            return _jsonable(
                await asyncio.to_thread(self._submit_service_intent, args["intent"])
            )
        if command == "ceo-intent-status":
            # Read-back only.  The durable JOB_CREATED event plus the Job row are
            # the whole record; no status store is introduced.
            self._exact_args(args, {"intent_id"})
            intent_id = self._id(args["intent_id"], "intent_id")
            return _jsonable(
                await asyncio.to_thread(ceo_intent.resolve_intent, runtime, intent_id)
            )
        if command == "cancel":
            self._exact_args(args, {"job_id"})
            return _jsonable(runtime.jobs.cancel_job(self._id(args["job_id"], "job_id")))
        if command == "reconcile":
            self._exact_args(args, set())
            if any(not task.done() for task in self._dispatch_tasks.values()):
                raise StateConflict("cannot reconcile while this service owns an active dispatch")
            return _jsonable(
                await asyncio.to_thread(
                    self._require_supervisor().reconcile_restart,
                    requeue_lost=False,
                )
            )
        if command == "requeue":
            self._exact_args(args, {"job_id"})
            job_id = self._id(args["job_id"], "job_id")
            return _jsonable(await self._requeue_proof_job(job_id))
        if command == "backup":
            self._exact_args(args, set())
            if self.config.backup_root is None:
                raise ServiceError("backup_root is not configured")
            self.config.backup_root.mkdir(mode=0o700, parents=True, exist_ok=True)
            self.config.backup_root.chmod(0o700)
            return _jsonable(
                await asyncio.to_thread(
                    self._backup_backend.create_online_backup,
                    runtime.store,
                    self.config.backup_root,
                )
            )
        if command == "verify-backup":
            self._exact_args(args, {"name"})
            database_path = self._backup_path(args["name"])
            manifest_path = database_path.with_suffix(".manifest.json")
            if not manifest_path.is_file() or manifest_path.is_symlink():
                raise ServiceError("backup has no canonical manifest and is not restorable")
            return _jsonable(
                await asyncio.to_thread(
                    self._backup_backend.verify_backup,
                    database_path,
                    manifest_path,
                )
            )
        raise ValueError(f"unknown control command {command!r}")


async def send_control_request(
    socket_path: str | Path,
    command: str,
    args: Mapping[str, Any] | None = None,
    *,
    max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
) -> dict[str, Any]:
    """Send one request over AF_UNIX; used by the thin operator CLI."""

    path = Path(socket_path)
    if not path.is_absolute():
        raise ServiceError("control socket path must be absolute")
    request = {
        "version": CONTROL_PROTOCOL_VERSION,
        "command": command,
        "args": dict(args or {}),
    }
    raw = _canonical_json(request)
    if len(raw) > DEFAULT_MAX_REQUEST_BYTES:
        raise ServiceError("control request exceeds byte limit")
    reader, writer = await asyncio.open_unix_connection(str(path), limit=max_response_bytes + 1)
    try:
        writer.write(raw)
        await writer.drain()
        try:
            response_raw = await reader.readuntil(b"\n")
        except asyncio.LimitOverrunError as exc:
            raise ServiceError("control response exceeds byte limit") from exc
        if len(response_raw) > max_response_bytes:
            raise ServiceError("control response exceeds byte limit")
        try:
            response = json.loads(response_raw.decode("utf-8", errors="strict"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ServiceError("control service returned invalid JSON") from exc
        if not isinstance(response, dict) or not isinstance(response.get("ok"), bool):
            raise ServiceError("control service returned an invalid envelope")
        return response
    finally:
        writer.close()
        await writer.wait_closed()


__all__ = [
    "BackupBackendProtocol",
    "CONTROL_PROTOCOL_VERSION",
    "DEFAULT_MAX_REQUEST_BYTES",
    "DEFAULT_MAX_RESPONSE_BYTES",
    "ExecutiveControlService",
    "ServiceConfig",
    "ServiceError",
    "SupervisorProtocol",
    "activate_launchd_socket",
    "send_control_request",
]
