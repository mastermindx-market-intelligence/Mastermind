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
MAX_BYTES = 819200
IDENTITY_FIELDS = ("adapter_instance_id", "session_id", "operation_key", "nonce",
                   "transport_boot_nonce", "action")
ADVANCED_READ = frozenset({"cdp_status", "frames", "accessibility", "dom", "locate", "wait",
    "events", "network", "response_body", "result", "downloads", "capture", "pdf"})
ADVANCED_ACTIONS = ADVANCED_READ | {"cdp_attach", "cdp_detach", "cdp", "evaluate", "interact",
    "upload", "download", "dialog", "emulate", "route"}
NO_SNAPSHOT = ADVANCED_READ | {"snapshot", "diagnostics", "cdp_detach", "dialog"}
READ_ACTIONS = frozenset({"status", "tabs", "snapshot", "screenshot", "diagnostics", "read"}) | ADVANCED_READ
PAGE_ACTIONS = frozenset({"click", "fill", "select", "press", "scroll", "read"})
TAB_ACTIONS = PAGE_ACTIONS | {"snapshot", "screenshot", "diagnostics", "navigate",
                            "reload", "back", "forward", "close", "focus"} | ADVANCED_ACTIONS
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
    _require(depth <= 24)
    if type(value) is dict:
        _require(len(value) <= 256 and all(type(k) is str for k in value))
        for child in value.values():
            _plain(child, depth + 1)
    elif type(value) is list:
        _require(len(value) <= 2048)
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


ADVANCED_FIELDS = {
    "cdp_attach": {"network", "capture_stream_data"}, "cdp_detach": set(), "cdp_status": set(),
    "cdp": {"method", "params", "frame_id"}, "evaluate": {"expression", "frame_id", "await_promise", "world"},
    "frames": set(), "accessibility": {"frame_id", "limit"}, "dom": {"frame_id", "depth", "pierce", "selector"},
    "locate": {"frame_id", "locator", "limit", "include_hidden"},
    "interact": {"ref", "kind", "text", "key", "value", "checked", "x", "y", "target_ref"},
    "wait": {"frame_id", "locator", "state", "timeout_ms"}, "events": {"after", "limit", "method"},
    "network": {"limit", "request_id"}, "response_body": {"request_id", "offset", "limit"},
    "result": {"result_id", "offset", "limit"}, "upload": {"ref", "files"},
    "download": {"url", "filename"}, "downloads": {"download_id"}, "dialog": {"accept", "prompt", "dialog_ref"},
    "emulate": {"viewport", "user_agent", "media", "timezone", "reset"}, "route": {"rules"},
    "capture": {"full_page", "format", "quality", "max_width", "max_height"},
    "pdf": {"landscape", "print_background", "scale"},
}


def validate_advanced(action, params):
    _require(type(params) is dict and not set(params) - ADVANCED_FIELDS[action])
    _require(len(json.dumps(params, ensure_ascii=False, allow_nan=False)) <= 30000)
    if "frame_id" in params:
        _require(_text(params["frame_id"], 1, 256))
    if "limit" in params:
        maximum = 32000 if action in {"response_body", "result"} else 200
        _require(type(params["limit"]) is int and 1 <= params["limit"] <= maximum)
    for field in ("offset", "after"):
        if field in params:
            _require(type(params[field]) is int and 0 <= params[field] <= (2000000 if field == "offset" else 9007199254740991))
    if action == "cdp":
        _require(_text(params.get("method"), 3, 160) and re.fullmatch(r"[A-Z][A-Za-z]+\.[a-zA-Z][a-zA-Z0-9]+", params["method"]))
        _require(type(params.get("params", {})) is dict)
    if action == "evaluate":
        _require(type(params.get("expression")) is str and 1 <= len(params["expression"]) <= 20000 and "\x00" not in params["expression"])
        _require(params.get("world", "isolated") in {"isolated", "page"})
    if action in {"locate", "wait"}:
        locator = params.get("locator")
        _require(type(locator) is dict and bool(locator) and not set(locator) - {"css", "role", "name", "text", "label", "testid", "exact", "index"})
        for field, value in locator.items():
            _require(type(value) is bool if field == "exact" else
                     type(value) is int and 0 <= value <= 10000 if field == "index" else _text(value, 1, 1000))
        _require(params.get("state", "visible") in {"visible", "hidden", "attached", "detached"})
        _require(type(params.get("timeout_ms", 5000)) is int and 0 <= params.get("timeout_ms", 5000) <= 8000)
    if action in {"interact", "upload"}:
        _require(type(params.get("ref")) is str and re.fullmatch(r"n[0-9a-f]{24}", params["ref"]))
    if action == "interact":
        _require(params.get("kind") in {"click", "double_click", "hover", "fill", "type", "press", "select", "check", "scroll", "drag"})
    if "text" in params:
        _require(type(params["text"]) is str and len(params["text"]) <= 16000 and "\x00" not in params["text"])
    if action == "upload":
        files = params.get("files")
        _require(type(files) is list and 1 <= len(files) <= 16 and all(
            _text(f, 1, 4096) and f.startswith("/") and "\n" not in f and "\r" not in f for f in files))
    if action == "download":
        _require(valid_url(params.get("url")))
        if "filename" in params:
            _require(_text(params["filename"], 1, 120) and re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9 ._-]{0,119}", params["filename"]) and ".." not in params["filename"])
    if action == "route":
        rules = params.get("rules")
        _require(type(rules) is list and len(rules) <= 16)
        for rule in rules:
            _require(type(rule) is dict and set(rule) == {"url_pattern", "action"} and rule["action"] in {"continue", "block"}
                     and _text(rule["url_pattern"], 1, 1000) and rule["url_pattern"].startswith(("http://", "https://")))
    for field in ("network", "capture_stream_data", "await_promise", "pierce", "include_hidden", "accept", "checked", "full_page", "landscape", "print_background", "reset"):
        if field in params:
            _require(type(params[field]) is bool)
    for field, lower, upper in (("quality", 10, 100), ("depth", 0, 8), ("max_width", 64, 4096), ("max_height", 64, 4096)):
        if field in params:
            _require(type(params[field]) is int and lower <= params[field] <= upper)
    if "format" in params:
        _require(params["format"] in {"png", "jpeg"})
    if action in {"response_body", "result"}:
        _require(_text(params.get("request_id" if action == "response_body" else "result_id"), 1, 256))


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
    if action in TAB_ACTIONS - NO_SNAPSHOT:
        _require(_text(value["snapshot_id"], 16, 128))
    elif action == "diagnostics":
        # diagnostics is the snapshot-free recovery read: it accepts the last
        # observation's id when one exists, and None when none does.
        _require(value["snapshot_id"] is None or _text(value["snapshot_id"], 16, 128))
    else:
        _require(value["snapshot_id"] is None)
    if action in PAGE_ACTIONS:
        _require(_text(value["ref"], 1, 32))
    else:
        _require(value["ref"] is None)
    if action in ADVANCED_ACTIONS:
        validate_advanced(action, params)
    elif action in {"open", "navigate"}:
        _require(set(params) == {"url"} and valid_url(params["url"]))
    elif action == "fill":
        # The editor pipeline issues one execCommand pair per line, so a fill
        # is line-bounded as well as length-bounded (a 30,000-newline fill
        # would otherwise freeze the tab). CR and CRLF both count: the
        # insertion feed normalizes them to line breaks. The length cap counts
        # UTF-16 code units — what every JavaScript layer of the pipeline
        # counts — so astral characters cannot slip past Python's code-point
        # len() and split the cap between layers.
        _require(set(params) == {"text"} and type(params["text"]) is str
                 and len(params["text"].encode("utf-16-le", "surrogatepass")) // 2 <= 30000
                 and "\x00" not in params["text"]
                 and len(re.sub(r"\r\n?", "\n", params["text"]).split("\n")) - 1 <= 2000)
    elif action == "read":
        # Paged whole-element text read: one observation ref plus the
        # character offset of the page to return.
        _require(set(params) == {"offset"} and type(params["offset"]) is int
                 and 0 <= params["offset"] <= 2000000)
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
