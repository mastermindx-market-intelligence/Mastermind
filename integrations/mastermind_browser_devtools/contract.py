"""Closed contract for a private Chrome DevTools MCP browser backend.

This module does not launch Chrome, open a debugging connection, issue MCP calls,
authenticate a caller, select a host, allocate a browser, persist an effect, or
retry anything. It projects trusted host configuration and closed Mastermind
browser actions into one pinned private backend. The existing Browser/Runtime/
Capacity owners remain authoritative for admission, placement, locking and
effect reconciliation.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
import hashlib
import json
import re
from urllib.parse import urlsplit

DEVTOOLS_MCP_VERSION = "1.10.1"
_TOOL_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_UID = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")

ALLOWED_BACKEND_TOOLS = frozenset({
    "list_pages",
    "take_snapshot",
    "take_screenshot",
    "wait_for",
    "click",
    "fill",
    "type_text",
    "press_key",
    "navigate_page",
})

READ_ONLY_BACKEND_TOOLS = frozenset({
    "list_pages", "take_snapshot", "take_screenshot", "wait_for",
})
MUTATING_BACKEND_TOOLS = ALLOWED_BACKEND_TOOLS - READ_ONLY_BACKEND_TOOLS

_ALLOWED_KEYS = frozenset({
    "Enter", "Tab", "Escape", "Backspace", "Delete",
    "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight",
    "PageUp", "PageDown", "Home", "End",
})


class BackendContractError(ValueError):
    """Closed refusal for a malformed or over-broad backend projection."""


@dataclass(frozen=True, slots=True)
class BackendPlan:
    command: str
    argv: tuple[str, ...]
    backend_version: str
    observed_tool_schema_digest: str
    attachment_mode: str
    requires_browser_user_consent: bool
    page_id_routing: bool
    allowed_backend_tools: frozenset[str]

    @property
    def is_admission(self) -> bool:
        return False


@dataclass(frozen=True, slots=True)
class BackendToolCall:
    tool_name: str
    arguments: dict[str, object]


def _absolute(value: object, name: str) -> str:
    if type(value) is not str or not value.startswith("/") or "\x00" in value:
        raise BackendContractError(f"{name} must be an absolute path")
    path = PurePosixPath(value)
    if ".." in path.parts or "." in path.parts or str(path) != value.rstrip("/"):
        raise BackendContractError(f"{name} must be normalized")
    return value


def _positive_page_id(value: object) -> int:
    if type(value) is not int or value < 1:
        raise BackendContractError("page_id must be a positive integer")
    return value


def _closed_dict(value: object, allowed: frozenset[str]) -> dict[str, object]:
    if type(value) is not dict or any(type(k) is not str for k in value):
        raise BackendContractError("arguments must be a closed object")
    if not set(value) <= allowed:
        raise BackendContractError("unexpected backend argument")
    return dict(value)


def _text(value: object, name: str, *, maximum: int, allow_empty: bool = False) -> str:
    if type(value) is not str or (not allow_empty and not value):
        raise BackendContractError(f"{name} is invalid")
    if "\x00" in value or len(value.encode("utf-8", errors="strict")) > maximum:
        raise BackendContractError(f"{name} is invalid")
    return value


def _uid(value: object) -> str:
    if type(value) is not str or _UID.fullmatch(value) is None:
        raise BackendContractError("uid is invalid")
    return value


def _http_url(value: object) -> str:
    url = _text(value, "url", maximum=2048)
    if any(ord(ch) <= 32 for ch in url):
        raise BackendContractError("url is invalid")
    try:
        parsed = urlsplit(url)
        _ = parsed.port
    except (TypeError, ValueError) as exc:
        raise BackendContractError("url is invalid") from exc
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise BackendContractError("url is invalid")
    return url


@dataclass(frozen=True, slots=True)
class BackendCatalogAttestation:
    selected_tools: tuple[str, ...]
    schema_digest: str

    @property
    def is_admission(self) -> bool:
        return False


def attest_backend_catalog(value: object) -> BackendCatalogAttestation:
    """Bind the selected private-backend tool schemas without granting them."""
    if type(value) is not dict or set(value) != {"tools"}:
        raise BackendContractError("backend catalog is invalid")
    rows = value["tools"]
    if type(rows) is not list:
        raise BackendContractError("backend catalog tools are invalid")

    by_name: dict[str, dict[str, object]] = {}
    for row in rows:
        if type(row) is not dict:
            raise BackendContractError("backend catalog row is invalid")
        name = row.get("name")
        schema = row.get("inputSchema")
        if type(name) is not str or not name or name in by_name or type(schema) is not dict:
            raise BackendContractError("backend catalog row is invalid")
        by_name[name] = row

    if not ALLOWED_BACKEND_TOOLS <= set(by_name):
        raise BackendContractError("backend catalog lacks a selected tool")

    selected: list[dict[str, object]] = []
    for name in sorted(ALLOWED_BACKEND_TOOLS):
        schema = by_name[name]["inputSchema"]
        if type(schema) is not dict or schema.get("type") != "object":
            raise BackendContractError("selected backend schema is invalid")
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        if type(properties) is not dict or type(required) is not list or any(
            type(item) is not str for item in required
        ):
            raise BackendContractError("selected backend schema is invalid")
        if name == "list_pages":
            if "pageId" in properties or "pageId" in required:
                raise BackendContractError("list_pages cannot be page scoped")
        else:
            page = properties.get("pageId")
            if (
                type(page) is not dict
                or page.get("type") not in {"number", "integer"}
                or "pageId" not in required
            ):
                raise BackendContractError("page-scoped tool lacks required pageId")
        try:
            canonical_schema = json.loads(
                json.dumps(
                    schema,
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=True,
                    allow_nan=False,
                )
            )
        except (TypeError, ValueError):
            raise BackendContractError("selected backend schema is invalid") from None
        selected.append({"name": name, "inputSchema": canonical_schema})

    raw = json.dumps(
        selected,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return BackendCatalogAttestation(
        selected_tools=tuple(sorted(ALLOWED_BACKEND_TOOLS)),
        schema_digest=hashlib.sha256(raw).hexdigest(),
    )


def build_auto_connect_plan(
    *,
    node_executable: object,
    cli_path: object,
    user_data_dir: object,
    installed_version: object,
    observed_tool_schema_digest: object,
) -> BackendPlan:
    """Project one already-enrolled existing Chrome profile into a private backend.

    The caller owns the host/process configuration. This plan is not permission
    to enable Chrome remote debugging or accept its user-consent prompt.
    """
    node = _absolute(node_executable, "node_executable")
    cli = _absolute(cli_path, "cli_path")
    profile = _absolute(user_data_dir, "user_data_dir")
    if not cli.endswith(
        "/node_modules/chrome-devtools-mcp/build/src/bin/chrome-devtools-mcp.js"
    ):
        raise BackendContractError("cli_path is not the pinned Chrome DevTools MCP entrypoint")
    if installed_version != DEVTOOLS_MCP_VERSION:
        raise BackendContractError("Chrome DevTools MCP version mismatch")
    if (
        type(observed_tool_schema_digest) is not str
        or _TOOL_DIGEST.fullmatch(observed_tool_schema_digest) is None
    ):
        raise BackendContractError("tool schema digest is invalid")

    argv = (
        cli,
        "--autoConnect",
        "--pageIdRouting",
        f"--userDataDir={profile}",
        "--no-usage-statistics",
        "--no-performance-crux",
        "--no-category-performance",
        "--no-category-network",
        "--no-category-memory",
        "--no-category-emulation",
        "--no-javascript-evaluation",
        "--screenshot-format=jpeg",
        "--screenshot-quality=70",
        "--screenshot-max-width=1600",
        "--screenshot-max-height=1200",
    )
    return BackendPlan(
        command=node,
        argv=argv,
        backend_version=DEVTOOLS_MCP_VERSION,
        observed_tool_schema_digest=observed_tool_schema_digest,
        attachment_mode="existing_chrome_autoconnect",
        requires_browser_user_consent=True,
        page_id_routing=True,
        allowed_backend_tools=ALLOWED_BACKEND_TOOLS,
    )


def project_backend_call(
    tool_name: object,
    *,
    page_id: object,
    arguments: object,
) -> BackendToolCall:
    """Map one owner-approved action into the pinned private backend surface."""
    if type(tool_name) is not str or tool_name not in ALLOWED_BACKEND_TOOLS:
        raise BackendContractError("backend tool is not allowed")

    if tool_name == "list_pages":
        if page_id is not None:
            raise BackendContractError("list_pages cannot carry page_id")
        args = _closed_dict(arguments, frozenset())
        if args:
            raise BackendContractError("list_pages has no arguments")
        return BackendToolCall("list_pages", {})

    pid = _positive_page_id(page_id)

    if tool_name == "take_snapshot":
        args = _closed_dict(arguments, frozenset({"verbose"}))
        if "verbose" in args and type(args["verbose"]) is not bool:
            raise BackendContractError("verbose must be boolean")
        projected: dict[str, object] = {"pageId": pid}
        if "verbose" in args:
            projected["verbose"] = args["verbose"]
        return BackendToolCall(tool_name, projected)

    if tool_name == "take_screenshot":
        args = _closed_dict(arguments, frozenset())
        if args:
            raise BackendContractError("screenshot options are controller-owned")
        return BackendToolCall(
            tool_name,
            {
                "pageId": pid,
                "format": "jpeg",
                "quality": 70,
                "fullPage": False,
            },
        )

    if tool_name == "click":
        args = _closed_dict(arguments, frozenset({"uid"}))
        if set(args) != {"uid"}:
            raise BackendContractError("click requires uid")
        return BackendToolCall(
            tool_name,
            {
                "pageId": pid,
                "uid": _uid(args["uid"]),
                "dblClick": False,
                "includeSnapshot": False,
            },
        )

    if tool_name == "fill":
        args = _closed_dict(arguments, frozenset({"uid", "value"}))
        if set(args) != {"uid", "value"}:
            raise BackendContractError("fill requires uid and value")
        return BackendToolCall(
            tool_name,
            {
                "pageId": pid,
                "uid": _uid(args["uid"]),
                "value": _text(args["value"], "value", maximum=16384, allow_empty=True),
                "includeSnapshot": False,
            },
        )

    if tool_name == "type_text":
        args = _closed_dict(arguments, frozenset({"text"}))
        if set(args) != {"text"}:
            raise BackendContractError("type_text requires text")
        return BackendToolCall(
            tool_name,
            {
                "pageId": pid,
                "text": _text(args["text"], "text", maximum=16384, allow_empty=True),
            },
        )

    if tool_name == "press_key":
        args = _closed_dict(arguments, frozenset({"key"}))
        if set(args) != {"key"} or args["key"] not in _ALLOWED_KEYS:
            raise BackendContractError("key is not in the closed key set")
        return BackendToolCall(
            tool_name,
            {"pageId": pid, "key": args["key"], "includeSnapshot": False},
        )

    if tool_name == "navigate_page":
        args = _closed_dict(arguments, frozenset({"url"}))
        if set(args) != {"url"}:
            raise BackendContractError("navigate_page requires url")
        return BackendToolCall(
            tool_name,
            {
                "pageId": pid,
                "type": "url",
                "url": _http_url(args["url"]),
                "handleBeforeUnload": "dismiss",
            },
        )

    if tool_name == "wait_for":
        args = _closed_dict(arguments, frozenset({"text"}))
        if set(args) != {"text"} or type(args["text"]) is not list:
            raise BackendContractError("wait_for requires a text list")
        values = args["text"]
        if not 1 <= len(values) <= 8:
            raise BackendContractError("wait_for text list is invalid")
        selected = [_text(value, "wait text", maximum=1024) for value in values]
        return BackendToolCall(
            tool_name,
            {"pageId": pid, "text": selected, "timeout": 5000},
        )

    raise BackendContractError("unreachable backend tool")
