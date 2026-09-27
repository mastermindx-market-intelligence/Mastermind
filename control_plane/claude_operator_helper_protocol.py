"""Strict JSON-lines protocol for the transient native Claude helper.

The helper is deliberately boring: every request has a closed field set, every
response is small JSON, and provider/account values are reduced before crossing
the process boundary.  The Executive adapter owns process lifecycle, retries and
authority; this module owns only encoding validation.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Mapping


INTERFACE_VERSION = "mastermind.claude_native_helper/v1"
MAX_WIRE_BYTES = 1024 * 1024
MAX_TEXT_CHARS = 16_000
MAX_EVENTS = 256
REQUEST_ID_RE = re.compile(r"req-[A-Za-z0-9_-]{1,64}")
OPERATIONS = frozenset(
    {
        "initialize",
        "begin_turn",
        "read_events",
        "interrupt",
        "collect",
        "reconcile",
        "disconnect",
    }
)
_ALLOWED_FIELDS = {
    "initialize": frozenset({"interface_version", "generation_id", "config"}),
    "begin_turn": frozenset({"interface_version", "generation_id", "turn_id", "payload"}),
    "read_events": frozenset({"interface_version", "generation_id", "max_events", "after_sequence"}),
    "interrupt": frozenset({"interface_version", "generation_id", "turn_id"}),
    "collect": frozenset({"interface_version", "generation_id", "turn_id"}),
    "reconcile": frozenset({"interface_version", "generation_id"}),
    "disconnect": frozenset({"interface_version", "generation_id"}),
}

# Strict allowlist for initialize.config — env/extra_args are refused.
_ALLOWED_CONFIG_KEYS = frozenset(
    {
        "cli_path",
        "cwd",
        "model",
        "session_id",
        "tools",
        "mcp_servers",
        "permission_mode",
        "max_turns",
        "resume",
        "setting_sources",
        "strict_mcp_config",
        "skills",
        "allowed_tools",
        "disallowed_tools",
        "sandbox",
        "settings",
    }
)


class HelperProtocolError(ValueError):
    """Malformed, duplicate, oversize, or semantically invalid helper wire."""


@dataclass(frozen=True)
class HelperRequest:
    operation: str
    request_id: str
    fields: Mapping[str, Any]


def _mapping(value: Any, where: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise HelperProtocolError(f"{where} must be an object")
    return value


def _reject_duplicate_keys(pairs):
    seen: set = set()
    result: dict = {}
    for k, v in pairs:
        if not isinstance(k, str):
            raise HelperProtocolError("JSON key must be a string")
        if k in seen:
            raise HelperProtocolError("wire message has duplicate JSON key")
        seen.add(k)
        result[k] = v
    return result


def _reject_nonfinite(c: str) -> None:
    raise HelperProtocolError("wire message has nonfinite JSON constant")


def encode_json_line(value: Mapping[str, Any]) -> bytes:
    encoded = json.dumps(
        value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8") + b"\n"
    if len(encoded) > MAX_WIRE_BYTES:
        raise HelperProtocolError("wire message exceeds the size bound")
    return encoded


def decode_json_line(line: bytes | str) -> Mapping[str, Any]:
    if isinstance(line, bytes):
        if len(line) > MAX_WIRE_BYTES:
            raise HelperProtocolError("wire message exceeds the size bound")
        try:
            line = line.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise HelperProtocolError("wire message must be UTF-8") from exc
    # Strip trailing newline(s); reject any internal newline.
    line = line.rstrip("\r\n")
    if "\n" in line:
        raise HelperProtocolError("wire message exceeds the size bound")
    encoded_len = len(line.encode("utf-8"))
    if encoded_len > MAX_WIRE_BYTES:
        raise HelperProtocolError("wire message exceeds the size bound")
    try:
        value = json.loads(
            line,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_nonfinite,
        )
    except HelperProtocolError:
        raise
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise HelperProtocolError("wire message is malformed") from exc
    return _mapping(value, "wire message")


def parse_request(message: Mapping[str, Any], *, seen_request_ids: set[str]) -> HelperRequest:
    if len(seen_request_ids) >= 4096:
        raise HelperProtocolError("generation request budget exhausted")
    if set(message) != {"operation", "request_id", "fields"}:
        raise HelperProtocolError("request envelope has unknown fields")
    operation = message["operation"]
    request_id = message["request_id"]
    if not isinstance(operation, str) or operation not in OPERATIONS:
        raise HelperProtocolError("operation is refused")
    if not isinstance(request_id, str) or REQUEST_ID_RE.fullmatch(request_id) is None:
        raise HelperProtocolError("request_id is malformed")
    if request_id in seen_request_ids:
        raise HelperProtocolError("request_id is duplicate")
    fields = _mapping(message["fields"], "request fields")
    allowed = _ALLOWED_FIELDS[operation]
    if set(fields) != allowed:
        raise HelperProtocolError("request fields are incomplete or not allowlisted")
    if fields.get("interface_version") != INTERFACE_VERSION:
        raise HelperProtocolError("interface version mismatch")
    generation_id = fields.get("generation_id")
    if not isinstance(generation_id, str) or not generation_id or len(generation_id) > 128:
        raise HelperProtocolError("generation_id is malformed")
    for name in ("turn_id", "payload"):
        if name in fields and not isinstance(fields[name], str):
            raise HelperProtocolError(f"{name} must be a string")
    if "payload" in fields:
        if len(fields["payload"].encode("utf-8")) > MAX_TEXT_CHARS:
            raise HelperProtocolError("payload exceeds bound")
    if "max_events" in fields:
        value = fields["max_events"]
        if type(value) is not int or not 1 <= value <= MAX_EVENTS:
            raise HelperProtocolError("max_events is out of range")
    if operation == "initialize":
        config = fields.get("config")
        _mapping(config, "initialize config")
        unknown = set(config) - _ALLOWED_CONFIG_KEYS
        if unknown:
            raise HelperProtocolError("initialize config keys are not allowlisted")
        for key in ("cli_path", "cwd", "model", "session_id"):
            if not isinstance(config.get(key), str) or not 1 <= len(config[key]) <= 4096:
                raise HelperProtocolError("required native configuration is malformed")
        if config.get("setting_sources", []) != [] or config.get("strict_mcp_config", True) is not True:
            raise HelperProtocolError("ambient configuration discovery is refused")
        for key in ("tools", "allowed_tools", "disallowed_tools", "skills"):
            if key in config:
                value = config[key]
                if not isinstance(value, list) or len(value) > 256 or any(
                    not isinstance(x, str) or not 1 <= len(x) <= 4096 for x in value
                ):
                    raise HelperProtocolError("capability list is malformed")
        if type(config.get("max_turns", 1)) is not int or not 1 <= config.get("max_turns", 1) <= 100:
            raise HelperProtocolError("max_turns is out of range")
        if config.get("permission_mode", "dontAsk") not in {"dontAsk", "default", "acceptEdits", "plan"}:
            raise HelperProtocolError("permission mode is refused")
        mcp = config.get("mcp_servers", {})
        if not isinstance(mcp, dict) or len(mcp) > 32:
            raise HelperProtocolError("MCP configuration is malformed")
        for name, server in mcp.items():
            if not isinstance(name, str) or not 1 <= len(name) <= 200 or not isinstance(server, dict):
                raise HelperProtocolError("MCP server is malformed")
            if set(server) - {"type", "command", "args", "url"}:
                raise HelperProtocolError("MCP credential or unknown configuration refused")
        if "settings" in config:
            if security_settings(config["settings"]) != config["settings"]:
                raise HelperProtocolError("only explicit security settings are admitted")
        for key, value in (config or {}).items():
            if not isinstance(key, str):
                raise HelperProtocolError("config key must be a string")
            if value is None:
                continue
            if not isinstance(value, (str, int, bool, list, dict)):
                raise HelperProtocolError("config value is not a bounded scalar")
    seen_request_ids.add(request_id)
    return HelperRequest(operation=operation, request_id=request_id, fields=fields)


def validate_response(message: Mapping[str, Any], *, request_id: str) -> Mapping[str, Any]:
    if set(message) != {"ok", "request_id", "value"}:
        raise HelperProtocolError("response envelope has unknown fields")
    if message["request_id"] != request_id:
        raise HelperProtocolError("response request_id mismatch")
    if type(message["ok"]) is not bool:
        raise HelperProtocolError("response status must be boolean")
    if message["ok"] is not True:
        if isinstance(message["value"], str) and len(message["value"]) <= 500:
            return message
        raise HelperProtocolError("refusal value must be bounded text")
    return message


def bounded_text(value: Any, *, limit: int = MAX_TEXT_CHARS) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    return value[:limit]


def security_settings(effective: Any) -> dict[str, Any]:
    """Project only settings that determine the v1 native tool policy.

    Other settings (including env, account identity, hooks and telemetry) never
    cross this boundary. Unknown keys *inside* either security block refuse.
    """
    source = _mapping(effective, "effective settings")
    result = {}
    shapes = {
        "permissions": {"allow", "deny", "ask", "defaultMode", "additionalDirectories", "disableBypassPermissionsMode"},
        "sandbox": {"enabled", "failIfUnavailable", "autoAllowBashIfSandboxed", "excludedCommands", "allowUnsandboxedCommands", "network", "filesystem", "enableWeakerNestedSandbox"},
    }
    for block, allowed in shapes.items():
        if block not in source:
            continue
        value = _mapping(source[block], "security settings")
        if set(value) - allowed:
            raise HelperProtocolError("unknown native security setting")
        if block == "sandbox":
            for nested, keys in {
                "network": {"allowedDomains", "deniedDomains", "allowLocalBinding", "allowUnixSockets", "allowAllUnixSockets", "allowManagedDomainsOnly", "httpProxyPort", "socksProxyPort"},
                "filesystem": {"allowWrite", "denyWrite", "denyRead", "allowRead"},
            }.items():
                if nested in value and set(_mapping(value[nested], nested)) - keys:
                    raise HelperProtocolError("unknown native sandbox setting")
        result[block] = json.loads(json.dumps(value, allow_nan=False))
    if len(json.dumps(result)) > 64_000:
        raise HelperProtocolError("native security settings exceed bound")
    return result



__all__ = [
    "INTERFACE_VERSION",
    "HelperProtocolError",
    "HelperRequest",
    "MAX_EVENTS",
    "MAX_TEXT_CHARS",
    "MAX_WIRE_BYTES",
    "OPERATIONS",
    "bounded_text",
    "decode_json_line",
    "encode_json_line",
    "parse_request",
    "validate_response",
]
