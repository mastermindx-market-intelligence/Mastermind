"""Connection-bound Darwin peer evidence for the disarmed C1 consumer.

Kernel capture is not service qualification or release authority. The Product
owner supplies separately qualified installed-service provenance. Public JSON,
UID equality, a PID, or a constructed Python record cannot substitute for it.
"""

from __future__ import annotations

import ctypes
from dataclasses import dataclass, field
from functools import lru_cache
import hashlib
import os
import re
import socket
import sys
from uuid import UUID
import weakref

__all__ = ["capture_peer_identity", "require_installed_service_peer"]

# Darwin sys/un.h. Audit layout is opaque: use libbsm's published accessors,
# not numeric offsets into the token. All 32 kernel bytes remain bound.
_SOL_LOCAL = 0
_LOCAL_PEERTOKEN = 0x006


class PeerIdentityError(ValueError):
    """Closed nonsecret failure code; no reflected kernel or caller payload."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class _AuditToken(ctypes.Structure):
    _fields_ = [("opaque", ctypes.c_uint32 * 8)]


@dataclass(frozen=True, slots=True)
class _KernelObservation:
    audit_token: bytes = field(repr=False)
    euid: int
    pid: int
    pidversion: int
    descriptor_identity: tuple[int, int, int, int]


@dataclass(frozen=True, slots=True, weakref_slot=True, eq=False, init=False)
class PeerIdentity:
    """Read-only capture. Only capture_peer_identity can establish provenance."""

    audit_token: bytes = field(repr=False)
    euid: int
    pid: int
    pidversion: int
    audit_identity_digest: str
    connection_instance: object = field(repr=False)

    def __new__(cls, *args, **kwargs):
        raise TypeError("use capture_peer_identity")


@dataclass(frozen=True, slots=True)
class _CaptureState:
    connection: weakref.ReferenceType[socket.socket]
    original: _KernelObservation
    connection_instance: object
    receiver_pid: int


# Ephemeral object provenance, local to this service process. These weak entries
# neither persist authority nor track effects/leases/Jobs or coordinate services.
_CAPTURES: weakref.WeakKeyDictionary[PeerIdentity, _CaptureState] = (
    weakref.WeakKeyDictionary()
)


@lru_cache(maxsize=1)
def _darwin_accessors():
    if sys.platform != "darwin":
        raise PeerIdentityError("PEER_PLATFORM_UNSUPPORTED")
    try:
        lib = ctypes.CDLL("/usr/lib/libbsm.dylib")
        functions = []
        for name, result_type in (
            ("audit_token_to_euid", ctypes.c_uint32),
            ("audit_token_to_pid", ctypes.c_int),
            ("audit_token_to_pidversion", ctypes.c_int),
        ):
            function = getattr(lib, name)
            function.argtypes = [_AuditToken]
            function.restype = result_type
            functions.append(function)
        return lib, tuple(functions)
    except (OSError, AttributeError):
        raise PeerIdentityError("PEER_AUDIT_API_UNAVAILABLE") from None


def _decode_audit(raw: bytes) -> tuple[int, int, int]:
    if type(raw) is not bytes or len(raw) != ctypes.sizeof(_AuditToken):
        raise PeerIdentityError("PEER_AUDIT_TOKEN_INVALID")
    _, accessors = _darwin_accessors()
    token = _AuditToken.from_buffer_copy(raw)
    euid, pid, version = (function(token) for function in accessors)
    if euid == 0xFFFFFFFF or pid <= 0 or version <= 0:
        raise PeerIdentityError("PEER_AUDIT_IDENTITY_INCOMPLETE")
    return euid, pid, version


def _descriptor_identity(connection: socket.socket) -> tuple[int, int, int, int]:
    descriptor = connection.fileno()
    if descriptor < 0:
        raise PeerIdentityError("PEER_CONNECTION_CLOSED")
    value = os.fstat(descriptor)
    return descriptor, value.st_dev, value.st_ino, value.st_mode


def _observe_socket(connection: socket.socket) -> _KernelObservation:
    if sys.platform != "darwin":
        raise PeerIdentityError("PEER_PLATFORM_UNSUPPORTED")
    if type(connection) is not socket.socket:
        raise PeerIdentityError("PEER_SOCKET_REQUIRED")
    try:
        if (
            connection.family != socket.AF_UNIX
            or connection.getsockopt(socket.SOL_SOCKET, socket.SO_TYPE)
            != socket.SOCK_STREAM
        ):
            raise PeerIdentityError("PEER_UNIX_STREAM_REQUIRED")
        # Darwin can return ENOPROTOOPT for SO_ACCEPTCONN on an otherwise valid
        # connected Unix socket. getpeername establishes the needed condition:
        # listening/unconnected descriptors have no connected peer.
        connection.getpeername()
        before = _descriptor_identity(connection)
        raw = connection.getsockopt(
            _SOL_LOCAL, _LOCAL_PEERTOKEN, ctypes.sizeof(_AuditToken)
        )
        euid, pid, version = _decode_audit(raw)
        after_raw = connection.getsockopt(
            _SOL_LOCAL, _LOCAL_PEERTOKEN, ctypes.sizeof(_AuditToken)
        )
        after = _descriptor_identity(connection)
        if before != after or raw != after_raw:
            raise PeerIdentityError("PEER_IDENTITY_CHANGED")
        return _KernelObservation(raw, euid, pid, version, after)
    except PeerIdentityError:
        raise
    except (OSError, ValueError):
        raise PeerIdentityError("PEER_KERNEL_IDENTITY_UNAVAILABLE") from None


def capture_peer_identity(accepted_socket: socket.socket) -> PeerIdentity:
    """Capture the connected kernel peer, retaining the exact socket identity.

    Does not read application messages, infer a service from UID/PID, or fall
    back to getpeereid/peer-supplied identity on an unsupported platform.
    """
    observation = _observe_socket(accepted_socket)
    result = object.__new__(PeerIdentity)
    for name in ("audit_token", "euid", "pid", "pidversion"):
        object.__setattr__(result, name, getattr(observation, name))
    object.__setattr__(
        result,
        "audit_identity_digest",
        hashlib.sha256(observation.audit_token).hexdigest(),
    )
    connection_instance = object()
    object.__setattr__(result, "connection_instance", connection_instance)
    _CAPTURES[result] = _CaptureState(
        weakref.ref(accepted_socket), observation, connection_instance, os.getpid()
    )
    return result


def _current_capture(peer: PeerIdentity) -> _CaptureState:
    if type(peer) is not PeerIdentity or peer not in _CAPTURES:
        raise PeerIdentityError("PEER_CAPTURE_PROVENANCE_REQUIRED")
    state = _CAPTURES[peer]
    if state.receiver_pid != os.getpid():
        raise PeerIdentityError("PEER_CAPTURE_PROCESS_CHANGED")
    connection = state.connection()
    if connection is None:
        raise PeerIdentityError("PEER_CONNECTION_CLOSED")
    current = _observe_socket(connection)
    if current != state.original:
        raise PeerIdentityError("PEER_IDENTITY_CHANGED")
    # Even a caller using object.__setattr__ cannot make altered public fields
    # match the captured observation retained privately by this process.
    if any(
        getattr(peer, name, None) != getattr(current, name)
        for name in ("audit_token", "euid", "pid", "pidversion")
    ):
        raise PeerIdentityError("PEER_CAPTURE_ALTERED")
    if (
        peer.audit_identity_digest != hashlib.sha256(current.audit_token).hexdigest()
        or peer.connection_instance is not state.connection_instance
    ):
        raise PeerIdentityError("PEER_CAPTURE_ALTERED")
    return state


@dataclass(frozen=True, slots=True)
class _QualifiedOwnerObservation:
    """Immutable owner observation, not authority by itself.

    Product's external factory must have checked real boot, SecCode dynamic
    validity/designated requirement, exact root-owned plist/argv/runtime/wrapper,
    and unchanged launchctl observations before and after qualification. This
    record does none of those checks and is never accepted by the public API.
    """

    real_boot_id: str
    audit_identity_digest: str
    service_label: str
    installed_release: str
    config_digest: str
    connection_instance: object = field(repr=False)
    euid: int
    pid: int
    pidversion: int
    plist_path: str
    plist_uid: int
    service_uid: int
    argv: tuple[str, ...]
    python_provenance_digest: str
    wrapper_digest: str
    designated_requirement_digest: str
    dynamic_code_identity_digest: str
    dynamic_code_status: int


@dataclass(frozen=True, slots=True, weakref_slot=True, eq=False, init=False)
class InstalledServicePeerBinding:
    """Opaque owner-issued identity. Cannot be built from public arguments."""

    def __new__(cls, *args, **kwargs):
        raise TypeError("installed binding requires private owner composition")


@dataclass(frozen=True, slots=True, weakref_slot=True, eq=False, init=False)
class TrustedServicePeerContext:
    """Exact connection result, not a grant or reusable bearer token."""

    real_boot_id: str
    audit_identity_digest: str
    service_label: str
    installed_release: str
    config_digest: str
    connection_instance: object = field(repr=False)

    def __new__(cls, *args, **kwargs):
        raise TypeError("use require_installed_service_peer")


@dataclass(frozen=True, slots=True)
class _BindingState:
    peer: weakref.ReferenceType[PeerIdentity]
    observation: _QualifiedOwnerObservation


# This object is neither a secret credential nor a serialized authority field.
# The private Product factory in this SAME trusted service process holds this
# capability only after its real qualification. Another process importing the
# module gets different identities; no socket/parser accepts these objects.
# Arbitrary code execution inside this trusted process is outside this boundary.
_OWNER_CAPABILITY = object()
_BINDINGS: weakref.WeakKeyDictionary[InstalledServicePeerBinding, _BindingState] = (
    weakref.WeakKeyDictionary()
)


def _fixed_text(value: object, maximum: int = 4096) -> bool:
    return (
        type(value) is str
        and 0 < len(value) <= maximum
        and value.isascii()
        and not any(ord(char) < 32 or ord(char) == 127 for char in value)
    )


def _validate_owner_observation(
    observation: _QualifiedOwnerObservation, peer: PeerIdentity
) -> None:
    if type(observation) is not _QualifiedOwnerObservation:
        raise PeerIdentityError("SERVICE_OWNER_OBSERVATION_REQUIRED")
    if type(observation.real_boot_id) is not str:
        raise PeerIdentityError("SERVICE_OWNER_OBSERVATION_INVALID")
    try:
        boot = UUID(observation.real_boot_id)
    except (ValueError, TypeError, AttributeError):
        raise PeerIdentityError("SERVICE_OWNER_OBSERVATION_INVALID") from None
    if boot.int == 0 or str(boot) != observation.real_boot_id:
        raise PeerIdentityError("SERVICE_OWNER_OBSERVATION_INVALID")
    for name in (
        "audit_identity_digest",
        "config_digest",
        "python_provenance_digest",
        "wrapper_digest",
        "designated_requirement_digest",
        "dynamic_code_identity_digest",
    ):
        value = getattr(observation, name)
        if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
            raise PeerIdentityError("SERVICE_OWNER_OBSERVATION_INVALID")
    if (
        type(observation.installed_release) is not str
        or re.fullmatch(r"[0-9a-f]{40}", observation.installed_release) is None
    ):
        raise PeerIdentityError("SERVICE_OWNER_OBSERVATION_INVALID")
    if (
        not _fixed_text(observation.service_label, 160)
        or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", observation.service_label)
        is None
        or not _fixed_text(observation.plist_path)
        or not observation.plist_path.startswith("/")
        or any(
            part in ("", ".", "..") for part in observation.plist_path.split("/")[1:]
        )
    ):
        raise PeerIdentityError("SERVICE_OWNER_OBSERVATION_INVALID")
    if type(observation.plist_uid) is not int or observation.plist_uid != 0:
        raise PeerIdentityError("SERVICE_OWNER_OBSERVATION_INVALID")
    if (
        type(observation.argv) is not tuple
        or not 1 <= len(observation.argv) <= 64
        or not all(_fixed_text(arg) for arg in observation.argv)
        or not observation.argv[0].startswith("/")
    ):
        raise PeerIdentityError("SERVICE_OWNER_OBSERVATION_INVALID")
    if (
        type(observation.dynamic_code_status) is not int
        or observation.dynamic_code_status != 0
    ):
        raise PeerIdentityError("SERVICE_DYNAMIC_CODE_NOT_VALID")
    for name in ("euid", "service_uid", "pid", "pidversion"):
        value = getattr(observation, name)
        if type(value) is not int or value < (
            0 if name in ("euid", "service_uid") else 1
        ):
            raise PeerIdentityError("SERVICE_OWNER_OBSERVATION_INVALID")
    if (
        observation.connection_instance is not peer.connection_instance
        or observation.audit_identity_digest != peer.audit_identity_digest
        or observation.euid != peer.euid
        or observation.service_uid != peer.euid
        or observation.pid != peer.pid
        or observation.pidversion != peer.pidversion
    ):
        raise PeerIdentityError("SERVICE_PEER_IDENTITY_MISMATCH")


def _bind_qualified_owner_observation(
    owner_capability: object,
    *,
    peer: PeerIdentity,
    observation: _QualifiedOwnerObservation,
) -> InstalledServicePeerBinding:
    """Private composition seam; Product retains the ACTUAL owner factory.

    The caller must already have performed R2 qualification outside this module.
    No environment/config/request switch or public constructor exposes this
    capability. Tests using the private capability prove mechanics only. The
    production owner factory is absent in C1 until separately implemented and
    qualified; this module does not install or enable one.
    """
    if owner_capability is not _OWNER_CAPABILITY:
        raise PeerIdentityError("SERVICE_OWNER_CAPABILITY_REQUIRED")
    _current_capture(peer)
    _validate_owner_observation(observation, peer)
    # Take a detached immutable snapshot, so even later reflective mutation of
    # the owner's source dataclass cannot alter this issued binding.
    snapshot = _QualifiedOwnerObservation(
        **{
            name: getattr(observation, name)
            for name in _QualifiedOwnerObservation.__dataclass_fields__
        }
    )
    binding = object.__new__(InstalledServicePeerBinding)
    _BINDINGS[binding] = _BindingState(weakref.ref(peer), snapshot)
    return binding


def require_installed_service_peer(
    peer: PeerIdentity, installed_binding: InstalledServicePeerBinding
) -> TrustedServicePeerContext:
    """Match fresh kernel evidence to the exact owner-qualified connection.

    SecCode, launchctl pre/post checks, installed-file trust, real-boot freshness
    and installed-policy arming belong to Product's private owner factory. A
    context is valid only in that original live connection/qualification; callers
    must requalify before an action after drift/restart. This is not an authority
    grant, a cross-process token, or an alternative to current release policy.
    """
    _current_capture(peer)
    if (
        type(installed_binding) is not InstalledServicePeerBinding
        or installed_binding not in _BINDINGS
    ):
        raise PeerIdentityError("SERVICE_OWNER_BINDING_REQUIRED")
    state = _BINDINGS[installed_binding]
    if state.peer() is not peer:
        raise PeerIdentityError("SERVICE_CONNECTION_MISMATCH")
    _validate_owner_observation(state.observation, peer)
    result = object.__new__(TrustedServicePeerContext)
    for name in (
        "real_boot_id",
        "audit_identity_digest",
        "service_label",
        "installed_release",
        "config_digest",
        "connection_instance",
    ):
        object.__setattr__(result, name, getattr(state.observation, name))
    return result
