"""Stateless Browser MCP facade over an existing owner and caller identity."""
from __future__ import annotations

import inspect
import json
import re
from typing import Any, Callable, Protocol
from urllib.parse import urlsplit

from jsonschema import Draft202012Validator

from .catalog import CATALOG_GENERATION, SCHEMA_DIGEST, catalog

EFFECTS = frozenset({"NOT_APPLIED", "APPLIED", "EFFECT_UNKNOWN"})
MAX_BYTES = 65_536
_CODE = re.compile(r"[A-Z][A-Z0-9_]{0,79}\Z")


class OwnerRefused(ValueError):
    """Existing owner attests a definite pre-effect refusal."""

    def __init__(self, code: str):
        if type(code) is not str or _CODE.fullmatch(code) is None:
            raise ValueError("invalid refusal code")
        self.code = code
        super().__init__(code)


class BrowserOwnerPort(Protocol):
    async def browser_fleet(self, caller: Any, args: dict) -> dict: ...
    async def browser_tabs(self, caller: Any, args: dict) -> dict: ...
    async def browser_snapshot(self, caller: Any, args: dict) -> dict: ...
    async def browser_screenshot(self, caller: Any, args: dict) -> dict: ...
    async def prepare_browser_action(self, caller: Any, args: dict) -> dict: ...
    async def run_browser_action(self, caller: Any, args: dict) -> dict: ...
    async def reconcile_browser_action(self, caller: Any, args: dict) -> dict: ...


def _snapshot(value: Any) -> dict:
    try:
        raw = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8", errors="strict")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise ValueError("invalid JSON value") from exc
    if len(raw) > MAX_BYTES:
        raise ValueError("oversize")
    decoded = json.loads(raw)
    if type(decoded) is not dict:
        raise ValueError("object required")
    return decoded


def _error(code: str, *, effect: str = "NOT_APPLIED") -> dict:
    return {
        "schema": "mastermind.browser_mcp_result.v1",
        "is_error": True,
        "code": code,
        "effect": effect,
        "retry_allowed": False,
    }


class BrowserFacade:
    def __init__(self, *, owner: BrowserOwnerPort, caller_resolver: Callable):
        rows = catalog()
        if not callable(caller_resolver) or any(
            not callable(getattr(owner, row["name"], None)) for row in rows
        ):
            raise TypeError("existing owner and trusted caller resolver are required")
        self._owner = owner
        self._caller_resolver = caller_resolver
        self._validators = {
            row["name"]: Draft202012Validator(row["inputSchema"]) for row in rows
        }
        self.schema_digest = SCHEMA_DIGEST

    def catalog(self) -> list[dict]:
        return catalog()

    async def call(self, name: str, arguments: dict) -> dict:
        if type(name) is not str or name not in self._validators:
            return _error("UNKNOWN_TOOL")
        try:
            args = _snapshot(arguments)
            self._validators[name].validate(args)
            if name == "prepare_browser_action":
                if args["action"] == "navigate":
                    value = args["args"]["url"]
                    parsed = urlsplit(value)
                    if (
                        parsed.scheme not in {"http", "https"}
                        or not parsed.hostname
                        or parsed.username is not None
                        or parsed.password is not None
                        or any(ord(ch) <= 32 for ch in value)
                    ):
                        raise ValueError("invalid URL")
                    _ = parsed.port
                if args["action"] == "type":
                    value = args["args"]["text"]
                    if "\x00" in value or len(value.encode("utf-8")) > 16384:
                        raise ValueError("invalid text")
        except Exception:
            return _error("INVALID_ARGUMENTS")

        try:
            caller = self._caller_resolver()
            if inspect.isawaitable(caller):
                caller = await caller
            if caller is None:
                raise ValueError("caller missing")
        except Exception:
            return _error("CALLER_UNAVAILABLE")

        uncertain = name in {"run_browser_action", "reconcile_browser_action"}
        try:
            result = await getattr(self._owner, name)(caller, args)
        except OwnerRefused as exc:
            return _error(exc.code)
        except Exception:
            return _error(
                "OWNER_UNAVAILABLE",
                effect="EFFECT_UNKNOWN" if uncertain else "NOT_APPLIED",
            )

        try:
            data = _snapshot(result)
            if uncertain:
                effect = data.get("effect")
                if effect not in EFFECTS:
                    raise ValueError("effect missing")
            else:
                effect = "NOT_APPLIED"
                if data.get("effect", "NOT_APPLIED") != "NOT_APPLIED":
                    raise ValueError("read smuggled effect")
            return _snapshot(
                {
                    "schema": "mastermind.browser_mcp_result.v1",
                    "catalog_generation": CATALOG_GENERATION,
                    "is_error": False,
                    "effect": effect,
                    "retry_allowed": False,
                    "data": data,
                }
            )
        except Exception:
            return _error(
                "OWNER_RESULT_INVALID",
                effect="EFFECT_UNKNOWN" if uncertain else "NOT_APPLIED",
            )
