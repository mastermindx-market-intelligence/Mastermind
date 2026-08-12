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
from typing import Any, Callable, Mapping, Protocol
from uuid import uuid4

from control_plane.executive_runtime import (
    Job,
    JobStatus,
    Runtime,
    RuntimeProofError,
    SCHEMA_VERSION,
    StateConflict,
)
from control_plane.executive_workspace import prepare_credentialless_clone


CONTROL_PROTOCOL_VERSION = "mastermind.executive_control/v1"
DEFAULT_MAX_REQUEST_BYTES = 64 * 1024
DEFAULT_MAX_RESPONSE_BYTES = 1024 * 1024
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_BACKUP_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}\.sqlite3$")
_PROOF_WORKSPACE_RE = re.compile(r"^proof-([0-9a-f]{32})$")
_WORKSPACE_ROTATION_SCHEMA = "mastermind.executive_workspace_rotation/v1"
_PROOF_ARTIFACT = "research/executive_os_phase1c_worker_proof/receipt.md"
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


class ServiceError(RuntimeProofError):
    """A private control-service request could not be completed safely."""


class SupervisorProtocol(Protocol):
    async def start_job(self, job_id: str) -> Any: ...

    async def finish_job(self, active: Any) -> Any: ...

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
        for field_name in ("worker_id", "quota_class"):
            if _ID_RE.fullmatch(str(getattr(self, field_name))) is None:
                raise ValueError(f"invalid {field_name}")
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
        backup_backend: BackupBackendProtocol | None = None,
        activated_socket: socket.socket | None = None,
        service_state: str = "READY",
    ) -> None:
        self.config = config
        self._runtime_factory = runtime_factory
        self._supervisor_factory = supervisor_factory
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
        self._server: asyncio.AbstractServer | None = None
        self._lock_fd: int | None = None
        self._dispatch_lock = asyncio.Lock()
        self._workspace_lock = asyncio.Lock()
        self._dispatch_tasks: dict[str, asyncio.Task[Any]] = {}
        self._dispatch_errors: dict[str, str] = {}
        self._startup_reconciliation: list[Any] = []
        self._started_at: str | None = None
        if service_state not in {"READY", "AWAITING_CANARY"}:
            raise ValueError("service_state must be READY or AWAITING_CANARY")
        self._service_state = service_state
        self.instance_id = f"executive-service-{uuid4().hex}"

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

    async def start(self) -> None:
        if self._server is not None:
            raise ServiceError("Executive control service is already started")
        self._prepare_socket()
        try:
            self.runtime = self._runtime_factory(self.config.runtime_root)
            health = self._database_health()
            if not health["ok"]:
                raise ServiceError(f"Executive database health check failed: {health!r}")
            if self._supervisor_factory is None:
                raise ServiceError("supervisor_factory is required for startup reconciliation")
            self.supervisor = self._supervisor_factory(self.runtime)
            # Startup reconciliation must never auto-requeue.  LOST work returns
            # to QUEUED only through the explicit requeue command.
            if self._service_state == "READY":
                self._startup_reconciliation = await asyncio.to_thread(
                    self.supervisor.reconcile_restart, requeue_lost=False
                )
            if self._activated_socket is None:
                self._server = await asyncio.start_unix_server(
                    self._handle_connection,
                    path=str(self.socket_path),
                    limit=self.config.max_request_bytes + 1,
                )
                self.socket_path.chmod(0o600)
            else:
                activated, self._activated_socket = self._activated_socket, None
                self._server = await asyncio.start_unix_server(
                    self._handle_connection,
                    sock=activated,
                    limit=self.config.max_request_bytes + 1,
                )
                mode = stat.S_IMODE(self.socket_path.stat().st_mode)
                if mode & 0o007:
                    raise ServiceError("launchd control socket must not be world-accessible")
            self._started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        except Exception:
            await self.close()
            raise

    async def close(self) -> None:
        server, self._server = self._server, None
        if server is not None:
            server.close()
            await server.wait_closed()

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

        if not self._launchd_activated:
            try:
                info = self.socket_path.lstat()
            except FileNotFoundError:
                pass
            else:
                if stat.S_ISSOCK(info.st_mode):
                    self.socket_path.unlink()
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
            except (BrokenPipeError, ConnectionResetError):
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
        writer.write(raw)
        await writer.drain()

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
        existing = runtime.workers.get_worker(self.config.worker_id)
        if existing is not None:
            expected_capabilities = ["code", "research", "tests"]
            quota = existing.quota_classes.get(self.config.quota_class)
            if (
                existing.provider != self.config.provider
                or existing.account_label != self.config.worker_account_label
                or existing.worker_type != self.config.worker_type
                or existing.capabilities != expected_capabilities
                or quota is None
                or quota.get("capabilities") != expected_capabilities
            ):
                raise StateConflict("configured worker identity already exists with different policy")
            return existing
        return runtime.workers.register_worker(
            self.config.worker_id,
            provider=self.config.provider,
            account_label=self.config.worker_account_label,
            worker_type=self.config.worker_type,
            capabilities=["research", "code", "tests"],
            quota_classes={
                self.config.quota_class: {
                    "provider": self.config.provider,
                    "model": self.config.model,
                    "effort": self.config.effort,
                    "cost_class": self.config.cost_class,
                    "capabilities": ["research", "code", "tests"],
                }
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

    def _git_output(self, workspace: Path, arguments: list[str]) -> bytes:
        home = self.config.proof_workspace_root / ".supervisor-home"
        environment = {
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
        head = self._git_output(
            workspace, ["rev-parse", "--verify", "HEAD^{commit}"]
        ).decode("ascii", errors="strict").strip()
        branch = self._git_output(
            workspace, ["rev-parse", "--abbrev-ref", "HEAD"]
        ).decode("utf-8", errors="strict").strip()
        status = self._git_output(
            workspace, ["status", "--porcelain=v1", "-z", "--untracked-files=all"]
        )
        remotes = tuple(
            value
            for value in self._git_output(workspace, ["remote"])
            .decode("utf-8", errors="strict")
            .splitlines()
            if value
        )
        if require_fresh and (
            head != self.config.proof_base_sha
            or branch != expected_branch
            or status
            or remotes
        ):
            raise ServiceError(
                "replacement proof workspace is not clean, exact-SHA, branch-bound, and no-remote"
            )
        return {
            "path": str(workspace),
            "device": int(info.st_dev),
            "inode": int(info.st_ino),
            "uid": int(info.st_uid),
            "gid": int(info.st_gid),
            "mode": stat.S_IMODE(info.st_mode),
            "head": head,
            "branch": branch,
            "status_sha256": hashlib.sha256(status).hexdigest(),
            "status_dirty": bool(status),
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
            }
        if command == "health":
            self._exact_args(args, set())
            return self._database_health()
        if self._service_state != "READY":
            raise StateConflict(
                f"Executive control service is {self._service_state}; "
                "only status and health are available"
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
