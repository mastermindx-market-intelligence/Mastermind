"""Secure service packaging for the production-inert MH1 gateway core.

This module reads one root-owned local configuration, renders the reviewed
launchd template and runs the existing stateless gateway in the foreground.
It installs nothing, provisions no certificate, opens no listener at import,
and owns no Executive lifecycle, retry, queue or host-selection state.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import plistlib
import re
import signal
import stat
import sys
from pathlib import Path
from typing import Any, Awaitable, Callable, Mapping

from ops.executive_os.remote_worker_gateway import RemoteWorkerGateway
from ops.executive_os.remote_worker_gateway_config import (
    FABRIC_BROKER_TARGET,
    WORKER_BROKER_TARGET,
    HOST_OBSERVATION_GATEWAY_CONFIG_SCHEMA,
    SECRETARY_GATEWAY_CONFIG_SCHEMA, CONVERSATION_GATEWAY_CONFIG_SCHEMA,
    HermesSecretaryGatewayConfig, HermesConversationGatewayConfig,
    HermesSecretaryConversationBinding, HermesMetaConversationBinding,
    GatewayConfig,
    HostObservationGatewayConfig,
    HermesRoleMetadataReadBinding,
    RemoteWorkerGatewayConfig,
)
from ops.executive_os.remote_assignment_control import AssignmentControlBinding

SERVICE_LABEL = "com.mastermind.executive.remote-worker-gateway"
SERVICE_CHECK_SCHEMA = "mastermind.remote_worker_gateway_service_check/v1"
DEFAULT_GATEWAY_ROOT = Path("/Library/Application Support/MastermindExecutive/remote-worker-gateway")
DEFAULT_BROKER_SOCKET_ROOT = Path("/var/run/mastermind-executive")
DARWIN_FABRIC_SOCKET_ROOT = Path("/private/var/run/mastermind-executive")
LINUX_GATEWAY_ROOT = Path("/etc/mastermind-executive")
LINUX_HOST_OBSERVATION_ROOT = LINUX_GATEWAY_ROOT / "remote-worker-gateway"
LINUX_HOST_OBSERVATION_CONFIG = LINUX_HOST_OBSERVATION_ROOT / "host-observation.json"
LINUX_SECRETARY_CONVERSATION_CONFIG = LINUX_HOST_OBSERVATION_ROOT / "secretary-conversation.json"
LINUX_BROKER_SOCKET_ROOT = Path("/run")
MAX_CONFIG_BYTES = 64 * 1024
MAX_TLS_FILE_BYTES = 1024 * 1024
_ACCOUNT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]{0,63}$")
_GATEWAY_DIRECTORY_MODE = stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP

CONFIG_FIELDS = frozenset(
    {
        "schema",
        "host_ref",
        "listen_host",
        "listen_port",
        "certificate_path",
        "key_path",
        "ca_path",
        "expected_control_fingerprint",
        "broker_socket_path",
        "allowed_worker_ids",
        "allowed_operations",
        "request_timeout_seconds",
        "max_frame_bytes",
    }
)
HOST_OBSERVATION_CONFIG_FIELDS = (
    CONFIG_FIELDS - {"broker_socket_path", "allowed_worker_ids", "allowed_operations"}
) | {"profile", "hermes_role_metadata_read"}
SECRETARY_GATEWAY_CONFIG_FIELDS = HOST_OBSERVATION_CONFIG_FIELDS | {"hermes_secretary_conversation"}
CONVERSATION_GATEWAY_CONFIG_FIELDS = SECRETARY_GATEWAY_CONFIG_FIELDS | {"hermes_meta_conversation"}


class RemoteWorkerGatewayServiceError(ValueError):
    """A closed service-package or local-config refusal."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _refuse(code: str) -> None:
    raise RemoteWorkerGatewayServiceError(code)


def _existing_control_identity() -> tuple[str, str]:
    """Read the established Executive control identity without owning it here."""

    from ops.executive_os import acceptance as executive_acceptance

    user = executive_acceptance.CONTROL_USER
    group = executive_acceptance.CONTROL_GROUP
    if (
        type(user) is not str
        or type(group) is not str
        or _ACCOUNT_RE.fullmatch(user) is None
        or _ACCOUNT_RE.fullmatch(group) is None
    ):
        _refuse("GATEWAY_IDENTITY_INVALID")
    return user, group


def _safe_absolute(path: Path | str, *, code: str) -> Path:
    try:
        candidate = Path(path)
    except (TypeError, ValueError):
        _refuse(code)
    if (
        not candidate.is_absolute()
        or any(part in {"", ".", ".."} for part in candidate.parts)
        or "\x00" in os.fspath(candidate)
    ):
        _refuse(code)
    return candidate


def _within(path: Path, root: Path, *, code: str) -> None:
    try:
        path.relative_to(root)
    except ValueError:
        _refuse(code)


def _metadata_tuple(info: os.stat_result) -> tuple[int, ...]:
    return (
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_nlink,
        info.st_uid,
        info.st_gid,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def _verify_directory_chain(
    path: Path,
    *,
    root: Path,
    expected_owner_uid: int,
    expected_group_gid: int,
) -> None:
    _within(path, root, code="GATEWAY_PATH_ESCAPE")
    relative_parent = path.parent.relative_to(root)
    current = root
    candidates = [root]
    for part in relative_parent.parts:
        current = current / part
        candidates.append(current)
    for directory in candidates:
        try:
            info = directory.lstat()
        except OSError:
            raise RemoteWorkerGatewayServiceError("GATEWAY_DIRECTORY_INVALID") from None
        if (
            not stat.S_ISDIR(info.st_mode)
            or stat.S_ISLNK(info.st_mode)
            or info.st_uid != expected_owner_uid
            or info.st_gid != expected_group_gid
            or stat.S_IMODE(info.st_mode) != _GATEWAY_DIRECTORY_MODE
        ):
            _refuse("GATEWAY_DIRECTORY_INVALID")


def _secure_regular_file(
    path: Path,
    *,
    root: Path,
    expected_owner_uid: int,
    expected_group_gid: int,
    max_bytes: int,
    read_bytes: bool,
) -> bytes:
    _verify_directory_chain(
        path,
        root=root,
        expected_owner_uid=expected_owner_uid,
        expected_group_gid=expected_group_gid,
    )
    try:
        before = path.lstat()
    except OSError:
        raise RemoteWorkerGatewayServiceError("GATEWAY_FILE_INVALID") from None
    if (
        stat.S_ISLNK(before.st_mode)
        or not stat.S_ISREG(before.st_mode)
        or before.st_nlink != 1
        or before.st_uid != expected_owner_uid
        or before.st_gid != expected_group_gid
        or stat.S_IMODE(before.st_mode) != 0o440
        or before.st_size <= 0
    ):
        _refuse("GATEWAY_FILE_INVALID")
    if before.st_size > max_bytes:
        _refuse("GATEWAY_CONFIG_OVERSIZE" if read_bytes else "GATEWAY_FILE_INVALID")
    required_flags = ("O_NOFOLLOW", "O_CLOEXEC", "O_NONBLOCK")
    if any(not hasattr(os, name) for name in required_flags):
        _refuse("GATEWAY_FILE_INVALID")
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK
    try:
        descriptor = os.open(path, flags)
    except OSError:
        raise RemoteWorkerGatewayServiceError("GATEWAY_FILE_INVALID") from None
    try:
        try:
            opened = os.fstat(descriptor)
            if _metadata_tuple(opened) != _metadata_tuple(before):
                _refuse("GATEWAY_FILE_INVALID")
            chunks: list[bytes] = []
            total = 0
            if read_bytes:
                while True:
                    chunk = os.read(descriptor, min(65536, max_bytes + 1 - total))
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > max_bytes:
                        _refuse("GATEWAY_CONFIG_OVERSIZE")
                    chunks.append(chunk)
            final = path.lstat()
            if _metadata_tuple(final) != _metadata_tuple(opened):
                _refuse("GATEWAY_FILE_INVALID")
            return b"".join(chunks)
        except OSError:
            raise RemoteWorkerGatewayServiceError("GATEWAY_FILE_INVALID") from None
    finally:
        try:
            os.close(descriptor)
        except OSError:
            if sys.exc_info()[0] is None:
                raise RemoteWorkerGatewayServiceError("GATEWAY_FILE_INVALID") from None


def _closed_json(raw: bytes) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if type(key) is not str or key in result:
                _refuse("GATEWAY_CONFIG_INVALID")
            result[key] = value
        return result

    try:
        value = json.loads(raw.decode("utf-8", errors="strict"), object_pairs_hook=pairs)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise RemoteWorkerGatewayServiceError("GATEWAY_CONFIG_INVALID") from None
    loader_fields = (
        CONFIG_FIELDS,
        CONFIG_FIELDS | {"assignment_control"},
        CONFIG_FIELDS | {"broker_target", "expected_broker_peer_uid"},
        CONFIG_FIELDS
        | {"assignment_control", "broker_target", "expected_broker_peer_uid"},
    )
    loader_fields += tuple(fields | {"hermes_role_metadata_read"} for fields in loader_fields)
    loader_fields += (HOST_OBSERVATION_CONFIG_FIELDS, SECRETARY_GATEWAY_CONFIG_FIELDS,
                      CONVERSATION_GATEWAY_CONFIG_FIELDS)
    if type(value) is not dict or set(value) not in loader_fields:
        _refuse("GATEWAY_CONFIG_INVALID")
    return value


def _sorted_unique_strings(value: object, *, code: str) -> tuple[str, ...]:
    if (
        type(value) is not list
        or not value
        or any(type(item) is not str for item in value)
        or value != sorted(set(value))
    ):
        _refuse(code)
    return tuple(value)


def _canonical_config(config: GatewayConfig) -> bytes:
    value = {
        "schema": config.schema,
        "host_ref": config.host_ref,
        "listen_host": config.listen_host,
        "listen_port": config.listen_port,
        "certificate_path": os.fspath(config.certificate_path),
        "key_path": os.fspath(config.key_path),
        "ca_path": os.fspath(config.ca_path),
        "expected_control_fingerprint": config.expected_control_fingerprint,
        "request_timeout_seconds": float(config.request_timeout_seconds),
        "max_frame_bytes": config.max_frame_bytes,
    }
    if type(config) in (HostObservationGatewayConfig, HermesSecretaryGatewayConfig,
                        HermesConversationGatewayConfig):
        value["profile"] = config.profile
        if type(config) in (HermesSecretaryGatewayConfig, HermesConversationGatewayConfig):
            value["hermes_secretary_conversation"] = config.hermes_secretary_conversation.to_wire()
        if type(config) is HermesConversationGatewayConfig:
            value["hermes_meta_conversation"] = config.hermes_meta_conversation.to_wire()
    else:
        value.update(
            broker_socket_path=os.fspath(config.broker_socket_path),
            allowed_worker_ids=sorted(config.allowed_worker_ids),
            allowed_operations=sorted(config.allowed_operations),
        )
        if config.assignment_control is not None:
            value["assignment_control"] = config.assignment_control.to_wire()
        if config.broker_target == FABRIC_BROKER_TARGET:
            # The legacy configuration's canonical bytes remain unchanged.
            value["broker_target"] = config.broker_target
            value["expected_broker_peer_uid"] = config.expected_broker_peer_uid
    if config.hermes_role_metadata_read is not None:
        value["hermes_role_metadata_read"] = config.hermes_role_metadata_read.to_wire()
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _trusted_observation_ancestors(root: Path) -> None:
    """Qualify the shared namespace without changing its traversable mode."""
    try:
        for parent in root.parents:
            info = parent.lstat()
            if (not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode)
                    or info.st_uid != 0 or stat.S_IMODE(info.st_mode) & 0o022):
                _refuse("GATEWAY_DIRECTORY_INVALID")
    except OSError:
        raise RemoteWorkerGatewayServiceError("GATEWAY_DIRECTORY_INVALID") from None


def _qualified_tls_paths(document, *, root, expected_owner_uid, expected_group_gid):
    tls_paths = {
        key: _safe_absolute(document[key], code="GATEWAY_TLS_PATH_INVALID")
        for key in ("certificate_path", "key_path", "ca_path")
    }
    for tls_path in tls_paths.values():
        _within(tls_path, root, code="GATEWAY_PATH_ESCAPE")
        _secure_regular_file(
            tls_path, root=root, expected_owner_uid=expected_owner_uid,
            expected_group_gid=expected_group_gid, max_bytes=MAX_TLS_FILE_BYTES, read_bytes=False,
        )
    return tls_paths


def _request_limits(document):
    port, frame, timeout = (document.get(key) for key in
                            ("listen_port", "max_frame_bytes", "request_timeout_seconds"))
    if (type(port) is not int or not 1 <= port <= 65535
            or type(frame) is not int or type(timeout) not in (int, float)):
        _refuse("GATEWAY_CONFIG_INVALID")
    return port, frame, timeout


def decode_host_observation_gateway_config(raw: bytes, *, expected_group_gid: int) -> HostObservationGatewayConfig:
    """Qualify inert installation input against the one fixed Linux TLS root.

    The enroller owns the input file's custody. The running entrypoint still
    accepts this profile only at LINUX_HOST_OBSERVATION_CONFIG.
    """
    if (sys.platform != "linux" or type(expected_group_gid) is not int
            or expected_group_gid < 0 or type(raw) is not bytes or not 0 < len(raw) <= MAX_CONFIG_BYTES):
        _refuse("GATEWAY_CONFIG_INVALID")
    document = _closed_json(raw)
    if set(document) != HOST_OBSERVATION_CONFIG_FIELDS:
        _refuse("GATEWAY_CONFIG_INVALID")
    _trusted_observation_ancestors(LINUX_HOST_OBSERVATION_ROOT)
    paths = _qualified_tls_paths(document, root=LINUX_HOST_OBSERVATION_ROOT,
                                 expected_owner_uid=0, expected_group_gid=expected_group_gid)
    port, frame, timeout = _request_limits(document)
    try:
        return HostObservationGatewayConfig(
            schema=document["schema"], profile=document["profile"],
            host_ref=document["host_ref"], listen_host=document["listen_host"],
            listen_port=port, expected_control_fingerprint=document["expected_control_fingerprint"],
            hermes_role_metadata_read=HermesRoleMetadataReadBinding.from_wire(document["hermes_role_metadata_read"]),
            request_timeout_seconds=float(timeout), max_frame_bytes=frame, **paths,
        )
    except (KeyError, TypeError, ValueError):
        raise RemoteWorkerGatewayServiceError("GATEWAY_CONFIG_INVALID") from None


def _decode_conversation_gateway_config(raw: bytes, *, expected_group_gid: int, dual: bool):
    """Qualify the closed Secretary profile in the existing fixed Linux namespace."""
    if (type(dual) is not bool or sys.platform != "linux" or type(expected_group_gid) is not int
            or expected_group_gid < 0 or type(raw) is not bytes or not 0 < len(raw) <= MAX_CONFIG_BYTES):
        _refuse("GATEWAY_CONFIG_INVALID")
    document = _closed_json(raw)
    fields = CONVERSATION_GATEWAY_CONFIG_FIELDS if dual else SECRETARY_GATEWAY_CONFIG_FIELDS
    if set(document) != fields:
        _refuse("GATEWAY_CONFIG_INVALID")
    _trusted_observation_ancestors(LINUX_HOST_OBSERVATION_ROOT)
    paths = _qualified_tls_paths(document, root=LINUX_HOST_OBSERVATION_ROOT,
                                 expected_owner_uid=0, expected_group_gid=expected_group_gid)
    port, frame, timeout = _request_limits(document)
    try:
        binding = HermesSecretaryConversationBinding.from_wire(document["hermes_secretary_conversation"])
        _secure_regular_file(
            binding.credential_path, root=LINUX_HOST_OBSERVATION_ROOT, expected_owner_uid=0,
            expected_group_gid=expected_group_gid, max_bytes=257, read_bytes=False,
        )
        extra = {}
        if dual:
            meta = HermesMetaConversationBinding.from_wire(document["hermes_meta_conversation"])
            _secure_regular_file(
                meta.credential_path, root=LINUX_HOST_OBSERVATION_ROOT, expected_owner_uid=0,
                expected_group_gid=expected_group_gid, max_bytes=257, read_bytes=False,
            )
            extra["hermes_meta_conversation"] = meta
        config_type = HermesConversationGatewayConfig if dual else HermesSecretaryGatewayConfig
        return config_type(
            schema=document["schema"], profile=document["profile"],
            host_ref=document["host_ref"], listen_host=document["listen_host"],
            listen_port=port, expected_control_fingerprint=document["expected_control_fingerprint"],
            hermes_role_metadata_read=HermesRoleMetadataReadBinding.from_wire(document["hermes_role_metadata_read"]),
            hermes_secretary_conversation=binding,
            request_timeout_seconds=float(timeout), max_frame_bytes=frame, **paths, **extra,
        )
    except (KeyError, TypeError, ValueError):
        raise RemoteWorkerGatewayServiceError("GATEWAY_CONFIG_INVALID") from None


def decode_secretary_gateway_config(raw: bytes, *, expected_group_gid: int) -> HermesSecretaryGatewayConfig:
    return _decode_conversation_gateway_config(raw, expected_group_gid=expected_group_gid, dual=False)


def decode_conversation_gateway_config(raw: bytes, *, expected_group_gid: int) -> HermesConversationGatewayConfig:
    return _decode_conversation_gateway_config(raw, expected_group_gid=expected_group_gid, dual=True)


def load_remote_worker_gateway_config(
    path: Path | str,
    *,
    allowed_root: Path | str | None = None,
    broker_socket_root: Path | str | None = None,
    expected_owner_uid: int = 0,
    expected_group_gid: int | None = None,
) -> GatewayConfig:
    """Read one immutable root-owned local gateway configuration."""

    # Match the existing Linux installer's systemd configuration. Selecting
    # the platform namespace is not a fallback to a caller-selected root.
    config_path = _safe_absolute(path, code="GATEWAY_CONFIG_INVALID")
    explicit_root = allowed_root is not None
    observation_path = sys.platform == "linux" and config_path == LINUX_HOST_OBSERVATION_CONFIG
    secretary_path = sys.platform == "linux" and config_path == LINUX_SECRETARY_CONVERSATION_CONFIG
    if allowed_root is None:
        if observation_path or secretary_path:
            allowed_root = LINUX_HOST_OBSERVATION_ROOT
            _trusted_observation_ancestors(allowed_root)
        else:
            allowed_root = LINUX_GATEWAY_ROOT if sys.platform == "linux" else DEFAULT_GATEWAY_ROOT
    default_socket_root = broker_socket_root is None
    if default_socket_root:
        broker_socket_root = (LINUX_BROKER_SOCKET_ROOT if sys.platform == "linux"
                              else DEFAULT_BROKER_SOCKET_ROOT)
    if type(expected_owner_uid) is not int or expected_owner_uid < 0:
        _refuse("GATEWAY_IDENTITY_INVALID")
    if expected_group_gid is None:
        expected_group_gid = os.getegid()
    if type(expected_group_gid) is not int or expected_group_gid < 0:
        _refuse("GATEWAY_IDENTITY_INVALID")
    root = _safe_absolute(allowed_root, code="GATEWAY_ROOT_INVALID")
    socket_root = _safe_absolute(
        broker_socket_root, code="GATEWAY_BROKER_SOCKET_INVALID"
    )
    _within(config_path, root, code="GATEWAY_PATH_ESCAPE")
    raw = _secure_regular_file(
        config_path,
        root=root,
        expected_owner_uid=expected_owner_uid,
        expected_group_gid=expected_group_gid,
        max_bytes=MAX_CONFIG_BYTES,
        read_bytes=True,
    )
    document = _closed_json(raw)
    conversation_profile = document.get("schema") in (
        SECRETARY_GATEWAY_CONFIG_SCHEMA, CONVERSATION_GATEWAY_CONFIG_SCHEMA)
    if conversation_profile and (not secretary_path or explicit_root or not default_socket_root
                                  or expected_owner_uid != 0):
        _refuse("GATEWAY_CONFIG_INVALID")
    if secretary_path and not conversation_profile:
        _refuse("GATEWAY_CONFIG_INVALID")
    if conversation_profile:
        decoder = (decode_conversation_gateway_config
                   if document["schema"] == CONVERSATION_GATEWAY_CONFIG_SCHEMA
                   else decode_secretary_gateway_config)
        return decoder(raw, expected_group_gid=expected_group_gid)
    observation_only = document.get("schema") == HOST_OBSERVATION_GATEWAY_CONFIG_SCHEMA
    if observation_only and (not observation_path or explicit_root or not default_socket_root
                             or expected_owner_uid != 0):
        _refuse("GATEWAY_CONFIG_INVALID")
    if observation_path and not observation_only:
        _refuse("GATEWAY_CONFIG_INVALID")
    if observation_only:
        return decode_host_observation_gateway_config(raw, expected_group_gid=expected_group_gid)
    if (default_socket_root and sys.platform == 'darwin'
            and document.get('broker_target') == FABRIC_BROKER_TARGET):
        # This new target requires a canonical root-installed endpoint. Keep
        # the legacy worker-broker default/digest unchanged; never resolve an
        # arbitrary symlink to make the strict Fabric parent guard pass.
        socket_root = DARWIN_FABRIC_SOCKET_ROOT
    for key in (
        "schema",
        "host_ref",
        "listen_host",
        "certificate_path",
        "key_path",
        "ca_path",
        "expected_control_fingerprint",
    ):
        if type(document.get(key)) is not str:
            _refuse("GATEWAY_CONFIG_INVALID")
    tls_paths = _qualified_tls_paths(document, root=root, expected_owner_uid=expected_owner_uid,
                                     expected_group_gid=expected_group_gid)
    listen_port, frame_bytes, timeout = _request_limits(document)
    if type(document.get("broker_socket_path")) is not str:
        _refuse("GATEWAY_CONFIG_INVALID")
    broker_socket = _safe_absolute(
        document["broker_socket_path"], code="GATEWAY_BROKER_SOCKET_INVALID"
    )
    _within(
        broker_socket,
        socket_root,
        code="GATEWAY_BROKER_SOCKET_INVALID",
    )
    workers = _sorted_unique_strings(
        document.get("allowed_worker_ids"), code="GATEWAY_CONFIG_INVALID"
    )
    operations = _sorted_unique_strings(
        document.get("allowed_operations"), code="GATEWAY_CONFIG_INVALID"
    )
    if "broker_target" in document or "expected_broker_peer_uid" in document:
        # The optional broker endpoint fields are paired: never accept one alone.
        if "broker_target" not in document or "expected_broker_peer_uid" not in document:
            _refuse("GATEWAY_CONFIG_INVALID")
        if type(document["broker_target"]) is not str:
            _refuse("GATEWAY_CONFIG_INVALID")
        peer_uid = document["expected_broker_peer_uid"]
        if isinstance(peer_uid, bool) or not isinstance(peer_uid, int) or peer_uid <= 0:
            _refuse("GATEWAY_CONFIG_INVALID")
    try:
        return RemoteWorkerGatewayConfig(
            schema=document["schema"],
            host_ref=document["host_ref"],
            listen_host=document["listen_host"],
            listen_port=listen_port,
            certificate_path=tls_paths["certificate_path"],
            key_path=tls_paths["key_path"],
            ca_path=tls_paths["ca_path"],
            expected_control_fingerprint=document["expected_control_fingerprint"],
            broker_socket_path=broker_socket,
            allowed_worker_ids=frozenset(workers),
            allowed_operations=frozenset(operations),
            request_timeout_seconds=float(timeout),
            max_frame_bytes=frame_bytes,
            assignment_control=(AssignmentControlBinding.from_wire(document["assignment_control"])
                                if "assignment_control" in document else None),
            broker_target=document.get("broker_target", WORKER_BROKER_TARGET),
            expected_broker_peer_uid=document.get("expected_broker_peer_uid"),
            hermes_role_metadata_read=(HermesRoleMetadataReadBinding.from_wire(document["hermes_role_metadata_read"])
                                      if "hermes_role_metadata_read" in document else None),
        )
    except (TypeError, ValueError):
        raise RemoteWorkerGatewayServiceError("GATEWAY_CONFIG_INVALID") from None


def remote_worker_gateway_config_digest(config: GatewayConfig) -> str:
    if type(config) not in (RemoteWorkerGatewayConfig, HostObservationGatewayConfig,
                            HermesSecretaryGatewayConfig, HermesConversationGatewayConfig):
        raise TypeError("config must be a closed gateway profile")
    return hashlib.sha256(_canonical_config(config)).hexdigest()



def _path_argument(value: Path | str, *, code: str) -> str:
    return os.fspath(_safe_absolute(value, code=code))


def _replace_template(value: Any, replacements: Mapping[str, str]) -> Any:
    if isinstance(value, str):
        if value in replacements:
            return replacements[value]
        if value.startswith("__") and value.endswith("__"):
            _refuse("GATEWAY_PLIST_TEMPLATE_INVALID")
        return value
    if isinstance(value, list):
        return [_replace_template(item, replacements) for item in value]
    if isinstance(value, dict):
        return {key: _replace_template(item, replacements) for key, item in value.items()}
    return value


def render_remote_worker_gateway_plist(
    template_bytes: bytes,
    *,
    python_binary: Path | str,
    entrypoint: Path | str,
    config_path: Path | str,
    release_root: Path | str,
    control_home: Path | str,
    stdout_path: Path | str,
    stderr_path: Path | str,
) -> bytes:
    if not isinstance(template_bytes, bytes) or not 0 < len(template_bytes) <= 65536:
        _refuse("GATEWAY_PLIST_TEMPLATE_INVALID")
    try:
        value = plistlib.loads(template_bytes)
    except (plistlib.InvalidFileException, ValueError):
        raise RemoteWorkerGatewayServiceError("GATEWAY_PLIST_TEMPLATE_INVALID") from None
    if (
        not isinstance(value, dict)
        or value.get("Label") != SERVICE_LABEL
        or value.get("UserName") != "__CONTROL_USER__"
        or value.get("GroupName") != "__CONTROL_GROUP__"
    ):
        _refuse("GATEWAY_PLIST_TEMPLATE_INVALID")
    control_user, control_group = _existing_control_identity()
    replacements = {
        "__CONTROL_USER__": control_user,
        "__CONTROL_GROUP__": control_group,
        "__PYTHON_BINARY__": _path_argument(
            python_binary, code="GATEWAY_PLIST_ARGUMENT_INVALID"
        ),
        "__GATEWAY_ENTRYPOINT__": _path_argument(
            entrypoint, code="GATEWAY_PLIST_ARGUMENT_INVALID"
        ),
        "__GATEWAY_CONFIG__": _path_argument(
            config_path, code="GATEWAY_PLIST_ARGUMENT_INVALID"
        ),
        "__RELEASE_ROOT__": _path_argument(
            release_root, code="GATEWAY_PLIST_ARGUMENT_INVALID"
        ),
        "__CONTROL_HOME__": _path_argument(
            control_home, code="GATEWAY_PLIST_ARGUMENT_INVALID"
        ),
        "__GATEWAY_STDOUT__": _path_argument(
            stdout_path, code="GATEWAY_PLIST_ARGUMENT_INVALID"
        ),
        "__GATEWAY_STDERR__": _path_argument(
            stderr_path, code="GATEWAY_PLIST_ARGUMENT_INVALID"
        ),
    }
    rendered = _replace_template(value, replacements)
    expected_arguments = [
        replacements["__PYTHON_BINARY__"],
        "-I",
        "-S",
        "-B",
        replacements["__GATEWAY_ENTRYPOINT__"],
        "--config",
        replacements["__GATEWAY_CONFIG__"],
    ]
    if (
        rendered.get("ProgramArguments") != expected_arguments
        or rendered.get("WorkingDirectory") != replacements["__RELEASE_ROOT__"]
        or rendered.get("UserName") != replacements["__CONTROL_USER__"]
        or rendered.get("GroupName") != replacements["__CONTROL_GROUP__"]
        or rendered.get("RunAtLoad") is not True
        or rendered.get("KeepAlive") is not True
    ):
        _refuse("GATEWAY_PLIST_TEMPLATE_INVALID")
    environment = rendered.get("EnvironmentVariables")
    if not isinstance(environment, dict) or environment.get("HOME") != replacements[
        "__CONTROL_HOME__"
    ]:
        _refuse("GATEWAY_PLIST_TEMPLATE_INVALID")
    try:
        return plistlib.dumps(rendered, fmt=plistlib.FMT_XML, sort_keys=False)
    except (TypeError, ValueError):
        raise RemoteWorkerGatewayServiceError("GATEWAY_PLIST_TEMPLATE_INVALID") from None


async def wait_for_gateway_shutdown() -> None:
    loop = asyncio.get_running_loop()
    stopped = asyncio.Event()
    installed: list[signal.Signals] = []
    for item in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(item, stopped.set)
            installed.append(item)
        except (NotImplementedError, RuntimeError):
            continue
    if not installed:
        _refuse("GATEWAY_SIGNAL_UNAVAILABLE")
    try:
        await stopped.wait()
    finally:
        for item in installed:
            loop.remove_signal_handler(item)


def _lstat(path: Path) -> os.stat_result:
    try:
        return path.lstat()
    except OSError:
        raise RemoteWorkerGatewayServiceError("GATEWAY_BROKER_SOCKET_INVALID") from None


def _fabric_socket_identity(path: Path) -> tuple[int, ...]:
    """Prove the attended-Fabric broker endpoint before exposing the gateway.

    The Fabric socket is created by root, so every parent directory and the
    socket node itself must be root-owned and symlink-free, no parent may be
    group- or world-writable, and the socket carries no world permissions.
    This is endpoint metadata only: no Fabric connection, status request,
    admission check or START is ever attempted here.
    """
    if not path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        _refuse("GATEWAY_BROKER_SOCKET_INVALID")
    directories: list[Path] = []
    current = path.parent
    while True:
        directories.append(current)
        if current.parent == current:
            break
        current = current.parent
    for directory in reversed(directories):
        info = _lstat(directory)
        if (
            stat.S_ISLNK(info.st_mode)
            or not stat.S_ISDIR(info.st_mode)
            or info.st_uid != 0
            or stat.S_IMODE(info.st_mode) & 0o022
        ):
            _refuse("GATEWAY_BROKER_SOCKET_INVALID")
    info = _lstat(path)
    if (
        stat.S_ISLNK(info.st_mode)
        or not stat.S_ISSOCK(info.st_mode)
        or info.st_nlink != 1
        or info.st_uid != 0
        or stat.S_IMODE(info.st_mode) & 0o007
    ):
        _refuse("GATEWAY_BROKER_SOCKET_INVALID")
    return _metadata_tuple(info)


def _broker_socket_identity(path: Path) -> tuple[int, int, int, int, int]:
    """Prove the current local broker endpoint before exposing the gateway."""

    try:
        info = path.lstat()
    except OSError:
        raise RemoteWorkerGatewayServiceError("GATEWAY_BROKER_SOCKET_INVALID") from None
    if (
        stat.S_ISLNK(info.st_mode)
        or not stat.S_ISSOCK(info.st_mode)
        or info.st_nlink != 1
        or info.st_uid != os.geteuid()
        or info.st_gid != os.getegid()
        or stat.S_IMODE(info.st_mode) != 0o600
    ):
        _refuse("GATEWAY_BROKER_SOCKET_INVALID")
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid)


async def serve_remote_worker_gateway(
    config: GatewayConfig,
    *,
    gateway_factory: Callable[[GatewayConfig], Any] = RemoteWorkerGateway,
    shutdown_waiter: Callable[[], Awaitable[None]] = wait_for_gateway_shutdown,
) -> None:
    if type(config) not in (RemoteWorkerGatewayConfig, HostObservationGatewayConfig,
                            HermesSecretaryGatewayConfig, HermesConversationGatewayConfig):
        raise TypeError("config must be a closed gateway profile")
    observation_only = type(config) is not RemoteWorkerGatewayConfig
    fabric = not observation_only and config.broker_target == FABRIC_BROKER_TARGET
    if not observation_only:
        endpoint_identity = _fabric_socket_identity if fabric else _broker_socket_identity
        broker_identity = endpoint_identity(config.broker_socket_path)
    gateway = gateway_factory(config)
    if type(config) in (HermesSecretaryGatewayConfig, HermesConversationGatewayConfig):
        from ops.executive_os.hermes_secretary_forwarder import HermesSecretaryForwarder, HermesMetaForwarder
        gateway._secretary_forwarder = HermesSecretaryForwarder(
            config.hermes_secretary_conversation, expected_group_gid=os.getegid(),
            timeout_seconds=min(10.0, float(config.request_timeout_seconds)),
        )
        gateway._secretary_host_binding_sha256 = remote_worker_gateway_config_digest(config)
        if type(config) is HermesConversationGatewayConfig:
            gateway._meta_forwarder = HermesMetaForwarder(
                config.hermes_meta_conversation, expected_group_gid=os.getegid(),
                timeout_seconds=min(10.0, float(config.request_timeout_seconds)),
            )
            if gateway._secretary_forwarder.has_same_credential(gateway._meta_forwarder):
                _refuse("GATEWAY_CONVERSATION_CREDENTIAL_ALIAS")
            gateway._meta_host_binding_sha256 = gateway._secretary_host_binding_sha256
    if config.hermes_role_metadata_read is not None:
        from ops.executive_os.hermes_role_metadata_observer import HermesRoleMetadataObserver

        gateway._host_observer = HermesRoleMetadataObserver(
            host_binding_sha256=remote_worker_gateway_config_digest(config),
            implementation_sha=config.hermes_role_metadata_read.implementation_sha,
        )
    if not observation_only and endpoint_identity(config.broker_socket_path) != broker_identity:
        _refuse("GATEWAY_BROKER_SOCKET_INVALID")
    if not observation_only and not fabric:
        try:
            broker_status = await asyncio.wait_for(
                gateway.broker_call("status", {}),
                timeout=config.request_timeout_seconds,
            )
        except Exception:
            raise RemoteWorkerGatewayServiceError("GATEWAY_BROKER_UNAVAILABLE") from None
        if not isinstance(broker_status, Mapping):
            _refuse("GATEWAY_BROKER_UNAVAILABLE")
    # A Fabric target has no startup RPC at all: readiness is the verified
    # endpoint metadata above, never a fabricated status request or an
    # invented Attempt.  The bridge peer uid is enforced on every actual
    # request by WorkerBrokerClient.
    server = await gateway.start_server()
    try:
        async with server:
            await shutdown_waiter()
    finally:
        server.close()
        await server.wait_closed()


def run_remote_worker_gateway_service(config: GatewayConfig) -> None:
    asyncio.run(serve_remote_worker_gateway(config))


__all__ = [
    "CONFIG_FIELDS",
    "DEFAULT_BROKER_SOCKET_ROOT",
    "DEFAULT_GATEWAY_ROOT",
    "MAX_CONFIG_BYTES",
    "RemoteWorkerGatewayServiceError",
    "SERVICE_CHECK_SCHEMA",
    "SERVICE_LABEL",
    "load_remote_worker_gateway_config",
    "remote_worker_gateway_config_digest",
    "render_remote_worker_gateway_plist",
    "run_remote_worker_gateway_service",
    "serve_remote_worker_gateway",
    "wait_for_gateway_shutdown",
]
