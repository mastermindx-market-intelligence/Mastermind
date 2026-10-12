"""Static, non-authorizing Product MCP contracts.

Executive OS owns runtime/admission. Macro/Terminal own market data and identity.
This module only names exact approved public producer observations; it provides no
product-user login, scheduler, session store, or source-publication authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from types import MappingProxyType
from typing import Any, Mapping
import json
import re

PROFILE = "mastermind.product_mcp.v1"
RESULT_SCHEMA = "mastermind.product_observation.v1"
SERVER_NAME = "Mastermind Product Observations"
SERVER_VERSION = "0.1.0"
READ_SCOPE = "mastermind.product.read"  # resource-specific issuer, when supported
OIDC_READ_SCOPE = "openid"             # Supabase OAuth 2.1 standard scope
ALLOWED_READ_SCOPES = frozenset({(READ_SCOPE,), (OIDC_READ_SCOPE,)})

# Static owner-selected sources. Neither tool accepts a URL or a bearer token.
SOURCES = MappingProxyType({
    ("macro", "status"): (
        "macro.public_status",
        "https://www.mastermind-x.com/api/status",
    ),
    ("macro", "overlay"): (
        "macro.public_live_overlay",
        "https://www.mastermind-x.com/api/overlay",
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
OVERLAY_BODY_CAP = 524288
MAX_BODY_CAP = OVERLAY_BODY_CAP

MANIFEST_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object", "properties": {}, "additionalProperties": False,
}
OBSERVE_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "product": {"type": "string", "enum": ["macro", "terminal"]},
        "view": {"type": "string", "enum": ["status", "market_risk", "overlay"]},
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
        if self.scopes not in ALLOWED_READ_SCOPES or type(self.expires_at) is not int:
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
    """Validate nested producer fields before copying a bounded JSON result.

    A trusted port can fail or return a structurally unexpected object. The
    transport must never blindly forward new fields such as tokens, cookies,
    user identifiers or private service URLs into the Web CEO transcript.
    """
    def refuse() -> None:
        raise ProductRefused("RESULT_UNVERIFIED")

    if not isinstance(value, Mapping) or set(value) != set(OUTPUT_SCHEMA["required"]):
        refuse()
    if value.get("schema") != RESULT_SCHEMA or value.get("profile") != PROFILE:
        refuse()
    tool, status = value.get("tool"), value.get("status")
    if tool not in _TOOL_NAMES or status not in ALLOWED_STATUSES:
        refuse()
    observed_at = value.get("observed_at")
    if (type(observed_at) is not str
        or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:[.][0-9]{1,6})?Z", observed_at) is None):
        refuse()
    try:
        datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
    except ValueError:
        refuse()
    caller = value.get("caller")
    if type(caller) is not dict or set(caller) != {"subject_digest", "client_ref"}:
        refuse()
    if not isinstance(caller["subject_digest"], str) or not _DIGEST.fullmatch(caller["subject_digest"]):
        refuse()
    if type(caller["client_ref"]) is not str or not 1 <= len(caller["client_ref"]) <= 128:
        refuse()
    fresh = value.get("freshness")
    allowed_fresh = {"qualified", "reasons", "clock_basis", "reported_age_minutes",
                     "source_session", "market_timezone", "owner_stale"}
    if type(fresh) is not dict or not set(fresh) <= allowed_fresh:
        refuse()
    if type(fresh.get("qualified")) is not bool or type(fresh.get("reasons")) is not list:
        refuse()
    if len(fresh["reasons"]) > 32 or any(
        type(r) is not str or len(r) > 100 or
        re.fullmatch(r"[A-Za-z0-9._:-]+", r) is None for r in fresh["reasons"]
    ):
        refuse()
    ages = fresh.get("reported_age_minutes")
    if ages is not None:
        if type(ages) is not dict or len(ages) > 12:
            refuse()
        for k, age in ages.items():
            if type(k) is not str or len(k) > 40 or type(age) not in (int, float):
                refuse()
    source = value.get("source")
    allowed_source = {"source_id", "evidence_class", "representation",
                      "http_status", "body_bytes", "body_sha256", "content_type",
                      "etag", "last_modified", "cache_age_seconds"}
    if source is not None:
        if type(source) is not dict or not set(source) <= allowed_source:
            refuse()
        if source.get("source_id") not in {x[0] for x in SOURCES.values()}:
            refuse()
        if source.get("evidence_class") != "public_upstream":
            refuse()
        if "body_sha256" in source and (
            type(source["body_sha256"]) is not str
            or _DIGEST.fullmatch(source["body_sha256"]) is None
        ):
            refuse()
        if "http_status" in source and type(source["http_status"]) is not int:
            refuse()
        if "body_bytes" in source and (
            type(source["body_bytes"]) is not int or source["body_bytes"] < 0
        ):
            refuse()
        if "representation" in source and source["representation"] not in (
            "complete", "retained_prefix", "not_observed"
        ):
            refuse()
        for key in ("etag", "content_type", "last_modified", "cache_age_seconds"):
            item = source.get(key)
            if item is not None and (
                type(item) is not str or len(item) > 150
                or any(ord(ch) < 32 or ord(ch) == 127 for ch in item)
            ):
                refuse()
    data = value.get("data")
    if type(data) is not dict:
        refuse()
    macro_fields = {"reported_status", "reported_service_commit",
                    "reported_site_commit", "checks"}
    risk_fields = {"schema", "verdict", "score", "asof", "built",
                   "source_event_time", "stale_after", "source_basis",
                   "cause_basis", "stale", "stale_reasons", "display_only"}
    overlay_fields = {"schema", "built", "quote_ts_max", "n", "n_fresh",
                      "n_quotes", "delayed_min", "reported_realtime",
                      "market", "sessions"}
    errors = {None, "READ_UNAVAILABLE", "REDIRECT_REFUSED",
              "UPSTREAM_ACCESS_REFUSED", "UPSTREAM_UNAVAILABLE",
              "INVALID_REPRESENTATION"}
    if type(value.get("error")) not in (str, type(None)) or value["error"] not in errors:
        refuse()
    if tool == "product_manifest":
        if source is not None or status != "OK":
            refuse()
        if set(data) != {"views", "mode", "private_product_user_grant_proven"}:
            refuse()
        if data["mode"] != "readonly" or data["private_product_user_grant_proven"] is not False:
            refuse()
        views = data["views"]
        if type(views) is not list or len(views) != len(SOURCES):
            refuse()
        for view in views:
            if type(view) is not dict or set(view) != {
                "product", "view", "source_id", "evidence_class"}:
                refuse()
            if (view.get("product"), view.get("view")) not in SOURCES:
                refuse()
            if (view["source_id"] != SOURCES[(view["product"], view["view"])][0]
                or view["evidence_class"] != "public_upstream"):
                refuse()
    else:
        if source is None:
            refuse()
        if status in ("OK", "PARTIAL", "STALE") and (
            value["error"] is not None
            or source.get("http_status") != 200
            or type(source.get("body_bytes")) is not int
            or source["body_bytes"] <= 0
            or source.get("representation") != "complete"
        ):
            refuse()
        selected_fields = {
            "macro.public_status": macro_fields,
            "macro.public_live_overlay": overlay_fields,
            "terminal.public_risk_projection": risk_fields,
        }[source["source_id"]]
        if not set(data) <= selected_fields:
            refuse()
        source_name = source["source_id"]
        if status == "INVALID" and data:
            refuse()
        if status in ("OK", "PARTIAL", "STALE"):
            if source_name == "macro.public_status":
                # The public status endpoint is not a whole-market freshness
                # authority; it only projects individual producer observations.
                if status != "PARTIAL" or fresh["qualified"] is not False or not data:
                    refuse()
                if type(data.get("reported_status")) is not str:
                    refuse()
            elif source_name == "macro.public_live_overlay":
                # A fast-price overlay is never the settled regime state, nor
                # are its quote/session clocks proof of true real-time data.
                if status != "PARTIAL" or fresh["qualified"] is not False or not data:
                    refuse()
            else:
                if not data:
                    # The risk owner can report unknown freshness without
                    # supplying a qualified verdict. Never call that healthy.
                    if status != "PARTIAL" or fresh["qualified"] is not False or not fresh["reasons"]:
                        refuse()
                else:
                    if (not {"schema", "verdict", "asof", "stale",
                             "stale_reasons", "display_only"} <= set(data)
                        or data["schema"] != "market_risk/v1"
                        or data["verdict"] not in ("RISK_ON", "MIXED", "RISK_OFF")
                        or type(data["stale"]) is not bool
                        or data["display_only"] is not True
                        or type(data["asof"]) is not str
                        or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", data["asof"]) is None):
                        refuse()
                    try:
                        date.fromisoformat(data["asof"])
                    except ValueError:
                        refuse()
                    if status == "OK" and (
                        data["stale"] or fresh["qualified"] is not True
                        or fresh["reasons"] or
                        type(data.get("score")) not in (int, float) or
                        not 0 <= data["score"] <= 100
                    ):
                        refuse()
                    if status != "OK" and (
                        fresh["qualified"] is not False or not fresh["reasons"]
                    ):
                        refuse()
        if source["source_id"] == "macro.public_live_overlay" and data:
            if (status not in ("PARTIAL", "STALE") or
                not {"schema", "built", "n", "n_fresh", "n_quotes",
                     "delayed_min", "reported_realtime", "market", "sessions"} <= set(data)
                or data["schema"] != "live.overlay.v2"
                or any(type(data[k]) is not int or not 0 <= data[k] <= 500
                       for k in ("n", "n_fresh", "n_quotes"))
                or data["n_fresh"] > data["n"]
                or type(data["delayed_min"]) is not int
                or not 0 <= data["delayed_min"] <= 1440
                or type(data["reported_realtime"]) is not bool
                or type(data["built"]) is not str
                or len(data["built"]) > 40):
                refuse()
            market, sessions = data["market"], data["sessions"]
            if (type(market) is not dict or
                not set(market) <= {"SPY", "QQQ", "VIX"}
                or type(sessions) is not dict or
                not set(sessions) <= {"us", "cn", "hk", "ca"}):
                refuse()
            market_fields = {"stale", "band", "data_state", "data_frozen",
                             "data_through", "session_state"}
            session_fields = {"state", "calendar_verified", "data_frozen",
                              "expected_session"}
            for rows, permitted in ((market, market_fields),
                                     (sessions, session_fields)):
                for entry in rows.values():
                    if type(entry) is not dict or not set(entry) <= permitted:
                        refuse()
                    if any(
                        value is not None and type(value) not in (str, bool)
                        or (type(value) is str and len(value) > 180)
                        for value in entry.values()
                    ):
                        refuse()
        if "checks" in data:
            checks = data["checks"]
            allowed_components = {"site", "overlay", "risk_state", "china_risk_state",
                                  "breadth", "prophet_live", "terminal_data",
                                  "flow_pulse", "basket_pulse", "orchestrator",
                                  "release_publications", "quotes"}
            allowed_check_fields = {"schema", "built", "as_of", "asof", "age_min",
                                    "stale", "fresh", "freshness", "commit",
                                    "source_asof", "pack_as_of", "pack_ok",
                                    "expected_now", "session_et", "status",
                                    "usable", "n", "coverage_pct"}
            if type(checks) is not dict or not set(checks) <= allowed_components:
                refuse()
            if any(type(fields) is not dict or not set(fields) <= allowed_check_fields
                   for fields in checks.values()):
                refuse()
        if "stale_reasons" in data and (
            type(data["stale_reasons"]) is not list or
            any(type(x) is not str or len(x) > 100 for x in data["stale_reasons"])
        ):
            refuse()
    try:
        wire = json.dumps(dict(value), allow_nan=False, ensure_ascii=False,
                          separators=(",", ":")).encode("utf-8")
        if len(wire) > RESULT_CAP:
            refuse()
        return json.loads(wire)
    except (ValueError, TypeError, UnicodeError) as exc:
        if isinstance(exc, ProductRefused):
            raise
        raise ProductRefused("RESULT_UNVERIFIED") from None
