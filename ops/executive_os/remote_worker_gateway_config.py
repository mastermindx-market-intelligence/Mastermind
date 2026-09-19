"""Root-managed configuration contract for the MH1 remote Worker gateway.

Only local operator configuration belongs here.  No endpoint, certificate path,
private key, or broker socket path is part of Executive lifecycle state or the
remote wire envelope.
"""
from __future__ import annotations

import dataclasses
import ipaddress
import re
from pathlib import Path

from control_plane.remote_worker_transport import (
    MAX_FRAME_BYTES,
    TransportValidationError,
    validate_host_ref,
)

REMOTE_WORKER_GATEWAY_CONFIG_SCHEMA = "mastermind.remote_worker_gateway_config/v1"

_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{1,127}$")


@dataclasses.dataclass(frozen=True)
class RemoteWorkerGatewayConfig:
    """One host-local gateway binding with no lifecycle or retry state."""

    schema: str
    host_ref: str
    listen_host: str
    listen_port: int
    certificate_path: Path
    key_path: Path
    ca_path: Path
    expected_control_fingerprint: str
    broker_socket_path: Path
    allowed_worker_ids: set[str] | frozenset[str]
    allowed_operations: set[str] | frozenset[str]
    request_timeout_seconds: float = 30.0
    max_frame_bytes: int = MAX_FRAME_BYTES

    def __post_init__(self) -> None:
        if self.schema != REMOTE_WORKER_GATEWAY_CONFIG_SCHEMA:
            raise ValueError("remote worker gateway config schema is unsupported")
        try:
            validate_host_ref(self.host_ref)
        except TransportValidationError as exc:
            raise ValueError("remote worker gateway host_ref is invalid") from exc

        try:
            listen_ip = ipaddress.ip_address(self.listen_host)
        except ValueError as exc:
            raise ValueError("remote worker gateway listen address must be an IP literal") from exc
        if listen_ip.is_unspecified or listen_ip.is_multicast or listen_ip.is_global:
            raise ValueError("remote worker gateway listen address is not private")
        if isinstance(self.listen_port, bool) or not isinstance(self.listen_port, int):
            raise ValueError("remote worker gateway listen port is invalid")
        if not 0 <= self.listen_port <= 65535:
            raise ValueError("remote worker gateway listen port is invalid")

        for field_name in ("certificate_path", "key_path", "ca_path"):
            path = Path(getattr(self, field_name))
            if not path.is_absolute() or not path.is_file():
                raise ValueError("remote worker gateway TLS configuration is invalid")
            object.__setattr__(self, field_name, path)

        if not _HEX64_RE.fullmatch(str(self.expected_control_fingerprint)):
            raise ValueError("remote worker gateway control fingerprint is invalid")

        broker_socket = Path(self.broker_socket_path)
        if not broker_socket.is_absolute():
            raise ValueError("remote worker gateway broker socket must be absolute")
        object.__setattr__(self, "broker_socket_path", broker_socket)

        workers = frozenset(self.allowed_worker_ids)
        operations = frozenset(self.allowed_operations)
        if not workers or any(not _ID_RE.fullmatch(str(value)) for value in workers):
            raise ValueError("remote worker gateway worker allowlist is invalid")
        if not operations or any(not _ID_RE.fullmatch(str(value)) for value in operations):
            raise ValueError("remote worker gateway operation allowlist is invalid")
        object.__setattr__(self, "allowed_worker_ids", workers)
        object.__setattr__(self, "allowed_operations", operations)

        if not 0.1 <= float(self.request_timeout_seconds) <= 3600:
            raise ValueError("remote worker gateway request timeout is invalid")
        if isinstance(self.max_frame_bytes, bool) or not isinstance(self.max_frame_bytes, int):
            raise ValueError("remote worker gateway frame ceiling is invalid")
        if not 1024 <= self.max_frame_bytes <= MAX_FRAME_BYTES:
            raise ValueError("remote worker gateway frame ceiling is invalid")