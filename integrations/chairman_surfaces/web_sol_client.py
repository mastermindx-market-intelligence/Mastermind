"""Explicit Python client for the Web-Sol S0/S1 exact-surface adapter.

This module is intentionally separate from :mod:`chatgpt`: the historical
managed-browser ``open_surface`` path remains fail-closed and gains no hidden
promotion/fallback behavior. OCR-6 may later call this seam only after it has
already selected one exact reviewed binding.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import secrets
import socket
import stat
import time
from typing import Any, Callable
from urllib.parse import urlsplit, urlunsplit

from control_plane import surface_bindings as sb
from . import web_sol_instance as wsi
from . import web_sol_native_host as native
from . import web_sol_protocol as wsp

SOCKET_TIMEOUT_SECONDS = 5.0
_CHATGPT_CANONICAL_HOST = "chatgpt.com"
_CHATGPT_HOST_ALIASES = frozenset({_CHATGPT_CANONICAL_HOST, "chat.openai.com"})


class WebSolExtensionError(RuntimeError):
    """Stable, locator-free failure from the explicit extension seam."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _accepted_binding(binding: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(binding, dict):
        raise WebSolExtensionError("invalid_binding")
    problems = sb.validate_bindings_document(
        {"schema": sb.SCHEMA, "bindings": [binding]}
    )
    if problems:
        raise WebSolExtensionError("invalid_binding")
    if (
        binding.get("provider") != "chatgpt"
        or binding.get("locator_kind") != "chatgpt_managed_env"
    ):
        raise WebSolExtensionError("invalid_binding")
    return binding


def _canonical_conversation_url(binding: dict[str, Any]) -> str:
    accepted = _accepted_binding(binding)
    parsed = urlsplit(accepted["locator"]["url"])
    path = parsed.path[:-1] if parsed.path.endswith("/") else parsed.path
    host = parsed.hostname.lower() if parsed.hostname else ""
    if host in _CHATGPT_HOST_ALIASES:
        host = _CHATGPT_CANONICAL_HOST
    return urlunsplit(
        (
            parsed.scheme.lower(),
            host,
            path,
            "",
            "",
        )
    )


def conversation_fingerprint(binding: dict[str, Any]) -> str:
    return hashlib.sha256(
        _canonical_conversation_url(binding).encode("utf-8")
    ).hexdigest()


def binding_fingerprint(binding: dict[str, Any]) -> str:
    accepted = _accepted_binding(binding)
    document = {
        "schema": "mastermind.web_sol_binding_fingerprint.v1",
        "binding_id": accepted["binding_id"].lower(),
        "work_ref": accepted["work_ref"],
        "role": accepted["role"],
        "seat_ref": accepted["seat_ref"],
        "provider": accepted["provider"],
        "locator_kind": accepted["locator_kind"],
        "env_manager": accepted["locator"]["env_manager"],
        "folder_id": accepted["locator"].get("folder_id"),
        "profile_id": accepted["locator"]["profile_id"],
        "conversation_fingerprint": conversation_fingerprint(accepted),
    }
    return hashlib.sha256(_canonical_bytes(document)).hexdigest()


def _request(
    binding: dict[str, Any],
    *,
    action: str,
    operation_key: str,
    issued_at: str,
    expires_at: str,
    nonce: str,
) -> dict[str, Any]:
    accepted = _accepted_binding(binding)
    request = {
        "schema": wsp.ACTION_SCHEMA,
        "binding_id": accepted["binding_id"].lower(),
        "conversation_fingerprint": conversation_fingerprint(accepted),
        "binding_fingerprint": binding_fingerprint(accepted),
        "action": action,
        "operation_key": operation_key,
        "issued_at": issued_at,
        "expires_at": expires_at,
        "nonce": nonce,
    }
    return wsp.validate_request(request)


def _private_socket(path: Path) -> None:
    try:
        parent = path.parent.lstat()
        target = path.lstat()
    except OSError as exc:
        raise WebSolExtensionError("extension_unavailable") from exc
    if (
        stat.S_ISLNK(parent.st_mode)
        or not stat.S_ISDIR(parent.st_mode)
        or parent.st_uid != target.st_uid
        or stat.S_IMODE(parent.st_mode) & 0o077
        or stat.S_ISLNK(target.st_mode)
        or not stat.S_ISSOCK(target.st_mode)
        or stat.S_IMODE(target.st_mode) & 0o077
    ):
        raise WebSolExtensionError("extension_unavailable")


def _challenge_nonce(factory: Callable[[], str]) -> str:
    if not callable(factory):
        raise WebSolExtensionError("transport_challenge_invalid")
    try:
        value = factory()
    except Exception as exc:
        raise WebSolExtensionError("transport_challenge_invalid") from exc
    if (
        not isinstance(value, str)
        or not 16 <= len(value) <= 128
        or any(character.isspace() for character in value)
    ):
        raise WebSolExtensionError("transport_challenge_invalid")
    return value


def _accepted_transport_ack(
    value: Any,
    *,
    expected_instance_id: str,
    expected_challenge: str,
    expected_boot_nonce: str | None,
) -> dict[str, Any]:
    try:
        accepted = wsp.validate_transport_hello_ack(value)
    except wsp.WebSolProtocolError as exc:
        raise WebSolExtensionError("transport_ack_invalid") from exc
    if accepted["role"] != "client":
        raise WebSolExtensionError("transport_role_mismatch")
    if accepted["adapter_instance_id"] != expected_instance_id:
        raise WebSolExtensionError("transport_instance_mismatch")
    versions = (
        accepted["client_package_version"],
        accepted["native_package_version"],
        accepted["extension_package_version"],
    )
    if versions != (wsp.WEB_SOL_PACKAGE_VERSION,) * 3:
        raise WebSolExtensionError("transport_version_mismatch")
    if accepted["capability_digest"] != wsp.transport_capability_digest():
        raise WebSolExtensionError("transport_capability_mismatch")
    if accepted["challenge_nonce"] != expected_challenge:
        raise WebSolExtensionError("transport_challenge_mismatch")
    if (
        expected_boot_nonce is not None
        and accepted["boot_nonce"] != expected_boot_nonce
    ):
        raise WebSolExtensionError("transport_boot_mismatch")
    return accepted


def _complete_transport_handshake(
    reader,
    writer,
    *,
    expected_instance_id: str,
    challenge_factory: Callable[[], str] | None = None,
    deadline: native.Deadline | None = None,
    monotonic: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    """Complete two bound challenges before any action document is sent."""

    try:
        instance_id = wsi.validate_instance_id(expected_instance_id)
    except wsi.WebSolInstanceError as exc:
        raise WebSolExtensionError("transport_instance_mismatch") from exc
    factory = challenge_factory or (lambda: secrets.token_urlsafe(24))
    first_challenge = _challenge_nonce(factory)
    first = wsp.build_transport_hello(
        role="client",
        adapter_instance_id=instance_id,
        client_package_version=wsp.WEB_SOL_PACKAGE_VERSION,
        native_package_version=wsp.WEB_SOL_PACKAGE_VERSION,
        extension_package_version=wsp.WEB_SOL_PACKAGE_VERSION,
        capability_digest=wsp.transport_capability_digest(),
        boot_nonce=None,
        challenge_nonce=first_challenge,
    )
    try:
        native.write_frame(
            writer,
            first,
            deadline=deadline,
            monotonic=monotonic,
        )
        first_ack = native.read_frame(
            reader,
            deadline=deadline,
            monotonic=monotonic,
        )
    except native.NativeHostError as exc:
        raise WebSolExtensionError("transport_handshake_failed") from exc
    accepted_first = _accepted_transport_ack(
        first_ack,
        expected_instance_id=instance_id,
        expected_challenge=first_challenge,
        expected_boot_nonce=None,
    )

    second_challenge = _challenge_nonce(factory)
    if second_challenge == first_challenge:
        raise WebSolExtensionError("transport_challenge_reused")
    second = wsp.build_transport_hello(
        role="client",
        adapter_instance_id=instance_id,
        client_package_version=wsp.WEB_SOL_PACKAGE_VERSION,
        native_package_version=wsp.WEB_SOL_PACKAGE_VERSION,
        extension_package_version=wsp.WEB_SOL_PACKAGE_VERSION,
        capability_digest=wsp.transport_capability_digest(),
        boot_nonce=accepted_first["boot_nonce"],
        challenge_nonce=second_challenge,
    )
    try:
        native.write_frame(
            writer,
            second,
            deadline=deadline,
            monotonic=monotonic,
        )
        second_ack = native.read_frame(
            reader,
            deadline=deadline,
            monotonic=monotonic,
        )
    except native.NativeHostError as exc:
        raise WebSolExtensionError("transport_handshake_failed") from exc
    return _accepted_transport_ack(
        second_ack,
        expected_instance_id=instance_id,
        expected_challenge=second_challenge,
        expected_boot_nonce=accepted_first["boot_nonce"],
    )


class _FrameWriteProgress:
    """Track bytes a writer accepted without changing framing or retry law."""

    def __init__(self, stream, *, expected_bytes: int):
        self._stream = stream
        self._expected_bytes = expected_bytes
        self.accepted_bytes = 0
        self._write_raised = False

    def __getattr__(self, name: str):
        return getattr(self._stream, name)

    def write(self, payload: bytes):
        try:
            written = self._stream.write(payload)
        except BaseException:
            self._write_raised = True
            raise
        if type(written) is int and 0 < written <= len(payload):
            self.accepted_bytes += written
        return written

    @property
    def frame_complete(self) -> bool:
        return self.accepted_bytes >= self._expected_bytes

    @property
    def effect_possible(self) -> bool:
        return self._write_raised or self.frame_complete


def _transport_failure_code(
    error: BaseException,
    *,
    sent: bool,
    action: str,
) -> str:
    if sent and action == "FOREGROUND":
        return "foreground_effect_unknown"
    if sent:
        return "inspect_effect_unknown"
    return "extension_unavailable"


def _exchange_web_sol_socket(
    request: dict[str, Any],
    *,
    path: Path,
    expected_instance_id: str,
    challenge_factory: Callable[[], str] | None = None,
    monotonic: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    _private_socket(path)
    deadline = native.Deadline(
        ends_at=monotonic() + SOCKET_TIMEOUT_SECONDS,
    )
    connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    connection.settimeout(deadline.remaining(monotonic))
    sent = False
    try:
        connection.connect(str(path))
        reader = connection.makefile("rb", buffering=0)
        writer = connection.makefile("wb", buffering=0)
        try:
            handshake_kwargs = {
                "expected_instance_id": expected_instance_id,
                "deadline": deadline,
                "monotonic": monotonic,
            }
            if challenge_factory is not None:
                handshake_kwargs["challenge_factory"] = challenge_factory
            _complete_transport_handshake(
                reader,
                writer,
                **handshake_kwargs,
            )
            action_writer = _FrameWriteProgress(
                writer,
                expected_bytes=len(native.encode_frame(request)),
            )
            try:
                native.write_frame(
                    action_writer,
                    request,
                    deadline=deadline,
                    monotonic=monotonic,
                )
            except native.NativeHostError:
                sent = action_writer.effect_possible
                raise
            sent = True
            response = native.read_frame(
                reader,
                deadline=deadline,
                monotonic=monotonic,
            )
        finally:
            reader.close()
            writer.close()
    except WebSolExtensionError:
        raise
    except (
        OSError,
        socket.timeout,
        native.NativeHostError,
        wsp.WebSolProtocolError,
    ) as exc:
        raise WebSolExtensionError(
            _transport_failure_code(
                exc,
                sent=sent,
                action=request["action"],
            )
        ) from exc
    finally:
        connection.close()
    return response


def _untrusted_receipt_code(action: str, default: str) -> str:
    return "foreground_effect_unknown" if action == "FOREGROUND" else default


def _invoke(
    binding: dict[str, Any],
    *,
    action: str,
    operation_key: str,
    issued_at: str,
    expires_at: str,
    nonce: str,
) -> dict[str, Any]:
    request = _request(
        binding,
        action=action,
        operation_key=operation_key,
        issued_at=issued_at,
        expires_at=expires_at,
        nonce=nonce,
    )
    try:
        instance_id = wsi.adapter_instance_id(binding)
        path = wsi.socket_path(instance_id)
    except wsi.WebSolInstanceError as exc:
        raise WebSolExtensionError(exc.code) from exc
    try:
        receipt = _exchange_web_sol_socket(
            request,
            path=path,
            expected_instance_id=instance_id,
        )
    except WebSolExtensionError:
        raise
    except native.NativeHostError as exc:
        raise WebSolExtensionError(exc.code) from exc
    try:
        accepted = wsp.validate_receipt(receipt)
    except wsp.WebSolProtocolError as exc:
        raise WebSolExtensionError(
            _untrusted_receipt_code(action, "invalid_receipt")
        ) from exc
    for field in (
        "binding_id",
        "conversation_fingerprint",
        "binding_fingerprint",
        "action",
        "operation_key",
        "nonce",
    ):
        if accepted[field] != request[field]:
            raise WebSolExtensionError(
                _untrusted_receipt_code(action, "receipt_identity_mismatch")
            )
    return accepted


def inspect_via_extension(
    binding: dict[str, Any],
    *,
    operation_key: str,
    issued_at: str,
    expires_at: str,
    nonce: str,
) -> dict[str, Any]:
    """Inspect one already-selected exact ChatGPT conversation through F2."""

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
    """Foreground one exact conversation once; uncertain effects never repeat."""

    return _invoke(
        binding,
        action="FOREGROUND",
        operation_key=operation_key,
        issued_at=issued_at,
        expires_at=expires_at,
        nonce=nonce,
    )
