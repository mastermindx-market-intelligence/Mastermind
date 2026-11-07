"""Loopback-only process composition for Workspace Agent candidate return.

This service turns the accepted Workspace return contracts into one deployable
local endpoint without creating another lifecycle, target, result, retry,
credential, or provider-control plane.  It composes existing owners only:

* Business MCP auth verifies one approved Workspace Agent principal.
* Executive Runtime is opened existing-only and supplies current target truth.
* Wake evidence supplies the exact Agent Dialogue physical thread.
* Agent Dialogue remains the only candidate transport/effect owner.
* A host-only HMAC key signs short-lived opaque return references.

The service itself never publishes or triggers a Workspace Agent and never
accepts a returned candidate as company truth.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, contextmanager
from collections.abc import Mapping
import dataclasses
from datetime import datetime, timezone
from http import HTTPStatus
import json
import os
from pathlib import Path
import socket
import stat
import sys
import time
from typing import Any
from urllib.parse import urlsplit

from integrations.business_mcp_auth.audit import (
    AuditAcquisitionUncertain,
    DurableAuthAuditSink,
)
from integrations.business_mcp_auth.contracts import load_resource_policy
from integrations.business_mcp_auth.jwks import (
    BoundedJwksCache,
    HttpxJwksFetcher,
)
from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator
from integrations.business_mcp_auth.mcp_adapter import MastermindTokenVerifier
from control_plane.executive_runtime import Runtime
from integrations.workspace_agent_return import (
    WorkspaceCandidateReturnGateway,
    WorkspaceReturnTicketCodec,
)
from integrations.slack_agent_dialogue.service import (
    DialogueServiceError,
    call_service,
)
from integrations.workspace_agent_return_app import (
    REQUIRED_SCOPE,
    create_authenticated_return_server,
)
from integrations.workspace_agent_runtime_binding import (
    ExecutiveWorkspaceReturnBindingResolver,
)


SERVICE_SCHEMA = "mastermind.workspace_agent_return_service.v1"
MAX_CONFIG_BYTES = 64 * 1024
MAX_POLICY_BYTES = 64 * 1024
_CONFIG_KEYS = frozenset(
    {
        "schema",
        "policy_file",
        "ticket_key_file",
        "audit_directory",
        "executive_runtime_root",
        "dialogue_socket_path",
        "bind_host",
        "bind_port",
        "incoming_authority",
        "close_timeout_seconds",
    }
)


class ServiceConfigurationError(RuntimeError):
    """Closed startup/runtime refusal without private dependency detail."""

    _CODES = frozenset(
        {
            "SERVICE_CONFIGURATION_REFUSED",
            "SERVICE_BIND_REFUSED",
            "SERVICE_STARTUP_CLEANUP_UNCERTAIN",
        }
    )

    def __init__(self, code: str = "SERVICE_CONFIGURATION_REFUSED") -> None:
        if code not in self._CODES:
            raise ValueError("unknown Workspace return service error code")
        self.code = code
        super().__init__(code)


@dataclasses.dataclass(frozen=True, slots=True)
class ServiceConfig:
    schema: str
    policy_file: str
    ticket_key_file: str
    audit_directory: str
    executive_runtime_root: str
    dialogue_socket_path: str
    bind_host: str
    bind_port: int
    incoming_authority: str
    close_timeout_seconds: float

    @property
    def allowed_hosts(self) -> tuple[str, ...]:
        return (self.incoming_authority,)


@dataclasses.dataclass(slots=True)
class ServiceState:
    lifespan_started: bool = False
    lifespan_completed: bool = False
    socket_owned: bool = False
    stopping: bool = False
    server_failed: bool = False
    audit_close_attempted: bool = False
    audit_close_uncertain: bool = False


@dataclasses.dataclass(frozen=True, slots=True)
class WorkspaceReturnServiceRuntime:
    executive_runtime: Runtime
    gateway: WorkspaceCandidateReturnGateway
    server: object
    dialogue_socket_path: Path
    audit_sink: DurableAuthAuditSink


def _refuse(code: str = "SERVICE_CONFIGURATION_REFUSED") -> None:
    raise ServiceConfigurationError(code)


def _closed_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            _refuse()
        value[key] = item
    return value


def _reject_constant(_value: str) -> object:
    _refuse()


def _absolute_path(value: object) -> str:
    if (
        type(value) is not str
        or not value
        or not value.startswith("/")
        or "\x00" in value
    ):
        _refuse()
    return value


def _bounded_port(value: object) -> int:
    if type(value) is not int or not 1 <= value <= 65535:
        _refuse()
    return value


def _bounded_timeout(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _refuse()
    selected = float(value)
    if not 0 < selected <= 120.0:
        _refuse()
    return selected


def _incoming_authority(value: object) -> str:
    if type(value) is not str or not value or len(value) > 256:
        _refuse()
    if any(ord(character) <= 32 or ord(character) == 127 for character in value):
        _refuse()
    try:
        parsed = urlsplit("//" + value)
        port = parsed.port
    except (TypeError, ValueError):
        _refuse()
    if (
        not parsed.hostname
        or port is None
        or not 1 <= port <= 65535
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path
        or parsed.query
        or parsed.fragment
    ):
        _refuse()
    return value


def parse_service_config(value: object) -> ServiceConfig:
    if not isinstance(value, dict) or set(value) != _CONFIG_KEYS:
        _refuse()
    if value.get("schema") != SERVICE_SCHEMA or value.get("bind_host") != "127.0.0.1":
        _refuse()
    bind_port = _bounded_port(value.get("bind_port"))
    authority = _incoming_authority(value.get("incoming_authority"))
    return ServiceConfig(
        schema=SERVICE_SCHEMA,
        policy_file=_absolute_path(value.get("policy_file")),
        ticket_key_file=_absolute_path(value.get("ticket_key_file")),
        audit_directory=_absolute_path(value.get("audit_directory")),
        executive_runtime_root=_absolute_path(value.get("executive_runtime_root")),
        dialogue_socket_path=_absolute_path(value.get("dialogue_socket_path")),
        bind_host="127.0.0.1",
        bind_port=bind_port,
        incoming_authority=authority,
        close_timeout_seconds=_bounded_timeout(value.get("close_timeout_seconds")),
    )


def _secure_regular_bytes(
    path: str,
    *,
    maximum: int,
    exact_mode: int | None = None,
) -> bytes:
    selected = Path(_absolute_path(path))
    try:
        before = selected.lstat()
    except OSError:
        _refuse()
    mode = stat.S_IMODE(before.st_mode)
    if (
        stat.S_ISLNK(before.st_mode)
        or not stat.S_ISREG(before.st_mode)
        or before.st_nlink != 1
        or before.st_uid != os.geteuid()
        or (exact_mode is None and mode & 0o022)
        or (exact_mode is not None and mode != exact_mode)
        or before.st_size <= 0
        or before.st_size > maximum
    ):
        _refuse()

    nofollow = getattr(os, "O_NOFOLLOW", 0)
    nonblock = getattr(os, "O_NONBLOCK", 0)
    cloexec = getattr(os, "O_CLOEXEC", 0)
    if not nofollow or not nonblock or not cloexec:
        _refuse()

    descriptor = -1
    chunks: list[bytes] = []
    primary_error: BaseException | None = None
    close_error: BaseException | None = None
    try:
        descriptor = os.open(
            selected,
            os.O_RDONLY | nofollow | nonblock | cloexec,
        )
        opened = os.fstat(descriptor)
        opened_mode = stat.S_IMODE(opened.st_mode)
        if (
            opened.st_dev != before.st_dev
            or opened.st_ino != before.st_ino
            or not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink != 1
            or opened.st_uid != before.st_uid
            or (exact_mode is None and opened_mode & 0o022)
            or (exact_mode is not None and opened_mode != exact_mode)
            or os.get_inheritable(descriptor)
        ):
            _refuse()
        total = 0
        while True:
            chunk = os.read(
                descriptor,
                min(4096, maximum + 1 - total),
            )
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > maximum:
                _refuse()
    except BaseException as error:
        primary_error = error
    finally:
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except BaseException as error:
                close_error = error

    if close_error is not None:
        raise ServiceConfigurationError(
            "SERVICE_STARTUP_CLEANUP_UNCERTAIN"
        ) from close_error
    if primary_error is not None:
        if isinstance(primary_error, ServiceConfigurationError):
            raise primary_error
        _refuse()

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
        or after.st_size != before.st_size
    ):
        _refuse()
    return b"".join(chunks)


def _secure_json(path: str, *, maximum: int) -> dict[str, object]:
    raw = _secure_regular_bytes(path, maximum=maximum)
    try:
        document = json.loads(
            raw.decode("ascii", errors="strict"),
            object_pairs_hook=_closed_object,
            parse_constant=_reject_constant,
        )
    except ServiceConfigurationError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
        _refuse()
    if not isinstance(document, dict):
        _refuse()
    return document


def _secure_ticket_key(path: str) -> bytes:
    raw = _secure_regular_bytes(path, maximum=65, exact_mode=0o600)
    if raw.endswith(b"\n"):
        raw = raw[:-1]
    if len(raw) != 64 or any(byte not in b"0123456789abcdef" for byte in raw):
        _refuse()
    try:
        return bytes.fromhex(raw.decode("ascii"))
    except (UnicodeDecodeError, ValueError):
        _refuse()
    raise AssertionError("unreachable")


def _open_safe_directory(path: str) -> int:
    """Open one owner-controlled directory without granting audit authority."""

    selected = Path(_absolute_path(path))
    try:
        before = selected.lstat()
    except OSError:
        _refuse()
    directory = getattr(os, "O_DIRECTORY", 0)
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    cloexec = getattr(os, "O_CLOEXEC", 0)
    if (
        not directory
        or not nofollow
        or not cloexec
        or stat.S_ISLNK(before.st_mode)
        or not stat.S_ISDIR(before.st_mode)
        or before.st_uid != os.geteuid()
        or stat.S_IMODE(before.st_mode) & 0o022
    ):
        _refuse()
    descriptor = -1
    try:
        descriptor = os.open(
            selected,
            os.O_RDONLY | directory | nofollow | cloexec,
        )
        opened = os.fstat(descriptor)
        if (
            opened.st_dev != before.st_dev
            or opened.st_ino != before.st_ino
            or not stat.S_ISDIR(opened.st_mode)
            or opened.st_uid != before.st_uid
            or stat.S_IMODE(opened.st_mode) & 0o022
            or os.get_inheritable(descriptor)
        ):
            _refuse()
        return descriptor
    except BaseException as error:
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except BaseException as cleanup_error:
                raise ServiceConfigurationError(
                    "SERVICE_STARTUP_CLEANUP_UNCERTAIN"
                ) from cleanup_error
        if isinstance(error, ServiceConfigurationError):
            raise
        _refuse()
    raise AssertionError("unreachable")


def _open_audit_sink(path: str, *, policy_id: str) -> DurableAuthAuditSink:
    """Acquire the existing durable Business-auth audit owner."""

    directory_fd = _open_safe_directory(path)
    sink: DurableAuthAuditSink | None = None
    primary_error: BaseException | None = None
    try:
        sink = DurableAuthAuditSink.open(
            directory_fd,
            policy_id=policy_id,
        )
    except BaseException as error:
        primary_error = error
    try:
        os.close(directory_fd)
    except BaseException as close_error:
        if sink is not None:
            try:
                sink.close()
            except BaseException:
                pass
        raise ServiceConfigurationError(
            "SERVICE_STARTUP_CLEANUP_UNCERTAIN"
        ) from close_error
    if primary_error is not None:
        if isinstance(primary_error, AuditAcquisitionUncertain):
            raise ServiceConfigurationError(
                "SERVICE_STARTUP_CLEANUP_UNCERTAIN"
            ) from primary_error
        _refuse()
    assert sink is not None
    return sink


def load_service_config(path: str) -> ServiceConfig:
    return parse_service_config(_secure_json(path, maximum=MAX_CONFIG_BYTES))


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _dialogue_socket_is_trusted(path: Path) -> bool:
    """Verify the configured local dialogue target before every carrier effect."""

    try:
        parent = path.parent.lstat()
        observed = path.lstat()
    except OSError:
        return False
    parent_mode = stat.S_IMODE(parent.st_mode)
    socket_mode = stat.S_IMODE(observed.st_mode)
    return bool(
        stat.S_ISDIR(parent.st_mode)
        and not stat.S_ISLNK(parent.st_mode)
        and parent.st_uid == os.geteuid()
        and parent_mode in {int("700", 8), int("710", 8)}
        and stat.S_ISSOCK(observed.st_mode)
        and not stat.S_ISLNK(observed.st_mode)
        and observed.st_uid == os.geteuid()
        and socket_mode in {int("600", 8), int("660", 8)}
    )


async def _trusted_dialogue_call(
    socket_path: Path,
    request: Mapping[str, Any],
) -> dict[str, Any]:
    if not _dialogue_socket_is_trusted(Path(socket_path)):
        raise DialogueServiceError("SERVICE_UNAVAILABLE")
    return await call_service(socket_path, request)


def create_runtime(config: ServiceConfig) -> WorkspaceReturnServiceRuntime:
    """Compose existing owners; perform no provider or Agent Dialogue effect."""

    if not isinstance(config, ServiceConfig):
        _refuse()
    policy_document = _secure_json(config.policy_file, maximum=MAX_POLICY_BYTES)
    try:
        policy = load_resource_policy(policy_document)
    except Exception:
        _refuse()
    if (
        policy.required_scopes != (REQUIRED_SCOPE,)
        or len(policy.allowed_subject_digests) != 1
    ):
        _refuse()

    ticket_key = _secure_ticket_key(config.ticket_key_file)
    audit_sink = _open_audit_sink(
        config.audit_directory,
        policy_id=policy.policy_id,
    )
    try:
        executive_runtime = Runtime.at(
            config.executive_runtime_root,
            create=False,
        )
        binding_resolver = ExecutiveWorkspaceReturnBindingResolver(
            executive_runtime
        )
        gateway = WorkspaceCandidateReturnGateway(
            codec=WorkspaceReturnTicketCodec(ticket_key),
            binding_resolver=binding_resolver,
            socket_path=Path(config.dialogue_socket_path),
            clock_ms=lambda: int(time.time() * 1000),
            utc_now=_utc_now,
            service_call=_trusted_dialogue_call,
        )
        cache = BoundedJwksCache(
            policy=policy,
            fetcher=HttpxJwksFetcher(policy),
            monotonic=time.monotonic,
        )
        authenticator = JwtAuthenticator(
            policy=policy,
            jwks_cache=cache,
        )
        verifier = MastermindTokenVerifier(
            authenticator=authenticator,
            policy=policy,
            now=lambda: int(time.time()),
            audit_sink=audit_sink,
        )
        server = create_authenticated_return_server(
            gateway=gateway,
            policy=policy,
            token_verifier=verifier,
            allowed_hosts=config.allowed_hosts,
            allowed_origins=(),
        )
    except BaseException as error:
        try:
            audit_sink.close()
        except BaseException as cleanup_error:
            raise ServiceConfigurationError(
                "SERVICE_STARTUP_CLEANUP_UNCERTAIN"
            ) from cleanup_error
        if isinstance(error, ServiceConfigurationError):
            raise
        _refuse()

    return WorkspaceReturnServiceRuntime(
        executive_runtime=executive_runtime,
        gateway=gateway,
        server=server,
        dialogue_socket_path=Path(config.dialogue_socket_path),
        audit_sink=audit_sink,
    )

def reserve_loopback_socket(
    config: ServiceConfig,
    *,
    _allow_ephemeral_for_test: bool = False,
) -> socket.socket:
    if not isinstance(config, ServiceConfig) or config.bind_host != "127.0.0.1":
        _refuse("SERVICE_BIND_REFUSED")
    port = config.bind_port
    if port == 0 and not _allow_ephemeral_for_test:
        _refuse("SERVICE_BIND_REFUSED")
    if type(port) is not int or not 0 <= port <= 65535:
        _refuse("SERVICE_BIND_REFUSED")
    owned = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        owned.set_inheritable(False)
        if owned.get_inheritable():
            _refuse("SERVICE_BIND_REFUSED")
        owned.bind((config.bind_host, port))
        return owned
    except BaseException:
        try:
            owned.close()
        except BaseException as cleanup_error:
            raise ServiceConfigurationError(
                "SERVICE_STARTUP_CLEANUP_UNCERTAIN"
            ) from cleanup_error
        raise ServiceConfigurationError("SERVICE_BIND_REFUSED") from None


def is_ready(
    runtime: WorkspaceReturnServiceRuntime,
    state: ServiceState,
) -> bool:
    """Passive process/dependency readiness; never validates a specific ticket."""

    if (
        not isinstance(runtime, WorkspaceReturnServiceRuntime)
        or not isinstance(state, ServiceState)
        or not state.lifespan_started
        or not state.socket_owned
        or state.stopping
        or state.server_failed
    ):
        return False
    return _dialogue_socket_is_trusted(runtime.dialogue_socket_path)


def _close_audit(
    runtime: WorkspaceReturnServiceRuntime,
    state: ServiceState,
) -> None:
    if state.audit_close_attempted:
        if state.audit_close_uncertain:
            raise ServiceConfigurationError(
                "SERVICE_STARTUP_CLEANUP_UNCERTAIN"
            )
        return
    state.audit_close_attempted = True
    try:
        runtime.audit_sink.close()
    except BaseException as error:
        state.audit_close_uncertain = True
        state.server_failed = True
        raise ServiceConfigurationError(
            "SERVICE_STARTUP_CLEANUP_UNCERTAIN"
        ) from error


def build_service_app(
    runtime: WorkspaceReturnServiceRuntime,
    state: ServiceState,
):
    from starlette.applications import Starlette
    from starlette.responses import PlainTextResponse
    from starlette.routing import Mount, Route

    if not isinstance(runtime, WorkspaceReturnServiceRuntime):
        raise TypeError("runtime must be WorkspaceReturnServiceRuntime")
    inner = runtime.server.streamable_http_app()

    async def health(_request):
        return PlainTextResponse("OK\n", status_code=HTTPStatus.OK)

    async def ready(_request):
        if is_ready(runtime, state):
            return PlainTextResponse("READY\n", status_code=HTTPStatus.OK)
        return PlainTextResponse(
            "NOT_READY\n",
            status_code=HTTPStatus.SERVICE_UNAVAILABLE,
        )

    @asynccontextmanager
    async def lifespan(_app):
        try:
            async with runtime.server.session_manager.run():
                state.lifespan_started = True
                try:
                    yield
                finally:
                    state.stopping = True
            state.lifespan_completed = True
        except BaseException:
            state.server_failed = True
            raise
        finally:
            state.stopping = True
            try:
                _close_audit(runtime, state)
            except ServiceConfigurationError:
                state.server_failed = True

    return Starlette(
        routes=[
            Route("/healthz", health, methods=["GET"]),
            Route("/readyz", ready, methods=["GET"]),
            Mount("/", app=inner),
        ],
        lifespan=lifespan,
    )


async def run_service(config: ServiceConfig) -> int:
    """Run one pre-bound loopback server; installation remains a separate gate."""

    runtime = create_runtime(config)
    state = ServiceState()
    owned: socket.socket | None = None
    server = None
    try:
        owned = reserve_loopback_socket(config)
        state.socket_owned = True
        app = build_service_app(runtime, state)
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
                originals = {
                    item: signal.signal(item, self.handle_exit)
                    for item in handled
                }
                try:
                    yield
                finally:
                    for item, handler in originals.items():
                        signal.signal(item, handler)

        server = _ServiceServer(
            uvicorn.Config(
                app,
                host=config.bind_host,
                port=config.bind_port,
                log_level="info",
                access_log=False,
                proxy_headers=False,
                lifespan="on",
                timeout_graceful_shutdown=config.close_timeout_seconds,
            )
        )
        await server.serve(sockets=[owned])
    except ServiceConfigurationError:
        raise
    except BaseException:
        state.server_failed = True
    finally:
        state.stopping = True
        state.socket_owned = False
        close_failed = False
        if owned is not None and owned.fileno() >= 0:
            try:
                owned.close()
                close_failed = owned.fileno() != -1
            except OSError:
                close_failed = True
        if close_failed:
            state.server_failed = True
        if not state.audit_close_attempted:
            try:
                _close_audit(runtime, state)
            except ServiceConfigurationError:
                state.server_failed = True

    return 0 if state.lifespan_completed and not state.server_failed else 5


def run_configured_service(path: str) -> int:
    try:
        config = load_service_config(path)
        return asyncio.run(run_service(config))
    except ServiceConfigurationError as error:
        print(error.code, file=sys.stderr, flush=True)
        return (
            5
            if error.code == "SERVICE_STARTUP_CLEANUP_UNCERTAIN"
            else 2
        )
    except BaseException:
        print("SERVICE_RUNTIME_FAILED", file=sys.stderr, flush=True)
        return 5


__all__ = [
    "SERVICE_SCHEMA",
    "ServiceConfig",
    "ServiceConfigurationError",
    "ServiceState",
    "WorkspaceReturnServiceRuntime",
    "build_service_app",
    "create_runtime",
    "is_ready",
    "load_service_config",
    "parse_service_config",
    "reserve_loopback_socket",
    "run_configured_service",
    "run_service",
]
