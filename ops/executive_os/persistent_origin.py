"""Current Data-volume custody for prospective, logical retained-origin reads.

Historical device numbers remain observations, never retrospective volume UUIDs.
This private mechanism grants no migration, preparation or lifecycle authority.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import os
from pathlib import Path
import stat
import sys
from typing import Any

from control_plane.fs_security import has_macos_acl


DATA_VOLUME_ANCHOR = Path("/System/Volumes/Data")


class PersistentOriginError(RuntimeError):
    """Current custody could not be established or held."""


def _principal() -> None:
    if sys.platform != "darwin" or os.geteuid() != 0:
        raise PersistentOriginError("current Data custody requires Root on Darwin")


def _directory_identity(info: os.stat_result) -> tuple[int, ...]:
    # Creating unrelated children must not invalidate a held directory object.
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid)


def _file_identity(info: os.stat_result) -> tuple[int, ...]:
    return (*_directory_identity(info), info.st_nlink, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns)


@dataclass(frozen=True)
class _Directory:
    path: Path
    fd: int
    parent_fd: int | None
    name: str
    identity: tuple[int, ...]


class CurrentDataVolumeGuard:
    """Hold an independent, fixed current-boot anchor and every named prefix.

    No caller selects the anchor or supplies a trust assertion. The observed
    current device is separate from every immutable historical device field.
    """

    def __init__(self) -> None:
        self._nodes: list[_Directory] = []
        self._closed = False
        try:
            _principal()
            anchor = DATA_VOLUME_ANCHOR
            if (not isinstance(anchor, Path) or not anchor.is_absolute()
                    or ".." in anchor.parts or anchor.resolve(strict=True) != anchor):
                raise PersistentOriginError("current Data anchor is not canonical")
            flags = (os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
                     | getattr(os, "O_CLOEXEC", 0) | os.O_NONBLOCK)
            for path in [*reversed(anchor.parents), anchor]:
                parent_fd = self._nodes[-1].fd if self._nodes else None
                fd = os.open(path.name if parent_fd is not None else str(path),
                             flags, dir_fd=parent_fd)
                # Own the FD before any check which could fail.
                try:
                    identity = _directory_identity(os.fstat(fd))
                except BaseException:
                    os.close(fd)
                    raise
                node = _Directory(path, fd, parent_fd, path.name, identity)
                self._nodes.append(node)
                self._check_node(node)
            self.check()
        except BaseException as exc:
            self.close()
            if isinstance(exc, Exception) and not isinstance(exc, PersistentOriginError):
                raise PersistentOriginError("current Data anchor qualification refused") from exc
            raise

    def _check_node(self, node: _Directory) -> None:
        held = os.fstat(node.fd)
        named = (os.stat(node.name, dir_fd=node.parent_fd, follow_symlinks=False)
                 if node.parent_fd is not None else node.path.lstat())
        if (not stat.S_ISDIR(held.st_mode) or held.st_uid != 0
                or held.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
                or _directory_identity(held) != node.identity
                or _directory_identity(named) != node.identity
                or _directory_identity(os.lstat(node.path)) != node.identity
                or has_macos_acl(node.path, descriptor=node.fd,
                                 expected_identity=held)):
            raise PersistentOriginError("current Data anchor custody changed")

    def check(self) -> None:
        _principal()
        if getattr(self, "_closed", True) or not self._nodes:
            raise PersistentOriginError("current Data anchor is closed")
        try:
            if self._nodes[-1].path != DATA_VOLUME_ANCHOR:
                raise PersistentOriginError("current Data anchor binding changed")
            for node in self._nodes:
                self._check_node(node)
        except PersistentOriginError:
            raise
        except (OSError, ValueError, AttributeError, RuntimeError) as exc:
            raise PersistentOriginError("current Data anchor observation refused") from exc

    @property
    def current_device(self) -> int:
        self.check()
        value = self._nodes[-1].identity[0]
        if type(value) is not int or value <= 0:
            raise PersistentOriginError("current Data device is invalid")
        return value

    def require_device(self, observed: int) -> None:
        if type(observed) is not int or observed <= 0 or observed != self.current_device:
            raise PersistentOriginError("retained origin is outside the current Data volume")

    def require_path_device(self, path: Path, info: os.stat_result | None = None) -> None:
        """Check a named object's own device; do not follow a link or read bytes."""
        self.check()
        path = Path(path)
        if not path.is_absolute() or ".." in path.parts:
            raise PersistentOriginError("retained origin path is not absolute")
        try:
            named = os.lstat(path)
            if info is not None and _file_identity(info) != _file_identity(named):
                raise PersistentOriginError("retained origin named identity changed")
            self.require_device(named.st_dev)
            if _file_identity(os.lstat(path)) != _file_identity(named):
                raise PersistentOriginError("retained origin changed during observation")
            self.check()
        except PersistentOriginError:
            raise
        except (OSError, ValueError, AttributeError) as exc:
            raise PersistentOriginError("retained origin observation refused") from exc

    def close(self) -> None:
        self._closed = True
        nodes, self._nodes = self._nodes, []
        error = None
        for node in reversed(nodes):
            try:
                os.close(node.fd)
            except OSError as exc:
                error = error or exc
        if error is not None:
            raise PersistentOriginError("current Data descriptor close failed") from error

    def __enter__(self) -> CurrentDataVolumeGuard:
        self.check()
        return self

    def __exit__(self, kind, error, traceback) -> None:
        self.close()


def _same_value(expected: Any, observed: Any) -> bool:
    if type(expected) is not type(observed):
        return False
    if type(expected) is dict:
        return (all(type(key) is str for key in expected)
                and set(expected) == set(observed)
                and all(_same_value(expected[key], observed[key]) for key in expected))
    if type(expected) is list:
        return (len(expected) == len(observed)
                and all(_same_value(a, b) for a, b in zip(expected, observed)))
    if type(expected) is float:
        return math.isfinite(expected) and expected == observed
    return type(expected) in (str, int, bool, bytes, type(None)) and expected == observed


def persistent_record_matches(expected: dict, observed: dict, *,
                              volume: CurrentDataVolumeGuard,
                              historical_device: int) -> bool:
    """Compare one already schema-qualified original to current owned evidence.

    The caller retains original historical fields and owns the surrounding
    schema, provenance and effect guards. Only this record's top-level device
    observation changes meaning across time; nested historical joins stay exact.
    """
    if type(volume) is not CurrentDataVolumeGuard:
        raise PersistentOriginError("actual current Data volume guard required")
    current = volume.current_device
    if (type(historical_device) is not int or historical_device <= 0
            or type(expected) is not dict or type(observed) is not dict
            or set(expected) != set(observed) or "device" not in expected
            or any(type(key) is not str for key in expected)
            or type(expected["device"]) is not int
            or type(observed["device"]) is not int
            or expected["device"] != historical_device
            or observed["device"] != current):
        return False
    matched = all(_same_value(expected[key], observed[key])
                  for key in expected if key != "device")
    volume.check()
    return matched
