"""Bounded browser messages on the incumbent Web-Sol native connection.

Chrome owns site permission; Hermes owns caller identity; the native host owns
serialization and the connection generation. This module is pure validation.
"""
from __future__ import annotations

import copy
import json
import re
from datetime import datetime, timezone
from urllib.parse import urlsplit

from .web_sol_protocol import WebSolProtocolError

REQUEST_SCHEMA = "mastermind.web_sol_browser_request.v1"
RECEIPT_SCHEMA = "mastermind.web_sol_browser_receipt.v1"
TOTAL_SECONDS = 20
MAX_BYTES = 61440
IDENTITY_FIELDS = ("adapter_instance_id", "session_id", "operation_key", "nonce",
                   "transport_boot_nonce", "action")
READ_ACTIONS = frozenset({"status", "tabs", "snapshot", "screenshot", "diagnostics"})
PAGE_ACTIONS = frozenset({"click", "fill", "select", "press", "scroll"})
TAB_ACTIONS = PAGE_ACTIONS | {"snapshot", "screenshot", "diagnostics", "navigate",
                            "reload", "back", "forward", "close", "focus"}
ACTIONS = READ_ACTIONS | TAB_ACTIONS | {"open"}
KEYS = frozenset({"Enter", "Tab", "Escape", "ArrowUp", "ArrowDown", "ArrowLeft",
                  "ArrowRight", "Home", "End", "Backspace", "Delete", "Space"})
REQUEST_KEYS = frozenset({"schema", *IDENTITY_FIELDS, "tab_id", "url_fingerprint",
                          "snapshot_id", "ref", "params", "issued_at", "expires_at"})
RECEIPT_KEYS = frozenset({"schema", *IDENTITY_FIELDS, "status", "effect", "observed_at", "data"})


def _require(value):
    if not value:
        raise WebSolProtocolError("invalid_browser_value")


def _text(value, low=1, high=128):
    return (type(value) is str and low <= len(value) <= high
            and not any(ord(c) < 32 or ord(c) == 127 for c in value))


def _hex(value):
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _timestamp(value):
    _require(type(value) is str and re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z", value) is not None)
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise WebSolProtocolError("invalid_browser_value") from None


def _plain(value, depth=0):
    _require(depth <= 12)
    if type(value) is dict:
        _require(len(value) <= 256 and all(type(k) is str for k in value))
        for child in value.values():
            _plain(child, depth + 1)
    elif type(value) is list:
        _require(len(value) <= 256)
        for child in value:
            _plain(child, depth + 1)
    else:
        _require(type(value) in (str, int, float, bool, type(None)))
        if type(value) is int:
            _require(abs(value) <= 9007199254740991)


def bounded(value):
    _plain(value)
    try:
        _require(len(json.dumps(value, ensure_ascii=False, allow_nan=False,
                                separators=(",", ":")).encode("utf-8")) <= MAX_BYTES)
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise WebSolProtocolError("invalid_browser_value") from None


def valid_url(value):
    if not _text(value, 1, 4096) or any(c.isspace() for c in value):
        return False
    try:
        u = urlsplit(value)
        return (u.scheme in {"http", "https"} and bool(u.hostname)
                and u.username is None and u.password is None and u.port != 0)
    except ValueError:
        return False


def _identity(value):
    _require(_hex(value["adapter_instance_id"]) and _hex(value["session_id"]))
    _require(_text(value["operation_key"], 1, 128))
    _require(_text(value["nonce"], 16, 128))
    _require(type(value["action"]) is str and value["action"] in ACTIONS)
    _require(value["transport_boot_nonce"] is None and value["action"] == "status"
             or _text(value["transport_boot_nonce"], 16, 128))


def validate_request(value):
    bounded(value)
    _require(type(value) is dict and set(value) == REQUEST_KEYS)
    _require(value["schema"] == REQUEST_SCHEMA)
    _identity(value)
    action, params = value["action"], value["params"]
    _require(type(params) is dict)
    if action in TAB_ACTIONS:
        _require(type(value["tab_id"]) is int and 0 <= value["tab_id"] <= 2147483647)
        _require(_hex(value["url_fingerprint"]))
    else:
        _require(value["tab_id"] is None and value["url_fingerprint"] is None)
    if action in TAB_ACTIONS - {"snapshot"}:
        _require(_text(value["snapshot_id"], 16, 128))
    else:
        _require(value["snapshot_id"] is None)
    if action in PAGE_ACTIONS:
        _require(_text(value["ref"], 1, 32))
    else:
        _require(value["ref"] is None)
    if action in {"open", "navigate"}:
        _require(set(params) == {"url"} and valid_url(params["url"]))
    elif action == "fill":
        _require(set(params) == {"text"} and type(params["text"]) is str
                 and len(params["text"]) <= 8000 and "\x00" not in params["text"])
    elif action == "select":
        _require(set(params) == {"value"} and _text(params["value"], 0, 512))
    elif action == "press":
        _require(set(params) == {"key"} and type(params["key"]) is str and params["key"] in KEYS)
    elif action == "scroll":
        _require(set(params) == {"x", "y"} and all(
            type(params[k]) is int and abs(params[k]) <= 3000 for k in params))
    else:
        _require(not params)
    _timestamp(value["issued_at"])
    _timestamp(value["expires_at"])
    return copy.deepcopy(value)


def validate_window(value, *, now=None):
    accepted = validate_request(value)
    current = now or datetime.now(timezone.utc)
    start, end = _timestamp(accepted["issued_at"]), _timestamp(accepted["expires_at"])
    _require(0 < (end - start).total_seconds() <= 60)
    _require((start - current).total_seconds() <= 5 and end > current)
    return accepted


def receipt(request, *, status, effect="NOT_APPLIED", data=None):
    value = {"schema": RECEIPT_SCHEMA, **{k: request[k] for k in IDENTITY_FIELDS},
             "status": status, "effect": effect,
             "observed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
             "data": data}
    return validate_receipt(value)


def validate_receipt(value):
    bounded(value)
    _require(type(value) is dict and set(value) == RECEIPT_KEYS)
    _require(value["schema"] == RECEIPT_SCHEMA)
    _identity(value)
    _require(type(value["status"]) is str and re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", value["status"]) is not None)
    _require(type(value["effect"]) is str and value["effect"] in {"NOT_APPLIED", "APPLIED", "EFFECT_UNKNOWN"})
    _require(type(value["data"]) in (dict, type(None)))
    _timestamp(value["observed_at"])
    return copy.deepcopy(value)
