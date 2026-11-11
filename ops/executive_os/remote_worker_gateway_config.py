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

from ops.executive_os.remote_assignment_control import AssignmentControlBinding
from ops.executive_os.capacity_broker_topology import CONTROL_UID

from control_plane.remote_worker_transport import (
    MAX_FRAME_BYTES,
    TransportValidationError,
    validate_broker_operation,
    validate_host_ref,
)

REMOTE_WORKER_GATEWAY_CONFIG_SCHEMA = "mastermind.remote_worker_gateway_config/v1"
HOST_OBSERVATION_GATEWAY_CONFIG_SCHEMA = "mastermind.remote_worker_gateway_config/v2"
HOST_OBSERVATION_PROFILE = "hermes-role-metadata-read"
HERMES_ROLE_METADATA_READ_SCHEMA = "mastermind.hermes_role_metadata_read_binding/v1"
SECRETARY_GATEWAY_CONFIG_SCHEMA = "mastermind.remote_worker_gateway_config/v3"
SECRETARY_GATEWAY_PROFILE = "hermes-secretary-conversation"
HERMES_SECRETARY_CONVERSATION_SCHEMA = "mastermind.hermes_secretary_conversation_binding/v1"
SECRETARY_CREDENTIAL_PATH = Path("/etc/mastermind-executive/remote-worker-gateway/secretary-conversation.token")
CONVERSATION_GATEWAY_CONFIG_SCHEMA = "mastermind.remote_worker_gateway_config/v4"
CONVERSATION_GATEWAY_PROFILE = "hermes-role-conversations"
HERMES_META_CONVERSATION_SCHEMA = "mastermind.hermes_meta_conversation_binding/v1"
META_CREDENTIAL_PATH = Path("/etc/mastermind-executive/remote-worker-gateway/meta-conversation.token")

_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{1,127}$")
_SHA_RE = re.compile(r"[0-9a-f]{40}")

WORKER_BROKER_TARGET = "worker-broker"
FABRIC_BROKER_TARGET = "attended-fabric"
FABRIC_ALLOWED_OPERATIONS = frozenset(
    {
        "start",
        "status",
        "collect",
        "cancel",
        "validate",
        "attended-secret-canary",
        "assignment-seal",
        "assignment-seal-finalize",
    }
)


@dataclasses.dataclass(frozen=True)
class HermesRoleMetadataReadBinding:
    """An optional fixed read capability; this claim is not source attestation."""

    implementation_sha: str

    def __post_init__(self) -> None:
        if type(self.implementation_sha) is not str or _SHA_RE.fullmatch(self.implementation_sha) is None:
            raise ValueError("Hermes metadata read binding is invalid")

    @classmethod
    def from_wire(cls, value) -> HermesRoleMetadataReadBinding:
        if (type(value) is not dict or set(value) != {"schema", "implementation_sha"}
                or value["schema"] != HERMES_ROLE_METADATA_READ_SCHEMA):
            raise ValueError("Hermes metadata read binding is invalid")
        return cls(value["implementation_sha"])

    def to_wire(self) -> dict[str, str]:
        return {"schema": HERMES_ROLE_METADATA_READ_SCHEMA, "implementation_sha": self.implementation_sha}


def _validate_tls_listener(config) -> None:
    """One TLS/listener validator shared by the closed gateway profiles."""
    try:
        validate_host_ref(config.host_ref)
    except TransportValidationError as exc:
        raise ValueError("remote worker gateway host_ref is invalid") from exc
    try:
        listen_ip = ipaddress.ip_address(config.listen_host)
    except ValueError as exc:
        raise ValueError("remote worker gateway listen address must be an IP literal") from exc
    if listen_ip.is_unspecified or listen_ip.is_multicast or listen_ip.is_global:
        raise ValueError("remote worker gateway listen address is not private")
    if isinstance(config.listen_port, bool) or not isinstance(config.listen_port, int):
        raise ValueError("remote worker gateway listen port is invalid")
    if not 0 <= config.listen_port <= 65535:
        raise ValueError("remote worker gateway listen port is invalid")
    for field_name in ("certificate_path", "key_path", "ca_path"):
        path = Path(getattr(config, field_name))
        if not path.is_absolute() or not path.is_file():
            raise ValueError("remote worker gateway TLS configuration is invalid")
        object.__setattr__(config, field_name, path)
    if not _HEX64_RE.fullmatch(str(config.expected_control_fingerprint)):
        raise ValueError("remote worker gateway control fingerprint is invalid")


def _validate_request_limits(config) -> None:
    if not 0.1 <= float(config.request_timeout_seconds) <= 3600:
        raise ValueError("remote worker gateway request timeout is invalid")
    if isinstance(config.max_frame_bytes, bool) or not isinstance(config.max_frame_bytes, int):
        raise ValueError("remote worker gateway frame ceiling is invalid")
    if not 1024 <= config.max_frame_bytes <= MAX_FRAME_BYTES:
        raise ValueError("remote worker gateway frame ceiling is invalid")


@dataclasses.dataclass(frozen=True)
class HostObservationGatewayConfig:
    """The same MH1 listener with only its fixed host-read capability.

    This variant deliberately has no Worker identity, broker endpoint, operation
    allowlist, assignment Control, or provider execution configuration.
    """

    schema: str
    profile: str
    host_ref: str
    listen_host: str
    listen_port: int
    certificate_path: Path
    key_path: Path
    ca_path: Path
    expected_control_fingerprint: str
    hermes_role_metadata_read: HermesRoleMetadataReadBinding
    request_timeout_seconds: float = 4.0
    max_frame_bytes: int = MAX_FRAME_BYTES

    def __post_init__(self) -> None:
        if (self.schema != HOST_OBSERVATION_GATEWAY_CONFIG_SCHEMA
                or self.profile != HOST_OBSERVATION_PROFILE
                or type(self.hermes_role_metadata_read) is not HermesRoleMetadataReadBinding):
            raise ValueError("host observation gateway profile is invalid")
        if (type(self.listen_host) is not str
                or type(self.expected_control_fingerprint) is not str
                or type(self.request_timeout_seconds) not in (int, float)):
            raise ValueError("host observation gateway configuration is invalid")
        _validate_tls_listener(self)
        _validate_request_limits(self)


@dataclasses.dataclass(frozen=True)
class HermesSecretaryConversationBinding:
    """One existing native session and its separately enrolled role credential."""

    implementation_sha: str
    root_id: str
    session_id: str
    gateway_port: int
    credential_path: Path

    @classmethod
    def _wire_identity(cls):
        if cls is HermesSecretaryConversationBinding:
            return HERMES_SECRETARY_CONVERSATION_SCHEMA, SECRETARY_CREDENTIAL_PATH
        if cls is HermesMetaConversationBinding:
            return HERMES_META_CONVERSATION_SCHEMA, META_CREDENTIAL_PATH
        raise ValueError("Hermes conversation binding type is invalid")

    def __post_init__(self) -> None:
        _, credential_path = type(self)._wire_identity()
        if (type(self.implementation_sha) is not str or _SHA_RE.fullmatch(self.implementation_sha) is None
                or type(self.root_id) is not str or _ID_RE.fullmatch(self.root_id) is None
                or type(self.session_id) is not str or not self.session_id or len(self.session_id) > 1024
                or any(ord(c) < 32 or ord(c) == 127 for c in self.session_id)
                or type(self.gateway_port) is not int or not 1024 <= self.gateway_port <= 65535
                or self.credential_path != credential_path):
            raise ValueError("Hermes Secretary conversation binding is invalid")

    @classmethod
    def from_wire(cls, value) -> HermesSecretaryConversationBinding:
        schema, credential_path = cls._wire_identity()
        fields = {"schema", "implementation_sha", "root_id", "session_id", "gateway_port", "credential_path"}
        if (type(value) is not dict or set(value) != fields
                or value["schema"] != schema
                or value["credential_path"] != str(credential_path)):
            raise ValueError("Hermes Secretary conversation binding is invalid")
        return cls(value["implementation_sha"], value["root_id"], value["session_id"],
                   value["gateway_port"], credential_path)

    def to_wire(self) -> dict:
        schema, _ = type(self)._wire_identity()
        return {"schema": schema,
                "implementation_sha": self.implementation_sha, "root_id": self.root_id,
                "session_id": self.session_id, "gateway_port": self.gateway_port,
                "credential_path": str(self.credential_path)}



@dataclasses.dataclass(frozen=True)
class HermesMetaConversationBinding(HermesSecretaryConversationBinding):
    """The explicit Meta peer; inherited validation selects only its own contract."""


@dataclasses.dataclass(frozen=True)
class HermesSecretaryGatewayConfig:
    """The existing listener with metadata and a single bound Secretary session."""

    schema: str
    profile: str
    host_ref: str
    listen_host: str
    listen_port: int
    certificate_path: Path
    key_path: Path
    ca_path: Path
    expected_control_fingerprint: str
    hermes_role_metadata_read: HermesRoleMetadataReadBinding
    hermes_secretary_conversation: HermesSecretaryConversationBinding
    request_timeout_seconds: float = 4.0
    max_frame_bytes: int = MAX_FRAME_BYTES

    def __post_init__(self) -> None:
        if (self.schema != SECRETARY_GATEWAY_CONFIG_SCHEMA or self.profile != SECRETARY_GATEWAY_PROFILE
                or type(self.hermes_role_metadata_read) is not HermesRoleMetadataReadBinding
                or type(self.hermes_secretary_conversation) is not HermesSecretaryConversationBinding
                or self.hermes_role_metadata_read.implementation_sha
                   != self.hermes_secretary_conversation.implementation_sha
                or type(self.listen_host) is not str
                or type(self.expected_control_fingerprint) is not str
                or type(self.request_timeout_seconds) not in (int, float)):
            raise ValueError("Hermes Secretary gateway profile is invalid")
        _validate_tls_listener(self)
        _validate_request_limits(self)


@dataclasses.dataclass(frozen=True)
class HermesConversationGatewayConfig:
    """One incumbent listener with metadata and two distinct role capabilities."""

    schema: str
    profile: str
    host_ref: str
    listen_host: str
    listen_port: int
    certificate_path: Path
    key_path: Path
    ca_path: Path
    expected_control_fingerprint: str
    hermes_role_metadata_read: HermesRoleMetadataReadBinding
    hermes_secretary_conversation: HermesSecretaryConversationBinding
    hermes_meta_conversation: HermesMetaConversationBinding
    request_timeout_seconds: float = 4.0
    max_frame_bytes: int = MAX_FRAME_BYTES

    def __post_init__(self) -> None:
        if (self.schema != CONVERSATION_GATEWAY_CONFIG_SCHEMA or self.profile != CONVERSATION_GATEWAY_PROFILE
                or type(self.hermes_role_metadata_read) is not HermesRoleMetadataReadBinding
                or type(self.hermes_secretary_conversation) is not HermesSecretaryConversationBinding
                or type(self.hermes_meta_conversation) is not HermesMetaConversationBinding
                or self.hermes_role_metadata_read.implementation_sha
                   != self.hermes_meta_conversation.implementation_sha
                or self.hermes_role_metadata_read.implementation_sha
                   != self.hermes_secretary_conversation.implementation_sha
                or type(self.listen_host) is not str
                or type(self.expected_control_fingerprint) is not str
                or type(self.request_timeout_seconds) not in (int, float)):
            raise ValueError("Hermes Secretary gateway profile is invalid")
        _validate_tls_listener(self)
        _validate_request_limits(self)


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
    assignment_control: AssignmentControlBinding | None = None
    broker_target: str = WORKER_BROKER_TARGET
    expected_broker_peer_uid: int | None = None
    hermes_role_metadata_read: HermesRoleMetadataReadBinding | None = None

    def __post_init__(self) -> None:
        if self.hermes_role_metadata_read is not None and not isinstance(
            self.hermes_role_metadata_read, HermesRoleMetadataReadBinding
        ):
            raise ValueError("Hermes metadata read binding is invalid")
        if self.schema != REMOTE_WORKER_GATEWAY_CONFIG_SCHEMA:
            raise ValueError("remote worker gateway config schema is unsupported")
        _validate_tls_listener(self)

        broker_socket = Path(self.broker_socket_path)
        if not broker_socket.is_absolute():
            raise ValueError("remote worker gateway broker socket must be absolute")
        object.__setattr__(self, "broker_socket_path", broker_socket)

        workers = frozenset(self.allowed_worker_ids)
        operations = frozenset(self.allowed_operations)
        if not workers or any(
            not isinstance(value, str) or _ID_RE.fullmatch(value) is None
            for value in workers
        ):
            raise ValueError("remote worker gateway worker allowlist is invalid")
        if not operations:
            raise ValueError("remote worker gateway operation allowlist is invalid")
        try:
            operations = frozenset(validate_broker_operation(value) for value in operations)
        except TransportValidationError as exc:
            raise ValueError("remote worker gateway operation allowlist is invalid") from exc
        object.__setattr__(self, "allowed_worker_ids", workers)
        object.__setattr__(self, "allowed_operations", operations)
        if isinstance(self.broker_target, bool) or not isinstance(self.broker_target, str):
            raise ValueError("remote worker gateway broker target is invalid")
        if self.broker_target == FABRIC_BROKER_TARGET:
            # The fixed Unix peer owns the original Worker observations;
            # configured Control owns the finite filesystem seal, not a run.
            peer_uid = self.expected_broker_peer_uid
            if isinstance(peer_uid, bool) or not isinstance(peer_uid, int) or peer_uid <= 0:
                raise ValueError("remote worker gateway Fabric broker peer uid is invalid")
            if peer_uid == CONTROL_UID:
                raise ValueError(
                    "remote worker gateway Fabric broker peer uid is the Control uid"
                )
            if not operations <= FABRIC_ALLOWED_OPERATIONS:
                raise ValueError("remote worker gateway Fabric operation allowlist is invalid")
            object.__setattr__(self, "broker_target", FABRIC_BROKER_TARGET)
            object.__setattr__(self, "expected_broker_peer_uid", peer_uid)
            if self.assignment_control is not None and (
                not isinstance(self.assignment_control, AssignmentControlBinding)
                or self.assignment_control.control_uid != CONTROL_UID
                or self.assignment_control.worker_uid != peer_uid
            ):
                raise ValueError("gateway assignment Control binding differs from Fabric principals")
        elif self.broker_target == WORKER_BROKER_TARGET:
            if self.expected_broker_peer_uid is not None:
                raise ValueError(
                    "remote worker gateway broker peer uid requires the Fabric target"
                )
            object.__setattr__(self, "broker_target", WORKER_BROKER_TARGET)
        else:
            raise ValueError("remote worker gateway broker target is invalid")
        if self.assignment_control is not None:
            if (not isinstance(self.assignment_control, AssignmentControlBinding)
                    or workers != frozenset({self.assignment_control.worker_id})):
                raise ValueError("gateway assignment Control binding differs from worker")
        if (
            "assignment-seal" in operations
            and self.assignment_control is None
        ):
            raise ValueError("gateway assignment seal requires explicit Control binding")

        _validate_request_limits(self)


GatewayConfig = (RemoteWorkerGatewayConfig | HostObservationGatewayConfig
                 | HermesSecretaryGatewayConfig | HermesConversationGatewayConfig)
