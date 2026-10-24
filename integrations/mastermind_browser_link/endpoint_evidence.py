"""Exact native socket evidence borrowed from the existing framing owner.

Only the Workbench resource owner decides whether an old process is absent.
This helper cannot terminate processes, grant consent, discover another path,
or infer ownership from a refused connection. The caller retains the existing
exclusive/cooperating store and profile writer across cleanup and the next
bind. Stat/unlink is not an atomic CAS against a non-cooperating same-UID writer.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import os
from pathlib import Path
import stat

from integrations.chairman_surfaces import web_sol_native_host as framing
from .native_channel import LinkProtocolError

ENDPOINT_SCHEMA = "mastermind.browser_link.native_endpoint.v1"


@dataclass(frozen=True)
class NativeEndpointEvidence:
    socket_path: str
    parent_device: int
    parent_inode: int
    socket_device: int
    socket_inode: int
    socket_ctime_ns: int
    owner_uid: int

    def __post_init__(self):
        path = Path(self.socket_path) if type(self.socket_path) is str else None
        if (path is None or not path.is_absolute() or ".." in path.parts
                or str(path) != self.socket_path or "\x00" in self.socket_path
                or len(os.fsencode(path)) > 103):
            raise LinkProtocolError("LINK_ENDPOINT_INVALID")
        for name in ("parent_device", "parent_inode", "socket_device", "socket_inode", "socket_ctime_ns", "owner_uid"):
            value = getattr(self, name)
            if type(value) is not int or not 0 <= value < 2**63:
                raise LinkProtocolError("LINK_ENDPOINT_INVALID")

    def document(self):
        return {"schema": ENDPOINT_SCHEMA, **asdict(self)}

    @classmethod
    def from_document(cls, value):
        fields = {"socket_path", "parent_device", "parent_inode",
                  "socket_device", "socket_inode", "socket_ctime_ns", "owner_uid"}
        if type(value) is not dict or set(value) != fields | {"schema"} or value["schema"] != ENDPOINT_SCHEMA:
            raise LinkProtocolError("LINK_ENDPOINT_INVALID")
        return cls(**{name: value[name] for name in fields})

    def _open_parent(self, expected_path):
        self.__post_init__()
        if str(expected_path) != self.socket_path or self.owner_uid != os.geteuid():
            raise LinkProtocolError("LINK_ENDPOINT_MISMATCH")
        fd = os.open(Path(self.socket_path).parent,
                     os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            parent = os.fstat(fd)
            if (not stat.S_ISDIR(parent.st_mode) or stat.S_IMODE(parent.st_mode) != 0o700
                    or (parent.st_dev, parent.st_ino, parent.st_uid)
                    != (self.parent_device, self.parent_inode, self.owner_uid)):
                raise LinkProtocolError("LINK_ENDPOINT_PARENT_CHANGED")
            self._check_parent_path(fd)
            return fd
        except BaseException:
            os.close(fd)
            raise

    def _check_parent_path(self, fd):
        named = Path(self.socket_path).parent.lstat()
        held = os.fstat(fd)
        expected = (self.parent_device, self.parent_inode, self.owner_uid)
        if (not stat.S_ISDIR(named.st_mode) or stat.S_IMODE(named.st_mode) != 0o700
                or (named.st_dev, named.st_ino, named.st_uid) != expected
                or (held.st_dev, held.st_ino, held.st_uid) != expected):
            raise LinkProtocolError("LINK_ENDPOINT_PARENT_CHANGED")

    def _check_socket(self, fd, *, missing_ok):
        try:
            current = os.stat(Path(self.socket_path).name, dir_fd=fd, follow_symlinks=False)
        except FileNotFoundError:
            if missing_ok:
                return False
            raise LinkProtocolError("LINK_ENDPOINT_ABSENT") from None
        if (not stat.S_ISSOCK(current.st_mode) or stat.S_IMODE(current.st_mode) != 0o600
                or (current.st_dev, current.st_ino, current.st_uid)
                != (self.socket_device, self.socket_inode, self.owner_uid)
                or current.st_ctime_ns != self.socket_ctime_ns):
            raise LinkProtocolError("LINK_ENDPOINT_CHANGED")
        return True

    def qualify(self, expected_path, *, missing_ok=False):
        fd = self._open_parent(expected_path)
        try:
            return self._check_socket(fd, missing_ok=missing_ok)
        finally:
            os.close(fd)

    def remove_after_owner_proved_absence(self, expected_path):
        """Remove qualified evidence under exclusive writer custody and proven absence."""
        fd = self._open_parent(expected_path)
        try:
            if not self._check_socket(fd, missing_ok=True):
                self._check_parent_path(fd)
                return
            self._check_parent_path(fd)
            os.unlink(Path(self.socket_path).name, dir_fd=fd)
            os.fsync(fd)
            try:
                os.stat(Path(self.socket_path).name, dir_fd=fd, follow_symlinks=False)
            except FileNotFoundError:
                self._check_parent_path(fd)
                return
            raise LinkProtocolError("LINK_ENDPOINT_REAPPEARED")
        finally:
            os.close(fd)


def capture_native_endpoint(server, path, *, parent_identity):
    """Read the exact inode already recorded by the incumbent socket owner."""
    path = Path(path)
    # This existing private map is the framing owner's bind-time identity.
    # Capturing just lstat(path) would wrongly bless a substituted socket.
    identity = framing._SERVER_SOCKET_IDENTITIES.get(id(server))
    if identity is None or server.getsockname() != str(path):
        raise LinkProtocolError("LINK_ENDPOINT_UNOWNED")
    parent = path.parent.lstat()
    if (parent.st_dev, parent.st_ino) != parent_identity:
        raise LinkProtocolError("LINK_ENDPOINT_PARENT_CHANGED")
    current = path.lstat()
    evidence = NativeEndpointEvidence(
        socket_path=str(path), parent_device=parent.st_dev, parent_inode=parent.st_ino,
        socket_device=identity[0], socket_inode=identity[1],
        socket_ctime_ns=current.st_ctime_ns, owner_uid=os.geteuid(),
    )
    evidence.qualify(path)
    return evidence
