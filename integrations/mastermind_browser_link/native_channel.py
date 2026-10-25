"""Closed Browser Link channel contracts.

This is a new composition of the current extension protocol. Chrome framing is
reused from the incumbent Web Sol transport; no Web Sol action or handshake is
accepted here. Enrollment selects a profile before any extension hello arrives.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any
from urllib.parse import urlsplit

from integrations.chairman_surfaces.web_sol_native_host import (
    Deadline, NativeHostError, encode_frame, read_frame, write_frame,
    open_private_server, close_private_server,
)

HELLO_SCHEMA = "mastermind.browser_link.hello.v2"
READY_SCHEMA = "mastermind.browser_link.ready.v2"
OBSERVE_SCHEMA = "mastermind.browser_link.observe.v2"
INVENTORY_SCHEMA = "mastermind.browser_link.inventory.v2"
COMMAND_SCHEMA = "mastermind.browser_link.command.v2"
RESULT_SCHEMA = "mastermind.browser_link.result.v2"
ENROLLMENT_SCHEMA = "mastermind.browser_link.enrollment.v2"
MAX_LIFETIME_MS = 30_000
MAX_TABS = 64
_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_EXTENSION = re.compile(r"^[a-p]{32}$")
_CODE = re.compile(r"^[A-Z][A-Z0-9_]{0,95}$")
READ_COMMANDS = frozenset({"snapshot", "screenshot"})
WRITE_COMMANDS = frozenset({"click", "type", "scroll", "navigate", "create_tab", "create_window"})


class LinkProtocolError(ValueError):
    """A closed, payload-free channel refusal."""


def _refuse() -> None:
    raise LinkProtocolError("LINK_PROTOCOL_INVALID")


def record(value: Any, required: set[str], optional: set[str] = frozenset()) -> dict:
    if type(value) is not dict or not required <= value.keys() or value.keys() - required - optional:
        _refuse()
    return value


def reference(value: Any) -> str:
    if type(value) is not str or _REF.fullmatch(value) is None:
        _refuse()
    return value


def integer(value: Any) -> int:
    if type(value) is not int or not 0 <= value <= 2**53 - 1:
        _refuse()
    return value


def snapshot(value: Any) -> dict:
    """Copy and bound before a caller can change an object across an await."""
    try:
        framed = encode_frame(value)
        return json.loads(framed[4:].decode("utf-8"))
    except (NativeHostError, ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise LinkProtocolError("LINK_PROTOCOL_INVALID") from exc


def http_url(value: Any, *, origin: bool = False) -> str:
    if type(value) is not str or not value or len(value) > 2048 or any(ord(c) <= 32 for c in value):
        _refuse()
    try:
        parts = urlsplit(value)
        if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username is not None or parts.password is not None:
            _refuse()
        if parts.port is not None and not 1 <= parts.port <= 65535:
            _refuse()
        if origin and (parts.path not in {"", "/"} or parts.query or parts.fragment):
            _refuse()
    except ValueError as exc:
        raise LinkProtocolError("LINK_PROTOCOL_INVALID") from exc
    return value


def native_host_name(instance_id: str) -> str:
    if type(instance_id) is not str or _HEX64.fullmatch(instance_id) is None:
        _refuse()
    return "com.mastermind.browser_link." + instance_id[:24]


@dataclass(frozen=True)
class LinkEnrollment:
    extension_id: str
    instance_id: str
    socket_path: Path

    def __post_init__(self) -> None:
        if type(self.extension_id) is not str or _EXTENSION.fullmatch(self.extension_id) is None:
            _refuse()
        native_host_name(self.instance_id)
        path = self.socket_path
        if not isinstance(path, Path) or not path.is_absolute() or ".." in path.parts or len(bytes(path)) > 103:
            _refuse()

    def document(self) -> dict:
        return {"schema": ENROLLMENT_SCHEMA, "extension_id": self.extension_id,
                "instance_id": self.instance_id, "socket_path": str(self.socket_path)}

    @classmethod
    def from_document(cls, value: Any) -> "LinkEnrollment":
        record(value, {"schema", "extension_id", "instance_id", "socket_path"})
        if value["schema"] != ENROLLMENT_SCHEMA or type(value["socket_path"]) is not str:
            _refuse()
        path = Path(value["socket_path"])
        if str(path) != value["socket_path"]:
            _refuse()
        return cls(value["extension_id"], value["instance_id"], path)


def validate_hello(value: Any, enrollment: LinkEnrollment) -> dict:
    data = snapshot(value)
    record(data, {"schema", "protocol_version", "extension_id", "instance_ref", "connection_generation"})
    if (data["schema"] != HELLO_SCHEMA or type(data["protocol_version"]) is not int
            or data["protocol_version"] != 2 or data["extension_id"] != enrollment.extension_id
            or data["instance_ref"] != enrollment.instance_id):
        _refuse()
    reference(data["connection_generation"])
    return data


def validate_inventory(value: Any, generation: str) -> dict:
    data = snapshot(value)
    record(data, {"schema", "connection_generation", "shared_tabs"}, {"request_id"})
    if data["schema"] != INVENTORY_SCHEMA or data["connection_generation"] != generation:
        _refuse()
    if "request_id" in data:
        reference(data["request_id"])
    rows = data["shared_tabs"]
    if type(rows) is not list or len(rows) > MAX_TABS:
        _refuse()
    seen = set()
    for row in rows:
        record(row, {"tab_id", "origin", "consent_id", "document_revision", "state", "allow_create"})
        if type(row["allow_create"]) is not bool:
            _refuse()
        integer(row["tab_id"])
        integer(row["document_revision"])
        reference(row["consent_id"])
        http_url(row["origin"], origin=True)
        if type(row["state"]) is not str or row["state"] not in {"shared", "busy", "navigating", "effect_unresolved"} or row["tab_id"] in seen:
            _refuse()
        seen.add(row["tab_id"])
    return data


def validate_target(value: Any) -> dict:
    data = snapshot(value)
    record(data, {"connection_generation", "tab_id", "consent_id", "document_revision"})
    reference(data["connection_generation"])
    reference(data["consent_id"])
    integer(data["tab_id"])
    integer(data["document_revision"])
    return data


def validate_command(value: Any, *, now_ms: int | None = None) -> dict:
    data = snapshot(value)
    record(data, {"schema", "request_id", "connection_generation", "tab_id", "consent_id",
                  "document_revision", "expires_at_ms", "command", "args"}, {"writer"})
    if data["schema"] != COMMAND_SCHEMA or type(data["command"]) is not str or data["command"] not in READ_COMMANDS | WRITE_COMMANDS:
        _refuse()
    for key in ("request_id", "connection_generation", "consent_id"):
        reference(data[key])
    for key in ("tab_id", "document_revision", "expires_at_ms"):
        integer(data[key])
    if now_ms is not None:
        integer(now_ms)
        if not now_ms < data["expires_at_ms"] <= now_ms + MAX_LIFETIME_MS:
            _refuse()
    command, args = data["command"], data["args"]
    if command in READ_COMMANDS:
        if "writer" in data:
            _refuse()
        record(args, set())
    else:
        writer = data.get("writer")
        record(writer, {"holder_ref", "fence"})
        reference(writer["holder_ref"])
        integer(writer["fence"])
        if command == "click":
            record(args, {"element_ref"})
            reference(args["element_ref"])
        elif command == "type":
            record(args, {"element_ref", "text"})
            reference(args["element_ref"])
            if type(args["text"]) is not str or "\x00" in args["text"] or len(args["text"].encode("utf-8")) > 16384:
                _refuse()
        elif command == "scroll":
            record(args, {"delta_x", "delta_y"})
            if any(type(args[k]) is not int or abs(args[k]) > 2000 for k in args):
                _refuse()
        elif command in {"navigate", "create_tab", "create_window"}:
            record(args, {"url"})
            http_url(args["url"])
    return data


def validate_owner_message(value: Any, generation: str, *, now_ms: int | None = None) -> dict:
    data = snapshot(value)
    if data.get("schema") == READY_SCHEMA:
        record(data, {"schema", "connection_generation"})
    elif data.get("schema") == OBSERVE_SCHEMA:
        record(data, {"schema", "request_id", "connection_generation"})
        reference(data["request_id"])
    else:
        data = validate_command(data, now_ms=now_ms)
    if data["connection_generation"] != generation:
        _refuse()
    return data


def validate_result(value: Any, generation: str) -> dict:
    data = snapshot(value)
    record(data, {"schema", "request_id", "connection_generation", "status", "effect"},
           {"output", "document_revision", "code", "replayed", "original_effect"})
    if data["schema"] != RESULT_SCHEMA or data["connection_generation"] != generation:
        _refuse()
    reference(data["request_id"])
    if type(data["status"]) is not str or type(data["effect"]) is not str or data["status"] not in {"completed", "refused", "pending"} or data["effect"] not in {"NOT_APPLIED", "APPLIED", "EFFECT_UNKNOWN"}:
        _refuse()
    if data["effect"] == "APPLIED" and data["status"] != "completed":
        _refuse()
    if "original_effect" in data and (type(data["original_effect"]) is not str or data["original_effect"] not in {"NOT_APPLIED", "APPLIED", "EFFECT_UNKNOWN"}):
        _refuse()
    if "replayed" in data and type(data["replayed"]) is not bool:
        _refuse()
    if "document_revision" in data:
        integer(data["document_revision"])
    if "output" in data and type(data["output"]) is not dict:
        _refuse()
    if "code" in data and (type(data["code"]) is not str or _CODE.fullmatch(data["code"]) is None):
        _refuse()
    return data


def validate_extension_message(value: Any, generation: str) -> dict:
    if type(value) is dict and value.get("schema") == INVENTORY_SCHEMA:
        return validate_inventory(value, generation)
    return validate_result(value, generation)
