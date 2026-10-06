"""Runnable loopback-only process owner for Workbench Action F0.

This service composes the existing Business authentication, durable auth audit,
shared bounded synchronous executor, selected-project Workbench Action runtime,
and FastMCP server. It creates no credential/account, project registry, generic
shell, Git publication path, Executive lifecycle, provider session, retry plane,
or browser/desktop authority.

The action-token signing key is one owner-provisioned generation key loaded from
a fixed same-euid ``0600`` file. Ordinary service restart therefore preserves
reconciliation for still-live prepared actions without creating a replay store.
Key rotation is a generation boundary and must not strand an unresolved effect.
"""
from __future__ import annotations

import asyncio
from contextlib import AsyncExitStack, asynccontextmanager, contextmanager
import dataclasses
import enum
import json
import math
import os
from pathlib import Path
import re
import socket
import stat
import sys
import time
from urllib.parse import urlsplit

from integrations.business_mcp_auth.contracts import load_resource_policy
from integrations.business_mcp_auth.jwks import BoundedJwksCache, HttpxJwksFetcher
from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator
from integrations.workbench_read_mcp.runtime import (
    RuntimeCloseIncomplete,
    RuntimeCloseUncertain,
)

from .contracts import ActionCaller
from .runtime import StableWorkbenchActionLease, WorkbenchActionRuntime

SERVICE_SCHEMA = "mastermind.workbench_action_service.v1"
SERVICE_SCHEMA_V2 = "mastermind.workbench_action_service.v2"
MAX_CONFIG_BYTES = 64 * 1024
MAX_POLICY_BYTES = 64 * 1024
MAX_BROWSER_CATALOG_BYTES = 2 * 1024 * 1024
MAX_CONCURRENCY = 8
MAX_TIMEOUT_SECONDS = 60.0
MAX_ACTION_TTL_MS = 5 * 60 * 1000
_HOST_LABEL = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?")
_HEX64 = re.compile(r"[0-9a-f]{64}")
_CONFIG_KEYS = frozenset(
    {
        "schema",
        "policy_file",
        "project_root",
        "audit_directory",
        "artifact_directory",
        "host_id",
        "action_key_file",
        "bind_host",
        "bind_port",
        "incoming_authority",
        "max_concurrency",
        "io_timeout_seconds",
        "close_timeout_seconds",
        "action_ttl_ms",
        "lease",
    }
)
_CONFIG_KEYS_V2 = _CONFIG_KEYS | {"browser"}
_BROWSER_KEYS = frozenset(
    {
        "source_root",
        "python_executable",
        "node_executable",
        "mcp_cli_path",
        "chrome_executable",
        "relay_root",
        "output_root",
        "home_dir",
        "tmp_dir",
        "tool_catalog_file",
        "startup_timeout_seconds",
    }
)
_LEASE_KEYS = frozenset(
    {
        "expected_subject_digest",
        "expected_client_ref",
        "resource",
        "required_scopes",
        "project_ref",
        "context_ref",
        "responsibility_ref",
        "operation_ref",
        "owner_ref",
        "generation",
        "allowed_paths",
        "committed_head",
        "lease_expires_at_ms",
    }
)


class ServiceConfigurationError(RuntimeError):
    _CODES = frozenset(
        {
            "SERVICE_CONFIGURATION_REFUSED",
            "SERVICE_BIND_REFUSED",
            "SERVICE_STARTUP_CLEANUP_UNCERTAIN",
        }
    )

    def __init__(self, code: str = "SERVICE_CONFIGURATION_REFUSED") -> None:
        if code not in self._CODES:
            raise ValueError("unknown Workbench Action service error code")
        self.code = code
        super().__init__(code)


class ShutdownOutcome(str, enum.Enum):
    CLEAN = "CLEAN"
    RUNTIME_CLOSE_INCOMPLETE = "RUNTIME_CLOSE_INCOMPLETE"
    RUNTIME_CLOSE_UNCERTAIN = "RUNTIME_CLOSE_UNCERTAIN"
    SERVER_FAILED = "SERVER_FAILED"


@dataclasses.dataclass(frozen=True)
class BrowserServiceConfig:
    """Closed owner-selected Browser sibling settings for service v2."""

    source_root: str
    python_executable: str
    node_executable: str
    mcp_cli_path: str
    chrome_executable: str
    relay_root: str
    output_root: str
    home_dir: str
    tmp_dir: str
    tool_catalog_file: str
    startup_timeout_seconds: float
    mount_path: str = "/browser"


@dataclasses.dataclass(frozen=True)
class ServiceConfig:
    schema: str
    policy_file: str
    project_root: str
    audit_directory: str
    artifact_directory: str
    host_id: str
    action_key_file: str
    bind_host: str
    bind_port: int
    incoming_authority: str
    max_concurrency: int
    io_timeout_seconds: float
    close_timeout_seconds: float
    action_ttl_ms: int
    lease: StableWorkbenchActionLease
    browser: BrowserServiceConfig | None = None

    @property
    def allowed_hosts(self) -> tuple[str, ...]:
        return (self.incoming_authority,)

    @property
    def allowed_origins(self) -> tuple[str, ...]:
        return ()


@dataclasses.dataclass
class ServiceState:
    lifespan_started: bool = False
    lifespan_completed: bool = False
    runtime_close_attempted: bool = False
    socket_owned: bool = False
    stopping: bool = False
    shutdown_outcome: ShutdownOutcome | None = None


def _refuse(code: str = "SERVICE_CONFIGURATION_REFUSED") -> None:
    raise ServiceConfigurationError(code)


def _closed_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            _refuse()
        result[key] = value
    return result


def _reject_constant(_value: str) -> object:
    _refuse()


def _absolute_path(value: object) -> str:
    if type(value) is not str or not value or not value.startswith("/") or "\x00" in value:
        _refuse()
    return value


def _host_id(value: object) -> str:
    if type(value) is not str or _HEX64.fullmatch(value) is None:
        _refuse()
    return value


def _bounded_int(value: object, *, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        _refuse()
    return value


def _bounded_timeout(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _refuse()
    selected = float(value)
    if not math.isfinite(selected) or not 0 < selected <= MAX_TIMEOUT_SECONDS:
        _refuse()
    return selected


def _incoming_authority(value: object) -> str:
    if type(value) is not str or not value or len(value) > 512:
        _refuse()
    if any(ord(character) <= 32 or ord(character) == 127 for character in value):
        _refuse()
    try:
        parsed = urlsplit("//" + value)
        port = parsed.port
    except (TypeError, ValueError):
        _refuse()
    hostname = parsed.hostname
    if (
        not hostname
        or port is None
        or not 1 <= port <= 65535
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path
        or parsed.query
        or parsed.fragment
    ):
        _refuse()
    if ":" not in hostname and any(
        _HOST_LABEL.fullmatch(label) is None for label in hostname.rstrip(".").split(".")
    ):
        _refuse()
    return value


def parse_browser_service_config(value: object) -> BrowserServiceConfig:
    if not isinstance(value, dict) or set(value) != _BROWSER_KEYS:
        _refuse()
    return BrowserServiceConfig(
        source_root=_absolute_path(value.get("source_root")),
        python_executable=_absolute_path(value.get("python_executable")),
        node_executable=_absolute_path(value.get("node_executable")),
        mcp_cli_path=_absolute_path(value.get("mcp_cli_path")),
        chrome_executable=_absolute_path(value.get("chrome_executable")),
        relay_root=_absolute_path(value.get("relay_root")),
        output_root=_absolute_path(value.get("output_root")),
        home_dir=_absolute_path(value.get("home_dir")),
        tmp_dir=_absolute_path(value.get("tmp_dir")),
        tool_catalog_file=_absolute_path(value.get("tool_catalog_file")),
        startup_timeout_seconds=_bounded_timeout(value.get("startup_timeout_seconds")),
    )


def _lease(value: object) -> StableWorkbenchActionLease:
    if not isinstance(value, dict) or set(value) != _LEASE_KEYS:
        _refuse()
    scopes = value.get("required_scopes")
    paths = value.get("allowed_paths")
    if scopes != ["workbench.action"]:
        _refuse()
    if (
        not isinstance(paths, list)
        or not 1 <= len(paths) <= 64
        or any(type(item) is not str or not item for item in paths)
        or len(paths) != len(set(paths))
    ):
        _refuse()
    committed = value.get("committed_head")
    if committed is not None and (
        type(committed) is not str
        or len(committed) != 40
        or any(character not in "0123456789abcdef" for character in committed)
    ):
        _refuse()
    expiry = value.get("lease_expires_at_ms")
    if type(expiry) is not int or not 0 <= expiry < 2**63:
        _refuse()
    try:
        return StableWorkbenchActionLease(
            expected_subject_digest=value["expected_subject_digest"],  # type: ignore[arg-type]
            expected_client_ref=value["expected_client_ref"],  # type: ignore[arg-type]
            resource=value["resource"],  # type: ignore[arg-type]
            required_scopes=("workbench.action",),
            project_ref=value["project_ref"],  # type: ignore[arg-type]
            context_ref=value["context_ref"],  # type: ignore[arg-type]
            responsibility_ref=value["responsibility_ref"],  # type: ignore[arg-type]
            operation_ref=value["operation_ref"],  # type: ignore[arg-type]
            owner_ref=value["owner_ref"],  # type: ignore[arg-type]
            generation=value["generation"],  # type: ignore[arg-type]
            allowed_paths=tuple(paths),
            committed_head=committed,
            lease_expires_at_ms=expiry,
        )
    except (KeyError, TypeError, ValueError):
        _refuse()
    raise AssertionError("unreachable")


def parse_service_config(value: object) -> ServiceConfig:
    if not isinstance(value, dict):
        _refuse()
    schema = value.get("schema")
    if schema == SERVICE_SCHEMA:
        if set(value) != _CONFIG_KEYS:
            _refuse()
        browser = None
    elif schema == SERVICE_SCHEMA_V2:
        if set(value) != _CONFIG_KEYS_V2:
            _refuse()
        browser = parse_browser_service_config(value.get("browser"))
    else:
        _refuse()
    if value.get("bind_host") != "127.0.0.1":
        _refuse()
    ttl = _bounded_int(value.get("action_ttl_ms"), minimum=1000, maximum=MAX_ACTION_TTL_MS)
    return ServiceConfig(
        schema=schema,
        policy_file=_absolute_path(value.get("policy_file")),
        project_root=_absolute_path(value.get("project_root")),
        audit_directory=_absolute_path(value.get("audit_directory")),
        artifact_directory=_absolute_path(value.get("artifact_directory")),
        host_id=_host_id(value.get("host_id")),
        action_key_file=_absolute_path(value.get("action_key_file")),
        bind_host="127.0.0.1",
        bind_port=_bounded_int(value.get("bind_port"), minimum=1, maximum=65535),
        incoming_authority=_incoming_authority(value.get("incoming_authority")),
        max_concurrency=_bounded_int(
            value.get("max_concurrency"), minimum=1, maximum=MAX_CONCURRENCY
        ),
        io_timeout_seconds=_bounded_timeout(value.get("io_timeout_seconds")),
        close_timeout_seconds=_bounded_timeout(value.get("close_timeout_seconds")),
        action_ttl_ms=ttl,
        lease=_lease(value.get("lease")),
        browser=browser,
    )


def _secure_json(path: str, *, maximum: int) -> dict[str, object]:
    selected = Path(_absolute_path(path))
    try:
        before = selected.lstat()
    except OSError:
        _refuse()
    if (
        stat.S_ISLNK(before.st_mode)
        or not stat.S_ISREG(before.st_mode)
        or before.st_nlink != 1
        or before.st_uid != os.geteuid()
        or stat.S_IMODE(before.st_mode) & 0o022
    ):
        _refuse()
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    nonblock = getattr(os, "O_NONBLOCK", 0)
    cloexec = getattr(os, "O_CLOEXEC", 0)
    if not nofollow or not nonblock or not cloexec:
        _refuse()
    fd = -1
    chunks: list[bytes] = []
    primary: BaseException | None = None
    cleanup: BaseException | None = None
    try:
        fd = os.open(selected, os.O_RDONLY | nofollow | nonblock | cloexec)
        opened = os.fstat(fd)
        if (
            opened.st_dev != before.st_dev
            or opened.st_ino != before.st_ino
            or not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink != 1
            or opened.st_uid != os.geteuid()
            or stat.S_IMODE(opened.st_mode) & 0o022
            or os.get_inheritable(fd)
        ):
            _refuse()
        total = 0
        while True:
            chunk = os.read(fd, min(4096, maximum + 1 - total))
            if not chunk:
                break
            total += len(chunk)
            if total > maximum:
                _refuse()
            chunks.append(chunk)
    except BaseException as error:
        primary = error
    finally:
        if fd >= 0:
            try:
                os.close(fd)
            except BaseException as error:
                cleanup = error
    if cleanup is not None:
        raise ServiceConfigurationError("SERVICE_STARTUP_CLEANUP_UNCERTAIN") from cleanup
    if primary is not None:
        if isinstance(primary, ServiceConfigurationError):
            raise primary
        _refuse()
    try:
        after = selected.lstat()
    except OSError:
        _refuse()
    if (
        after.st_dev != before.st_dev
        or after.st_ino != before.st_ino
        or after.st_uid != before.st_uid
        or after.st_mode != before.st_mode
        or after.st_nlink != before.st_nlink
    ):
        _refuse()
    try:
        decoded = b"".join(chunks).decode("ascii", errors="strict")
        result = json.loads(
            decoded,
            object_pairs_hook=_closed_object,
            parse_constant=_reject_constant,
        )
    except ServiceConfigurationError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
        _refuse()
    if not isinstance(result, dict):
        _refuse()
    return result


def load_service_config(path: str) -> ServiceConfig:
    return parse_service_config(_secure_json(path, maximum=MAX_CONFIG_BYTES))


def _secure_action_key(path: str) -> bytes:
    selected = Path(_absolute_path(path))
    try:
        before = selected.lstat()
    except OSError:
        _refuse()
    if (
        stat.S_ISLNK(before.st_mode)
        or not stat.S_ISREG(before.st_mode)
        or before.st_nlink != 1
        or before.st_uid != os.geteuid()
        or stat.S_IMODE(before.st_mode) != 0o600
        or before.st_size not in (64, 65)
    ):
        _refuse()
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    nonblock = getattr(os, "O_NONBLOCK", 0)
    cloexec = getattr(os, "O_CLOEXEC", 0)
    if not nofollow or not nonblock or not cloexec:
        _refuse()
    fd = -1
    try:
        fd = os.open(selected, os.O_RDONLY | nofollow | nonblock | cloexec)
        opened = os.fstat(fd)
        if (
            opened.st_dev != before.st_dev
            or opened.st_ino != before.st_ino
            or not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink != 1
            or opened.st_uid != os.geteuid()
            or stat.S_IMODE(opened.st_mode) != 0o600
            or os.get_inheritable(fd)
        ):
            _refuse()
        raw = b""
        while len(raw) <= 65:
            chunk = os.read(fd, 66 - len(raw))
            if not chunk:
                break
            raw += chunk
        if len(raw) > 65:
            _refuse()
    except ServiceConfigurationError:
        raise
    except (OSError, TypeError, ValueError):
        _refuse()
    finally:
        if fd >= 0:
            try:
                os.close(fd)
            except OSError as error:
                raise ServiceConfigurationError(
                    "SERVICE_STARTUP_CLEANUP_UNCERTAIN"
                ) from error
    try:
        after = selected.lstat()
    except OSError:
        _refuse()
    if (
        after.st_dev != before.st_dev
        or after.st_ino != before.st_ino
        or after.st_mode != before.st_mode
        or after.st_nlink != before.st_nlink
        or after.st_uid != before.st_uid
    ):
        _refuse()
    if raw.endswith(b"\n"):
        raw = raw[:-1]
    if len(raw) != 64 or any(byte not in b"0123456789abcdef" for byte in raw):
        _refuse()
    return bytes.fromhex(raw.decode("ascii"))


def _open_safe_directory(path: str) -> int:
    selected = Path(_absolute_path(path))
    try:
        before = selected.lstat()
    except OSError:
        _refuse()
    if (
        stat.S_ISLNK(before.st_mode)
        or not stat.S_ISDIR(before.st_mode)
        or before.st_uid != os.geteuid()
        or stat.S_IMODE(before.st_mode) & 0o022
    ):
        _refuse()
    directory = getattr(os, "O_DIRECTORY", 0)
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    cloexec = getattr(os, "O_CLOEXEC", 0)
    if not directory or not nofollow or not cloexec:
        _refuse()
    fd = -1
    try:
        fd = os.open(selected, os.O_RDONLY | directory | nofollow | cloexec)
        opened = os.fstat(fd)
        if (
            opened.st_dev != before.st_dev
            or opened.st_ino != before.st_ino
            or not stat.S_ISDIR(opened.st_mode)
            or opened.st_uid != os.geteuid()
            or stat.S_IMODE(opened.st_mode) & 0o022
            or os.get_inheritable(fd)
        ):
            _refuse()
        return fd
    except BaseException as error:
        if fd >= 0:
            try:
                os.close(fd)
            except BaseException as cleanup_error:
                raise ServiceConfigurationError(
                    "SERVICE_STARTUP_CLEANUP_UNCERTAIN"
                ) from cleanup_error
        if isinstance(error, ServiceConfigurationError):
            raise
        _refuse()
    raise AssertionError("unreachable")


def reserve_loopback_socket(
    config: ServiceConfig, *, _allow_ephemeral_for_test: bool = False
) -> socket.socket:
    if not isinstance(config, ServiceConfig) or config.bind_host != "127.0.0.1":
        _refuse("SERVICE_BIND_REFUSED")
    port = config.bind_port
    if port == 0 and not _allow_ephemeral_for_test:
        _refuse("SERVICE_BIND_REFUSED")
    if type(port) is not int or not 0 <= port <= 65535:
        _refuse("SERVICE_BIND_REFUSED")
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.set_inheritable(False)
        if sock.get_inheritable():
            _refuse("SERVICE_BIND_REFUSED")
        sock.bind((config.bind_host, port))
        return sock
    except BaseException:
        try:
            sock.close()
        except BaseException as cleanup_error:
            raise ServiceConfigurationError(
                "SERVICE_STARTUP_CLEANUP_UNCERTAIN"
            ) from cleanup_error
        raise ServiceConfigurationError("SERVICE_BIND_REFUSED") from None


def is_ready(runtime: object, config: ServiceConfig, state: ServiceState) -> bool:
    if (
        not isinstance(config, ServiceConfig)
        or not isinstance(state, ServiceState)
        or not state.lifespan_started
        or not state.socket_owned
        or state.stopping
        or not callable(getattr(runtime, "resolve_binding", None))
    ):
        return False
    stable = config.lease
    caller = ActionCaller(
        subject_digest=stable.expected_subject_digest,
        client_ref=stable.expected_client_ref,
        resource=stable.resource,
        scopes=stable.required_scopes,
        expires_at=max(1, stable.lease_expires_at_ms // 1000),
    )
    try:
        binding = runtime.resolve_binding(caller, stable.project_ref)
    except Exception:
        return False
    if binding is None or binding.caller != caller or binding.project_ref != stable.project_ref:
        return False
    scope = binding.scope
    return (
        scope.context_ref == stable.context_ref
        and scope.responsibility_ref == stable.responsibility_ref
        and scope.operation_ref == stable.operation_ref
        and scope.owner_ref == stable.owner_ref
        and scope.generation == stable.generation
        and scope.allowed_paths == stable.allowed_paths
        and scope.committed_head == stable.committed_head
        and scope.expires_at_ms == stable.lease_expires_at_ms
    )


def shutdown_exit_code(outcome: ShutdownOutcome) -> int:
    return {
        ShutdownOutcome.CLEAN: 0,
        ShutdownOutcome.RUNTIME_CLOSE_INCOMPLETE: 3,
        ShutdownOutcome.RUNTIME_CLOSE_UNCERTAIN: 4,
        ShutdownOutcome.SERVER_FAILED: 5,
    }[outcome]


async def _close_runtime(
    runtime: WorkbenchActionRuntime, config: ServiceConfig, state: ServiceState
) -> None:
    state.stopping = True
    if state.runtime_close_attempted:
        return
    state.runtime_close_attempted = True
    previous = state.shutdown_outcome
    runtime.revoke()
    try:
        await runtime.aclose(timeout=config.close_timeout_seconds)
    except RuntimeCloseIncomplete:
        state.shutdown_outcome = ShutdownOutcome.RUNTIME_CLOSE_INCOMPLETE
        raise
    except RuntimeCloseUncertain:
        state.shutdown_outcome = ShutdownOutcome.RUNTIME_CLOSE_UNCERTAIN
        raise
    else:
        if previous is None:
            state.shutdown_outcome = ShutdownOutcome.CLEAN


async def _rollback_runtime(
    runtime: WorkbenchActionRuntime, config: ServiceConfig, state: ServiceState
) -> None:
    try:
        await _close_runtime(runtime, config, state)
    except (RuntimeCloseIncomplete, RuntimeCloseUncertain):
        pass


def _call_receipt_sink(event: object) -> None:
    # Stable process telemetry only. It is deliberately not another action
    # ledger or retry owner. No patch text, action token, path, credential, or
    # absolute project location is emitted.
    try:
        if not isinstance(event, dict):
            return
        print(
            "MMX_WORKBENCH_ACTION_CALL_RECEIVED "
            + json.dumps(event, sort_keys=True, separators=(",", ":")),
            file=sys.stderr,
            flush=True,
        )
    except Exception:
        return


async def create_runtime(config: ServiceConfig) -> WorkbenchActionRuntime:
    policy_document = _secure_json(config.policy_file, maximum=MAX_POLICY_BYTES)
    try:
        policy = load_resource_policy(policy_document)
    except Exception:
        _refuse()
    if policy.required_scopes != ("workbench.action",):
        _refuse()
    cache = BoundedJwksCache(
        policy=policy,
        fetcher=HttpxJwksFetcher(policy),
        monotonic=time.monotonic,
    )
    authenticator = JwtAuthenticator(policy=policy, jwks_cache=cache)
    action_token_key = _secure_action_key(config.action_key_file)
    project_fd = -1
    audit_fd = -1
    artifact_fd = -1
    runtime: WorkbenchActionRuntime | None = None
    primary_error: BaseException | None = None
    cleanup_errors: list[BaseException] = []
    try:
        project_fd = _open_safe_directory(config.project_root)
        audit_fd = _open_safe_directory(config.audit_directory)
        artifact_fd = _open_safe_directory(config.artifact_directory)
        runtime = WorkbenchActionRuntime.open(
            authenticator=authenticator,
            policy=policy,
            now=lambda: int(time.time()),
            clock_ms=lambda: int(time.time() * 1000),
            project_directory_fd=project_fd,
            audit_directory_fd=audit_fd,
            host_artifact_fd=artifact_fd,
            host_id=config.host_id,
            lease=config.lease,
            action_token_key=action_token_key,
            allowed_hosts=config.allowed_hosts,
            call_receipt_sink=_call_receipt_sink,
            allowed_origins=config.allowed_origins,
            max_concurrency=config.max_concurrency,
            io_timeout_seconds=config.io_timeout_seconds,
            action_ttl_ms=config.action_ttl_ms,
        )
        if runtime.services.allowed_hosts != config.allowed_hosts:
            _refuse()
    except BaseException as error:
        primary_error = error
    finally:
        for descriptor in (artifact_fd, audit_fd, project_fd):
            if descriptor >= 0:
                try:
                    os.close(descriptor)
                except BaseException as error:
                    cleanup_errors.append(error)
    if cleanup_errors:
        if runtime is not None:
            await _rollback_runtime(runtime, config, ServiceState())
        raise ServiceConfigurationError(
            "SERVICE_STARTUP_CLEANUP_UNCERTAIN"
        ) from cleanup_errors[0]
    if primary_error is not None:
        if isinstance(primary_error, RuntimeCloseUncertain):
            raise ServiceConfigurationError(
                "SERVICE_STARTUP_CLEANUP_UNCERTAIN"
            ) from primary_error
        if runtime is not None:
            rollback_state = ServiceState()
            await _rollback_runtime(runtime, config, rollback_state)
            if rollback_state.shutdown_outcome in (
                ShutdownOutcome.RUNTIME_CLOSE_INCOMPLETE,
                ShutdownOutcome.RUNTIME_CLOSE_UNCERTAIN,
            ):
                raise ServiceConfigurationError(
                    "SERVICE_STARTUP_CLEANUP_UNCERTAIN"
                ) from primary_error
        if isinstance(primary_error, ServiceConfigurationError):
            raise primary_error
        _refuse()
    if runtime is None:
        _refuse()
    return runtime


def create_browser_sibling(
    runtime: WorkbenchActionRuntime,
    config: ServiceConfig,
):
    """Compose Browser from the exact existing Workbench runtime services.

    V1 stays action-only. V2 creates no second runtime, lease, artifact store,
    token key, auth policy, process owner, or lifecycle.
    """
    if not isinstance(runtime, WorkbenchActionRuntime) or not isinstance(config, ServiceConfig):
        _refuse()
    selected = config.browser
    if selected is None:
        return None
    try:
        from integrations.workbench_browser_mcp.deployment import create_browser_deployment
        from integrations.workbench_browser_mcp.resource_port import BrowserHostConfig

        catalog = _secure_json(
            selected.tool_catalog_file,
            maximum=MAX_BROWSER_CATALOG_BYTES,
        )
        host_config = BrowserHostConfig(
            source_root=Path(selected.source_root),
            python_executable=selected.python_executable,
            node_executable=selected.node_executable,
            mcp_cli_path=selected.mcp_cli_path,
            chrome_executable=selected.chrome_executable,
            relay_root=Path(selected.relay_root),
            output_root=Path(selected.output_root),
            home_dir=selected.home_dir,
            tmp_dir=selected.tmp_dir,
            startup_timeout_seconds=selected.startup_timeout_seconds,
        )
        return create_browser_deployment(
            services=runtime.services,
            host_config=host_config,
            tool_catalog=catalog,
            # Persistent authenticated profiles remain held until the existing
            # profile owner can provide an exclusive typed grant.
            profile_resolver=lambda _profile_ref: None,
        )
    except ServiceConfigurationError:
        raise
    except Exception as error:
        raise ServiceConfigurationError("SERVICE_CONFIGURATION_REFUSED") from error


def build_service_app(
    runtime: WorkbenchActionRuntime,
    config: ServiceConfig,
    state: ServiceState,
):
    from starlette.applications import Starlette
    from starlette.responses import PlainTextResponse
    from starlette.routing import Mount, Route

    inner = runtime.server.streamable_http_app()
    browser_deployment = create_browser_sibling(runtime, config)
    browser_inner = (
        browser_deployment.server.streamable_http_app()
        if browser_deployment is not None
        else None
    )

    async def health(_request):
        return PlainTextResponse("OK\n", status_code=200)

    async def ready(_request):
        if is_ready(runtime, config, state):
            return PlainTextResponse("READY\n", status_code=200)
        return PlainTextResponse("NOT_READY\n", status_code=503)

    @asynccontextmanager
    async def lifespan(_app):
        try:
            async with AsyncExitStack() as stack:
                await stack.enter_async_context(runtime.server.session_manager.run())
                if browser_deployment is not None:
                    await stack.enter_async_context(
                        browser_deployment.server.session_manager.run()
                    )
                state.lifespan_started = True
                try:
                    yield
                finally:
                    await _close_runtime(runtime, config, state)
            state.lifespan_completed = True
        except BaseException:
            if state.shutdown_outcome in (None, ShutdownOutcome.CLEAN):
                state.shutdown_outcome = ShutdownOutcome.SERVER_FAILED
            raise
        finally:
            state.stopping = True
            if not state.runtime_close_attempted:
                await _close_runtime(runtime, config, state)

    routes = [
        Route("/healthz", health, methods=["GET"]),
        Route("/readyz", ready, methods=["GET"]),
    ]
    if browser_inner is not None:
        routes.append(Mount(config.browser.mount_path, app=browser_inner))
    routes.append(Mount("/", app=inner))
    return Starlette(routes=routes, lifespan=lifespan)


async def run_service(config: ServiceConfig) -> int:
    runtime = await create_runtime(config)
    state = ServiceState()
    sock: socket.socket | None = None
    server = None
    try:
        try:
            sock = reserve_loopback_socket(config)
        except ServiceConfigurationError:
            await _rollback_runtime(runtime, config, state)
            if state.shutdown_outcome in (
                ShutdownOutcome.RUNTIME_CLOSE_INCOMPLETE,
                ShutdownOutcome.RUNTIME_CLOSE_UNCERTAIN,
            ):
                return shutdown_exit_code(state.shutdown_outcome)
            raise
        state.socket_owned = True
        app = build_service_app(runtime, config, state)
        import uvicorn

        class _ServiceServer(uvicorn.Server):
            @contextmanager
            def capture_signals(self):
                import signal
                import threading

                if threading.current_thread() is not threading.main_thread():
                    yield
                    return
                handled = [signal.SIGINT, signal.SIGTERM]
                if sys.platform == "win32" and hasattr(signal, "SIGBREAK"):
                    handled.append(signal.SIGBREAK)
                originals = {sig: signal.signal(sig, self.handle_exit) for sig in handled}
                try:
                    yield
                finally:
                    for sig, handler in originals.items():
                        signal.signal(sig, handler)

        uvicorn_config = uvicorn.Config(
            app,
            host=config.bind_host,
            port=config.bind_port,
            log_level="info",
            access_log=False,
            proxy_headers=False,
            lifespan="on",
            timeout_graceful_shutdown=config.close_timeout_seconds,
        )
        server = _ServiceServer(uvicorn_config)
        try:
            await server.serve(sockets=[sock])
        except (RuntimeCloseIncomplete, RuntimeCloseUncertain):
            pass
        except BaseException:
            if state.shutdown_outcome in (None, ShutdownOutcome.CLEAN):
                state.shutdown_outcome = ShutdownOutcome.SERVER_FAILED
    finally:
        lifespan = getattr(server, "lifespan", None)
        lifecycle_failed = (
            not state.lifespan_completed
            or bool(getattr(server, "force_exit", False))
            or any(
                bool(getattr(lifespan, flag, False))
                for flag in ("startup_failed", "shutdown_failed", "error_occurred")
            )
        )
        if lifecycle_failed and state.shutdown_outcome in (None, ShutdownOutcome.CLEAN):
            state.shutdown_outcome = ShutdownOutcome.SERVER_FAILED
        state.socket_owned = False
        socket_close_failed = False
        if sock is not None and sock.fileno() >= 0:
            try:
                sock.close()
                socket_close_failed = sock.fileno() != -1
            except OSError:
                socket_close_failed = True
        if not state.runtime_close_attempted:
            await _rollback_runtime(runtime, config, state)
        if socket_close_failed and state.shutdown_outcome in (None, ShutdownOutcome.CLEAN):
            state.shutdown_outcome = ShutdownOutcome.SERVER_FAILED
        if state.shutdown_outcome is None:
            state.shutdown_outcome = ShutdownOutcome.SERVER_FAILED
    return shutdown_exit_code(state.shutdown_outcome)


def run_configured_service(path: str) -> int:
    try:
        config = load_service_config(path)
        return asyncio.run(run_service(config))
    except ServiceConfigurationError as error:
        print(error.code, file=sys.stderr, flush=True)
        return 5 if error.code == "SERVICE_STARTUP_CLEANUP_UNCERTAIN" else 2
    except BaseException:
        print("SERVICE_RUNTIME_FAILED", file=sys.stderr, flush=True)
        return 5


__all__ = [
    "SERVICE_SCHEMA",
    "ServiceConfig",
    "ServiceConfigurationError",
    "ServiceState",
    "ShutdownOutcome",
    "build_service_app",
    "create_runtime",
    "is_ready",
    "load_service_config",
    "parse_service_config",
    "reserve_loopback_socket",
    "run_configured_service",
    "run_service",
    "shutdown_exit_code",
]
