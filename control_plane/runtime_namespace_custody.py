"""Private Executive service custody for bounded Runtime observations.

The existing service flock excludes supported maintenance actors; SQLite excludes
ordinary SQLite writers. This does not defend against arbitrary root mutation,
raw database descriptor closes, or another linked SQLite library in this process.
The service assigns this inert owner before start(), and drains all its physical
workers before close(). Failed physical close retains this owner and its locks.
"""
from __future__ import annotations

import errno
import fcntl
import json
import os
from pathlib import Path
import sqlite3
import stat
import sys
import threading
import time
from typing import Any

from control_plane.executive_runtime import (
    Runtime, RuntimeNamespaceCapability, RuntimeReadBinding, RuntimeReadUnavailable,
    _DB_RELATIVE_PATH,
)


def _identity(value: os.stat_result) -> tuple[int, ...]:
    return (value.st_dev, value.st_ino, value.st_mode, value.st_uid,
            value.st_gid, 0 if stat.S_ISDIR(value.st_mode) else value.st_nlink)


class _RequestCapability(RuntimeNamespaceCapability):
    def __init__(self, owner: ServiceRuntimeNamespaceCustody) -> None:
        self.owner = owner
        self.binding: RuntimeReadBinding | None = None
        self.invalid = False
        self.scope: _ReservationScope | None = None

    def namespace(self, database_path: Path) -> _ReservationScope:
        self.validate(database_path)
        self.scope = _ReservationScope(self)
        return self.scope

    def validate(self, database_path: Path) -> None:
        if self.invalid or database_path != self.owner.database_path:
            self.invalid = True
            raise RuntimeReadUnavailable("namespace request invalidated")
        try:
            self.owner._validate()
        except BaseException:
            self.invalid = True
            raise


class _ReservationScope:
    # Deliberately no generator/finalizer: a retained failed binding must never
    # roll back its reservation merely because an ExitStack is garbage collected.
    def __init__(self, capability: _RequestCapability) -> None:
        self.capability = capability

    def __enter__(self) -> None:
        self.capability.owner._enter(self.capability)

    def __exit__(self, kind: Any, value: Any, traceback: Any) -> bool:
        self.capability.owner._exit(self.capability)
        return False


class ServiceRuntimeNamespaceCustody:
    """One service-owned connection, one active request, no grant authority."""

    def __init__(self, *, runtime: Runtime, service_lock_fd: int,
                 lock_path: str | Path, marker_path: str | Path,
                 instance_id: str, reservation_timeout: float = 0.25) -> None:
        if not isinstance(runtime, Runtime) or not 0 < reservation_timeout <= 0.25:
            raise RuntimeReadUnavailable("unsupported namespace owner")
        self.runtime = runtime
        self.database_path = runtime.store.path.absolute()
        self._original_lock_fd = service_lock_fd
        self._lock_path = Path(lock_path).absolute()
        self._marker_path = Path(marker_path).absolute()
        self._instance_id = instance_id
        self._timeout = reservation_timeout
        self._pid = os.getpid()
        self._connection: sqlite3.Connection | None = None
        self._fds: dict[Path, int] = {}
        self._seals: dict[Path, tuple[int, ...] | None] = {}
        self._aliases: dict[Path, tuple[tuple[int, ...], str]] = {}
        self._lock_fd: int | None = None
        self._condition = threading.Condition(threading.RLock())
        self._active: _RequestCapability | None = None
        self._started = False
        self._closing = False
        self._closed = False
        self._invalid = False
        self._uncertain = False

    def _canonical(self, path: Path) -> Path:
        if ".." in path.parts:
            raise RuntimeReadUnavailable("namespace parent traversal refused")
        if path.parts[:2] == ("/", "var") and sys.platform == "darwin":
            alias = Path("/var")
            value = os.lstat(alias)
            target = os.readlink(alias)
            if not stat.S_ISLNK(value.st_mode) or target not in ("private/var", "/private/var"):
                raise RuntimeReadUnavailable("Darwin namespace alias changed")
            self._aliases[alias] = (_identity(value), target)
            return Path("/private/var").joinpath(*path.parts[2:])
        return path

    def _seal(self, path: Path, *, directory: bool = False, optional: bool = False) -> None:
        if path in self._seals:
            return
        try:
            value = os.lstat(path)
        except FileNotFoundError:
            if optional:
                self._seals[path] = None
                return
            raise
        expected = stat.S_ISDIR if directory else stat.S_ISREG
        if not expected(value.st_mode):
            raise RuntimeReadUnavailable("namespace contains unsupported file type")
        if not directory and (value.st_uid != os.geteuid() or value.st_nlink != 1
                              or stat.S_IMODE(value.st_mode) & 0o077):
            raise RuntimeReadUnavailable("namespace file ownership or mode invalid")
        if directory and sys.platform == "darwin":
            # Runtime ancestors may deliberately permit traversal without
            # listing. O_SEARCH retains a directory identity descriptor without
            # requiring the additional read permission of O_RDONLY.
            directory_flag = getattr(os, "O_DIRECTORY", None)
            nofollow = getattr(os, "O_NOFOLLOW", None)
            if directory_flag is None or nofollow is None:
                raise RuntimeReadUnavailable("Darwin directory search flags unavailable")
            # Darwin sys/fcntl.h defines O_EXEC=0x40000000 and
            # O_SEARCH=(O_EXEC | O_DIRECTORY). Some Python builds (including
            # the installed Control 3.12 runtime) omit both exported symbols.
            search = getattr(os, "O_SEARCH", 0x40000000 | directory_flag)
            flags = search | nofollow
        else:
            flags = os.O_RDONLY | os.O_NOFOLLOW
            if directory:
                flags |= os.O_DIRECTORY
        fd = os.open(path, flags)
        # Retain even a failed seal. Closing a raw database/SHM descriptor can
        # drop unrelated POSIX locks held by this process's SQLite connections.
        self._fds[path] = fd
        if _identity(os.fstat(fd)) != _identity(value):
            raise RuntimeReadUnavailable("namespace changed during sealing")
        self._seals[path] = _identity(value)

    def _seal_chain(self, directory: Path) -> None:
        for path in reversed((directory, *directory.parents)):
            self._seal(path, directory=True)

    def _statement(self, sql: str) -> Any:
        assert self._connection is not None
        cursor = self._connection.cursor()
        try:
            cursor.execute(sql)
            return cursor.fetchone()
        finally:
            cursor.close()

    def start(self) -> None:
        """Startup only; the caller already retains this object and service lock."""
        with self._condition:
            if self._started or self._closing or self._invalid:
                raise RuntimeReadUnavailable("namespace startup is not repeatable")
            try:
                self.database_path = self._canonical(self.database_path)
                root = self._canonical(self.runtime.store.root.absolute())
                self._lock_path = self._canonical(self._lock_path)
                self._marker_path = self._canonical(self._marker_path)
                if self.database_path != root / _DB_RELATIVE_PATH:
                    raise RuntimeReadUnavailable("namespace Runtime path is not canonical")
                if self._lock_path != self.database_path.parent / "executive-service.lock":
                    raise RuntimeReadUnavailable("namespace lock path is not canonical")
                if self._marker_path != self.database_path.parent / "executive-service.running":
                    raise RuntimeReadUnavailable("namespace marker path is not canonical")
                self._lock_fd = os.dup(self._original_lock_fd)
                self._seal_chain(self.database_path.parent)
                for path in (self.database_path, self._lock_path, self._marker_path):
                    self._seal(path)
                self._verify_lock()
                self._verify_marker()
                self._connection = sqlite3.connect(
                    self.database_path.as_uri() + "?mode=rw", uri=True,
                    isolation_level=None, check_same_thread=False, timeout=self._timeout,
                )
                if self._statement("PRAGMA journal_mode")[0].lower() != "wal":
                    raise RuntimeReadUnavailable("namespace requires qualified WAL Runtime")
                try:
                    self._statement("BEGIN IMMEDIATE")
                    self._statement("ROLLBACK")
                except BaseException:
                    self._uncertain = True
                    raise
                for suffix in ("-wal", "-shm"):
                    self._seal(Path(str(self.database_path) + suffix))
                for path in (Path(str(self.database_path) + "-journal"),
                             self.database_path.parent / "executive-schema-upgrade.in-progress.json"):
                    self._seal(path, optional=True)
                    if self._seals[path] is not None:
                        raise RuntimeReadUnavailable("namespace maintenance barrier present")
                self._started = True
                self._validate()
            except BaseException:
                self._invalid = True
                # Caller owns cleanup after all same-process actors are drained.
                # Do not close partial seals or unlock here.
                raise

    def _verify_lock(self) -> None:
        assert self._lock_fd is not None
        expected = self._seals[self._lock_path]
        if (_identity(os.fstat(self._original_lock_fd)) != expected or
                _identity(os.fstat(self._lock_fd)) != expected):
            raise RuntimeReadUnavailable("service lock descriptor changed")
        probe = os.open(self._lock_path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            if _identity(os.fstat(probe)) != expected:
                raise RuntimeReadUnavailable("service lock name changed")
            try:
                fcntl.flock(probe, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                if exc.errno not in (errno.EACCES, errno.EAGAIN):
                    raise
            else:
                raise RuntimeReadUnavailable("canonical service lock is not held")
        finally:
            os.close(probe)  # flock inode only; never a SQLite inode
        # Reassert, never unlock, the same inherited open-file description.
        fcntl.flock(self._lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _verify_marker(self) -> None:
        raw = os.pread(self._fds[self._marker_path], 4097, 0)
        if len(raw) > 4096:
            raise RuntimeReadUnavailable("service marker exceeds bound")
        if json.loads(raw) != {"instance_id": self._instance_id, "pid": self._pid}:
            raise RuntimeReadUnavailable("service marker identity changed")

    def _validate(self, *, releasing: bool = False) -> None:
        with self._condition:
            if (not self._started or self._closed or self._invalid or self._uncertain
                    or (self._closing and not releasing) or os.getpid() != self._pid):
                raise RuntimeReadUnavailable("namespace custody unavailable")
            try:
                for path, (identity, target) in self._aliases.items():
                    if _identity(os.lstat(path)) != identity or os.readlink(path) != target:
                        raise RuntimeReadUnavailable("namespace alias invalidated")
                for path, identity in self._seals.items():
                    if identity is None:
                        if os.path.lexists(path):
                            raise RuntimeReadUnavailable("namespace absent name appeared")
                    elif (_identity(os.lstat(path)) != identity or
                          _identity(os.fstat(self._fds[path])) != identity):
                        raise RuntimeReadUnavailable("namespace identity invalidated")
                self._verify_lock()
                self._verify_marker()
            except BaseException:
                self._invalid = True
                raise

    def bound_runtime(self, actual_runtime: Runtime) -> Runtime:
        if actual_runtime is not self.runtime:
            raise RuntimeReadUnavailable("namespace requires exact service Runtime")
        self._validate()
        capability = _RequestCapability(self)
        capability.binding = RuntimeReadBinding(capability)
        return Runtime.at(self.runtime.store.root, create=False,
                          read_binding=capability.binding)

    def _enter(self, capability: _RequestCapability) -> None:
        deadline = time.monotonic() + self._timeout
        with self._condition:
            while self._active is not None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    capability.invalid = True
                    raise RuntimeReadUnavailable("namespace reservation busy")
                self._condition.wait(remaining)
            self._validate()
            self._active = capability
            try:
                remaining_ms = max(1, int((deadline - time.monotonic()) * 1000))
                self._statement(f"PRAGMA busy_timeout={remaining_ms}")
                self._statement("BEGIN IMMEDIATE")
            except sqlite3.OperationalError as exc:
                if getattr(exc, "sqlite_errorcode", None) in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
                    capability.invalid = True
                    self._active = None
                    self._condition.notify_all()
                else:
                    self._uncertain = True
                raise RuntimeReadUnavailable("namespace reservation unavailable") from exc
            except BaseException:
                self._uncertain = True
                raise
            try:
                self._validate()
            except BaseException:
                self._exit(capability)
                raise

    def _exit(self, capability: _RequestCapability) -> None:
        with self._condition:
            if self._active is not capability:
                self._invalid = True
                raise RuntimeReadUnavailable("namespace physical owner changed")
            assert capability.binding is not None
            if capability.binding._unclosed_connection is not None:
                self._uncertain = True
                raise RuntimeReadUnavailable("namespace physical close unresolved")
            validation_error = None
            try:
                self._validate(releasing=True)
            except BaseException as exc:
                validation_error = exc
            try:
                self._statement("ROLLBACK")
            except BaseException as exc:
                self._uncertain = True
                raise RuntimeReadUnavailable("namespace rollback unresolved") from exc
            try:
                self._validate(releasing=True)
            except BaseException as exc:
                validation_error = validation_error or exc
            self._active = None
            self._condition.notify_all()
            if validation_error is not None:
                raise validation_error

    def close(self, *, timeout_seconds: float = 0.25) -> None:
        """Call only after every service SQLite actor has physically drained."""
        if not 0 <= timeout_seconds <= 30:
            raise ValueError("namespace drain timeout out of bounds")
        deadline = time.monotonic() + timeout_seconds
        with self._condition:
            self._closing = True
            if self._closed:
                return
            while self._active is not None and not self._uncertain:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise RuntimeReadUnavailable("namespace physical work has not drained")
                self._condition.wait(remaining)
            if self._uncertain:
                raise RuntimeReadUnavailable("namespace close requires reconciliation")
            if self._connection is not None:
                try:
                    self._connection.close()
                except BaseException as exc:
                    self._uncertain = True
                    raise RuntimeReadUnavailable("namespace connection close unresolved") from exc
                self._connection = None
            # SQLite is certainly closed and all service actors are drained.
            # Only now may raw inode seals be physically closed.
            for path, fd in tuple(self._fds.items()):
                try:
                    os.close(fd)
                except BaseException as exc:
                    self._uncertain = True
                    raise RuntimeReadUnavailable("namespace seal close unresolved") from exc
                del self._fds[path]
            if self._lock_fd is not None:
                try:
                    os.close(self._lock_fd)
                except BaseException as exc:
                    self._uncertain = True
                    raise RuntimeReadUnavailable("namespace lock close unresolved") from exc
                self._lock_fd = None
            self._closed = True
