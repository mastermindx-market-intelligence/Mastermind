"""Owning Workbench read runtime over the protected deployment seams.

One instance owns one immutable pseudonymous project lease, an independently
opened project root, one durable auth audit sink, and one bounded synchronous
attempt owner.  It creates no listener, credential, account, provider session,
project registry, retry plane, or installation claim.
"""

from __future__ import annotations

import asyncio
import dataclasses
import math
import os
import re
import stat
import threading
from collections.abc import Callable
from urllib.parse import urlsplit

from mcp.server.auth.routes import build_resource_metadata_url
from pydantic import AnyHttpUrl

from common.bounded_sync_executor import (
    BoundedSyncExecutor,
    SyncExecutorCloseTimeout,
    SyncExecutorClosed,
    SyncExecutorLoopConflict,
)
from integrations.business_mcp_auth.audit import (
    AuditAcquisitionUncertain,
    AuditSinkPoisoned,
    DurableAuthAuditSink,
)
from integrations.business_mcp_auth.contracts import (
    ResourcePolicy,
    validate_resource_policy,
)
from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator
from .app import ReadCaller
from .deployment import RuntimeServices, create_deployment
from .observer import ReadScope
from .read_port import ProjectReadBinding

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_HEX40 = re.compile(r"^[0-9a-f]{40}$")
_PREFIXES = {
    "project_ref": "project:",
    "context_ref": "context:",
    "owner_ref": "owner:",
    "generation": "generation:",
}


class RuntimeConfigurationError(ValueError):
    """Pre-acquisition runtime authority or platform refusal."""


class RuntimeClosed(RuntimeError):
    """Runtime admission is revoked, closing, or closed."""


class RuntimeCloseIncomplete(RuntimeError):
    def __init__(self, active: int, pending: int) -> None:
        self.active_physical_operations = active
        self.pending_operations = pending
        super().__init__(
            f"runtime close incomplete: {active} active physical and "
            f"{pending} pending operation(s)"
        )


class RuntimeCloseUncertain(RuntimeError):
    """Physical drain completed but owned descriptor release is uncertain."""

    def __init__(
        self,
        message: str,
        *,
        primary_error: BaseException | None = None,
        cleanup_errors: tuple[BaseException, ...] = (),
    ) -> None:
        self.primary_error = primary_error
        self.cleanup_errors = cleanup_errors
        super().__init__(message)


@dataclasses.dataclass(frozen=True)
class StableWorkbenchLease:
    expected_subject_digest: str
    expected_client_ref: str
    resource: str
    required_scopes: tuple[str, ...]
    project_ref: str
    context_ref: str
    owner_ref: str
    generation: str
    allowed_paths: tuple[str, ...]
    committed_head: str | None
    lease_expires_at_ms: int


@dataclasses.dataclass(frozen=True)
class _OwnedLease:
    stable: StableWorkbenchLease
    root_fd: int
    root_device: int
    root_inode: int
    root_uid: int
    root_mode: int


def _configuration(message: str) -> RuntimeConfigurationError:
    return RuntimeConfigurationError(message)


def _exact_clock(value: object, name: str) -> int:
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


def _validate_path(value: object) -> str:
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
        encoded = value.encode("utf-8")
        parts = value.split("/")
        if (
            len(encoded) > 512
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


def _validate_prefixed(value: object, name: str) -> str:
    prefix = _PREFIXES[name]
    if (
        type(value) is not str
        or not value.startswith(prefix)
        or _HEX64.fullmatch(value[len(prefix) :]) is None
    ):
        raise _configuration(f"{name} is not an exact pseudonymous reference")
    return value


def _validate_lease(value: object, *, now_ms: int) -> StableWorkbenchLease:
    if type(value) is not StableWorkbenchLease:
        raise _configuration("lease must be an exact StableWorkbenchLease")
    try:
        value = dataclasses.replace(value)
    except (AttributeError, TypeError) as error:
        raise _configuration("stable lease snapshot is invalid") from error
    if (
        type(value.expected_subject_digest) is not str
        or _HEX64.fullmatch(value.expected_subject_digest) is None
    ):
        raise _configuration("expected subject digest is invalid")
    if (
        type(value.expected_client_ref) is not str
        or _HEX64.fullmatch(value.expected_client_ref) is None
    ):
        raise _configuration("expected client reference is invalid")
    if (
        type(value.required_scopes) is not tuple
        or len(value.required_scopes) != 1
        or type(value.required_scopes[0]) is not str
        or value.required_scopes[0] != "workbench.read"
    ):
        raise _configuration("lease must require exactly workbench.read")
    for name in _PREFIXES:
        _validate_prefixed(getattr(value, name), name)
    if (
        type(value.resource) is not str
        or not value.resource
        or value.resource != value.resource.strip()
    ):
        raise _configuration("lease resource is invalid")
    if type(value.allowed_paths) is not tuple or not 0 < len(value.allowed_paths) <= 64:
        raise _configuration("lease path allowlist is invalid")
    paths = tuple(_validate_path(path) for path in value.allowed_paths)
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
) -> tuple[ResourcePolicy, StableWorkbenchLease]:
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
    if selected_policy.required_scopes != ("workbench.read",):
        raise _configuration("policy must require exactly workbench.read")
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
        raise _configuration("Workbench resource path must be exactly /mcp")
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
        if _directory_identity(host_stat) != _directory_identity(
            owned_stat
        ) or os.get_inheritable(owned):
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


class WorkbenchReadRuntime:
    def __init__(
        self,
        *,
        lease: _OwnedLease,
        audit_sink: DurableAuthAuditSink,
        executor: BoundedSyncExecutor,
        io_timeout_seconds: float,
        clock_ms: Callable[[], int],
    ) -> None:
        self._lease = lease
        self._audit_sink = audit_sink
        self._executor = executor
        self._io_timeout_seconds = io_timeout_seconds
        self._clock_ms = clock_ms
        self.services: RuntimeServices
        self.server: object
        self._lease_gate = threading.RLock()
        self._revoked = False
        self._closing = False
        self._closed = False
        self._close_in_progress = False
        self._close_uncertain: RuntimeCloseUncertain | None = None

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
        lease: StableWorkbenchLease,
        allowed_hosts: tuple[str, ...],
        allowed_origins: tuple[str, ...] = (),
        max_concurrency: int = 4,
        io_timeout_seconds: float = 5.0,
    ) -> "WorkbenchReadRuntime":
        if not callable(now) or not callable(clock_ms):
            raise _configuration("runtime clocks must be callable")
        try:
            _exact_clock(now(), "now")
            now_ms = _exact_clock(clock_ms(), "clock_ms")
        except RuntimeConfigurationError:
            raise
        except Exception as error:
            raise _configuration("runtime clock failed") from error
        selected_policy, selected_lease = _validate_policy_and_lease(
            policy, authenticator, lease, now_ms=now_ms
        )
        if (
            type(allowed_hosts) is not tuple
            or not allowed_hosts
            or any(type(value) is not str or not value for value in allowed_hosts)
        ):
            raise _configuration("allowed_hosts must be a nonempty string tuple")
        if type(allowed_origins) is not tuple or any(
            type(value) is not str or not value for value in allowed_origins
        ):
            raise _configuration("allowed_origins must be a string tuple")
        capacity = _positive_integer(max_concurrency, "max_concurrency")
        io_timeout = _positive_float(io_timeout_seconds, "io_timeout_seconds")
        root_fd = -1
        audit_sink: DurableAuthAuditSink | None = None
        try:
            root_fd, root_stat = _open_owned_root(project_directory_fd)
            audit_sink = DurableAuthAuditSink.open(
                audit_directory_fd, policy_id=selected_policy.policy_id
            )
            executor = BoundedSyncExecutor(max_concurrency=capacity)
            owned = _OwnedLease(
                stable=selected_lease,
                root_fd=root_fd,
                root_device=root_stat.st_dev,
                root_inode=root_stat.st_ino,
                root_uid=root_stat.st_uid,
                root_mode=stat.S_IMODE(root_stat.st_mode),
            )
            runtime = cls(
                lease=owned,
                audit_sink=audit_sink,
                executor=executor,
                io_timeout_seconds=io_timeout,
                clock_ms=clock_ms,
            )
            runtime.services = RuntimeServices(
                authenticator=authenticator,
                policy=selected_policy,
                now=now,
                clock_ms=clock_ms,
                audit_sink=audit_sink,
                resolve_binding=runtime.resolve_binding,
                run_io=runtime.run_io,
                allowed_hosts=allowed_hosts,
                allowed_origins=allowed_origins,
            )
            runtime.server = create_deployment(runtime.services)
            return runtime
        except BaseException as error:
            cleanup_errors: list[BaseException] = []
            if audit_sink is not None:
                try:
                    audit_sink.close()
                except BaseException as cleanup:
                    cleanup_errors.append(cleanup)
            if root_fd >= 0:
                try:
                    os.close(root_fd)
                except BaseException as cleanup:
                    cleanup_errors.append(cleanup)
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
                raise RuntimeConfigurationError(
                    "durable audit acquisition refused"
                ) from error
            raise RuntimeConfigurationError("runtime composition refused") from error

    @property
    def root_fd(self) -> int:
        return self._lease.root_fd

    def resolve_binding(
        self, caller: ReadCaller, project_ref: str
    ) -> ProjectReadBinding | None:
        with self._lease_gate:
            if self._revoked or self._closing or self._closed:
                return None
            try:
                self._validate_live_root_locked()
            except RuntimeClosed:
                return None
            stable = self._lease.stable
            try:
                current_ms = _exact_clock(self._clock_ms(), "clock_ms")
            except Exception:
                self._revoked = True
                return None
            if current_ms >= stable.lease_expires_at_ms:
                self._revoked = True
                return None
            if (
                type(caller) is not ReadCaller
                or caller.subject_digest != stable.expected_subject_digest
                or caller.client_ref != stable.expected_client_ref
                or caller.resource != stable.resource
                or caller.scopes != stable.required_scopes
                or type(caller.expires_at) is not int
                or caller.expires_at <= 0
                or project_ref != stable.project_ref
            ):
                return None
            current_caller = dataclasses.replace(caller)
            scope = ReadScope(
                root_fd=self._lease.root_fd,
                root_device=self._lease.root_device,
                root_inode=self._lease.root_inode,
                context_ref=stable.context_ref,
                owner_ref=stable.owner_ref,
                generation=stable.generation,
                allowed_paths=stable.allowed_paths,
                expires_at_ms=stable.lease_expires_at_ms,
                committed_head=stable.committed_head,
            )
            return ProjectReadBinding(
                caller=current_caller,
                project_ref=stable.project_ref,
                scope=scope,
            )

    def _validate_live_root_locked(self) -> None:
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

    def _guarded_operation(self, operation: Callable[[], object]) -> object:
        with self._lease_gate:
            if self._revoked or self._closing or self._closed:
                raise RuntimeClosed("runtime admission is closed")
            self._validate_live_root_locked()
        try:
            result = operation()
        except BaseException as operation_error:
            try:
                with self._lease_gate:
                    self._validate_live_root_locked()
            except RuntimeClosed as root_error:
                raise root_error from operation_error
            raise
        with self._lease_gate:
            self._validate_live_root_locked()
        return result

    async def run_io(self, operation: Callable[[], object]) -> object:
        if not callable(operation):
            raise TypeError("operation must be callable")
        with self._lease_gate:
            if self._revoked or self._closing or self._closed:
                raise RuntimeClosed("runtime admission is closed")
            self._validate_live_root_locked()
        guarded = lambda: self._guarded_operation(operation)
        try:
            return await self._executor.run(
                guarded, timeout=self._io_timeout_seconds
            )
        except (SyncExecutorClosed, SyncExecutorLoopConflict) as error:
            raise RuntimeClosed("runtime admission is closed") from error

    def revoke(self) -> None:
        with self._lease_gate:
            self._revoked = True

    async def aclose(self, *, timeout: float) -> None:
        selected_timeout = _positive_float(timeout, "close timeout")
        with self._lease_gate:
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
            with self._lease_gate:
                self._close_in_progress = False
            raise RuntimeCloseIncomplete(
                error.active_physical_operations, error.pending_operations
            ) from error
        except SyncExecutorLoopConflict as error:
            with self._lease_gate:
                self._close_in_progress = False
            raise RuntimeCloseIncomplete(0, 1) from error
        except BaseException:
            with self._lease_gate:
                self._close_in_progress = False
            raise

        release_errors: list[BaseException] = []
        with self._lease_gate:
            try:
                self._validate_live_root_locked()
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
        with self._lease_gate:
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
    "RuntimeCloseIncomplete",
    "RuntimeCloseUncertain",
    "RuntimeClosed",
    "RuntimeConfigurationError",
    "StableWorkbenchLease",
    "WorkbenchReadRuntime",
]
