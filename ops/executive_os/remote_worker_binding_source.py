"""Root-managed physical bindings for already-selected remote Executive workers.

Capacity and Executive Runtime own host/worker/provider placement. This source
only maps the exact selected ``(host_ref, worker_id)`` pair to local mTLS and OS
principal coordinates. It owns no discovery, registry, lifecycle, retry, queue,
placement, failover, or credential material beyond paths to the incumbent mTLS
files.
"""
from __future__ import annotations

import ipaddress
import json
import math
import os
import re
import stat
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from control_plane.remote_attempt_transport import RemoteWorkerHostBinding
from control_plane.remote_worker_transport import BrokerTransportBinding

BINDING_SOURCE_SCHEMA = "mastermind.remote_worker_host_bindings/v1"
_MAX_CONFIG_BYTES = 256 * 1024
_MAX_TLS_BYTES = 1024 * 1024
_MAX_BINDINGS = 64
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_USER = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]{0,63}$")
_SECRET_KEY = re.compile(
    r"(?:^|_)(?:api_?key|authorization|credential|password|private_?key|token|secret)(?:$|_)",
    re.IGNORECASE,
)
_TOP_FIELDS = frozenset({"schema", "bindings"})
_ROW_FIELDS = frozenset(
    {
        "host_ref",
        "worker_id",
        "adapter_id",
        "worker_user",
        "worker_uid",
        "worker_gid",
        "endpoint_host",
        "endpoint_port",
        "ca_path",
        "client_cert_path",
        "client_key_path",
        "expected_server_fingerprint",
        "timeout_seconds",
        "secret_canary_verdict",
    }
)


class RemoteWorkerBindingSourceError(ValueError):
    """A sanitized root-binding source refusal."""


def _refuse(message: str) -> None:
    raise RemoteWorkerBindingSourceError(message)


def _identity(info: os.stat_result) -> tuple[int, ...]:
    return (
        int(info.st_dev),
        int(info.st_ino),
        int(info.st_uid),
        int(info.st_gid),
        int(info.st_mode),
        int(info.st_nlink),
        int(info.st_size),
        int(info.st_mtime_ns),
        int(info.st_ctime_ns),
    )


def _read_regular(
    path: Path,
    *,
    expected_owner_uid: int,
    expected_group_gid: int,
    allowed_modes: frozenset[int],
    maximum: int,
    label: str,
) -> bytes:
    if not path.is_absolute():
        _refuse(f"{label} path is invalid")
    try:
        before = path.lstat()
    except OSError:
        _refuse(f"{label} is unavailable")
    if (
        stat.S_ISLNK(before.st_mode)
        or not stat.S_ISREG(before.st_mode)
        or before.st_nlink != 1
        or before.st_uid != expected_owner_uid
        or before.st_gid != expected_group_gid
        or stat.S_IMODE(before.st_mode) not in allowed_modes
        or before.st_size <= 0
        or before.st_size > maximum
    ):
        _refuse(f"{label} identity is invalid")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
        try:
            opened = os.fstat(descriptor)
            if _identity(opened) != _identity(before):
                _refuse(f"{label} identity changed")
            chunks: list[bytes] = []
            total = 0
            while True:
                chunk = os.read(descriptor, min(65536, maximum + 1 - total))
                if not chunk:
                    break
                total += len(chunk)
                if total > maximum:
                    _refuse(f"{label} exceeds its byte ceiling")
                chunks.append(chunk)
            after = os.fstat(descriptor)
        finally:
            os.close(descriptor)
        final = path.lstat()
    except RemoteWorkerBindingSourceError:
        raise
    except OSError:
        _refuse(f"{label} is unavailable")
    raw = b"".join(chunks)
    if (
        _identity(opened) != _identity(after)
        or _identity(after) != _identity(final)
        or len(raw) != after.st_size
    ):
        _refuse(f"{label} changed while reading")
    return raw


def _closed_json(raw: bytes) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if type(key) is not str or key in result:
                _refuse("binding source contains duplicate keys")
            result[key] = value
        return result

    def finite(value: str) -> float:
        parsed = float(value)
        if not math.isfinite(parsed):
            _refuse("binding source contains a non-finite number")
        return parsed

    try:
        value = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=pairs,
            parse_float=finite,
            parse_constant=lambda _value: _refuse(
                "binding source contains a non-finite constant"
            ),
        )
    except RemoteWorkerBindingSourceError:
        raise
    except (UnicodeError, json.JSONDecodeError, ValueError, OverflowError):
        _refuse("binding source is not strict UTF-8 JSON")
    if type(value) is not dict or set(value) != _TOP_FIELDS:
        _refuse("binding source fields are invalid")
    return value


def _positive(value: Any, field: str) -> int:
    if type(value) is not int or value <= 0 or value >= 2**31:
        _refuse(f"binding {field} is invalid")
    return value


def _clean_token(value: Any, field: str, pattern: re.Pattern[str]) -> str:
    if type(value) is not str or pattern.fullmatch(value) is None:
        _refuse(f"binding {field} is invalid")
    return value


def _secret_free(value: Any, *, path: str = "verdict") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if type(key) is not str or _SECRET_KEY.search(key):
                _refuse(f"binding secret field is forbidden at {path}")
            _secret_free(child, path=f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _secret_free(child, path=f"{path}[{index}]")
    elif type(value) not in (str, int, float, bool, type(None)):
        _refuse("binding verdict is not JSON-safe")
    elif isinstance(value, float) and not math.isfinite(value):
        _refuse("binding verdict contains a non-finite number")


def _endpoint_host(value: Any) -> str:
    if type(value) is not str or not value or value != value.strip() or len(value) > 253:
        _refuse("binding endpoint host is invalid")
    try:
        parsed = ipaddress.ip_address(value)
    except ValueError:
        if any(part in {"", ".", ".."} for part in value.split(".")):
            _refuse("binding endpoint host is invalid")
    else:
        if parsed.is_unspecified or parsed.is_multicast:
            _refuse("binding endpoint host is invalid")
    return value


class RootManagedRemoteWorkerBindingSource:
    """Reread one sealed physical-binding projection on every resolution."""

    def __init__(
        self,
        path: Path | str,
        *,
        expected_owner_uid: int = 0,
        expected_group_gid: int | None = None,
    ) -> None:
        candidate = Path(path)
        if not candidate.is_absolute():
            _refuse("binding source path is invalid")
        if type(expected_owner_uid) is not int or expected_owner_uid < 0:
            _refuse("binding source owner is invalid")
        if expected_group_gid is None:
            expected_group_gid = os.getegid()
        if type(expected_group_gid) is not int or expected_group_gid < 0:
            _refuse("binding source group is invalid")
        self.path = candidate
        self.expected_owner_uid = expected_owner_uid
        self.expected_group_gid = expected_group_gid

    def _rows(self) -> tuple[RemoteWorkerHostBinding, ...]:
        raw = _read_regular(
            self.path,
            expected_owner_uid=self.expected_owner_uid,
            expected_group_gid=self.expected_group_gid,
            allowed_modes=frozenset({0o440}),
            maximum=_MAX_CONFIG_BYTES,
            label="binding source",
        )
        document = _closed_json(raw)
        if document["schema"] != BINDING_SOURCE_SCHEMA:
            _refuse("binding source schema is unsupported")
        rows = document["bindings"]
        if type(rows) is not list or not rows or len(rows) > _MAX_BINDINGS:
            _refuse("binding source rows are invalid")
        identities: list[tuple[str, str]] = []
        result: list[RemoteWorkerHostBinding] = []
        for raw_row in rows:
            if type(raw_row) is not dict or set(raw_row) != _ROW_FIELDS:
                _refuse("binding row fields are invalid")
            host_ref = _clean_token(raw_row["host_ref"], "host_ref", _ID)
            worker_id = _clean_token(raw_row["worker_id"], "worker_id", _ID)
            adapter_id = raw_row["adapter_id"]
            if adapter_id not in {"codex-cli", "claude-code", "dot2api"}:
                _refuse("binding adapter_id is invalid")
            worker_user = _clean_token(raw_row["worker_user"], "worker_user", _USER)
            worker_uid = _positive(raw_row["worker_uid"], "worker_uid")
            worker_gid = _positive(raw_row["worker_gid"], "worker_gid")
            endpoint_host = _endpoint_host(raw_row["endpoint_host"])
            endpoint_port = _positive(raw_row["endpoint_port"], "endpoint_port")
            if endpoint_port > 65535:
                _refuse("binding endpoint_port is invalid")
            fingerprint = raw_row["expected_server_fingerprint"]
            if type(fingerprint) is not str or _HEX64.fullmatch(fingerprint) is None:
                _refuse("binding server fingerprint is invalid")
            timeout = raw_row["timeout_seconds"]
            if type(timeout) not in (int, float) or isinstance(timeout, bool) or not 0.1 <= float(timeout) <= 3600:
                _refuse("binding timeout is invalid")
            verdict = raw_row["secret_canary_verdict"]
            if type(verdict) is not dict:
                _refuse("binding secret-canary verdict is invalid")
            _secret_free(verdict)
            if (
                verdict.get("passed") is not True
                or verdict.get("worker_id") != worker_id
                or type(verdict.get("receipt_sha256")) is not str
                or _HEX64.fullmatch(verdict["receipt_sha256"]) is None
            ):
                _refuse("binding secret-canary verdict is invalid")
            paths = {
                name: Path(raw_row[name])
                for name in ("ca_path", "client_cert_path", "client_key_path")
            }
            for name, path in paths.items():
                _read_regular(
                    path,
                    expected_owner_uid=self.expected_owner_uid,
                    expected_group_gid=self.expected_group_gid,
                    allowed_modes=(
                        frozenset({0o400, 0o440})
                        if name == "client_key_path"
                        else frozenset({0o440})
                    ),
                    maximum=_MAX_TLS_BYTES,
                    label=f"binding {name}",
                )
            transport = BrokerTransportBinding(
                endpoint=(endpoint_host, endpoint_port),
                ca_path=paths["ca_path"],
                client_cert_path=paths["client_cert_path"],
                client_key_path=paths["client_key_path"],
                expected_server_fingerprint=fingerprint,
                timeout_seconds=float(timeout),
            )
            result.append(
                RemoteWorkerHostBinding(
                    host_ref=host_ref,
                    worker_id=worker_id,
                    adapter_id=adapter_id,
                    transport=transport,
                    worker_user=worker_user,
                    worker_uid=worker_uid,
                    worker_gid=worker_gid,
                    secret_canary_verdict=dict(verdict),
                )
            )
            identities.append((host_ref, worker_id))
        if identities != sorted(identities) or len(identities) != len(set(identities)):
            _refuse("binding rows must be ordered and duplicate-free")
        return tuple(result)

    def __call__(self, host_ref: str, worker_id: str) -> RemoteWorkerHostBinding | None:
        if type(host_ref) is not str or type(worker_id) is not str:
            return None
        matches = [
            row for row in self._rows()
            if row.host_ref == host_ref and row.worker_id == worker_id
        ]
        if len(matches) > 1:
            _refuse("binding source contains duplicate exact rows")
        return matches[0] if matches else None


__all__ = [
    "BINDING_SOURCE_SCHEMA",
    "RemoteWorkerBindingSourceError",
    "RootManagedRemoteWorkerBindingSource",
]
