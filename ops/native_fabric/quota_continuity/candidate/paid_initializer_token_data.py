"""Finite private credential DATA; never shell execution or approval authority.

The existing owner must separately qualify named ancestors, original custody,
the expected commitment and allowed effects. An FD or fingerprint supplies none
of that authority. This module opens no paths and reads no ambient environment.
"""
from __future__ import annotations

from collections.abc import Mapping
from contextlib import contextmanager
import fcntl
import hashlib
import hmac
import os
import re
import stat
import sys
from types import MappingProxyType

from .paid_initializer import sealed_snapshot

SCHEMA = "mastermind.paid_helper_private_data/v1"
_PATTERN = re.compile(br'export GLM_SHIM_TOKEN="([0-9a-f]{32})"\n\Z')
_SIZE = len(b'export GLM_SHIM_TOKEN="') + 32 + len(b'"\n')
_FIELDS = ("st_dev", "st_ino", "st_mode", "st_uid", "st_gid", "st_nlink",
           "st_size", "st_mtime_ns", "st_ctime_ns")


class TokenDataRefused(ValueError):
    def __init__(self):
        super().__init__("paid_helper_data_refused")


def _refuse():
    raise TokenDataRefused() from None


class _PrivateEnvironment(Mapping):
    __slots__ = ("_values",)

    def __init__(self, values):
        object.__setattr__(self, "_values", MappingProxyType(values))

    def __setattr__(self, name, value):
        raise AttributeError("private environment is immutable") from None

    def __getitem__(self, key):
        try:
            return self._values[key]
        except KeyError:
            raise KeyError("private environment key unavailable") from None

    def __iter__(self):
        return iter(self._values)

    def __len__(self):
        return len(self._values)

    def __repr__(self):
        return "<PrivateEnvironment>"

    __str__ = __repr__

    def __reduce_ex__(self, protocol):
        raise TypeError("private environment is not serializable") from None


class PrivateTokenData:
    __slots__ = ("_token",)

    def __init__(self, token, *, _seal=None):
        if _seal is not _SEAL:
            _refuse()
        object.__setattr__(self, "_token", token)

    def __setattr__(self, name, value):
        raise AttributeError("private data is immutable") from None

    def __repr__(self):
        return "<PrivateTokenData>"

    __str__ = __repr__

    def __reduce_ex__(self, protocol):
        raise TypeError("private data is not serializable") from None

    def child_environment(self, base):
        """Private Mapping for a child env, never argv or evidence material.

        Conflicting inherited credentials refuse rather than choose another
        source. No process is created and os.environ is never modified.
        """
        try:
            if not isinstance(base, Mapping):
                _refuse()
            values = dict(base)
            for key, value in values.items():
                if (type(key) is not str or type(value) is not str
                        or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key)
                        or "\0" in value or key.startswith(("BASH_FUNC_", "LD_"))
                        or key in {"BASH_ENV", "ENV", "PYTHONHOME", "PYTHONEXECUTABLE",
                                   "__PYVENV_LAUNCHER__"}):
                    _refuse()
            token = self._token.decode("ascii")
            if ("GLM_SHIM_TOKEN" in values
                    and not hmac.compare_digest(values["GLM_SHIM_TOKEN"], token)):
                _refuse()
            values["GLM_SHIM_TOKEN"] = token
            if sum(len(k.encode()) + len(v.encode()) + 2
                   for k, v in values.items()) > 65536:
                _refuse()
            return _PrivateEnvironment(values)
        except Exception:
            _refuse()

    def verify_environment(self, environment):
        """Post-initialization check: never inject or repair a missing token."""
        try:
            if not isinstance(environment, Mapping):
                _refuse()
            supplied = environment.get("GLM_SHIM_TOKEN")
            if (type(supplied) is not str
                    or not hmac.compare_digest(supplied, self._token.decode("ascii"))):
                _refuse()
        except Exception:
            _refuse()


_SEAL = object()


def parse_helper_data(raw):
    if type(raw) is not bytes or len(raw) != _SIZE:
        _refuse()
    match = _PATTERN.fullmatch(raw)
    if match is None:
        _refuse()
    return PrivateTokenData(match.group(1), _seal=_SEAL)


def _expected(value):
    if (type(value) is not dict
            or set(value) != {"sha256", "size", "uid", "gid", "mode"}
            or type(value["sha256"]) is not str
            or re.fullmatch(r"[0-9a-f]{64}", value["sha256"]) is None
            or type(value["size"]) is not int or value["size"] != _SIZE
            or type(value["mode"]) is not int or value["mode"] != 0o600):
        _refuse()
    for key in ("uid", "gid"):
        if type(value[key]) is not int or not 0 < value[key] < 2**31:
            _refuse()
    return dict(value)


def _identity(info):
    return tuple(getattr(info, name) for name in _FIELDS)


def _read_origin(fd, expected):
    if fcntl.fcntl(fd, fcntl.F_GETFL) & os.O_ACCMODE != os.O_RDONLY:
        _refuse()
    before = os.fstat(fd)
    if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
            or before.st_uid != expected["uid"] or before.st_gid != expected["gid"]
            or stat.S_IMODE(before.st_mode) != expected["mode"]
            or before.st_size != expected["size"]):
        _refuse()
    raw = os.pread(fd, expected["size"] + 1, 0)
    if (len(raw) != expected["size"] or _identity(before) != _identity(os.fstat(fd))
            or not hmac.compare_digest(hashlib.sha256(raw).hexdigest(), expected["sha256"])):
        _refuse()
    parse_helper_data(raw)
    return raw, _identity(before)


def _check_snapshot(fd, expected_sha256, expected_size, expected_identity):
    before = os.fstat(fd)
    if _identity(before) != expected_identity:
        _refuse()
    required = (fcntl.F_SEAL_WRITE | fcntl.F_SEAL_GROW
                | fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_SEAL)
    if (os.get_inheritable(fd)
            or fcntl.fcntl(fd, fcntl.F_GET_SEALS) & required != required):
        _refuse()
    raw = os.pread(fd, expected_size + 1, 0)
    if (len(raw) != expected_size or before.st_size != expected_size
            or _identity(before) != _identity(os.fstat(fd))
            or not hmac.compare_digest(hashlib.sha256(raw).hexdigest(), expected_sha256)):
        _refuse()


class FrozenHelper:
    __slots__ = ("_origin", "_snapshot", "_identity", "_snapshot_identity",
                 "_expected", "_private", "_closed")

    def __init__(self, origin, snapshot, identity, expected, private, *, _seal=None):
        if _seal is not _SEAL:
            _refuse()
        self._origin, self._snapshot = origin, snapshot
        self._identity, self._expected, self._private = identity, expected, private
        self._snapshot_identity = _identity(os.fstat(snapshot))
        self._closed = False

    def __repr__(self):
        return "<FrozenPrivateHelper>"

    def __reduce_ex__(self, protocol):
        raise TypeError("private helper is not serializable") from None

    @property
    def fingerprint(self):
        return {"schema_version": SCHEMA, **self._expected}

    @property
    def private_data(self):
        self.check()
        return self._private

    @property
    def snapshot_fd(self):
        self.check()
        return self._snapshot

    def check(self):
        try:
            if self._closed or os.get_inheritable(self._origin):
                _refuse()
            _raw, identity = _read_origin(self._origin, self._expected)
            if identity != self._identity:
                _refuse()
            _check_snapshot(self._snapshot, self._expected["sha256"], self._expected["size"],
                            self._snapshot_identity)
        except (OSError, ValueError, TypeError, AttributeError):
            _refuse()

    def close(self):
        if self._closed:
            return
        self._closed = True
        failed = False
        for fd, identity in ((self._origin, self._identity),
                             (self._snapshot, self._snapshot_identity)):
            try:
                current = os.fstat(fd)
                if (current.st_dev, current.st_ino) != identity[:2]:
                    failed = True
                    continue  # never close a foreign object reusing our number
                os.close(fd)
            except OSError:
                failed = True
        self._origin = self._snapshot = -1
        self._private = None
        if failed:
            _refuse()


@contextmanager
def freeze_helper_data(fd, *, expected):
    """Private DATA only; the existing owner retains named/ancestor proofs."""
    origin = snapshot = None
    frozen = None
    try:
        if (type(fd) is not int or fd < 0 or sys.platform != "linux"
                or not hasattr(os, "memfd_create")):
            _refuse()
        wanted = _expected(expected)
        raw, identity = _read_origin(fd, wanted)
        origin = os.dup(fd)
        if os.get_inheritable(origin):
            _refuse()
        snapshot = sealed_snapshot(raw)
        frozen = FrozenHelper(origin, snapshot, identity, wanted,
                              parse_helper_data(raw), _seal=_SEAL)
        frozen.check()
    except (OSError, ValueError, TypeError, AttributeError):
        for owned in (origin, snapshot):
            if owned is not None:
                try:
                    os.close(owned)
                except OSError:
                    pass
        _refuse()
    try:
        yield frozen
    except BaseException:
        try:
            frozen.close()
        except TokenDataRefused:
            pass
        raise
    else:
        try:
            frozen.check()
        finally:
            frozen.close()
