"""Pure profile-derived routing for the Web-Sol native adapter.

The existing ``mastermind.surface_bindings.v1`` document remains the sole
navigation coordinate.  This module derives an opaque adapter instance and a
short private socket/host leaf from that already-validated managed-browser
coordinate.  It owns no registry, persistence, profile discovery, browser
access, lifecycle, authority, retry or fallback behavior.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from control_plane import surface_bindings as sb


ADAPTER_INSTANCE_SCHEMA = "mastermind.web_sol_adapter_instance.v1"
DEFAULT_SOCKET_ROOT = "~/Library/Application Support/Mastermind/wsx"
SOCKET_LEAF_HEX = 32
NATIVE_HOST_LEAF_HEX = 24
# Darwin's sockaddr_un.sun_path is 104 bytes including its terminator.  Keep
# the encoded path strictly below this constant so the terminator fits.
DARWIN_SUN_PATH_BYTES = 104


class WebSolInstanceError(ValueError):
    """Stable, coordinate-free Web-Sol instance derivation failure."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _valid_binding(binding: Any) -> dict[str, Any]:
    if not isinstance(binding, dict):
        raise WebSolInstanceError("invalid_binding")
    problems = sb.validate_bindings_document(
        {"schema": sb.SCHEMA, "bindings": [binding]}
    )
    if problems:
        raise WebSolInstanceError("invalid_binding")
    if (
        binding.get("provider") != "chatgpt"
        or binding.get("locator_kind") != "chatgpt_managed_env"
    ):
        raise WebSolInstanceError("invalid_binding")
    locator = binding.get("locator")
    if not isinstance(locator, dict):
        raise WebSolInstanceError("invalid_binding")
    return binding


def _instance_document(binding: dict[str, Any]) -> dict[str, Any]:
    accepted = _valid_binding(binding)
    locator = accepted["locator"]
    manager = locator["env_manager"]
    profile_id = locator["profile_id"].lower()
    folder_id = locator.get("folder_id")
    if isinstance(folder_id, str):
        folder_id = folder_id.lower()
    return {
        "schema": ADAPTER_INSTANCE_SCHEMA,
        "env_manager": manager,
        "folder_id": folder_id if manager == "multilogin" else None,
        "profile_id": profile_id,
    }


def adapter_instance_id(binding: dict[str, Any]) -> str:
    """Return the opaque instance digest for one managed browser environment.

    Conversation URL, work reference, seat label and binding row identity are
    deliberately excluded: one installed profile-local adapter continues to
    represent the same browser environment as conversations rotate.
    """

    payload = json.dumps(
        _instance_document(binding),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def validate_instance_id(value: Any) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise WebSolInstanceError("invalid_instance_id")
    return value


def socket_leaf(instance_id: str) -> str:
    accepted = validate_instance_id(instance_id)
    return f"wsx-{accepted[:SOCKET_LEAF_HEX]}.sock"


def native_host_name(instance_id: str) -> str:
    accepted = validate_instance_id(instance_id)
    return f"com.mastermind.web_sol_surface.{accepted[:NATIVE_HOST_LEAF_HEX]}"


def socket_path(
    instance_id: str,
    *,
    root: str | os.PathLike[str] | None = None,
) -> Path:
    """Derive the one bounded AF_UNIX path for an accepted instance digest."""

    accepted = validate_instance_id(instance_id)
    base = Path(root if root is not None else DEFAULT_SOCKET_ROOT).expanduser()
    if not base.is_absolute():
        raise WebSolInstanceError("socket_root_invalid")
    destination = base / socket_leaf(accepted)
    try:
        encoded = os.fsencode(destination)
    except (TypeError, UnicodeError, ValueError) as exc:
        raise WebSolInstanceError("socket_path_invalid") from exc
    if len(encoded) >= DARWIN_SUN_PATH_BYTES:
        raise WebSolInstanceError("socket_path_too_long")
    return destination
