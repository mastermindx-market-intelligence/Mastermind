"""Selected-project runtime owner for Workbench Action.

This sibling reuses the existing Business authentication/audit contracts and the
shared bounded synchronous executor. It owns one already-authorized project root
and one short-lived action-token key; it creates no project registry, provider
session, Git publication path, Executive lifecycle, retry plane, or shell.
"""

from __future__ import annotations

import dataclasses
import hashlib
import math
import os
import platform
import re
import stat
import threading
from collections.abc import Callable, Mapping
from typing import Any
from urllib.parse import urlsplit

from mcp.server.auth.routes import build_resource_metadata_url
from pydantic import AnyHttpUrl

from common.bounded_sync_executor import (
    BoundedSyncExecutor,
    SyncExecutorCloseTimeout,
    SyncExecutorClosed,
    SyncExecutorLoopConflict,
)
from control_plane.codex_worker import ProcessInspector
from integrations.business_mcp_auth.audit import (
    AuditAcquisitionUncertain,
    AuditSinkPoisoned,
    DurableAuthAuditSink,
)
from integrations.business_mcp_auth.contracts import (
    ChannelAuditEvent,
    ResourcePolicy,
    validate_resource_policy,
)
from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator
from integrations.workbench_read_mcp.runtime import (
    RuntimeCloseIncomplete,
    RuntimeCloseUncertain,
    RuntimeClosed,
    RuntimeConfigurationError,
)

from .action_artifacts import (
    ActionArtifactStore,
    ActionHostBinding,
    adopt_artifact_store,
    revalidate_artifact_store,
    validate_host_binding,
)
from .contracts import ActionCaller, ActionScope, ProjectActionBinding
from .deployment import RuntimeServices, create_deployment

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_HEX40 = re.compile(r"^[0-9a-f]{40}$")
_REF_PREFIXES = {
    "project_ref": "project:",
    "context_ref": "context:",
    "responsibility_ref": "responsibility:",
    "operation_ref": "operation:",
    "owner_ref": "owner:",
    "generation": "generation:",
}

CHANNEL_AUTHORITY_KIND = "secure_mcp_tunnel_channel"
_CHANNEL_DOMAIN = "mastermind.secure_mcp_tunnel_channel.v1"
_CHANNEL_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


@dataclasses.dataclass(frozen=True)
class FixedTunnelChannel:
    """One host-selected exact tunnel/organization/workspace binding.

    The triple names a Secure MCP Tunnel association, not an end user.  A
    channel therefore never carries a principal claim of its own; its only
    authority is the digest the host lease already pins.
    """

    tunnel_id: str
    organization_id: str
    workspace_id: str


def validate_fixed_tunnel_channel(value: object) -> FixedTunnelChannel:
    if type(value) is not FixedTunnelChannel:
        raise _configuration("channel must be an exact FixedTunnelChannel")
    for identifier in (value.tunnel_id, value.organization_id, value.workspace_id):
        if type(identifier) is not str or _CHANNEL_ID.fullmatch(identifier) is None:
            raise _configuration("fixed tunnel channel identity is invalid")
    return value


def _channel_digest(purpose: str, channel: FixedTunnelChannel) -> str:
    return hashlib.sha256(
        "\x00".join(
            (
                _CHANNEL_DOMAIN,
                purpose,
                channel.tunnel_id,
                channel.organization_id,
                channel.workspace_id,
            )
        ).encode("utf-8")
    ).hexdigest()


def channel_subject_digest(channel: FixedTunnelChannel) -> str:
    """Domain-separated opaque channel digest for ``ActionCaller.subject_digest``."""

    return _channel_digest("subject", validate_fixed_tunnel_channel(channel))


def channel_client_ref(channel: FixedTunnelChannel) -> str:
    """Domain-separated opaque channel digest for ``ActionCaller.client_ref``."""

    return _channel_digest("client", validate_fixed_tunnel_channel(channel))


def channel_binding_ref(channel: FixedTunnelChannel) -> str:
    """Opaque bounded channel reference for receipts and channel audit events."""

    return _channel_digest("binding", validate_fixed_tunnel_channel(channel))


@dataclasses.dataclass(frozen=True)
class StableWorkbenchActionLease:
    expected_subject_digest: str
    expected_client_ref: str
    resource: str
    required_scopes: tuple[str, ...]
    project_ref: str
    context_ref: str
    responsibility_ref: str
    operation_ref: str
    owner_ref: str
    generation: str
    allowed_paths: tuple[str, ...]
    committed_head: str | None
    lease_expires_at_ms: int


@dataclasses.dataclass(frozen=True)
class _OwnedLease:
    stable: StableWorkbenchActionLease
    root_fd: int
    root_device: int
    root_inode: int
    root_uid: int
    root_mode: int


@dataclasses.dataclass(frozen=True)
class ChannelRuntimeServices:
    """Fixed-channel entry-point services owned by one runtime composition.

    Everything here is host-selected: the exact channel triple, its derived
    ``ActionCaller`` projection, the bound project reference, the runtime
    clock, the durable channel audit identity and sink, and the stable action
    key.  The channel authenticates the transport association only; it is
    never a cryptographically attested end user.
    """

    channel: FixedTunnelChannel
    channel_ref: str
    caller: ActionCaller
    project_ref: str
    audit_policy_id: str
    clock_ms: Callable[[], int]
    audit_sink: DurableAuthAuditSink
    artifact_store: ActionArtifactStore
    host_binding: ActionHostBinding
    action_token_key: bytes
    action_ttl_ms: int
    call_receipt_sink: Callable[[Mapping[str, Any]], None] | None


def _configuration(message: str) -> RuntimeConfigurationError:
    return RuntimeConfigurationError(message)


def _clock(value: object, name: str) -> int:
    if type(value) is not int or not 0 <= value < 2**63:
        raise _configuration(f"{name} must return a nonnegative integer")
    return value


def _positive_float(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _configuration(f"{name} must be a positive finite number")
    selected = float(value)
    if not math.isfinite(selected) or selected <= 0:
        raise _configuration(f"{name} must be a positive finite number")
    return selected


def _positive_integer(value: object, name: str) -> int:
    if type(value) is not int or value <= 0:
        raise _configuration(f"{name} must be a positive integer")
    return value


def _relative_path(value: object) -> str:
    if (
        type(value) is not str
        or not value
        or value.startswith(("/", "~"))
        or "\\" in value
        or ":" in value
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise _configuration("lease path allowlist is invalid")
    try:
        parts = value.split("/")
        if (
            len(value.encode("utf-8")) > 512
            or len(parts) > 16
            or any(
                part in ("", ".", "..") or len(part.encode("utf-8")) > 255
                for part in parts
            )
        ):
            raise _configuration("lease path allowlist is invalid")
    except UnicodeError as error:
        raise _configuration("lease path allowlist is invalid") from error
    return value


def _prefixed(value: object, name: str) -> str:
    prefix = _REF_PREFIXES[name]
    if (
        type(value) is not str
        or not value.startswith(prefix)
        or _HEX64.fullmatch(value[len(prefix) :]) is None
    ):
        raise _configuration(f"{name} is not an exact pseudonymous reference")
    return value


def _validate_lease(value: object, *, now_ms: int) -> StableWorkbenchActionLease:
    if type(value) is not StableWorkbenchActionLease:
        raise _configuration("lease must be an exact StableWorkbenchActionLease")
    if (
        type(value.expected_subject_digest) is not str
        or _HEX64.fullmatch(value.expected_subject_digest) is None
        or type(value.expected_client_ref) is not str
        or _HEX64.fullmatch(value.expected_client_ref) is None
        or value.required_scopes != ("workbench.action",)
    ):
        raise _configuration("stable action identity is invalid")
    for name in _REF_PREFIXES:
        _prefixed(getattr(value, name), name)
    if type(value.resource) is not str or not value.resource or value.resource != value.resource.strip():
        raise _configuration("lease resource is invalid")
    if type(value.allowed_paths) is not tuple or not 0 < len(value.allowed_paths) <= 64:
        raise _configuration("lease path allowlist is invalid")
    paths = tuple(_relative_path(path) for path in value.allowed_paths)
    if len(paths) != len(set(paths)):
        raise _configuration("lease path allowlist contains duplicates")
    if value.committed_head is not None and (
        type(value.committed_head) is not str
        or _HEX40.fullmatch(value.committed_head) is None
    ):
        raise _configuration("committed baseline is invalid")
    if (
        type(value.lease_expires_at_ms) is not int
        or not 0 <= value.lease_expires_at_ms < 2**63
        or value.lease_expires_at_ms <= now_ms
    ):
        raise _configuration("stable lease is expired or invalid")
    return value


def _validate_policy_and_lease(
    policy: object,
    authenticator: object,
    lease: object,
    *,
    now_ms: int,
) -> tuple[ResourcePolicy, StableWorkbenchActionLease]:
    try:
        selected_policy = validate_resource_policy(policy)
    except Exception as error:
        raise _configuration("resource policy refused") from error
    selected_lease = _validate_lease(lease, now_ms=now_ms)
    if not isinstance(authenticator, JwtAuthenticator):
        raise _configuration("authenticator must be JwtAuthenticator")
    try:
        authenticator_policy = validate_resource_policy(authenticator.policy)
    except Exception as error:
        raise _configuration("authenticator policy refused") from error
    if authenticator_policy != selected_policy:
        raise _configuration("authenticator and runtime policy differ")
    if selected_policy.required_scopes != ("workbench.action",):
        raise _configuration("policy must require exactly workbench.action")
    if selected_policy.allowed_subject_digests != (
        selected_lease.expected_subject_digest,
    ):
        raise _configuration("policy must authorize exactly the stable subject")
    if (
        selected_lease.resource != selected_policy.resource
        or selected_lease.required_scopes != selected_policy.required_scopes
    ):
        raise _configuration("stable lease does not match resource policy")
    if selected_policy.authorization_servers != (selected_policy.issuer,):
        raise _configuration("policy must expose one canonical issuer")
    parsed = urlsplit(selected_policy.resource)
    if parsed.path != "/mcp" or parsed.query or parsed.fragment:
        raise _configuration("Workbench Action resource path must be exactly /mcp")
    try:
        expected_metadata = str(
            build_resource_metadata_url(AnyHttpUrl(selected_policy.resource))
        )
    except Exception as error:
        raise _configuration("resource metadata derivation failed") from error
    if expected_metadata != selected_policy.resource_metadata_url:
        raise _configuration("AUTH_RESOURCE_METADATA_BINDING_MISMATCH")
    return selected_policy, selected_lease


def _directory_identity(value: os.stat_result) -> tuple[int, int, int, int]:
    return value.st_dev, value.st_ino, value.st_uid, stat.S_IMODE(value.st_mode)


def _validate_directory(value: os.stat_result) -> None:
    if (
        not stat.S_ISDIR(value.st_mode)
        or value.st_uid != os.geteuid()
        or stat.S_IMODE(value.st_mode) & 0o022
    ):
        raise _configuration("project directory security refused")


def _open_owned_root(host_fd: int) -> tuple[int, os.stat_result]:
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    directory = getattr(os, "O_DIRECTORY", 0)
    cloexec = getattr(os, "O_CLOEXEC", 0)
    if (
        type(host_fd) is not int
        or host_fd < 0
        or not nofollow
        or not directory
        or not cloexec
        or os.open not in os.supports_dir_fd
    ):
        raise _configuration("descriptor-relative project root is unqualified")
    owned = -1
    try:
        host_stat = os.fstat(host_fd)
        _validate_directory(host_stat)
        owned = os.open(
            ".", os.O_RDONLY | directory | nofollow | cloexec, dir_fd=host_fd
        )
        owned_stat = os.fstat(owned)
        _validate_directory(owned_stat)
        if _directory_identity(host_stat) != _directory_identity(owned_stat) or os.get_inheritable(owned):
            raise _configuration("owned project root identity changed")
        return owned, owned_stat
    except BaseException as error:
        cleanup_errors: list[BaseException] = []
        if owned >= 0:
            try:
                os.close(owned)
            except BaseException as cleanup_error:
                cleanup_errors.append(cleanup_error)
        if cleanup_errors:
            raise RuntimeCloseUncertain(
                "project root acquisition cleanup is uncertain",
                primary_error=error,
                cleanup_errors=tuple(cleanup_errors),
            ) from cleanup_errors[0]
        raise


def _host_binding(host_id: object) -> ActionHostBinding:
    try:
        boot_session_id = ProcessInspector().boot_session_id()
    except Exception as error:
        raise _configuration("host boot identity is unavailable") from error
    if platform.system() == "Darwin" and boot_session_id.startswith("adapter-"):
        raise _configuration("native host boot identity is unavailable")
    try:
        return validate_host_binding(
            ActionHostBinding(
                host_id=host_id,  # type: ignore[arg-type]
                boot_session_id=boot_session_id,
            )
        )
    except Exception as error:
        raise _configuration("host binding is invalid") from error


class WorkbenchActionRuntime:
    def __init__(
        self,
        *,
        lease: _OwnedLease,
        audit_sink: DurableAuthAuditSink,
        executor: BoundedSyncExecutor,
        artifact_store: ActionArtifactStore,
        host_binding: ActionHostBinding,
        io_timeout_seconds: float,
        clock_ms: Callable[[], int],
    ) -> None:
        self._lease = lease
        self._audit_sink = audit_sink
        self._executor = executor
        self._artifact_store = artifact_store
        self._host_binding = host_binding
        self._io_timeout_seconds = io_timeout_seconds
        self._clock_ms = clock_ms
        self._gate = threading.RLock()
        self._revoked = False
        self._closing = False
        self._closed = False
        self._close_in_progress = False
        self._close_uncertain: RuntimeCloseUncertain | None = None
        self.services: RuntimeServices
        self.server: object
        self.channel_services: ChannelRuntimeServices

    @classmethod
    def open(
        cls,
        *,
        authenticator: JwtAuthenticator,
        policy: ResourcePolicy,
        now: Callable[[], int],
        clock_ms: Callable[[], int],
        project_directory_fd: int,
        audit_directory_fd: int,
        host_artifact_fd: int,
        host_id: str,
        lease: StableWorkbenchActionLease,
        action_token_key: bytes,
        allowed_hosts: tuple[str, ...],
        allowed_origins: tuple[str, ...] = (),
        call_receipt_sink: Callable[[Mapping[str, Any]], None] | None = None,
        max_concurrency: int = 2,
        io_timeout_seconds: float = 5.0,
        action_ttl_ms: int = 5 * 60 * 1000,
    ) -> "WorkbenchActionRuntime":
        if not callable(now) or not callable(clock_ms):
            raise _configuration("runtime clocks must be callable")
        try:
            _clock(now(), "now")
            now_ms = _clock(clock_ms(), "clock_ms")
        except RuntimeConfigurationError:
            raise
        except Exception as error:
            raise _configuration("runtime clock failed") from error
        selected_policy, selected_lease = _validate_policy_and_lease(
            policy, authenticator, lease, now_ms=now_ms
        )
        selected_host = _host_binding(host_id)
        if (
            type(action_token_key) is not bytes
            or len(action_token_key) < 32
            or type(allowed_hosts) is not tuple
            or not allowed_hosts
            or any(type(value) is not str or not value for value in allowed_hosts)
            or type(allowed_origins) is not tuple
            or any(type(value) is not str or not value for value in allowed_origins)
        ):
            raise _configuration("runtime action/transport configuration refused")
        capacity = _positive_integer(max_concurrency, "max_concurrency")
        io_timeout = _positive_float(io_timeout_seconds, "io_timeout_seconds")
        if type(action_ttl_ms) is not int or not 1000 <= action_ttl_ms <= 5 * 60 * 1000:
            raise _configuration("action ttl is invalid")

        def wire_oauth(
            runtime: "WorkbenchActionRuntime", audit_sink: DurableAuthAuditSink
        ) -> None:
            runtime.services = RuntimeServices(
                authenticator=authenticator,
                policy=selected_policy,
                now=now,
                clock_ms=clock_ms,
                audit_sink=audit_sink,
                artifact_store=runtime.artifact_store,
                host_binding=runtime.host_binding,
                resolve_binding=runtime.resolve_binding,
                run_io=runtime.run_io,
                action_token_key=bytes(action_token_key),
                allowed_hosts=allowed_hosts,
                call_receipt_sink=call_receipt_sink,
                allowed_origins=allowed_origins,
                action_ttl_ms=action_ttl_ms,
            )
            runtime.server = create_deployment(runtime.services)

        return cls._acquire(
            selected_lease=selected_lease,
            clock_ms=clock_ms,
            project_directory_fd=project_directory_fd,
            audit_directory_fd=audit_directory_fd,
            host_artifact_fd=host_artifact_fd,
            host_binding=selected_host,
            audit_policy_id=selected_policy.policy_id,
            capacity=capacity,
            io_timeout=io_timeout,
            wire=wire_oauth,
        )

    @classmethod
    def open_channel(
        cls,
        *,
        channel: FixedTunnelChannel,
        clock_ms: Callable[[], int],
        project_directory_fd: int,
        audit_directory_fd: int,
        host_artifact_fd: int,
        host_id: str,
        audit_policy_id: str,
        lease: StableWorkbenchActionLease,
        action_token_key: bytes,
        call_receipt_sink: Callable[[Mapping[str, Any]], None] | None = None,
        max_concurrency: int = 2,
        io_timeout_seconds: float = 5.0,
        action_ttl_ms: int = 5 * 60 * 1000,
    ) -> "WorkbenchActionRuntime":
        """Open the fixed-channel stdio entry point over the same ownership.

        No ``JwtAuthenticator``, ``ResourcePolicy``, token verifier, or OAuth
        acceptance is constructed here: the tunnel association authenticates
        one host-selected channel whose derived digests must already be the
        stable host lease's pinned references.  Root descriptor, revoke,
        ``run_io``, physical drain, and audit closure remain owned by this
        single runtime class for both entry points.
        """

        if not callable(clock_ms):
            raise _configuration("runtime clocks must be callable")
        now_ms = _clock(clock_ms(), "clock_ms")
        selected_channel = validate_fixed_tunnel_channel(channel)
        selected_lease = _validate_lease(lease, now_ms=now_ms)
        selected_host = _host_binding(host_id)
        if (
            type(audit_policy_id) is not str
            or not audit_policy_id
            or len(audit_policy_id) > 96
        ):
            raise _configuration("channel audit identity is invalid")
        if (
            channel_subject_digest(selected_channel)
            != selected_lease.expected_subject_digest
            or channel_client_ref(selected_channel)
            != selected_lease.expected_client_ref
        ):
            raise _configuration("fixed channel does not match the stable host lease")
        if type(action_token_key) is not bytes or len(action_token_key) < 32:
            raise _configuration("runtime action/transport configuration refused")
        capacity = _positive_integer(max_concurrency, "max_concurrency")
        io_timeout = _positive_float(io_timeout_seconds, "io_timeout_seconds")
        if type(action_ttl_ms) is not int or not 1000 <= action_ttl_ms <= 5 * 60 * 1000:
            raise _configuration("action ttl is invalid")

        def wire_channel(
            runtime: "WorkbenchActionRuntime", audit_sink: DurableAuthAuditSink
        ) -> None:
            runtime.channel_services = ChannelRuntimeServices(
                channel=selected_channel,
                channel_ref=channel_binding_ref(selected_channel),
                caller=ActionCaller(
                    subject_digest=selected_lease.expected_subject_digest,
                    client_ref=selected_lease.expected_client_ref,
                    resource=selected_lease.resource,
                    scopes=selected_lease.required_scopes,
                    expires_at=max(1, selected_lease.lease_expires_at_ms // 1000),
                ),
                project_ref=selected_lease.project_ref,
                audit_policy_id=audit_policy_id,
                clock_ms=clock_ms,
                audit_sink=audit_sink,
                artifact_store=runtime.artifact_store,
                host_binding=runtime.host_binding,
                action_token_key=bytes(action_token_key),
                action_ttl_ms=action_ttl_ms,
                call_receipt_sink=call_receipt_sink,
            )

        return cls._acquire(
            selected_lease=selected_lease,
            clock_ms=clock_ms,
            project_directory_fd=project_directory_fd,
            audit_directory_fd=audit_directory_fd,
            host_artifact_fd=host_artifact_fd,
            host_binding=selected_host,
            audit_policy_id=audit_policy_id,
            capacity=capacity,
            io_timeout=io_timeout,
            wire=wire_channel,
        )

    @classmethod
    def _acquire(
        cls,
        *,
        selected_lease: StableWorkbenchActionLease,
        clock_ms: Callable[[], int],
        project_directory_fd: int,
        audit_directory_fd: int,
        host_artifact_fd: int,
        host_binding: ActionHostBinding,
        audit_policy_id: str,
        capacity: int,
        io_timeout: float,
        wire: Callable[["WorkbenchActionRuntime", DurableAuthAuditSink], None],
    ) -> "WorkbenchActionRuntime":
        """One shared acquisition path for both entry points.

        This method owns the project-root descriptor, the durable audit sink,
        and the bounded executor, applies the entry-point ``wire`` projection,
        and preserves the single fail-closed rollback contract.
        """

        root_fd = -1
        artifact_fd = -1
        artifact_store: ActionArtifactStore | None = None
        audit_sink: DurableAuthAuditSink | None = None
        try:
            root_fd, root_stat = _open_owned_root(project_directory_fd)
            artifact_fd, _artifact_stat = _open_owned_root(host_artifact_fd)
            artifact_store = adopt_artifact_store(artifact_fd)
            audit_sink = DurableAuthAuditSink.open(
                audit_directory_fd, policy_id=audit_policy_id
            )
            executor = BoundedSyncExecutor(max_concurrency=capacity)
            runtime = cls(
                lease=_OwnedLease(
                    stable=selected_lease,
                    root_fd=root_fd,
                    root_device=root_stat.st_dev,
                    root_inode=root_stat.st_ino,
                    root_uid=root_stat.st_uid,
                    root_mode=stat.S_IMODE(root_stat.st_mode),
                ),
                audit_sink=audit_sink,
                executor=executor,
                artifact_store=artifact_store,
                host_binding=host_binding,
                io_timeout_seconds=io_timeout,
                clock_ms=clock_ms,
            )
            wire(runtime, audit_sink)
            return runtime
        except BaseException as error:
            cleanup_errors: list[BaseException] = []
            if audit_sink is not None:
                try:
                    audit_sink.close()
                except BaseException as cleanup_error:
                    cleanup_errors.append(cleanup_error)
            if root_fd >= 0:
                try:
                    os.close(root_fd)
                except BaseException as cleanup_error:
                    cleanup_errors.append(cleanup_error)
            if artifact_fd >= 0:
                try:
                    os.close(artifact_fd)
                except BaseException as cleanup_error:
                    if artifact_store is not None:
                        artifact_store.mark_cleanup_uncertain("runtime_acquisition_close")
                    cleanup_errors.append(cleanup_error)
            if cleanup_errors:
                raise RuntimeCloseUncertain(
                    "runtime construction failed and rollback is uncertain",
                    primary_error=error,
                    cleanup_errors=tuple(cleanup_errors),
                ) from cleanup_errors[0]
            if isinstance(error, RuntimeCloseUncertain):
                raise
            if isinstance(error, AuditAcquisitionUncertain):
                raise RuntimeCloseUncertain(
                    "durable audit acquisition cleanup is uncertain",
                    primary_error=error.primary_error,
                    cleanup_errors=error.cleanup_errors,
                ) from error
            if isinstance(error, RuntimeConfigurationError):
                raise
            if isinstance(error, AuditSinkPoisoned):
                raise RuntimeConfigurationError("durable audit acquisition refused") from error
            raise RuntimeConfigurationError("runtime composition refused") from error

    @property
    def root_fd(self) -> int:
        return self._lease.root_fd

    @property
    def artifact_store(self) -> ActionArtifactStore:
        return self._artifact_store

    @property
    def host_binding(self) -> ActionHostBinding:
        return self._host_binding

    def _validate_root_locked(self) -> None:
        try:
            current = os.fstat(self._lease.root_fd)
            current_mode = stat.S_IMODE(current.st_mode)
            if (
                not stat.S_ISDIR(current.st_mode)
                or current.st_dev != self._lease.root_device
                or current.st_ino != self._lease.root_inode
                or current.st_uid != self._lease.root_uid
                or current.st_uid != os.geteuid()
                or current_mode != self._lease.root_mode
                or current_mode & 0o022
                or os.get_inheritable(self._lease.root_fd)
            ):
                raise RuntimeClosed("runtime project root identity changed")
        except RuntimeClosed:
            self._revoked = True
            raise
        except (OSError, TypeError, ValueError) as error:
            self._revoked = True
            raise RuntimeClosed("runtime project root is unavailable") from error

    def resolve_binding(
        self, caller: ActionCaller, project_ref: str
    ) -> ProjectActionBinding | None:
        with self._gate:
            if self._revoked or self._closing or self._closed:
                return None
            try:
                self._validate_root_locked()
                current_ms = _clock(self._clock_ms(), "clock_ms")
            except Exception:
                self._revoked = True
                return None
            stable = self._lease.stable
            if current_ms >= stable.lease_expires_at_ms:
                self._revoked = True
                return None
            if (
                type(caller) is not ActionCaller
                or caller.subject_digest != stable.expected_subject_digest
                or caller.client_ref != stable.expected_client_ref
                or caller.resource != stable.resource
                or caller.scopes != stable.required_scopes
                or type(caller.expires_at) is not int
                or caller.expires_at <= 0
                or project_ref != stable.project_ref
            ):
                return None
            scope = ActionScope(
                root_fd=self._lease.root_fd,
                root_device=self._lease.root_device,
                root_inode=self._lease.root_inode,
                context_ref=stable.context_ref,
                responsibility_ref=stable.responsibility_ref,
                operation_ref=stable.operation_ref,
                owner_ref=stable.owner_ref,
                generation=stable.generation,
                allowed_paths=stable.allowed_paths,
                expires_at_ms=stable.lease_expires_at_ms,
                committed_head=stable.committed_head,
            )
            return ProjectActionBinding(dataclasses.replace(caller), stable.project_ref, scope)

    def _guarded_operation(self, operation: Callable[[], object]) -> object:
        with self._gate:
            if self._revoked or self._closing or self._closed:
                raise RuntimeClosed("runtime admission is closed")
            self._validate_root_locked()
        try:
            result = operation()
        except BaseException as operation_error:
            try:
                with self._gate:
                    self._validate_root_locked()
            except RuntimeClosed as root_error:
                raise root_error from operation_error
            raise
        with self._gate:
            self._validate_root_locked()
        return result

    async def run_io(self, operation: Callable[[], object]) -> object:
        if not callable(operation):
            raise TypeError("operation must be callable")
        with self._gate:
            if self._revoked or self._closing or self._closed:
                raise RuntimeClosed("runtime admission is closed")
            self._validate_root_locked()
        try:
            return await self._executor.run(
                lambda: self._guarded_operation(operation),
                timeout=self._io_timeout_seconds,
            )
        except (SyncExecutorClosed, SyncExecutorLoopConflict) as error:
            raise RuntimeClosed("runtime admission is closed") from error

    async def emit_channel_audit(self, event: ChannelAuditEvent) -> None:
        if type(event) is not ChannelAuditEvent:
            raise TypeError("event must be an exact ChannelAuditEvent")
        with self._gate:
            if self._closing or self._closed:
                raise RuntimeClosed("runtime admission is closed")
            services = getattr(self, "channel_services", None)
            if (
                type(services) is not ChannelRuntimeServices
                or event.policy_id != services.audit_policy_id
                or event.channel_ref != services.channel_ref
            ):
                raise ValueError("channel audit binding is invalid")
        try:
            await self._executor.run(
                lambda: self._audit_sink.emit(event),
                timeout=self._io_timeout_seconds,
            )
        except (SyncExecutorClosed, SyncExecutorLoopConflict) as error:
            raise RuntimeClosed("runtime admission is closed") from error

    def read_channel_admissions(self, action_digest: str) -> tuple[ChannelAuditEvent, ...]:
        """Read the durable channel admission facts for one exact action digest.

        Synchronous by design: the consumer is an already admitted ``run_io``
        operation on the bounded executor thread, so the read must never be
        nested through the executor again.  It observes the same sink the
        admission path appends to, mutates nothing, and reopens no admission.
        """

        with self._gate:
            if self._closing or self._closed:
                raise RuntimeClosed("runtime admission is closed")
            if type(getattr(self, "channel_services", None)) is not ChannelRuntimeServices:
                raise ValueError("channel audit binding is invalid")
        return self._audit_sink.read_channel_admissions(action_digest)

    def revoke(self) -> None:
        with self._gate:
            self._revoked = True

    async def aclose(self, *, timeout: float) -> None:
        selected_timeout = _positive_float(timeout, "close timeout")
        with self._gate:
            if self._close_uncertain is not None:
                raise self._close_uncertain
            if self._closed:
                return
            if self._close_in_progress:
                raise RuntimeCloseIncomplete(0, 1)
            self._close_in_progress = True
            self._revoked = True
            self._closing = True
        try:
            await self._executor.aclose(timeout=selected_timeout)
        except SyncExecutorCloseTimeout as error:
            with self._gate:
                self._close_in_progress = False
            raise RuntimeCloseIncomplete(
                error.active_physical_operations, error.pending_operations
            ) from error
        except SyncExecutorLoopConflict as error:
            with self._gate:
                self._close_in_progress = False
            raise RuntimeCloseIncomplete(0, 1) from error
        except BaseException:
            with self._gate:
                self._close_in_progress = False
            raise

        release_errors: list[BaseException] = []
        with self._gate:
            try:
                self._validate_root_locked()
            except BaseException as error:
                release_errors.append(error)
        try:
            self._audit_sink.close()
        except BaseException as error:
            release_errors.append(error)
        try:
            os.close(self._lease.root_fd)
        except BaseException as error:
            release_errors.append(error)
        try:
            revalidate_artifact_store(self._artifact_store)
        except BaseException as error:
            self._artifact_store.mark_cleanup_uncertain("runtime_store_revalidation")
            release_errors.append(error)
        try:
            os.close(self._artifact_store.dir_fd)
        except BaseException as error:
            self._artifact_store.mark_cleanup_uncertain("runtime_store_close")
            release_errors.append(error)
        try:
            self._artifact_store.raise_if_cleanup_uncertain()
        except BaseException as error:
            release_errors.append(error)
        with self._gate:
            self._closed = True
            self._closing = False
            self._close_in_progress = False
            if release_errors:
                self._close_uncertain = RuntimeCloseUncertain(
                    "runtime descriptor close is uncertain",
                    primary_error=release_errors[0],
                    cleanup_errors=tuple(release_errors[1:]),
                )
        if self._close_uncertain is not None:
            raise self._close_uncertain from release_errors[0]


__all__ = [
    "CHANNEL_AUTHORITY_KIND",
    "ChannelRuntimeServices",
    "FixedTunnelChannel",
    "StableWorkbenchActionLease",
    "WorkbenchActionRuntime",
    "channel_binding_ref",
    "channel_client_ref",
    "channel_subject_digest",
    "validate_fixed_tunnel_channel",
]
