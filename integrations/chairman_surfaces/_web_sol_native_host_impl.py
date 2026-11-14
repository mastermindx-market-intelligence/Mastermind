"""Private transport bridge for the Web-Sol exact-surface extension.

Chrome owns this process's stdin/stdout through Native Messaging. While that
port is alive, the explicit Mastermind seam exchanges closed action receipts.
The host derives one private endpoint from a wrapper-fixed managed-profile
instance. It owns no target selection, persistence, lifecycle, retry or Wake
state.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import errno
import fcntl
import os
from pathlib import Path
import secrets
import select
import socket
import stat
import struct
import sys
import threading
import time
from typing import Any, Callable

from . import web_sol_instance as wsi
from . import web_sol_protocol as wsp
from . import web_sol_census_protocol as census
from . import web_sol_browser_protocol as browser

NATIVE_HOST_NAME = "com.mastermind.web_sol_surface"
EXTENSION_ID = "kmpbpccecbofdnhpcmjogofgmdodpnko"
ALLOWED_EXTENSION_ORIGIN = f"chrome-extension://{EXTENSION_ID}/"
MAX_MESSAGE_BYTES = 900 * 1024
MAX_UNIX_SOCKET_PATH_BYTES = 103
_HEADER = struct.Struct("@I")
_MATCH_FIELDS = (
    "binding_id",
    "conversation_fingerprint",
    "binding_fingerprint",
    "action",
    "operation_key",
    "nonce",
)
_PROBE_EVENT_KEYS = frozenset(
    {"kind", "conversation_fingerprint", "observation"}
)
_PROBE_KEYS = frozenset(
    {
        "schema",
        "target_present",
        "exact_conversation_loaded",
        "page_responsive",
        "document_ready_state",
        "visibility",
        "composer_available",
        "generation_state",
        "auth_required",
        "provider_error_present",
    }
)
_SERVER_SOCKET_IDENTITIES: dict[int, tuple[int, int]] = {}
_SERVER_LOCKS: dict[int, int] = {}
_TYPED_REENTRY_NONCES: set[str] = set()
MAX_TYPED_REENTRY_NONCES = 256
_BROWSER_NONCES: dict[str, datetime] = {}
MAX_BROWSER_NONCES = 2048


class NativeHostError(RuntimeError):
    """Stable, payload-free native bridge failure."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class ChromeChannelError(NativeHostError):
    """Host-terminal protocol corruption on Chrome's Native Messaging side."""


@dataclass(frozen=True)
class Deadline:
    """One immutable monotonic deadline shared by a complete exchange."""

    ends_at: float

    def remaining(
        self,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> float:
        remaining = float(self.ends_at) - float(monotonic())
        return remaining if remaining > 0.0 else 0.0


def _reject_duplicate_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise NativeHostError("frame_duplicate_key")
        result[key] = value
    return result


def _reject_constant(_value: str):
    raise NativeHostError("frame_invalid_json")


def _canonical_json(document: dict[str, Any]) -> bytes:
    if not isinstance(document, dict):
        raise NativeHostError("frame_not_object")
    try:
        payload = json.dumps(
            document,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise NativeHostError("frame_invalid_document") from exc
    if not payload:
        raise NativeHostError("frame_size_invalid")
    if len(payload) > MAX_MESSAGE_BYTES:
        raise NativeHostError("frame_too_large")
    return payload


def encode_frame(document: dict[str, Any]) -> bytes:
    """Encode one deterministic Chrome Native Messaging frame."""

    payload = _canonical_json(document)
    return _HEADER.pack(len(payload)) + payload


def _remaining_or_timeout(
    deadline: Deadline | None,
    monotonic: Callable[[], float],
    code: str,
) -> float | None:
    if deadline is None:
        return None
    try:
        remaining = deadline.remaining(monotonic)
    except Exception as exc:
        raise NativeHostError(code) from exc
    if remaining <= 0.0:
        raise NativeHostError(code)
    return remaining


def _wait_stream_ready(
    stream,
    *,
    writable: bool,
    deadline: Deadline | None,
    monotonic: Callable[[], float],
    code: str,
) -> None:
    remaining = _remaining_or_timeout(deadline, monotonic, code)
    if remaining is None:
        return
    try:
        descriptor = stream.fileno()
    except (AttributeError, OSError, TypeError, ValueError):
        return
    if not isinstance(descriptor, int) or descriptor < 0:
        raise NativeHostError("frame_stream_invalid")
    try:
        if writable:
            _, ready, _ = select.select([], [descriptor], [], remaining)
        else:
            ready, _, _ = select.select([descriptor], [], [], remaining)
    except (OSError, TypeError, ValueError) as exc:
        raise NativeHostError("frame_stream_invalid") from exc
    if not ready:
        raise NativeHostError(code)


def _read_exact(
    stream,
    size: int,
    *,
    deadline: Deadline | None = None,
    monotonic: Callable[[], float] = time.monotonic,
) -> bytes:
    chunks: list[bytes] = []
    remaining = size
    while remaining:
        _wait_stream_ready(
            stream,
            writable=False,
            deadline=deadline,
            monotonic=monotonic,
            code="frame_read_timeout",
        )
        try:
            chunk = stream.read(remaining)
        except (OSError, TypeError, ValueError) as exc:
            raise NativeHostError("frame_stream_invalid") from exc
        _remaining_or_timeout(deadline, monotonic, "frame_read_timeout")
        if not chunk:
            break
        if not isinstance(chunk, (bytes, bytearray)):
            raise NativeHostError("frame_stream_invalid")
        material = bytes(chunk)
        chunks.append(material)
        remaining -= len(material)
    return b"".join(chunks)


def read_frame(
    stream,
    *,
    deadline: Deadline | None = None,
    monotonic: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    """Read and strictly decode one bounded Native Messaging frame."""

    header = _read_exact(
        stream,
        _HEADER.size,
        deadline=deadline,
        monotonic=monotonic,
    )
    if not header:
        raise NativeHostError("frame_header_missing")
    if len(header) != _HEADER.size:
        raise NativeHostError("frame_header_truncated")
    (size,) = _HEADER.unpack(header)
    if size == 0:
        raise NativeHostError("frame_size_invalid")
    if size > MAX_MESSAGE_BYTES:
        raise NativeHostError("frame_too_large")
    payload = _read_exact(
        stream,
        size,
        deadline=deadline,
        monotonic=monotonic,
    )
    if len(payload) != size:
        raise NativeHostError("frame_payload_truncated")
    try:
        text = payload.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise NativeHostError("frame_invalid_utf8") from exc
    try:
        document = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_constant,
        )
    except NativeHostError:
        raise
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise NativeHostError("frame_invalid_json") from exc
    if not isinstance(document, dict):
        raise NativeHostError("frame_not_object")
    return document


def write_frame(
    stream,
    document: dict[str, Any],
    *,
    deadline: Deadline | None = None,
    monotonic: Callable[[], float] = time.monotonic,
) -> None:
    """Write every byte or fail; BinaryIO.write may legitimately be short.

    Zero progress, None, booleans and impossible byte counts are refusals, not
    successful delivery. Effect certainty is decided by the transport caller.
    """

    payload = encode_frame(document)
    offset = 0
    try:
        while offset < len(payload):
            _wait_stream_ready(
                stream,
                writable=True,
                deadline=deadline,
                monotonic=monotonic,
                code="frame_write_timeout",
            )
            written = stream.write(payload[offset:])
            _remaining_or_timeout(deadline, monotonic, "frame_write_timeout")
            if (
                type(written) is not int
                or written <= 0
                or written > len(payload) - offset
            ):
                raise NativeHostError("frame_write_failed")
            offset += written
        if hasattr(stream, "flush"):
            _wait_stream_ready(
                stream,
                writable=True,
                deadline=deadline,
                monotonic=monotonic,
                code="frame_write_timeout",
            )
            stream.flush()
            _remaining_or_timeout(deadline, monotonic, "frame_write_timeout")
    except NativeHostError:
        raise
    except (OSError, TypeError, ValueError) as exc:
        raise NativeHostError("frame_write_failed") from exc


def validate_caller_origin(value: Any) -> str:
    if value != ALLOWED_EXTENSION_ORIGIN:
        raise NativeHostError("caller_origin_refused")
    return ALLOWED_EXTENSION_ORIGIN


def _valid_transport_nonce(value: Any) -> bool:
    return (
        isinstance(value, str)
        and 16 <= len(value) <= 128
        and not any(character.isspace() for character in value)
    )


def _transport_nonce(factory: Callable[[], str], *, code: str) -> str:
    if not callable(factory):
        raise NativeHostError(code)
    try:
        value = factory()
    except Exception as exc:
        raise NativeHostError(code) from exc
    if not _valid_transport_nonce(value):
        raise NativeHostError(code)
    return value


def _accepted_peer_hello(
    value: Any,
    *,
    expected_role: str,
    expected_instance_id: str,
    expected_boot_nonce: str | None,
) -> dict[str, Any]:
    try:
        accepted = wsp.validate_transport_hello(value)
    except wsp.WebSolProtocolError as exc:
        raise NativeHostError("transport_hello_invalid") from exc
    if accepted["role"] != expected_role:
        raise NativeHostError("transport_role_mismatch")
    if accepted["adapter_instance_id"] != expected_instance_id:
        raise NativeHostError("transport_instance_mismatch")
    versions = (
        accepted["client_package_version"],
        accepted["native_package_version"],
        accepted["extension_package_version"],
    )
    if versions != (wsp.WEB_SOL_PACKAGE_VERSION,) * 3:
        raise NativeHostError("transport_version_mismatch")
    # Compatibility admission (ruling 16): the peer may present this
    # release's digest or exactly the one previous release's; anything else
    # is refused. Which set the connection is then held to is decided by
    # transport_capability_action_set at the request boundary.
    if (
        wsp.transport_capability_action_set(accepted["capability_digest"])
        is None
    ):
        raise NativeHostError("transport_capability_mismatch")
    if accepted["boot_nonce"] != expected_boot_nonce:
        raise NativeHostError("transport_boot_mismatch")
    return accepted


def complete_server_handshake(
    reader,
    writer,
    *,
    expected_role: str,
    expected_instance_id: str,
    boot_nonce: str,
    deadline: Deadline | None = None,
    monotonic: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    """Complete the two-message challenge exchange for one bound peer."""

    try:
        instance_id = wsi.validate_instance_id(expected_instance_id)
    except wsi.WebSolInstanceError as exc:
        raise NativeHostError("transport_instance_mismatch") from exc
    if expected_role not in {"client", "extension"}:
        raise NativeHostError("transport_role_mismatch")
    if not _valid_transport_nonce(boot_nonce):
        raise NativeHostError("transport_boot_invalid")

    first = _accepted_peer_hello(
        read_frame(
            reader,
            deadline=deadline,
            monotonic=monotonic,
        ),
        expected_role=expected_role,
        expected_instance_id=instance_id,
        expected_boot_nonce=None,
    )
    write_frame(
        writer,
        wsp.build_transport_hello_ack(first, boot_nonce=boot_nonce),
        deadline=deadline,
        monotonic=monotonic,
    )

    second = _accepted_peer_hello(
        read_frame(
            reader,
            deadline=deadline,
            monotonic=monotonic,
        ),
        expected_role=expected_role,
        expected_instance_id=instance_id,
        expected_boot_nonce=boot_nonce,
    )
    if second["challenge_nonce"] == first["challenge_nonce"]:
        raise NativeHostError("transport_challenge_reused")
    if second["capability_digest"] != first["capability_digest"]:
        # One connection presents exactly one capability release; admitting
        # each hello independently would let a peer mix two admitted sets.
        raise NativeHostError("transport_digest_changed")
    final_ack = wsp.build_transport_hello_ack(second, boot_nonce=boot_nonce)
    write_frame(
        writer,
        final_ack,
        deadline=deadline,
        monotonic=monotonic,
    )
    return final_ack


def _is_strict_bool(value: Any) -> bool:
    return type(value) is bool


def _valid_nullable_bool(value: Any) -> bool:
    return value is None or type(value) is bool


def _is_probe_event(message: Any) -> bool:
    if not isinstance(message, dict) or set(message) != _PROBE_EVENT_KEYS:
        return False
    if message.get("kind") != "MMX_WEB_SOL_PROBE":
        return False
    fingerprint = message.get("conversation_fingerprint")
    if fingerprint is not None and (
        not isinstance(fingerprint, str)
        or len(fingerprint) != 64
        or any(
            character not in "0123456789abcdef"
            for character in fingerprint
        )
    ):
        return False
    observation = message.get("observation")
    if not isinstance(observation, dict) or set(observation) != _PROBE_KEYS:
        return False
    if observation.get("schema") != wsp.PROBE_SCHEMA:
        return False
    if not all(
        _is_strict_bool(observation.get(field))
        for field in (
            "target_present",
            "exact_conversation_loaded",
            "page_responsive",
        )
    ):
        return False
    for field, allowed in (
        ("document_ready_state", {"loading", "interactive", "complete"}),
        ("visibility", {"visible", "hidden"}),
        ("generation_state", {"active", "idle", "unknown"}),
    ):
        if (
            not isinstance(observation.get(field), str)
            or observation[field] not in allowed
        ):
            return False
    return all(
        _valid_nullable_bool(observation.get(field))
        for field in (
            "composer_available",
            "auth_required",
            "provider_error_present",
        )
    )


def _timeout_code(request: dict[str, Any]) -> str:
    if request.get("schema") == browser.REQUEST_SCHEMA:
        return "browser_unavailable" if request.get("action") in browser.READ_ACTIONS else "browser_effect_unknown"
    if request.get("action") == "FOREGROUND":
        return "foreground_effect_unknown"
    if request.get("action") == "TYPED_REENTRY":
        return "typed_reentry_timeout"
    return "census_timeout" if request.get("schema") == census.REQUEST_SCHEMA else "inspect_timeout"


def _receipt_matches(
    request: dict[str, Any],
    receipt: dict[str, Any],
) -> bool:
    fields = (browser.IDENTITY_FIELDS if request.get("schema") == browser.REQUEST_SCHEMA
              else census.IDENTITY_FIELDS if request.get("schema") == census.REQUEST_SCHEMA else _MATCH_FIELDS)
    return all(receipt.get(field) == request[field] for field in fields)


def _untrusted_receipt_code(request: dict[str, Any], default: str) -> str:
    if request.get("schema") == browser.REQUEST_SCHEMA:
        return "browser_unavailable" if request.get("action") in browser.READ_ACTIONS else "browser_effect_unknown"
    if request.get("action") == "FOREGROUND":
        return "foreground_effect_unknown"
    if request.get("action") == "TYPED_REENTRY":
        return "typed_reentry_effect_unknown"
    return default


def _validate_timeout_seconds(timeout_seconds: float) -> float:
    if (
        not isinstance(timeout_seconds, (int, float))
        or isinstance(timeout_seconds, bool)
        or timeout_seconds <= 0
    ):
        raise NativeHostError("timeout_invalid")
    return float(timeout_seconds)


def forward_request(
    request: dict[str, Any],
    *,
    write_chrome: Callable[[dict[str, Any]], None],
    read_chrome: Callable[[float], dict[str, Any] | None],
    timeout_seconds: float,
    deadline: Deadline | None = None,
    monotonic: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    """Forward one exact action once and wait for its matching receipt."""

    timeout = _validate_timeout_seconds(timeout_seconds)
    is_census = request.get("schema") == census.REQUEST_SCHEMA if isinstance(request, dict) else False
    is_browser = request.get("schema") == browser.REQUEST_SCHEMA if isinstance(request, dict) else False
    accepted = (browser.validate_window(request) if is_browser else
                census.validate_census_window(request) if is_census else wsp.validate_request(request))
    if not is_census and not is_browser:
        accepted = wsp.validate_action_window(accepted, now=datetime.now(timezone.utc))
    if is_browser:
        current = datetime.now(timezone.utc)
        for key, expiry in list(_BROWSER_NONCES.items()):
            if expiry <= current:
                del _BROWSER_NONCES[key]
        if accepted["nonce"] in _BROWSER_NONCES:
            return browser.receipt(accepted, status="NONCE_REUSED")
        if len(_BROWSER_NONCES) >= MAX_BROWSER_NONCES:
            return browser.receipt(accepted, status="NONCE_LIMIT")
        _BROWSER_NONCES[accepted["nonce"]] = browser._timestamp(accepted["expires_at"])
    if (
        accepted.get("action") == wsp.SurfaceAction.TYPED_REENTRY.value
        and accepted["nonce"] in _TYPED_REENTRY_NONCES
    ):
        raise NativeHostError("nonce_reused")
    if (
        accepted.get("action") == wsp.SurfaceAction.TYPED_REENTRY.value
        and len(_TYPED_REENTRY_NONCES) >= MAX_TYPED_REENTRY_NONCES
    ):
        raise wsp._error(
            "$.nonce",
            "nonce ledger full; TYPED_REENTRY is closed",
        )
    if accepted.get("action") == wsp.SurfaceAction.TYPED_REENTRY.value:
        _TYPED_REENTRY_NONCES.add(accepted["nonce"])
    fields = browser.IDENTITY_FIELDS if is_browser else census.IDENTITY_FIELDS if is_census else _MATCH_FIELDS
    exchange_deadline = deadline or Deadline(ends_at=monotonic() + timeout)
    _remaining_or_timeout(
        exchange_deadline,
        monotonic,
        _timeout_code(accepted),
    )
    write_chrome(accepted)
    ignored = 0
    try:
        while True:
            remaining = _remaining_or_timeout(
                exchange_deadline,
                monotonic,
                _timeout_code(accepted),
            )
            assert remaining is not None
            message = read_chrome(remaining)
            if message is None:
                raise NativeHostError(_timeout_code(accepted))
            if _is_probe_event(message):
                ignored += 1
                if ignored > 32:
                    raise ChromeChannelError(
                        _untrusted_receipt_code(accepted, "probe_event_limit")
                    )
                continue
            if (
                isinstance(message, dict)
                and all(field in message for field in fields)
                and not _receipt_matches(accepted, message)
            ):
                raise ChromeChannelError(
                    _untrusted_receipt_code(accepted, "receipt_identity_mismatch")
                )
            try:
                receipt = (browser.validate_receipt(message) if is_browser else
                           census.validate_census_receipt(message) if is_census else wsp.validate_receipt(message))
            except wsp.WebSolProtocolError as exc:
                raise ChromeChannelError(
                    _untrusted_receipt_code(accepted, "receipt_invalid")
                ) from exc
            if not _receipt_matches(accepted, receipt):
                raise ChromeChannelError(
                    _untrusted_receipt_code(accepted, "receipt_identity_mismatch")
                )
            _remaining_or_timeout(exchange_deadline, monotonic, _timeout_code(accepted))
            return receipt
    except BaseException:
        raise


def _private_parent(path: Path, owner_uid: int) -> None:
    try:
        info = path.lstat()
    except OSError as exc:
        raise NativeHostError("socket_parent_unsafe") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise NativeHostError("socket_parent_unsafe")
    if info.st_uid != owner_uid or stat.S_IMODE(info.st_mode) & 0o077:
        raise NativeHostError("socket_parent_unsafe")


def _ensure_private_parent(path: Path, owner_uid: int) -> None:
    """Create the derived native transport root; never repair unsafe metadata."""
    try:
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
    except OSError:
        raise NativeHostError("socket_parent_unsafe") from None
    _private_parent(path, owner_uid)


def _endpoint_lock(destination: Path, owner_uid: int) -> int:
    """Keep one lock inode for the endpoint's lifetime and across restarts."""
    flags = os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    try:
        fd = os.open(str(destination) + ".lock", flags, 0o600)
    except OSError:
        raise NativeHostError("socket_lock_unsafe") from None
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != owner_uid or info.st_mode & 0o077 or info.st_size > 4096:
            raise NativeHostError("socket_lock_unsafe")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise NativeHostError("socket_owner_live") from None
        return fd
    except BaseException:
        os.close(fd)
        raise


def _recover_qualified_dead_endpoint(destination: Path, owner_uid: int, lock_fd: int) -> None:
    if not os.path.lexists(destination):
        return
    info = destination.lstat()
    if not stat.S_ISSOCK(info.st_mode) or info.st_uid != owner_uid or info.st_mode & 0o077:
        raise NativeHostError("socket_path_unsafe")
    identity = (info.st_dev, info.st_ino)
    try:
        os.lseek(lock_fd, 0, os.SEEK_SET)
        prior = json.loads(os.read(lock_fd, 4097))
        if (prior.get("schema") != "mastermind.native_socket_owner.v1"
                or prior.get("socket") != list(identity) or type(prior.get("pid")) is not int or prior["pid"] < 1):
            raise ValueError()
    except (ValueError, TypeError, AttributeError, OSError):
        # A legacy owner might be between bind and listen without holding our
        # lock. Its endpoint is not eligible for automatic reclamation.
        raise NativeHostError("socket_legacy_owner_unreconciled") from None
    try:
        os.kill(prior["pid"], 0)
    except ProcessLookupError:
        pass
    except OSError:
        raise NativeHostError("socket_owner_unreconciled") from None
    else:
        raise NativeHostError("socket_owner_live")
    probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    probe.settimeout(0.2)
    try:
        probe.connect(str(destination))
    except OSError as error:
        if error.errno != errno.ECONNREFUSED:
            raise NativeHostError("socket_owner_unreconciled") from None
    else:
        raise NativeHostError("socket_owner_live")
    finally:
        probe.close()
    _unlink_exact_owned_socket(destination, owner_uid=owner_uid, identity=identity)
    if os.path.lexists(destination):
        raise NativeHostError("socket_owner_unreconciled")


def _socket_identity(path: Path) -> tuple[int, int] | None:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return None
    except OSError:
        raise NativeHostError("socket_cleanup_failed") from None
    if not stat.S_ISSOCK(info.st_mode):
        return None
    return (info.st_dev, info.st_ino)


def _unlink_exact_owned_socket(
    path: Path,
    *,
    owner_uid: int,
    identity: tuple[int, int] | None,
    require_private_mode: bool = True,
) -> None:
    if identity is None:
        return
    try:
        info = path.lstat()
    except FileNotFoundError:
        return
    except OSError:
        raise NativeHostError("socket_cleanup_failed") from None
    if (
        not stat.S_ISSOCK(info.st_mode)
        or info.st_uid != owner_uid
        or (info.st_dev, info.st_ino) != identity
        or (
            require_private_mode
            and bool(stat.S_IMODE(info.st_mode) & 0o077)
        )
    ):
        return

    try:
        path.unlink()
    except FileNotFoundError:
        return
    except OSError:
        try:
            current = path.lstat()
        except FileNotFoundError:
            return
        except OSError:
            raise NativeHostError("socket_cleanup_failed") from None
        if (current.st_dev, current.st_ino) != identity:
            return
        raise NativeHostError("socket_cleanup_failed") from None

    try:
        current = path.lstat()
    except FileNotFoundError:
        return
    except OSError:
        raise NativeHostError("socket_cleanup_failed") from None
    if (current.st_dev, current.st_ino) == identity:
        raise NativeHostError("socket_cleanup_failed") from None


def open_private_server(
    path: str | Path,
    *,
    owner_uid: int,
) -> socket.socket:
    """Bind one derived user-private AF_UNIX transport endpoint."""

    destination = Path(path)
    _ensure_private_parent(destination.parent, owner_uid)
    if len(os.fsencode(destination)) > MAX_UNIX_SOCKET_PATH_BYTES:
        raise NativeHostError("socket_path_too_long")
    lock_fd = _endpoint_lock(destination, owner_uid)
    try:
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    except BaseException:
        os.close(lock_fd)
        raise
    identity: tuple[int, int] | None = None
    try:
        _recover_qualified_dead_endpoint(destination, owner_uid, lock_fd)
        server.bind(os.fspath(destination))
        identity = _socket_identity(destination)
        if identity is None:
            raise NativeHostError("socket_path_unsafe")
        _SERVER_SOCKET_IDENTITIES[id(server)] = identity
        _SERVER_LOCKS[id(server)] = lock_fd
        os.chmod(destination, 0o600)
        info = destination.lstat()
        if (
            not stat.S_ISSOCK(info.st_mode)
            or info.st_uid != owner_uid
            or stat.S_IMODE(info.st_mode) & 0o077
            or (info.st_dev, info.st_ino) != identity
        ):
            raise NativeHostError("socket_path_unsafe")
        owner = json.dumps({"schema": "mastermind.native_socket_owner.v1", "pid": os.getpid(), "socket": list(identity)}).encode()
        os.lseek(lock_fd, 0, os.SEEK_SET)
        os.ftruncate(lock_fd, 0)
        os.write(lock_fd, owner)
        os.fsync(lock_fd)
        server.listen(1)
        return server
    except Exception:
        _SERVER_SOCKET_IDENTITIES.pop(id(server), None)
        _SERVER_LOCKS.pop(id(server), None)
        server.close()
        try:
            _unlink_exact_owned_socket(destination, owner_uid=owner_uid,
                identity=identity, require_private_mode=False)
        finally:
            os.close(lock_fd)
        raise


def close_private_server(
    server: socket.socket,
    path: str | Path,
    *,
    owner_uid: int,
) -> None:
    destination = Path(path)
    identity = _SERVER_SOCKET_IDENTITIES.pop(id(server), None)
    lock_fd = _SERVER_LOCKS.pop(id(server), None)
    try:
        server.close()
    except OSError:
        pass
    try:
        _unlink_exact_owned_socket(destination, owner_uid=owner_uid, identity=identity)
    finally:
        if lock_fd is not None:
            os.close(lock_fd)


def _read_chrome_with_timeout(
    stream,
    timeout_seconds: float,
    *,
    deadline: Deadline | None = None,
    monotonic: Callable[[], float] = time.monotonic,
) -> dict[str, Any] | None:
    try:
        descriptor = stream.fileno()
    except (AttributeError, OSError) as exc:
        raise ChromeChannelError("chrome_stream_invalid") from exc
    wait_seconds = float(timeout_seconds)
    if deadline is not None:
        wait_seconds = min(wait_seconds, deadline.remaining(monotonic))
    if wait_seconds <= 0.0:
        return None
    try:
        readable, _, _ = select.select([descriptor], [], [], wait_seconds)
    except (OSError, ValueError) as exc:
        raise ChromeChannelError("chrome_stream_failed") from exc
    if not readable:
        return None
    try:
        return read_frame(
            stream,
            deadline=deadline,
            monotonic=monotonic,
        )
    except NativeHostError as exc:
        if exc.code == "frame_header_missing":
            return None
        raise ChromeChannelError(exc.code) from exc


def _write_chrome(
    stream,
    document: dict[str, Any],
    *,
    deadline: Deadline | None = None,
    monotonic: Callable[[], float] = time.monotonic,
) -> None:
    try:
        write_frame(
            stream,
            document,
            deadline=deadline,
            monotonic=monotonic,
        )
    except NativeHostError as exc:
        raise ChromeChannelError(exc.code) from exc


def _serve_client(
    client: socket.socket,
    chrome_in,
    chrome_out,
    *,
    timeout_seconds: float,
    expected_instance_id: str,
    boot_nonce: str,
    extension_actions=None,
    extension_digest=None,
    monotonic: Callable[[], float] = time.monotonic,
) -> None:
    timeout = _validate_timeout_seconds(timeout_seconds)
    started = monotonic()
    deadline = Deadline(ends_at=started + min(timeout, 5.0))
    with client:
        reader = client.makefile("rb", buffering=0)
        writer = client.makefile("wb", buffering=0)
        try:
            final_ack = complete_server_handshake(
                reader,
                writer,
                expected_role="client",
                expected_instance_id=expected_instance_id,
                boot_nonce=boot_nonce,
                deadline=deadline,
                monotonic=monotonic,
            )
            # The connection is held to the action set its own digest
            # describes, whatever the client sends after admission.
            admitted_actions = wsp.transport_capability_action_set(
                final_ack["capability_digest"]
            )
            request = read_frame(
                reader,
                deadline=deadline,
                monotonic=monotonic,
            )
            if request.get("schema") == census.REQUEST_SCHEMA:
                request = census.validate_census_window(request)
                if request["adapter_instance_id"] != expected_instance_id:
                    raise NativeHostError("transport_instance_mismatch")
                if (not wsp.transport_capability_admits_census(final_ack["capability_digest"])
                        or not wsp.transport_capability_admits_census(extension_digest)):
                    # Census joins the browser family's intersection: an
                    # absent or unknown digest at either end refuses before
                    # anything reaches Chrome. No census receipt builder
                    # exists for a refusal, so the connection closes typed.
                    raise NativeHostError("transport_capability_mismatch")
                deadline = Deadline(ends_at=started + census.TOTAL_SECONDS)
            elif request.get("schema") == browser.REQUEST_SCHEMA:
                request = browser.validate_window(request)
                if (request["adapter_instance_id"] != expected_instance_id
                        or request["transport_boot_nonce"] != boot_nonce):
                    raise NativeHostError("transport_instance_mismatch")
                deadline = Deadline(ends_at=started + browser.TOTAL_SECONDS)
                if (admitted_actions is None
                        or request["action"] not in admitted_actions
                        or extension_actions is None
                        or request["action"] not in extension_actions):
                    # An action outside either admitted set — client's or the
                    # extension's — is refused without reaching Chrome, so a
                    # mixed client/extension pair never dispatches an action
                    # one end cannot execute. The receipt keeps the refusal
                    # explicit instead of breaking the session's connection.
                    write_frame(
                        writer,
                        browser.receipt(
                            request,
                            status="ACTION_UNAVAILABLE",
                            effect="NOT_APPLIED",
                            data={"reason": "transport_capability_mismatch"},
                        ),
                        deadline=deadline,
                        monotonic=monotonic,
                    )
                    return
            elif request.get("schema") == wsp.ACTION_SCHEMA:
                request = wsp.validate_request(request)
                surface = wsp.transport_capability_surface_actions(
                    final_ack["capability_digest"]
                )
                peer_surface = wsp.transport_capability_surface_actions(
                    extension_digest
                )
                if (surface is None or request["action"] not in surface
                        or peer_surface is None
                        or request["action"] not in peer_surface):
                    # Surface actions join the same intersection; like census
                    # there is no refusal receipt shape, so the connection
                    # closes typed instead of dispatching one end cannot do.
                    raise NativeHostError("transport_capability_mismatch")
            receipt = forward_request(
                request,
                write_chrome=lambda document: _write_chrome(
                    chrome_out,
                    document,
                    deadline=deadline,
                    monotonic=monotonic,
                ),
                read_chrome=lambda remaining: _read_chrome_with_timeout(
                    chrome_in,
                    remaining,
                    deadline=deadline,
                    monotonic=monotonic,
                ),
                timeout_seconds=timeout,
                deadline=deadline,
                monotonic=monotonic,
            )
            write_frame(
                writer,
                receipt,
                deadline=deadline,
                monotonic=monotonic,
            )
        finally:
            reader.close()
            writer.close()


def _serve_guarded_client(
    client: socket.socket,
    chrome_in,
    chrome_out,
    *,
    timeout_seconds: float,
    expected_instance_id: str,
    boot_nonce: str,
    extension_actions=None,
    extension_digest=None,
    action_gate: threading.Lock,
    gate_pre_acquired: bool = False,
) -> str:
    acquired = gate_pre_acquired
    if not acquired:
        acquired = action_gate.acquire(blocking=False)
    if not acquired:
        try:
            client.close()
        except OSError:
            pass
        return "adapter_busy"
    try:
        _serve_client(
            client,
            chrome_in,
            chrome_out,
            timeout_seconds=timeout_seconds,
            expected_instance_id=expected_instance_id,
            boot_nonce=boot_nonce,
            extension_actions=extension_actions,
            extension_digest=extension_digest,
        )
    except ChromeChannelError:
        raise
    except (
        NativeHostError,
        wsp.WebSolProtocolError,
        OSError,
        socket.timeout,
    ):
        return "client_refused"
    finally:
        action_gate.release()
    return "served"


def run_native_host(
    chrome_in,
    chrome_out,
    *,
    caller_origin: str,
    expected_instance_id: str,
    socket_root: str | os.PathLike[str] | None = None,
    owner_uid: int | None = None,
    action_timeout_seconds: float = 5.0,
    boot_nonce_factory: Callable[[], str] | None = None,
) -> None:
    """Run one wrapper-fixed profile bridge until Chrome disconnects."""

    validate_caller_origin(caller_origin)
    timeout = _validate_timeout_seconds(action_timeout_seconds)
    try:
        instance_id = wsi.validate_instance_id(expected_instance_id)
        destination = wsi.socket_path(instance_id, root=socket_root)
    except wsi.WebSolInstanceError as exc:
        raise NativeHostError(exc.code) from exc
    uid = os.getuid() if owner_uid is None else owner_uid
    nonce_factory = boot_nonce_factory or (lambda: secrets.token_urlsafe(24))
    boot_nonce = _transport_nonce(
        nonce_factory,
        code="transport_boot_invalid",
    )
    startup_deadline = Deadline(ends_at=time.monotonic() + timeout)
    extension_ack = complete_server_handshake(
        chrome_in,
        chrome_out,
        expected_role="extension",
        expected_instance_id=instance_id,
        boot_nonce=boot_nonce,
        deadline=startup_deadline,
    )
    # The extension end may also present the one previous release's digest
    # (host respawned while the profile still runs the old bundle); every
    # client request is intersected with this set before it reaches Chrome.
    extension_actions = wsp.transport_capability_action_set(
        extension_ack["capability_digest"]
    )
    extension_digest = extension_ack["capability_digest"]
    server = open_private_server(destination, owner_uid=uid)
    action_gate = threading.Lock()
    fatal_event = threading.Event()
    fatal_errors: list[BaseException] = []
    fatal_lock = threading.Lock()

    def record_fatal(exc: BaseException) -> None:
        with fatal_lock:
            if not fatal_errors:
                fatal_errors.append(exc)
        fatal_event.set()

    def serve_reserved_client(peer: socket.socket) -> None:
        try:
            _serve_guarded_client(
                peer,
                chrome_in,
                chrome_out,
                timeout_seconds=timeout,
                expected_instance_id=instance_id,
                boot_nonce=boot_nonce,
                extension_actions=extension_actions,
                extension_digest=extension_digest,
                action_gate=action_gate,
                gate_pre_acquired=True,
            )
        except BaseException as exc:
            record_fatal(exc)

    def accept_one() -> None:
        peer, _ = server.accept()
        if not action_gate.acquire(blocking=False):
            try:
                peer.close()
            except OSError:
                pass
            return
        worker = threading.Thread(
            target=serve_reserved_client,
            args=(peer,),
            daemon=True,
            name="web-sol-action",
        )
        try:
            worker.start()
        except BaseException:
            action_gate.release()
            try:
                peer.close()
            except OSError:
                pass
            raise

    try:
        while True:
            if fatal_event.is_set():
                with fatal_lock:
                    fatal = fatal_errors[0] if fatal_errors else None
                if fatal is not None:
                    raise fatal
                raise NativeHostError("chrome_stream_failed")
            try:
                readable, _, _ = select.select(
                    [server, chrome_in],
                    [],
                    [],
                    1.0,
                )
            except (OSError, TypeError, ValueError) as exc:
                raise NativeHostError("host_poll_failed") from exc

            if server in readable:
                accept_one()

            if chrome_in in readable:
                if not action_gate.acquire(blocking=False):
                    continue
                try:
                    # The action worker may have consumed the receipt after
                    # select() returned but before this lock was acquired.
                    # Recheck under the single-reader gate; a stale readiness
                    # observation must not start a blocking unsolicited read.
                    ready_now, _, _ = select.select([chrome_in], [], [], 0)
                    if not ready_now:
                        continue
                    try:
                        unsolicited_deadline = Deadline(
                            ends_at=time.monotonic() + timeout
                        )
                        unsolicited = read_frame(
                            chrome_in,
                            deadline=unsolicited_deadline,
                        )
                    except NativeHostError as exc:
                        if exc.code == "frame_header_missing":
                            return
                        raise ChromeChannelError(exc.code) from exc
                    if not _is_probe_event(unsolicited):
                        raise ChromeChannelError("unexpected_chrome_message")
                finally:
                    action_gate.release()
    finally:
        close_private_server(server, destination, owner_uid=uid)


def _parse_main_arguments(arguments: list[str]) -> tuple[str, str]:
    # The generated per-profile executable wrapper fixes --instance-id before
    # forwarding Chrome's exact extension origin and optional parent-window
    # argument. The native host itself never discovers or elects a profile.
    if len(arguments) < 4 or arguments[1] != "--instance-id":
        raise NativeHostError("startup_arguments_invalid")
    try:
        instance_id = wsi.validate_instance_id(arguments[2])
    except wsi.WebSolInstanceError as exc:
        raise NativeHostError(exc.code) from exc
    origin = validate_caller_origin(arguments[3])
    extras = arguments[4:]
    if len(extras) > 1 or any(
        not value.startswith("--parent-window=") for value in extras
    ):
        raise NativeHostError("startup_arguments_invalid")
    return instance_id, origin


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv if argv is None else argv)
    try:
        instance_id, caller_origin = _parse_main_arguments(arguments)
        run_native_host(
            sys.stdin.buffer,
            sys.stdout.buffer,
            caller_origin=caller_origin,
            expected_instance_id=instance_id,
        )
    except (NativeHostError, wsp.WebSolProtocolError):
        return 65
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
