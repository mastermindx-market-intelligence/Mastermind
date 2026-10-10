"""Static, non-authorizing Product MCP contracts.

Executive OS owns runtime/admission. Macro/Terminal own market data and identity.
This module only names two already-public producer observations; it provides no
product-user login, scheduler, session store, or source-publication authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping
import json
import re

PROFILE = "mastermind.product_mcp.v1"
RESULT_SCHEMA = "mastermind.product_observation.v1"
SERVER_NAME = "Mastermind Product Observations"
SERVER_VERSION = "0.1.0"
READ_SCOPE = "mastermind.product.read"

# Static owner-selected sources. Neither tool accepts a URL or a bearer token.
SOURCES = MappingProxyType({
    ("macro", "status"): (
        "macro.public_status",
        "https://www.mastermind-x.com/api/status",
    ),
    ("terminal", "market_risk"): (
        "terminal.public_risk_projection",
        "https://app.mastermind-x.com/data/market_risk.json",
    ),
})
ALLOWED_STATUSES = frozenset({
    "OK", "PARTIAL", "STALE", "MISSING", "INVALID",
    "UNAUTHORIZED", "FORBIDDEN", "DEPENDENCY_UNAVAILABLE",
})
_TOOL_NAMES = frozenset({"product_manifest", "product_observe"})
ARGUMENT_CAP = 2048
RESULT_CAP = 16384
BODY_CAP = 65536

MANIFEST_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object", "properties": {}, "additionalProperties": False,
}
OBSERVE_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "product": {"type": "string", "enum": ["macro", "terminal"]},
        "view": {"type": "string", "enum": ["status", "market_risk"]},
    },
    "required": ["product", "view"],
    "additionalProperties": False,
}
OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "schema": {"type": "string", "const": RESULT_SCHEMA},
        "profile": {"type": "string", "const": PROFILE},
        "tool": {"type": "string", "enum": sorted(_TOOL_NAMES)},
        "status": {"type": "string", "enum": sorted(ALLOWED_STATUSES)},
        "observed_at": {"type": "string"},
        "caller": {"type": "object"},
        "source": {"type": ["object", "null"]},
        "freshness": {"type": "object"},
        "data": {"type": "object"},
        "error": {"type": ["string", "null"]},
    },
    "required": ["schema", "profile", "tool", "status", "observed_at",
                 "caller", "source", "freshness", "data", "error"],
    "additionalProperties": False,
}

_DIGEST = re.compile(r"^[0-9a-f]{64}$")


class ProductRefused(ValueError):
    """Closed error codes: never echo raw provider or token text."""
    def __init__(self, code: str = "PRODUCT_REFUSED") -> None:
        if code not in {
            "INVALID_REQUEST", "PRODUCT_REFUSED", "AUTHENTICATION_REQUIRED",
            "AUTHENTICATION_CHANGED", "PRODUCT_GRANT_CHANGED", "READ_UNAVAILABLE",
            "RESULT_UNVERIFIED", "TOOL_NOT_AVAILABLE",
        }:
            raise ValueError("unsupported product refusal")
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class ProductCaller:
    """Projection of an existing verified MCP access context, not a new grant."""
    subject_digest: str
    client_ref: str
    resource: str
    scopes: tuple[str, ...]
    expires_at: int

    def __post_init__(self) -> None:
        if not isinstance(self.subject_digest, str) or not _DIGEST.fullmatch(self.subject_digest):
            raise ProductRefused("AUTHENTICATION_REQUIRED")
        if not isinstance(self.client_ref, str) or not self.client_ref:
            raise ProductRefused("AUTHENTICATION_REQUIRED")
        if not isinstance(self.resource, str) or not self.resource.startswith("https://"):
            raise ProductRefused("AUTHENTICATION_REQUIRED")
        if self.scopes != (READ_SCOPE,) or type(self.expires_at) is not int:
            raise ProductRefused("AUTHENTICATION_REQUIRED")

    def public_identity(self) -> dict[str, str]:
        # Never emit raw JWT, user email, cookie, or token-derived free-form data.
        return {"subject_digest": self.subject_digest, "client_ref": self.client_ref}


def canonical_arguments(tool: str, arguments: Any) -> Mapping[str, str]:
    if tool not in _TOOL_NAMES:
        raise ProductRefused("TOOL_NOT_AVAILABLE")
    if not isinstance(arguments, dict):
        raise ProductRefused("INVALID_REQUEST")
    try:
        raw = json.dumps(arguments, ensure_ascii=False, allow_nan=False,
                         separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise ProductRefused("INVALID_REQUEST") from None
    if len(raw) > ARGUMENT_CAP:
        raise ProductRefused("INVALID_REQUEST")
    if tool == "product_manifest":
        if arguments:
            raise ProductRefused("INVALID_REQUEST")
        return MappingProxyType({})
    if set(arguments) != {"product", "view"}:
        raise ProductRefused("INVALID_REQUEST")
    product, view = arguments["product"], arguments["view"]
    if type(product) is not str or type(view) is not str or (product, view) not in SOURCES:
        raise ProductRefused("INVALID_REQUEST")
    return MappingProxyType({"product": product, "view": view})


def canonical_result(value: Mapping[str, Any]) -> dict[str, Any]:
    """Freeze JSON data, apply a whole-frame byte cap, reject NaN/unknown fields."""
    if not isinstance(value, Mapping) or set(value) != set(OUTPUT_SCHEMA["required"]):
        raise ProductRefused("RESULT_UNVERIFIED")
    if value.get("schema") != RESULT_SCHEMA or value.get("profile") != PROFILE:
        raise ProductRefused("RESULT_UNVERIFIED")
    if value.get("tool") not in _TOOL_NAMES or value.get("status") not in ALLOWED_STATUSES:
        raise ProductRefused("RESULT_UNVERIFIED")
    try:
        wire = json.dumps(dict(value), allow_nan=False, ensure_ascii=False,
                          separators=(",", ":")).encode("utf-8")
        if len(wire) > RESULT_CAP:
            raise ProductRefused("RESULT_UNVERIFIED")
        return json.loads(wire)
    except (ValueError, TypeError, UnicodeError) as exc:
        if isinstance(exc, ProductRefused):
            raise
        raise ProductRefused("RESULT_UNVERIFIED") from None
