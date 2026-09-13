"""Strict root-managed configuration for the MH1 remote Worker Broker gateway."""
from __future__ import annotations

import dataclasses
import json
import os
import re
import stat
from collections.abc import Mapping
from pathlib import Path
from typing import Any


GATEWAY_CONFIG_SCHEMA = "mastermind.remote_worker_gateway_config/v1"
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_CONFIG_KEYS = frozenset(
    {
        "schema",
        "host_ref",
        "listen_host",
        "listen_port",
        "server_certificate_path",
        "server_private_key_path",
        "ca_certificate_path",
        "expected_control_client_certificate_sha256",
        "worker_broker_socket_path",
        "allowed_worker_ids",
        "max_request_bytes",
        "max_response_bytes",
        "read_timeout_seconds",
        "local_broker_timeout_seconds",
    }
)


class RemoteWorkerGatewayConfigError(ValueError):
    """Closed refusal for unsafe remote-gateway local configuration."""


def _id(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or _ID_RE.fullmatch(value) is None or "@" in value:
        raise RemoteWorkerGatewayConfigError(f"{field} is malformed")
    return value


def _path(value: Any, *, field: str) -> Path:
    try:
        result = Path(value)
    except TypeError as exc:
        raise RemoteWorkerGatewayConfigError(f"{field} must be a path") from exc
    if not result.is_absolute():
        raise RemoteWorkerGatewayConfigError(f"{field} must be absolute")
    return result


def _positive_int(value: Any, *, field: str, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        raise RemoteWorkerGatewayConfigError(f"{field} is outside the safe range")
    return value


def _timeout(value: Any, *, field: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise RemoteWorkerGatewayConfigError(f"{field} must be numeric") from exc
    if not 0.1 <= result <= 3600.0:
        raise RemoteWorkerGatewayConfigError(f"{field} is outside the safe range")
    return result


def _listen_host(value: Any) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise RemoteWorkerGatewayConfigError("listen_host is malformed")
    if value in {"0.0.0.0", "::", "*"} or "://" in value or "/" in value or "\\" in value:
        raise RemoteWorkerGatewayConfigError("listen_host must name one private interface")
    if len(value) > 253 or any(ch.isspace() for ch in value) or "\x00" in value:
        raise RemoteWorkerGatewayConfigError("listen_host is malformed")
    return value


@dataclasses.dataclass(frozen=True)
class RemoteWorkerGatewayConfig:
    schema: str
    host_ref: str
    listen_host: str
    listen_port: int
    server_certificate_path: Path
    server_private_key_path: Path = dataclasses.field(repr=False)
    ca_certificate_path: Path
    expected_control_client_certificate_sha256: str = dataclasses.field(repr=False)
    worker_broker_socket_path: Path
    allowed_worker_ids: tuple[str, ...]
    max_request_bytes: int = 2 * 1024 * 1024
    max_response_bytes: int = 16 * 1024 * 1024
    read_timeout_seconds: float = 30.0
    local_broker_timeout_seconds: float = 30.0

    def __post_init__(self) -> None:
        if self.schema != GATEWAY_CONFIG_SCHEMA:
            raise RemoteWorkerGatewayConfigError("gateway config schema is unsupported")
        object.__setattr__(self, "host_ref", _id(self.host_ref, field="host_ref"))
        object.__setattr__(self, "listen_host", _listen_host(self.listen_host))
        object.__setattr__(
            self,
            "listen_port",
            _positive_int(self.listen_port, field="listen_port", low=1, high=65535),
        )
        for field in (
            "server_certificate_path",
            "server_private_key_path",
            "ca_certificate_path",
            "worker_broker_socket_path",
        ):
            object.__setattr__(self, field, _path(getattr(self, field), field=field))
        digest = self.expected_control_client_certificate_sha256
        if not isinstance(digest, str) or _DIGEST_RE.fullmatch(digest) is None:
            raise RemoteWorkerGatewayConfigError(
                "expected_control_client_certificate_sha256 is malformed"
            )
        workers = tuple(_id(item, field="allowed_worker_ids item") for item in self.allowed_worker_ids)
        if not workers or workers != tuple(sorted(set(workers))):
            raise RemoteWorkerGatewayConfigError(
                "allowed_worker_ids must be non-empty, unique, and sorted"
            )
        object.__setattr__(self, "allowed_worker_ids", workers)
        object.__setattr__(
            self,
            "max_request_bytes",
            _positive_int(
                self.max_request_bytes,
                field="max_request_bytes",
                low=1024,
                high=16 * 1024 * 1024,
            ),
        )
        object.__setattr__(
            self,
            "max_response_bytes",
            _positive_int(
                self.max_response_bytes,
                field="max_response_bytes",
                low=1024,
                high=16 * 1024 * 1024,
            ),
        )
        object.__setattr__(
            self,
            "read_timeout_seconds",
            _timeout(self.read_timeout_seconds, field="read_timeout_seconds"),
        )
        object.__setattr__(
            self,
            "local_broker_timeout_seconds",
            _timeout(self.local_broker_timeout_seconds, field="local_broker_timeout_seconds"),
        )

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "RemoteWorkerGatewayConfig":
        if not isinstance(value, Mapping) or set(value) != _CONFIG_KEYS:
            raise RemoteWorkerGatewayConfigError(
                f"gateway config must contain exactly {sorted(_CONFIG_KEYS)!r}"
            )
        raw = dict(value)
        workers = raw.get("allowed_worker_ids")
        if not isinstance(workers, list):
            raise RemoteWorkerGatewayConfigError("allowed_worker_ids must be a JSON list")
        raw["allowed_worker_ids"] = tuple(workers)
        return cls(**raw)


def load_gateway_config(path: str | Path) -> RemoteWorkerGatewayConfig:
    """Load one root-owned, non-symlink, non-group/world-writable config file."""

    config_path = _path(path, field="config path")
    try:
        info = os.lstat(config_path)
    except OSError as exc:
        raise RemoteWorkerGatewayConfigError("gateway config file is unavailable") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise RemoteWorkerGatewayConfigError("gateway config must be a regular non-symlink file")
    if info.st_uid != 0:
        raise RemoteWorkerGatewayConfigError("gateway config must be root-owned")
    if stat.S_IMODE(info.st_mode) & 0o077:
        raise RemoteWorkerGatewayConfigError("gateway config must not be group/world accessible")
    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RemoteWorkerGatewayConfigError("gateway config is not valid UTF-8 JSON") from exc
    return RemoteWorkerGatewayConfig.from_mapping(raw)


__all__ = [
    "GATEWAY_CONFIG_SCHEMA",
    "RemoteWorkerGatewayConfig",
    "RemoteWorkerGatewayConfigError",
    "load_gateway_config",
]
