"""Explicit Python client for the Web-Sol S0/S1 exact-surface adapter.

This module is intentionally separate from :mod:`chatgpt`: the historical
managed-browser ``open_surface`` path remains fail-closed and gains no hidden
promotion/fallback behavior.  OCR-6 may later call this seam only after it has
already resolved an exact Web-Sol surface binding.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import socket
import stat
from typing import Any
from urllib.parse import urlsplit

from control_plane import surface_bindings as sb

from . import web_sol_native_host as native
from . import web_sol_protocol as wsp

WEB_SOL_SOCKET_PATH = native.SOCKET_PATH
_SOCKET_TIMEOUT_SECONDS = 5.0
_BINDING_REVISION_V1 = 0
_MATCH_FIELDS = (
    "binding_id",
    "conversation_fingerprint",
    "binding_fingerprint",
    "binding_revision",
    "action",
    "operation_key",
    "nonce",
)


class WebSolExtensionError(RuntimeError):
    """Stable, locator-free explicit Web-Sol client failure."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _valid_binding(binding: Any) -> dict[str, Any]:
    if not isinstance(binding, dict):
        raise WebSolExtensionError("invalid_binding")
    problems = sb.validate_bindings_document({"schema": sb.SCHEMA, "bindings": [binding]})
    if problems:
        raise WebSolExtensionError("invalid_binding")
    if binding.get("provider") != "chatgpt" or binding.get("locator_kind") != "chatgpt_managed_env":
        raise WebSolExtensionError("invalid_binding")
    locator = binding.get("locator")
    if not isinstance(locator, dict) or not isinstance(locator.get("url"), str):
        raise WebSolExtensionError("invalid_binding")
    return binding


def _canonical_conversation_identity(binding: dict[str, Any]) -> str:
    accepted = _valid_binding(binding)
    parsed = urlsplit(accepted["locator"]["url"])
    host = (parsed.hostname or "").lower()
    path = parsed.path[:-1] if parsed.path.endswith("/") else parsed.path
    if not host or not path:
        raise WebSolExtensionError("invalid_binding")
    return f"https://{host}{path}"


def conversation_fingerprint(binding: dict[str, Any]) -> str:
    """Return the exact canonical conversation identity digest only."""

    identity = _canonical_conversation_identity(binding)
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def binding_fingerprint(binding: dict[str, Any]) -> str:
    """Digest stable exact-surface binding identity, excluding evidence clocks."""

    accepted = _valid_binding(binding)
    locator = dict(accepted["locator"])
    locator["url"] = _canonical_conversation_identity(accepted)
    stable = {
        "binding_id": accepted["binding_id"],
        "work_ref": accepted["work_ref"],
        "role": accepted["role"],
        "seat_ref": accepted.get("seat_ref"),
        "provider": accepted["provider"],
        "locator_kind": accepted["locator_kind"],
        "locator": locator,
    }
    payload = json.dumps(
        stable,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _private_socket_info(path: Path) -> None:
    try:
        parent = path.parent.lstat()
        info = path.lstat()
    except OSError as exc:
        raise WebSolExtensionError("extension_unavailable") from exc
    uid = os.getuid()
    if (
        stat.S_ISLNK(parent.st_mode)
        or not stat.S_ISDIR(parent.st_mode)
        or parent.st_uid != uid
        or stat.S_IMODE(parent.st_mode) & 0o077
    ):
        raise WebSolExtensionError("socket_parent_unsafe")
    if (
        stat.S_ISLNK(info.st_mode)
        or not stat.S_ISSOCK(info.st_mode)
        or info.st_uid != uid
        or stat.S_IMODE(info.st_mode) & 0o077
    ):
        raise WebSolExtensionError("socket_path_unsafe")


def _transport_failure_code(request: dict[str, Any], *, sent: bool) -> str:
    if not sent:
        return "extension_unavailable"
    if request.get("action") == "FOREGROUND":
        return "foreground_effect_unknown"
    return "inspect_timeout"


def _exchange_web_sol_socket(request: dict[str, Any]) -> dict[str, Any]:
    """Exchange exactly one closed action/receipt over the fixed private socket."""

    accepted = wsp.validate_request(request)
    path = Path(WEB_SOL_SOCKET_PATH).expanduser()
    _private_socket_info(path)

    peer = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    peer.settimeout(_SOCKET_TIMEOUT_SECONDS)
    sent = False
    try:
        peer.connect(os.fspath(path))
        reader = peer.makefile("rb", buffering=0)
        writer = peer.makefile("wb", buffering=0)
        try:
            native.write_frame(writer, accepted)
            sent = True
            receipt = native.read_frame(reader)
        finally:
            reader.close()
            writer.close()
    except socket.timeout as exc:
        raise WebSolExtensionError(_transport_failure_code(accepted, sent=sent)) from exc
    except (ConnectionError, OSError) as exc:
        raise WebSolExtensionError(_transport_failure_code(accepted, sent=sent)) from exc
    except native.NativeHostError as exc:
        raise WebSolExtensionError(exc.code) from exc
    finally:
        peer.close()
    return receipt


def _compose_request(
    binding: dict[str, Any],
    *,
    action: str,
    operation_key: str,
    issued_at: str,
    expires_at: str,
    nonce: str,
) -> dict[str, Any]:
    accepted = _valid_binding(binding)
    request = {
        "schema": wsp.ACTION_SCHEMA,
        "binding_id": accepted["binding_id"],
        "conversation_fingerprint": conversation_fingerprint(accepted),
        "binding_fingerprint": binding_fingerprint(accepted),
        "binding_revision": _BINDING_REVISION_V1,
        "action": action,
        "operation_key": operation_key,
        "issued_at": issued_at,
        "expires_at": expires_at,
        "nonce": nonce,
    }
    try:
        return wsp.validate_request(request)
    except wsp.WebSolProtocolError as exc:
        raise WebSolExtensionError("invalid_request") from exc


def _validate_matching_receipt(request: dict[str, Any], receipt: Any) -> dict[str, Any]:
    try:
        accepted = wsp.validate_receipt(receipt)
    except wsp.WebSolProtocolError as exc:
        raise WebSolExtensionError("invalid_receipt") from exc
    if any(accepted[field] != request[field] for field in _MATCH_FIELDS):
        raise WebSolExtensionError("receipt_identity_mismatch")
    return accepted


def _invoke(
    binding: dict[str, Any],
    *,
    action: str,
    operation_key: str,
    issued_at: str,
    expires_at: str,
    nonce: str,
) -> dict[str, Any]:
    request = _compose_request(
        binding,
        action=action,
        operation_key=operation_key,
        issued_at=issued_at,
        expires_at=expires_at,
        nonce=nonce,
    )
    try:
        receipt = _exchange_web_sol_socket(request)
    except WebSolExtensionError:
        raise
    except native.NativeHostError as exc:
        raise WebSolExtensionError(exc.code) from exc
    except wsp.WebSolProtocolError as exc:
        raise WebSolExtensionError("bridge_protocol_error") from exc
    return _validate_matching_receipt(request, receipt)


def inspect_via_extension(
    binding: dict[str, Any],
    *,
    operation_key: str,
    issued_at: str,
    expires_at: str,
    nonce: str,
) -> dict[str, Any]:
    """Perform one explicit S0 inspection through the exact-surface bridge."""

    return _invoke(
        binding,
        action="INSPECT",
        operation_key=operation_key,
        issued_at=issued_at,
        expires_at=expires_at,
        nonce=nonce,
    )


def foreground_via_extension(
    binding: dict[str, Any],
    *,
    operation_key: str,
    issued_at: str,
    expires_at: str,
    nonce: str,
) -> dict[str, Any]:
    """Perform one explicit S1 exact-tab/window foreground request."""

    return _invoke(
        binding,
        action="FOREGROUND",
        operation_key=operation_key,
        issued_at=issued_at,
        expires_at=expires_at,
        nonce=nonce,
    )
