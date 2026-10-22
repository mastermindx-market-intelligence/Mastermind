"""Immutable root-installed data composition for exact attended Fabric routes.

This module selects no host, imports no configured code, and owns no lifecycle.
Every lookup revalidates the one approved file before returning its fixed route.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import re
import stat
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

from control_plane.executive_fabric_adapter import FabricHostBinding
from control_plane.executive_worker_broker import BrokerStateError

CONFIG_SCHEMA_VERSION = "mastermind.executive_fabric_bindings/v1"
REMOTE_CONFIG_SCHEMA_VERSION = "mastermind.executive_fabric_bindings/v2"
MAX_CONFIG_BYTES = 64 * 1024
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_BINDING_FIELDS = frozenset(field.name for field in dataclasses.fields(FabricHostBinding))


class FabricCompositionError(BrokerStateError):
    """The pinned composition is unavailable, changed, or untrusted."""


def _absolute_path(value: object) -> Path:
    if type(value) is not str or not value or "\x00" in value:
        raise FabricCompositionError("Fabric composition path is invalid")
    path = Path(value)
    if not path.is_absolute() or ".." in path.parts or str(path) != value:
        raise FabricCompositionError("Fabric composition paths must be canonical and absolute")
    return path


def _trusted_parent_chain(path: Path) -> None:
    for parent in path.parents:
        info = parent.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise FabricCompositionError("Fabric composition parent is not root-controlled")


def _identity(info: os.stat_result) -> tuple[int, ...]:
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns,
            info.st_ctime_ns, info.st_uid, info.st_gid, info.st_mode, info.st_nlink)


def _read_pinned(path: Path, expected_sha256: str) -> tuple[bytes, tuple[int, ...]]:
    descriptor = None
    try:
        _trusted_parent_chain(path)
        visible = path.lstat()
        if not stat.S_ISREG(visible.st_mode):
            raise FabricCompositionError("Fabric composition must be a regular file, never a symlink")
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        before = os.fstat(descriptor)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid != 0
                or before.st_mode & 0o022 or not 0 < before.st_size <= MAX_CONFIG_BYTES):
            raise FabricCompositionError("Fabric composition is not a bounded root-owned protected file")
        raw = bytearray()
        while len(raw) <= MAX_CONFIG_BYTES:
            part = os.read(descriptor, MAX_CONFIG_BYTES + 1 - len(raw))
            if not part:
                break
            raw.extend(part)
        after = os.fstat(descriptor)
        if (len(raw) != before.st_size or len(raw) > MAX_CONFIG_BYTES
                or _identity(visible) != _identity(before)
                or _identity(before) != _identity(after)
                or _identity(after) != _identity(path.lstat())):
            raise FabricCompositionError("Fabric composition identity changed while reading")
        if hashlib.sha256(raw).hexdigest() != expected_sha256:
            raise FabricCompositionError("Fabric composition hash differs from its approved source")
        return bytes(raw), _identity(after)
    except OSError as exc:
        raise FabricCompositionError("Root-installed Fabric composition is unavailable") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _pairs(pairs):
    document = {}
    for key, value in pairs:
        if key in document:
            raise FabricCompositionError("Duplicate Fabric composition JSON keys are forbidden")
        document[key] = value
    return document


def _nonfinite(value):
    raise FabricCompositionError("Nonfinite Fabric composition JSON values are forbidden")


def _document(raw: bytes):
    try:
        document = json.loads(raw.decode("utf-8", errors="strict"),
                              object_pairs_hook=_pairs, parse_constant=_nonfinite)
        # This also refuses overflowed numeric literals and lone surrogates.
        json.dumps(document, ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise FabricCompositionError("Fabric composition is not bounded strict UTF-8 JSON") from exc
    return document


def _bindings(raw: bytes) -> tuple[FabricHostBinding, ...]:
    document = _document(raw)
    if (type(document) is not dict or set(document) != {"schema_version", "bindings"}
            or document["schema_version"] != CONFIG_SCHEMA_VERSION
            or type(document["bindings"]) is not list or not document["bindings"]):
        raise FabricCompositionError("Fabric composition document differs from its closed schema")
    bindings = []
    keys = set()
    for value in document["bindings"]:
        if type(value) is not dict or set(value) != _BINDING_FIELDS:
            raise FabricCompositionError("Fabric binding differs from its closed dataclass fields")
        for name, item in value.items():
            if name not in {"worker_uid", "worker_gid", "bridge_uid"}:
                if type(item) is not str or not item or any(ord(char) < 32 for char in item):
                    raise FabricCompositionError("Fabric binding contains an invalid string")
        for name in ("socket_path", "provider_home"):
            _absolute_path(value[name])
        try:
            binding = FabricHostBinding(**value)
        except (BrokerStateError, TypeError, ValueError) as exc:
            raise FabricCompositionError("Fabric binding physical identity is invalid") from exc
        key = (binding.host_ref, binding.worker_id)
        if key in keys:
            raise FabricCompositionError("Duplicate exact Fabric host/worker binding is forbidden")
        keys.add(key)
        bindings.append(binding)
    return tuple(bindings)


def _composition(raw):
    document = _document(raw)
    if type(document) is dict and document.get('schema_version') == REMOTE_CONFIG_SCHEMA_VERSION:
        if (set(document) != {'schema_version', 'bindings', 'remote_transports'}
                or type(document['remote_transports']) is not list
                or not document['remote_transports']):
            raise FabricCompositionError('Remote Fabric composition differs from its closed schema')
        legacy = dict(schema_version=CONFIG_SCHEMA_VERSION, bindings=document['bindings'])
        bindings = _bindings(json.dumps(legacy, ensure_ascii=False, allow_nan=False).encode())
        index = {(b.host_ref, b.worker_id): b for b in bindings}
        from control_plane.fabric_remote_transport import FabricRemoteTransport
        transports = {}
        for value in document['remote_transports']:
            if type(value) is not dict:
                raise FabricCompositionError('Remote Fabric transport is invalid')
            key = (value.get('host_ref'), value.get('worker_id'))
            if any(type(part) is not str for part in key) or key not in index or key in transports:
                raise FabricCompositionError('Remote Fabric transport requires one exact physical binding')
            transports[key] = FabricRemoteTransport.from_document(value, index[key])
        return bindings, MappingProxyType(transports)
    return _bindings(raw), MappingProxyType({})


@dataclasses.dataclass(frozen=True)
class FabricBindingSource:
    """Callable exact-key lookup over one immutable approved composition file."""
    path: Path
    expected_sha256: str
    bindings: tuple[FabricHostBinding, ...]
    _file_identity: tuple[int, ...] = dataclasses.field(repr=False)
    _index: Mapping[tuple[str, str], FabricHostBinding] = dataclasses.field(repr=False, compare=False)
    _remote_index: Mapping = dataclasses.field(repr=False, compare=False)

    @classmethod
    def from_path(cls, path: str | Path, expected_sha256: str) -> "FabricBindingSource":
        if type(expected_sha256) is not str or _SHA256.fullmatch(expected_sha256) is None:
            raise FabricCompositionError("Fabric composition requires an exact approved SHA-256")
        if not isinstance(path, (str, Path)):
            raise FabricCompositionError("Fabric composition requires a filesystem path")
        fixed_path = _absolute_path(str(path))
        raw, identity = _read_pinned(fixed_path, expected_sha256)
        bindings, remote_index = _composition(raw)
        return cls(fixed_path, expected_sha256, bindings, identity,
                   MappingProxyType({(b.host_ref, b.worker_id): b for b in bindings}), remote_index)

    def __call__(self, host_ref: str, worker_id: str) -> FabricHostBinding:
        _, identity = _read_pinned(self.path, self.expected_sha256)
        if identity != self._file_identity:
            raise FabricCompositionError("Fabric composition file identity changed after pinning")
        if type(host_ref) is not str or type(worker_id) is not str:
            raise FabricCompositionError("Fabric lookup requires exact host and worker strings")
        try:
            return self._index[(host_ref, worker_id)]
        except KeyError as exc:
            raise FabricCompositionError("Exact Fabric host/worker binding is not installed") from exc

    def client_for(self, physical: FabricHostBinding, payload):
        if self(physical.host_ref, physical.worker_id) != physical:
            raise FabricCompositionError('Fabric client cannot change its installed physical route')
        remote = self._remote_index.get((physical.host_ref, physical.worker_id))
        if remote is None:
            from control_plane.executive_fabric_adapter import _fixed_client
            return _fixed_client(physical)
        from control_plane.fabric_remote_transport import PinnedFabricRemoteClient
        return PinnedFabricRemoteClient(self, physical, payload, remote)
