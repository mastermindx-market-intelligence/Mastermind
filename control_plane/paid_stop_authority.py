"""Same-process paid-stop receipt authority (bounded source-only qualifier).

This module is a *kernel/receipt qualifier* for the original paid stop owner.
It performs no privileged effect: no listener, no request, no lease, no
credential, no Runtime mutation, no source mutation, no installation.  It only
establishes, inside the already-privileged broker process, that

* the peer connection is the live kernel-captured root broker connection,
* the presented descriptor is a genuine read-only descriptor on the exact
  inflight receipt file the stop request names, and
* the receipt's contents reconstruct the exact canonical privileged request
  the caller's stop intent claims.

Authority objects are same-process capabilities with a private proven-origin
registry.  They are never serializable, never reconstructible from public
arguments, and never accepted from caller-supplied identity, receipts,
callbacks, PIDs, or type booleans.

Inert syscall seams: every kernel interaction is routed through the private
``_SYSCALLS`` record.  The default members are the real ``os``/``fcntl``
primitives and the real reference peer-capture/boot primitives; offline tests
replace the record with inert fakes.  Fixture-backed tests therefore prove
mechanics only -- they never assert live authorization, real euid 0, a real
Darwin boot identifier, or a real ``/var/db`` receipt.
"""

from __future__ import annotations

import datetime as dt
import fcntl
import hashlib
import json
import os
import re
import stat
import uuid as _uuid
import weakref
from dataclasses import dataclass
from typing import Any, Callable, Mapping

__all__ = [
    "PaidStopAuthorityError",
    "PaidStopAuthority",
    "StopAuthorityObservation",
    "StopIntent",
    "qualify_stop_receipt",
    "require_stop_authority",
]

REQUEST_SCHEMA = "mastermind.executive_privileged_action_request.v1"
PAID_STOP_REQUEST_SCHEMA = REQUEST_SCHEMA
PAID_STOP_ACTION = "executive.services.stop_paid"
PAID_STOP_EFFECT_CLASS = "SERVICE_CONTROL"
PAID_STOP_REQUEST_KEYS = frozenset({"schema", "request_id", "action", "args"})
PAID_STOP_ARG_KEYS = frozenset({"expected_definition_sha256"})
INFLIGHT_SCHEMA = "mastermind.executive_privileged_action_inflight.v1"
INFLIGHT_FIELDS = frozenset(
    {
        "schema",
        "request_id",
        "request_sha256",
        "action",
        "effect_class",
        "started_at",
        "release_sha",
    }
)
RECEIPT_DIR = "/private/var/db/mastermind-executive/privileged-actions/receipts/inflight"
_F_GETPATH = 50  # Darwin fcntl command; no Linux equivalent exists.
_MAX_RECEIPT_BYTES = 65536
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,63}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_UTC_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")


class PaidStopAuthorityError(ValueError):
    """Fixed nonsecret refusal code; no kernel, path, or payload reflection."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class StopIntent:
    """The caller's claimed stop identity, exactly these four fields."""

    request_id: str
    request_sha256: str
    release_sha: str
    expected_definition_sha256: str

    def to_dict(self) -> dict[str, str]:
        return {
            "request_id": self.request_id,
            "request_sha256": self.request_sha256,
            "release_sha": self.release_sha,
            "expected_definition_sha256": self.expected_definition_sha256,
        }


@dataclass(frozen=True, slots=True)
class _BrokerProcess:
    pid: int
    pidversion: int
    euid: int
    audit_identity_digest: str
    boot_id: str


@dataclass(frozen=True, slots=True)
class _ReceiptIdentity:
    device: int
    inode: int
    mode: int
    uid: int
    gid: int
    size: int
    mtime_ns: int
    ctime_ns: int

    @classmethod
    def from_stat(cls, value: os.stat_result) -> "_ReceiptIdentity":
        return cls(
            device=value.st_dev,
            inode=value.st_ino,
            mode=value.st_mode,
            uid=value.st_uid,
            gid=value.st_gid,
            size=value.st_size,
            mtime_ns=value.st_mtime_ns,
            ctime_ns=value.st_ctime_ns,
        )

    def as_tuple(self) -> tuple[int, ...]:
        return (
            self.device,
            self.inode,
            self.mode,
            self.uid,
            self.gid,
            self.size,
            self.mtime_ns,
            self.ctime_ns,
        )

    def to_dict(self) -> dict[str, int]:
        return {
            "device": self.device,
            "inode": self.inode,
            "mode": self.mode,
            "uid": self.uid,
            "gid": self.gid,
            "size": self.size,
            "mtime_ns": self.mtime_ns,
            "ctime_ns": self.ctime_ns,
        }


@dataclass(frozen=True, slots=True)
class StopAuthorityObservation:
    """Detached strict observation.  Data only; never accepted as authority."""

    broker_process: _BrokerProcess
    receipt_sha256: str
    receipt_identity: _ReceiptIdentity
    stop_intent: StopIntent

    def to_dict(self) -> dict[str, object]:
        return {
            "broker_process": {
                name: getattr(self.broker_process, name)
                for name in ("pid", "pidversion", "euid", "audit_identity_digest", "boot_id")
            },
            "receipt_sha256": self.receipt_sha256,
            "receipt_identity": self.receipt_identity.to_dict(),
            "stop_intent": self.stop_intent.to_dict(),
        }


@dataclass(frozen=True, slots=True, weakref_slot=True, eq=False, init=False)
class PaidStopAuthority:
    """Opaque same-process authority.  Only qualify_stop_receipt issues it."""

    def __new__(cls, *args: Any, **kwargs: Any):
        raise PaidStopAuthorityError("STOP_AUTHORITY_CONSTRUCTION_PRIVATE")

    def __reduce__(self) -> Any:
        raise PaidStopAuthorityError("STOP_AUTHORITY_NOT_SERIALIZABLE")


@dataclass(frozen=True, slots=True)
class _AuthorityState:
    peer: Any
    connection_ref: weakref.ReferenceType[Any]
    receiver_pid: int
    boot_id: str
    stop_intent: StopIntent
    expected_path: str
    receipt_sha256: str
    receipt_identity: _ReceiptIdentity
    owned_fd: int


# Private proven-origin registry.  Entries die with their authority object and
# never persist authority across processes or coordinate services.
_AUTHORITIES: "weakref.WeakKeyDictionary[PaidStopAuthority, _AuthorityState]" = (
    weakref.WeakKeyDictionary()
)


# ---------------------------------------------------------------- seams ----
def _reference_peer_functions() -> tuple[Callable[..., Any], Callable[..., Any]]:
    from control_plane.executive_peer_identity import capture_peer_identity,_current_capture
    return capture_peer_identity,_current_capture


def _reference_boot_session_id() -> str:
    from control_plane.codex_worker import ProcessInspector
    try:return ProcessInspector().boot_session_id()
    except Exception:
        raise PaidStopAuthorityError("BOOT_IDENTITY_UNAVAILABLE") from None


def _capture_reference(connection):
    try:return _reference_peer_functions()[0](connection)
    except Exception:raise PaidStopAuthorityError("BROKER_PEER_UNAVAILABLE") from None


def _verify_reference(peer):
    try:return _reference_peer_functions()[1](peer)
    except Exception:raise PaidStopAuthorityError("BROKER_PEER_UNAVAILABLE") from None


def _real_fcntl_getfl(descriptor: int) -> int:
    return fcntl.fcntl(descriptor, fcntl.F_GETFL)


def _real_fcntl_getpath(descriptor: int) -> str:
    raw = fcntl.fcntl(descriptor, _F_GETPATH, b"\x00" * 1024)
    return raw.split(b"\x00", 1)[0].decode("utf-8", "surrogateescape")


def _real_fcntl_setfd_cloexec(descriptor: int) -> None:
    flags = fcntl.fcntl(descriptor, fcntl.F_GETFD)
    fcntl.fcntl(descriptor, fcntl.F_SETFD, flags | fcntl.FD_CLOEXEC)


def _real_pread(descriptor: int, count: int, offset: int) -> bytes:
    return os.pread(descriptor, count, offset)


@dataclass(frozen=True)
class _Syscalls:
    """Kernel interaction surface.  Default members are the real primitives."""

    dup: Callable[[int], int] = os.dup
    close: Callable[[int], None] = os.close
    getpid: Callable[[], int] = os.getpid
    getfl: Callable[[int], int] = _real_fcntl_getfl
    getpath: Callable[[int], str] = _real_fcntl_getpath
    setfd_cloexec: Callable[[int], None] = _real_fcntl_setfd_cloexec
    fstat: Callable[[int], os.stat_result] = os.fstat
    pread: Callable[[int, int, int], bytes] = _real_pread
    capture_peer: Callable[[Any], Any] = _capture_reference
    verify_peer: Callable[[Any], Any] = _verify_reference
    boot_session_id: Callable[[], str] = _reference_boot_session_id


_REAL_SYSCALLS = _Syscalls()
_SYSCALLS: _Syscalls = _REAL_SYSCALLS


# ------------------------------------------------------------- validation ---
def _coerce_stop_intent(stop_intent: Any) -> StopIntent:
    if type(stop_intent) is StopIntent:
        intent = stop_intent
    elif type(stop_intent) is dict:
        if frozenset(stop_intent) != frozenset(
            (
                "request_id",
                "request_sha256",
                "release_sha",
                "expected_definition_sha256",
            )
        ):
            raise PaidStopAuthorityError("STOP_INTENT_KEYS_INVALID")
        intent = StopIntent(
            request_id=stop_intent["request_id"],
            request_sha256=stop_intent["request_sha256"],
            release_sha=stop_intent["release_sha"],
            expected_definition_sha256=stop_intent["expected_definition_sha256"],
        )
    else:
        raise PaidStopAuthorityError("STOP_INTENT_REQUIRED")
    if (
        type(intent.request_id) is not str
        or type(intent.request_sha256) is not str
        or type(intent.release_sha) is not str
        or type(intent.expected_definition_sha256) is not str
    ):
        raise PaidStopAuthorityError("STOP_INTENT_TYPES_INVALID")
    if _REQUEST_ID_RE.fullmatch(intent.request_id) is None:
        raise PaidStopAuthorityError("STOP_INTENT_REQUEST_ID_INVALID")
    if re.fullmatch(r"[0-9a-f]{40}",intent.release_sha) is None:
        raise PaidStopAuthorityError("STOP_INTENT_DIGEST_INVALID")
    for name in ("request_sha256", "expected_definition_sha256"):
        if _SHA256_RE.fullmatch(getattr(intent, name)) is None:
            raise PaidStopAuthorityError("STOP_INTENT_DIGEST_INVALID")
    return intent


def _bind_intent(stop_intent: Any) -> tuple[StopIntent, str]:
    """Validate intent and bind it to the reconstructed canonical request."""
    intent = _coerce_stop_intent(stop_intent)
    request_sha256 = hashlib.sha256(canonical_paid_stop_request(intent)).hexdigest()
    if intent.request_sha256 != request_sha256:
        raise PaidStopAuthorityError("STOP_INTENT_REQUEST_DIGEST_MISMATCH")
    return intent, request_sha256


def canonical_paid_stop_request(intent: StopIntent) -> bytes:
    """Reconstruct the exact canonical privileged stop_paid request bytes."""
    request = {
        "schema": PAID_STOP_REQUEST_SCHEMA,
        "request_id": intent.request_id,
        "action": PAID_STOP_ACTION,
        "args": {"expected_definition_sha256": intent.expected_definition_sha256},
    }
    if frozenset(request) != PAID_STOP_REQUEST_KEYS:
        raise PaidStopAuthorityError("STOP_REQUEST_RECONSTRUCTION_INVALID")
    if frozenset(request["args"]) != PAID_STOP_ARG_KEYS:
        raise PaidStopAuthorityError("STOP_REQUEST_RECONSTRUCTION_INVALID")
    return (
        json.dumps(request, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        + "\n"
    ).encode("ascii")


def _expected_receipt_path(request_id: str) -> str:
    expected = RECEIPT_DIR + "/" + request_id + ".json"
    if not expected.startswith(RECEIPT_DIR + "/"):
        raise PaidStopAuthorityError("RECEIPT_PATH_NAMESPACE_INVALID")
    try:
        expected.encode("ascii")
    except UnicodeEncodeError:
        raise PaidStopAuthorityError("RECEIPT_PATH_NAMESPACE_INVALID") from None
    return expected


def _validate_started_at(raw: Any, now: dt.datetime) -> dt.datetime:
    if type(raw) is not str or _UTC_RE.fullmatch(raw) is None:
        raise PaidStopAuthorityError("RECEIPT_STARTED_AT_INVALID")
    try:
        parsed = dt.datetime.strptime(raw, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        raise PaidStopAuthorityError("RECEIPT_STARTED_AT_INVALID") from None
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != raw:
        raise PaidStopAuthorityError("RECEIPT_STARTED_AT_NOT_CANONICAL")
    started = parsed.replace(tzinfo=dt.timezone.utc)
    # The existing original inflight lifecycle has no expiry. A clock or age
    # threshold cannot clear its reservation or create a retry allowance.
    return started


def _read_receipt_bytes(descriptor: int) -> tuple[bytes, str]:
    """Descriptor-relative reads only: no path open, no shared offset, no follow."""
    try:
        first = _SYSCALLS.pread(descriptor, _MAX_RECEIPT_BYTES + 1, 0)
    except (OSError, ValueError):
        raise PaidStopAuthorityError("RECEIPT_READ_UNAVAILABLE") from None
    if len(first) == 0 or len(first) > _MAX_RECEIPT_BYTES:
        raise PaidStopAuthorityError("RECEIPT_SIZE_OUT_OF_BOUNDS")
    try:
        second = _SYSCALLS.pread(descriptor, _MAX_RECEIPT_BYTES + 1, 0)
    except (OSError, ValueError):
        raise PaidStopAuthorityError("RECEIPT_READ_UNAVAILABLE") from None
    if first != second:
        raise PaidStopAuthorityError("RECEIPT_CONTENT_UNSTABLE")
    if b"\x00" in first:
        raise PaidStopAuthorityError("RECEIPT_CONTENT_NOT_TEXT")
    try:
        first.decode("utf-8", "strict")
    except UnicodeDecodeError:
        raise PaidStopAuthorityError("RECEIPT_CONTENT_NOT_UTF8") from None
    return first, hashlib.sha256(first).hexdigest()


def _parse_inflight_marker(content: bytes) -> Mapping[str, Any]:
    def pairs(items):
        result={}
        for key,value in items:
            if key in result:raise ValueError('duplicate')
            result[key]=value
        return result
    def nonfinite(value):raise ValueError('nonfinite')
    try:
        marker = json.loads(content.decode("utf-8", "strict"),object_pairs_hook=pairs,parse_constant=nonfinite)
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError, RecursionError):
        raise PaidStopAuthorityError("RECEIPT_MARKER_MALFORMED") from None
    if not isinstance(marker, Mapping):
        raise PaidStopAuthorityError("RECEIPT_MARKER_NOT_OBJECT")
    if frozenset(marker) != INFLIGHT_FIELDS:
        raise PaidStopAuthorityError("RECEIPT_MARKER_KEYS_INVALID")
    return marker


def _validate_marker_against_intent(
    marker: Mapping[str, Any],
    intent: StopIntent,
    request_sha256: str,
    now: dt.datetime,
) -> None:
    if marker["schema"] != INFLIGHT_SCHEMA or type(marker["schema"]) is not str:
        raise PaidStopAuthorityError("RECEIPT_MARKER_SCHEMA_INVALID")
    if marker["action"] != PAID_STOP_ACTION or type(marker["action"]) is not str:
        raise PaidStopAuthorityError("RECEIPT_MARKER_ACTION_INVALID")
    if marker["effect_class"] != PAID_STOP_EFFECT_CLASS or type(marker["effect_class"]) is not str:
        raise PaidStopAuthorityError("RECEIPT_MARKER_EFFECT_CLASS_INVALID")
    if marker["request_id"] != intent.request_id:
        raise PaidStopAuthorityError("RECEIPT_REQUEST_IDENTITY_MISMATCH")
    if marker["release_sha"] != intent.release_sha:
        raise PaidStopAuthorityError("RECEIPT_RELEASE_MISMATCH")
    if marker["request_sha256"] != request_sha256:
        raise PaidStopAuthorityError("RECEIPT_REQUEST_DIGEST_MISMATCH")
    _validate_started_at(marker["started_at"], now)


def _snapshot_broker_process(peer: Any) -> _BrokerProcess:
    boot_id = _validate_boot_id(_SYSCALLS.boot_session_id())
    try:
        euid = peer.euid
        pid = peer.pid
        pidversion = peer.pidversion
        if any(type(v) is not int for v in (euid,pid,pidversion)):
            raise PaidStopAuthorityError("BROKER_PEER_FIELDS_INVALID")
        digest = peer.audit_identity_digest
    except (AttributeError, TypeError, ValueError):
        raise PaidStopAuthorityError("BROKER_PEER_FIELDS_INVALID") from None
    if type(digest) is not str or _SHA256_RE.fullmatch(digest) is None:
        raise PaidStopAuthorityError("BROKER_PEER_FIELDS_INVALID")
    if euid != 0 or pid <= 0 or pidversion <= 0:
        raise PaidStopAuthorityError("BROKER_PEER_NOT_ROOT")
    return _BrokerProcess(
        pid=pid, pidversion=pidversion, euid=euid, audit_identity_digest=digest, boot_id=boot_id
    )


def _validate_boot_id(raw: Any) -> str:
    if type(raw) is not str:
        raise PaidStopAuthorityError("BOOT_IDENTITY_UNAVAILABLE")
    try:
        parsed = _uuid.UUID(raw)
    except (ValueError, AttributeError, TypeError):
        raise PaidStopAuthorityError("BOOT_IDENTITY_INVALID") from None
    if parsed.int == 0 or str(parsed) != raw.lower():
        raise PaidStopAuthorityError("BOOT_IDENTITY_INVALID")
    return raw


def _stable_fstat(descriptor: int) -> os.stat_result:
    try:
        first = _SYSCALLS.fstat(descriptor)
        second = _SYSCALLS.fstat(descriptor)
    except (OSError, ValueError):
        raise PaidStopAuthorityError("RECEIPT_DESCRIPTOR_UNAVAILABLE") from None
    identity_fields = (
        "st_dev",
        "st_ino",
        "st_mode",
        "st_uid",
        "st_gid",
        "st_size",
        "st_mtime_ns",
        "st_ctime_ns",
    )
    if any(getattr(first, name) != getattr(second, name) for name in identity_fields):
        raise PaidStopAuthorityError("RECEIPT_IDENTITY_UNSTABLE")
    return first


def _validate_receipt_descriptor(descriptor: int) -> os.stat_result:
    try:
        flags = _SYSCALLS.getfl(descriptor)
    except (OSError, ValueError):
        raise PaidStopAuthorityError("RECEIPT_DESCRIPTOR_UNAVAILABLE") from None
    if flags & os.O_ACCMODE != os.O_RDONLY:
        raise PaidStopAuthorityError("RECEIPT_FD_NOT_READ_ONLY")
    if flags & (os.O_WRONLY | os.O_RDWR | os.O_APPEND | os.O_TRUNC):
        raise PaidStopAuthorityError("RECEIPT_FD_WRITABLE")
    observed = _stable_fstat(descriptor)
    if not stat.S_ISREG(observed.st_mode):
        raise PaidStopAuthorityError("RECEIPT_NOT_REGULAR")
    if observed.st_nlink != 1:
        raise PaidStopAuthorityError("RECEIPT_LINK_COUNT_INVALID")
    if observed.st_uid != 0 or observed.st_gid != 0:
        raise PaidStopAuthorityError("RECEIPT_OWNERSHIP_INVALID")
    if stat.S_IMODE(observed.st_mode) != 0o600:
        raise PaidStopAuthorityError("RECEIPT_MODE_INVALID")
    if not 0 < observed.st_size <= _MAX_RECEIPT_BYTES:
        raise PaidStopAuthorityError("RECEIPT_SIZE_OUT_OF_BOUNDS")
    return observed


def _validate_receipt_path(descriptor: int, expected_path: str) -> None:
    try:
        observed = _SYSCALLS.getpath(descriptor)
    except (OSError, ValueError):
        raise PaidStopAuthorityError("RECEIPT_PATH_UNAVAILABLE") from None
    if type(observed) is not str or observed != expected_path:
        raise PaidStopAuthorityError("RECEIPT_PATH_MISMATCH")


def _owned_descriptor(source_fd: Any) -> int:
    if type(source_fd) is not int or isinstance(source_fd, bool) or source_fd < 0:
        raise PaidStopAuthorityError("RECEIPT_FD_REQUIRED")
    try:
        owned = _SYSCALLS.dup(source_fd)
    except (OSError, ValueError):
        raise PaidStopAuthorityError("RECEIPT_FD_DUP_UNAVAILABLE") from None
    try:
        _SYSCALLS.setfd_cloexec(owned)
    except (OSError, ValueError):
        _close_quietly(owned)
        raise PaidStopAuthorityError("RECEIPT_FD_CLOEXEC_UNAVAILABLE") from None
    return owned


def _close_quietly(descriptor: int) -> None:
    try:
        _SYSCALLS.close(descriptor)
    except (OSError, ValueError):
        pass


def _release_authority(state: _AuthorityState) -> None:
    _close_quietly(state.owned_fd)


# ------------------------------------------------------------ public API ----
def qualify_stop_receipt(fd: Any, connection: Any, *, stop_intent: Any) -> PaidStopAuthority:
    """Qualify the presented receipt descriptor against live broker evidence.

    Returns an opaque same-process authority.  Accepts no caller-declared
    identity: the peer comes from kernel capture, the boot identifier from the
    process inspector, and the receipt only from the presented descriptor.
    """
    intent, request_sha256 = _bind_intent(stop_intent)
    expected_path = _expected_receipt_path(intent.request_id)
    receiver_pid = _SYSCALLS.getpid()

    peer = _SYSCALLS.capture_peer(connection)
    _SYSCALLS.verify_peer(peer)
    broker = _snapshot_broker_process(peer)

    owned = _owned_descriptor(fd)
    try:
        observed = _validate_receipt_descriptor(owned)
        _validate_receipt_path(owned, expected_path)
        content, receipt_sha256 = _read_receipt_bytes(owned)
        marker = _parse_inflight_marker(content)
        _validate_marker_against_intent(
            marker, intent, request_sha256, dt.datetime.now(dt.timezone.utc)
        )
        identity = _ReceiptIdentity.from_stat(_stable_fstat(owned))
        if identity.as_tuple() != _ReceiptIdentity.from_stat(observed).as_tuple():
            raise PaidStopAuthorityError("RECEIPT_IDENTITY_UNSTABLE")
    except BaseException:
        _close_quietly(owned)
        raise

    authority = object.__new__(PaidStopAuthority)
    state = _AuthorityState(
        peer=peer,
        connection_ref=weakref.ref(connection),
        receiver_pid=receiver_pid,
        boot_id=broker.boot_id,
        stop_intent=intent,
        expected_path=expected_path,
        receipt_sha256=receipt_sha256,
        receipt_identity=identity,
        owned_fd=owned,
    )
    _AUTHORITIES[authority] = state
    weakref.finalize(authority, _release_authority, state)
    return authority


def require_stop_authority(value: Any, *, stop_intent: Any) -> StopAuthorityObservation:
    """Detach a strict observation only from a still-live proven authority."""
    intent, request_sha256 = _bind_intent(stop_intent)
    if type(value) is not PaidStopAuthority or value not in _AUTHORITIES:
        raise PaidStopAuthorityError("STOP_AUTHORITY_PROVENANCE_REQUIRED")
    state = _AUTHORITIES[value]

    if state.receiver_pid != _SYSCALLS.getpid():
        raise PaidStopAuthorityError("STOP_AUTHORITY_PROCESS_CHANGED")
    if state.stop_intent != intent:
        raise PaidStopAuthorityError("STOP_AUTHORITY_INTENT_MISMATCH")
    peer = state.peer
    if state.connection_ref() is None:
        raise PaidStopAuthorityError("STOP_AUTHORITY_CONNECTION_CLOSED")
    _SYSCALLS.verify_peer(peer)
    broker = _snapshot_broker_process(peer)
    if broker.boot_id != state.boot_id:
        raise PaidStopAuthorityError("STOP_AUTHORITY_BOOT_CHANGED")

    expected_path = _expected_receipt_path(intent.request_id)
    try:
        observed_stat = _validate_receipt_descriptor(state.owned_fd)
        _validate_receipt_path(state.owned_fd, expected_path)
        content, receipt_sha256 = _read_receipt_bytes(state.owned_fd)
        marker = _parse_inflight_marker(content)
        _validate_marker_against_intent(
            marker, intent, request_sha256, dt.datetime.now(dt.timezone.utc)
        )
        identity = _ReceiptIdentity.from_stat(_stable_fstat(state.owned_fd))
    except (OSError, ValueError) as exc:
        if isinstance(exc, PaidStopAuthorityError):
            raise
        raise PaidStopAuthorityError("RECEIPT_DESCRIPTOR_UNAVAILABLE") from None
    if identity.as_tuple() != state.receipt_identity.as_tuple():
        raise PaidStopAuthorityError("RECEIPT_GENERATION_DRIFT")
    if receipt_sha256 != state.receipt_sha256:
        raise PaidStopAuthorityError("RECEIPT_GENERATION_DRIFT")
    if observed_stat.st_size != len(content):
        raise PaidStopAuthorityError("RECEIPT_GENERATION_DRIFT")

    return StopAuthorityObservation(
        broker_process=broker,
        receipt_sha256=receipt_sha256,
        receipt_identity=identity,
        stop_intent=intent,
    )
