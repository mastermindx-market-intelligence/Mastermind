"""Private transport bridge for the Web-Sol exact-surface extension.

Chrome owns this process's stdin/stdout through Native Messaging.  While that
port is alive, the host exposes one fixed user-local AF_UNIX socket so the
explicit Mastermind Web-Sol seam can exchange one closed action/receipt at a
time.  The host owns no target selection, persistence, lifecycle, retry, Wake,
or provider/account authority.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import select
import socket
import stat
import struct
import sys
import time
from typing import Any, Callable

from . import web_sol_protocol as wsp

NATIVE_HOST_NAME = "com.mastermind.web_sol_surface"
EXTENSION_ID = "kmpbpccecbofdnhpcmjogofgmdodpnko"
ALLOWED_EXTENSION_ORIGIN = f"chrome-extension://{EXTENSION_ID}/"
SOCKET_PATH = "~/Library/Application Support/Mastermind/control-room/web_sol_surface.sock"
MAX_MESSAGE_BYTES = 64 * 1024

_HEADER = struct.Struct("@I")
_MATCH_FIELDS = (
    "binding_id",
    "conversation_fingerprint",
    "binding_fingerprint",
    "binding_revision",
    "action",
    "operation_key",
    "nonce",
)
_PROBE_EVENT_KEYS = frozenset({"kind", "conversation_fingerprint", "observation"})
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


class NativeHostError(RuntimeError):
    """Stable, payload-free native bridge failure."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


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


def _read_exact(stream, size: int) -> bytes:
    chunks: list[bytes] = []
    remaining = size
    while remaining:
        chunk = stream.read(remaining)
        if not chunk:
            break
        if not isinstance(chunk, (bytes, bytearray)):
            raise NativeHostError("frame_stream_invalid")
        material = bytes(chunk)
        chunks.append(material)
        remaining -= len(material)
    return b"".join(chunks)


def read_frame(stream) -> dict[str, Any]:
    """Read and strictly decode one bounded Native Messaging frame."""

    header = _read_exact(stream, _HEADER.size)
    if not header:
        raise NativeHostError("frame_header_missing")
    if len(header) != _HEADER.size:
        raise NativeHostError("frame_header_truncated")
    (size,) = _HEADER.unpack(header)
    if size == 0:
        raise NativeHostError("frame_size_invalid")
    if size > MAX_MESSAGE_BYTES:
        raise NativeHostError("frame_too_large")
    payload = _read_exact(stream, size)
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


def write_frame(stream, document: dict[str, Any]) -> None:
    payload = encode_frame(document)
    try:
        stream.write(payload)
        if hasattr(stream, "flush"):
            stream.flush()
    except OSError as exc:
        raise NativeHostError("frame_write_failed") from exc


def validate_caller_origin(value: Any) -> str:
    if value != ALLOWED_EXTENSION_ORIGIN:
        raise NativeHostError("caller_origin_refused")
    return ALLOWED_EXTENSION_ORIGIN


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
        or any(character not in "0123456789abcdef" for character in fingerprint)
    ):
        return False
    observation = message.get("observation")
    if not isinstance(observation, dict) or set(observation) != _PROBE_KEYS:
        return False
    if observation.get("schema") != wsp.PROBE_SCHEMA:
        return False
    if not all(
        _is_strict_bool(observation.get(field))
        for field in ("target_present", "exact_conversation_loaded", "page_responsive")
    ):
        return False
    if observation.get("document_ready_state") not in {"loading", "interactive", "complete"}:
        return False
    if observation.get("visibility") not in {"visible", "hidden"}:
        return False
    if observation.get("generation_state") not in {"active", "idle", "unknown"}:
        return False
    if not all(
        _valid_nullable_bool(observation.get(field))
        for field in ("composer_available", "auth_required", "provider_error_present")
    ):
        return False
    return True


def _timeout_code(request: dict[str, Any]) -> str:
    return "foreground_effect_unknown" if request["action"] == "FOREGROUND" else "inspect_timeout"


def _receipt_matches(request: dict[str, Any], receipt: dict[str, Any]) -> bool:
    return all(receipt[field] == request[field] for field in _MATCH_FIELDS)


def forward_request(
    request: dict[str, Any],
    *,
    write_chrome: Callable[[dict[str, Any]], None],
    read_chrome: Callable[[float], dict[str, Any] | None],
    timeout_seconds: float,
) -> dict[str, Any]:
    """Forward one exact action once and wait for its matching receipt."""

    if not isinstance(timeout_seconds, (int, float)) or isinstance(timeout_seconds, bool) or timeout_seconds <= 0:
        raise NativeHostError("timeout_invalid")
    accepted = wsp.validate_request(request)
    write_chrome(accepted)
    deadline = time.monotonic() + float(timeout_seconds)
    ignored = 0
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise NativeHostError(_timeout_code(accepted))
        message = read_chrome(remaining)
        if message is None:
            raise NativeHostError(_timeout_code(accepted))
        if _is_probe_event(message):
            ignored += 1
            if ignored > 32:
                raise NativeHostError("probe_event_limit")
            continue
        receipt = wsp.validate_receipt(message)
        if not _receipt_matches(accepted, receipt):
            raise NativeHostError("receipt_identity_mismatch")
        return receipt


def _private_parent(path: Path, owner_uid: int) -> None:
    try:
        info = path.lstat()
    except OSError as exc:
        raise NativeHostError("socket_parent_unsafe") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise NativeHostError("socket_parent_unsafe")
    if info.st_uid != owner_uid or stat.S_IMODE(info.st_mode) & 0o077:
        raise NativeHostError("socket_parent_unsafe")


def open_private_server(path: str | Path, *, owner_uid: int) -> socket.socket:
    """Bind the fixed-style user-private AF_UNIX transport endpoint."""

    destination = Path(path)
    _private_parent(destination.parent, owner_uid)
    if os.path.lexists(destination):
        raise NativeHostError("socket_path_unsafe")
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    created = False
    try:
        server.bind(os.fspath(destination))
        created = True
        os.chmod(destination, 0o600)
        info = destination.lstat()
        if not stat.S_ISSOCK(info.st_mode) or info.st_uid != owner_uid or stat.S_IMODE(info.st_mode) & 0o077:
            raise NativeHostError("socket_path_unsafe")
        server.listen(1)
        return server
    except Exception:
        server.close()
        if created:
            try:
                info = destination.lstat()
            except OSError:
                pass
            else:
                if stat.S_ISSOCK(info.st_mode) and info.st_uid == owner_uid:
                    try:
                        destination.unlink()
                    except OSError:
                        pass
        raise


def close_private_server(server: socket.socket, path: str | Path, *, owner_uid: int) -> None:
    destination = Path(path)
    try:
        server.close()
    finally:
        try:
            info = destination.lstat()
        except OSError:
            return
        if (
            stat.S_ISSOCK(info.st_mode)
            and info.st_uid == owner_uid
            and not (stat.S_IMODE(info.st_mode) & 0o077)
        ):
            try:
                destination.unlink()
            except OSError:
                pass


def _read_chrome_with_timeout(stream, timeout_seconds: float) -> dict[str, Any] | None:
    try:
        descriptor = stream.fileno()
    except (AttributeError, OSError) as exc:
        raise NativeHostError("chrome_stream_invalid") from exc
    try:
        readable, _, _ = select.select([descriptor], [], [], timeout_seconds)
    except (OSError, ValueError) as exc:
        raise NativeHostError("chrome_stream_failed") from exc
    if not readable:
        return None
    try:
        return read_frame(stream)
    except NativeHostError as exc:
        if exc.code == "frame_header_missing":
            return None
        raise


def _write_chrome(stream, document: dict[str, Any]) -> None:
    write_frame(stream, document)


def _serve_client(client: socket.socket, chrome_in, chrome_out, *, timeout_seconds: float) -> None:
    with client:
        reader = client.makefile("rb", buffering=0)
        writer = client.makefile("wb", buffering=0)
        try:
            request = read_frame(reader)
            receipt = forward_request(
                request,
                write_chrome=lambda document: _write_chrome(chrome_out, document),
                read_chrome=lambda remaining: _read_chrome_with_timeout(chrome_in, remaining),
                timeout_seconds=timeout_seconds,
            )
            write_frame(writer, receipt)
        finally:
            reader.close()
            writer.close()


def run_native_host(
    chrome_in,
    chrome_out,
    *,
    caller_origin: str,
    socket_path: str | Path | None = None,
    owner_uid: int | None = None,
    action_timeout_seconds: float = 5.0,
) -> None:
    """Run the single-process private bridge until Chrome disconnects."""

    validate_caller_origin(caller_origin)
    uid = os.getuid() if owner_uid is None else owner_uid
    destination = Path(socket_path or SOCKET_PATH).expanduser()
    server = open_private_server(destination, owner_uid=uid)
    selector = select.poll() if hasattr(select, "poll") else None
    try:
        if selector is None:
            while True:
                client, _ = server.accept()
                _serve_client(client, chrome_in, chrome_out, timeout_seconds=action_timeout_seconds)
        else:
            selector.register(server.fileno(), select.POLLIN)
            selector.register(chrome_in.fileno(), select.POLLIN | select.POLLHUP | select.POLLERR)
            while True:
                events = selector.poll(1000)
                for descriptor, event in events:
                    if descriptor == chrome_in.fileno():
                        if event & (select.POLLHUP | select.POLLERR):
                            return
                        try:
                            unsolicited = read_frame(chrome_in)
                        except NativeHostError as exc:
                            if exc.code == "frame_header_missing":
                                return
                            raise
                        if not _is_probe_event(unsolicited):
                            raise NativeHostError("unexpected_chrome_message")
                    elif descriptor == server.fileno() and event & select.POLLIN:
                        client, _ = server.accept()
                        _serve_client(client, chrome_in, chrome_out, timeout_seconds=action_timeout_seconds)
    finally:
        close_private_server(server, destination, owner_uid=uid)


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv if argv is None else argv)
    if len(arguments) < 2:
        return 64
    try:
        run_native_host(
            sys.stdin.buffer,
            sys.stdout.buffer,
            caller_origin=arguments[1],
        )
    except (NativeHostError, wsp.WebSolProtocolError):
        return 65
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
